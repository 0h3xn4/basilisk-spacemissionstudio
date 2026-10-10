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

"""The SIL comparison panel (Flight Software tab): the last SIL run's
headline numbers, each signal's residual against the simulation's own
flight software, the residual plots and the program's output.
Vizard stays the 3D view of the same run."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from .scenario_explainer_widget import _stat_tile
from .theme import PALETTE
from .widgets import TabWidget

_COLUMNS = ("Signal", "Kind", "Max |residual|", "RMS", "At t [s]", "Max |reference|", "Not written [steps]")


class _NumberItem(QTableWidgetItem):
    def __init__(self, value: float, text: Optional[str] = None):
        super().__init__(text if text is not None else ("" if math.isnan(value) else f"{value:.6g}"))
        self._value = value
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other):  # noqa: D105 -- Qt sort hook
        if isinstance(other, _NumberItem):
            return self._value < other._value
        return super().__lt__(other)


def _duration(seconds: float) -> str:
    return f"{seconds * 1e6:.3g} \u00b5s" if seconds < 1e-3 else f"{seconds * 1e3:.3g} ms"


def _sentence(text: str) -> str:
    text = text.strip()
    return (text[0].upper() + text[1:] + ("" if text.endswith(".") else ".")) if text else ""


class SilComparisonWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.report = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        header = QHBoxLayout()
        self.title_label = QLabel("No SIL run yet")
        self.title_label.setStyleSheet(f"font-weight: 600; font-size: 15px; color: {PALETTE['text']};")
        header.addWidget(self.title_label, 1)
        self.save_button = QPushButton("Save report...")
        self.save_button.setToolTip("The full report (JSON) and the sampled residuals (CSV).")
        self.save_button.clicked.connect(self._on_save)
        header.addWidget(self.save_button)
        layout.addLayout(header)
        self.status_label = QLabel("Run SIL... on a spacecraft shows its comparison here.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        layout.addWidget(self.status_label)
        self.tiles_row = QHBoxLayout()
        layout.addLayout(self.tiles_row)
        self.views = TabWidget()
        signals_page = QWidget()
        signals_layout = QVBoxLayout(signals_page)
        signals_layout.setContentsMargins(0, 4, 0, 0)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        signals_layout.addWidget(self.table, 1)
        self.views.addTab(signals_page, "Signals")
        # The plot view (a QWebEngineView) is built only when there is a
        # report to show, as in the Monte Carlo tab.
        self.plots = None
        self._plots_placeholder = QWidget()
        self.views.addTab(self._plots_placeholder, "Residuals")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.views.addTab(self.log_view, "Program output")
        layout.addWidget(self.views, 1)
        layout.addStretch(0)  # keeps the empty state at the top
        self.show_report(None)

    def show_report(self, report, failure: str = "") -> None:
        """Shows ``report`` (a sil.report.SilReport, or None);
        ``failure`` is the reason when the run did not finish."""
        self.report = report
        has = report is not None
        self.views.setVisible(has)
        self.save_button.setEnabled(has)
        self._set_tiles([])
        if not has:
            self.title_label.setText("No SIL run yet")
            self.status_label.setText("Run SIL... on a spacecraft shows its comparison here.")
            self.table.setRowCount(0)
            if self.plots is not None:
                self.plots.set_result(None)
            self.log_view.setPlainText("")
            return
        self.title_label.setText(f"{report.spacecraft} in the loop with {Path(report.binary).name}")
        lines = []
        if failure:
            lines.append(_sentence(f"Stopped: {failure}"))
        elif report.completed:
            lines.append("Completed.")
        if report.fsw_name and report.fsw_name != report.spacecraft:
            lines.append(_sentence(f"Flight software \"{report.fsw_name}\""))
        lines += [_sentence(w) for w in report.warnings]
        self.status_label.setText(" ".join(lines))
        self.status_label.setStyleSheet(f"color: {PALETTE['danger' if failure else 'text_muted']};")
        self.status_label.setToolTip(f"{report.binary}\nSHA-256 {report.binary_sha256}")
        missing = report.signals_missing
        self._set_tiles([
            ("Steps", f"{report.steps}"),
            ("Dropped steps", f"{report.dropped_steps}"),
            ("Max |residual|", f"{report.max_abs_error:.3g}" + (f" ({missing} not written)" if missing else "")),
            ("Round trip p99", _duration(report.round_trip.get("p99_s", 0.0))),
            ("Jitter (std)", _duration(report.round_trip.get("jitter_s", 0.0))),
            ("Flight-software step", _duration(report.execution.get("mean_s", 0.0))),
        ])
        self._fill_table(report)
        result = report.to_result_set()
        self._ensure_plots().set_result(result if result.series else None)
        self.log_view.setPlainText(report.log_tail or "(the program wrote nothing)")

    def _set_tiles(self, tiles) -> None:
        while self.tiles_row.count():
            item = self.tiles_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for label, value in tiles:
            self.tiles_row.addWidget(_stat_tile(label, value))
        if tiles:
            self.tiles_row.addStretch(1)

    def _fill_table(self, report) -> None:
        self.table.setSortingEnabled(False)
        # Zero in the reference and no error: an unused array slot (motorTorque[4..35]).
        shown = [s for s in report.signals if s.max_abs_reference or s.max_abs_error]
        provided_steps = report.steps - report.dropped_steps
        self.table.setRowCount(len(shown))
        for row, s in enumerate(shown):
            never = provided_steps > 0 and s.steps_missing >= provided_steps
            self.table.setItem(row, 0, QTableWidgetItem(s.name))
            self.table.setItem(row, 1, QTableWidgetItem(s.kind))
            self.table.setItem(row, 2, _NumberItem(math.inf, "not written") if never else _NumberItem(s.max_abs_error))
            self.table.setItem(row, 3, _NumberItem(s.rms_error))
            self.table.setItem(row, 4, _NumberItem(s.time_of_max_s))
            self.table.setItem(row, 5, _NumberItem(s.max_abs_reference))
            self.table.setItem(row, 6, _NumberItem(float(s.steps_missing), str(s.steps_missing)))
        self.table.setSortingEnabled(True)
        self.table.sortItems(2, Qt.SortOrder.DescendingOrder)

    def _ensure_plots(self):
        if self.plots is None:
            from .results_widget import ResultsWidget

            self.plots = ResultsWidget()
            index = self.views.indexOf(self._plots_placeholder)
            self.views.removeTab(index)
            self._plots_placeholder.deleteLater()
            self.views.insertTab(index, self.plots, "Residuals")
        return self.plots

    def choose_report_path(self) -> Optional[Path]:
        """Asks where to save (tests replace this)."""
        name = f"sil_{self.report.spacecraft}.json" if self.report else "sil.json"
        chosen, _ = QFileDialog.getSaveFileName(self, "Save the SIL report", name, "JSON (*.json)")
        return Path(chosen) if chosen else None

    def _on_save(self) -> None:
        if self.report is None:
            return
        path = self.choose_report_path()
        if path is None:
            return
        try:
            path.write_text(self.report.to_json() + "\n", encoding="utf-8")
            self.report.write_residuals_csv(path.with_suffix(".residuals.csv"))
        except OSError as exc:
            QMessageBox.warning(self, "Could not save the report", str(exc))
