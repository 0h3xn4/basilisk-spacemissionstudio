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

"""The "Monte Carlo" tab: what a batch produced.

Shows the summary ``engine.monte_carlo_results`` keeps of a batch (never
Basilisk's pickled archive, security analysis S-04): headline tiles for
how far the runs spread, the per-run curves and their 1-sigma spread in
an embedded Results view, and a sortable table of what each run drew
and where it ended. Filled after Run Monte Carlo..., or from a folder an
earlier batch saved (**Open results...**).
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

from ..engine import monte_carlo_results as mcr
from .results_widget import ResultsWidget
from .scenario_explainer_widget import _stat_tile
from .theme import PALETTE

_EMPTY_HINT = ("Run > Run Monte Carlo... shows its batch here. Open results... shows one an earlier batch saved "
               "(the folder you chose for it).")


class _NumberItem(QTableWidgetItem):
    """A table cell shown to 6 significant figures and sorted by value."""

    def __init__(self, value: float):
        super().__init__("" if math.isnan(value) else f"{value:.6g}")
        self._value = value
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other):  # noqa: D105 -- Qt sort hook
        if isinstance(other, _NumberItem):
            return self._value < other._value
        return super().__lt__(other)


_km = mcr.format_km


class MonteCarloResultsWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.batch: Optional[mcr.MonteCarloBatch] = None
        self.folder: Optional[Path] = None

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title_label = QLabel("No Monte Carlo batch yet")
        self.title_label.setStyleSheet(f"font-weight: 600; font-size: 15px; color: {PALETTE['text']};")
        header.addWidget(self.title_label, 1)
        self.spacecraft_label = QLabel("Spacecraft:")
        self.spacecraft_combo = QComboBox()
        self.spacecraft_combo.currentIndexChanged.connect(self._refresh_spacecraft_views)
        header.addWidget(self.spacecraft_label)
        header.addWidget(self.spacecraft_combo)
        self.open_button = QPushButton("Open results...")
        self.open_button.setToolTip("Show the batch an earlier Run Monte Carlo... saved in a folder.")
        self.open_button.clicked.connect(self._on_open)
        header.addWidget(self.open_button)
        layout.addLayout(header)

        self.hint_label = QLabel(_EMPTY_HINT)
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        layout.addWidget(self.hint_label)

        self.tiles_row = QHBoxLayout()
        layout.addLayout(self.tiles_row)

        self.views = QTabWidget()
        # The plot view (a second QWebEngineView next to the Results tab's)
        # is built only once a batch is shown: an idle one in every window
        # costs a Chromium renderer, and the macOS CI runner's test worker
        # crashed showing it on a plain tab switch.
        self.plots: Optional[ResultsWidget] = None
        self._plots_placeholder = QWidget()
        self.views.addTab(self._plots_placeholder, "Plots")
        runs_page = QWidget()
        runs_layout = QVBoxLayout(runs_page)
        runs_layout.setContentsMargins(0, 4, 0, 0)
        runs_hint = QLabel("What each run drew, and where it ended against the batch mean. Click a column to sort.")
        runs_hint.setWordWrap(True)
        runs_hint.setStyleSheet(f"color: {PALETTE['text_muted']};")
        runs_layout.addWidget(runs_hint)
        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        runs_layout.addWidget(self.table, 1)
        export_row = QHBoxLayout()
        export_row.addStretch(1)
        self.export_button = QPushButton("Export table CSV...")
        self.export_button.clicked.connect(self._on_export)
        export_row.addWidget(self.export_button)
        runs_layout.addLayout(export_row)
        self.views.addTab(runs_page, "Runs")
        layout.addWidget(self.views, 1)
        layout.addStretch(0)  # keeps the empty state's hint at the top
        self._show(None)

    # -- loading -----------------------------------------------------------

    def load_folder(self, folder: "str | Path") -> bool:
        """Show the batch summarized in ``folder``. On a problem, says so in
        the hint line and returns False."""
        folder = Path(folder)
        try:
            batch = mcr.load(folder)
        except mcr.MonteCarloResultsError as exc:
            self._show(None)
            self.hint_label.setText(str(exc))
            return False
        self.folder = folder
        self._show(batch)
        return True

    def _on_open(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Monte Carlo results")
        if folder and not self.load_folder(folder):
            QMessageBox.warning(self, "No Monte Carlo results", self.hint_label.text())

    def _show(self, batch: Optional[mcr.MonteCarloBatch]) -> None:
        self.batch = batch
        has_batch = batch is not None and bool(batch.runs)
        self.views.setVisible(has_batch)
        self.export_button.setEnabled(has_batch)
        self.spacecraft_combo.blockSignals(True)
        self.spacecraft_combo.clear()
        if has_batch:
            self.spacecraft_combo.addItems(batch.spacecraft)
        self.spacecraft_combo.blockSignals(False)
        several = has_batch and len(batch.spacecraft) > 1
        self.spacecraft_label.setVisible(several)
        self.spacecraft_combo.setVisible(several)
        if not has_batch:
            self.title_label.setText("No Monte Carlo batch yet")
            self.hint_label.setText(_EMPTY_HINT)
            self._set_tiles([])
            if self.plots is not None:
                self.plots.set_result(None)
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return
        self.title_label.setText(batch.scenario_name)
        days = float(batch.time_s[-1]) / 86400.0 if batch.time_s.size else 0.0
        shown = min(len(batch.runs), mcr.MAX_PLOTTED_RUNS)
        note = f" Plots show the first {shown} runs; the spread uses all." if shown < len(batch.runs) else ""
        source = f"saved in {self.folder.name}" if self.folder else "from this session"
        self.hint_label.setText(f"{days:.3g} days per run, {source}. Spreads are 1-sigma offsets from the mean of "
                                f"all runs: along the orbit, radially and across it.{note}")
        self.hint_label.setToolTip(str(self.folder) if self.folder else "")
        self._ensure_plots().set_result(mcr.to_result_set(batch), batch.epoch_utc or None)
        self._refresh_spacecraft_views()

    def _ensure_plots(self) -> ResultsWidget:
        if self.plots is None:
            self.plots = ResultsWidget()
            index = self.views.indexOf(self._plots_placeholder)
            self.views.removeTab(index)
            self._plots_placeholder.deleteLater()
            self.views.insertTab(index, self.plots, "Plots")
            self.views.setCurrentIndex(index)
        return self.plots

    def _refresh_spacecraft_views(self) -> None:
        batch = self.batch
        if batch is None or not batch.runs:
            return
        spacecraft = self.spacecraft_combo.currentText() or batch.spacecraft[0]
        spread = mcr.final_spread(batch, spacecraft)
        requested = len(batch.runs) + len(batch.failed)
        self._set_tiles([
            ("Runs", f"{len(batch.runs)} of {requested}"),
            ("Failed", ", ".join(str(run) for run in batch.failed) if batch.failed else "none"),
            ("Along-track spread, end", _km(spread.along_track_m)),
            ("Radial spread, end", _km(spread.radial_m)),
            ("Cross-track spread, end", _km(spread.cross_track_m)),
            ("Altitude, end", f"{spread.altitude_min_m / 1e3:.0f}-{spread.altitude_max_m / 1e3:.0f} km"),
        ])
        self.plots.set_featured_series([f"{spacecraft}.monte_carlo.{field}" for field in
                                        ("spread", "along_track_offset", "altitude", "radial_offset")])
        self.plots.show_series(f"{spacecraft}.monte_carlo.spread")
        self._fill_table(spacecraft)

    def _set_tiles(self, tiles) -> None:
        while self.tiles_row.count():
            item = self.tiles_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for label, value in tiles:
            self.tiles_row.addWidget(_stat_tile(label, value), 1)  # equal widths

    def _fill_table(self, spacecraft: str) -> None:
        labels, rows = mcr.run_table(self.batch, spacecraft)
        if len(self.batch.spacecraft) == 1:  # the spacecraft's name on every column says nothing
            labels = [label.removeprefix(f"{spacecraft} ") for label in labels]
        self.table.setSortingEnabled(False)
        self.table.setColumnCount(len(labels))
        self.table.setHorizontalHeaderLabels(labels)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = _NumberItem(value)
                if c == 0:
                    item.setText(str(int(value)))
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.SortOrder.AscendingOrder)

    # -- export ------------------------------------------------------------

    def export_table_csv(self, path: "str | Path") -> Path:
        """The Runs table, for the shown spacecraft, as CSV."""
        path = Path(path)
        labels, rows = mcr.run_table(self.batch, self.spacecraft_combo.currentText() or None)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(labels)
            for row in rows:
                writer.writerow([int(row[0])] + [f"{value:.9g}" for value in row[1:]])
        return path

    def _on_export(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(self, "Export Monte Carlo runs to CSV", "monte_carlo_runs.csv",
                                                  "CSV files (*.csv)")
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix != ".csv":
            path = path.with_suffix(".csv")
        try:
            self.export_table_csv(path)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export complete", f"Wrote {path}")
