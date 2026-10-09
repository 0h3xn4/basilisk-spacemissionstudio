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

"""The Monte Carlo tab: a batch's tiles, plots and run table, from its
pickle-free summary; and when the main window shows the tab."""

import csv
import math
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.requires_gui

_R_M = 6778.0e3  # [m]
_N_RAD_S = math.sqrt(3.986004415e14 / _R_M ** 3)  # [rad/s]


def _save_batch(folder, runs=5, names=("sat-1",)):
    """A synthetic batch: circular orbits 0.1 mrad apart along track, run k
    drawing Cd = 2.0 + 0.2 k, saved as engine.monte_carlo_results does."""
    from spacemissionstudio.engine import monte_carlo_results as mcr

    t = np.linspace(0.0, 3000.0, 30)  # [s]
    phase = (np.arange(runs) - (runs - 1) / 2) * 1e-4  # [rad]
    u = _N_RAD_S * t[None, :] + phase[:, None]
    r = np.stack([_R_M * np.cos(u), _R_M * np.sin(u), np.zeros_like(u)], axis=-1)
    v = np.stack([-_R_M * _N_RAD_S * np.sin(u), _R_M * _N_RAD_S * np.cos(u), np.zeros_like(u)], axis=-1)
    batch = mcr.MonteCarloBatch("Synthetic batch", "earth", t, list(range(runs)), [runs],
                                {n: r for n in names}, {n: v for n in names},
                                [{f"{names[0]} drag coefficient [-]": 2.0 + 0.2 * k} for k in range(runs)],
                                "2030-01-01T00:00:00")
    mcr.save(batch, folder)
    return batch


def _tile_texts(widget):
    from PySide6.QtWidgets import QLabel

    texts = []
    for i in range(widget.tiles_row.count()):
        tile = widget.tiles_row.itemAt(i).widget()
        if tile is not None:
            texts.append(" | ".join(label.text() for label in tile.findChildren(QLabel)))
    return texts


def test_a_saved_batch_shows_tiles_plots_and_a_sortable_run_table(qtbot, tmp_path):
    """Five runs plus one failed: the tiles count them and give the final
    spread, the plots open on the spread, the table lists every run."""
    from spacemissionstudio.gui.monte_carlo_results_widget import MonteCarloResultsWidget

    _save_batch(tmp_path)
    widget = MonteCarloResultsWidget()
    qtbot.addWidget(widget)
    assert widget.load_folder(tmp_path)
    assert widget.title_label.text() == "Synthetic batch"
    tiles = _tile_texts(widget)
    assert tiles[0] == "5 of 6 | Runs" and tiles[1] == "5 | Failed"
    along_km = np.std((np.arange(5) - 2) * 1e-4) * _R_M / 1e3  # [km]
    assert tiles[2] == f"{along_km:.3g} km | Along-track spread, end"
    assert widget.plots.series_combo.currentData() == "sat-1.monte_carlo.spread"
    table = widget.table
    assert table.rowCount() == 5
    headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
    assert headers[:2] == ["Run", "drag coefficient [-]"]  # one spacecraft: its name is not repeated
    from PySide6.QtCore import Qt

    table.sortItems(1, Qt.SortOrder.DescendingOrder)  # by Cd: a numeric sort, not text
    assert [table.item(r, 0).text() for r in range(5)] == ["4", "3", "2", "1", "0"]
    assert not widget.spacecraft_combo.isVisible()


def test_the_run_table_exports_to_csv(qtbot, tmp_path):
    from spacemissionstudio.gui.monte_carlo_results_widget import MonteCarloResultsWidget

    _save_batch(tmp_path)
    widget = MonteCarloResultsWidget()
    qtbot.addWidget(widget)
    widget.load_folder(tmp_path)
    rows = list(csv.reader(widget.export_table_csv(tmp_path / "runs.csv").open(encoding="utf-8")))
    assert rows[0][:2] == ["Run", "sat-1 drag coefficient [-]"]
    assert [row[0] for row in rows[1:]] == ["0", "1", "2", "3", "4"]
    assert float(rows[3][1]) == pytest.approx(2.4)


def test_a_folder_without_results_says_so_and_shows_nothing(qtbot, tmp_path):
    from spacemissionstudio.gui.monte_carlo_results_widget import MonteCarloResultsWidget

    widget = MonteCarloResultsWidget()
    qtbot.addWidget(widget)
    assert widget.views.isHidden()
    assert not widget.load_folder(tmp_path)
    assert "has no Monte Carlo results" in widget.hint_label.text()
    assert widget.batch is None and widget.views.isHidden() and _tile_texts(widget) == []


def test_several_spacecraft_choose_whose_spread_is_shown(qtbot, tmp_path):
    from spacemissionstudio.gui.monte_carlo_results_widget import MonteCarloResultsWidget

    _save_batch(tmp_path, names=("chief", "follower"))
    widget = MonteCarloResultsWidget()
    qtbot.addWidget(widget)
    widget.load_folder(tmp_path)
    assert not widget.spacecraft_combo.isHidden()
    widget.spacecraft_combo.setCurrentText("follower")
    assert widget.plots.series_combo.currentData() == "follower.monte_carlo.spread"
    assert widget.table.horizontalHeaderItem(widget.table.columnCount() - 1).text().startswith("follower final")


def test_per_run_series_are_drawn_as_one_ensemble(qtbot, tmp_path):
    """Interchangeable runs get one colour, thin translucent lines and a
    single legend entry, and the hover shows the run under the pointer --
    not a colour each from a cycled palette and a 20-row hover box."""
    from spacemissionstudio.gui.monte_carlo_results_widget import MonteCarloResultsWidget

    _save_batch(tmp_path)
    widget = MonteCarloResultsWidget()
    qtbot.addWidget(widget)
    widget.load_folder(tmp_path)
    widget.plots.show_series("sat-1.monte_carlo.along_track_offset")
    fig = widget.plots.figure
    runs = [trace for trace in fig.data if trace.legendgroup == "runs"]
    assert len(runs) == 5
    assert len({trace.line.color for trace in runs}) == 1
    assert [trace.showlegend for trace in runs] == [True, False, False, False, False]
    assert runs[0].name == "Each run (5)" and fig.layout.hovermode == "closest"
    widget.plots.show_series("sat-1.monte_carlo.spread")  # three distinct quantities: a colour and entry each
    assert len({trace.line.color for trace in widget.plots.figure.data}) == 3


def test_the_main_window_shows_the_tab_only_when_it_has_something(qtbot, tmp_path, monkeypatch):
    """Nine tabs no longer fit a typical window: the Monte Carlo tab shows
    for a scenario with Monte Carlo on, or once a batch is open."""
    from PySide6.QtWidgets import QFileDialog

    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.main_window import MainWindow

    window = MainWindow(prompt_startup_fetch=False, check_autosave_recovery=False)
    qtbot.addWidget(window)
    tabs, tab = window.right_tabs, window.monte_carlo_results_widget
    assert not tabs.isTabVisible(tabs.indexOf(tab))
    window.open_path(TEMPLATES_DIR / "09_monte_carlo_dispersion_analysis.json")
    assert tabs.isTabVisible(tabs.indexOf(tab))
    window.open_path(TEMPLATES_DIR / "01_two_body_circular_orbit.json")
    assert not tabs.isTabVisible(tabs.indexOf(tab))

    _save_batch(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: str(tmp_path))
    window.open_monte_carlo_results_action.trigger()
    assert tabs.isTabVisible(tabs.indexOf(tab)) and tabs.currentWidget() is tab
    assert tab.folder == Path(tmp_path)
