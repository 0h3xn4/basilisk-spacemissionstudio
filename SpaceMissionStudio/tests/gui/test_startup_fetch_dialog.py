"""Tests for gui.startup_fetch_dialog -- the once-per-MainWindow-session
consent prompt for the one piece of this app's offline policy that runs
automatically: real user decision ("a one time fetch during each
startup... the user always should be asked if they want to fetch/
update"). Every test here mocks StartupFetchWorker.run() (same
convention as test_kernel_status_widget.py's own _KernelFetchWorker
mocking) rather than exercising a real network call/Basilisk build --
this module's OWN job (ask first, run selected fetches, summarize) is
what's under test, not engine.kernels/engine.spaceweather themselves
(covered by their own test files).
"""

import pytest

pytestmark = pytest.mark.requires_gui


def test_dialog_defaults_to_both_items_checked(qtbot):
    from spacemissionstudio.gui.startup_fetch_dialog import StartupFetchDialog

    dialog = StartupFetchDialog()
    qtbot.addWidget(dialog)

    assert dialog.selected() == (True, True)


def test_dialog_selected_reflects_unchecked_items(qtbot):
    from spacemissionstudio.gui.startup_fetch_dialog import StartupFetchDialog

    dialog = StartupFetchDialog()
    qtbot.addWidget(dialog)
    dialog.kernels_checkbox.setChecked(False)

    assert dialog.selected() == (False, True)


def test_skip_button_rejects_the_dialog(qtbot):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.startup_fetch_dialog import StartupFetchDialog

    dialog = StartupFetchDialog()
    qtbot.addWidget(dialog)
    dialog.skip_button.click()

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_fetch_now_button_accepts_the_dialog(qtbot):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.startup_fetch_dialog import StartupFetchDialog

    dialog = StartupFetchDialog()
    qtbot.addWidget(dialog)
    dialog.fetch_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted


def _mock_dialog_exec(monkeypatch, *, accept: bool, fetch_kernels: bool = True, fetch_space_weather: bool = True):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui import startup_fetch_dialog as module

    def _exec(self):
        self.kernels_checkbox.setChecked(fetch_kernels)
        self.space_weather_checkbox.setChecked(fetch_space_weather)
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(module.StartupFetchDialog, "exec", _exec)


def test_maybe_run_skips_entirely_without_touching_the_worker(qtbot, monkeypatch):
    from spacemissionstudio.gui import startup_fetch_dialog as module

    _mock_dialog_exec(monkeypatch, accept=False)
    started = []
    monkeypatch.setattr(module.StartupFetchWorker, "start", lambda self: started.append(1))

    module.maybe_run_startup_fetch(None)

    assert started == []


def test_maybe_run_skips_when_both_items_unchecked(qtbot, monkeypatch):
    from spacemissionstudio.gui import startup_fetch_dialog as module

    _mock_dialog_exec(monkeypatch, accept=True, fetch_kernels=False, fetch_space_weather=False)
    started = []
    monkeypatch.setattr(module.StartupFetchWorker, "start", lambda self: started.append(1))

    module.maybe_run_startup_fetch(None)

    assert started == []


def test_maybe_run_fetches_selected_items_and_shows_summary(qtbot, monkeypatch):
    from spacemissionstudio.gui import startup_fetch_dialog as module

    _mock_dialog_exec(monkeypatch, accept=True, fetch_kernels=True, fetch_space_weather=True)

    def _fake_run(self):
        result = {}
        if self.fetch_kernels:
            result["kernels"] = (True, "4/4 support-data file(s) available.")
        if self.fetch_space_weather:
            result["space_weather"] = (True, "/fake/cache/SW-All.csv")
        self.finished_all.emit(result)

    monkeypatch.setattr(module.StartupFetchWorker, "run", _fake_run)
    monkeypatch.setattr(module.StartupFetchWorker, "start", lambda self: self.run())

    shown = []
    monkeypatch.setattr(module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: shown.append(a)))

    module.maybe_run_startup_fetch(None)

    assert shown
    message = shown[0][-1]
    assert "4/4 support-data file(s) available." in message
    assert "/fake/cache/SW-All.csv" in message


def test_maybe_run_reports_a_failed_space_weather_fetch(qtbot, monkeypatch):
    from spacemissionstudio.gui import startup_fetch_dialog as module

    _mock_dialog_exec(monkeypatch, accept=True, fetch_kernels=False, fetch_space_weather=True)

    def _fake_run(self):
        self.finished_all.emit({"space_weather": (False, "could not fetch https://celestrak.org/...: boom")})

    monkeypatch.setattr(module.StartupFetchWorker, "run", _fake_run)
    monkeypatch.setattr(module.StartupFetchWorker, "start", lambda self: self.run())

    shown = []
    monkeypatch.setattr(module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: shown.append(a)))

    module.maybe_run_startup_fetch(None)

    message = shown[0][-1]
    assert "could not fetch" in message
    assert "boom" in message


def test_maybe_run_reports_an_unexpected_worker_error(qtbot, monkeypatch):
    from spacemissionstudio.gui import startup_fetch_dialog as module

    _mock_dialog_exec(monkeypatch, accept=True, fetch_kernels=True, fetch_space_weather=False)

    def _fake_run(self):
        self.finished_all.emit({"error": (False, "something nobody expected")})

    monkeypatch.setattr(module.StartupFetchWorker, "run", _fake_run)
    monkeypatch.setattr(module.StartupFetchWorker, "start", lambda self: self.run())

    shown = []
    monkeypatch.setattr(module.QMessageBox, "information",
                         staticmethod(lambda *a, **k: shown.append(a)))

    module.maybe_run_startup_fetch(None)

    assert shown
    message = shown[0][-1]
    assert "unexpectedly" in message
    assert "something nobody expected" in message


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("Basilisk") is not None,
    reason="this test's premise is specifically that Basilisk is unavailable",
)
def test_worker_fetch_kernels_reports_missing_basilisk():
    """This sandbox genuinely has no Basilisk build -- ``engine.kernels``
    itself raises ``ImportError`` on import (same real path
    ``test_kernel_status_widget.py``'s own
    ``test_refresh_without_basilisk_reports_clear_status`` exercises), so
    no mocking is needed to hit this branch here.
    """
    from spacemissionstudio.gui.startup_fetch_dialog import StartupFetchWorker

    ok, message = StartupFetchWorker._fetch_kernels()

    assert ok is False
    assert "Basilisk is not installed" in message


def test_worker_fetch_space_weather_reports_failure(monkeypatch):
    from spacemissionstudio.gui.startup_fetch_dialog import StartupFetchWorker
    from spacemissionstudio.engine import spaceweather as sw

    def _raise(*args, **kwargs):
        raise sw.SpaceWeatherError("could not fetch: boom")

    monkeypatch.setattr(sw, "fetch", _raise)

    ok, message = StartupFetchWorker._fetch_space_weather()

    assert ok is False
    assert "boom" in message


def test_worker_fetch_space_weather_reports_success(monkeypatch, tmp_path):
    from spacemissionstudio.gui.startup_fetch_dialog import StartupFetchWorker
    from spacemissionstudio.engine import spaceweather as sw

    fake_path = tmp_path / "SW-All.csv"
    monkeypatch.setattr(sw, "fetch", lambda **kwargs: fake_path)

    ok, message = StartupFetchWorker._fetch_space_weather()

    assert ok is True
    assert message == str(fake_path)


def test_worker_run_always_emits_even_if_a_helper_raises_unexpectedly(qtbot, monkeypatch):
    """Regression guard: maybe_run_startup_fetch() waits for finished_all
    inside a blocking QEventLoop behind a progress dialog with NO cancel
    button. If a helper raised something neither _fetch_kernels nor
    _fetch_space_weather already catches, run() used to let it propagate
    uncaught -- finished_all would never fire, and that loop would hang
    forever with no way for the user to dismiss it. run() itself must
    catch anything that slips past those helpers.
    """
    from spacemissionstudio.gui.startup_fetch_dialog import StartupFetchWorker

    def _raise(*args, **kwargs):
        raise RuntimeError("something nobody expected")

    monkeypatch.setattr(StartupFetchWorker, "_fetch_kernels", staticmethod(_raise))

    worker = StartupFetchWorker(fetch_kernels=True, fetch_space_weather=False)
    with qtbot.waitSignal(worker.finished_all, timeout=5000) as blocker:
        worker.start()
    assert worker.wait(5000)  # join it: GC of a still-running QThread aborts the process

    result = blocker.args[0]
    assert "error" in result
    ok, message = result["error"]
    assert ok is False
    assert "something nobody expected" in message
