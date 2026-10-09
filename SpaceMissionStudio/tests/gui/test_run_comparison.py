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
"""Run comparison (UX/UI guidelines: keep finished runs in the session,
overlay a series from several runs, a diff of their inputs)."""

import numpy as np
import pytest

from spacemissionstudio.engine.results import ResultSet, TimeSeries
from spacemissionstudio.gui.run_history import RunHistory


def _result(offset_m):
    t = np.arange(0.0, 3600.0, 60.0)  # [s]
    result = ResultSet("demo")
    result.add(TimeSeries("sat-1.orbit_elements.semi_major_axis", t, ("semi_major_axis",),
                          np.full((t.size, 1), 6928e3 + offset_m), units="m"))
    return result


def test_the_history_keeps_the_last_runs_numbered():
    history = RunHistory(max_runs=2)
    for n in range(3):
        history.add({"name": f"s{n}"}, _result(0.0), "2026-01-01T00:00:00")
    assert [r.number for r in history.runs] == [2, 3]
    assert history.latest().label.startswith("Run 3 (") and history.latest().label.endswith("s2")
    assert history.find(1) is None and history.find(2).scenario == {"name": "s1"}


@pytest.fixture
def results(qtbot):
    from spacemissionstudio.gui.results_widget import ResultsWidget

    widget = ResultsWidget()
    qtbot.addWidget(widget)
    history = RunHistory()
    first = history.add({"name": "demo", "sim_settings": {"duration_days": 1.0}}, _result(0.0), "2026-01-01T00:00:00")
    second = history.add({"name": "demo", "sim_settings": {"duration_days": 2.0}}, _result(500.0),
                         "2026-01-01T00:00:00", cancelled=True)
    widget.set_result(second.result, second.epoch_utc)
    widget.set_runs(history.runs, second)
    return widget, first, second


def test_an_earlier_run_is_overlaid_dashed_and_named(results):
    widget, first, _second = results
    assert widget.compare_combo.isVisibleTo(widget) and widget.compare_combo.count() == 2
    assert len(widget.figure.data) == 1
    widget.compare_combo.setCurrentIndex(widget.compare_combo.findData(first.number))
    traces = widget.figure.data
    assert len(traces) == 2 and traces[1].line.dash == "dash" and traces[1].name.endswith("(Run 1)")
    assert widget.figure.layout.showlegend
    assert np.allclose(np.asarray(traces[0].y) - np.asarray(traces[1].y), 0.5)  # [km] the 500 m offset


def test_the_input_differences_name_the_changed_fields(results, monkeypatch):
    from PySide6.QtWidgets import QDialog

    widget, first, _second = results
    widget.compare_combo.setCurrentIndex(widget.compare_combo.findData(first.number))
    assert widget.input_differences() == [("sim_settings.duration_days", 2.0, 1.0)]
    shown = []
    monkeypatch.setattr(QDialog, "exec", lambda self: shown.append(self.windowTitle()) or 0)
    widget.diff_button.click()
    assert shown == ["Input differences"]


def test_no_earlier_run_hides_the_comparison(qtbot):
    from spacemissionstudio.gui.results_widget import ResultsWidget

    widget = ResultsWidget()
    qtbot.addWidget(widget)
    history = RunHistory()
    only = history.add({"name": "demo"}, _result(0.0), "2026-01-01T00:00:00")
    widget.set_runs(history.runs, only)
    assert not widget.compare_combo.isVisibleTo(widget) and widget.input_differences() == []
