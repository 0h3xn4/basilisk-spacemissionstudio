"""Tests for gui.results_widget.ResultsWidget -- uses synthetic
ResultSet data, no Basilisk needed. Inspects the built ``go.Figure``
object directly (``widget.figure``) rather than the rendered
QWebEngineView content -- the same role matplotlib's ``Axes`` used to
play before the Plotly migration (see that module's own docstring).
"""

from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.requires_gui


def _sample_result_set(n=50):
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    t = np.linspace(0, 3600 * 3, n)
    pos = np.column_stack([np.sin(t / 500), np.cos(t / 500), t * 0.001]) * 7.0e6
    vel = np.column_stack([np.cos(t / 500), -np.sin(t / 500), np.zeros_like(t)])

    rs = ResultSet(scenario_name="demo")
    rs.add(TimeSeries("sat-1.position_N", t, ("x", "y", "z"), pos, units="m"))
    rs.add(TimeSeries("sat-1.velocity_N", t, ("x", "y", "z"), vel, units="m/s"))
    return rs


@pytest.fixture
def widget(qtbot):
    from spacemissionstudio.gui.results_widget import ResultsWidget

    w = ResultsWidget()
    qtbot.addWidget(w)
    return w


def test_set_result_populates_series_combo_and_plots(widget):
    widget.set_result(_sample_result_set())
    assert widget.series_combo.count() == 2
    assert widget.export_button.isEnabled()
    assert len(widget.figure.data) == 3  # x, y, z


def test_series_combo_is_searchable_by_substring(widget):
    """Real scenarios (e.g. the built-in 6-satellite Walker constellation
    template) produce 30-40+ series named after the dotted
    "{spacecraft}.{category}..." scheme -- a plain, unsearchable dropdown
    that long is tedious to scan. The combo must be editable with a
    substring (not just prefix) completer, since the useful
    discriminator (the spacecraft name, or the category after the first
    dot) is often in the middle of the string, not the start.
    """
    widget.set_result(_sample_result_set())

    assert widget.series_combo.isEditable()
    completer = widget.series_combo.completer()
    assert completer is not None
    from PySide6.QtCore import Qt

    assert completer.filterMode() == Qt.MatchFlag.MatchContains
    assert completer.caseSensitivity() == Qt.CaseSensitivity.CaseInsensitive


def test_series_combo_completer_model_stays_in_sync_after_set_result(widget):
    """Regression guard: the QCompleter is bound to series_combo's model
    once at construction -- if set_result()'s clear()/addItem() calls
    ever replaced that model object instead of mutating it in place, the
    completer would silently keep matching against stale, previously
    -shown series names.
    """
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    widget.set_result(_sample_result_set())
    first_model = widget.series_combo.completer().model()

    other = ResultSet(scenario_name="demo2")
    other.add(TimeSeries("sat-9.battery_charge", np.linspace(0, 10, 5), ("charge",),
                          np.zeros((5, 1)), units="W*hr"))
    widget.set_result(other)

    assert widget.series_combo.completer().model() is first_model
    assert widget.series_combo.completer().model().rowCount() == 1


def test_switching_series_redraws(widget):
    widget.set_result(_sample_result_set())
    widget.series_combo.setCurrentIndex(1)
    assert len(widget.figure.data) == 3


def test_set_result_none_clears_everything(widget):
    widget.set_result(_sample_result_set())
    widget.set_result(None)
    assert widget.series_combo.count() == 0
    assert not widget.export_button.isEnabled()
    assert widget.figure is None


def test_export_writes_csv_files(widget, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    widget.set_result(_sample_result_set())
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(tmp_path)))
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    widget._on_export()

    written = sorted(p.name for p in Path(tmp_path).glob("*.csv"))
    assert written == ["sat-1.position_N.csv", "sat-1.velocity_N.csv"]
    assert len(info_calls) == 1


def test_export_with_no_result_is_a_no_op(widget, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    calls = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: calls.append(1) or ""))
    widget._on_export()  # self._result is None
    assert calls == []


def test_save_plot_as_png_writes_a_real_png_file(widget, tmp_path, monkeypatch, qtbot):
    """End-to-end: real plotly.js rendering a real PNG in the offscreen
    QWebEngineView, not a mocked JS call -- the same "confirmed directly
    in this sandbox, not assumed" discipline this module's own docstring
    already holds itself to for the base setHtml()/loadFinished pipeline.
    Plotly.toImage() is asynchronous (page().runJavaScript() callback),
    so this waits for the file to actually appear rather than asserting
    immediately after the click.
    """
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=10000):
        widget.set_result(_sample_result_set())
    assert widget.save_png_button.isEnabled()
    out_path = tmp_path / "plot.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (str(out_path), "PNG images (*.png)")))
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    widget._on_save_plot_png()
    qtbot.waitUntil(lambda: out_path.exists(), timeout=10000)

    png_bytes = out_path.read_bytes()
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"  # real PNG magic bytes, not an empty/garbage file
    assert len(png_bytes) > 1000  # a real rendered chart, not a 1x1 placeholder
    qtbot.waitUntil(lambda: len(info_calls) == 1, timeout=5000)


def test_save_plot_as_png_appends_extension_if_missing(widget, tmp_path, monkeypatch, qtbot):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=10000):
        widget.set_result(_sample_result_set())
    out_path_no_ext = tmp_path / "plot"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (str(out_path_no_ext), "PNG images (*.png)")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    widget._on_save_plot_png()
    expected_path = tmp_path / "plot.png"
    qtbot.waitUntil(lambda: expected_path.exists(), timeout=10000)
    assert not out_path_no_ext.exists()


def test_save_plot_as_png_with_no_result_is_a_no_op(widget, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    assert not widget.save_png_button.isEnabled()
    calls = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: calls.append(1) or ("", "")))
    widget._on_save_plot_png()  # self.figure is None
    assert calls == []


def test_save_plot_as_png_cancelled_dialog_is_a_no_op(widget, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    widget.set_result(_sample_result_set())
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    widget._on_save_plot_png()  # must not raise, must not create anything

    assert list(tmp_path.iterdir()) == []


def test_redraw_does_not_reenable_save_button_while_a_png_poll_is_in_flight(widget, qtbot):
    """Regression guard for a real bug: a live-updating run calls
    _redraw() repeatedly (via set_live_result()) while an earlier "Save
    plot as PNG..." click's poll is still in flight. _redraw() used to
    unconditionally re-enable save_png_button regardless, which let a
    second click start a SECOND, independent QTimer/poll sharing the
    same self._png_poll_state/page-global JS variable as the first --
    orphaning the first timer (nothing would ever stop it again) so it
    kept firing forever, re-triggering a duplicate file write + a
    duplicate "Plot saved" dialog every poll interval.
    """
    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=10000):
        widget.set_result(_sample_result_set())
    assert widget.save_png_button.isEnabled()

    from PySide6.QtCore import QTimer
    widget._png_poll_state = {"path": "/dev/null", "timer": QTimer(widget), "attempts": 0}
    widget.save_png_button.setEnabled(False)

    widget._redraw()  # simulates a live update landing mid-poll

    assert not widget.save_png_button.isEnabled()


def test_save_plot_as_png_is_a_no_op_while_a_poll_is_already_in_flight(widget, qtbot, monkeypatch):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QFileDialog

    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=10000):
        widget.set_result(_sample_result_set())

    calls = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: calls.append(1) or ("", "")))
    widget._png_poll_state = {"path": "/dev/null", "timer": QTimer(widget), "attempts": 0}

    widget._on_save_plot_png()  # must return immediately, never even open the Save dialog

    assert calls == []


def test_save_plot_as_png_poll_state_resets_after_completion_allowing_a_later_save(widget, tmp_path, monkeypatch,
                                                                                    qtbot):
    """The re-entrancy guard above must not become permanent: once a save
    genuinely finishes (success or failure), self._png_poll_state must go
    back to None so a LATER, legitimate click still works.
    """
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=10000):
        widget.set_result(_sample_result_set())
    first_path = tmp_path / "first.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (str(first_path), "PNG images (*.png)")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    widget._on_save_plot_png()
    qtbot.waitUntil(lambda: first_path.exists(), timeout=10000)
    qtbot.waitUntil(lambda: widget._png_poll_state is None, timeout=5000)
    assert widget.save_png_button.isEnabled()

    second_path = tmp_path / "second.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (str(second_path), "PNG images (*.png)")))

    widget._on_save_plot_png()
    qtbot.waitUntil(lambda: second_path.exists(), timeout=10000)


def test_set_live_result_populates_combo_on_first_update(widget):
    widget.set_live_result(_sample_result_set(n=5))
    assert widget.series_combo.count() == 2
    assert widget.export_button.isEnabled()
    assert len(widget.figure.data) == 3  # x, y, z


def test_set_live_result_does_not_reset_users_series_selection(widget):
    """Regression guard: a live run's series names are fixed from its
    first chunk (see set_live_result's docstring) -- later chunks with
    MORE data but the SAME series names must not rebuild series_combo,
    which would silently snap the user's current selection back to index
    0 every time a new chunk arrives while they're watching a different
    series.
    """
    widget.set_live_result(_sample_result_set(n=5))
    widget.series_combo.setCurrentIndex(1)  # "sat-1.velocity_N"

    widget.set_live_result(_sample_result_set(n=25))  # later chunk, more samples, same series names

    assert widget.series_combo.currentIndex() == 1
    assert widget.series_combo.count() == 2


def test_set_live_result_grows_the_plotted_data(widget):
    widget.set_live_result(_sample_result_set(n=5))
    first_trace_length = len(widget.figure.data[0].x)

    widget.set_live_result(_sample_result_set(n=25))

    assert len(widget.figure.data[0].x) > first_trace_length


def test_set_live_result_throttles_rapid_webview_redraws(widget, monkeypatch):
    """Real user report: during a live-updating run, switching the Series
    dropdown appeared to do nothing. Root cause: a fast-running scenario
    fires set_live_result() chunks faster than a full QWebEngineView page
    reload can settle, so redrawing on every single chunk left the view
    permanently stuck mid-reload -- including while the user tried to
    pick a different series. Rapid-fire chunks (as happens here, calling
    set_live_result() back-to-back with no delay) must NOT each trigger
    a real webview push; self.figure must still update every time
    regardless (see test_set_live_result_grows_the_plotted_data above).
    """
    push_calls = []
    monkeypatch.setattr(widget, "_push_figure_to_webview", lambda: push_calls.append(1))

    widget.set_live_result(_sample_result_set(n=5))
    assert push_calls == [1]  # the first chunk always pushes immediately

    for n in (10, 15, 20, 25):
        widget.set_live_result(_sample_result_set(n=n))

    assert push_calls == [1]  # none of the rapid-fire follow-ups pushed
    assert len(widget.figure.data[0].x) == 25  # but self.figure is still fully current


def test_set_live_result_eventually_pushes_after_the_throttle_window(widget, qtbot, monkeypatch):
    widget.set_live_result(_sample_result_set(n=5))

    push_calls = []
    monkeypatch.setattr(widget, "_push_figure_to_webview", lambda: push_calls.append(1))
    qtbot.wait(350)  # real time past _LIVE_REDRAW_MIN_INTERVAL_MS (300ms)
    widget.set_live_result(_sample_result_set(n=10))

    assert push_calls == [1]


def test_user_series_change_is_never_throttled_during_a_live_run(widget, monkeypatch):
    """A user-initiated series change must redraw immediately even while
    still inside a live run's throttle window -- switching series is
    exactly the interaction the throttle must never block. Checked via
    _push_figure_to_webview() actually being called (not a second
    loadFinished wait -- a same-shaped page reload isn't guaranteed to
    re-emit it differently from the first), matching
    test_set_live_result_throttles_rapid_webview_redraws's own style.
    """
    widget.set_live_result(_sample_result_set(n=5))
    first_series = widget.series_combo.currentText()
    other_series = next(name for name in widget._result.series if name != first_series)

    push_calls = []
    monkeypatch.setattr(widget, "_push_figure_to_webview", lambda: push_calls.append(1))
    # setCurrentIndex (not setCurrentText): the combo is editable, where
    # setCurrentText only updates the line-edit's displayed text and
    # relies on editingFinished (Enter/focus-loss) to sync currentIndex
    # -- not what a real dropdown pick (this test's actual subject) does.
    widget.series_combo.setCurrentIndex(widget.series_combo.findText(other_series))  # still inside the throttle window

    assert widget.series_combo.currentText() == other_series
    assert push_calls == [1]


def test_selecting_a_series_via_the_completer_popup_redraws_the_plot(widget):
    """Real user report, reproduced here: picking a series by typing to
    filter and then selecting a suggestion from the completer popup (the
    combo's own documented reason for being editable -- see its
    construction comment) left the OLD series' plot on screen even
    though the text box showed the newly-picked series name. Root cause:
    series_combo.currentIndexChanged (what _redraw() was wired to) does
    not reliably fire for a completer-driven pick in this combo's
    configuration -- only for a plain dropdown-arrow click. Simulates the
    actual completer path (QCompleter.activated, emitted the instant a
    popup suggestion is chosen by click or Enter-within-the-popup), not
    series_combo.setCurrentIndex() directly (already covered by
    test_user_series_change_is_never_throttled_during_a_live_run, which
    is deliberately the OTHER, dropdown-arrow pick path).
    """
    widget.set_result(_sample_result_set())
    first_series = widget.series_combo.currentText()
    other_series = next(name for name in widget._result.series if name != first_series)
    original_y_title = widget.figure.layout.yaxis.title.text

    widget.series_combo.completer().activated.emit(other_series)

    assert widget.series_combo.currentText() == other_series
    assert widget.figure.layout.yaxis.title.text != original_y_title  # the plot actually rebuilt, not just the combo text


def test_typing_an_exact_series_name_and_pressing_enter_redraws_the_plot(widget, qtbot):
    """Same real report, other reliable commit path: typing a series
    name out in full (no popup suggestion ever clicked) and pressing
    Enter -- QLineEdit.editingFinished, not the completer at all.
    """
    from PySide6.QtCore import Qt

    widget.set_result(_sample_result_set())
    first_series = widget.series_combo.currentText()
    other_series = next(name for name in widget._result.series if name != first_series)
    original_y_title = widget.figure.layout.yaxis.title.text

    widget.series_combo.setFocus()
    widget.series_combo.lineEdit().setText(other_series)
    qtbot.keyClick(widget.series_combo.lineEdit(), Qt.Key.Key_Return)

    assert widget.series_combo.currentText() == other_series
    assert widget.figure.layout.yaxis.title.text != original_y_title  # the plot actually rebuilt, not just the combo text


def test_position_series_plots_in_raw_meters(widget):
    """Regression guard for a real, explicit user request ("state vector
    elements shall be displayed in meters for position and m/s for
    velocity") that REVERSED this module's own earlier km-conversion
    decision for exactly these two series -- see results_widget's module
    docstring and _vector_display()'s own docstring.
    """
    rs = _sample_result_set()
    raw_x_m = rs.series["sat-1.position_N"].data[:, 0]

    widget.set_result(rs)

    plotted_x = np.asarray(widget.figure.data[0].y)
    np.testing.assert_allclose(plotted_x, raw_x_m)
    assert widget.figure.layout.yaxis.title.text == "Position [m]"


def test_velocity_series_plots_in_raw_m_s(widget):
    rs = _sample_result_set()
    raw_vx_m_s = rs.series["sat-1.velocity_N"].data[:, 0]

    widget.set_result(rs)
    widget.series_combo.setCurrentIndex(1)  # "sat-1.velocity_N"

    plotted_x = np.asarray(widget.figure.data[0].y)
    np.testing.assert_allclose(plotted_x, raw_vx_m_s)
    assert widget.figure.layout.yaxis.title.text == "Velocity [m/s]"


def test_delta_v_series_always_plots_in_m_s_not_km_s():
    """Regression guard for the explicit "delta-V shall always be
    displayed in m/s" request -- delta-V shares the literal "m/s" unit
    string with velocity, which is exactly why the old blanket
    unit-string-keyed conversion got this wrong (see module docstring).
    """
    from PySide6.QtWidgets import QApplication

    from spacemissionstudio.engine.results import ResultSet, TimeSeries
    from spacemissionstudio.gui.results_widget import ResultsWidget

    QApplication.instance() or QApplication([])
    w = ResultsWidget()
    rs = ResultSet(scenario_name="demo")
    raw_dv = np.linspace(0, 42.0, 5)
    rs.add(TimeSeries("sat-1.station_keeping.delta_v", np.linspace(0, 100, 5), ("cumulative_delta_v",),
                       raw_dv.reshape(-1, 1), units="m/s"))
    w.set_result(rs)

    plotted = np.asarray(w.figure.data[0].y)
    np.testing.assert_allclose(plotted, raw_dv)
    assert w.figure.layout.yaxis.title.text == "Cumulative delta-V [m/s]"


def test_altitude_and_semi_major_axis_series_plot_in_km():
    """"altitudes, semi-major axes shall be displayed in km" -- both are
    recorded in raw meters by engine.service (matching every other
    Basilisk-facing SI field), so the km conversion is display-only here.
    """
    from PySide6.QtWidgets import QApplication

    from spacemissionstudio.engine.results import ResultSet, TimeSeries
    from spacemissionstudio.gui.results_widget import ResultsWidget

    QApplication.instance() or QApplication([])
    w = ResultsWidget()
    rs = ResultSet(scenario_name="demo")
    raw_a_m = np.linspace(7.0e6, 7.1e6, 5)
    rs.add(TimeSeries("sat-1.orbit_elements.semi_major_axis", np.linspace(0, 100, 5), ("a",),
                       raw_a_m.reshape(-1, 1), units="m"))
    w.set_result(rs)

    plotted = np.asarray(w.figure.data[0].y)
    np.testing.assert_allclose(plotted, raw_a_m / 1000.0)
    assert w.figure.layout.yaxis.title.text == "Semi-major axis [km]"
    assert w.figure.layout.title.text == "sat-1: Osculating Semi-Major Axis"


def test_mean_orbital_element_series_is_plotted_and_labeled_distinctly_from_osculating():
    from PySide6.QtWidgets import QApplication

    from spacemissionstudio.engine.results import ResultSet, TimeSeries
    from spacemissionstudio.gui.results_widget import ResultsWidget

    QApplication.instance() or QApplication([])
    w = ResultsWidget()
    rs = ResultSet(scenario_name="demo")
    raw_i_rad = np.linspace(0.9, 0.95, 5)
    rs.add(TimeSeries("sat-1.orbit_elements_mean.inclination", np.linspace(0, 100, 5), ("i",),
                       raw_i_rad.reshape(-1, 1), units="rad"))
    w.set_result(rs)

    plotted = np.asarray(w.figure.data[0].y)
    np.testing.assert_allclose(plotted, np.degrees(raw_i_rad))
    assert w.figure.layout.yaxis.title.text == "Inclination [deg]"
    assert w.figure.layout.title.text == "sat-1: Mean (first-order J2) Inclination"


def test_dimensionless_series_is_not_unit_converted(widget):
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    rs = ResultSet(scenario_name="demo")
    rs.add(TimeSeries("sat-1.eccentricity", np.linspace(0, 100, 5), ("e",), np.full((5, 1), 0.01), units="-"))
    widget.set_result(rs)

    plotted = np.asarray(widget.figure.data[0].y)
    np.testing.assert_allclose(plotted, 0.01)  # unchanged -- "-" isn't in _DISPLAY_UNIT_CONVERSIONS
    assert widget.figure.layout.yaxis.title.text == "[-]"
    assert widget.figure.layout.title.text == "sat-1.eccentricity"


def test_single_column_series_has_no_legend():
    """dataviz principle: a single series names itself in the chart
    title -- no legend box is needed (unlike a >= 2 column series, e.g.
    position's x/y/z, which does need one to tell the lines apart).
    """
    from PySide6.QtWidgets import QApplication

    from spacemissionstudio.engine.results import ResultSet, TimeSeries
    from spacemissionstudio.gui.results_widget import ResultsWidget

    QApplication.instance() or QApplication([])
    w = ResultsWidget()
    rs = ResultSet(scenario_name="demo")
    rs.add(TimeSeries("sat-1.eccentricity", np.linspace(0, 100, 5), ("e",), np.full((5, 1), 0.01), units="-"))
    w.set_result(rs)
    assert w.figure.layout.showlegend is False


def test_multi_column_series_has_a_legend(widget):
    widget.set_result(_sample_result_set())
    assert widget.figure.layout.showlegend is True


def test_axes_never_use_scientific_notation(widget):
    """Regression test for the real complaint that started the Plotly
    migration: matplotlib's default axis formatter fell back to
    scientific/offset notation on several of this app's own plots.
    """
    widget.set_result(_sample_result_set())
    assert widget.figure.layout.xaxis.exponentformat == "none"
    assert widget.figure.layout.yaxis.exponentformat == "none"


def test_default_x_axis_is_elapsed_time_in_hours(widget):
    rs = _sample_result_set()
    widget.set_result(rs)

    plotted_x = np.asarray(widget.figure.data[0].x)
    np.testing.assert_allclose(plotted_x, rs.series["sat-1.position_N"].time_s / 3600.0)
    assert "Elapsed time" in widget.figure.layout.xaxis.title.text


def test_epoch_x_axis_converts_time_s_to_datetimes(widget):
    from datetime import datetime, timedelta

    rs = _sample_result_set(n=5)
    widget.set_result(rs, epoch_utc="2030-01-01T00:00:00")
    widget.x_axis_combo.setCurrentIndex(widget.x_axis_combo.findData("epoch"))

    plotted_x = list(widget.figure.data[0].x)
    base = datetime.fromisoformat("2030-01-01T00:00:00")
    expected = [base + timedelta(seconds=float(t)) for t in rs.series["sat-1.position_N"].time_s]
    assert plotted_x == expected
    assert widget.figure.layout.xaxis.title.text == "Epoch (UTC)"


def test_epoch_x_axis_falls_back_to_elapsed_time_without_a_known_epoch(widget):
    rs = _sample_result_set()
    widget.set_result(rs)  # no epoch_utc given
    widget.x_axis_combo.setCurrentIndex(widget.x_axis_combo.findData("epoch"))

    assert "Elapsed time" in widget.figure.layout.xaxis.title.text


def test_epoch_x_axis_falls_back_to_elapsed_time_on_unparseable_epoch(widget):
    rs = _sample_result_set()
    widget.set_result(rs, epoch_utc="not a real epoch string")
    widget.x_axis_combo.setCurrentIndex(widget.x_axis_combo.findData("epoch"))

    assert "Elapsed time" in widget.figure.layout.xaxis.title.text


def test_switching_x_axis_back_to_elapsed_time_restores_it(widget):
    rs = _sample_result_set()
    widget.set_result(rs, epoch_utc="2030-01-01T00:00:00")
    widget.x_axis_combo.setCurrentIndex(widget.x_axis_combo.findData("epoch"))
    widget.x_axis_combo.setCurrentIndex(widget.x_axis_combo.findData("elapsed"))

    assert "Elapsed time" in widget.figure.layout.xaxis.title.text


def test_live_result_carries_epoch_through_to_the_plot(widget):
    rs = _sample_result_set(n=5)
    widget.set_live_result(rs, epoch_utc="2030-06-15T00:00:00")
    widget.x_axis_combo.setCurrentIndex(widget.x_axis_combo.findData("epoch"))

    assert widget.figure.layout.xaxis.title.text == "Epoch (UTC)"


def test_set_live_result_rebuilds_combo_if_series_names_change(widget):
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    widget.set_live_result(_sample_result_set(n=5))
    widget.series_combo.setCurrentIndex(1)

    other = ResultSet(scenario_name="demo")
    other.add(TimeSeries("sat-2.position_N", np.linspace(0, 10, 5), ("x", "y", "z"),
                          np.zeros((5, 3)), units="m"))
    widget.set_live_result(other)

    assert widget.series_combo.count() == 1
    assert widget.series_combo.currentText() == "sat-2.position_N"
