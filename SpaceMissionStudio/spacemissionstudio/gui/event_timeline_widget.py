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
"""The Events tab: a run's passes, eclipses, burns, thruster firings and
mode changes as a Gantt timeline over a sortable table (UX/UI guidelines,
"events as a timeline with a sortable, exportable table").

The events come from :func:`engine.events.extract_events`. The timeline
shows the shared :class:`gui.time_cursor.TimeCursor` and sets it by click
or drag; a table row sets it to the event's start; Esc clears it. The mouse wheel zooms
the timeline around the pointer and "Fit" shows the whole run. The table
exports to CSV with a provenance file beside it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QToolTip, QVBoxLayout,
                               QWidget)

from .. import output_provenance
from ..engine import events as event_model
from ..engine.results import ResultSet
from .theme import PALETTE, SERIES_COLORS
from .time_cursor import TimeCursor, describe

# Fixed categorical order, one colour per kind (the Results tab's series colours).
KIND_COLOURS: Dict[str, str] = dict(zip(event_model.KINDS, SERIES_COLORS))
_COLUMNS = ["Start", "End", "Duration", "Kind", "Spacecraft", "Event", "Detail"]
_ROW_HEIGHT = 22  # [px]
_AXIS_HEIGHT = 26  # [px]
_MIN_BAR_PX = 2  # [px] a short event on a long run stays visible


def _plural(kind: str, count: int) -> str:
    """"1 pass", "2 passes", "1 thruster firing", "3 thruster firings"."""
    if count == 1:
        return f"1 {kind}"
    return f"{count} {kind}{'es' if kind.endswith('ss') else 's'}"


def _duration_text(seconds: float) -> str:
    if seconds < 120.0:
        return f"{seconds:.0f} s"
    if seconds < 7200.0:
        return f"{seconds / 60.0:.1f} min"
    return f"{seconds / 3600.0:.2f} h"


class _SortItem(QTableWidgetItem):
    """A cell that sorts by a number, not by its text."""

    def __init__(self, text: str, key: float):
        super().__init__(text)
        self._key = key

    def __lt__(self, other):  # noqa: D105 -- Qt sort hook
        if isinstance(other, _SortItem):
            return self._key < other._key
        return super().__lt__(other)


class GanttView(QWidget):
    """The timeline: one row per spacecraft and kind (per station for a pass)."""

    time_picked = Signal(float)  # [s]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(_AXIS_HEIGHT + 2 * _ROW_HEIGHT)
        self.events: List[event_model.Event] = []
        self.rows: List[str] = []
        self.cursor_s: Optional[float] = None
        self.run_end_s = 1.0  # [s]
        self.view = (0.0, 1.0)  # [s] the visible time span

    def set_events(self, events: List[event_model.Event], run_end_s: float) -> None:
        self.events = events
        self.rows = list(dict.fromkeys(e.row for e in sorted(events, key=lambda e: (e.kind, e.row))))
        self.run_end_s = max(run_end_s, max((e.end_s for e in events), default=0.0), 1.0)  # [s]
        self.fit()
        self.setMinimumHeight(_AXIS_HEIGHT + max(len(self.rows), 2) * _ROW_HEIGHT + 4)

    def fit(self) -> None:
        self.view = (0.0, self.run_end_s)
        self.update()

    def set_cursor_time(self, time_s: Optional[float]) -> None:
        self.cursor_s = time_s
        self.update()

    # -- geometry ---------------------------------------------------------

    def _label_width(self) -> int:
        metrics = QFontMetrics(self.font())
        return min(max([metrics.horizontalAdvance(r) for r in self.rows] + [60]) + 12, self.width() // 3)

    def _plot_rect(self) -> QRectF:
        left = self._label_width()
        return QRectF(left, 0, max(self.width() - left - 8, 10), self.height() - _AXIS_HEIGHT)

    def x_of(self, time_s: float) -> float:
        rect = self._plot_rect()
        start, end = self.view
        return rect.left() + (time_s - start) / (end - start) * rect.width()

    def time_at(self, x: float) -> float:
        rect = self._plot_rect()
        start, end = self.view
        fraction = min(max((x - rect.left()) / rect.width(), 0.0), 1.0)
        return start + fraction * (end - start)  # [s]

    def event_at(self, point: QPointF) -> Optional[event_model.Event]:
        row = int(point.y() // _ROW_HEIGHT)
        if not 0 <= row < len(self.rows):
            return None
        time_s = self.time_at(point.x())
        tolerance_s = (self.view[1] - self.view[0]) / max(self._plot_rect().width(), 1.0) * 3  # [s] 3 px
        for event in self.events:
            if event.row == self.rows[row] and event.start_s - tolerance_s <= time_s <= event.end_s + tolerance_s:
                return event
        return None

    # -- painting ---------------------------------------------------------

    def paintEvent(self, _event):  # noqa: N802 -- Qt API name
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(PALETTE["surface"]))
        rect = self._plot_rect()
        muted, grid = QColor(PALETTE["text_muted"]), QColor(PALETTE["border"])
        if not self.rows:
            painter.setPen(muted)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No events in this run.")
            return
        for index, row in enumerate(self.rows):
            top = index * _ROW_HEIGHT
            painter.setPen(QColor(PALETTE["text"]))
            painter.drawText(QRectF(4, top, rect.left() - 8, _ROW_HEIGHT),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, row)
            painter.setPen(grid)
            painter.drawLine(QPointF(rect.left(), top + _ROW_HEIGHT), QPointF(rect.right(), top + _ROW_HEIGHT))
        self._paint_axis(painter, rect, muted, grid)
        row_index = {row: i for i, row in enumerate(self.rows)}
        start, end = self.view
        painter.setPen(Qt.PenStyle.NoPen)
        for event in self.events:
            if event.end_s < start or event.start_s > end:
                continue
            x0, x1 = self.x_of(max(event.start_s, start)), self.x_of(min(event.end_s, end))
            top = row_index[event.row] * _ROW_HEIGHT + 4
            painter.setBrush(QColor(KIND_COLOURS.get(event.kind, PALETTE["accent"])))
            painter.drawRoundedRect(QRectF(x0, top, max(x1 - x0, _MIN_BAR_PX), _ROW_HEIGHT - 8), 2, 2)
        if self.cursor_s is not None and start <= self.cursor_s <= end:
            x = self.x_of(self.cursor_s)
            painter.setPen(QPen(QColor(PALETTE["danger"]), 2))
            painter.drawLine(QPointF(x, 0), QPointF(x, rect.bottom()))

    def _paint_axis(self, painter: QPainter, rect: QRectF, muted: QColor, grid: QColor) -> None:
        start, end = self.view
        span_h = (end - start) / 3600.0  # [h]
        step_h = next((s for s in (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 6, 12, 24, 48, 168, 720, 2160, 8760)
                       if span_h / s <= 8), 8760.0)  # [h]
        tick = np.ceil(start / 3600.0 / step_h) * step_h  # [h]
        while tick <= end / 3600.0:
            x = self.x_of(tick * 3600.0)
            painter.setPen(grid)
            painter.drawLine(QPointF(x, 0), QPointF(x, rect.bottom()))
            painter.setPen(muted)
            label = f"{tick / 24:g} d" if step_h >= 24 else f"{tick:g} h"
            painter.drawText(QRectF(x - 40, rect.bottom() + 2, 80, _AXIS_HEIGHT - 4), Qt.AlignmentFlag.AlignCenter,
                             label)
            tick += step_h

    # -- mouse ------------------------------------------------------------

    def mousePressEvent(self, event):  # noqa: N802 -- Qt API name
        if event.button() == Qt.MouseButton.LeftButton and event.position().x() >= self._plot_rect().left():
            self.time_picked.emit(self.time_at(event.position().x()))

    def mouseMoveEvent(self, event):  # noqa: N802 -- Qt API name
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.time_picked.emit(self.time_at(event.position().x()))
            return
        hit = self.event_at(event.position())
        if hit is None:
            QToolTip.hideText()
            return
        text = f"{hit.label} ({hit.spacecraft})\n{_duration_text(hit.duration_s)}" + (
            f"\n{hit.detail}" if hit.detail else "")
        QToolTip.showText(event.globalPosition().toPoint(), text, self)

    def wheelEvent(self, event):  # noqa: N802 -- Qt API name
        """Zoom around the pointer, in to one second across at most."""
        centre = self.time_at(event.position().x())
        factor = 0.8 if event.angleDelta().y() > 0 else 1.25
        start, end = self.view
        width = min(max((end - start) * factor, 1.0), self.run_end_s)  # [s]
        new_start = min(max(centre - (centre - start) * width / (end - start), 0.0), self.run_end_s - width)
        self.view = (new_start, new_start + width)
        self.update()


class EventTimelineWidget(QWidget):
    """The Events tab."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._cursor: Optional[TimeCursor] = None
        self._result: Optional[ResultSet] = None
        self._epoch_utc: Optional[str] = None
        self.events: List[event_model.Event] = []
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.kind_boxes: Dict[str, QCheckBox] = {}
        for kind in event_model.KINDS:
            box = QCheckBox(_plural(kind, 2)[2:].capitalize())
            box.setChecked(True)
            box.setStyleSheet(f"QCheckBox {{ border-left: 10px solid {KIND_COLOURS[kind]}; padding-left: 4px; }}")
            box.toggled.connect(self._apply_filter)
            controls.addWidget(box)
            self.kind_boxes[kind] = box
        controls.addStretch(1)
        self.fit_button = QPushButton("Fit")
        self.fit_button.setToolTip("Show the whole run. The mouse wheel zooms the timeline.")
        controls.addWidget(self.fit_button)
        self.export_button = QPushButton("Export CSV...")
        self.export_button.setToolTip("The events shown in the table, with a provenance file beside them.")
        self.export_button.clicked.connect(self._on_export)
        controls.addWidget(self.export_button)
        layout.addLayout(controls)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.cursor_label = QLabel(describe(None))
        self.cursor_label.setWordWrap(True)
        layout.addWidget(self.cursor_label)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.gantt = GanttView()
        self.fit_button.clicked.connect(self.gantt.fit)
        self.gantt.time_picked.connect(self._pick_time)
        splitter.addWidget(self.gantt)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(_COLUMNS.index("Detail"), QHeaderView.ResizeMode.Stretch)
        self.table.cellClicked.connect(self._on_row_clicked)
        self._sorted_by_user = False
        self.table.horizontalHeader().sectionClicked.connect(lambda _c: setattr(self, "_sorted_by_user", True))
        splitter.addWidget(self.table)
        splitter.setSizes([220, 300])
        layout.addWidget(splitter, 1)
        clear = QShortcut(QKeySequence("Esc"), self, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        clear.activated.connect(lambda: self._pick_time(None))
        self.set_result(None)

    # -- wiring -----------------------------------------------------------

    def set_time_cursor(self, cursor: TimeCursor) -> None:
        self._cursor = cursor
        cursor.changed.connect(self.on_cursor_changed)
        self.on_cursor_changed(cursor.time_s)

    def set_result(self, result: Optional[ResultSet], epoch_utc: Optional[str] = None) -> None:
        self._result, self._epoch_utc = result, epoch_utc
        self.events = event_model.extract_events(result)
        missing = event_model.missing_kinds(result) if result is not None else {}
        counts = {kind: sum(e.kind == kind for e in self.events) for kind in event_model.KINDS}
        if result is None:
            self.summary_label.setText("Run a scenario to see its passes, eclipses, burns and mode changes.")
        else:
            text = ", ".join(_plural(kind, n) for kind, n in counts.items() if n)
            self.summary_label.setText((text or "No events") + "." + "".join(
                f" No {_plural(kind, 2)[2:]}: {why}." for kind, why in missing.items()))
        self.export_button.setEnabled(bool(self.events))
        self._apply_filter()

    def visible_events(self) -> List[event_model.Event]:
        shown = {kind for kind, box in self.kind_boxes.items() if box.isChecked()}
        return [e for e in self.events if e.kind in shown]

    def _apply_filter(self) -> None:
        visible = self.visible_events()
        run_end = max((float(s.time_s[-1]) for s in self._result.series.values() if s.time_s.size),
                      default=0.0) if self._result is not None else 0.0  # [s]
        self.gantt.set_events(visible, run_end)
        self._fill_table(visible)

    def _time_text(self, time_s: float) -> str:
        if self._epoch_utc:
            from ..engine import time_system

            try:
                return event_model.utc_text(time_system.elapsed_to_utc(self._epoch_utc, [time_s])[0], "seconds")
            except ValueError:
                pass
        return f"T+{time_s / 3600.0:.3f} h"

    def _fill_table(self, visible: List[event_model.Event]) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(visible))
        for row, event in enumerate(visible):
            cells = [_SortItem(self._time_text(event.start_s), event.start_s),
                     _SortItem(self._time_text(event.end_s), event.end_s),
                     _SortItem(_duration_text(event.duration_s), event.duration_s),
                     QTableWidgetItem(event.kind), QTableWidgetItem(event.spacecraft),
                     QTableWidgetItem(event.label), QTableWidgetItem(event.detail)]
            cells[0].setData(Qt.ItemDataRole.UserRole, event.start_s)
            cells[0].setToolTip(f"T+{event.start_s:.1f} s")
            cells[-1].setToolTip(event.detail)
            for column, item in enumerate(cells):
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)
        if self.table.horizontalHeader().sortIndicatorSection() == 0 and not self._sorted_by_user:
            self.table.sortItems(0, Qt.SortOrder.AscendingOrder)  # earliest first until the user sorts

    # -- cursor -----------------------------------------------------------

    def _pick_time(self, time_s: Optional[float]) -> None:
        if self._cursor is not None:
            self._cursor.set_time(time_s)
        else:
            self.on_cursor_changed(time_s)

    def _on_row_clicked(self, row: int, _column: int) -> None:
        start = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if start is not None:
            self._pick_time(float(start))

    def on_cursor_changed(self, time_s: Optional[float]) -> None:
        self.gantt.set_cursor_time(time_s)
        if time_s is None:
            self.cursor_label.setText(describe(None))
            return
        current = [f"{e.label} ({e.spacecraft})" for e in self.visible_events() if e.start_s <= time_s <= e.end_s]
        self.cursor_label.setText(f"Cursor {describe(time_s, self._epoch_utc)}: "
                                  + ("; ".join(current) if current else "no event in progress") + ".")

    # -- export -----------------------------------------------------------

    def _on_export(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(self, "Export events to CSV", "events.csv", "CSV files (*.csv)")
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix != ".csv":
            path = path.with_suffix(".csv")
        try:
            self.export_csv(path)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export complete", f"Wrote {path}")

    def export_csv(self, path: Path) -> Path:
        """Write the shown events to ``path``, and the run's provenance to
        ``<path>.provenance.json`` (as the Mission Output export does)."""
        event_model.write_csv(self.visible_events(), path, self._epoch_utc)
        provenance = getattr(self._result, "provenance", None)
        if provenance is not None:  # provenance on every output (UX/UI guidelines)
            output_provenance.write_sidecar(path, provenance.to_dict())
        return path
