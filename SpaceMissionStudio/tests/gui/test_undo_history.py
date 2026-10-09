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
"""Undo and redo of scenario edits (UX/UI guidelines, "undo and redo")."""

import pytest

from spacemissionstudio.gui.undo_history import ScenarioHistory


def test_undo_and_redo_walk_the_recorded_states():
    history = ScenarioHistory()
    history.reset({"name": "a"})
    assert not history.can_undo()
    assert history.record({"name": "b"}) and history.record({"name": "c"})
    assert history.record({"name": "c"}) is False  # nothing changed
    assert history.undo() == {"name": "b"} and history.undo() == {"name": "a"}
    assert history.undo() is None
    assert history.redo() == {"name": "b"}
    history.record({"name": "d"})  # a new edit drops what could be redone
    assert not history.can_redo() and history.undo() == {"name": "b"}


def test_states_are_copies_and_the_history_is_capped():
    history = ScenarioHistory(max_steps=3)
    state = {"list": [1]}
    history.reset(state)
    state["list"].append(2)  # the caller changing its dict does not change the history
    for n in range(5):
        history.record({"n": n})
    steps = 0
    while history.undo() is not None:
        steps += 1
    assert steps == 3


@pytest.fixture
def window(qtbot, monkeypatch):
    """A main window whose close never waits on the unsaved-changes prompt
    (as tests/gui/test_main_window.py: offscreen, nothing would answer it)."""
    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.gui.main_window import MainWindow

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard))

    w = MainWindow(prompt_startup_fetch=False, check_autosave_recovery=False)
    qtbot.addWidget(w)
    return w


def test_the_edit_menu_undoes_and_redoes_scenario_edits(window, qtbot):
    """Each settled edit is one step; undo brings back the earlier
    scenario in the editor, redo the later one."""
    editor = window.scenario_editor
    original = editor.name_edit.text()
    assert not window.undo_action.isEnabled()
    editor.name_edit.setText("first edit")
    window._history_timer.stop()
    window._record_history()  # as the settle timer would
    editor.name_edit.setText("second edit")  # not yet settled: undo records it first
    window.undo_action.trigger()
    assert editor.name_edit.text() == "first edit"
    window.undo_action.trigger()
    assert editor.name_edit.text() == original and not window.undo_action.isEnabled()
    window.redo_action.trigger()
    window.redo_action.trigger()
    assert editor.name_edit.text() == "second edit" and not window.redo_action.isEnabled()
    assert window._dirty


def test_an_unfinished_scenario_is_recorded_and_loading_starts_a_new_history(window):
    """A scenario being built is invalid until it has a spacecraft; its
    edits are undoable all the same. New starts the history again."""
    editor = window.scenario_editor
    editor.name_edit.setText("")  # an empty name does not validate
    window._history_timer.stop()
    window._record_history()
    assert window.undo_action.isEnabled()
    window.undo_action.trigger()
    assert editor.name_edit.text() != ""
    window._dirty = False
    window.on_new()
    assert not window.undo_action.isEnabled() and not window.redo_action.isEnabled()
