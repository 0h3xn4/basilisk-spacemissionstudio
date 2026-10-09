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

"""Monte Carlo editor: :class:`DispersionListWidget` (one
:class:`schema.scenario.DispersionConfig` per row, referencing a
spacecraft by name) and :class:`MonteCarloGroupWidget` (the enable/
num_runs/thread_count/verbose settings plus that list) -- composed into
``scenario_editor.py`` the same way the space-weather/ground-station
groups are.

The dispersion editor dialog needs to know which spacecraft NAMES exist in
the scenario being edited right now (a dispersion references one by name),
so :class:`DispersionListWidget`/:class:`MonteCarloGroupWidget` expose
``set_spacecraft_names()``; ``ScenarioEditorWidget`` calls it whenever the
spacecraft list changes, same live-refresh pattern as the third-body
-perturber checklist reacting to the central-body combo.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..schema.scenario import (
    SPREAD_ONLY_DISPERSION_QUANTITIES,
    DISPERSION_KINDS_BY_QUANTITY,
    DISPERSION_QUANTITIES,
    ORBIT_ELEMENT_SPREAD_KEYS,
    DispersionConfig,
    MonteCarloConfig,
)
from .feedback import show_toast
from .widgets import ComboBox, PreciseDoubleSpinBox, SpinBox


def _spin(minimum: float, maximum: float, decimals: int = 4, step: float = 1.0, value: float = 0.0) -> QDoubleSpinBox:
    box = PreciseDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setValue(value)
    return box


# What the numbers below mean for each quantity (DispersionConfig field comments).
_UNITS = {
    "dry_mass_kg": "kg",
    "attitude_sigma_bn": "rad, as Euler angles",
    "orbit_elements": "a spread on each element of the initial orbit",
    "inertia_kg_m2": "kg m^2 on each diagonal element, added to the inertia",
    "angular_rate_bn_b": "deg/s on each axis, added to the initial rate",
    "drag_coeff": "drag coefficient Cd [-]",
    "srp_coeff": "radiation-pressure coefficient Cr [-]",
}
_ELEMENT_LABELS = {
    "semi_major_axis_km": "Semi-major axis [km]",
    "eccentricity": "Eccentricity [-]",
    "inclination_deg": "Inclination [deg]",
    "raan_deg": "RAAN [deg]",
    "arg_periapsis_deg": "Argument of periapsis [deg]",
    "true_anomaly_deg": "True anomaly [deg]",
}


class _DispersionEditorDialog(QDialog):
    def __init__(self, spacecraft_names: list, item: DispersionConfig | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit dispersion" if item is not None else "New dispersion")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.spacecraft_combo = ComboBox()
        for name in spacecraft_names:
            self.spacecraft_combo.addItem(name, userData=name)
        if item is not None:
            index = self.spacecraft_combo.findData(item.spacecraft)
            if index >= 0:
                self.spacecraft_combo.setCurrentIndex(index)
            else:
                # item.spacecraft doesn't match any current spacecraft name
                # (e.g. renamed or removed since this dispersion was saved).
                # Silently falling back to index 0 would re-target this
                # dispersion at whichever spacecraft happens to be first --
                # wrong, and invisible to the user. Surface the stale name
                # as its own selectable entry instead (userData carries the
                # real name; the label just flags it), so to_dataclass()
                # still round-trips it unless the user explicitly retargets
                # this dispersion.
                self.spacecraft_combo.addItem(f"{item.spacecraft} (not found in this scenario)",
                                               userData=item.spacecraft)
                self.spacecraft_combo.setCurrentIndex(self.spacecraft_combo.count() - 1)
        form.addRow("Spacecraft", self.spacecraft_combo)

        self.quantity_combo = ComboBox()
        self.quantity_combo.setToolTip(
            "Which quantity gets randomized, independently, on each Monte Carlo run -- e.g. a "
            "real uncertainty in orbit insertion, mass properties, initial attitude or rate, or "
            "the drag and radiation-pressure coefficients. Every other dispersion on this "
            "spacecraft (if any) varies independently alongside it. See User Manual, section 10."
        )
        self.quantity_combo.addItems(DISPERSION_QUANTITIES)
        self.quantity_combo.currentTextChanged.connect(self._refresh_kind_choices)
        self.quantity_combo.currentTextChanged.connect(lambda _text: self._refresh_rows())
        form.addRow("Quantity", self.quantity_combo)

        self.kind_combo = ComboBox()
        self.kind_combo.setToolTip(
            "The probability distribution each run's random draw is taken from -- 'uniform' "
            "needs Bounds below (every value in range equally likely); 'normal' needs Mean/Std "
            "deviation below (a bell curve centered on Mean)."
        )
        self.kind_combo.currentTextChanged.connect(self._on_kind_changed)
        form.addRow("Kind", self.kind_combo)

        self.bounds_lo_spin = _spin(-1.0e9, 1.0e9, decimals=6, value=0.0)
        self.bounds_hi_spin = _spin(-1.0e9, 1.0e9, decimals=6, value=1.0)
        _bounds_tip = "The [low, high] range each run's uniformly-random draw is taken from, inclusive."
        self.bounds_lo_spin.setToolTip(_bounds_tip)
        self.bounds_hi_spin.setToolTip(_bounds_tip)
        self._bounds_row = QHBoxLayout()
        self._bounds_row.addWidget(self.bounds_lo_spin)
        self._bounds_row.addWidget(self.bounds_hi_spin)
        form.addRow("Bounds [lo, hi]", self._bounds_row)

        self.mean_spin = _spin(-1.0e9, 1.0e9, decimals=6, value=0.0)
        self.mean_spin.setToolTip("The center of the normal (bell-curve) distribution each run draws from.")
        form.addRow("Mean", self.mean_spin)
        self.std_spin = _spin(0.0, 1.0e9, decimals=6, value=1.0)
        self.std_spin.setToolTip(
            "The spread of the normal distribution -- about 68% of runs land within one std "
            "deviation of the mean, ~95% within two."
        )
        form.addRow("Std deviation", self.std_spin)
        self.units_label = QLabel()
        self.units_label.setWordWrap(True)
        form.addRow("Units", self.units_label)
        # "orbit_elements": one spread per element (1-sigma for normal,
        # half-width for uniform); 0 leaves the element at its nominal value.
        self.element_spins = {}
        for key in ORBIT_ELEMENT_SPREAD_KEYS:
            spin = _spin(0.0, 1.0e6, decimals=6, value=0.0)
            spin.setToolTip("Spread around this spacecraft's initial value: 1-sigma for 'normal', half-width "
                            "for 'uniform'. 0 keeps the element as configured. For a near-circular orbit put "
                            "an along-track spread on the true anomaly only.")
            self.element_spins[key] = spin
            form.addRow(_ELEMENT_LABELS[key], spin)
        self.angle_std_spin = _spin(0.0, 180.0, decimals=4, value=0.0)
        self.angle_std_spin.setToolTip("1-sigma of a small random rotation of the inertia tensor, which mixes "
                                       "in off-diagonal (product-of-inertia) terms. 0 disperses the diagonal only.")
        form.addRow("Off-diagonal angle 1-sigma [deg]", self.angle_std_spin)
        self._form = form

        layout.addLayout(form)

        if item is not None:
            index = self.quantity_combo.findText(item.quantity)
            if index >= 0:
                self.quantity_combo.setCurrentIndex(index)
        self._refresh_kind_choices(self.quantity_combo.currentText())
        if item is not None:
            index = self.kind_combo.findText(item.kind)
            if index >= 0:
                self.kind_combo.setCurrentIndex(index)
            if item.bounds:
                self.bounds_lo_spin.setValue(item.bounds[0])
                self.bounds_hi_spin.setValue(item.bounds[1])
            if item.mean is not None:
                self.mean_spin.setValue(item.mean)
            if item.std_deviation is not None:
                self.std_spin.setValue(item.std_deviation)
            for key, value in (item.element_spread or {}).items():
                if key in self.element_spins:
                    self.element_spins[key].setValue(value)
            if item.angle_std_deg is not None:
                self.angle_std_spin.setValue(item.angle_std_deg)
        # _on_kind_changed already ran (connected above, and both
        # _refresh_kind_choices()/setCurrentIndex() fire
        # currentTextChanged as they go) -- one more explicit call in
        # case the final kind ended up the SAME as whatever the combo
        # happened to default to, which fires no signal at all, and
        # would otherwise leave the row visibility out of sync with the
        # real selection.
        self._on_kind_changed(self.kind_combo.currentText())

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # See constellation_dialog.py's identical fix for why this is
        # needed: Qt can size a freshly-constructed QDialog smaller than
        # its own sizeHint() on first show() on a real desktop, a gap
        # this project's own offscreen test rendering doesn't reproduce.
        self.resize(self.sizeHint())

    def _refresh_kind_choices(self, quantity: str) -> None:
        current = self.kind_combo.currentText()
        self.kind_combo.clear()
        kinds = DISPERSION_KINDS_BY_QUANTITY.get(quantity, ())
        self.kind_combo.addItems(kinds)
        index = self.kind_combo.findText(current)
        if index >= 0:
            self.kind_combo.setCurrentIndex(index)

    def _on_kind_changed(self, kind: str) -> None:
        """Real user-facing bug this fixes: Bounds/Mean/Std-deviation
        were ALL shown and editable at once regardless of Kind, but
        to_dataclass() only ever uses the pair that matches the
        currently-selected kind (see its own field-by-field ``if kind
        == ...`` logic) -- a value typed into whichever row doesn't
        match was silently discarded with no indication anything was
        ignored. Hiding the irrelevant row(s) makes the dialog show
        only what will actually be used.
        """
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        """Only the fields the selected quantity and kind use are shown."""
        quantity, kind = self.quantity_combo.currentText(), self.kind_combo.currentText()
        orbit = quantity == "orbit_elements"
        self._set_row_visible(self._bounds_row, kind in ("uniform", "uniform_euler_mrp") and not orbit)
        self._set_row_visible(self.mean_spin, kind == "normal" and quantity not in SPREAD_ONLY_DISPERSION_QUANTITIES)
        self._set_row_visible(self.std_spin, kind == "normal" and not orbit)
        for spin in self.element_spins.values():
            self._set_row_visible(spin, orbit)
        self._set_row_visible(self.angle_std_spin, quantity == "inertia_kg_m2")
        self.units_label.setText(_UNITS.get(quantity, ""))

    def _set_row_visible(self, field, visible: bool) -> None:
        label = self._form.labelForField(field)
        if label is not None:
            label.setVisible(visible)
        if isinstance(field, QHBoxLayout):
            for i in range(field.count()):
                widget = field.itemAt(i).widget()
                if widget is not None:
                    widget.setVisible(visible)
        else:
            field.setVisible(visible)

    def _on_accept(self) -> None:
        try:
            self.to_dataclass()
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid dispersion", str(exc))
            return
        self.accept()

    def to_dataclass(self) -> DispersionConfig:
        if not self.spacecraft_combo.count():
            raise ValueError("this scenario has no spacecraft to disperse yet -- add one first")
        kind = self.kind_combo.currentText()
        quantity = self.quantity_combo.currentText()
        orbit = quantity == "orbit_elements"
        config = DispersionConfig(
            spacecraft=self.spacecraft_combo.currentData(),
            quantity=quantity,
            kind=kind,
            bounds=[self.bounds_lo_spin.value(), self.bounds_hi_spin.value()]
            if kind in ("uniform", "uniform_euler_mrp") and not orbit else None,
            mean=self.mean_spin.value() if kind == "normal" and quantity not in SPREAD_ONLY_DISPERSION_QUANTITIES else None,
            std_deviation=self.std_spin.value() if kind == "normal" and not orbit else None,
            element_spread={key: spin.value() for key, spin in self.element_spins.items() if spin.value() > 0}
            if orbit else None,
            angle_std_deg=self.angle_std_spin.value() if quantity == "inertia_kg_m2" else None,
        )
        config.validate()
        return config


class DispersionListWidget(QWidget):
    """A list of :class:`DispersionConfig`, with Add/Edit/Remove -- mirrors
    :class:`gui.sensor_actuator_editor.SensorActuatorListWidget`'s shape.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._items: list = []
        self._spacecraft_names: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Add...")
        self.edit_button = QPushButton("Edit...")
        self.remove_button = QPushButton("Remove")
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.edit_button)
        button_row.addWidget(self.remove_button)
        layout.addLayout(button_row)

        self.add_button.clicked.connect(self._on_add)
        self.edit_button.clicked.connect(self._on_edit)
        self.remove_button.clicked.connect(self._on_remove)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._on_edit())

    def set_spacecraft_names(self, names: list) -> None:
        self._spacecraft_names = list(names)

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for item in self._items:
            self.list_widget.addItem(QListWidgetItem(f"{item.spacecraft}: {item.quantity} ({item.kind})"))

    def _on_add(self) -> None:
        dialog = _DispersionEditorDialog(self._spacecraft_names, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            item = dialog.to_dataclass()
            self._items.append(item)
            self._refresh_list()
            self.list_widget.setCurrentRow(len(self._items) - 1)
            show_toast(self.window(), f"Added dispersion: {item.spacecraft}: {item.quantity}")
            self.changed.emit()

    def _on_edit(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        dialog = _DispersionEditorDialog(self._spacecraft_names, item=self._items[row], parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            item = dialog.to_dataclass()
            self._items[row] = item
            self._refresh_list()
            self.list_widget.setCurrentRow(row)
            show_toast(self.window(), f"Updated dispersion: {item.spacecraft}: {item.quantity}")
            self.changed.emit()

    def _on_remove(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        item = self._items[row]
        del self._items[row]
        self._refresh_list()
        show_toast(self.window(), f"Removed dispersion: {item.spacecraft}: {item.quantity}", kind="info")
        self.changed.emit()

    def to_list(self) -> list:
        return list(self._items)

    def from_list(self, items: list) -> None:
        self._items = list(items)
        self._refresh_list()


class MonteCarloGroupWidget(QGroupBox):
    """Composed directly into ``scenario_editor.py``, same pattern as its
    other ``_build_*_group()`` sections.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Monte Carlo", parent)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setToolTip(
            "Checking this ON runs this scenario repeatedly (Number of runs below), each time "
            "with a fresh random draw for every dispersion configured below, instead of the "
            "single ordinary run Run Simulation otherwise does -- for statistically "
            "characterizing how sensitive the outcome is to real initial-condition uncertainty."
        )
        self.enabled_check.toggled.connect(self.changed)
        form.addRow(self.enabled_check)

        self.num_runs_spin = SpinBox()
        self.num_runs_spin.setRange(1, 1_000_000)
        self.num_runs_spin.setValue(10)
        self.num_runs_spin.setToolTip(
            "How many independent randomized runs to execute. More runs give a statistically "
            "better-characterized spread of outcomes, at a roughly proportional cost in total "
            "run time."
        )
        self.num_runs_spin.valueChanged.connect(self.changed)
        form.addRow("Number of runs", self.num_runs_spin)

        self.thread_count_spin = SpinBox()
        self.thread_count_spin.setRange(1, 256)
        self.thread_count_spin.setValue(1)
        self.thread_count_spin.setToolTip(
            "Unverified above 1 in this project's development sandbox (no Basilisk build there) -- see "
            "engine/monte_carlo.py's module docstring."
        )
        self.thread_count_spin.valueChanged.connect(self.changed)
        form.addRow("Thread count", self.thread_count_spin)

        self.verbose_check = QCheckBox("Verbose")
        self.verbose_check.toggled.connect(self.changed)
        form.addRow(self.verbose_check)
        layout.addLayout(form)

        layout.addWidget(QLabel("Dispersions"))
        self.dispersion_list = DispersionListWidget()
        self.dispersion_list.changed.connect(self.changed)
        layout.addWidget(self.dispersion_list)

    def set_spacecraft_names(self, names: list) -> None:
        self.dispersion_list.set_spacecraft_names(names)

    def to_dataclass(self) -> MonteCarloConfig:
        config = MonteCarloConfig(
            enabled=self.enabled_check.isChecked(),
            num_runs=self.num_runs_spin.value(),
            thread_count=self.thread_count_spin.value(),
            verbose=self.verbose_check.isChecked(),
            dispersions=self.dispersion_list.to_list(),
        )
        config.validate()
        return config

    def from_dataclass(self, config: MonteCarloConfig) -> None:
        self.enabled_check.setChecked(config.enabled)
        self.num_runs_spin.setValue(config.num_runs)
        self.thread_count_spin.setValue(config.thread_count)
        self.verbose_check.setChecked(config.verbose)
        self.dispersion_list.from_list(config.dispersions)
