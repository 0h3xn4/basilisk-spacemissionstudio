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

"""MissionOutputWidget: the results of a ``mission_sequence`` run's
``report`` commands -- one table row per reported quantity and one column
per report (e.g. "Before burn" / "After burn"), plus a "Change" column
when there are exactly two, so a before/after comparison reads across a
row. Values use the same names and display units as the Results tab's
plots (``plot_categories``), e.g. semi-major axis in km and angles in
degrees, instead of raw SI code-named values. Populated once per run by
``MainWindow._on_run_finished()``.

The filter is view-only: matching a report's label shows just that
report's column; otherwise it keeps the rows whose name, code name or
values match. "Export CSV..." always writes every report
(``CommandSummary.export_csv()``, raw SI units), filtered or not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..engine.results import CommandSummary, ResultSet, TimeSeries
from ..plot_categories import categorize, legacy_display
from .theme import PALETTE

_FILE_FILTER = "CSV files (*.csv)"
_MISSING = "–"


def _format_time(t_s: float) -> str:
    """Mission time in the largest unit that keeps it readable."""
    if abs(t_s) < 120.0:  # [s]
        return f"{t_s:.3g} s"
    if abs(t_s) < 2 * 3600.0:  # [s]
        return f"{t_s / 60.0:.3g} min"
    if abs(t_s) < 2 * 86400.0:  # [s]
        return f"{t_s / 3600.0:.3g} h"
    return f"{t_s / 86400.0:.3g} d"


def _format_value(value: float) -> str:
    if not np.isfinite(value):
        return str(value)
    if abs(value) >= 1.0e4:
        return f"{value:,.1f}"
    return f"{value:.6g}"


def _format_change(change: float, shown: list) -> str:
    """``after - before`` to the precision the two values are shown at,
    so a change below that precision reads "0", not "+1.7e-05"."""
    decimals = [len(text.split(".", 1)[1]) if "." in text else 0 for text in shown if "e" not in text]
    if len(decimals) != len(shown):
        return f"{change:+.3g}"
    text = f"{change:+,.{max(decimals)}f}"
    return "0" if float(text.replace(",", "")) == 0.0 else text


# Orbit-element families get a group header row, so each row's own label
# stays short ("Inclination [deg]" under "Mean elements (first-order J2)").
_GROUPS = (("Osculating ", "Osculating elements"), ("Mean (first-order J2) ", "Mean elements (first-order J2)"))


def _group_and_title(title: str):
    for prefix, group in _GROUPS:
        if title.startswith(prefix):
            return group, title[len(prefix):]
    return "", title


def _series_rows(name: str, values: np.ndarray, result: Optional[ResultSet], multi_spacecraft: bool):
    """(group, row label, unit, display factor) for each component of one
    reported series, named like its Results-tab plot."""
    values = np.atleast_1d(values)
    series = result.series.get(name) if result is not None else None
    if series is None or len(series.columns) != len(values):
        columns = ("x", "y", "z") if len(values) == 3 else tuple(str(i) for i in range(len(values)))
        series = TimeSeries(name, np.zeros(1), columns, np.zeros((1, len(values))), units="")
    display = categorize(name, series) or legacy_display(name, series)
    group, title = _group_and_title(display.title)
    if not display.standalone_title and multi_spacecraft:
        spacecraft = name.split(".", 1)[0]
        if group:
            group = f"{spacecraft}: {group}"
        else:
            title = f"{spacecraft}: {title}"
    unit = "" if display.unit in ("", "-") else f" [{display.unit}]"
    if len(values) == 1:
        return [(group, f"{title}{unit}", display.unit, display.factor)]
    labels = display.columns or {}
    return [(group, f"{title} {labels.get(column, column)}{unit}", display.unit, display.factor)
            for column in series.columns]


class MissionOutputWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._summary: Optional[CommandSummary] = None
        self._result: Optional[ResultSet] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Report, quantity or value...")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._refresh_table)
        top_row.addWidget(self.filter_edit, stretch=1)
        self.export_button = QPushButton("Export CSV...")
        self.export_button.setToolTip(
            "Write every report's values to one CSV file (SI units, one row per value) -- always every "
            "report, whatever the filter shows."
        )
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._on_export)
        top_row.addWidget(self.export_button)
        layout.addLayout(top_row)

        self.summary_label = QLabel(
            "No reports yet -- add report commands under Mission sequence, then Run Simulation."
        )
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        layout.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setVisible(False)
        layout.addWidget(self.table, stretch=1)
        layout.addStretch(0)

    # -- public API ------------------------------------------------------
    def clear(self) -> None:
        self._summary = None
        self._result = None
        self.export_button.setEnabled(False)
        self.filter_edit.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.table.setVisible(False)
        self.summary_label.setText("")

    def set_command_summary(self, summary: Optional[CommandSummary], result: Optional[ResultSet] = None) -> None:
        """``result`` (the same run's ResultSet) supplies each series'
        units and component names; without it values are shown unconverted."""
        if summary is None:
            self.clear()
            return
        self._summary = summary
        self._result = result
        self.export_button.setEnabled(bool(summary.reports))
        self._refresh_table()

    def table_text(self) -> str:
        """The visible table as tab-separated text (headers first) -- what
        a user would copy; also what the tests read."""
        table = self.table
        visible_columns = [c for c in range(table.columnCount()) if not table.isColumnHidden(c)]
        lines = ["\t".join(table.horizontalHeaderItem(c).text().replace("\n", " ") for c in visible_columns)]
        for row in range(table.rowCount()):
            if not table.isRowHidden(row):
                lines.append("\t".join(table.item(row, c).text() if table.item(row, c) else ""
                                        for c in visible_columns).rstrip("\t"))
        return "\n".join(lines)

    # -- internals ---------------------------------------------------------
    def _refresh_table(self) -> None:
        summary = self._summary
        if summary is None:
            return
        reports = summary.reports
        commands = f"{summary.commands_executed} command{'s' if summary.commands_executed != 1 else ''} run"
        if not reports:
            self.summary_label.setText(f"{commands} · no report commands ran")
            self.table.setVisible(False)
            return

        names: list = []
        for report in reports:
            names += [name for name in report.values if name not in names]
        spacecraft = {name.split(".", 1)[0] for name in names}
        show_change = len(reports) == 2

        grouped: dict = {}  # group -> [(label, code name, unit, [raw value or None per report])]
        for name in names:
            sample = next(report.values[name] for report in reports if name in report.values)
            for component, (group, label, unit, factor) in enumerate(
                    _series_rows(name, sample, self._result, len(spacecraft) > 1)):
                per_report = []
                for report in reports:
                    values = np.atleast_1d(report.values[name]) if name in report.values else None
                    per_report.append(None if values is None or component >= len(values)
                                      else float(values[component]) * factor)
                grouped.setdefault(group, []).append((label, name, unit, per_report))
        # Ungrouped rows (state vector, controllers, ...) first, then each
        # element family under its header. A header row is (group, None, ...).
        rows = list(grouped.pop("", []))
        for group, members in grouped.items():
            rows.append((group, None, "", []))
            rows.extend(members)

        headers = ["Quantity"] + [f"{report.label or f'Report {i + 1}'}\n{_format_time(report.t_s)}"
                                  for i, report in enumerate(reports)]
        if show_change:
            headers.append("Change")
        table = self.table
        table.setUpdatesEnabled(False)
        table.clear()
        table.setColumnCount(len(headers))
        table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels(headers)
        number_alignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        group_font = table.font()
        group_font.setBold(True)
        for row, (label, name, unit, per_report) in enumerate(rows):
            item = QTableWidgetItem(label)
            if name is None:  # a group header row
                item.setFont(group_font)
                item.setForeground(QColor(PALETTE["text"]))
                item.setBackground(QColor(PALETTE["accent_soft"]))
                table.setItem(row, 0, item)
                table.setSpan(row, 0, 1, len(headers))
                continue
            item.setToolTip(name)
            table.setItem(row, 0, item)
            cells = [_MISSING if v is None else _format_value(v) for v in per_report]
            if show_change:
                before, after = per_report
                if before is None or after is None:
                    cells.append(_MISSING)
                else:
                    change = after - before
                    if unit == "deg":
                        change = (change + 180.0) % 360.0 - 180.0  # the short way round
                    cells.append(_format_change(change, cells))
            for column, text in enumerate(cells, start=1):
                cell = QTableWidgetItem(text)
                cell.setTextAlignment(number_alignment)
                table.setItem(row, column, cell)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(headers)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        table.setVisible(True)
        self._apply_filter(rows, reports, commands)
        table.setUpdatesEnabled(True)

    def _apply_filter(self, rows, reports, commands: str) -> None:
        table = self.table
        needle = self.filter_edit.text().strip().lower()
        report_text = f"{len(reports)} report{'s' if len(reports) != 1 else ''}"
        matching_reports = [i for i, report in enumerate(reports) if needle and needle in (report.label or "").lower()]
        for column in range(1, table.columnCount()):
            report_index = column - 1
            if matching_reports:
                table.setColumnHidden(column, report_index not in matching_reports)
            else:
                table.setColumnHidden(column, False)
        shown_rows = 0
        quantity_rows = 0
        group_row = None
        group_visible = False
        for row, (label, name, _unit, per_report) in enumerate(rows):
            if name is None:  # a header: shown when any of its rows is
                if group_row is not None:
                    table.setRowHidden(group_row, not group_visible)
                group_row, group_visible = row, False
                continue
            quantity_rows += 1
            if matching_reports:
                visible = any(per_report[i] is not None for i in matching_reports)
            elif needle:
                raw = [repr(v) for v in per_report if v is not None]
                cells = [table.item(row, c).text() for c in range(1, table.columnCount())]
                visible = any(needle in text.lower() for text in [label, name, *cells, *raw])
            else:
                visible = True
            table.setRowHidden(row, not visible)
            shown_rows += visible
            group_visible = group_visible or visible
        if group_row is not None:
            table.setRowHidden(group_row, not group_visible)
        if matching_reports:
            status = f"{len(matching_reports)} of {report_text} match"
        elif needle:
            status = f"{shown_rows} of {quantity_rows} rows match"
        else:
            status = report_text
        self.summary_label.setText(f"{commands} · {status}")

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
