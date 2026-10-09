#
#  ISC License
#
#  Copyright (c) 2026, Autonomous Vehicle Systems Lab, University of Colorado at Boulder
#
#  Permission to use, copy, modify, and/or distribute this software for any
#  purpose with or without fee is hereby granted, provided that the above
#  copyright notice and this permission notice appear in all copies.
#
#  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
#  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
#  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
#  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
#  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
#  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
#  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#
"""The command palette (UX/UI guidelines, "a command palette"): every
menu command and tab, found by typing part of its name."""

from PySide6.QtCore import Qt

from spacemissionstudio.gui.command_palette import CommandPalette, PaletteEntry, matches


def _entries(calls):
    return [PaletteEntry("File > Save As...", lambda: calls.append("save as"), "Ctrl+Shift+S"),
            PaletteEntry("File > Save", lambda: calls.append("save"), "Ctrl+S"),
            PaletteEntry("Run > Run Simulation", lambda: calls.append("run"), "Ctrl+R"),
            PaletteEntry("Run > Abort Simulation", lambda: calls.append("abort"), enabled=False),
            PaletteEntry("Go to tab > Events", lambda: calls.append("events"))]


def test_every_word_must_match_and_name_prefixes_come_first():
    entries = _entries([])
    assert [e.label for e in matches("save as", entries)] == ["File > Save As..."]
    assert [e.label for e in matches("s", entries)][:2] == ["File > Save As...", "File > Save"]
    # the menu name counts too: "run" also finds Run > Abort, ranked after the name match
    assert [e.label for e in matches("RUN SIM", entries)] == ["Run > Run Simulation", "Run > Abort Simulation"]
    assert matches("", entries) == entries
    assert matches("nothing like this", entries) == []


def test_enter_runs_the_highlighted_command_and_skips_disabled_ones(qtbot):
    calls = []
    palette = CommandPalette(_entries(calls))
    qtbot.addWidget(palette)
    qtbot.keyClicks(palette.search, "simulation")
    assert palette.list.count() == 2
    assert palette.list.currentItem().text().startswith("Run > Run Simulation")  # the enabled one
    qtbot.keyClick(palette.search, Qt.Key.Key_Down)  # the disabled abort is not selectable
    assert palette.list.currentItem().text().startswith("Run > Run Simulation")
    qtbot.keyClick(palette.search, Qt.Key.Key_Return)
    assert calls == ["run"] and palette.ran.label == "Run > Run Simulation"


def test_nothing_matching_says_so(qtbot):
    palette = CommandPalette(_entries([]))
    qtbot.addWidget(palette)
    palette.search.setText("zzz")
    assert palette.list.count() == 0 and palette.hint.text() == "Nothing matches."
    palette.run_current()  # nothing to run, no error
    assert palette.ran is None


def test_the_main_window_lists_its_menus_and_tabs_on_ctrl_k(qtbot):
    from spacemissionstudio.gui.main_window import MainWindow

    window = MainWindow(prompt_startup_fetch=False, check_autosave_recovery=False)
    qtbot.addWidget(window)
    assert window.palette_action.shortcut().toString() == "Ctrl+K"
    labels = [e.label for e in window.palette_entries()]
    assert "Run > Run Simulation" in labels and "Go to tab > Events" in labels
    assert not any(label.endswith("Command Palette...") for label in labels)
    go_events = next(e for e in window.palette_entries() if e.label == "Go to tab > Events")
    go_events.run()
    assert window.right_tabs.currentWidget() is window.event_timeline_widget
    assert any(label.startswith("Open template > 05 formation flying") for label in labels)


def test_the_palette_shows_a_series_of_the_result(qtbot):
    import numpy as np

    from spacemissionstudio.engine.results import ResultSet, TimeSeries
    from spacemissionstudio.gui.main_window import MainWindow

    window = MainWindow(prompt_startup_fetch=False, check_autosave_recovery=False)
    qtbot.addWidget(window)
    result = ResultSet("r")
    for name in ("sat-1.position_N", "sat-1.velocity_N"):
        result.add(TimeSeries(name, np.arange(3.0), ("x", "y", "z"), np.zeros((3, 3)), units="m"))
    window.results_widget.set_result(result)
    entry = next(e for e in window.palette_entries() if e.label == "Show series > sat-1.velocity_N")
    entry.run()
    assert window.results_widget.current_series_name() == "sat-1.velocity_N"
    assert window.right_tabs.currentWidget() is window.results_widget
