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
"""The Data tab (UX/UI guidelines: every reference file with its version,
dates and source; downloads only with consent, naming source, files and
size; what changed; import and rollback). Replaces the Kernel Status tab,
whose checks (table layout, tooltips, a second click while busy, failures)
carry over."""

import threading

import pytest

from spacemissionstudio.engine.reference_data import ReferenceFile
from spacemissionstudio.gui import data_panel_widget as dp

_FILES = [
    ReferenceFile("SPICE kernel", "naif0012.tls", "ok", "https://naif.jpl.nasa.gov/x", "/cache/naif0012.tls", 5257,
                  "ab" * 32, "2026-10-01T00:00:00+00:00"),
    ReferenceFile("space weather", "SW-All.txt", "out of date", "bundled", "/pkg/SW-All.txt", 100, "cd" * 32,
                  "2026-10-01T00:00:00+00:00", "1957-10-01 to 2041-10-31 (observed to 2025-07-20)",
                  "in use; observed data end 2025-07-20"),
    ReferenceFile("Earth orientation", "IERS-based Earth PCKs", "missing", "https://naif.jpl.nasa.gov/pck/",
                  note="runs use IAU_EARTH"),
]


@pytest.fixture
def panel(qtbot, monkeypatch):
    monkeypatch.setattr(dp.reference_data, "inventory", lambda now=None: list(_FILES))
    widget = dp.DataPanelWidget()
    qtbot.addWidget(widget)
    return widget


def test_the_table_lists_every_file_with_status_dates_source_and_checksum(panel):
    assert panel.table.rowCount() == 3
    cells = [[panel.table.item(r, c).text() for c in range(panel.table.columnCount())] for r in range(3)]
    assert cells[1][:4] == ["space weather", "SW-All.txt", "out of date", _FILES[1].covers]
    assert panel.table.item(0, dp._COLUMNS.index("SHA-256")).toolTip() == "ab" * 32  # full SHA-256 one hover away
    assert panel.table.item(0, dp._COLUMNS.index("Source")).toolTip() == "https://naif.jpl.nasa.gov/x"
    assert panel.table.item(0, 1).toolTip() == "/cache/naif0012.tls"
    assert panel.table.item(2, 2).toolTip() == "runs use IAU_EARTH"
    assert "2 need attention" in panel.status_label.text()


def test_only_the_source_column_stretches(panel):
    from PySide6.QtWidgets import QHeaderView

    header = panel.table.horizontalHeader()
    stretching = [c for c in range(panel.table.columnCount())
                  if header.sectionResizeMode(c) == QHeaderView.ResizeMode.Stretch]
    assert stretching == [dp._COLUMNS.index("Source")]


def test_a_declined_download_fetches_nothing(panel, monkeypatch):
    """No consent, no network: the task never starts."""
    started = []
    monkeypatch.setitem(dp._DOWNLOAD_TASKS, "space_weather", lambda: started.append(1))
    monkeypatch.setattr(panel, "confirm_download", lambda download: False)
    assert panel.download("space_weather") is False
    assert started == []


def test_the_consent_prompt_names_source_files_and_size(panel, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    shown = {}

    def question(parent, title, text, buttons, default):
        shown.update(title=title, text=text, default=default)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", question)
    assert panel.download("earth_orientation") is False
    assert "naif.jpl.nasa.gov" in shown["text"] and "about 36 MB" in shown["text"]
    assert "earth_latest_high_prec.bpc" in shown["text"]
    assert shown["default"] == QMessageBox.StandardButton.No


def test_an_accepted_download_runs_and_reports_what_changed(panel, qtbot, monkeypatch):
    after = list(_FILES)
    after[1] = ReferenceFile("space weather", "SW-All.txt", "ok", "bundled", "/pkg/SW-All.txt", 100, "ef" * 32, "",
                             "1957-10-01 to 2041-10-31 (observed to 2026-10-08)")
    calls = []
    monkeypatch.setitem(dp._DOWNLOAD_TASKS, "space_weather",
                        lambda: calls.append(1) or monkeypatch.setattr(dp.reference_data, "inventory",
                                                                     lambda now=None: list(after)))
    monkeypatch.setattr(panel, "confirm_download", lambda download: True)
    assert panel.download("space_weather") is True
    assert not panel.download_button.isEnabled()  # busy while the worker runs
    with qtbot.waitSignal(panel._worker.finished, timeout=10000):
        pass
    qtbot.waitUntil(lambda: panel.download_button.isEnabled(), timeout=5000)
    assert calls == [1]
    assert any("observed to 2026-10-08" in line and "was" in line for line in panel.last_changes)
    assert panel.status_label.text().startswith("Done.")


def test_a_second_download_while_one_runs_is_refused(panel, qtbot, monkeypatch):
    """The re-entrancy guard of the old Kernel Status tab, kept: a second
    request while a task runs would orphan the running thread."""
    release = threading.Event()
    monkeypatch.setitem(dp._DOWNLOAD_TASKS, "support_data", lambda: release.wait(10))
    monkeypatch.setattr(panel, "confirm_download", lambda download: True)
    assert panel.download("support_data") is True
    first = panel._worker
    assert panel.download("support_data") is False
    assert panel._worker is first
    release.set()
    panel.wait_for_worker()


def test_a_failed_download_says_so_and_keeps_the_files(panel, qtbot, monkeypatch):
    def boom():
        raise OSError("network unreachable")

    monkeypatch.setitem(dp._DOWNLOAD_TASKS, "space_weather", boom)
    monkeypatch.setattr(panel, "confirm_download", lambda download: True)
    panel.download("space_weather")
    qtbot.waitUntil(lambda: panel.status_label.text().startswith("Failed:"), timeout=10000)
    assert "network unreachable" in panel.status_label.text()
    assert "unchanged" in panel.status_label.text()
    assert panel.download_button.isEnabled()


def test_changes_lists_new_replaced_and_removed_files():
    before = [ReferenceFile("k", "a", "ok", covers="2020"), ReferenceFile("k", "gone", "ok")]
    after = [ReferenceFile("k", "a", "ok", covers="2026"), ReferenceFile("k", "new", "ok", covers="x")]
    lines = dp.changes(before, after)
    assert "a: now 2026 (was 2020)" in lines and "new: new (x)" in lines and "gone: removed" in lines
    assert dp.changes(before, before) == ["Nothing changed: the files were already the newest available."]


def test_inventory_never_raises_and_names_what_it_could_not_read(monkeypatch):
    """A part that fails (here the Earth orientation files) is listed as missing; the rest still is."""
    from spacemissionstudio.engine import reference_data

    def broken(now):
        raise RuntimeError("manifest unreadable")

    monkeypatch.setattr(reference_data, "_earth_orientation_files", broken)
    files = reference_data.inventory()
    assert any(f.status == "missing" and "manifest unreadable" in f.note for f in files)
    assert any(f.kind == "space weather" for f in files)
