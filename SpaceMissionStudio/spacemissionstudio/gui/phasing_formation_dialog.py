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

"""PhasingFormationDialog: collects a
:class:`engine.formation.PhasingFormationRequest` plus which existing
spacecraft to use as the chief (its orbit) and the template (every other
field) -- see that module's docstring for the Hill-frame math and why
only orbit/name/station_keeping/phasing_keeping vary.

Same "doesn't import the Basilisk-needing engine module beyond its
Basilisk-free request dataclass" split ``constellation_dialog.py`` already
uses -- ``engine.formation`` imports Basilisk lazily, at
``generate_phasing_follower()`` call time, not at module import time (see
that module's docstring), so importing ``PhasingFormationRequest`` here is
still safe without Basilisk installed; the ImportError (if Basilisk truly
isn't available) only surfaces when the caller actually clicks
Generate -- see ``spacecraft_editor.py``'s ``_on_generate_phasing_formation``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from ..engine.formation import PhasingFormationRequest
from ..schema.scenario import ScenarioValidationError
from .widgets import PreciseDoubleSpinBox


def _form_group(title: str) -> tuple[QGroupBox, QFormLayout]:
    group = QGroupBox(title)
    return group, QFormLayout(group)


def _double_spin(minimum: float, maximum: float, decimals: int, step: float, value: float) -> QDoubleSpinBox:
    box = PreciseDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setValue(value)
    return box


class PhasingFormationDialog(QDialog):
    """Modal "Generate phasing formation..." dialog. ``spacecraft_names``
    lists the scenario's current spacecraft (by name) -- the chief must be
    one of them (its orbit is read directly, not re-entered); the
    template (every OTHER field the new follower clones) defaults to the
    same spacecraft but may be any of them, same pattern as
    ``WalkerConstellationDialog``'s own template picker. ``central_body``
    is the scenario's ACTUAL current central body (read-only here, not a
    combo), same reasoning as that dialog's own central-body display.
    """

    def __init__(self, spacecraft_names: list[str], central_body: str = "earth", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate phasing formation")
        self._central_body = central_body

        layout = QVBoxLayout(self)
        description_label = QLabel(
            "Generates a new follower spacecraft that holds a target along-track separation from an "
            "existing chief spacecraft (schema.scenario.PhasingKeepingConfig), from a Radial/Transverse/"
            "Normal (Hill-frame) offset at epoch -- see the Radial/Cross-track fields' own tooltips for an "
            "important limitation. Added to (not replacing) this scenario's spacecraft list."
        )
        # Real bug, from a real user screenshot: without word-wrap, Qt
        # sizes this QLabel (and so the whole dialog) to fit this entire
        # paragraph on ONE line -- thousands of pixels wide. The window
        # manager then centers that oversized dialog, pushing most of it
        # (including every row's own label) off the left edge of the
        # screen, leaving only a thin right-hand sliver visible -- exactly
        # what the screenshot showed.
        description_label.setWordWrap(True)
        layout.addWidget(description_label)

        # Grouped by what each field configures, in two columns -- a flat
        # 20-row form ran ~830 px tall and gave no hint which knobs belong
        # to which controller.
        spacecraft_group, spacecraft_form = _form_group("Spacecraft")
        offset_group, offset_form = _form_group("Initial offset at epoch (Hill frame)")
        propulsion_group, propulsion_form = _form_group("Propulsion")
        station_group, station_form = _form_group("Station-keeping (altitude hold)")
        phasing_group, phasing_form = _form_group("Phasing-keeping (separation hold)")

        spacecraft_form.addRow("Central body", QLabel(central_body))

        self.chief_combo = QComboBox()
        self.template_combo = QComboBox()
        if spacecraft_names:
            for name in spacecraft_names:
                self.chief_combo.addItem(name, userData=name)
                self.template_combo.addItem(name, userData=name)
        else:
            self.chief_combo.addItem("(no spacecraft in this scenario yet)", userData=None)
            self.chief_combo.setEnabled(False)
            self.template_combo.addItem("(no spacecraft in this scenario yet)", userData=None)
            self.template_combo.setEnabled(False)
        self.chief_combo.setToolTip("The existing spacecraft whose orbit the new follower's orbit is offset from.")
        self.template_combo.setToolTip(
            "The existing spacecraft everything else (mass, sensors, actuators, power, ...) is copied from."
        )
        spacecraft_form.addRow("Chief (orbit source)", self.chief_combo)
        spacecraft_form.addRow("Template (everything else)", self.template_combo)

        self.follower_name_edit = QLineEdit("follower-1")
        spacecraft_form.addRow("New follower name", self.follower_name_edit)

        self.radial_km = _double_spin(-10000.0, 10000.0, 3, 1.0, 0.0)
        self.radial_km.setToolTip(
            "Radial offset at epoch [km] -- outward along the chief's position vector. This is a STARTING "
            "geometry only: the active phasing controller does not hold radial separation, so this will "
            "drift over the run (see the dialog's own top note). A nonzero value here also distorts the "
            "follower's own orbital elements enough to throw off the controller's along-track error "
            "estimate (a known numerical effect, worse than merely imprecise -- a correction can end up "
            "making the real along-track separation WORSE, not better). A built-in safety guard suspends "
            "automatic corrections after a couple of cycles that don't actually converge rather than keep "
            "burning propellant into that spiral, but it is a safety net, not a fix -- leave this at 0 "
            "unless you specifically need a radial offset, and prefer a small value if you do."
        )
        self.along_track_km = _double_spin(-100000.0, 100000.0, 3, 1.0, 50.0)
        self.along_track_km.setToolTip(
            "Along-track offset at epoch [km] -- ahead of the chief along its velocity direction. This IS "
            "actively held: it becomes phasing_keeping.target_separation_km, the one separation component "
            "the controller maintains via along-track burns for the whole run. Achieved exactly at epoch "
            "when Radial and Cross-track are both 0. A nonzero radial offset especially (even a modest "
            "tens-of-km one) can push the achieved separation far past this target during the run, not "
            "just start short of it -- see the Radial field's own tooltip."
        )
        self.cross_track_km = _double_spin(-10000.0, 10000.0, 3, 1.0, 0.0)
        self.cross_track_km.setToolTip(
            "Cross-track offset at epoch [km] -- along the chief's orbit-normal direction (out of its "
            "orbital plane). Same starting-geometry-only caveat as the radial offset above -- not actively "
            "held by the controller."
        )
        offset_form.addRow("Radial (R) [km]", self.radial_km)
        offset_form.addRow("Along-track (T) [km]", self.along_track_km)
        offset_form.addRow("Cross-track (N) [km]", self.cross_track_km)

        self.thrust_n = _double_spin(1e-6, 1000.0, 6, 0.01, 0.05)
        self.isp_s = _double_spin(1.0, 1.0e5, 1, 10.0, 1500.0)
        self.propellant_kg = _double_spin(0.0, 1.0e6, 3, 1.0, 5.0)
        self.deadband_km = _double_spin(1e-6, 1.0e5, 3, 0.5, 2.0)
        propulsion_form.addRow("Thruster thrust [N]", self.thrust_n)
        propulsion_form.addRow("Thruster Isp [s]", self.isp_s)
        propulsion_form.addRow("Propellant available [kg]", self.propellant_kg)
        station_form.addRow("Deadband [km]", self.deadband_km)

        # station_keeping_target_altitude_km: None (the checkbox below
        # CHECKED, the default) derives this from the chief's own current
        # altitude at generation time -- the common case, per
        # PhasingFormationRequest's own docstring ("just the same altitude
        # the chief is already at"). Unchecking it reveals a spin box for
        # an explicit value instead.
        self.derive_altitude_check = QCheckBox("Derive from chief's own altitude")
        self.derive_altitude_check.setChecked(True)
        self.derive_altitude_check.setToolTip(
            "Checked (the common case): the new follower's station-keeping target altitude is read "
            "from the chief spacecraft's own current altitude when Generate is clicked, rather than "
            "asking for a value that would usually just repeat it. Uncheck to set an explicit target "
            "altitude instead."
        )
        self.derive_altitude_check.toggled.connect(lambda checked: self.station_keeping_target_altitude_km
                                                     .setEnabled(not checked))
        station_form.addRow("Target altitude", self.derive_altitude_check)
        self.station_keeping_target_altitude_km = _double_spin(0.001, 1.0e6, 3, 10.0, 500.0)
        self.station_keeping_target_altitude_km.setEnabled(False)
        self.station_keeping_target_altitude_km.setToolTip(
            "Explicit station-keeping target altitude for the new follower -- only used while the "
            "checkbox above is OFF."
        )
        station_form.addRow("Explicit altitude [km]", self.station_keeping_target_altitude_km)
        self.eclipse_sunlit_threshold = _double_spin(0.001, 1.0, 4, 0.01, 0.99)
        self.eclipse_sunlit_threshold.setToolTip(
            "The real simulated shadow (eclipse) factor must be at or above this before a reboost "
            "burn is allowed to fire -- a stand-in for a solar-electric bus that can't run its "
            "thruster off battery alone during eclipse. 1.0 = must be in full sunlight; lower values "
            "tolerate partial shadow (e.g. penumbra)."
        )
        station_form.addRow("Eclipse sunlit threshold [-]", self.eclipse_sunlit_threshold)

        self.reconfiguration_interval_days = _double_spin(0.0, 1.0e5, 2, 1.0, 90.0)
        self.tolerance_fraction = _double_spin(1e-6, 10.0, 4, 0.01, 0.10)
        self.restore_tolerance_fraction = _double_spin(1e-6, 10.0, 4, 0.01, 0.02)
        self.correction_window_days = _double_spin(1e-3, 1.0e4, 2, 1.0, 21.0)
        self.max_drift_days = _double_spin(1e-3, 1.0e4, 2, 1.0, 90.0)
        self.max_delta_sma_km = _double_spin(1e-6, 1.0e4, 3, 0.5, 3.0)
        phasing_form.addRow("Reconfiguration interval [day]", self.reconfiguration_interval_days)
        phasing_form.addRow("Tolerance fraction [-]", self.tolerance_fraction)
        phasing_form.addRow("Restore tolerance fraction [-]", self.restore_tolerance_fraction)
        phasing_form.addRow("Correction window [day]", self.correction_window_days)
        phasing_form.addRow("Max drift [day]", self.max_drift_days)
        phasing_form.addRow("Max SMA offset [km]", self.max_delta_sma_km)

        columns = QHBoxLayout()
        left_column = QVBoxLayout()
        right_column = QVBoxLayout()
        for group in (spacecraft_group, offset_group, propulsion_group):
            left_column.addWidget(group)
        for group in (station_group, phasing_group):
            right_column.addWidget(group)
        left_column.addStretch(1)
        right_column.addStretch(1)
        columns.addLayout(left_column, 1)
        columns.addLayout(right_column, 1)
        layout.addLayout(columns)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # See constellation_dialog.py's identical fix for why this is
        # needed: Qt can size a freshly-constructed QDialog smaller than
        # its own sizeHint() on first show() on a real desktop, a gap
        # this project's own offscreen test rendering doesn't reproduce
        # -- measured directly for THIS dialog, even: 497x545 vs its own
        # 497x601 sizeHint.
        self.resize(self.sizeHint())

    def _on_accept(self) -> None:
        try:
            self.to_request()
        except ScenarioValidationError as exc:
            QMessageBox.critical(self, "Invalid phasing formation request", str(exc))
            return
        if self.selected_chief_name() is None:
            QMessageBox.critical(self, "No chief spacecraft",
                                  "Add at least one spacecraft to this scenario before generating a formation.")
            return
        self.accept()

    def to_request(self) -> PhasingFormationRequest:
        request = PhasingFormationRequest(
            chief_name=self.chief_combo.currentData() or "",
            follower_name=self.follower_name_edit.text().strip(),
            radial_km=self.radial_km.value(),
            along_track_km=self.along_track_km.value(),
            cross_track_km=self.cross_track_km.value(),
            reconfiguration_interval_days=self.reconfiguration_interval_days.value(),
            tolerance_fraction=self.tolerance_fraction.value(),
            restore_tolerance_fraction=self.restore_tolerance_fraction.value(),
            correction_window_days=self.correction_window_days.value(),
            max_drift_days=self.max_drift_days.value(),
            max_delta_semi_major_axis_km=self.max_delta_sma_km.value(),
            station_keeping_target_altitude_km=(
                None if self.derive_altitude_check.isChecked() else self.station_keeping_target_altitude_km.value()
            ),
            station_keeping_deadband_km=self.deadband_km.value(),
            thrust_n=self.thrust_n.value(),
            isp_s=self.isp_s.value(),
            propellant_kg=self.propellant_kg.value(),
            eclipse_sunlit_threshold=self.eclipse_sunlit_threshold.value(),
        )
        request.validate()  # raises ScenarioValidationError with a specific message on anything bad
        return request

    def selected_chief_name(self) -> str | None:
        return self.chief_combo.currentData()

    def selected_template_name(self) -> str | None:
        return self.template_combo.currentData()
