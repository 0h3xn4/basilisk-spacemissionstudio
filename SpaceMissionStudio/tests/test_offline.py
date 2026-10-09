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
"""The tool works with no network at all (UX/UI guidelines, "offline and
closed operation": no background network use; it must work with
networking disabled, and an automated test verifies it).

Every way a Python process opens a connection or resolves a name fails
here, and any attempt is recorded, so a test fails on an attempt even if
the code would have swallowed the error. CI also runs this file in a
network namespace with no interfaces (``unshare -rn``), which stops what
the in-process block cannot see.
"""

import json
import os
import socket
import subprocess
import sys

import pytest

from spacemissionstudio import cli


@pytest.fixture
def no_network(monkeypatch):
    """Make every connection and name lookup fail, and record each attempt
    to reach another computer. Attempts to this computer (the closed local
    port Basilisk's import-time request is sent to, F-16) are blocked too
    but not counted: nothing leaves the machine."""
    attempts = []

    def refuse(what):
        def blocked(*args, **kwargs):
            target = args[1] if what in ("connect", "connect_ex") else args[0]
            host = str(target[0] if isinstance(target, tuple) else target)
            if host not in ("127.0.0.1", "::1", "localhost"):
                attempts.append((what, host))
            raise OSError(f"network disabled in this test ({what})")
        return blocked

    monkeypatch.setattr(socket.socket, "connect", refuse("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", refuse("connect_ex"))
    monkeypatch.setattr(socket, "create_connection", refuse("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", refuse("getaddrinfo"))
    monkeypatch.setattr(socket, "gethostbyname", refuse("gethostbyname"))
    return attempts


def test_validate_and_export_a_template_offline(no_network, tmp_path):
    """Validating, exporting to CCSDS and checking data needs no network."""
    template = sorted(_templates().glob("18_*.json"))[0]
    assert cli.main(["validate", str(template)]) == 0
    assert cli.main(["ccsds-export", str(template), "--out", str(tmp_path / "odm")]) == 0
    assert cli.main(["kernels-status"]) in (0, 1)  # 1 = a kernel is missing, which is reported, not fetched
    assert no_network == []


@pytest.mark.requires_basilisk
def test_a_run_with_real_space_weather_and_its_exports_need_no_network(no_network, tmp_path):
    """A one-day drag run on the bundled space weather, its CSV and OEM
    exports and its provenance: no connection, no name lookup."""
    template = sorted(_templates().glob("18_*.json"))[0]
    scenario = json.loads(template.read_text(encoding="utf-8"))
    scenario["sim_settings"]["duration_days"] = 0.05  # [day]
    path = tmp_path / "short.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    out = tmp_path / "out"
    assert cli.main(["run", str(path), "--out-dir", str(out), "--oem"]) == 0
    assert (out / "provenance.json").exists()
    assert list(out.glob("*.oem")) or list(out.rglob("*.oem"))
    assert no_network == []


def test_gui_start_up_with_the_download_prompt_declined_needs_no_network(no_network, qtbot, monkeypatch):
    """The main window as a user starts it, with the startup download
    prompt shown and declined: nothing is fetched."""
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui import startup_fetch_dialog
    from spacemissionstudio.gui.main_window import MainWindow

    shown = []
    monkeypatch.setattr(startup_fetch_dialog.StartupFetchDialog, "exec",
                        lambda self: shown.append(True) or QDialog.DialogCode.Rejected)
    window = MainWindow(check_autosave_recovery=False)
    qtbot.addWidget(window)
    qtbot.wait(200)  # [ms] let queued start-up work run
    assert no_network == []
    assert shown in ([], [True])  # shown when data are missing, else not needed


_SPY = """
import json, socket, sys
attempts = []
def spy(name):
    def blocked(*args, **kwargs):
        attempts.append(str(args[1][0] if name == "connect" else args[0]))
        raise OSError("blocked")
    return blocked
socket.getaddrinfo = spy("getaddrinfo")
socket.socket.connect = spy("connect")
socket.create_connection = spy("create_connection")
import spacemissionstudio.engine.service  # imports Basilisk, and with it dataFetcher
from Basilisk.utilities import simIncludeGravBody  # the CLI's direct import
print(json.dumps(attempts))
"""


@pytest.mark.requires_basilisk
def test_importing_basilisk_through_the_tool_contacts_no_other_computer():
    """F-16: Basilisk's data fetcher sends a HEAD request to github.com
    when imported. Through the tool, that request may go only to this
    computer (a closed local port), with the user's own proxy settings
    ignored for it and restored afterwards. Fresh interpreter: the import
    happens once per process."""
    env = dict(os.environ, HTTPS_PROXY="http://proxy.example:8080", NO_PROXY="github.com")
    out = subprocess.run([sys.executable, "-c", _SPY], capture_output=True, text=True, env=env,  # noqa: S603
                         timeout=300, check=True).stdout
    hosts = json.loads(out.strip().splitlines()[-1])
    assert all(host in ("127.0.0.1", "::1", "localhost") for host in hosts), hosts


def test_requests_stay_local_restores_the_proxy_settings(monkeypatch):
    """The proxy override lasts only for the import; the user's settings come back."""
    from spacemissionstudio import _offline

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("no_proxy", "intranet")
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    with _offline.requests_stay_local() as proxy:
        assert proxy.startswith("http://127.0.0.1:")
        assert os.environ["HTTPS_PROXY"] == proxy and "no_proxy" not in os.environ
    assert os.environ["HTTPS_PROXY"] == "http://proxy.example:8080"
    assert os.environ["no_proxy"] == "intranet"
    assert "HTTP_PROXY" not in os.environ


def _templates():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"


@pytest.mark.requires_basilisk
def test_a_run_with_a_support_file_missing_stops_instead_of_downloading(no_network, monkeypatch, tmp_path):
    """F-16: Basilisk's get_path downloads a file missing from its cache;
    a run of the tool only looks in the cache and says how to fetch."""
    from Basilisk.utilities.supportDataTools import dataFetcher

    from spacemissionstudio.engine import kernels
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.schema import load_scenario

    monkeypatch.setattr(dataFetcher, "LOCAL_SUPPORT", None)
    monkeypatch.setattr(dataFetcher.POOCH, "path", tmp_path)  # an empty cache
    scenario = load_scenario(sorted(_templates().glob("18_*.json"))[0])
    scenario.sim_settings.duration_days = 0.01  # [day]
    with pytest.raises(kernels.KernelError, match="Data tab"):
        SimulationService(scenario).run()
    assert no_network == []


@pytest.mark.requires_basilisk
def test_a_support_file_with_a_wrong_checksum_is_refused(monkeypatch, tmp_path):
    """A cached file whose checksum Basilisk's registry knows is checked."""
    import shutil

    from Basilisk.utilities.supportDataTools import dataFetcher

    from spacemissionstudio.engine import kernels

    good = kernels.cached_path(kernels.DataFile.LocalGravData.GGM03S)
    rel = dataFetcher.relpath(kernels.DataFile.LocalGravData.GGM03S)
    copy = tmp_path / rel
    copy.parent.mkdir(parents=True)
    shutil.copyfile(good, copy)
    with copy.open("a", encoding="ascii") as handle:
        handle.write("tampered\n")
    monkeypatch.setattr(dataFetcher, "LOCAL_SUPPORT", None)
    monkeypatch.setattr(dataFetcher.POOCH, "path", tmp_path)
    with pytest.raises(kernels.KernelError, match="checksum"):
        kernels.cached_path(kernels.DataFile.LocalGravData.GGM03S)
