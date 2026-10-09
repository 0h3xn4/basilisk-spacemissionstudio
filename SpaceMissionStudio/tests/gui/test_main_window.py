"""Tests for gui.main_window.MainWindow -- the full File/Run workflow,
with QFileDialog/QMessageBox monkeypatched so nothing blocks on a real
modal dialog. The "Run" test below genuinely exercises the no-Basilisk
error path in this development sandbox (see test_run_worker.py).
"""

import importlib.util

import pytest
from PySide6.QtCore import QObject, Signal

pytestmark = pytest.mark.requires_gui

_BASILISK_AVAILABLE = importlib.util.find_spec("Basilisk") is not None


@pytest.fixture(autouse=True)
def _isolated_autosave(tmp_path, monkeypatch):
    """Every test in this file gets an isolated autosave recovery
    location, same as tests/test_autosave.py's own fixture -- this
    file's own ``window`` fixture constructs a real ``MainWindow``,
    whose autosave timer/startup check (gui.autosave, design
    -philosophy roadmap item M4) must never read or write a real
    user's actual home directory from an automated test run.
    """
    from spacemissionstudio.gui import autosave

    recovery_dir = tmp_path / "autosave"
    monkeypatch.setattr(autosave, "_AUTOSAVE_DIR", recovery_dir)
    monkeypatch.setattr(autosave, "_RECOVERY_FILE", recovery_dir / "recovery.json")


@pytest.fixture
def window(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.gui.main_window import MainWindow

    # Safety net: qtbot.addWidget()'s teardown calls .close() on the
    # window, which -- for a test that leaves it dirty on purpose (e.g.
    # test_editing_marks_dirty) -- triggers the REAL, unmocked
    # unsaved-changes QMessageBox.question() prompt. In offscreen mode
    # nothing ever answers it, so teardown hangs forever. Default to
    # "Discard" here; any test that specifically exercises the close
    # -confirmation prompt overrides this with its own monkeypatch.setattr
    # call, which simply takes over for the rest of that test.
    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard))

    w = MainWindow(prompt_startup_fetch=False, check_autosave_recovery=False)
    qtbot.addWidget(w)
    return w


def _add_valid_spacecraft(window):
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    window.scenario_editor.spacecraft_list.from_list([
        SpacecraftConfig(name="sat-1", orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]))
    ])
    window.scenario_editor.changed.emit()


def test_initial_title_is_untitled(window):
    assert window.windowTitle() == "SpaceMissionStudio -- untitled"


def test_explain_tab_exists_and_shows_the_default_scenario_on_startup(window):
    assert window.right_tabs.indexOf(window.scenario_explainer_widget) >= 0
    assert window.right_tabs.tabText(window.right_tabs.indexOf(window.scenario_explainer_widget)) == "Explain"
    # reset_to_default()'s own scenario has zero spacecraft (invalid --
    # Scenario.validate() requires >= 1), so the placeholder is the
    # correct initial state here, not a crash -- this is the real
    # regression this test guards: reset_to_default() runs BEFORE
    # __init__ wires the changed signal, so without the explicit initial
    # call this fix adds, the widget would be left showing its
    # constructor-time blank state instead of ever calling set_scenario()
    # at all.
    assert not window.scenario_explainer_widget._placeholder_label.isHidden()


def test_explain_tab_refreshes_on_edit(window):
    _add_valid_spacecraft(window)
    assert window.scenario_explainer_widget._headline_label.isHidden() is False
    tile_labels = {
        window.scenario_explainer_widget._tiles_row.itemAt(i).widget()
        for i in range(window.scenario_explainer_widget._tiles_row.count())
        if window.scenario_explainer_widget._tiles_row.itemAt(i).widget() is not None
    }
    assert tile_labels  # at least one stat tile rendered for the new spacecraft


def test_explain_tab_shows_placeholder_while_scenario_is_invalid(window):
    window.scenario_editor.name_edit.setText("")  # name must not be empty -- an invalid scenario
    window.scenario_editor.changed.emit()
    assert not window.scenario_explainer_widget._placeholder_label.isHidden()


def test_explain_tab_refreshes_on_new(window):
    _add_valid_spacecraft(window)
    assert not window.scenario_explainer_widget._headline_label.isHidden()
    window.on_new()
    # on_new() resets to reset_to_default()'s own zero-spacecraft scenario,
    # which does NOT validate (Scenario.validate() requires >= 1
    # spacecraft) -- the placeholder, not the stale "sat-1" headline from
    # before on_new(), is the correct post-reset state.
    assert not window.scenario_explainer_widget._placeholder_label.isHidden()


def test_toolbar_actions_are_all_visible(window, qtbot):
    """Regression test for a real user report, with a screenshot: on
    their platform, one toolbar button ("Launch Vizard") simply wasn't
    visible in a single, wide, un-movable QToolBar -- confirmed present
    in the Run menu (so the QAction itself was fine), meaning it was a
    toolbar-width/overflow rendering issue this sandbox's own offscreen
    Fusion-style rendering never reproduced. _build_toolbar() now uses
    two shorter, fixed rows instead of one wide one specifically so no
    single action's visibility depends on window width/platform toolbar
    -overflow behavior -- assert every action this window exposes is
    actually on one of the two toolbars and visible, not just present as
    a QAction object somewhere.
    """
    from PySide6.QtWidgets import QToolBar

    window.show()
    qtbot.waitExposed(window)

    toolbars = window.findChildren(QToolBar)
    assert len(toolbars) == 2
    toolbar_actions = [a for tb in toolbars for a in tb.actions() if not a.isSeparator()]

    for action in (window.new_action, window.open_action, window.save_action, window.run_action,
                   window.abort_action, window.live_plot_action, window.monte_carlo_action,
                   window.vizard_action, window.vizard_launch_action, window.check_kernels_action):
        assert action in toolbar_actions, f"{action.text()!r} is missing from every toolbar"
        widget = next(tb.widgetForAction(action) for tb in toolbars if tb.widgetForAction(action) is not None)
        assert widget.isVisibleTo(window), f"{action.text()!r}'s toolbar button is not visible"


def test_editing_marks_dirty(window):
    assert not window._dirty
    _add_valid_spacecraft(window)
    assert window._dirty
    assert window.windowTitle().endswith("*")


def test_save_as_then_open_round_trip(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    _add_valid_spacecraft(window)
    save_path = tmp_path / "test_scenario.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(save_path), "")))
    window.on_save_as()

    assert save_path.exists()
    assert not window._dirty
    assert window._current_path == save_path

    window.on_new()
    assert window._current_path is None
    assert window.scenario_editor.spacecraft_list.to_list() == []

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(save_path), "")))
    window.on_open()
    assert window._current_path == save_path
    assert window.scenario_editor.spacecraft_list.to_list()[0].name == "sat-1"


def test_save_with_invalid_scenario_shows_error_and_does_not_write(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    save_path = tmp_path / "invalid.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(save_path), "")))
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    window.on_save_as()  # no spacecraft yet -- invalid

    assert not save_path.exists()
    assert len(critical_calls) == 1


def test_open_missing_file_shows_error(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    missing = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(missing), "")))
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    window.on_open()
    assert len(critical_calls) == 1
    assert window._current_path is None


def test_window_starts_on_load_scenario_tab(window):
    assert window.left_tabs.currentWidget() is window.load_scenario_widget


def test_choosing_a_template_opens_it_and_switches_to_editor_tab(window):
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR

    template_path = sorted(TEMPLATES_DIR.glob("*.json"))[0]

    window.load_scenario_widget.path_chosen.emit(template_path)

    assert window._current_path == template_path
    assert window.left_tabs.currentWidget() is window.scenario_editor
    assert len(window.scenario_editor.spacecraft_list.to_list()) >= 1


def test_choosing_a_template_with_unsaved_changes_prompts_first(window, monkeypatch):
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from PySide6.QtWidgets import QMessageBox

    _add_valid_spacecraft(window)
    question_calls = []
    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: question_calls.append(1) or QMessageBox.StandardButton.Cancel))

    template_path = sorted(TEMPLATES_DIR.glob("*.json"))[0]
    window.load_scenario_widget.path_chosen.emit(template_path)

    assert len(question_calls) == 1
    # Cancelled -- the original (dirty) scenario must still be showing,
    # not the template that was about to replace it.
    assert window._current_path is None
    assert window.left_tabs.currentWidget() is window.load_scenario_widget


def test_choosing_a_customized_scenario_opens_it_with_no_current_path(window):
    """gui.template_wizard.TemplateCustomizeWizard emits an in-memory
    Scenario, not a file path -- _on_load_scenario_customized must leave
    _current_path at None (so on_save() routes through on_save_as()
    rather than silently writing over the original template file this
    scenario was built from).
    """
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.schema import load_scenario

    template_path = TEMPLATES_DIR / "03_geo_station_keeping.json"
    scenario = load_scenario(template_path)
    scenario.spacecraft[0].geo_station_keeping.longitude_deadband_deg = 0.1

    window.load_scenario_widget.scenario_customized.emit(scenario)

    assert window._current_path is None
    assert window.left_tabs.currentWidget() is window.scenario_editor
    loaded = window.scenario_editor.to_scenario()
    assert loaded.spacecraft[0].geo_station_keeping.longitude_deadband_deg == 0.1
    # The original template file itself must be untouched.
    assert load_scenario(template_path).spacecraft[0].geo_station_keeping.longitude_deadband_deg != 0.1


def test_choosing_a_customized_scenario_with_unsaved_changes_prompts_first(window, monkeypatch):
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.schema import load_scenario
    from PySide6.QtWidgets import QMessageBox

    _add_valid_spacecraft(window)
    question_calls = []
    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: question_calls.append(1) or QMessageBox.StandardButton.Cancel))

    scenario = load_scenario(TEMPLATES_DIR / "03_geo_station_keeping.json")
    window.load_scenario_widget.scenario_customized.emit(scenario)

    assert len(question_calls) == 1
    assert window.left_tabs.currentWidget() is window.load_scenario_widget


def test_customized_scenario_that_fails_validation_shows_error_not_crash(window, monkeypatch):
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.schema import load_scenario
    from PySide6.QtWidgets import QMessageBox

    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    scenario = load_scenario(TEMPLATES_DIR / "03_geo_station_keeping.json")
    scenario.spacecraft[0].geo_station_keeping.longitude_deadband_deg = -1.0  # invalid: must be > 0

    window.load_scenario_widget.scenario_customized.emit(scenario)

    assert len(critical_calls) == 1
    assert window.left_tabs.currentWidget() is window.load_scenario_widget


def test_on_new_switches_to_editor_tab(window):
    window.left_tabs.setCurrentWidget(window.load_scenario_widget)
    window.on_new()
    assert window.left_tabs.currentWidget() is window.scenario_editor


def test_open_path_returns_true_on_success_false_on_failure(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR

    template_path = sorted(TEMPLATES_DIR.glob("*.json"))[0]
    assert window.open_path(template_path) is True

    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    missing = tmp_path / "does_not_exist.json"
    assert window.open_path(missing) is False


@pytest.mark.skipif(_BASILISK_AVAILABLE, reason="this test's premise is specifically that Basilisk is unavailable")
def test_run_without_basilisk_shows_error_and_reenables_action(window, qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    _add_valid_spacecraft(window)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    window.on_run()
    assert not window.run_action.isEnabled()
    qtbot.waitUntil(lambda: window.run_action.isEnabled(), timeout=5000)

    assert len(critical_calls) == 1
    assert "Basilisk is not installed" in critical_calls[0][2]


def test_run_with_invalid_scenario_shows_error_without_starting_worker(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    window.on_run()  # no spacecraft -- invalid, should never construct a RunWorker

    assert len(critical_calls) == 1
    assert window._run_worker is None


def test_close_with_unsaved_changes_prompts_and_cancel_blocks_close(window, monkeypatch):
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QMessageBox

    _add_valid_spacecraft(window)
    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel))

    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()


def test_close_with_unsaved_changes_discard_allows_close(window, monkeypatch):
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QMessageBox

    _add_valid_spacecraft(window)
    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard))

    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()


def test_configure_vizard_sets_request(window, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.vizard_dialog import VizardDialog

    assert window._vizard_request is None

    def fake_exec(self):
        self.live_stream_radio.setChecked(True)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(VizardDialog, "exec", fake_exec)
    window.on_configure_vizard()

    assert window._vizard_request is not None
    assert window._vizard_request.live_stream is True


def test_configure_vizard_cancel_leaves_request_unchanged(window, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.vizard_dialog import VizardDialog

    monkeypatch.setattr(VizardDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    window.on_configure_vizard()
    assert window._vizard_request is None


def test_run_passes_vizard_request_to_worker(window, monkeypatch):
    from spacemissionstudio.gui.main_window import MainWindow
    from spacemissionstudio.gui.run_worker import RunWorker
    from spacemissionstudio.engine.vizard import VizardRequest

    _add_valid_spacecraft(window)
    window._vizard_request = VizardRequest(live_stream=True)
    # on_run() now confirms Vizard is connected before starting a
    # live-stream run (see its own comment) -- stubbed out here since
    # this test is about vizard_request passthrough, not the Vizard
    # process itself (see test_run_ensures_vizard_is_running_before_a_
    # live_stream_run for that).
    monkeypatch.setattr(MainWindow, "on_launch_vizard", lambda self: True)

    captured = {}
    original_init = RunWorker.__init__

    def spy_init(self, scenario, vizard_request=None, live=False, parent=None, allow_scripts=False):
        captured["vizard_request"] = vizard_request
        original_init(self, scenario, vizard_request=vizard_request, live=live, parent=parent,
                      allow_scripts=allow_scripts)

    monkeypatch.setattr(RunWorker, "__init__", spy_init)
    monkeypatch.setattr(RunWorker, "start", lambda self: None)  # don't actually spin up the thread

    window.on_run()
    assert captured["vizard_request"] is window._vizard_request


def test_run_starts_busy_indicator_and_disables_other_run_actions(window, monkeypatch):
    from spacemissionstudio.gui.run_worker import RunWorker

    _add_valid_spacecraft(window)
    monkeypatch.setattr(RunWorker, "start", lambda self: None)  # don't actually spin up the thread

    window.on_run()
    assert window._busy_timer.isActive()
    assert not window.run_action.isEnabled()
    assert not window.live_plot_action.isEnabled()  # can't toggle it mid-run either
    assert not window.monte_carlo_action.isEnabled()  # can't start a second run while one is in flight
    assert "Running" in window.statusBar().currentMessage()


def test_live_plot_action_is_checked_by_default(window):
    assert window.live_plot_action.isChecked()


def test_run_passes_live_flag_from_action_to_worker(window, monkeypatch):
    from spacemissionstudio.gui.run_worker import RunWorker

    _add_valid_spacecraft(window)
    captured = {}
    original_init = RunWorker.__init__

    def spy_init(self, scenario, vizard_request=None, live=False, parent=None, allow_scripts=False):
        captured["live"] = live
        captured["allow_scripts"] = allow_scripts
        original_init(self, scenario, vizard_request=vizard_request, live=live, parent=parent,
                      allow_scripts=allow_scripts)

    monkeypatch.setattr(RunWorker, "__init__", spy_init)
    monkeypatch.setattr(RunWorker, "start", lambda self: None)
    monkeypatch.setattr(type(window), "_confirm_script_blocks", lambda self, blocks: True)

    window.live_plot_action.setChecked(True)
    window.on_run()
    assert captured["live"] is True

    window.live_plot_action.setChecked(False)
    window.on_run()
    assert captured["live"] is False


def test_run_with_live_plot_clears_previous_result_and_shows_results_tab(window, monkeypatch):
    from spacemissionstudio.engine.results import ResultSet, TimeSeries
    from spacemissionstudio.gui.run_worker import RunWorker

    _add_valid_spacecraft(window)
    monkeypatch.setattr(RunWorker, "start", lambda self: None)

    stale = ResultSet(scenario_name="stale")
    stale.add(TimeSeries("sat-1.position_N", [0.0], ("x", "y", "z"), [[0.0, 0.0, 0.0]], units="m"))
    window.results_widget.set_result(stale)
    window.right_tabs.setCurrentWidget(window.data_panel_widget)

    window.live_plot_action.setChecked(True)
    window.on_run()

    assert window.results_widget.series_combo.count() == 0
    assert window.right_tabs.currentWidget() is window.results_widget


def test_run_finished_preserves_users_series_selection(window):
    """Regression test for an audit finding: _on_run_finished() used to
    call ResultsWidget.set_result(), which unconditionally rebuilds
    series_combo and resets its selection to the first series -- so the
    instant a live-watched run actually finished, whatever series the
    user had picked to watch snapped back to the first one. It must use
    set_live_result() instead, which only rebuilds when the series set
    itself changes.
    """
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    def _result():
        rs = ResultSet(scenario_name="test")
        rs.add(TimeSeries("sat-1.position_N", [0.0], ("x", "y", "z"), [[0.0, 0.0, 0.0]], units="m"))
        rs.add(TimeSeries("sat-1.velocity_N", [0.0], ("x", "y", "z"), [[0.0, 0.0, 0.0]], units="m/s"))
        return rs

    window._on_run_progress(_result(), 0.5)
    window.results_widget.series_combo.setCurrentIndex(1)  # "sat-1.velocity_N"

    window._on_run_finished(_result())

    assert window.results_widget.series_combo.currentIndex() == 1


def test_close_while_run_in_progress_is_blocked(window, qtbot, monkeypatch):
    import threading

    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QMessageBox
    from spacemissionstudio.gui.run_worker import RunWorker

    _add_valid_spacecraft(window)
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    release = threading.Event()
    monkeypatch.setattr(RunWorker, "run", lambda self: release.wait(5))

    window.on_run()
    qtbot.waitUntil(lambda: window._run_worker.isRunning(), timeout=5000)

    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert len(info_calls) == 1

    release.set()
    qtbot.waitUntil(lambda: not window._run_worker.isRunning(), timeout=5000)


def test_run_progress_updates_results_widget_and_busy_bar(window):
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    window._start_busy("Running test...", determinate=True)
    partial = ResultSet(scenario_name="test")
    partial.add(TimeSeries("sat-1.position_N", [0.0, 1.0], ("x", "y", "z"),
                            [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], units="m"))

    window._on_run_progress(partial, 0.5)

    assert window.results_widget.series_combo.count() == 1
    assert window._busy_progress.value() == 50


def test_run_progress_exception_is_caught_not_propagated(window, monkeypatch):
    """Real user feedback: running another simulation after a previous
    one "seems to break a lot of things in the GUI" -- the app should
    never crash or get stuck just because something unusual happened.
    If a live-progress update ever raises (for whatever reason, on
    whichever chunk), _on_run_progress must swallow it (logged, surfaced
    once via a warning dialog) rather than let it propagate out through
    Qt's own signal dispatch -- the simulation itself, on its own
    thread, is completely unaffected either way.
    """
    from spacemissionstudio.engine.results import ResultSet
    from spacemissionstudio.gui import main_window as main_window_module

    window._start_busy("Running test...", determinate=True)
    monkeypatch.setattr(
        window.results_widget, "set_live_result",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    warnings = []
    monkeypatch.setattr(main_window_module.QMessageBox, "warning",
                         lambda *a, **k: warnings.append(a) or None)

    window._on_run_progress(ResultSet(scenario_name="test"), 0.5)  # must not raise

    assert len(warnings) == 1


def test_run_progress_exception_dialog_shown_only_once_per_run(window, monkeypatch):
    from spacemissionstudio.engine.results import ResultSet
    from spacemissionstudio.gui import main_window as main_window_module

    window._start_busy("Running test...", determinate=True)
    monkeypatch.setattr(
        window.results_widget, "set_live_result",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    warnings = []
    monkeypatch.setattr(main_window_module.QMessageBox, "warning",
                         lambda *a, **k: warnings.append(a) or None)

    for _ in range(5):
        window._on_run_progress(ResultSet(scenario_name="test"), 0.5)

    assert len(warnings) == 1  # not a dialog-per-chunk storm

    # A fresh on_run() (a new run starting) resets the suppression --
    # confirmed via the same flag on_run() itself resets, not by driving
    # a full real run here.
    window._progress_error_shown = False
    window._on_run_progress(ResultSet(scenario_name="test"), 0.5)
    assert len(warnings) == 2


def test_run_finished_exception_still_stops_busy_indicator(window, monkeypatch):
    """Same robustness principle as _on_run_progress's own tests, for the
    terminal handler: if displaying a successfully-finished run's results
    ever raises, the busy/Run-disabled state must still clear -- the
    historically worst form of "breaks a lot of things" is the user
    being unable to start another run at all without restarting the app.
    """
    from spacemissionstudio.engine.results import ResultSet
    from spacemissionstudio.gui import main_window as main_window_module

    window._start_busy("Running test...")
    monkeypatch.setattr(
        window.results_widget, "set_live_result",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", lambda *a, **k: None)

    window._on_run_finished(ResultSet(scenario_name="test", series={}))  # must not raise

    assert not window._busy_timer.isActive()
    assert window.run_action.isEnabled()


def test_run_cancelled_exception_still_stops_busy_indicator(window, monkeypatch):
    from spacemissionstudio.engine.results import ResultSet
    from spacemissionstudio.gui import main_window as main_window_module

    window._start_busy("Running test...")
    window.abort_action.setEnabled(True)
    monkeypatch.setattr(
        window.results_widget, "set_live_result",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(main_window_module.QMessageBox, "warning", lambda *a, **k: None)

    window._on_run_cancelled(ResultSet(scenario_name="test", series={}))  # must not raise

    assert not window._busy_timer.isActive()
    assert window.run_action.isEnabled()
    assert not window.abort_action.isEnabled()


def test_on_run_clears_previous_results_even_when_not_live(window, monkeypatch):
    """Real gap found while investigating the "breaks a lot of things"
    report: results_widget/mission_dashboard_widget were only cleared at
    the start of a new run when Live Plot was on -- a non-live run (or
    one with a mission_sequence) left the PREVIOUS run's plot on screen
    for the entire new run, indistinguishable from this run already
    having (stale, wrong) results before it actually does.
    """
    from spacemissionstudio.engine.results import ResultSet, TimeSeries
    from spacemissionstudio.gui.run_worker import RunWorker

    _add_valid_spacecraft(window)
    stale = ResultSet(scenario_name="stale")
    stale.add(TimeSeries("sat-1.position_N", [0.0, 1.0], ("x", "y", "z"),
                          [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], units="m"))
    window.results_widget.set_result(stale)
    assert window.results_widget.series_combo.count() == 1

    window.live_plot_action.setChecked(False)
    monkeypatch.setattr(RunWorker, "start", lambda self: None)  # don't actually spin up the thread

    window.on_run()

    assert window.results_widget.series_combo.count() == 0


def test_on_run_captures_epoch_and_passes_it_to_results_widget(window, monkeypatch):
    from spacemissionstudio.gui.run_worker import RunWorker

    _add_valid_spacecraft(window)
    window.scenario_editor.epoch_edit.setText("2031-05-01T00:00:00")
    monkeypatch.setattr(RunWorker, "start", lambda self: None)  # don't actually spin up the thread

    window.on_run()

    assert window._last_run_epoch_utc == "2031-05-01T00:00:00"


def test_run_finished_passes_captured_epoch_to_results_widget(window):
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    window._last_run_epoch_utc = "2032-01-01T00:00:00"
    result = ResultSet(scenario_name="test")
    result.add(TimeSeries("sat-1.position_N", [0.0, 1.0], ("x", "y", "z"),
                           [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], units="m"))

    window._on_run_finished(result)

    assert window.results_widget._epoch_utc == "2032-01-01T00:00:00"


def test_run_finished_stops_busy_indicator_and_reenables_actions(window):
    from spacemissionstudio.engine.results import ResultSet

    window._start_busy("Running test...")
    window._on_run_finished(ResultSet(scenario_name="test", series={}))
    assert not window._busy_timer.isActive()
    assert window.run_action.isEnabled()
    assert window.monte_carlo_action.isEnabled()


def test_run_failed_stops_busy_indicator_and_reenables_actions(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    window._start_busy("Running test...")
    window._on_run_failed("boom")
    assert not window._busy_timer.isActive()
    assert window.run_action.isEnabled()
    assert window.monte_carlo_action.isEnabled()


def test_run_failed_dialog_mentions_the_log_file_when_configured(window, monkeypatch):
    """Direct user feedback: a bare error message with nothing else to go
    on (e.g. a raw C++ exception's str()) left no way to actually
    diagnose an unexpected failure -- see logging_setup's own module
    docstring. Once logging is configured (real entry points always do
    this; a bare MainWindow() in a test does not, by default -- see the
    test right after this one for that case), the error dialog must say
    where the full traceback landed.
    """
    from pathlib import Path

    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.gui import main_window

    fake_log_path = Path("/tmp/fake/spacemissionstudio_20300101T000000Z.log")
    monkeypatch.setattr(main_window, "get_log_file_path", lambda: fake_log_path)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    window._on_run_failed("boom")

    assert len(critical_calls) == 1
    shown_message = critical_calls[0][2]
    assert "boom" in shown_message
    assert str(fake_log_path) in shown_message


def test_run_failed_dialog_omits_the_log_hint_when_logging_was_never_configured(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.gui import main_window

    monkeypatch.setattr(main_window, "get_log_file_path", lambda: None)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    window._on_run_failed("boom")

    assert critical_calls[0][2] == "boom"


def test_monte_carlo_failed_dialog_mentions_the_log_file_when_configured(window, monkeypatch):
    from pathlib import Path

    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.gui import main_window

    fake_log_path = Path("/tmp/fake/spacemissionstudio_20300101T000000Z.log")
    monkeypatch.setattr(main_window, "get_log_file_path", lambda: fake_log_path)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    window._on_monte_carlo_failed("boom")

    assert str(fake_log_path) in critical_calls[0][2]


def test_run_monte_carlo_rejects_disabled_monte_carlo(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    _add_valid_spacecraft(window)  # monte_carlo defaults to disabled
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    window.on_run_monte_carlo()
    assert len(critical_calls) == 1
    assert "enable monte carlo" in critical_calls[0][2].lower()
    assert window._mc_worker is None


def test_run_monte_carlo_starts_worker_with_chosen_archive_dir(window, monkeypatch, tmp_path):
    from spacemissionstudio.gui.run_worker import MonteCarloWorker
    from spacemissionstudio.schema.scenario import DispersionConfig, MonteCarloConfig
    from PySide6.QtWidgets import QFileDialog

    _add_valid_spacecraft(window)
    window.scenario_editor.monte_carlo_group.set_spacecraft_names(["sat-1"])
    window.scenario_editor.monte_carlo_group.from_dataclass(MonteCarloConfig(
        enabled=True, num_runs=3,
        dispersions=[DispersionConfig(spacecraft="sat-1", quantity="dry_mass_kg", kind="uniform", bounds=[90, 110])],
    ))

    archive_dir = tmp_path / "mc_archive"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(archive_dir)))
    monkeypatch.setattr(MonteCarloWorker, "start", lambda self: None)  # don't actually spin up the thread

    window.on_run_monte_carlo()
    assert window._mc_worker is not None
    assert window._mc_worker.archive_dir == archive_dir
    assert window._mc_worker.mc_config.num_runs == 3
    assert not window.monte_carlo_action.isEnabled()
    assert not window.run_action.isEnabled()  # can't start a second run while one is in flight
    assert window._busy_timer.isActive()


def test_monte_carlo_finished_stops_busy_indicator_and_reenables_actions(window):
    window._start_busy("Running Monte Carlo test...")
    window._on_monte_carlo_finished([])
    assert not window._busy_timer.isActive()
    assert window.run_action.isEnabled()
    assert window.monte_carlo_action.isEnabled()


def test_monte_carlo_finished_with_no_failures_shows_a_toast(window):
    """Regression guard: found while checking this tab's feedback for
    consistency -- _on_run_finished (the single-run sibling) already
    shows a toast on success, but this Monte Carlo equivalent had none
    at all.
    """
    window._start_busy("Running Monte Carlo test...")
    window._on_monte_carlo_finished([])

    toasts = getattr(window, "_spacemissionstudio_active_toasts", [])
    assert any("Monte Carlo complete" in t.text() for t in toasts)


def test_monte_carlo_finished_with_failures_does_not_show_a_toast(window, monkeypatch):
    """The QMessageBox.warning already shown for a partial failure is
    strong enough feedback on its own -- same reasoning as
    _on_run_failed having no toast alongside its own QMessageBox.critical.
    """
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    window._start_busy("Running Monte Carlo test...")
    window._on_monte_carlo_finished([2])

    toasts = getattr(window, "_spacemissionstudio_active_toasts", [])
    assert not any("Monte Carlo complete" in t.text() for t in toasts)


def test_monte_carlo_failed_stops_busy_indicator_and_reenables_actions(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    window._start_busy("Running Monte Carlo test...")
    window._on_monte_carlo_failed("boom")
    assert not window._busy_timer.isActive()
    assert window.run_action.isEnabled()
    assert window.monte_carlo_action.isEnabled()


def test_run_monte_carlo_cancel_dialog_does_not_start_worker(window, monkeypatch):
    from spacemissionstudio.schema.scenario import MonteCarloConfig
    from PySide6.QtWidgets import QFileDialog

    _add_valid_spacecraft(window)
    window.scenario_editor.monte_carlo_group.set_spacecraft_names(["sat-1"])
    window.scenario_editor.monte_carlo_group.from_dataclass(MonteCarloConfig(enabled=True))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))

    window.on_run_monte_carlo()
    assert window._mc_worker is None


def test_run_with_mission_sequence_ignores_live_flag_and_shows_mission_output(window, monkeypatch):
    from spacemissionstudio.gui.run_worker import RunWorker
    from spacemissionstudio.schema.command import Command

    _add_valid_spacecraft(window)
    window.scenario_editor.mission_sequence_editor.from_command_list([
        Command(kind="script_block", params={"code": "pass"}),
    ])
    window.scenario_editor.changed.emit()

    captured = {}
    original_init = RunWorker.__init__

    def spy_init(self, scenario, vizard_request=None, live=False, parent=None, allow_scripts=False):
        captured["live"] = live
        captured["allow_scripts"] = allow_scripts
        original_init(self, scenario, vizard_request=vizard_request, live=live, parent=parent,
                      allow_scripts=allow_scripts)

    monkeypatch.setattr(RunWorker, "__init__", spy_init)
    monkeypatch.setattr(RunWorker, "start", lambda self: None)
    monkeypatch.setattr(type(window), "_confirm_script_blocks", lambda self, blocks: True)

    window.live_plot_action.setChecked(True)
    window.on_run()

    # MissionEngine has no run_live() equivalent (see RunWorker.run()) --
    # a mission_sequence run always ignores the live-plot toggle.
    assert captured["live"] is False


def test_script_blocks_run_only_after_the_user_confirms(window, monkeypatch):
    """SRS-S-03: a scenario with a script_block asks first. Declining
    starts nothing; confirming starts the run with the consent passed on."""
    from spacemissionstudio.gui.run_worker import RunWorker
    from spacemissionstudio.schema.command import Command

    _add_valid_spacecraft(window)
    window.scenario_editor.mission_sequence_editor.from_command_list([
        Command(kind="script_block", label="mine", params={"code": "print('hello')"}),
    ])
    window.scenario_editor.changed.emit()
    started, asked = [], []
    monkeypatch.setattr(RunWorker, "start", lambda self: started.append(self.allow_scripts))

    monkeypatch.setattr(type(window), "_confirm_script_blocks", lambda self, blocks: asked.append(blocks) or False)
    window.on_run()
    assert started == []
    assert [path for path, _ in asked[0]] == ["mission_sequence[0]"]

    monkeypatch.setattr(type(window), "_confirm_script_blocks", lambda self, blocks: True)
    window.on_run()
    assert started == [True]


def test_script_block_confirmation_shows_the_code_and_defaults_to_no(window, monkeypatch):
    """The confirmation lists each block's path and code, and No is the
    default button."""
    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.schema.command import Command

    seen = {}

    def fake_exec(box):
        seen["details"] = box.detailedText()
        seen["default"] = box.defaultButton() is box.button(QMessageBox.StandardButton.No)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    block = Command(kind="script_block", label="mine", params={"code": "print('hello')"})
    assert window._confirm_script_blocks([("mission_sequence[0]", block)]) is False
    assert "mission_sequence[0] (mine):" in seen["details"] and "print('hello')" in seen["details"]
    assert seen["default"]


def test_run_finished_with_command_summary_shows_mission_output_tab(window):
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry, ResultSet

    summary = CommandSummary(reports=[ReportEntry(label="x", t_s=1.0, values={})], commands_executed=1)
    window._on_run_finished(ResultSet(scenario_name="test", series={}), summary)

    assert window.right_tabs.currentWidget() is window.mission_output_widget
    assert "1 command run" in window.mission_output_widget.summary_label.text()


def test_run_finished_without_command_summary_shows_results_tab(window):
    from spacemissionstudio.engine.results import ResultSet

    window.right_tabs.setCurrentWidget(window.data_panel_widget)
    window._on_run_finished(ResultSet(scenario_name="test", series={}))
    assert window.right_tabs.currentWidget() is window.results_widget


class _FakeVizardProcess:
    def __init__(self, pid=999):
        self.pid = pid
        self._alive = True
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self):
        return None if self._alive else 0

    def kill_for_test(self):
        self._alive = False

    def terminate(self):
        self.terminate_calls += 1
        self._alive = False

    def kill(self):
        self.kill_calls += 1
        self._alive = False

    def wait(self, timeout=None):
        return 0


def test_launch_vizard_starts_it_when_not_running(window, monkeypatch):
    from pathlib import Path

    from spacemissionstudio.gui import main_window

    calls = []
    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: Path("/fake/Vizard"))
    monkeypatch.setattr(main_window, "launch_vizard",
                         lambda path, direct_comm_address=None: calls.append(path) or _FakeVizardProcess())

    window.on_launch_vizard()

    assert calls == [Path("/fake/Vizard")]
    assert "Launched Vizard" in window.statusBar().currentMessage()


def test_launch_vizard_does_not_relaunch_while_already_running(window, monkeypatch):
    """The exact behavior the "Launch Vizard" action depends on: clicking
    it again while Vizard is still open must not spawn a second instance.
    """
    from pathlib import Path

    from spacemissionstudio.gui import main_window

    calls = []
    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: Path("/fake/Vizard"))
    monkeypatch.setattr(main_window, "launch_vizard",
                         lambda path, direct_comm_address=None: calls.append(path) or _FakeVizardProcess())

    window.on_launch_vizard()
    window.on_launch_vizard()
    window.on_launch_vizard()

    assert len(calls) == 1
    assert "already running" in window.statusBar().currentMessage().lower()


def test_launch_vizard_relaunches_after_the_process_exits(window, monkeypatch):
    from pathlib import Path

    from spacemissionstudio.gui import main_window

    processes = [_FakeVizardProcess(pid=111), _FakeVizardProcess(pid=222)]
    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: Path("/fake/Vizard"))
    monkeypatch.setattr(main_window, "launch_vizard", lambda path, direct_comm_address=None: processes.pop(0))

    window.on_launch_vizard()
    first = window._vizard_process
    first.kill_for_test()

    window.on_launch_vizard()
    assert window._vizard_process.pid == 222


def test_launch_vizard_not_found_falls_back_to_browse(window, monkeypatch):
    """`on_launch_vizard()`'s own contract once `find_vizard_executable()`
    comes up empty: whatever `_locate_vizard()` resolves to (via either
    its "Download" or "Browse..." path -- see the dedicated tests for
    those below) gets launched. Mocked at that seam rather than
    QFileDialog directly, since which of the two sub-paths the user took
    is no longer this test's concern.
    """
    from pathlib import Path

    from spacemissionstudio.gui import main_window

    picked = Path("/picked/Vizard")
    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: None)
    monkeypatch.setattr(main_window.MainWindow, "_locate_vizard", lambda self: picked)
    monkeypatch.setattr(main_window, "launch_vizard", lambda path, direct_comm_address=None: _FakeVizardProcess())

    window.on_launch_vizard()

    assert window._vizard_process is not None


def test_launch_vizard_not_found_and_resolution_cancelled_does_nothing(window, monkeypatch):
    from spacemissionstudio.gui import main_window

    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: None)
    monkeypatch.setattr(main_window.MainWindow, "_locate_vizard", lambda self: None)
    launch_calls = []
    monkeypatch.setattr(main_window, "launch_vizard",
                         lambda path, direct_comm_address=None: launch_calls.append(path))

    window.on_launch_vizard()

    assert launch_calls == []
    assert window._vizard_process is None


def test_locate_vizard_browse_option_remembers_the_picked_path(window, monkeypatch):
    """The original manual-browse path, now reached via the "not found"
    QMessageBox's "Browse..." button -- clicked here by text match (see
    this test's own `_click` helper) rather than assuming a specific
    button object, since QMessageBox builds its buttons fresh each call.
    """
    from pathlib import Path

    from PySide6.QtWidgets import QFileDialog, QMessageBox

    picked = Path("/picked/Vizard")
    monkeypatch.setattr(QMessageBox, "exec", _click_message_box_button("Browse..."))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(picked), "")))
    remembered = []
    monkeypatch.setattr("spacemissionstudio.gui.main_window.remember_vizard_executable",
                         lambda path: remembered.append(path))

    result = window._locate_vizard()

    assert result == picked
    assert remembered == [picked]


def test_locate_vizard_browse_cancelled_returns_none(window, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(QMessageBox, "exec", _click_message_box_button("Browse..."))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))

    assert window._locate_vizard() is None


def test_locate_vizard_dismissed_returns_none(window, monkeypatch):
    """Neither "Download Vizard" nor "Browse..." clicked (e.g. the dialog
    was closed via its window decoration) -- QMessageBox's own
    `clickedButton()` then returns its implicit Cancel button, which
    matches neither of the two named buttons this method checks for.
    """
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)  # never click anything

    assert window._locate_vizard() is None


class _FakeVizardFetchWorker(QObject):
    """Stands in for ``VizardFetchWorker`` without spinning up a real
    ``QThread`` -- mirrors this test file's own ``RunWorker``-patching
    convention (``monkeypatch.setattr(RunWorker, "start", ...)``) rather
    than exercising real threading/network in a unit test. Signals are
    emitted synchronously from :meth:`start`, exactly as they would be
    for a worker whose background thread happened to finish before the
    caller's nested ``QEventLoop`` even started spinning -- a real,
    documented-safe case for ``QEventLoop`` (``quit()`` before ``exec()``
    just makes the next ``exec()`` return immediately), not a test-only
    shortcut.
    """

    finished_ok = Signal(str)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, outcome_path=None, outcome_error=None, parent=None):
        super().__init__(parent)
        self._outcome_path = outcome_path
        self._outcome_error = outcome_error
        self.cancel_requested = False

    def request_cancel(self):
        self.cancel_requested = True

    def start(self):
        if self._outcome_error is not None:
            self.failed.emit(self._outcome_error)
        else:
            self.finished_ok.emit(self._outcome_path)

    def wait(self):
        pass


def test_fetch_vizard_with_progress_success_remembers_and_returns_the_path(window, monkeypatch):
    from pathlib import Path

    from spacemissionstudio.gui import main_window

    fetched = Path("/fetched/Vizard")
    monkeypatch.setattr(main_window, "VizardFetchWorker",
                         lambda parent=None: _FakeVizardFetchWorker(outcome_path=str(fetched)))
    remembered = []
    monkeypatch.setattr(main_window, "remember_vizard_executable", lambda path: remembered.append(path))

    result = window._fetch_vizard_with_progress()

    assert result == fetched
    assert remembered == [fetched]


def test_fetch_vizard_with_progress_failure_shows_error_and_returns_none(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.gui import main_window

    monkeypatch.setattr(main_window, "VizardFetchWorker",
                         lambda parent=None: _FakeVizardFetchWorker(outcome_error="could not download: boom"))
    shown = []
    monkeypatch.setattr(main_window.QMessageBox, "critical",
                         staticmethod(lambda *a, **k: shown.append(a) or QMessageBox.StandardButton.Ok))

    result = window._fetch_vizard_with_progress()

    assert result is None
    assert shown  # a critical dialog was shown with the failure reason


def _click_message_box_button(button_text):
    """Returns a replacement for ``QMessageBox.exec`` that, instead of
    actually blocking on user input, finds one of the box's own
    ``addButton()``-added buttons by its visible text and clicks it --
    exercising the real ``clickedButton()``/``buttonClicked`` machinery
    (that connection is wired in ``addButton()`` itself, not only while
    ``exec()`` is actually running) rather than faking the outcome.
    """
    def _exec(self):
        for button in self.buttons():
            if button.text() == button_text:
                button.click()
                return 0
        raise AssertionError(f"no QMessageBox button with text {button_text!r}")
    return _exec


def test_launch_vizard_failure_shows_error(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from pathlib import Path

    from spacemissionstudio.gui import main_window

    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: Path("/fake/Vizard"))

    def raise_oserror(path, direct_comm_address=None):
        raise OSError("permission denied")

    monkeypatch.setattr(main_window, "launch_vizard", raise_oserror)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    window.on_launch_vizard()

    assert len(critical_calls) == 1
    assert window._vizard_process is None


def test_launch_vizard_passes_direct_comm_address_when_live_stream_configured(window, monkeypatch):
    """Direct user feedback: manually launching Vizard for a live-stream
    run left it sitting on its own manual launcher screen (see
    on_launch_vizard()'s own docstring) -- it must be started with its
    -directComm flag whenever Vizard Configuration is set to live-stream.
    """
    from pathlib import Path

    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.engine.vizard import VizardRequest
    from spacemissionstudio.gui import main_window
    from spacemissionstudio.gui.vizard_launcher import DEFAULT_LIVE_STREAM_ADDRESS

    window._vizard_request = VizardRequest(live_stream=True)
    calls = []
    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: Path("/fake/Vizard"))
    monkeypatch.setattr(main_window, "launch_vizard",
                         lambda path, direct_comm_address=None: calls.append(direct_comm_address)
                         or _FakeVizardProcess())
    # A real launch with a -directComm address shows a one-time
    # "needs one click" info dialog (see on_launch_vizard()'s own
    # comment) -- mocked here since this test is about the address
    # passed to launch_vizard(), not that dialog itself (see
    # test_launch_vizard_shows_the_one_click_hint_once_per_session for
    # that).
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    window.on_launch_vizard()

    assert calls == [DEFAULT_LIVE_STREAM_ADDRESS]


def test_launch_vizard_shows_the_one_click_hint_once_per_session(window, monkeypatch):
    """-directComm pre-fills Vizard's socket address but (confirmed by
    direct user report) does not click "Start Visualization" for the
    user -- shown once per session as an info dialog so that one
    remaining click isn't a silent surprise, but not repeated on every
    single subsequent live-stream launch/run.
    """
    from pathlib import Path

    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.engine.vizard import VizardRequest
    from spacemissionstudio.gui import main_window

    window._vizard_request = VizardRequest(live_stream=True)
    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: Path("/fake/Vizard"))
    monkeypatch.setattr(main_window, "launch_vizard",
                         lambda path, direct_comm_address=None: _FakeVizardProcess())
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    assert not window._vizard_live_stream_hint_shown
    window.on_launch_vizard()
    assert len(info_calls) == 1
    assert "Start Visualization" in info_calls[0][2]
    assert window._vizard_live_stream_hint_shown

    # Vizard process still running -> "already running" early return,
    # no relaunch, no repeated dialog.
    window.on_launch_vizard()
    assert len(info_calls) == 1


def test_launch_vizard_passes_no_direct_comm_address_without_live_stream(window, monkeypatch):
    from pathlib import Path

    from spacemissionstudio.gui import main_window

    assert window._vizard_request is None  # save-file mode, or never configured at all
    calls = []
    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: Path("/fake/Vizard"))
    monkeypatch.setattr(main_window, "launch_vizard",
                         lambda path, direct_comm_address=None: calls.append(direct_comm_address)
                         or _FakeVizardProcess())

    window.on_launch_vizard()

    assert calls == [None]


def test_launch_vizard_relaunches_a_mismatched_already_running_instance(window, monkeypatch):
    """The known residual gap this closes: Vizard was already launched
    (by this same session's "Launch Vizard" button) before live-stream
    was ever configured -- e.g. for a save-file run, or before Vizard
    Configuration was set at all -- so the running instance has no
    -directComm connection. Simply trusting "already running" here would
    reproduce the exact original bug one launch later; it must be
    terminated and replaced with a live-stream-ready one instead.
    """
    from pathlib import Path

    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.engine.vizard import VizardRequest
    from spacemissionstudio.gui import main_window
    from spacemissionstudio.gui.vizard_launcher import DEFAULT_LIVE_STREAM_ADDRESS

    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: Path("/fake/Vizard"))
    launch_calls = []
    monkeypatch.setattr(main_window, "launch_vizard",
                         lambda path, direct_comm_address=None: launch_calls.append(direct_comm_address)
                         or _FakeVizardProcess())
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    # First launch: no live-stream configured yet.
    window.on_launch_vizard()
    first_process = window._vizard_process
    assert launch_calls == [None]

    # Now live-stream gets configured, and Vizard is asked for again.
    window._vizard_request = VizardRequest(live_stream=True)
    window.on_launch_vizard()

    assert first_process.terminate_calls == 1
    assert launch_calls == [None, DEFAULT_LIVE_STREAM_ADDRESS]
    assert window._vizard_process is not first_process
    assert window._vizard_direct_comm_address == DEFAULT_LIVE_STREAM_ADDRESS


def test_launch_vizard_keeps_a_live_stream_ready_instance_for_a_later_save_file_launch(window, monkeypatch):
    """The opposite direction is NOT a mismatch worth relaunching over --
    a -directComm connection doesn't stop Vizard from also being used to
    open a save file, so an already-live-stream-ready instance is kept.
    """
    from pathlib import Path

    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.engine.vizard import VizardRequest
    from spacemissionstudio.gui import main_window

    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: Path("/fake/Vizard"))
    launch_calls = []
    monkeypatch.setattr(main_window, "launch_vizard",
                         lambda path, direct_comm_address=None: launch_calls.append(direct_comm_address)
                         or _FakeVizardProcess())
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    window._vizard_request = VizardRequest(live_stream=True)
    window.on_launch_vizard()
    first_process = window._vizard_process

    window._vizard_request = None  # switch to save-file/no request
    window.on_launch_vizard()

    assert first_process.terminate_calls == 0
    assert len(launch_calls) == 1  # never relaunched
    assert window._vizard_process is first_process


def test_launch_vizard_never_touches_an_instance_it_did_not_itself_launch(window, monkeypatch):
    """self._vizard_process is None (this session never launched Vizard
    itself) even though Vizard may well already be running externally --
    there is no reliable way to ask it whether it's connected, so a
    fresh, correctly-configured instance is launched alongside it rather
    than guessing about (or worse, killing) a process this app doesn't
    own.
    """
    from pathlib import Path

    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.engine.vizard import VizardRequest
    from spacemissionstudio.gui import main_window
    from spacemissionstudio.gui.vizard_launcher import DEFAULT_LIVE_STREAM_ADDRESS

    assert window._vizard_process is None
    window._vizard_request = VizardRequest(live_stream=True)
    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: Path("/fake/Vizard"))
    launch_calls = []
    monkeypatch.setattr(main_window, "launch_vizard",
                         lambda path, direct_comm_address=None: launch_calls.append(direct_comm_address)
                         or _FakeVizardProcess())
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    window.on_launch_vizard()

    assert launch_calls == [DEFAULT_LIVE_STREAM_ADDRESS]


def test_run_ensures_vizard_is_running_before_a_live_stream_run(window, monkeypatch):
    """Regression test for a real user report: a live-stream run appeared
    to hang at 0% with Abort having no effect, because Vizard was never
    actually connected (see on_run()'s own comment) -- on_run() must
    confirm Vizard first via on_launch_vizard(), not just hand the
    request to RunWorker and hope.
    """
    from spacemissionstudio.engine.vizard import VizardRequest
    from spacemissionstudio.gui.main_window import MainWindow
    from spacemissionstudio.gui.run_worker import RunWorker

    _add_valid_spacecraft(window)
    window._vizard_request = VizardRequest(live_stream=True)
    calls = []
    monkeypatch.setattr(MainWindow, "on_launch_vizard", lambda self: calls.append(1) or True)
    monkeypatch.setattr(RunWorker, "start", lambda self: None)  # don't actually spin up the thread

    window.on_run()

    assert calls == [1]
    assert window._run_worker is not None  # the run actually proceeded


def test_run_refuses_to_start_when_vizard_cannot_be_confirmed(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.engine.vizard import VizardRequest
    from spacemissionstudio.gui.main_window import MainWindow
    from spacemissionstudio.gui.run_worker import RunWorker

    _add_valid_spacecraft(window)
    window._vizard_request = VizardRequest(live_stream=True)
    monkeypatch.setattr(MainWindow, "on_launch_vizard", lambda self: False)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))
    start_calls = []
    monkeypatch.setattr(RunWorker, "start", lambda self: start_calls.append(1))

    window.on_run()

    assert len(critical_calls) == 1
    assert start_calls == []
    assert window._run_worker is None  # never even constructed


def test_run_always_relaunches_vizard_fresh_for_a_live_stream_run(window, monkeypatch):
    """Real user feedback: "when running a new simulation after a
    previous simulation finished, vizard should completely refresh so it
    actually displays only stuff from the current simulation, and not the
    previous one." Confirmed directly from Vizard's own Unity source (see
    on_run()'s own comment): a running Vizard Main Scene has no way to
    reset itself live, so reusing an already-running, matching instance
    across separate runs (on_launch_vizard()'s own deliberate behavior,
    still correct for its OWN "Launch Vizard" menu entry point) must NOT
    happen when on_run() itself starts a new live-stream run -- the
    previous self-launched process must always be terminated and a fresh
    one started, even though it would otherwise "match" and be reused.
    """
    from pathlib import Path

    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.engine.vizard import VizardRequest
    from spacemissionstudio.gui import main_window
    from spacemissionstudio.gui.run_worker import RunWorker

    _add_valid_spacecraft(window)
    window._vizard_request = VizardRequest(live_stream=True)
    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: Path("/fake/Vizard"))
    launch_calls = []
    processes = [_FakeVizardProcess(pid=1), _FakeVizardProcess(pid=2)]
    monkeypatch.setattr(
        main_window, "launch_vizard",
        lambda path, direct_comm_address=None: launch_calls.append(direct_comm_address) or processes[len(launch_calls) - 1]
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(RunWorker, "start", lambda self: None)

    window.on_run()  # first run: nothing to terminate yet, launches process 1
    first_process = window._vizard_process
    assert first_process is processes[0]
    assert first_process.terminate_calls == 0

    window.on_run()  # second run: must terminate process 1 and launch a fresh one

    assert first_process.terminate_calls == 1
    assert window._vizard_process is processes[1]
    assert window._vizard_process is not first_process
    assert len(launch_calls) == 2


def test_run_never_touches_vizard_without_a_live_stream_request(window, monkeypatch):
    """Vizard Configuration defaults to None (no request at all) --
    on_run() must not try to launch/confirm Vizard for an ordinary run.
    """
    from spacemissionstudio.gui.main_window import MainWindow
    from spacemissionstudio.gui.run_worker import RunWorker

    _add_valid_spacecraft(window)
    assert window._vizard_request is None
    calls = []
    monkeypatch.setattr(MainWindow, "on_launch_vizard", lambda self: calls.append(1) or True)
    monkeypatch.setattr(RunWorker, "start", lambda self: None)

    window.on_run()

    assert calls == []


def test_close_with_no_unsaved_changes_does_not_prompt(window, monkeypatch):
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QMessageBox

    question_calls = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: question_calls.append(1)))

    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()


# -- Abort Simulation (direct user feedback: "there should also be the
# option to abort a running simulation, if needed, without breaking the
# tool") -- see gui.run_worker.RunWorker's own module docstring for the
# cooperative-cancellation design these tests exercise the MainWindow
# wiring for.

def test_abort_action_disabled_until_a_run_starts(window):
    assert not window.abort_action.isEnabled()


def test_on_run_enables_abort_action(window, monkeypatch):
    from spacemissionstudio.gui.run_worker import RunWorker

    _add_valid_spacecraft(window)
    monkeypatch.setattr(RunWorker, "start", lambda self: None)  # don't actually spin up the thread

    window.on_run()

    assert window.abort_action.isEnabled()


def test_on_run_monte_carlo_never_enables_abort_action(window, monkeypatch):
    """MonteCarloWorker has no request_cancel() -- see abort_action's own
    construction comment in main_window.py -- so a Monte Carlo run must
    never enable it.
    """
    from PySide6.QtWidgets import QFileDialog
    from spacemissionstudio.gui.run_worker import MonteCarloWorker
    from spacemissionstudio.schema.scenario import MonteCarloConfig

    _add_valid_spacecraft(window)
    window.scenario_editor.monte_carlo_group.set_spacecraft_names(["sat-1"])
    window.scenario_editor.monte_carlo_group.from_dataclass(MonteCarloConfig(enabled=True))
    window.scenario_editor.changed.emit()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: "/tmp/mc"))
    monkeypatch.setattr(MonteCarloWorker, "start", lambda self: None)

    window.on_run_monte_carlo()

    assert not window.abort_action.isEnabled()


def test_run_finished_disables_abort_action(window):
    from spacemissionstudio.engine.results import ResultSet

    window._start_busy("Running test...")
    window.abort_action.setEnabled(True)
    window._on_run_finished(ResultSet(scenario_name="test", series={}))
    assert not window.abort_action.isEnabled()


def test_run_failed_disables_abort_action(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    window._start_busy("Running test...")
    window.abort_action.setEnabled(True)
    window._on_run_failed("boom")
    assert not window.abort_action.isEnabled()


def test_on_abort_run_calls_request_cancel_on_the_running_worker(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from spacemissionstudio.gui.run_worker import RunWorker

    # isRunning() is patched to always return True below (to simulate an
    # in-flight worker without a real thread) -- if that patch is still
    # in effect when qtbot's teardown closes this window, closeEvent()
    # would hit its own real, unmocked "run in progress" QMessageBox and
    # block forever in this offscreen test session waiting for a click
    # that never comes. Mocked here too, same as
    # test_close_while_run_in_progress_is_blocked, so teardown can't hang
    # on it regardless of fixture teardown ordering.
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    _add_valid_spacecraft(window)
    monkeypatch.setattr(RunWorker, "start", lambda self: None)
    window.on_run()
    assert window.abort_action.isEnabled()

    cancel_calls = []
    monkeypatch.setattr(RunWorker, "isRunning", lambda self: True)
    monkeypatch.setattr(RunWorker, "request_cancel", lambda self: cancel_calls.append(1))

    window.on_abort_run()

    assert cancel_calls == [1]
    assert not window.abort_action.isEnabled()


def test_on_abort_run_is_a_no_op_without_a_running_worker(window):
    # No run ever started -- window._run_worker is still None -- must not
    # raise.
    window.on_abort_run()
    assert not window.abort_action.isEnabled()


def test_run_cancelled_updates_results_widget_and_status(window):
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    window._start_busy("Running test...")
    window.abort_action.setEnabled(True)
    window._last_run_epoch_utc = "2032-01-01T00:00:00"
    partial = ResultSet(scenario_name="test")
    partial.add(TimeSeries("sat-1.position_N", [0.0, 1.0], ("x", "y", "z"),
                            [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]], units="m"))

    window._on_run_cancelled(partial)

    assert not window._busy_timer.isActive()
    assert not window.abort_action.isEnabled()
    assert window.run_action.isEnabled()
    assert window.results_widget.series_combo.count() == 1
    assert window.results_widget._epoch_utc == "2032-01-01T00:00:00"
    assert window.right_tabs.currentWidget() is window.results_widget
    assert window.statusBar().currentMessage() == "Run cancelled by user."


def test_run_cancelled_with_command_summary_shows_mission_output_tab(window):
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry, ResultSet

    summary = CommandSummary(reports=[ReportEntry(label="x", t_s=1.0, values={})], commands_executed=1)
    window._on_run_cancelled(ResultSet(scenario_name="test", series={}), summary)

    assert window.right_tabs.currentWidget() is window.mission_output_widget
    assert "1 command run" in window.mission_output_widget.summary_label.text()


def test_end_to_end_cancel_signal_updates_window_without_crashing(window, qtbot, monkeypatch):
    """Drives the real signal/slot connection (RunWorker.cancelled ->
    MainWindow._on_run_cancelled) through a real background QThread,
    matching test_close_while_run_in_progress_is_blocked's approach for
    the same reason: this is the one thing a pure method-call test like
    the ones above can't prove -- that the Signal(object, object) really
    is connected end to end.
    """
    from spacemissionstudio.engine.results import ResultSet
    from spacemissionstudio.gui.run_worker import RunWorker

    _add_valid_spacecraft(window)
    partial = ResultSet(scenario_name="test", series={})

    def fake_run(self):
        self.cancelled.emit(partial, None)

    monkeypatch.setattr(RunWorker, "run", fake_run)

    window.on_run()
    qtbot.waitUntil(lambda: window._run_worker is not None, timeout=5000)
    qtbot.waitUntil(lambda: not window._run_worker.isRunning(), timeout=5000)
    # cancelled is a queued (cross-thread) connection -- the QThread
    # reporting not-running any more doesn't guarantee the GUI thread has
    # actually processed the queued slot invocation yet, so wait on the
    # slot's own observable effect rather than the thread state.
    qtbot.waitUntil(lambda: not window.abort_action.isEnabled(), timeout=5000)

    assert window.statusBar().currentMessage() == "Run cancelled by user."


def test_about_dialog_shows_version_and_basilisk_status(window, monkeypatch):
    """Regression guard for a real gap found while auditing the rest of
    the app: spacemissionstudio.__version__ already existed (a packaged
    desktop app, shipping .deb/Windows installers), but nothing in the
    GUI surfaced it anywhere -- no Help menu, no About dialog, no
    version visible at all.
    """
    from PySide6.QtWidgets import QMessageBox

    import spacemissionstudio

    calls = []
    monkeypatch.setattr(QMessageBox, "about", staticmethod(lambda *a, **k: calls.append(a)))

    window.on_about()

    assert len(calls) == 1
    shown_text = calls[0][2]
    assert spacemissionstudio.__version__ in shown_text
    assert "Basilisk" in shown_text


# -- autosave / crash recovery (design-philosophy roadmap item M4) ----------

def test_autosave_tick_does_nothing_when_not_dirty(window):
    from spacemissionstudio.gui import autosave

    assert not window._dirty
    window._on_autosave_tick()
    assert autosave.read_recovery_file() is None


def test_autosave_tick_writes_recovery_file_while_dirty(window):
    from spacemissionstudio.gui import autosave

    _add_valid_spacecraft(window)
    assert window._dirty

    window._on_autosave_tick()

    info = autosave.read_recovery_file()
    assert info is not None
    assert info.scenario.spacecraft[0].name == "sat-1"
    assert info.original_path is None  # never saved yet in this test


def test_autosave_tick_skips_silently_when_scenario_currently_invalid(window):
    """Mid-edit, the in-memory scenario can be transiently invalid (e.g.
    a spacecraft with an empty name) -- the autosave tick must skip
    that tick quietly rather than popping an error dialog on a timer
    the user never directly triggered.
    """
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig
    from spacemissionstudio.gui import autosave

    window.scenario_editor.spacecraft_list.from_list([
        SpacecraftConfig(name="", orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0],
                                                 velocity_km_s=[0, 7.5, 0]))
    ])
    window.scenario_editor.changed.emit()
    assert window._dirty

    window._on_autosave_tick()  # must not raise

    assert autosave.read_recovery_file() is None


def test_saving_clears_the_recovery_file(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from spacemissionstudio.gui import autosave

    _add_valid_spacecraft(window)
    window._on_autosave_tick()
    assert autosave.read_recovery_file() is not None

    save_path = tmp_path / "scenario.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(save_path), "")))
    window.on_save_as()

    assert autosave.read_recovery_file() is None


def test_discarding_unsaved_changes_clears_the_recovery_file(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.gui import autosave

    _add_valid_spacecraft(window)
    window._on_autosave_tick()
    assert autosave.read_recovery_file() is not None

    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard))
    window.on_new()

    assert autosave.read_recovery_file() is None


def test_check_autosave_recovery_with_no_recovery_file_does_nothing(window):
    window._check_autosave_recovery()  # must not raise, nothing to restore
    assert window._current_path is None
    assert not window._dirty


def test_check_autosave_recovery_user_accepts_restores_and_marks_dirty(window, monkeypatch):
    from pathlib import Path

    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.gui import autosave
    from spacemissionstudio.schema.scenario import OrbitIC, Scenario, SpacecraftConfig

    scenario = Scenario(name="recovered", epoch_utc="2030-01-01T00:00:00Z")
    scenario.spacecraft = [SpacecraftConfig(
        name="recovered-sat", orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0])
    )]
    original_path = Path("/does/not/matter/mission.json")
    autosave.write_recovery_file(scenario, original_path)

    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.Open))

    window._check_autosave_recovery()

    assert window.scenario_editor.spacecraft_list.to_list()[0].name == "recovered-sat"
    assert window._current_path == original_path
    assert window._dirty  # recovered content is still unsaved -- NOT the same as a clean open
    assert window.windowTitle().endswith("*")


def test_check_autosave_recovery_user_declines_clears_file_and_leaves_editor_untouched(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from spacemissionstudio.gui import autosave
    from spacemissionstudio.schema.scenario import OrbitIC, Scenario, SpacecraftConfig

    scenario = Scenario(name="recovered", epoch_utc="2030-01-01T00:00:00Z")
    scenario.spacecraft = [SpacecraftConfig(
        name="recovered-sat", orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0])
    )]
    autosave.write_recovery_file(scenario, None)

    monkeypatch.setattr(QMessageBox, "question",
                         staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard))

    window._check_autosave_recovery()

    assert window.scenario_editor.spacecraft_list.to_list() == []
    assert not window._dirty
    assert autosave.read_recovery_file() is None


def test_join_finished_worker_waits_out_a_thread_that_already_signalled(qtbot):
    """Regression test: a worker emits its terminal signal from INSIDE
    run(), so Run can be re-enabled while that thread is still returning;
    on_run()/on_run_monte_carlo() replacing the last reference to it then
    made Qt abort the whole app ("QThread: Destroyed while thread is still
    running"). _join_finished_worker() must leave it fully stopped first.
    """
    import threading

    from PySide6.QtCore import QThread, Signal

    from spacemissionstudio.gui.main_window import _join_finished_worker

    release = threading.Event()

    class _SignalsThenLingers(QThread):
        done = Signal()

        def run(self):
            self.done.emit()
            release.wait(5)  # still "returning" after its terminal signal  # [s]

    worker = _SignalsThenLingers()
    with qtbot.waitSignal(worker.done, timeout=5000):
        worker.start()
    assert worker.isRunning()

    threading.Timer(0.05, release.set).start()  # [s]
    _join_finished_worker(worker)
    assert not worker.isRunning()
    _join_finished_worker(None)  # no previous worker: a no-op


def test_explain_tab_title_counts_pre_run_warnings(window, qapp):
    """Pre-run checks (engine.scenario_checks) only help if they're seen:
    the Explain tab's own title says when there's something to check."""
    from pathlib import Path

    templates = Path(__file__).resolve().parents[2] / "spacemissionstudio" / "scenarios" / "templates"
    tab_index = window.right_tabs.indexOf(window.scenario_explainer_widget)
    from spacemissionstudio.schema import load_scenario

    assert window.open_path(next(templates.glob("19_*.json")))
    assert window.right_tabs.tabText(tab_index) == "Explain"
    late = load_scenario(next(templates.glob("19_*.json")))
    late.epoch_utc = "2030-01-01T00:00:00"  # the old epoch: no Berlin pass in the run
    window.scenario_editor.from_scenario(late)
    window.scenario_editor.changed.emit()
    assert window.right_tabs.tabText(tab_index) == "Explain (1 to check)"


def test_a_run_hands_the_scenarios_featured_series_to_the_results_tab(window, monkeypatch):
    """The Results tab's one-click suggestions come from the scenario
    being run -- template 19's description names five series."""
    from pathlib import Path

    from spacemissionstudio.engine.series_names import featured_series
    from spacemissionstudio.gui.run_worker import RunWorker
    from spacemissionstudio.schema import load_scenario

    path = next((Path(__file__).resolve().parents[2] / "spacemissionstudio" / "scenarios" / "templates")
                .glob("19_*.json"))
    assert window.open_path(path)
    monkeypatch.setattr(RunWorker, "start", lambda self: None)  # don't actually spin up the thread
    window.on_run()
    assert window.results_widget._featured == featured_series(load_scenario(path))
    assert len(window.results_widget._featured) == 5


def test_results_offer_the_last_runs_vizard_file_and_open_it(window, monkeypatch, tmp_path):
    """After a run that wrote a playback file, Results shows "Open in
    Vizard", which starts Vizard with -loadFile on that file; a new run
    hides it again."""
    from pathlib import Path

    from spacemissionstudio.gui import main_window

    playback = tmp_path / "run.bin"
    playback.write_bytes(b"\x00")
    window._last_run_vizard_file = str(playback)
    window._offer_vizard_playback()
    assert window.results_widget.vizard_button.isVisibleTo(window.results_widget)
    calls = []
    monkeypatch.setattr(main_window, "find_vizard_executable", lambda: Path("/fake/Vizard"))
    monkeypatch.setattr(main_window, "launch_vizard",
                        lambda path, load_file=None: calls.append((path, load_file)) or _FakeVizardProcess())
    window.results_widget.vizard_button.click()
    assert calls == [(Path("/fake/Vizard"), playback)]
    window._clear_run_views()
    assert not window.results_widget.vizard_button.isVisibleTo(window.results_widget)


def test_no_vizard_button_when_the_run_wrote_no_file(window, tmp_path):
    window._last_run_vizard_file = str(tmp_path / "missing.bin")
    window._offer_vizard_playback()
    assert not window.results_widget.vizard_button.isVisibleTo(window.results_widget)


def test_finished_runs_are_kept_for_comparison(window):
    """Each finished or cancelled run joins the session's history, and the
    Results tab offers the earlier ones (UX/UI guidelines, run comparison)."""
    import numpy as np

    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    window._last_run_scenario = window.scenario_editor.draft_scenario()
    window._last_run_epoch_utc = window._last_run_scenario.epoch_utc
    for _ in range(2):
        result = ResultSet("r")
        result.add(TimeSeries("sat-1.position_N", np.arange(3.0), ("x", "y", "z"), np.zeros((3, 3)), units="m"))
        window._keep_run(result, cancelled=False)
    assert [r.number for r in window.run_history.runs] == [1, 2]
    assert window.results_widget.compare_combo.findData(1) >= 0
    window._clear_run_views()
    assert not window.results_widget.compare_combo.isVisibleTo(window.results_widget)
