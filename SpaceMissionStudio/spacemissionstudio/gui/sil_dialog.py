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

"""Run SIL...: which program to run in the loop, how strictly to time it,
and the user's consent to start it (security analysis S-15).

The program is never taken from the scenario file: the user picks it here,
sees its full path and SHA-256, and confirms. The runner checks the hash
again just before it starts the program.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

from .theme import PALETTE

_TRANSPORTS = (("Automatic (Unix socket, TCP on Windows)", "auto"), ("Unix-domain socket", "unix"),
               ("TCP on 127.0.0.1", "tcp"))


def default_program(export_folder: Optional[Path]) -> Optional[Path]:
    """The export's built ``fsw_host`` when there is one."""
    if export_folder is None:
        return None
    for relative in ("build/fsw_host", "build/Release/fsw_host.exe", "build/Debug/fsw_host.exe", "build/fsw_host.exe"):
        candidate = export_folder / relative
        if candidate.is_file():
            return candidate
    return None


class SilRunDialog(QDialog):
    def __init__(self, spacecraft_name: str, export_folder: Optional[Path] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Run {spacecraft_name}'s flight software in the loop")
        self._export_folder = export_folder
        self._sha256: Optional[str] = None
        layout = QVBoxLayout(self)
        intro = QLabel("The program flies the spacecraft step by step. Its commands are compared with the "
                       "simulation's own flight software.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("fsw_host or fsw_adapter_host from a built export")
        self.path_edit.textChanged.connect(self._on_path_changed)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._on_browse)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        form.addRow("Program", path_row)
        self.hash_label = QLabel("")
        self.hash_label.setWordWrap(True)
        self.hash_label.setStyleSheet(f"color: {PALETTE['text_muted']}; font-family: monospace;")
        form.addRow("SHA-256", self.hash_label)
        self.transport_combo = QComboBox()
        for text, value in _TRANSPORTS:
            self.transport_combo.addItem(text, value)
        form.addRow("Link", self.transport_combo)
        self.deadline_spin = QDoubleSpinBox()
        self.deadline_spin.setRange(0.0, 10000.0)  # [ms]
        self.deadline_spin.setDecimals(2)
        self.deadline_spin.setSuffix(" ms")
        self.deadline_spin.setSpecialValueText("None (wait for every step)")
        self.deadline_spin.setToolTip("An answer later than this counts as a dropped step; the previous commands "
                                      "stay in place.")
        form.addRow("Step deadline", self.deadline_spin)
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(0.1, 600.0)  # [s]
        self.timeout_spin.setValue(10.0)  # [s]
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setToolTip("With no answer at all for this long, the run stops with an error.")
        form.addRow("Step timeout", self.timeout_spin)
        layout.addLayout(form)

        self.consent_check = QCheckBox("I trust this program: it runs on this computer with my user's rights.")
        self.consent_check.toggled.connect(self._update_ok)
        layout.addWidget(self.consent_check)
        self.problem_label = QLabel("")
        self.problem_label.setWordWrap(True)
        self.problem_label.setStyleSheet(f"color: {PALETTE['danger']};")
        layout.addWidget(self.problem_label)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.run_button = self.buttons.addButton("Run SIL", QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        program = default_program(export_folder)
        if program is not None:
            self.path_edit.setText(str(program))
        self._on_path_changed()

    def _on_browse(self) -> None:
        start = self.path_edit.text().strip() or str(self._export_folder or Path.home())
        chosen, _ = QFileDialog.getOpenFileName(self, "The flight-software program", start)
        if chosen:
            self.path_edit.setText(chosen)

    def _on_path_changed(self) -> None:
        from ..sil.contract import SilError
        from ..sil.runner import check_binary, file_sha256

        self._sha256 = None
        self.consent_check.setChecked(False)  # a new program needs a new consent
        text = self.path_edit.text().strip()
        if not text:
            self.hash_label.setText("")
            self.problem_label.setText("Choose the program to run.")
        else:
            try:
                path = check_binary(text)
                self._sha256 = file_sha256(path)
            except (SilError, OSError) as exc:
                self.hash_label.setText("")
                self.problem_label.setText(str(exc))
            else:
                self.hash_label.setText(self._sha256)
                self.hash_label.setToolTip(str(path))
                self.problem_label.setText("")
        self._update_ok()

    def _update_ok(self) -> None:
        self.run_button.setEnabled(self._sha256 is not None and self.consent_check.isChecked())

    def to_options(self):
        from ..sil.runner import SilOptions
        from ..sil.session import Timeouts

        deadline_ms = self.deadline_spin.value()
        timeouts = Timeouts(step_s=self.timeout_spin.value(), deadline_s=deadline_ms * 1e-3 if deadline_ms else None)
        return SilOptions(str(Path(self.path_edit.text().strip()).expanduser().resolve()), timeouts,
                          self.transport_combo.currentData(), expected_sha256=self._sha256)
