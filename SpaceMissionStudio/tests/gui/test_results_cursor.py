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
"""The shared time cursor on the Results plots (UX/UI guidelines, "one
shared time cursor across views"): drawn as a line, moved without a page
reload, and set by a click on the plot."""

import numpy as np
import pytest

from spacemissionstudio.engine.results import ResultSet, TimeSeries
from spacemissionstudio.gui.time_cursor import TimeCursor

_PAGE_LOAD_TIMEOUT_MS = 30000  # [ms] as tests/gui/test_results_widget.py (SRelD K-10)


def _result():
    t = np.arange(0.0, 7200.0, 60.0)  # [s]
    result = ResultSet("demo")
    result.add(TimeSeries("sat-1.semi_major_axis", t, ("a",), np.full((t.size, 1), 6928e3), units="m"))
    return result


@pytest.fixture
def plot(qtbot):
    """A shown results widget following a cursor, with a loaded plot."""
    from spacemissionstudio.gui.results_widget import ResultsWidget

    widget = ResultsWidget()
    qtbot.addWidget(widget)
    with qtbot.waitExposed(widget):
        widget.show()
    cursor = TimeCursor()
    widget.set_time_cursor(cursor)
    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS):
        widget.set_result(_result(), "2026-01-01T00:00:00")
    return widget, cursor


def _cursor_shapes(qtbot, widget):
    answer = {}
    widget.web_view.page().runJavaScript(
        "(function(){var d=document.getElementById('spacemissionstudio-plot');"
        "return JSON.stringify((d.layout.shapes||[]).filter(function(s){"
        "return s.name==='spacemissionstudio-cursor';}).map(function(s){return s.x0;}));})()",
        0, lambda value: answer.setdefault("x", value))
    qtbot.waitUntil(lambda: "x" in answer, timeout=10000)
    return answer["x"]


def test_the_cursor_is_drawn_and_moved_on_the_loaded_plot(qtbot, plot):
    widget, cursor = plot
    assert _cursor_shapes(qtbot, widget) == "[]"
    cursor.set_time(1800.0)  # [s]
    qtbot.waitUntil(lambda: _cursor_shapes(qtbot, widget) == "[0.5]", timeout=10000)  # [h]
    cursor.clear()
    qtbot.waitUntil(lambda: _cursor_shapes(qtbot, widget) == "[]", timeout=10000)


def test_a_click_on_the_plot_sets_the_cursor(qtbot, plot):
    """The page's own plotly_click handler logs the x value; the page passes it on."""
    widget, cursor = plot
    widget.web_view.page().runJavaScript(
        "document.getElementById('spacemissionstudio-plot').emit('plotly_click', {points: [{x: 1.25}]});")
    qtbot.waitUntil(lambda: cursor.time_s is not None, timeout=10000)
    assert cursor.time_s == pytest.approx(4500.0)  # [s] 1.25 h


def test_on_a_utc_axis_the_cursor_round_trips_through_the_plotted_text(qtbot, plot):
    widget, cursor = plot
    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS):
        widget.x_axis_combo.setCurrentIndex(widget.x_axis_combo.findData("epoch"))
    assert widget._x_is_epoch
    cursor.set_time(4321.5)  # [s]
    text = widget.cursor_x_literal().strip('"')
    assert text.startswith("2026-01-01 01:12")
    assert widget.plot_x_to_elapsed_s(text) == pytest.approx(4321.5, abs=1e-3)  # [s]
    assert widget.plot_x_to_elapsed_s("not a date") is None
