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


# The first plot page (plotly.js) can take over 10 s to load on a loaded CI runner
# with several test workers (Windows, macOS: SRelD K-10); the tool is not at fault.
_PAGE_LOAD_TIMEOUT_MS = 30000  # [ms]


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


def test_set_result_with_no_provenance_leaves_label_blank(widget):
    widget.set_result(_sample_result_set())
    assert widget.provenance_label.text() == ""


def test_set_result_with_provenance_shows_version_and_run_time(widget):
    from spacemissionstudio.engine.results import RunProvenance

    rs = _sample_result_set()
    rs.provenance = RunProvenance(
        spacemissionstudio_version="9.9.9", basilisk_version="2.12.0",
        run_started_utc="2030-01-01T00:00:00+00:00", integrator="rkf78", dynamics_task_rate_s=10.0,
    )
    widget.set_result(rs)
    label = widget.provenance_label.text()
    assert "9.9.9" in label
    assert "2.12.0" in label
    assert "RKF78, 10 s step" in label
    assert "2030-01-01 00:00 UTC" in label
    assert "deterministic" in widget.provenance_label.toolTip()


def test_set_result_none_clears_provenance_label(widget):
    from spacemissionstudio.engine.results import RunProvenance

    rs = _sample_result_set()
    rs.provenance = RunProvenance(
        spacemissionstudio_version="9.9.9", basilisk_version="2.12.0",
        run_started_utc="2030-01-01T00:00:00+00:00", integrator="rkf78", dynamics_task_rate_s=10.0,
    )
    widget.set_result(rs)
    widget.set_result(None)
    assert widget.provenance_label.text() == ""


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

    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS):
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

    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS):
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
    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS):
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

    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS):
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

    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS):
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


def test_save_plot_as_svg_writes_a_real_svg_file(widget, tmp_path, monkeypatch, qtbot):
    """End-to-end mirror of test_save_plot_as_png_writes_a_real_png_file,
    for the SVG path added alongside PNG (roadmap item M2) -- real
    plotly.js rendering in the offscreen QWebEngineView, not a mocked JS
    call. Confirms the SVG is written as plain decoded TEXT (Plotly's
    own SVG data URL is percent-encoded, not base64 -- see
    _on_plot_png_rendered's own docstring), not raw/garbled bytes.
    """
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS):
        widget.set_result(_sample_result_set())
    assert widget.save_svg_button.isEnabled()
    out_path = tmp_path / "plot.svg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (str(out_path), "SVG images (*.svg)")))
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    widget._on_save_plot_svg()
    qtbot.waitUntil(lambda: out_path.exists(), timeout=10000)

    svg_text = out_path.read_text(encoding="utf-8")
    assert svg_text.startswith("<svg")
    assert "</svg>" in svg_text
    qtbot.waitUntil(lambda: len(info_calls) == 1, timeout=5000)


def test_save_plot_as_svg_appends_extension_if_missing(widget, tmp_path, monkeypatch, qtbot):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS):
        widget.set_result(_sample_result_set())
    out_path_no_ext = tmp_path / "plot"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                         staticmethod(lambda *a, **k: (str(out_path_no_ext), "SVG images (*.svg)")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    widget._on_save_plot_svg()
    expected_path = tmp_path / "plot.svg"
    qtbot.waitUntil(lambda: expected_path.exists(), timeout=10000)
    assert not out_path_no_ext.exists()


def test_save_plot_as_svg_with_no_result_is_a_no_op(widget, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    assert not widget.save_svg_button.isEnabled()
    calls = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: calls.append(1) or ("", "")))
    widget._on_save_plot_svg()  # self.figure is None
    assert calls == []


def test_save_png_and_save_svg_share_the_same_re_entrancy_guard(widget, qtbot, monkeypatch):
    """Clicking "Save plot as SVG..." while a PNG save poll (or vice
    versa) is already in flight must be a no-op too -- both buttons
    drive the same self._png_poll_state/page-global JS result variable
    (see _on_save_plot_png's own re-entrancy-guard comment), so a second
    concurrent poll from EITHER button would orphan the first timer.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QFileDialog

    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS):
        widget.set_result(_sample_result_set())

    calls = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: calls.append(1) or ("", "")))
    widget._png_poll_state = {"path": "/dev/null", "fmt": "png", "timer": QTimer(widget), "attempts": 0}

    widget._on_save_plot_svg()  # must return immediately, never even open the Save dialog

    assert calls == []


def test_redraw_does_not_reenable_save_svg_button_while_a_poll_is_in_flight(widget, qtbot):
    """SVG counterpart of test_redraw_does_not_reenable_save_button_while_a_png_poll_is_in_flight --
    save_svg_button must stay disabled across a live-update _redraw()
    too, for the same reason.
    """
    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS):
        widget.set_result(_sample_result_set())
    assert widget.save_svg_button.isEnabled()

    from PySide6.QtCore import QTimer
    widget._png_poll_state = {"path": "/dev/null", "fmt": "svg", "timer": QTimer(widget), "attempts": 0}
    widget.save_svg_button.setEnabled(False)

    widget._redraw()  # simulates a live update landing mid-poll

    assert not widget.save_svg_button.isEnabled()


def test_series_colors_palette_is_8_distinct_valid_hex_colors():
    """Regression guard for roadmap item M3 (docs/ux_roadmap.md):
    `_SERIES_COLORS` is a specific, externally-validated-by-hand
    8-hue palette (see that constant's own comment for the exact
    `scripts/validate_palette.js` run and numbers this guards against
    silently going stale) -- this test can't re-run that Node-based
    validator itself (see the roadmap entry's own "no new dependency"
    rationale), but it CAN catch the shape of edit that would break the
    validated claim without anyone noticing: an accidental duplicate,
    a truncated list, or a non-hex typo.
    """
    import re

    from spacemissionstudio.gui.results_widget import _SERIES_COLORS

    assert len(_SERIES_COLORS) == 8
    assert len(set(_SERIES_COLORS)) == 8  # no accidental duplicate
    for color in _SERIES_COLORS:
        assert re.fullmatch(r"#[0-9a-fA-F]{6}", color), color


def _access_result_set(n=20):
    """A ResultSet with two ground-station/spacecraft access pairs --
    one with real access windows, one with none at all (regression
    guard: a pair that's never in view must still appear as its own
    row, not silently vanish).
    """
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    t = np.linspace(0, 3600, n)
    has_access_a = np.zeros((n, 1))
    has_access_a[5:10, 0] = 1.0
    has_access_a[15:18, 0] = 1.0
    has_access_b = np.zeros((n, 1))  # never has access

    rs = ResultSet(scenario_name="demo")
    rs.add(TimeSeries("station-a.access_to_sat-1.has_access", t, ("has_access",), has_access_a, units="-"))
    rs.add(TimeSeries("station-b.access_to_sat-1.has_access", t, ("has_access",), has_access_b, units="-"))
    return rs


def test_view_combo_defaults_to_single_series(widget):
    assert widget.view_combo.currentData() == "single"
    assert widget.series_combo.isEnabled()


def test_switching_to_access_timeline_disables_series_combo(widget):
    widget.set_result(_access_result_set())
    index = widget.view_combo.findData("access_timeline")
    widget.view_combo.setCurrentIndex(index)
    assert not widget.series_combo.isEnabled()

    index = widget.view_combo.findData("single")
    widget.view_combo.setCurrentIndex(index)
    assert widget.series_combo.isEnabled()


def test_access_timeline_plots_one_trace_per_pair_with_a_segment_per_window(widget):
    widget.set_result(_access_result_set())
    widget.view_combo.setCurrentIndex(widget.view_combo.findData("access_timeline"))

    assert widget.figure is not None
    y_values = {trace.y[0] for trace in widget.figure.data}
    assert y_values == {"station-a -> sat-1", "station-b -> sat-1"}
    # One trace per pair (thousands of per-pass traces were slow to draw on
    # long runs): station-a's two separate access windows are two segments
    # of its one trace, split by a None gap; station-b has none -> one
    # invisible placeholder trace.
    station_a_traces = [t for t in widget.figure.data if t.y[0] == "station-a -> sat-1"]
    station_b_traces = [t for t in widget.figure.data if t.y[0] == "station-b -> sat-1"]
    assert len(station_a_traces) == 1 and len(station_b_traces) == 1
    segments = [part for part in "|".join("x" if x is None else "s" for x in station_a_traces[0].x).split("x")
                if part.strip("|")]
    assert len(segments) == 2


def test_access_timeline_with_no_access_series_shows_explanatory_empty_state(widget):
    widget.set_result(_sample_result_set())  # position/velocity only, no access series
    widget.view_combo.setCurrentIndex(widget.view_combo.findData("access_timeline"))

    assert widget.figure is not None
    assert len(widget.figure.data) == 0
    assert "No ground-station access series" in widget.figure.layout.annotations[0].text


def test_access_timeline_ignores_x_axis_combo_always_uses_elapsed_time(widget):
    widget.set_result(_access_result_set())
    widget.view_combo.setCurrentIndex(widget.view_combo.findData("access_timeline"))
    widget.x_axis_combo.setCurrentIndex(widget.x_axis_combo.findData("epoch"))

    assert widget.figure.layout.xaxis.title.text == "Elapsed time [hr]"


def test_switching_back_to_single_series_restores_previous_plot(widget):
    widget.set_result(_access_result_set())
    widget.series_combo.setCurrentIndex(0)
    single_series_name = widget.series_combo.currentText()
    single_series_figure_data_len = len(widget.figure.data)

    widget.view_combo.setCurrentIndex(widget.view_combo.findData("access_timeline"))
    assert widget.figure.layout.title.text == "Ground Station Access Timeline"

    widget.view_combo.setCurrentIndex(widget.view_combo.findData("single"))

    assert widget.series_combo.currentText() == single_series_name
    assert widget.series_combo.isEnabled()
    assert len(widget.figure.data) == single_series_figure_data_len


def test_access_timeline_renders_in_the_real_webview(widget, qtbot):
    """End-to-end check that the access-timeline figure's generated HTML
    actually loads in the real (offscreen) QWebEngineView without
    error -- the unit-level trace-count assertions above don't catch a
    figure that builds fine in Python but is malformed Plotly JSON
    (e.g. a NaN/non-JSON-serializable value sneaking into a trace).
    """
    widget.set_result(_access_result_set())
    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS) as blocker:
        widget.view_combo.setCurrentIndex(widget.view_combo.findData("access_timeline"))
    assert blocker.args == [True]


def test_save_plot_default_name_is_access_timeline_in_that_view(widget, tmp_path, monkeypatch, qtbot):
    from PySide6.QtWidgets import QFileDialog

    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=_PAGE_LOAD_TIMEOUT_MS):
        widget.set_result(_access_result_set())
    widget.view_combo.setCurrentIndex(widget.view_combo.findData("access_timeline"))

    captured = {}

    def _fake_get_save_file_name(*args, **kwargs):
        captured["default_name"] = args[2] if len(args) > 2 else kwargs.get("dir", "")
        return "", ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(_fake_get_save_file_name))
    widget._on_save_plot_png()

    assert captured["default_name"] == "access_timeline.png"


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

    class _FrozenClock:  # "rapid" must not depend on machine load: no time passes
        def elapsed(self):
            return 0

        def restart(self):
            return 0

    monkeypatch.setattr(widget, "_live_redraw_elapsed", _FrozenClock())
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
    first_series = widget.current_series_name()
    other_series = next(name for name in widget._result.series if name != first_series)

    push_calls = []
    monkeypatch.setattr(widget, "_push_figure_to_webview", lambda: push_calls.append(1))
    # setCurrentIndex (not setCurrentText): the combo is editable, where
    # setCurrentText only updates the line-edit's displayed text and
    # relies on editingFinished (Enter/focus-loss) to sync currentIndex
    # -- not what a real dropdown pick (this test's actual subject) does.
    widget.series_combo.setCurrentIndex(widget.series_combo.findData(other_series))  # still inside the throttle window

    assert widget.current_series_name() == other_series
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
    first_series = widget.current_series_name()
    other_series = next(name for name in widget._result.series if name != first_series)
    original_y_title = widget.figure.layout.yaxis.title.text

    # The popup offers the shown labels, so that is what it emits.
    widget.series_combo.completer().activated.emit(
        widget.series_combo.itemText(widget.series_combo.findData(other_series)))

    assert widget.current_series_name() == other_series
    assert widget.figure.layout.yaxis.title.text != original_y_title  # the plot actually rebuilt, not just the combo text


def test_typing_an_exact_series_name_and_pressing_enter_redraws_the_plot(widget, qtbot):
    """Same real report, other reliable commit path: typing a series
    name out in full (no popup suggestion ever clicked) and pressing
    Enter -- QLineEdit.editingFinished, not the completer at all.
    """
    from PySide6.QtCore import Qt

    widget.set_result(_sample_result_set())
    first_series = widget.current_series_name()
    other_series = next(name for name in widget._result.series if name != first_series)
    original_y_title = widget.figure.layout.yaxis.title.text

    widget.series_combo.setFocus()
    widget.series_combo.lineEdit().setText(widget.series_combo.itemText(widget.series_combo.findData(other_series)))
    qtbot.keyClick(widget.series_combo.lineEdit(), Qt.Key.Key_Return)

    assert widget.current_series_name() == other_series
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


def test_wrapping_angle_breaks_its_line_instead_of_drawing_a_vertical_jump(widget):
    """True anomaly runs 0 -> 360 deg every orbit; drawn as one line, each
    wrap was a false vertical stroke across the whole plot."""
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    t = np.arange(0.0, 3 * 5400.0, 60.0)  # [s] three ~90 min orbits
    nu_rad = np.mod(2 * np.pi * t / 5400.0, 2 * np.pi)  # [rad]
    rs = ResultSet(scenario_name="demo")
    rs.add(TimeSeries("sat-1.orbit_elements.true_anomaly", t, ("nu",), nu_rad.reshape(-1, 1), units="rad"))
    widget.set_result(rs)

    y = np.asarray(widget.figure.data[0].y, dtype=float)
    assert np.count_nonzero(np.isnan(y)) == 2  # one gap per wrap
    finite = y[np.isfinite(y)]
    np.testing.assert_allclose(finite, np.degrees(nu_rad))  # every sample still drawn, still in [0, 360)
    segments = np.split(y, np.flatnonzero(np.isnan(y)))
    assert all(np.all(np.abs(np.diff(seg[np.isfinite(seg)])) < 180.0) for seg in segments)


def test_long_wrapping_series_is_thinned_evenly_not_min_max():
    """Min-max thinning would pick ~0 and ~360 deg from every stretch."""
    from spacemissionstudio.gui.results_widget import _MAX_PLOT_POINTS_PER_LINE, _wrapping_display_indices

    keep = _wrapping_display_indices(10 * _MAX_PLOT_POINTS_PER_LINE)
    assert len(keep) == _MAX_PLOT_POINTS_PER_LINE
    assert keep[0] == 0 and keep[-1] == 10 * _MAX_PLOT_POINTS_PER_LINE - 1
    assert np.ptp(np.diff(keep)) <= 1  # evenly spaced


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
    # time_s is TDB seconds (engine.time_system): UTC = epoch + t minus the
    # change of TDB - UTC, here microseconds (no leap second in between).
    assert all(abs((got - want).total_seconds()) < 1e-3 for got, want in zip(plotted_x, expected))
    assert plotted_x[0] == base
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
    assert widget.current_series_name() == "sat-2.position_N"


def test_a_large_series_still_shows_when_selected(widget, qtbot):
    """Real user report: during a long run, switching to chief-1.position_N
    or .velocity_N "just doesn't change" -- each was a ~5.8 MB page and
    QWebEngineView.setHtml() silently shows nothing above 2 MB, so the
    previous plot stayed up. Pages now load from a file, so a 90,000-
    sample, 3-line series must actually render after switching to it."""
    import numpy as np

    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    t = np.arange(90000) * 30.0  # [s] 30 s samples over ~31 days
    result = ResultSet(scenario_name="big")
    result.add(TimeSeries("sat-1.semi_major_axis", t, ("a",), np.full((len(t), 1), 6928e3), units="m"))
    position = np.column_stack([7e6 * np.cos(t / 900.0), 7e6 * np.sin(t / 900.0), np.zeros(len(t))])  # [m]
    result.add(TimeSeries("sat-1.position_N", t, ("x", "y", "z"), position, units="m"))
    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=20000):
        widget.set_result(result)
    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=20000):
        widget.series_combo.setCurrentIndex(widget.series_combo.findData("sat-1.position_N"))

    shown = {}
    widget.web_view.page().runJavaScript(
        "(function(){var d=document.querySelector('.plotly-graph-div');"
        "return d && d.layout ? d.layout.title.text + '|' + d.data.length : 'NO PLOT';})()",
        0, lambda value: shown.setdefault("title", value))
    qtbot.waitUntil(lambda: "title" in shown, timeout=10000)
    assert shown["title"].startswith("sat-1: ") and shown["title"].endswith("|3"), shown["title"]


def test_display_thinning_keeps_peaks_and_caps_points():
    """Each plotted line is thinned to at most _MAX_PLOT_POINTS_PER_LINE
    points, keeping every stretch's minimum and maximum, so a short burn
    or spike still shows. Small series are drawn in full."""
    import numpy as np

    from spacemissionstudio.gui.results_widget import _MAX_PLOT_POINTS_PER_LINE, _display_indices

    small = np.arange(500.0)
    assert np.array_equal(_display_indices(small), np.arange(500))

    values = np.sin(np.arange(200000) / 50.0)
    values[123457] = 25.0  # a one-sample spike
    keep = _display_indices(values)
    assert len(keep) <= _MAX_PLOT_POINTS_PER_LINE
    assert 123457 in keep and 0 in keep and len(values) - 1 in keep
    assert np.all(np.diff(keep) > 0)  # in time order


# -- decluttering (real user feedback: "check the Results tab for the same clutter") --

def test_series_list_shows_plot_titles_with_the_code_name_as_tooltip(widget):
    """The Series list used raw dotted code names; entries now read like
    their plot titles, and the code name (the CSV file name) stays
    available as the item's data and tooltip."""
    from PySide6.QtCore import Qt

    widget.set_result(_sample_result_set())
    combo = widget.series_combo
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert labels == ["sat-1: Inertial Position (ECI)", "sat-1: Inertial Velocity (ECI)"]
    assert [combo.itemData(i) for i in range(combo.count())] == ["sat-1.position_N", "sat-1.velocity_N"]
    assert combo.itemData(0, Qt.ItemDataRole.ToolTipRole) == "sat-1.position_N"
    assert widget.figure.layout.title.text == labels[0]  # list entry == plot title


def test_typing_a_full_code_name_still_selects_that_series(widget, qtbot):
    from PySide6.QtCore import Qt

    widget.set_result(_sample_result_set())
    widget.series_combo.setFocus()
    widget.series_combo.lineEdit().setText("sat-1.velocity_N")
    qtbot.keyClick(widget.series_combo.lineEdit(), Qt.Key.Key_Return)

    assert widget.current_series_name() == "sat-1.velocity_N"


def test_view_selector_only_appears_when_there_are_access_series(widget):
    """With no ground stations there is nothing to choose between."""
    widget.show()
    widget.set_result(_sample_result_set())
    assert not widget.view_combo.isVisible() and not widget.view_label.isVisible()

    widget.set_result(_access_result_set())
    assert widget.view_combo.isVisible() and widget.view_label.isVisible()

    widget.view_combo.setCurrentIndex(widget.view_combo.findData("access_timeline"))
    widget.set_result(_sample_result_set())  # back to a result without stations
    assert not widget.view_combo.isVisible()
    assert widget.view_combo.currentData() == "single"
    assert widget.figure.layout.title.text == "sat-1: Inertial Position (ECI)"


def test_results_tab_fits_a_narrow_pane(widget):
    """A one-line provenance label and a wide toolbar used to force the tab
    to ~780 px, wider than a typical right-hand pane."""
    from spacemissionstudio.engine.results import RunProvenance

    rs = _access_result_set()
    for name, series in _sample_result_set().series.items():
        rs.add(series)
    rs.provenance = RunProvenance(
        spacemissionstudio_version="2.0.0", basilisk_version="2.12.0",
        run_started_utc="2026-10-07T14:33:38.434854+00:00", integrator="rkf78", dynamics_task_rate_s=30.0,
    )
    rs.warnings = ["sat-1: orbital energy drifted 5.1% (limit 1%) -- try a smaller dynamics step or a "
                   "higher-order integrator"]
    widget.set_result(rs)
    widget.show()
    # 620 px at the Linux CI's font; as a count of average characters, so
    # a platform with wider fonts (Windows) gets the same bound (SRelD K-10).
    assert widget.minimumSizeHint().width() <= 103 * widget.fontMetrics().averageCharWidth()
    assert "14:33 UTC" in widget.provenance_label.text() and ".434854" not in widget.provenance_label.text()


def test_plot_page_fills_the_view_without_a_scroll_bar(widget, qtbot):
    """Plotly's page kept the browser's default body margin under a
    100%-height plot, so every plot had a scroll bar beside it."""
    widget.resize(800, 600)  # [px]
    widget.show()
    qtbot.waitExposed(widget)
    with qtbot.waitSignal(widget.web_view.loadFinished, timeout=20000):
        widget.set_result(_sample_result_set())
    sizes = {}
    widget.web_view.page().runJavaScript(
        "[document.documentElement.scrollHeight, window.innerHeight,"
        " document.documentElement.scrollWidth, window.innerWidth].join(',')",
        0, lambda value: sizes.setdefault("v", value))
    qtbot.waitUntil(lambda: "v" in sizes, timeout=5000)
    scroll_height, inner_height, scroll_width, inner_width = (int(v) for v in sizes["v"].split(","))
    assert scroll_height <= inner_height and scroll_width <= inner_width, sizes["v"]


def test_access_timeline_marks_each_pass_and_starts_at_zero(widget):
    """On a long run a pass is narrower than a pixel, so its segment alone
    vanished; fixed-size end ticks keep it visible. The ticks must not pad
    the axis to before t = 0."""
    widget.set_result(_access_result_set())
    widget.view_combo.setCurrentIndex(widget.view_combo.findData("access_timeline"))

    with_passes = [t for t in widget.figure.data if t.y[0] == "station-a -> sat-1"][0]
    assert "markers" in with_passes.mode
    assert with_passes.marker.symbol == "line-ns"
    assert widget.figure.layout.xaxis.range == (0.0, 1.0)  # [hr] the whole 3600 s run


# -- one-click "What to look at" suggestions ------------------------------------

def _comms_result():
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    t = np.linspace(0, 600, 20)
    rs = ResultSet(scenario_name="19")
    rs.add(TimeSeries("leo-comms-1.position_N", t, ("x", "y", "z"), np.zeros((20, 3)), units="m"))
    rs.add(TimeSeries("berlin-gs.access_to_leo-comms-1.has_access", t, ("has_access",),
                      (t > 300).astype(float)[:, None], units="-"))
    rs.add(TimeSeries("leo-comms-1.comms_pointing.pointing_error_deg", t, ("pointing_error_deg",),
                      np.linspace(90, 1, 20)[:, None], units="deg"))
    rs.add(TimeSeries("leo-comms-1.battery_charge", t, ("charge",), np.linspace(36, 30, 20)[:, None], units="W*hr"))
    return rs


def test_suggestions_offer_the_featured_series_and_open_on_the_first(widget):
    widget.show()
    widget.set_featured_series(["berlin-gs.access_to_leo-comms-1.has_access",
                                "leo-comms-1.comms_pointing.pointing_error_deg",
                                "leo-comms-1.battery_charge",
                                "leo-comms-1.comms_pointing.active_mode"])  # not in this result: no chip
    widget.set_result(_comms_result())

    assert widget.suggestion_row.isVisible()
    # One spacecraft and one station pair: the chips don't repeat them.
    assert [c.text() for c in widget._suggestion_chips] == ["Access Window", "Pointing Error", "Battery State of Charge"]
    assert [c.toolTip() for c in widget._suggestion_chips][0] == "berlin-gs.access_to_leo-comms-1.has_access"
    assert widget.current_series_name() == "berlin-gs.access_to_leo-comms-1.has_access"  # not position_N
    assert [c.isChecked() for c in widget._suggestion_chips] == [True, False, False]


def test_clicking_a_suggestion_shows_it_even_from_the_access_timeline(widget):
    widget.show()
    widget.set_featured_series(["leo-comms-1.battery_charge"])
    widget.set_result(_comms_result())
    widget.view_combo.setCurrentIndex(widget.view_combo.findData("access_timeline"))

    widget._suggestion_chips[0].click()

    assert widget.view_combo.currentData() == "single"
    assert widget.current_series_name() == "leo-comms-1.battery_charge"
    assert widget.figure.layout.title.text == "leo-comms-1: Battery State of Charge"
    assert widget._suggestion_chips[0].isChecked()


def test_suggestions_keep_names_that_tell_spacecraft_apart_and_hide_when_empty(widget):
    from spacemissionstudio.engine.results import TimeSeries

    widget.show()
    widget.set_featured_series(["leo-comms-1.battery_charge", "sat-2.position_N"])
    result = _comms_result()
    result.add(TimeSeries("sat-2.position_N", np.linspace(0, 600, 20), ("x", "y", "z"), np.zeros((20, 3)), units="m"))
    widget.set_result(result)
    assert [c.text() for c in widget._suggestion_chips] == ["leo-comms-1: Battery State of Charge",
                                                           "sat-2: Inertial Position (ECI)"]

    widget.set_featured_series([])
    assert not widget.suggestion_row.isVisible()
    widget.set_featured_series(["leo-comms-1.battery_charge"])
    widget.set_result(None)
    assert not widget.suggestion_row.isVisible()


def test_newly_named_series_get_plot_titles():
    """Featured in templates 19/20 but shown as raw code names before."""
    from spacemissionstudio.engine.results import TimeSeries
    from spacemissionstudio.gui.results_widget import _series_label

    def label(name, columns, units):
        return _series_label(name, TimeSeries(name, np.zeros(1), columns, np.zeros((1, len(columns))), units=units))

    assert label("leo-comms-1.comms_pointing.active_mode", ("active_mode",), "-") == \
        "leo-comms-1: Pointing Mode (0 Sun, 1 ground station)"
    assert label("leo-comms-1.comms_pointing.pointing_error_deg", ("pointing_error_deg",), "deg") == \
        "leo-comms-1: Pointing Error"
    assert label("sat-1.actuator.rw-1.motor_temperature", ("temperature",), "C") == "sat-1: Motor Temperature: rw-1"
    assert label("sat-1.sensor.therm-1", ("temperature",), "C") == "sat-1: Thermal Sensor: therm-1"


class _DeferredPage:
    """Stands in for the web page: runJavaScript() keeps the callbacks, which
    the test answers later, as the real asynchronous page does."""

    def __init__(self):
        self.pending = []

    def runJavaScript(self, script, callback=None):  # noqa: N802 -- Qt's name
        if callback is not None:
            self.pending.append(callback)


def _deferred_poll(widget, monkeypatch, tmp_path):
    from PySide6.QtCore import QTimer

    page = _DeferredPage()
    monkeypatch.setattr(widget.web_view, "page", lambda: page)
    rendered = []
    monkeypatch.setattr(widget, "_on_plot_png_rendered", lambda *args: rendered.append(args))
    widget._png_poll_state = {"path": str(tmp_path / "p.png"), "fmt": "png", "timer": QTimer(widget), "attempts": 0}
    return page, rendered


def test_a_poll_tick_after_the_poll_finished_is_ignored(widget):
    """SRelD K-08: a timer tick queued before the poll finished used to read
    the cleared state ("'NoneType' object is not subscriptable")."""
    widget._png_poll_state = None
    widget._poll_plot_png()  # must not raise


def test_only_one_poll_query_is_in_flight_and_late_answers_are_ignored(widget, monkeypatch, tmp_path):
    """SRelD K-08: on a slow machine several queries were in flight at once;
    each answer finished the save again (a second write and "saved"
    dialog). Ticks wait for the outstanding answer, and an answer to a
    finished poll does nothing."""
    page, rendered = _deferred_poll(widget, monkeypatch, tmp_path)
    widget._poll_plot_png()
    widget._poll_plot_png()  # the first answer is still outstanding
    widget._poll_plot_png()
    assert len(page.pending) == 1

    page.pending.pop()("data:image/png;base64,AAAA")
    assert len(rendered) == 1 and widget._png_poll_state is None

    widget._poll_plot_png()  # a late tick: nothing to do
    assert page.pending == [] and len(rendered) == 1


def test_a_pending_answer_lets_the_next_tick_ask_again(widget, monkeypatch, tmp_path):
    """While the plot is still rendering, each answer frees the next tick
    to ask again, until the result arrives."""
    from spacemissionstudio.gui.results_widget import _SAVE_PNG_PENDING_SENTINEL

    page, rendered = _deferred_poll(widget, monkeypatch, tmp_path)
    widget._poll_plot_png()
    page.pending.pop()(_SAVE_PNG_PENDING_SENTINEL)
    widget._poll_plot_png()
    assert len(page.pending) == 1 and widget._png_poll_state["attempts"] == 2
    page.pending.pop()("data:image/png;base64,AAAA")
    assert len(rendered) == 1


def test_an_answer_that_never_comes_does_not_stall_the_save(widget, monkeypatch, tmp_path):
    """One query at a time must not mean waiting forever: if an answer is
    lost, the poll asks again after a second of ticks."""
    from spacemissionstudio.gui.results_widget import _SAVE_PNG_MAX_WAIT_TICKS

    page, rendered = _deferred_poll(widget, monkeypatch, tmp_path)
    widget._poll_plot_png()
    page.pending.clear()  # the answer is lost
    for _ in range(_SAVE_PNG_MAX_WAIT_TICKS - 1):
        widget._poll_plot_png()
    assert page.pending == []
    widget._poll_plot_png()
    assert len(page.pending) == 1
    page.pending.pop()("data:image/png;base64,AAAA")
    assert len(rendered) == 1 and widget._png_poll_state is None

