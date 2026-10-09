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

"""The Flight Software tab: export each spacecraft's flight software as a
standalone C project, and see whether an earlier export still matches the
scenario (User Manual, "Exporting the flight software").

One card per spacecraft: a status badge (not exported, up to date, stale
with what changed, folder missing, changed on disk, or why it cannot be
exported), the folder, and **Export...** / **Open folder** / **Run SIL...**.
An export runs in a worker thread (it records a short simulation run); the
new record goes back to the scenario through
:attr:`FlightSoftwareWidget.exports_changed`. Run SIL... asks for the
program (:class:`.sil_dialog.SilRunDialog`) and hands the run to the main
window (:attr:`FlightSoftwareWidget.sil_requested`), which runs it like any
other run; its comparison comes back to :meth:`FlightSoftwareWidget.show_sil_report`
(User Manual, "Running the flight software in the loop").
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from .badges import ACCENT, DANGER, MUTED, SUCCESS, WARNING, badge_style
from .sil_comparison_widget import SilComparisonWidget
from .theme import PALETTE

_STATE_BADGES = {
    "current": ("Up to date", SUCCESS),
    "stale": ("Stale", WARNING),
    "missing": ("Folder missing", DANGER),
    "modified": ("Changed on disk", DANGER),
    "unknown spacecraft": ("Unknown spacecraft", DANGER),
}


def exportable_reason(scenario, spacecraft) -> Optional[str]:
    """Why ``spacecraft``'s flight software cannot be exported, or ``None``."""
    if spacecraft.comms_pointing is not None:
        return "comms pointing switches modes in Python, which is not exported"
    if scenario.simulation_mode == "orbit_only":
        return "orbit only: no attitude flight software"
    if spacecraft.fsw_mode is None:
        return "no attitude flight software (pointing mode not set)"
    return None


class _ExportWorker(QThread):
    finished_ok = Signal(object, object)  # ExportResult, FswExportRecord
    failed = Signal(str)

    def __init__(self, scenario, spacecraft_name: str, folder: Path, overwrite: bool, parent=None):
        super().__init__(parent)
        self._scenario = scenario
        self._spacecraft_name = spacecraft_name
        self._folder = folder
        self._overwrite = overwrite

    def run(self) -> None:
        try:
            from ..fsw_export.records import export_flight_software

            result, record = export_flight_software(self._scenario, self._spacecraft_name, self._folder,
                                                    overwrite=self._overwrite)
        except Exception as exc:  # noqa: BLE001 -- every failure is shown to the user, named
            self.failed.emit(str(exc) or type(exc).__name__)
        else:
            self.finished_ok.emit(result, record)


class _SpacecraftCard(QFrame):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("fswCard")
        self.setStyleSheet(f"QFrame#fswCard {{ background-color: {PALETTE['surface']}; "
                           f"border: 1px solid {PALETTE['border']}; border-radius: 0px; }}")
        layout = QGridLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        self.title = QLabel(name)
        self.title.setStyleSheet("font-weight: 600; border: none;")
        self.badge = QLabel()
        self.badge.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet(f"color: {PALETTE['text_muted']}; border: none;")
        self.folder = QLabel()  # the folder's name; the full path is its tooltip
        self.folder.setStyleSheet("border: none;")
        self.export_button = QPushButton("Export...")
        self.open_button = QPushButton("Open folder")
        self.sil_button = QPushButton("Run SIL...")
        self.sil_button.setToolTip("Fly this spacecraft with an external flight-software program, step by step, "
                                   "and compare it with the simulation's own.")
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.sil_button)
        buttons.addWidget(self.export_button)
        layout.addWidget(self.title, 0, 0)
        layout.addWidget(self.badge, 0, 1)
        layout.addWidget(self.folder, 1, 0, 1, 2)
        layout.addWidget(self.detail, 2, 0, 1, 2)
        layout.addLayout(buttons, 3, 0, 1, 2)
        layout.setColumnStretch(0, 1)

    def set_folder(self, path: Optional[str]) -> None:
        self.folder.setVisible(bool(path))
        self.folder.setText(f"Folder: {Path(path).name}" if path else "")
        self.folder.setToolTip(path or "")

    def set_badge(self, text: str, colors: tuple) -> None:
        self.badge.setText(text)
        self.badge.setStyleSheet(badge_style(colors))


class FlightSoftwareWidget(QWidget):
    """Export status and actions, one card per spacecraft."""

    exports_changed = Signal(list)  # the scenario's new fsw_exports list
    sil_requested = Signal(str, object)  # spacecraft name, sil.runner.SilOptions

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._scenario = None
        self._base_dir: Optional[Path] = None
        self._cards: Dict[str, _SpacecraftCard] = {}
        self._worker: Optional[_ExportWorker] = None
        self._busy: Optional[str] = None
        self._sil_running: Optional[str] = None
        outer = QVBoxLayout(self)
        intro = QLabel("Export each spacecraft's attitude flight software as a standalone C project "
                       "(User Manual, \"Exporting the flight software\").")
        intro.setWordWrap(True)
        outer.addWidget(intro)
        self._list = QVBoxLayout()
        outer.addLayout(self._list)
        self._placeholder = QLabel("Fix the validation errors to see the flight software.")
        self._placeholder.setStyleSheet(f"color: {PALETTE['text_muted']};")
        outer.addWidget(self._placeholder)
        self.comparison = SilComparisonWidget()
        outer.addWidget(self.comparison, 1)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(300)  # every keystroke re-validates; check the folders once typing pauses
        self._refresh_timer.timeout.connect(self._refresh)

    # ------------------------------------------------------------------ inputs

    def set_scenario(self, scenario) -> None:
        self._scenario = scenario
        self._refresh_timer.start()

    def set_base_dir(self, base_dir) -> None:
        """The scenario file's folder, for exports recorded with a relative path."""
        self._base_dir = Path(base_dir) if base_dir else None
        self._refresh_timer.start()

    def card(self, name: str) -> Optional[_SpacecraftCard]:
        return self._cards.get(name)

    def wait_for_worker(self) -> None:
        if self._worker is not None:
            self._worker.wait()

    # ------------------------------------------------------------------ display

    def _refresh(self) -> None:
        from ..fsw_export.records import export_status

        scenario = self._scenario
        self._placeholder.setVisible(scenario is None)
        names = [sc.name for sc in scenario.spacecraft] if scenario is not None else []
        for name in list(self._cards):
            if name not in names:
                self._cards.pop(name).deleteLater()
        for index, spacecraft in enumerate(scenario.spacecraft if scenario is not None else []):
            card = self._cards.get(spacecraft.name)
            if card is None:
                card = _SpacecraftCard(spacecraft.name)
                card.export_button.clicked.connect(lambda _=False, n=spacecraft.name: self._on_export(n))
                card.open_button.clicked.connect(lambda _=False, n=spacecraft.name: self._on_open(n))
                card.sil_button.clicked.connect(lambda _=False, n=spacecraft.name: self._on_sil(n))
                self._cards[spacecraft.name] = card
                self._list.insertWidget(index, card)
            reason = exportable_reason(scenario, spacecraft)
            record = next((r for r in scenario.fsw_exports if r.spacecraft == spacecraft.name), None)
            card.export_button.setEnabled(reason is None and self._busy is None)
            card.sil_button.setEnabled(reason is None and self._busy is None and self._sil_running is None)
            card.open_button.setEnabled(record is not None)
            card.set_folder(record.path if record is not None else None)
            if self._busy == spacecraft.name:
                card.set_badge("Exporting...", ACCENT)
                card.detail.setText("Recording a short run and writing the C project...")
            elif self._sil_running == spacecraft.name:
                card.set_badge("In the loop...", ACCENT)
                card.detail.setText("Running with the external flight software; see the progress bar.")
            elif reason is not None:
                card.set_badge("Not exportable", MUTED)
                card.detail.setText(reason)
            elif record is None:
                card.set_badge("Not exported", MUTED)
                card.detail.setText(f"Pointing mode {spacecraft.fsw_mode}; "
                                    f"{len(spacecraft.actuators)} actuator(s).")
            else:
                status = export_status(scenario, record, base_dir=self._base_dir)
                text, colors = _STATE_BADGES.get(status.state, ("?", MUTED))
                card.set_badge(text, colors)
                card.detail.setText(status.message)

    # ------------------------------------------------------------------ actions

    def _folder_of(self, name: str) -> Optional[Path]:
        record = next((r for r in self._scenario.fsw_exports if r.spacecraft == name), None) if self._scenario else None
        if record is None:
            return None
        path = Path(record.path)
        return path if path.is_absolute() or self._base_dir is None else self._base_dir / path

    def ask_sil_options(self, name: str):
        """The confirmed SIL options, or None (tests replace this)."""
        from .sil_dialog import SilRunDialog

        dialog = SilRunDialog(name, self._folder_of(name), self)
        if dialog.exec() != SilRunDialog.DialogCode.Accepted:
            return None
        return dialog.to_options()

    def _on_sil(self, name: str) -> None:
        if self._scenario is None or self._busy is not None or self._sil_running is not None:
            return
        options = self.ask_sil_options(name)
        if options is not None:
            self.sil_requested.emit(name, options)

    def set_sil_running(self, name: Optional[str]) -> None:
        """The spacecraft whose SIL run is in progress, or None."""
        self._sil_running = name
        self._refresh()

    def show_sil_report(self, report, failure: str = "") -> None:
        self._sil_running = None
        self.comparison.show_report(report, failure)
        self._refresh()

    def _on_open(self, name: str) -> None:
        folder = self._folder_of(name)
        if folder is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def choose_folder(self, name: str) -> Optional[Path]:
        """Asks for the export folder (tests replace this)."""
        start = self._folder_of(name) or ((self._base_dir or Path.home()) / f"fsw_{name}")
        chosen = QFileDialog.getExistingDirectory(self, f"Export the flight software of {name} into", str(start))
        return Path(chosen) if chosen else None

    def confirm_overwrite(self, folder: Path) -> bool:
        """Asks before replacing an earlier export (tests replace this)."""
        answer = QMessageBox.question(self, "Replace the earlier export?",
                                      f"{folder} holds an earlier flight-software export. Replace it?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def _on_export(self, name: str) -> None:
        if self._scenario is None or self._busy is not None:
            return
        folder = self.choose_folder(name)
        if folder is None:
            return
        overwrite = (folder / "manifest.json").is_file()
        if overwrite and not self.confirm_overwrite(folder):
            return
        self._busy = name
        self._refresh()
        self._worker = _ExportWorker(self._scenario, name, folder, overwrite, self)
        self._worker.finished_ok.connect(self._on_export_done)
        self._worker.failed.connect(self._on_export_failed)
        self._worker.start()

    def _on_export_done(self, result, record) -> None:
        from ..fsw_export.records import with_record

        self._busy = None
        records = with_record(self._scenario, record)
        self._scenario.fsw_exports = records
        self.exports_changed.emit(records)
        self._refresh()
        card = self._cards.get(record.spacecraft)
        if card is not None:
            manifest = result.manifest
            card.detail.setText(f"Exported {len(manifest['modules'])} modules and {manifest['recorded_steps']} "
                                "recorded steps. Save the scenario to keep the record.")

    def _on_export_failed(self, message: str) -> None:
        name, self._busy = self._busy, None
        self._refresh()
        card = self._cards.get(name)
        if card is not None:
            card.set_badge("Export failed", DANGER)
            card.detail.setText(message)
