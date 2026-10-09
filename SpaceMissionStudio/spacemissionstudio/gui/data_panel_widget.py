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
"""The Data tab: every reference data file the tool uses, and the only
places it downloads (UX/UI guidelines, "offline and closed operation").

The table lists each file's kind, status, the dates it covers, its
source, SHA-256 and install time (:func:`engine.reference_data.inventory`,
local reads only; out-of-date files are flagged). A download starts only
from the Download menu, after a prompt that names the source, the files
and their size; afterwards the tab says what changed. Space weather and
Earth orientation files can also be imported from local files and rolled
back to the previous version.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from ..engine import reference_data
from .theme import PALETTE

_logger = logging.getLogger(__name__)
_COLUMNS = ["Kind", "File", "Status", "Covers", "SHA-256", "Installed", "Source"]


class _TaskWorker(QThread):
    """Runs one download, import or rollback off the GUI thread."""

    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, task: Callable[[], object], parent=None):
        super().__init__(parent)
        self._task = task

    def run(self) -> None:
        try:
            self._task()
        except Exception as exc:  # noqa: BLE001 -- report any failure, never crash the worker silently
            _logger.exception("Data task failed")
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit()


def _fetch_support_data():
    from ..engine import kernels

    failed = [s for s in kernels.ensure_kernels() if not s.available]
    if failed:
        raise RuntimeError("; ".join(f"{s.filename}: {s.error}" for s in failed))


def _fetch_space_weather():
    from ..engine import spaceweather

    spaceweather.fetch("SW-All", force=True)


def _fetch_earth_orientation():
    from ..engine import earth_orientation

    earth_orientation.fetch()


_DOWNLOAD_TASKS: Dict[str, Callable[[], object]] = {
    "support_data": _fetch_support_data,
    "space_weather": _fetch_space_weather,
    "earth_orientation": _fetch_earth_orientation,
}


def changes(before: List[reference_data.ReferenceFile], after: List[reference_data.ReferenceFile]) -> List[str]:
    """Short lines on what a download, import or rollback changed."""
    old = {(f.kind, f.name): f for f in before}
    lines = []
    for file in after:
        previous = old.pop((file.kind, file.name), None)
        if previous is None:
            lines.append(f"{file.name}: new ({file.covers or file.status})")
        elif (previous.sha256, previous.covers, previous.status) != (file.sha256, file.covers, file.status):
            detail = f"now {file.covers}" if file.covers and file.covers != previous.covers else "replaced"
            if previous.status != file.status:
                detail += f", {previous.status} -> {file.status}"
            lines.append(f"{file.name}: {detail}" + (f" (was {previous.covers})"
                                                     if previous.covers and previous.covers != file.covers else ""))
    lines += [f"{name}: removed" for (_kind, name) in old]
    return lines or ["Nothing changed: the files were already the newest available."]


class DataPanelWidget(QWidget):
    """Reference data files, with consented downloads, import and rollback."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)  # long URLs keep both ends
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COLUMNS.index("Source"), QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Reads the files on this computer again. No network.")
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        self.download_button = self._menu_button(
            "Download...", "Asks before downloading, naming the source, the files and their size.",
            [(d.title, lambda checked=False, key=d.key: self.download(key))
             for d in reference_data.DOWNLOADS.values()])
        self.import_button = self._menu_button(
            "Import file...", "Install a file you already have, for example from removable media. No network.",
            [("Space-weather file (CelesTrak CSV or TXT)...", self.import_space_weather),
             ("Earth orientation files (NAIF Earth PCKs)...", self.import_earth_orientation)])
        self.rollback_button = self._menu_button(
            "Roll back...", "Put back the version that the last download or import replaced.",
            [("Space weather", lambda: self.roll_back("space_weather")),
             ("Earth orientation", lambda: self.roll_back("earth_orientation"))])
        for button in (self.download_button, self.import_button, self.rollback_button):
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        self._worker: Optional[_TaskWorker] = None
        self.last_changes: List[str] = []
        self.refresh()

    def _menu_button(self, text: str, tooltip: str, items) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        for label, slot in items:
            menu.addAction(label).triggered.connect(slot)
        button.setMenu(menu)
        return button

    # -- table ------------------------------------------------------------

    def refresh(self) -> None:
        """Re-read the local files (no network)."""
        files = reference_data.inventory()
        self._files = files
        self.table.setRowCount(len(files))
        colours = {"ok": PALETTE["success"], "missing": PALETTE["danger"], "out of date": PALETTE["warning"]}
        for row, file in enumerate(files):
            values = [file.kind, file.name, file.status, file.covers,
                      file.sha256[:12] + ("..." if file.sha256 else ""), file.installed_utc[:10], file.source]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == _COLUMNS.index("SHA-256"):
                    item.setToolTip(file.sha256 or "not computed (file over 32 MB)")
                elif column == _COLUMNS.index("File"):
                    item.setToolTip(file.path or file.note)
                elif column == _COLUMNS.index("Source"):
                    item.setToolTip(file.source)
                elif column == _COLUMNS.index("Status"):
                    item.setForeground(_brush(colours.get(file.status, PALETTE["text"])))
                    item.setToolTip(file.note)
                self.table.setItem(row, column, item)
        problems = [f for f in files if f.status != "ok"]
        self.status_label.setText(
            f"{len(files)} reference data file(s); " + (
                f"{len(problems)} need attention: " + ", ".join(f"{f.name} ({f.status})" for f in problems)
                if problems else "all present and current."))

    # -- actions ----------------------------------------------------------

    def confirm_download(self, download: reference_data.Download) -> bool:
        """The consent prompt: what, from where, how much. Default No."""
        text = (f"{download.title}\n\nFrom: {download.source}\nFiles: {', '.join(download.files)}\n"
                f"Size: {download.approx_size}\n\nThe previous files are kept where the data can be rolled "
                "back. Nothing else is sent or received.")
        answer = QMessageBox.question(self, "Download reference data?", text,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def download(self, key: str) -> bool:
        """Download after consent; False when declined or busy."""
        download = reference_data.DOWNLOADS[key]
        if self._busy() or not self.confirm_download(download):
            return False
        self._start(_DOWNLOAD_TASKS[key], f"Downloading: {download.title}...")
        return True

    def import_space_weather(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import space-weather file", "", "CelesTrak (*.csv *.txt)")
        if path and not self._busy():
            from ..engine import spaceweather

            self._start(lambda: spaceweather.import_file(path), "Importing the space-weather file...")

    def import_earth_orientation(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Import Earth orientation files", "",
                                                "NAIF Earth PCK (*.bpc *.cmt)")
        if paths and not self._busy():
            from ..engine import earth_orientation

            self._start(lambda: earth_orientation.import_files(paths), "Importing the Earth orientation files...")

    def roll_back(self, which: str) -> None:
        if self._busy():
            return
        if which == "space_weather":
            from ..engine import spaceweather

            task = spaceweather.rollback
        else:
            from ..engine import earth_orientation

            task = earth_orientation.rollback
        self._start(task, "Rolling back...")

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _start(self, task: Callable[[], object], message: str) -> None:
        self._before = reference_data.inventory()
        for button in (self.download_button, self.import_button, self.rollback_button, self.refresh_button):
            button.setEnabled(False)
        self.status_label.setText(message)
        self._worker = _TaskWorker(task, self)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _enable(self) -> None:
        for button in (self.download_button, self.import_button, self.rollback_button, self.refresh_button):
            button.setEnabled(True)

    def _on_finished(self) -> None:
        self._enable()
        self.refresh()
        self.last_changes = changes(self._before, self._files)
        self.status_label.setText("Done. " + " ".join(self.last_changes))

    def _on_failed(self, message: str) -> None:
        self._enable()
        self.refresh()
        self.last_changes = []
        self.status_label.setText(f"Failed: {message}. The previous files are unchanged.")

    def wait_for_worker(self, timeout_ms: int = 60000) -> None:  # [ms]
        if self._worker is not None:
            self._worker.wait(timeout_ms)


def _brush(colour: str):
    from PySide6.QtGui import QBrush, QColor

    return QBrush(QColor(colour))
