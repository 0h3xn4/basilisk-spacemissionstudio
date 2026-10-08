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

"""The "End of life" tab: when does a spacecraft come down, and does it
meet the disposal rules? Wraps :func:`engine.lifetime.end_of_life` --
from the scenario's start or the end of the last run, optionally after a
deorbit burn -- computed on a background thread (a few seconds)."""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .badges import MUTED, SUCCESS, WARNING, badge_style
from .scenario_explainer_widget import _clear_layout, _stat_tile
from .theme import PALETTE
from .widgets import ComboBox, PreciseDoubleSpinBox

_FROM_START = "Start of scenario"
_FROM_LAST_RUN = "End of last run"
_DEFAULT_DEORBIT_PERIGEE_KM = 250.0  # [km]
_DEFAULT_HORIZON_YEARS = 30.0  # [year]


class _LifetimeWorker(QThread):
    finished_ok = Signal(object)  # engine.lifetime.EndOfLife
    failed = Signal(str)

    def __init__(self, scenario, spacecraft_name, result, deorbit_perigee_km, max_years, forecast_percentile=50.0,
                 parent=None, drag_coeff=None):
        super().__init__(parent)
        self._args = (scenario, spacecraft_name, result, deorbit_perigee_km, max_years, forecast_percentile,
                      drag_coeff)

    def run(self) -> None:
        try:
            from ..engine import lifetime
        except ImportError as exc:
            self.failed.emit(f"Basilisk is not installed/built ({exc}) -- the lifetime uses its atmosphere model.")
            return
        scenario, name, result, perigee_km, max_years, percentile, drag_coeff = self._args
        try:
            self.finished_ok.emit(lifetime.end_of_life(scenario, name, result, perigee_km, max_years,
                                                       forecast_percentile=percentile, drag_coeff=drag_coeff))
        except lifetime.LifetimeError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 -- shown in the tab, never a crashed thread
            self.failed.emit(f"lifetime estimate failed: {exc}")


class AltitudeChart(QWidget):
    """Perigee and apogee altitude against years, with the 5- and 25-year
    marks and the re-entry altitude."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._data = None  # (years, perigee_km, apogee_km, reentry_km, horizon_years)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:
        return QSize(480, 260)

    def set_data(self, years, perigee_km, apogee_km, reentry_km: float, horizon_years: float) -> None:
        self._data = (list(years), list(perigee_km), list(apogee_km), reentry_km, horizon_years)
        self.update()

    def clear(self) -> None:
        self._data = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(PALETTE["surface"]))
        if not self._data or len(self._data[0]) < 2:
            painter.end()
            return
        years, perigee, apogee, reentry_km, horizon = self._data
        # Scaled to the decay itself (a 3-month lifetime squeezed against a
        # 25-year axis is unreadable); the rule marks show when they fit,
        # and the badges above always say whether each rule is met.
        span_years = years[-1] * 1.05 if years[-1] > 0.0 else 1.0
        top_km = max(apogee) * 1.04
        bottom_km = min(reentry_km, min(perigee)) * 0.9
        plot = QRectF(52.0, 12.0, self.width() - 64.0, self.height() - 40.0)

        def point(year, km):
            return QPointF(plot.left() + plot.width() * year / span_years,
                           plot.bottom() - plot.height() * (km - bottom_km) / (top_km - bottom_km))

        axis_pen = QPen(QColor(PALETTE["border"]))
        painter.setPen(axis_pen)
        painter.drawRect(plot)
        text_pen = QPen(QColor(PALETTE["text_muted"]))
        for km in _nice_ticks(bottom_km, top_km):
            y = point(0.0, km).y()
            painter.setPen(axis_pen)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(text_pen)
            painter.drawText(QRectF(0.0, y - 8.0, plot.left() - 6.0, 16.0),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{km:g}")
        tick_unit = 1.0 / 12.0 if span_years < 1.0 else 1.0  # [year] months for a short decay
        for year in (tick * tick_unit for tick in _nice_ticks(0.0, span_years / tick_unit)):
            x = point(year, bottom_km).x()
            painter.setPen(text_pen)
            painter.drawText(QRectF(x - 30.0, plot.bottom() + 4.0, 60.0, 16.0), Qt.AlignmentFlag.AlignHCenter,
                             f"{year * 12.0:g} mo" if span_years < 1.0 else f"{year:g} y")
        painter.drawText(QRectF(4.0, 0.0, 120.0, 12.0), Qt.AlignmentFlag.AlignLeft, "km")

        # the disposal-rule marks and the re-entry altitude
        rule_pen = QPen(QColor(PALETTE["warning"]))
        rule_pen.setStyle(Qt.PenStyle.DashLine)
        for mark, label in ((5.0, "5 y"), (25.0, "25 y")):
            if mark <= span_years:
                x = point(mark, bottom_km).x()
                painter.setPen(rule_pen)
                painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
                painter.drawText(QRectF(x + 3.0, plot.top() + 2.0, 40.0, 14.0), Qt.AlignmentFlag.AlignLeft, label)
        reentry_pen = QPen(QColor(PALETTE["text_muted"]))
        reentry_pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(reentry_pen)
        y = point(0.0, reentry_km).y()
        painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        legend_x = plot.right() - 150.0
        for row, (label, color) in enumerate((("Perigee", PALETTE["accent"]), ("Apogee", PALETTE["text_muted"]))):
            y = plot.top() + 12.0 + 16.0 * row
            pen = QPen(QColor(color))
            pen.setWidthF(2.0)
            painter.setPen(pen)
            painter.drawLine(QPointF(legend_x, y), QPointF(legend_x + 18.0, y))
            painter.setPen(text_pen)
            painter.drawText(QRectF(legend_x + 24.0, y - 8.0, 120.0, 16.0), Qt.AlignmentFlag.AlignVCenter,
                             f"{label} altitude")
        for series, color in ((apogee, PALETTE["text_muted"]), (perigee, PALETTE["accent"])):
            path = QPainterPath(point(years[0], series[0]))
            for year, km in zip(years[1:], series[1:]):
                path.lineTo(point(year, km))
            pen = QPen(QColor(color))
            pen.setWidthF(2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        painter.end()


def _nice_ticks(low: float, high: float, count: int = 5) -> list:
    import math

    raw = (high - low) / count
    if raw <= 0.0:
        return []
    magnitude = 10.0 ** math.floor(math.log10(raw))
    step = min((s * magnitude for s in (1.0, 2.0, 5.0, 10.0) if s * magnitude >= raw), default=raw)
    first = math.ceil(low / step) * step
    return [first + k * step for k in range(int((high - first) / step) + 1)]


class LifetimeWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._scenario = None
        self._last_run = None  # (scenario, ResultSet) of the last completed run
        self._worker: Optional[_LifetimeWorker] = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.spacecraft_combo = ComboBox()
        form.addRow("Spacecraft", self.spacecraft_combo)
        self.from_combo = ComboBox()
        self.from_combo.addItems([_FROM_START, _FROM_LAST_RUN])
        self.from_combo.setToolTip("End of last run: its final orbit, with the propellant left.")
        form.addRow("From", self.from_combo)
        deorbit_row = QHBoxLayout()
        self.deorbit_check = QCheckBox("Lower perigee to")
        self.deorbit_check.setToolTip("One retrograde burn at apogee with the orbit thruster.")
        self.deorbit_perigee_spin = PreciseDoubleSpinBox()
        self.deorbit_perigee_spin.setRange(130.0, 2000.0)
        self.deorbit_perigee_spin.setDecimals(0)
        self.deorbit_perigee_spin.setValue(_DEFAULT_DEORBIT_PERIGEE_KM)
        self.deorbit_perigee_spin.setSuffix(" km")
        self.deorbit_perigee_spin.setEnabled(False)
        self.deorbit_check.toggled.connect(self.deorbit_perigee_spin.setEnabled)
        deorbit_row.addWidget(self.deorbit_check)
        deorbit_row.addWidget(self.deorbit_perigee_spin)
        deorbit_row.addStretch(1)
        form.addRow("Deorbit burn", deorbit_row)
        self._activity_items = [("50th percentile (AD10 end of life)", 50.0), ("95th percentile", 95.0),
                                ("5th percentile", 5.0)]
        self.activity_combo = ComboBox()
        for label, _value in self._activity_items:
            self.activity_combo.addItem(label)
        self.activity_combo.setToolTip("NASA MSFC's predicted solar activity past the observations. "
                                       "ESA AD10 Sec. 5.9: 50th for end of life.")
        form.addRow("Solar activity", self.activity_combo)
        self._drag_items = [("2.2 (AD10 end of life)", 2.2), ("The spacecraft's own", None)]  # [-]
        self.drag_combo = ComboBox()
        for label, _value in self._drag_items:
            self.drag_combo.addItem(label)
        self.drag_combo.setToolTip("ESA AD10 Sec. 5.2: Cd 2.2 at end of life (3.0 in operations).")
        form.addRow("Drag coefficient", self.drag_combo)
        self.horizon_spin = PreciseDoubleSpinBox()
        self.horizon_spin.setRange(1.0, 100.0)
        self.horizon_spin.setDecimals(0)
        self.horizon_spin.setValue(_DEFAULT_HORIZON_YEARS)
        self.horizon_spin.setSuffix(" years")
        form.addRow("Look ahead", self.horizon_spin)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        self.compute_button = QPushButton("Estimate lifetime")
        self.compute_button.clicked.connect(self.compute)
        button_row.addWidget(self.compute_button)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        self.status_label.setWordWrap(True)
        button_row.addWidget(self.status_label, 1)
        layout.addLayout(button_row)

        self.tiles_row = QHBoxLayout()
        layout.addLayout(self.tiles_row)
        self.badges_row = QHBoxLayout()
        layout.addLayout(self.badges_row)
        self.notes_label = QLabel("")
        self.notes_label.setWordWrap(True)
        self.notes_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        layout.addWidget(self.notes_label)
        self.chart = AltitudeChart()
        layout.addWidget(self.chart, 1)
        hint = QLabel("Orbit-averaged drag with the scenario's atmosphere and space weather. "
                      "See User Manual Sec. 11 and 12.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px;")
        layout.addWidget(hint)
        self._update_from_choices()

    # -- inputs -------------------------------------------------------------

    def set_scenario(self, scenario) -> None:
        """The editor's current scenario (None while it does not validate)."""
        self._scenario = scenario
        current = self.spacecraft_combo.currentText()
        names = [sc.name for sc in scenario.spacecraft] if scenario is not None else []
        if names != [self.spacecraft_combo.itemText(i) for i in range(self.spacecraft_combo.count())]:
            self.spacecraft_combo.clear()
            self.spacecraft_combo.addItems(names)
            if current in names:
                self.spacecraft_combo.setCurrentText(current)
        self._update_from_choices()

    def set_last_run(self, scenario, result) -> None:
        """The scenario and results of the run that just finished."""
        self._last_run = (scenario, result) if scenario is not None and result is not None else None
        self._update_from_choices()

    def _update_from_choices(self) -> None:
        last_run_index = self.from_combo.findText(_FROM_LAST_RUN)
        item = self.from_combo.model().item(last_run_index)
        if item is not None:
            item.setEnabled(self._last_run is not None)
        if self._last_run is None and self.from_combo.currentText() == _FROM_LAST_RUN:
            self.from_combo.setCurrentText(_FROM_START)
        self.compute_button.setEnabled(self._worker is None and self.spacecraft_combo.count() > 0)

    # -- computing ----------------------------------------------------------

    def compute(self) -> None:
        name = self.spacecraft_combo.currentText()
        from_last_run = self.from_combo.currentText() == _FROM_LAST_RUN and self._last_run is not None
        scenario, result = self._last_run if from_last_run else (self._scenario, None)
        if scenario is None or not name:
            return
        if from_last_run and name not in {sc.name for sc in scenario.spacecraft}:
            self._show_error(f"{name} was not in the last run")
            return
        perigee_km = self.deorbit_perigee_spin.value() if self.deorbit_check.isChecked() else None
        self._worker = _LifetimeWorker(scenario, name, result, perigee_km, self.horizon_spin.value(),
                                       self._activity_items[self.activity_combo.currentIndex()][1], self,
                                       drag_coeff=self._drag_items[self.drag_combo.currentIndex()][1])
        self._worker.finished_ok.connect(self._show)
        self._worker.failed.connect(self._show_error)
        self._worker.finished.connect(self._worker_done)
        self.status_label.setText("Estimating...")
        self._update_from_choices()
        self._worker.start()

    def _worker_done(self) -> None:
        self._worker = None
        self._update_from_choices()

    def wait_for_worker(self, timeout_ms: int = 120000) -> None:
        """Blocks until a running estimate finishes (tests, shutdown)."""
        if self._worker is not None:
            self._worker.wait(timeout_ms)

    def _show_error(self, message: str) -> None:
        self.status_label.setText(message)
        self._clear_results()

    def _clear_results(self) -> None:
        _clear_layout(self.tiles_row)
        _clear_layout(self.badges_row)
        self.notes_label.setText("")
        self.chart.clear()

    def _show(self, end_of_life) -> None:
        from ..engine import lifetime as lt

        self._clear_results()
        result = end_of_life.lifetime
        self.status_label.setText("From the end of the last run" if end_of_life.from_end_of_run
                                  else "From the start of the scenario")
        horizon_years = result.horizon_years or self.horizon_spin.value()  # [year] can stop at the data's end
        if result.reentered:
            self.tiles_row.addWidget(_stat_tile("Re-entry", f"{result.reentry_utc:%Y-%m-%d}"))
            self.tiles_row.addWidget(_stat_tile("Lifetime", _years_text(result.lifetime_years)))
        else:
            end_utc = result.start_utc + timedelta(days=horizon_years * 365.25)
            self.tiles_row.addWidget(_stat_tile("Re-entry", f"after {end_utc:%Y-%m}"))
            self.tiles_row.addWidget(_stat_tile("Lifetime", f"> {horizon_years:.1f} years"))
        self.tiles_row.addWidget(_stat_tile("Mass", f"{end_of_life.mass_kg:.1f} kg"))
        plan = end_of_life.deorbit
        if plan is not None:
            self.tiles_row.addWidget(_stat_tile("Deorbit burn", f"{plan.delta_v_m_s:.1f} m/s, "
                                                f"{plan.propellant_kg:.2f} kg"))
        self.tiles_row.addStretch(1)

        for years, label in ((lt.ZERO_DEBRIS_YEARS, "5-year rule"), (lt.IADC_YEARS, "25-year guideline")):
            unknown = not result.known(years)
            met = result.meets(years)
            text = f"{label}: {'not known' if unknown else 'met' if met else 'not met'}"
            badge = QLabel(text)
            badge.setStyleSheet(badge_style(MUTED if unknown else SUCCESS if met else WARNING))
            self.badges_row.addWidget(badge)
        self.badges_row.addStretch(1)

        notes = []
        if plan is not None and not plan.sufficient:
            notes.append(f"Not enough propellant for {plan.target_perigee_km:g} km: the "
                         f"{plan.propellant_available_kg:.2f} kg left lowers the perigee to {plan.perigee_km:.0f} km.")
        notes.extend(result.warnings)
        self.notes_label.setText("\n".join(notes))
        self.chart.set_data([t / (365.25 * 86400.0) for t in result.time_s], result.perigee_altitude_km,
                            result.apogee_altitude_km, lt.REENTRY_ALTITUDE_KM, horizon_years)


def _years_text(years: float) -> str:
    return f"{years * 365.25:.0f} days" if years < 1.0 else f"{years:.1f} years"
