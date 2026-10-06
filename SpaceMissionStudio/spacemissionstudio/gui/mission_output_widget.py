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

"""MissionOutputWidget: the "debug console" for a ``mission_sequence``
run -- a read-only text log of every ``report`` command's
``engine.results.ReportEntry`` (mission time, label, requested series'
snapshot values), in execution order, plus the total command count from
``engine.results.CommandSummary``. Populated once per run by
``MainWindow._on_run_finished()``, not incrementally -- ``RunWorker``
only emits a whole ``CommandSummary`` at the end (``engine.mission_engine.
MissionEngine.run()`` has no per-command progress callback, same
limitation ``RunWorker``'s own docstring already notes for
``engine.service.SimulationService.run()`` vs. ``run_live()``).

``CommandSummary.export_csv()`` already existed (and was already
tested) in ``engine/results.py``, but nothing in this widget ever
called it -- a real gap, found while checking this tab for other UX
issues: the neighboring Results tab has had an "Export all series to
CSV..." button since the Plotly migration, but a user running a
``mission_sequence`` with ``report`` commands had no way to get that
data out except manually selecting/copying the text log. The export
button below fixes that, mirroring ``ResultsWidget._on_export()``'s
pattern (a single ``QFileDialog.getSaveFileName`` here, not
``getExistingDirectory`` -- ``CommandSummary.export_csv()`` writes ONE
file, unlike ``ResultSet.export_csv()``'s one-file-per-series).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..engine.results import CommandSummary

_FILE_FILTER = "CSV files (*.csv)"


class MissionOutputWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._summary: Optional[CommandSummary] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Design-philosophy audit finding (docs/ux_audit.md, "logs not
        # searchable") -- a VIEW-only filter: narrows which report
        # blocks are shown below, never affects what _on_export() writes
        # (that always exports every report, filtered or not, same as
        # this app's own Results tab -- filtering what you're looking at
        # is not the same as discarding data you didn't ask to discard).
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by label, series name, or value...")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._refresh_text)
        filter_row.addWidget(self.filter_edit, stretch=1)
        layout.addLayout(filter_row)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        font = self.text_edit.font()
        font.setFamily("monospace")
        self.text_edit.setFont(font)
        self.text_edit.setPlaceholderText(
            "No mission_sequence commands have run yet -- add commands under Mission sequence and Run Simulation."
        )
        layout.addWidget(self.text_edit)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.export_button = QPushButton("Export to CSV...")
        self.export_button.setToolTip(
            "Writes every report command's snapshot values to one CSV file (long format: one row per "
            "scalar component of every requested series in every report) -- always every report, "
            "regardless of the filter above."
        )
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._on_export)
        button_row.addWidget(self.export_button)
        layout.addLayout(button_row)

    def clear(self) -> None:
        self._summary = None
        self.export_button.setEnabled(False)
        self.filter_edit.clear()
        self.text_edit.clear()

    def set_command_summary(self, summary: Optional[CommandSummary]) -> None:
        if summary is None:
            self.clear()
            return
        self._summary = summary
        self.export_button.setEnabled(bool(summary.reports))
        self._refresh_text()

    def _refresh_text(self) -> None:
        """Rebuilds the displayed text from ``self._summary`` and the
        current filter text -- called on every run (:meth:`set_command_summary`)
        and every filter-box edit (``filter_edit.textChanged``), so typing
        in the filter always reflects the LATEST summary, never a stale one.
        """
        summary = self._summary
        if summary is None:
            return
        needle = self.filter_edit.text().strip().lower()
        lines = [f"{summary.commands_executed} command(s) executed, {len(summary.reports)} report(s):", ""]
        shown = 0
        for i, report in enumerate(summary.reports):
            label = f" ({report.label})" if report.label else ""
            header = f"[{i}] t = {report.t_s:.3f} s{label}"
            body_lines = [f"      {series_name} = {values.tolist()}" for series_name, values in report.values.items()]
            if needle and needle not in "\n".join([header, *body_lines]).lower():
                continue
            shown += 1
            lines.append(header)
            lines.extend(body_lines)
        if needle:
            lines.insert(2, f"({shown} of {len(summary.reports)} report(s) match {needle!r})")
            lines.insert(3, "")
        self.text_edit.setPlainText("\n".join(lines))

    def _on_export(self) -> None:
        if self._summary is None:
            return
        path_str, _selected_filter = QFileDialog.getSaveFileName(self, "Export mission output to CSV", "",
                                                                   _FILE_FILTER)
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix != ".csv":
            path = path.with_suffix(".csv")
        try:
            self._summary.export_csv(path)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export complete", f"Wrote {path}")
