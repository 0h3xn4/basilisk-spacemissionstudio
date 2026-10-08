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

"""Delta-V and propellant budget in the manner of ESA's AD10 guideline
(EOP-FM/2024-07-177; see engine/propellant_budget.py):

* :class:`BudgetInputsGroup` -- the inputs, a tab of the spacecraft editor
  (saved with the spacecraft as ``propellant_budget``);
* :class:`BudgetWidget` -- the "Budget" tab: the budget table for one
  spacecraft, using the last run for the simulated contributors.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..schema.scenario import SUPPORTED_DISPOSALS, PropellantBudgetConfig
from .theme import PALETTE
from .widgets import ComboBox, PreciseDoubleSpinBox

_DISPOSAL_LABELS = {
    "uncontrolled_reentry": "Uncontrolled re-entry (lower perigee)",
    "controlled_reentry": "Controlled re-entry",
    "graveyard": "Graveyard orbit (GEO)",
    "none": "None",
}


def _spin(minimum, maximum, value, decimals=2, suffix=""):
    box = PreciseDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setValue(value)
    if suffix:
        box.setSuffix(suffix)
    return box


class _OptionalValue(QWidget):
    """A value that can instead come "from the last run"."""

    def __init__(self, value: Optional[float], suffix: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.from_run = QCheckBox("from last run")
        self.spin = _spin(0.0, 1.0e5, value or 0.0, suffix=suffix)
        layout.addWidget(self.from_run)
        layout.addWidget(self.spin, 1)
        self.from_run.toggled.connect(lambda on: self.spin.setEnabled(not on))
        self.from_run.setChecked(value is None)
        self.spin.setEnabled(value is not None)

    def value(self) -> Optional[float]:
        return None if self.from_run.isChecked() else self.spin.value()


class BudgetInputsGroup(QGroupBox):
    """The budget inputs of one spacecraft. Checked: the spacecraft keeps
    a ``propellant_budget``; unchecked: none (the defaults are used)."""

    def __init__(self, config: Optional[PropellantBudgetConfig], parent=None):
        super().__init__("Delta-V and propellant budget (ESA AD10)", parent)
        self.setCheckable(True)
        self.setChecked(config is not None)
        c = config or PropellantBudgetConfig()
        layout = QVBoxLayout(self)

        general = QFormLayout()
        self.mission_years = _spin(0.1, 30.0, c.mission_years, suffix=" years")
        general.addRow("Mission duration", self.mission_years)
        self.dry_includes_margin = QCheckBox("Dry mass already includes margins")
        self.dry_includes_margin.setChecked(c.dry_mass_includes_margin)
        general.addRow(self.dry_includes_margin)
        self.system_margin = _spin(0.0, 99.0, c.system_margin_fraction * 100.0, suffix=" %")
        self.system_margin.setToolTip("AD10 Sec. 5.10: 15% when no other margin policy applies.")
        general.addRow("System margin on dry mass", self.system_margin)
        self.tank_capacity = _spin(0.0, 1.0e5, c.tank_capacity_kg, decimals=3, suffix=" kg")
        self.tank_capacity.setToolTip("Maximum propellant load: the residual (1%) and uncertainty (2%) are "
                                      "taken from it. 0: the budget's own total.")
        general.addRow("Tank capacity", self.tank_capacity)
        self.isp = _spin(0.0, 1.0e5, c.isp_s or 0.0, decimals=1, suffix=" s")
        self.isp.setSpecialValueText("orbit thruster's")
        general.addRow("Specific impulse", self.isp)
        self.thrust_angle = _spin(0.0, 89.9, c.thrust_angle_deg, suffix=" deg")
        self.misalignment = _spin(0.0, 89.9, c.misalignment_deg, suffix=" deg")
        self.plume = _spin(0.01, 1.0, c.plume_efficiency, decimals=3)
        self.modulation = _spin(0.01, 1.0, c.modulation_efficiency, decimals=3)
        general.addRow("Thrust angle / misalignment", _pair(self.thrust_angle, self.misalignment))
        general.addRow("Plume / modulation efficiency", _pair(self.plume, self.modulation))
        layout.addLayout(general)

        bol = QFormLayout()
        self.injection_sma = _spin(0.0, 1.0e4, c.injection_sma_error_km, suffix=" km")
        self.injection_ecc = _spin(0.0, 0.5, c.injection_eccentricity_error, decimals=5)
        self.injection_inc = _spin(0.0, 90.0, c.injection_inclination_error_deg, decimals=3, suffix=" deg")
        self.injection_raan = _spin(0.0, 1.0e4, c.injection_raan_delta_v_m_s, suffix=" m/s")
        self.acquisition = _spin(0.0, 1.0e4, c.orbit_acquisition_delta_v_m_s, suffix=" m/s")
        bol.addRow("Injection error (2-sigma): a", self.injection_sma)
        bol.addRow("Injection error: e vector", self.injection_ecc)
        bol.addRow("Injection error: inclination", self.injection_inc)
        bol.addRow("RAAN / local time correction", self.injection_raan)
        bol.addRow("Orbit acquisition", self.acquisition)
        layout.addWidget(_titled("Beginning of life", bol))

        ops = QFormLayout()
        self.transfer = _spin(0.0, 1.0e4, c.transfer_delta_v_m_s, suffix=" m/s")
        self.in_plane = _OptionalValue(c.in_plane_control_delta_v_m_s, " m/s")
        self.out_of_plane = _OptionalValue(c.out_of_plane_control_delta_v_m_s, " m/s")
        self.formation = _OptionalValue(c.formation_delta_v_m_s, " m/s")
        self.cam_count = _spin(0.0, 1.0e4, c.collision_avoidance_count, decimals=1)
        self.cam_count.setToolTip("Collision avoidances over the mission, e.g. from ESA's DRAMA; the budget "
                                  "counts four times as many (AD10 Sec. 5.6).")
        self.attitude_kg = _spin(0.0, 1.0e4, c.attitude_thruster_propellant_kg, decimals=3, suffix=" kg")
        self.attitude_kg.setToolTip("Attitude control by thrusters; the budget doubles it (AD10 Sec. 5.6).")
        self.hall_kg = _spin(0.0, 1.0e4, c.hall_thruster_ignition_kg, decimals=3, suffix=" kg")
        ops.addRow("Orbit transfers", self.transfer)
        ops.addRow("In-plane orbit control", self.in_plane)
        ops.addRow("Out-of-plane orbit control", self.out_of_plane)
        ops.addRow("Formation keeping", self.formation)
        ops.addRow("Collision avoidances", self.cam_count)
        ops.addRow("Thruster attitude control", self.attitude_kg)
        ops.addRow("Hall thruster ignitions", self.hall_kg)
        layout.addWidget(_titled("Operations", ops))

        eol = QFormLayout()
        self.disposal = ComboBox()
        for key in SUPPORTED_DISPOSALS:
            self.disposal.addItem(_DISPOSAL_LABELS[key], key)
        self.disposal.setCurrentIndex(SUPPORTED_DISPOSALS.index(c.disposal))
        self.disposal_years = _spin(0.1, 25.0, c.disposal_lifetime_years, suffix=" years")
        self.disposal_years.setToolTip("Orbit lifetime after the disposal burn: 5 years under ESA's LEO rule.")
        self.clearance = _spin(0.0, 1.0e3, c.clearance_sma_drop_km, suffix=" km")
        self.clearance.setToolTip("Drop out of the operational orbit first; AD10 suggests >= 5 km in formation.")
        self.controlled_dv = _spin(0.0, 1.0e4, c.controlled_reentry_delta_v_m_s, suffix=" m/s")
        self.controlled_last = _spin(0.0, 1.0e4, c.controlled_reentry_last_burn_m_s, suffix=" m/s")
        eol.addRow("Disposal", self.disposal)
        eol.addRow("Lifetime after disposal", self.disposal_years)
        eol.addRow("Clearance (lower a by)", self.clearance)
        eol.addRow("Controlled re-entry: earlier burns", self.controlled_dv)
        eol.addRow("Controlled re-entry: last burn", self.controlled_last)
        layout.addWidget(_titled("End of life", eol))

    def to_config(self) -> Optional[PropellantBudgetConfig]:
        if not self.isChecked():
            return None
        return PropellantBudgetConfig(
            mission_years=self.mission_years.value(),
            dry_mass_includes_margin=self.dry_includes_margin.isChecked(),
            system_margin_fraction=self.system_margin.value() / 100.0,
            tank_capacity_kg=self.tank_capacity.value(),
            isp_s=self.isp.value() or None,
            thrust_angle_deg=self.thrust_angle.value(),
            misalignment_deg=self.misalignment.value(),
            plume_efficiency=self.plume.value(),
            modulation_efficiency=self.modulation.value(),
            injection_sma_error_km=self.injection_sma.value(),
            injection_eccentricity_error=self.injection_ecc.value(),
            injection_inclination_error_deg=self.injection_inc.value(),
            injection_raan_delta_v_m_s=self.injection_raan.value(),
            orbit_acquisition_delta_v_m_s=self.acquisition.value(),
            transfer_delta_v_m_s=self.transfer.value(),
            in_plane_control_delta_v_m_s=self.in_plane.value(),
            out_of_plane_control_delta_v_m_s=self.out_of_plane.value(),
            formation_delta_v_m_s=self.formation.value(),
            collision_avoidance_count=self.cam_count.value(),
            attitude_thruster_propellant_kg=self.attitude_kg.value(),
            disposal=self.disposal.currentData(),
            clearance_sma_drop_km=self.clearance.value(),
            disposal_lifetime_years=self.disposal_years.value(),
            controlled_reentry_delta_v_m_s=self.controlled_dv.value(),
            controlled_reentry_last_burn_m_s=self.controlled_last.value(),
            hall_thruster_ignition_kg=self.hall_kg.value(),
        )


def _pair(first, second) -> QWidget:
    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(first)
    row.addWidget(second)
    return widget


def _titled(title: str, form: QFormLayout) -> QGroupBox:
    box = QGroupBox(title)
    box.setLayout(form)
    return box


class _BudgetWorker(QThread):
    finished_ok = Signal(object)  # engine.propellant_budget.Budget
    failed = Signal(str)

    def __init__(self, scenario, name, result, run_scenario, parent=None):
        super().__init__(parent)
        self._args = (scenario, name, result, run_scenario)

    def run(self) -> None:
        try:
            from ..engine import propellant_budget as pb
        except ImportError as exc:
            self.failed.emit(f"the budget needs Basilisk ({exc})")
            return
        scenario, name, result, run_scenario = self._args
        try:
            self.finished_ok.emit(pb.compute_budget(scenario, name, result, run_scenario))
        except pb.BudgetError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 -- shown in the tab, never a crashed thread
            self.failed.emit(f"budget failed: {exc}")


_COLUMNS = ("Phase", "Contributor", "Delta-V [m/s]", "Propellant [kg]", "Margin", "From")


class BudgetWidget(QWidget):
    """The budget table of one spacecraft (AD10's summary-table layout)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._scenario = None
        self._last_run = None  # (scenario, ResultSet)
        self._worker: Optional[_BudgetWorker] = None
        self._budget = None
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.spacecraft_combo = ComboBox()
        top.addWidget(QLabel("Spacecraft"))
        top.addWidget(self.spacecraft_combo, 1)
        self.compute_button = QPushButton("Compute budget")
        self.compute_button.clicked.connect(self.compute)
        top.addWidget(self.compute_button)
        self.copy_button = QPushButton("Copy as CSV")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy)
        top.addWidget(self.copy_button)
        layout.addLayout(top)
        self.status_label = QLabel("Inputs: the spacecraft editor's Budget (AD10) tab. The last run supplies "
                                   "orbit control and formation keeping.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        layout.addWidget(self.status_label)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        for column in range(len(_COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch if column == 1
                                        else QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)
        self.totals_label = QLabel("")
        self.totals_label.setStyleSheet("font-weight: 700;")
        layout.addWidget(self.totals_label)
        self.notes_label = QLabel("")
        self.notes_label.setWordWrap(True)
        self.notes_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        layout.addWidget(self.notes_label)
        self._update_enabled()

    def set_scenario(self, scenario) -> None:
        self._scenario = scenario
        current = self.spacecraft_combo.currentText()
        names = [sc.name for sc in scenario.spacecraft] if scenario is not None else []
        if names != [self.spacecraft_combo.itemText(i) for i in range(self.spacecraft_combo.count())]:
            self.spacecraft_combo.clear()
            self.spacecraft_combo.addItems(names)
            if current in names:
                self.spacecraft_combo.setCurrentText(current)
        self._update_enabled()

    def set_last_run(self, scenario, result) -> None:
        self._last_run = (scenario, result) if scenario is not None and result is not None else None

    def _update_enabled(self) -> None:
        self.compute_button.setEnabled(self._worker is None and self.spacecraft_combo.count() > 0)

    def compute(self) -> None:
        name = self.spacecraft_combo.currentText()
        if self._scenario is None or not name:
            return
        run_scenario, result = self._last_run if self._last_run is not None else (None, None)
        if run_scenario is not None and name not in {sc.name for sc in run_scenario.spacecraft}:
            run_scenario = result = None
        self._worker = _BudgetWorker(self._scenario, name, result, run_scenario, self)
        self._worker.finished_ok.connect(self._show)
        self._worker.failed.connect(self._show_error)
        self._worker.finished.connect(self._worker_done)
        self.status_label.setText("Computing (the disposal search can take a minute)...")
        self._update_enabled()
        self._worker.start()

    def wait_for_worker(self, timeout_ms: int = 300000) -> None:
        if self._worker is not None:
            self._worker.wait(timeout_ms)

    def _worker_done(self) -> None:
        self._worker = None
        self._update_enabled()

    def _show_error(self, message: str) -> None:
        self.status_label.setText(message)

    def _show(self, budget) -> None:
        self._budget = budget
        self.table.setRowCount(len(budget.rows))
        for row, entry in enumerate(budget.rows):
            dv = "" if entry.delta_v_m_s is None else f"{entry.delta_v_m_s:.2f}"
            for column, text in enumerate((entry.phase, entry.contributor, dv, f"{entry.propellant_kg:.3f}",
                                           entry.margin, entry.source)):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if column in (2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
        self.status_label.setText(f"Dry mass {budget.dry_mass_kg:.1f} kg, Isp {budget.isp_s:g} s, "
                                  f"efficiency {budget.efficiency:.3f}; {budget.iterations} iteration(s)")
        self.totals_label.setText(f"Total: {budget.total_delta_v_m_s:.2f} m/s, {budget.total_propellant_kg:.3f} kg")
        self.notes_label.setText("\n".join(f"- {n}" for n in budget.notes))
        self.copy_button.setEnabled(True)

    def _copy(self) -> None:
        if self._budget is None:
            return
        lines = [",".join(_COLUMNS)]
        for entry in self._budget.rows:
            dv = "" if entry.delta_v_m_s is None else f"{entry.delta_v_m_s:.3f}"
            lines.append(",".join(f'"{v}"' for v in (entry.phase, entry.contributor, dv,
                                                      f"{entry.propellant_kg:.4f}", entry.margin, entry.source)))
        lines.append(f'"Total","",{self._budget.total_delta_v_m_s:.3f},{self._budget.total_propellant_kg:.4f},"",""')
        QApplication.clipboard().setText("\n".join(lines))
