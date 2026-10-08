"""Tests for gui.vizard_launcher -- path lookup/persistence, process
launch, and fetching a pre-built Vizard binary, all with real
filesystem/QSettings I/O redirected into tmp_path (never touching the
real developer machine's actual Vizard install or settings store) and
the network itself always mocked (urllib.request.urlopen -- fetch_vizard
is only ever reached via an explicit user click, never automatically;
see that function's own docstring).
"""

import io
import os
import zipfile

import pytest
from PySide6.QtCore import QSettings

pytestmark = pytest.mark.requires_gui


def _settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_find_returns_none_with_no_remembered_path_and_nothing_on_disk(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher, "_candidate_roots", lambda: [tmp_path / "does_not_exist"])
    assert vizard_launcher.find_vizard_executable(settings=_settings(tmp_path)) is None


def test_remember_then_find_returns_the_remembered_path(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    fake_exe = tmp_path / "Vizard.x86_64"
    fake_exe.write_bytes(b"")
    settings = _settings(tmp_path)

    vizard_launcher.remember_vizard_executable(fake_exe, settings=settings)
    assert vizard_launcher.find_vizard_executable(settings=settings) == fake_exe


def test_remembered_path_that_no_longer_exists_falls_back_to_search(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    settings = _settings(tmp_path)
    vizard_launcher.remember_vizard_executable(tmp_path / "gone" / "Vizard.x86_64", settings=settings)

    search_root = tmp_path / "search_root"
    search_root.mkdir()
    found_exe = search_root / vizard_launcher._EXECUTABLE_NAME
    found_exe.write_bytes(b"")
    monkeypatch.setattr(vizard_launcher, "_candidate_roots", lambda: [search_root])

    assert vizard_launcher.find_vizard_executable(settings=settings) == found_exe


def test_search_finds_executable_directly_in_a_candidate_root(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    root = tmp_path / "Desktop"
    root.mkdir()
    exe = root / vizard_launcher._EXECUTABLE_NAME
    exe.write_bytes(b"")
    monkeypatch.setattr(vizard_launcher, "_candidate_roots", lambda: [root])

    assert vizard_launcher.find_vizard_executable(settings=_settings(tmp_path)) == exe


def test_search_finds_executable_one_level_down_in_a_candidate_root(tmp_path, monkeypatch):
    """Covers "unzipped into its own subfolder" (e.g. Desktop/Vizard_Windows64/Vizard.exe)."""
    from spacemissionstudio.gui import vizard_launcher

    root = tmp_path / "Downloads"
    nested = root / "Vizard_Windows64"
    nested.mkdir(parents=True)
    exe = nested / vizard_launcher._EXECUTABLE_NAME
    exe.write_bytes(b"")
    monkeypatch.setattr(vizard_launcher, "_candidate_roots", lambda: [root])

    assert vizard_launcher.find_vizard_executable(settings=_settings(tmp_path)) == exe


def test_search_skips_a_nonexistent_root_without_raising(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    real_root = tmp_path / "real"
    real_root.mkdir()
    exe = real_root / vizard_launcher._EXECUTABLE_NAME
    exe.write_bytes(b"")
    # A missing root ahead of a real one must be skipped, not raise.
    monkeypatch.setattr(vizard_launcher, "_candidate_roots", lambda: [tmp_path / "missing", real_root])

    assert vizard_launcher.find_vizard_executable(settings=_settings(tmp_path)) == exe


def test_launch_starts_the_given_executable_directly_on_non_macos(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    exe = tmp_path / "Vizard.x86_64"
    exe.write_bytes(b"")

    captured = {}

    class _FakeProcess:
        pid = 4242

        def poll(self):
            return None

    def fake_popen(args):
        captured["args"] = args
        return _FakeProcess()

    monkeypatch.setattr(vizard_launcher.subprocess, "Popen", fake_popen)
    result = vizard_launcher.launch_vizard(exe)

    assert captured["args"] == [str(exe)]
    assert result.pid == 4242


def test_launch_appends_direct_comm_flag_when_given(tmp_path, monkeypatch):
    """See DEFAULT_LIVE_STREAM_ADDRESS's own comment: -directComm is what
    makes Vizard connect to a live-stream run automatically instead of
    sitting on its own manual launcher screen.
    """
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    exe = tmp_path / "Vizard.x86_64"
    exe.write_bytes(b"")

    captured = {}
    monkeypatch.setattr(vizard_launcher.subprocess, "Popen", lambda args: captured.setdefault("args", args))

    vizard_launcher.launch_vizard(exe, direct_comm_address="tcp://localhost:5556")

    assert captured["args"] == [str(exe), "-directComm", "tcp://localhost:5556"]


def test_launch_omits_direct_comm_flag_when_not_given(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    exe = tmp_path / "Vizard.x86_64"
    exe.write_bytes(b"")

    captured = {}
    monkeypatch.setattr(vizard_launcher.subprocess, "Popen", lambda args: captured.setdefault("args", args))

    vizard_launcher.launch_vizard(exe)

    assert captured["args"] == [str(exe)]


def test_launch_resolves_macos_app_bundle_to_its_inner_binary(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "darwin")
    bundle = tmp_path / "Vizard.app"
    macos_dir = bundle / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True)
    inner_binary = macos_dir / "Vizard"
    inner_binary.write_bytes(b"")

    captured = {}
    monkeypatch.setattr(vizard_launcher.subprocess, "Popen", lambda args: captured.setdefault("args", args))

    vizard_launcher.launch_vizard(bundle)
    assert captured["args"] == [str(inner_binary)]


def test_launch_raises_a_clear_error_for_an_empty_macos_bundle(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.sys, "platform", "darwin")
    bundle = tmp_path / "Vizard.app"
    (bundle / "Contents" / "MacOS").mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="does not look like a valid macOS app bundle"):
        vizard_launcher.launch_vizard(bundle)


# -- fetch_vizard() -- downloading and extracting a pre-built Vizard -------

def test_download_url_for_platform_covers_all_three(monkeypatch):
    """Each platform gets its own Vizard download. ``vizard_launcher.sys``
    is ``sys`` itself, so the platform is set through monkeypatch, which
    restores the real value (an earlier version of this test left
    ``sys.platform`` at "linux" for every later test in the process)."""
    from spacemissionstudio.gui import vizard_launcher

    for platform_value, expected_substring in (("darwin", "macOS"), ("win32", "Windows"), ("linux", "Linux")):
        monkeypatch.setattr(vizard_launcher.sys, "platform", platform_value)
        assert expected_substring in vizard_launcher._download_url_for_platform()


def _as_linux_build(monkeypatch, vizard_launcher):
    """Make ``fetch_vizard()`` take the Linux path on any OS: the platform
    it downloads for, and the executable name it then searches for, which
    the module fixes at import from the real platform."""
    monkeypatch.setattr(vizard_launcher.sys, "platform", "linux")
    monkeypatch.setattr(vizard_launcher, "_EXECUTABLE_NAME", "Vizard.x86_64")


class _FakeUrlResponse:
    """Minimal stand-in for ``urllib.request.urlopen``'s return value --
    a context manager with a chunked ``.read(n)``, matching how
    :func:`fetch_vizard` actually reads it (cooperative-cancellation
    checks happen BETWEEN chunks).
    """

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            chunk = self._data[self._pos:]
            self._pos = len(self._data)
            return chunk
        chunk = self._data[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _make_vizard_zip(zip_path, *, executable_name, wrapper_folder=None):
    """Writes a minimal real zip file containing one entry named
    ``executable_name`` (optionally nested one level under
    ``wrapper_folder``, matching AVS's own real .zip layout) -- a real
    zip, not a mock, so the real extraction/zip-slip-guard code under
    test is genuinely exercised.
    """
    rel = f"{wrapper_folder}/{executable_name}" if wrapper_folder else executable_name
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(rel, b"fake binary contents")


def test_fetch_vizard_downloads_extracts_and_finds_the_executable(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    _as_linux_build(monkeypatch, vizard_launcher)
    zip_buf = io.BytesIO()
    zip_name = tmp_path / "staging.zip"
    _make_vizard_zip(zip_name, executable_name="Vizard.x86_64")
    zip_buf.write(zip_name.read_bytes())
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen",
                         lambda *a, **k: _FakeUrlResponse(zip_buf.getvalue()))

    executable = vizard_launcher.fetch_vizard(dest_dir=tmp_path)

    assert executable.name == "Vizard.x86_64"
    assert executable.exists()


def test_fetch_vizard_sends_a_browser_like_user_agent(tmp_path, monkeypatch):
    """Regression guard: urllib's own default User-Agent
    ("Python-urllib/<version>") got "HTTPError: 403 Forbidden" from a
    real host on a real user's machine -- asserts the actual outgoing
    urllib.request.Request carries a real User-Agent header, not just
    that some response gets consumed.
    """
    from spacemissionstudio.gui import vizard_launcher

    _as_linux_build(monkeypatch, vizard_launcher)
    zip_name = tmp_path / "staging.zip"
    _make_vizard_zip(zip_name, executable_name="Vizard.x86_64")
    captured = {}

    def _fake_urlopen(request, timeout=None):
        captured["request"] = request
        return _FakeUrlResponse(zip_name.read_bytes())

    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", _fake_urlopen)

    vizard_launcher.fetch_vizard(dest_dir=tmp_path)

    sent_request = captured["request"]
    assert isinstance(sent_request, vizard_launcher.urllib.request.Request)
    user_agent = sent_request.get_header("User-agent")  # urllib title-cases header names internally
    assert user_agent
    assert "python-urllib" not in user_agent.lower()


def test_fetch_vizard_sets_the_executable_bit_on_non_windows(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    _as_linux_build(monkeypatch, vizard_launcher)
    zip_name = tmp_path / "staging.zip"
    _make_vizard_zip(zip_name, executable_name="Vizard.x86_64")
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen",
                         lambda *a, **k: _FakeUrlResponse(zip_name.read_bytes()))

    requested = []
    real_chmod = vizard_launcher.Path.chmod

    def spy_chmod(path, mode, *args, **kwargs):
        requested.append(mode)
        return real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(vizard_launcher.Path, "chmod", spy_chmod)
    executable = vizard_launcher.fetch_vizard(dest_dir=tmp_path)

    assert requested and requested[-1] & vizard_launcher.stat.S_IXUSR
    if os.name == "posix":  # Windows has no executable bit to read back
        assert executable.stat().st_mode & vizard_launcher.stat.S_IXUSR


def test_fetch_vizard_reports_network_failure(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    def _raise(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", _raise)

    with pytest.raises(vizard_launcher.VizardFetchError, match="could not download"):
        vizard_launcher.fetch_vizard(dest_dir=tmp_path)


def test_fetch_vizard_reports_a_corrupt_zip(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen",
                         lambda *a, **k: _FakeUrlResponse(b"not a real zip file"))

    with pytest.raises(vizard_launcher.VizardFetchError, match="not a valid zip file"):
        vizard_launcher.fetch_vizard(dest_dir=tmp_path)


def test_fetch_vizard_reports_a_zip_with_no_recognizable_executable(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    _as_linux_build(monkeypatch, vizard_launcher)
    zip_name = tmp_path / "staging.zip"
    with zipfile.ZipFile(zip_name, "w") as zf:
        zf.writestr("readme.txt", b"no executable in here")
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen",
                         lambda *a, **k: _FakeUrlResponse(zip_name.read_bytes()))

    with pytest.raises(vizard_launcher.VizardFetchError, match="could not find"):
        vizard_launcher.fetch_vizard(dest_dir=tmp_path)


def test_fetch_vizard_honors_cooperative_cancellation(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen",
                         lambda *a, **k: _FakeUrlResponse(b"x" * 10))

    with pytest.raises(vizard_launcher.VizardFetchError, match="cancelled"):
        vizard_launcher.fetch_vizard(dest_dir=tmp_path, should_cancel=lambda: True)


def test_fetch_vizard_rejects_a_response_over_the_size_cap(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    monkeypatch.setattr(vizard_launcher, "_MAX_DOWNLOAD_BYTES", 10)
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen",
                         lambda *a, **k: _FakeUrlResponse(b"x" * 100))

    with pytest.raises(vizard_launcher.VizardFetchError, match="exceeded"):
        vizard_launcher.fetch_vizard(dest_dir=tmp_path)


def test_fetch_vizard_reports_progress_status(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    _as_linux_build(monkeypatch, vizard_launcher)
    zip_name = tmp_path / "staging.zip"
    _make_vizard_zip(zip_name, executable_name="Vizard.x86_64")
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen",
                         lambda *a, **k: _FakeUrlResponse(zip_name.read_bytes()))

    statuses = []
    vizard_launcher.fetch_vizard(dest_dir=tmp_path, on_status=statuses.append)

    assert any("Downloading" in s for s in statuses)
    assert any("Extracting" in s for s in statuses)


def test_fetch_vizard_records_the_download_with_its_sha256(tmp_path, monkeypatch):
    """No checksum is published for Vizard, so the download is recorded
    (source, size, SHA-256) and the hash is shown to the user
    (security analysis S-05)."""
    import hashlib
    import json

    from spacemissionstudio.gui import vizard_launcher

    _as_linux_build(monkeypatch, vizard_launcher)
    zip_name = tmp_path / "staging.zip"
    _make_vizard_zip(zip_name, executable_name="Vizard.x86_64")
    data = zip_name.read_bytes()
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen", lambda *a, **k: _FakeUrlResponse(data))

    statuses = []
    vizard_launcher.fetch_vizard(dest_dir=tmp_path, on_status=statuses.append)

    record = json.loads((tmp_path / "download.json").read_text())
    assert record["sha256"] == hashlib.sha256(data).hexdigest()
    assert record["size_bytes"] == len(data) and record["url"].startswith("https://")
    assert any(record["sha256"] in s for s in statuses)


def test_fetch_vizard_finds_the_executable_inside_a_same_named_wrapper_folder(tmp_path, monkeypatch):
    """Matches AVS's own real .zip layout -- Vizard_<platform>.zip wraps
    its contents in a same-named top-level folder.
    """
    from spacemissionstudio.gui import vizard_launcher

    _as_linux_build(monkeypatch, vizard_launcher)
    zip_name = tmp_path / "staging.zip"
    _make_vizard_zip(zip_name, executable_name="Vizard.x86_64", wrapper_folder="Vizard_Linux")
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen",
                         lambda *a, **k: _FakeUrlResponse(zip_name.read_bytes()))

    executable = vizard_launcher.fetch_vizard(dest_dir=tmp_path)

    assert executable.name == "Vizard.x86_64"
    assert executable.parent.name == "Vizard_Linux"


def test_fetch_vizard_clears_stale_files_from_an_earlier_extraction(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    _as_linux_build(monkeypatch, vizard_launcher)

    old_zip = tmp_path / "old.zip"
    _make_vizard_zip(old_zip, executable_name="Vizard.x86_64", wrapper_folder="Vizard_Linux_Old")
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen",
                         lambda *a, **k: _FakeUrlResponse(old_zip.read_bytes()))
    vizard_launcher.fetch_vizard(dest_dir=tmp_path)
    stale_marker = tmp_path / "extracted" / "Vizard_Linux_Old"
    assert stale_marker.exists()

    new_zip = tmp_path / "new.zip"
    _make_vizard_zip(new_zip, executable_name="Vizard.x86_64", wrapper_folder="Vizard_Linux_New")
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen",
                         lambda *a, **k: _FakeUrlResponse(new_zip.read_bytes()))
    executable = vizard_launcher.fetch_vizard(dest_dir=tmp_path)

    assert not stale_marker.exists()
    assert executable.parent.name == "Vizard_Linux_New"


def test_fetch_vizard_rejects_a_zip_slip_entry(tmp_path, monkeypatch):
    from spacemissionstudio.gui import vizard_launcher

    _as_linux_build(monkeypatch, vizard_launcher)
    zip_name = tmp_path / "staging.zip"
    with zipfile.ZipFile(zip_name, "w") as zf:
        zf.writestr("../escaped.txt", b"zip-slip payload")
    monkeypatch.setattr(vizard_launcher.urllib.request, "urlopen",
                         lambda *a, **k: _FakeUrlResponse(zip_name.read_bytes()))

    with pytest.raises(vizard_launcher.VizardFetchError, match="unsafe entry"):
        vizard_launcher.fetch_vizard(dest_dir=tmp_path)


# -- VizardFetchWorker -- the QThread wrapper -------------------------------

def test_vizard_fetch_worker_emits_finished_ok_on_success(tmp_path, monkeypatch, qtbot):
    from spacemissionstudio.gui import vizard_launcher

    fake_path = tmp_path / "Vizard.x86_64"
    monkeypatch.setattr(vizard_launcher, "fetch_vizard", lambda *a, **k: fake_path)

    worker = vizard_launcher.VizardFetchWorker(dest_dir=tmp_path)
    with qtbot.waitSignal(worker.finished_ok, timeout=5000) as blocker:
        worker.start()
    assert worker.wait(5000)  # join it: GC of a still-running QThread aborts the process

    assert blocker.args == [str(fake_path)]


def test_vizard_fetch_worker_emits_failed_on_error(tmp_path, monkeypatch, qtbot):
    from spacemissionstudio.gui import vizard_launcher

    def _raise(*args, **kwargs):
        raise vizard_launcher.VizardFetchError("could not download: boom")

    monkeypatch.setattr(vizard_launcher, "fetch_vizard", _raise)

    worker = vizard_launcher.VizardFetchWorker(dest_dir=tmp_path)
    with qtbot.waitSignal(worker.failed, timeout=5000) as blocker:
        worker.start()
    assert worker.wait(5000)  # join it: GC of a still-running QThread aborts the process

    assert "boom" in blocker.args[0]


def test_vizard_fetch_worker_request_cancel_is_seen_by_should_cancel(tmp_path, monkeypatch, qtbot):
    from spacemissionstudio.gui import vizard_launcher

    seen_should_cancel = {}

    def _fake_fetch(dest_dir, should_cancel=None, on_status=None):
        seen_should_cancel["callable"] = should_cancel
        return tmp_path / "Vizard.x86_64"

    monkeypatch.setattr(vizard_launcher, "fetch_vizard", _fake_fetch)

    worker = vizard_launcher.VizardFetchWorker(dest_dir=tmp_path)
    worker.request_cancel()
    with qtbot.waitSignal(worker.finished_ok, timeout=5000):
        worker.start()
    assert worker.wait(5000)  # join it: GC of a still-running QThread aborts the process

    assert seen_should_cancel["callable"]() is True  # the Event was already set before start()

