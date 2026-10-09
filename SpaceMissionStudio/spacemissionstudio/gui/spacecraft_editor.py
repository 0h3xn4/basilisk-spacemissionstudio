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

"""Spacecraft list + per-spacecraft editor dialog.

Phase 1 scope note (superseded): editing used to only touch the fields
``engine.service.SimulationService`` consumed at the time (name, orbit,
dry mass, inertia, initial attitude/rate) and silently DROPPED
``sensors``/``actuators``/``fsw_mode``/``fsw_params``/``control_params``
on every edit -- ``to_dataclass()`` built a brand new ``SpacecraftConfig``
without passing them through. That was fine as long as nothing set them
(no Phase 1 editor did), but it was a latent bug the moment anything else
did (a hand-edited scenario file, or this Phase 2 editor itself re-editing
a spacecraft). Fixed now: ``to_dataclass()`` takes the ORIGINAL config (if
editing one) and carries those fields through unless this dialog's own
sensor/actuator/FSW editors changed them.

drag/SRP are still not editable here -- there is deliberately no UI for
them yet, same reasoning as before -- even though ``engine.service`` DOES
now wire them up (Phase 4; see that module's docstring). ``to_dataclass()``
carries ``enable_drag``/``drag_coeff``/``drag_area_m2``/``enable_srp``/
``srp_coeff``/``srp_area_m2`` through from the original config the same
way it does sensors/actuators/fsw_mode, so editing a spacecraft with these
already set (e.g. from a hand-edited scenario file) doesn't silently reset
them -- that was a real bug (found by audit, no editor ever existed to
trigger it in the GUI itself) fixed at the same time this paragraph was
corrected.
"""

from __future__ import annotations

from typing import NamedTuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..schema.scenario import (
    ActuatorConfig,
    CommsPointingConfig,
    ConstantThrustConfig,
    FuelTankConfig,
    GeoStationKeepingConfig,
    MagneticMomentumManagementConfig,
    MomentumDumpingConfig,
    OrbitIC,
    PhasingKeepingConfig,
    PowerConfig,
    RFLinkConfig,
    ScenarioValidationError,
    SensorConfig,
    SpacecraftConfig,
    StationKeepingConfig,
    SUPPORTED_ACTUATOR_KINDS,
    SUPPORTED_FSW_MODES,
    SUPPORTED_SENSOR_KINDS,
    SUPPORTED_THRUST_FRAMES,
)
from .facet_editor import FacetTableWidget
from .feedback import clear_invalid, mark_invalid, show_toast
from .number_list import NumberListEditor
from .orbit_ic_widget import OrbitIcWidget
from .param_form import ParamForm
from .sensor_actuator_editor import SensorActuatorListWidget
from .theme import PALETTE
from .widgets import ComboBox, PreciseDoubleSpinBox, TabWidget

_FSW_MODE_NONE_LABEL = "(none -- no attitude control)"


class _FswParamSpec(NamedTuple):
    key: str
    required: bool
    example: object
    help_text: str
    # False only for locationPointing's target_body: it and
    # target_ground_station are mutually exclusive (Scenario.validate()
    # enforces exactly one), so "Reset to template" must not fill both at
    # once -- see _fsw_template_params.
    fill_on_reset: bool = True
    normalizable: bool = True  # False for a 3-vector that is not a direction
    label: str = ""  # short form-row label (gui.param_form.ParamForm)


# One spec per fsw_params key -- drives the Attitude control tab's form
# (gui.param_form.ParamForm), "Reset to template" and the required-key
# check. Keep in sync with engine.fsw.build_guidance()'s actual
# fsw_params.get()/[...] usage.
_FSW_MODE_PARAM_SPECS: dict[str, list[_FswParamSpec]] = {
    "inertial3D": [
        _FswParamSpec("sigma_R0N", False, [0.0, 0.0, 0.0], "target inertial attitude, MRP [-]",
                      normalizable=False, label="Target attitude (MRP)"),
    ],
    "hillPoint": [],
    "velocityPoint": [],
    "sunSafePoint": [
        _FswParamSpec("sHatBdyCmd", False, [0.0, 0.0, 1.0], "body-frame sun-pointing axis, unit vector [-]",
                      label="Axis to point at the Sun"),
        _FswParamSpec("min_unit_mag", False, 0.1, "minimum sun-sensor signal magnitude to trust [-]",
                      label="Min. sun-sensor signal"),
        _FswParamSpec("sun_axis_spin_rate_rad_s", False, 0.0, "commanded spin rate about sHatBdyCmd [rad/s]",
                      label="Spin rate about the Sun axis"),
        _FswParamSpec("use_css_estimation", False, False,
                      "true: estimate sun heading from this spacecraft's own 'coarse_sun_sensor' "
                      "sensors (cssWlsEst) instead of simpleNav's noise-free truth -- requires at "
                      "least one coarse_sun_sensor sensor", label="Estimate Sun heading from CSS"),
    ],
    "locationPointing": [
        # Exactly one of these two (Scenario.validate() enforces the xor).
        # Both are optional rows in the form, and ticking one unticks the
        # other; target_body's fill_on_reset=False keeps "Reset to
        # template" from filling both.
        _FswParamSpec("target_ground_station", False, "<ground station name>",
                      "name of a GroundStationConfig already in this scenario -- exactly one of this or "
                      "target_body is required", label="Point at ground station"),
        _FswParamSpec("target_body", False, "moon",
                      "name of a SPICE-tracked body (gravity.central_body or a gravity"
                      ".third_body_perturbers entry) to point at directly -- exactly one of this or "
                      "target_ground_station is required", fill_on_reset=False, label="Point at celestial body"),
        _FswParamSpec("pHat_B", False, [0.0, 0.0, 1.0], "body-frame pointing axis, unit vector [-]",
                      label="Pointing axis"),
    ],
}

# One line per mode, shown under the mode combo.
_FSW_MODE_SUMMARIES: dict = {
    None: "No attitude control: the spacecraft coasts under the torques that are switched on.",
    "inertial3D": "Holds one fixed attitude relative to the stars.",
    "hillPoint": "Keeps the body aligned with the orbit (Hill) frame: radial, along-track, orbit normal.",
    "velocityPoint": "Keeps the body aligned with the velocity direction.",
    "sunSafePoint": "Points a body axis at the Sun.",
    "locationPointing": "Points a body axis at a ground station or a celestial body.",
}

_TARGET_BODY_CHOICES = ["moon", "sun", "earth", "mars", "venus", "jupiter"]

# Mirrors engine.fsw.DEFAULT_MRP_GAINS -- not imported directly since
# engine.fsw pulls in Basilisk, which this GUI module must not require
# just to be opened (see e.g. tests/gui/'s requires_gui-only, no
# requires_basilisk, marker on every test that imports this module).
_CONTROL_PARAM_SPECS: list[_FswParamSpec] = [
    _FswParamSpec("K", False, 3.5, "MRP feedback proportional (attitude) gain", label="Attitude gain K"),
    _FswParamSpec("P", False, 30.0, "MRP feedback derivative (rate) gain", label="Rate gain P"),
    _FswParamSpec("Ki", False, -1.0, "integral gain (negative disables integral feedback)",
                  label="Integral gain Ki"),
    _FswParamSpec("integral_limit", False, 0.0, "integral windup limit", label="Integral limit"),
]


def _fsw_template_params(fsw_mode: "str | None") -> dict:
    if fsw_mode is None:
        return {}
    return {spec.key: spec.example for spec in _FSW_MODE_PARAM_SPECS.get(fsw_mode, []) if spec.fill_on_reset}


def _fsw_missing_required_keys(fsw_mode: "str | None", params: dict) -> list[str]:
    if fsw_mode is None:
        return []
    if fsw_mode == "locationPointing":
        # Exactly one of these two satisfies locationPointing's own
        # requirement (Scenario.validate() enforces the xor itself, with a
        # specific error message, if both end up present).
        return [] if ("target_ground_station" in params or "target_body" in params) else ["target_ground_station"]
    return [spec.key for spec in _FSW_MODE_PARAM_SPECS.get(fsw_mode, []) if spec.required and spec.key not in params]


def _fsw_hint_text(fsw_mode: "str | None") -> str:
    return _FSW_MODE_SUMMARIES.get(fsw_mode, "")


def _spin(minimum: float, maximum: float, decimals: int = 4, step: float = 1.0, value: float = 0.0) -> QDoubleSpinBox:
    box = PreciseDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setValue(value)
    return box


def _scrollable(content: QWidget) -> QScrollArea:
    """Wraps a tab page in its own scroll area. Without this, a
    QTabWidget sizes EVERY tab to fit whichever tab page is tallest (a
    well-known Qt behavior -- its internal QStackedWidget's size hint is
    the max across all pages, not just the current one), so one busy tab
    (e.g. "Power / propulsion / link budget", with five stacked group
    boxes) forced every other tab -- including "Orbit / mass", whose own
    content is a third the height -- to render with a huge dead-space gap
    at the bottom of its group box. Each tab scrolling independently
    fixes that and keeps the dialog itself from growing unreasonably
    tall, same reasoning as ``gui.scenario_editor.ScenarioEditorWidget``'s
    own top-level QScrollArea.
    """
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(content)
    return scroll


class SpacecraftEditorDialog(QDialog):
    """Edits one :class:`SpacecraftConfig` in place. Construct with an
    existing config to edit it, or ``None`` for a fresh default.
    """

    def __init__(self, config: SpacecraftConfig | None = None, parent: QWidget | None = None,
                 other_spacecraft_names: list[str] | None = None, simulation_mode: str = "full_attitude",
                 ground_station_names: list[str] | None = None, epoch_provider=None):
        super().__init__(parent)
        self.setWindowTitle("Spacecraft" if config is None else f"Spacecraft: {config.name}")
        self._other_spacecraft_names = other_spacecraft_names or []
        # Used only to populate comms_pointing_group's target_ground_station
        # combo below -- same "provider-fed, not cross-checked here"
        # convention as _other_spacecraft_names/pk_chief_combo.
        self._ground_station_names = ground_station_names or []
        # See Scenario.simulation_mode's docstring: "orbit_only" hides the
        # Sensors/actuators and FSW tabs and the Power budget group below
        # (RF link/station-keeping/constant-thrust stay -- none need
        # attitude). Only affects what's SHOWN here; the actual enforcement
        # is schema-level (Scenario.validate()), so a scenario file that
        # already has these set still round-trips correctly if the mode is
        # later switched back to "full_attitude".
        self._orbit_only = simulation_mode == "orbit_only"

        outer_layout = QVBoxLayout(self)
        tabs = TabWidget()
        self.tabs = tabs
        outer_layout.addWidget(tabs)

        orbit_tab = QWidget()
        layout = QVBoxLayout(orbit_tab)

        top_form = QFormLayout()
        self.name_edit = QLineEdit(config.name if config else "sat-1")
        self.name_edit.textChanged.connect(self._on_name_changed)
        top_form.addRow("Name", self.name_edit)
        self.dry_mass_kg = _spin(0.001, 1.0e6, decimals=3, step=10.0, value=config.dry_mass_kg if config else 100.0)
        self.dry_mass_kg.setToolTip(
            "Spacecraft mass WITHOUT propellant (propellant for any thruster below is tracked "
            "separately). Affects acceleration from any force (thrust, drag, SRP) -- a heavier "
            "spacecraft responds less to the same force."
        )
        top_form.addRow("Dry mass [kg]", self.dry_mass_kg)
        layout.addLayout(top_form)

        orbit_group = QGroupBox("Orbit initial condition")
        orbit_layout = QVBoxLayout(orbit_group)
        self.orbit_widget = OrbitIcWidget()
        if epoch_provider is not None:
            self.orbit_widget.set_epoch_provider(epoch_provider)
        orbit_layout.addWidget(self.orbit_widget)
        layout.addWidget(orbit_group)

        inertia_group = QGroupBox("Principal moments of inertia [kg*m^2] (off-diagonal terms fixed at 0)")
        inertia_group.setToolTip(
            "How the spacecraft's mass is distributed around its own body axes -- resistance to "
            "being rotated about each axis, the rotational analog of mass. A larger value on an "
            "axis means a slower response (and a larger commanded torque needed) for a given "
            "attitude maneuver about that axis. Assumed diagonal (a 'principal axis' body frame, "
            "no cross-coupling terms) -- the common simplifying assumption for a simple-shaped bus."
        )
        inertia_form = QFormLayout(inertia_group)
        inertia0 = config.inertia_kg_m2 if config else [10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0]
        self.ixx = _spin(0.001, 1.0e8, decimals=3, step=1.0, value=inertia0[0])
        self.iyy = _spin(0.001, 1.0e8, decimals=3, step=1.0, value=inertia0[4])
        self.izz = _spin(0.001, 1.0e8, decimals=3, step=1.0, value=inertia0[8])
        inertia_form.addRow("Ixx", self.ixx)
        inertia_form.addRow("Iyy", self.iyy)
        inertia_form.addRow("Izz", self.izz)
        self.gravity_gradient_check = QCheckBox("Enable gravity gradient torque")
        self.gravity_gradient_check.setToolTip(
            "Real torque from the central body's gravity acting across this spacecraft's own inertia "
            "(Basilisk's GravityGradientEffector). Usually negligible next to an active attitude "
            "controller's own torques, but real for a coasting (fsw_mode = None) or high-inertia spacecraft."
        )
        self.gravity_gradient_check.setChecked(config.enable_gravity_gradient if config else False)
        inertia_form.addRow(self.gravity_gradient_check)
        layout.addWidget(inertia_group)

        # Drag/SRP finally get a real editor here (Phase 5) -- previously
        # round-tripped only (see this module's docstring history): no UI
        # existed anywhere to actually SET them, even though engine.service
        # has wired them into the physics since Phase 4. Needed in
        # particular for Scenario.simulation_mode's "orbit_only" cannonball
        # use case, where drag_area_m2/srp_area_m2 ARE the spacecraft's
        # only physical shape.
        drag_srp_group = QGroupBox("Atmospheric drag / solar radiation pressure")
        drag_srp_form = QFormLayout(drag_srp_group)
        self.enable_drag_check = QCheckBox("Enable atmospheric drag")
        self.enable_drag_check.setToolTip(
            "Adds real air-drag deceleration (Basilisk's exponential or NRLMSISE-00 atmosphere "
            "model, set in Propagation setup) -- the dominant force shrinking a LEO orbit over "
            "time. Negligible above ~800-1000 km; matters a lot below ~500 km. Turning this on "
            "with no station-keeping configured means the orbit will genuinely decay over the run."
        )
        self.enable_drag_check.setChecked(config.enable_drag if config else False)
        drag_srp_form.addRow(self.enable_drag_check)
        self.drag_coeff = _spin(0.1, 10.0, decimals=3, step=0.1,
                                 value=config.drag_coeff if config else SpacecraftConfig.drag_coeff)
        self.drag_coeff.setToolTip(
            "Dimensionless drag coefficient (Cd) -- how efficiently the spacecraft's shape "
            "converts the local atmosphere into drag force. ~2.0-2.2 is a common default for a "
            "generic convex bus; a real value needs a shape-specific aerodynamic analysis."
        )
        drag_srp_form.addRow("Drag coefficient [-]", self.drag_coeff)
        self.drag_area_m2 = _spin(0.0001, 1.0e6, decimals=4, step=0.1,
                                   value=config.drag_area_m2 if config else SpacecraftConfig.drag_area_m2)
        self.drag_area_m2.setToolTip(
            "Cross-sectional area facing the oncoming atmosphere -- a flat-plate approximation, "
            "not the spacecraft's full surface area. Bigger = more drag force = faster orbit decay."
        )
        drag_srp_form.addRow("Drag cross-section area [m^2]", self.drag_area_m2)
        self.enable_srp_check = QCheckBox("Enable solar radiation pressure")
        self.enable_srp_check.setToolTip(
            "Adds the real, small push from sunlight photons reflecting/absorbing off the "
            "spacecraft (Basilisk's radiationPressure model) -- automatically zero while the "
            "spacecraft is in Earth's shadow. Usually a minor effect next to drag in LEO, but "
            "the dominant long-term perturbation at GEO and beyond, where drag is negligible."
        )
        self.enable_srp_check.setChecked(config.enable_srp if config else False)
        drag_srp_form.addRow(self.enable_srp_check)
        self.srp_coeff = _spin(0.0, 3.0, decimals=3, step=0.1,
                                value=config.srp_coeff if config else SpacecraftConfig.srp_coeff)
        self.srp_coeff.setToolTip(
            "Reflectivity coefficient (Cr): 1.0 = a perfectly absorbing (black) surface, 2.0 = "
            "a perfectly reflecting (mirror) surface -- a reflecting surface feels roughly twice "
            "the force for the same cross-section, since the photon's momentum reverses instead "
            "of just stopping."
        )
        drag_srp_form.addRow("SRP reflectivity coefficient [-]", self.srp_coeff)
        self.srp_area_m2 = _spin(0.0001, 1.0e6, decimals=4, step=0.1,
                                  value=config.srp_area_m2 if config else SpacecraftConfig.srp_area_m2)
        self.srp_area_m2.setToolTip(
            "Cross-sectional area facing the Sun -- a flat-plate approximation, same idea as the "
            "drag area above but for sunlight pressure instead of atmosphere."
        )
        drag_srp_form.addRow("SRP cross-section area [m^2]", self.srp_area_m2)
        layout.addWidget(drag_srp_group)

        facet_group = QGroupBox("Surface facets (attitude-dependent drag / SRP)")
        facet_group.setToolTip("When facets are listed, enabled drag and SRP use them instead of the areas "
                               "above. Needs full-attitude mode.")
        facet_layout = QVBoxLayout(facet_group)
        facet_hint = QLabel("Optional: drag and SRP then use these plates, follow the attitude and add torque.")
        facet_hint.setWordWrap(True)
        facet_layout.addWidget(facet_hint)
        self.facet_table = FacetTableWidget()
        self.facet_table.from_list(config.facets if config else [])
        facet_layout.addWidget(self.facet_table)
        layout.addWidget(facet_group)

        attitude_group = QGroupBox("Initial attitude / body rate")
        attitude_group.setToolTip(
            "The spacecraft's starting orientation and spin rate at the epoch -- only matters "
            "if 'Full attitude' mode is selected (rotational dynamics aren't simulated in "
            "'Orbit only' mode, so these fields are ignored there)."
        )
        attitude_form = QFormLayout(attitude_group)
        sigma0 = config.sigma_bn_init if config else [0.0, 0.0, 0.0]
        omega0 = config.omega_bn_b_init_rad_s if config else [0.0, 0.0, 0.0]
        self.sigma1 = _spin(-1.0, 1.0, decimals=6, step=0.01, value=sigma0[0])
        self.sigma2 = _spin(-1.0, 1.0, decimals=6, step=0.01, value=sigma0[1])
        self.sigma3 = _spin(-1.0, 1.0, decimals=6, step=0.01, value=sigma0[2])
        self.omega1 = _spin(-10.0, 10.0, decimals=6, step=0.001, value=omega0[0])
        self.omega2 = _spin(-10.0, 10.0, decimals=6, step=0.001, value=omega0[1])
        self.omega3 = _spin(-10.0, 10.0, decimals=6, step=0.001, value=omega0[2])
        _sigma_tip = (
            "Starting attitude, as a Modified Rodrigues Parameter (MRP) set -- Basilisk's own "
            "compact 3-number attitude representation (no gimbal lock, unlike Euler angles; no "
            "redundant 4th component, unlike quaternions). All zeros means the body frame starts "
            "exactly aligned with the inertial frame. A magnitude close to 1 means close to a "
            "180 deg rotation; MRPs switch to an equivalent 'shadow set' past that to stay "
            "numerically well-behaved, which is why the range here is capped at +/-1."
        )
        for box in (self.sigma1, self.sigma2, self.sigma3):
            box.setToolTip(_sigma_tip)
        _omega_tip = (
            "Starting angular velocity about each BODY axis (not inertial) -- how fast the "
            "spacecraft is tumbling/spinning at the epoch. All zeros means it starts perfectly "
            "at rest relative to inertial space. A nonzero value here is exactly how a "
            "'detumble' scenario is set up: start fast, watch the chosen FSW mode slow it down."
        )
        for box in (self.omega1, self.omega2, self.omega3):
            box.setToolTip(_omega_tip)
        attitude_form.addRow("sigma_BN [-] (MRP, body B relative to EME2000 N)",
                              _hbox(self.sigma1, self.sigma2, self.sigma3))
        attitude_form.addRow("omega_BN_B [rad/s] (body frame B)",
                              _hbox(self.omega1, self.omega2, self.omega3))
        layout.addWidget(attitude_group)

        if config is not None:
            self.orbit_widget.from_dataclass(config.orbit)

        tabs.addTab(_scrollable(orbit_tab), "Orbit / mass")

        # -- Sensors / actuators tab (Phase 2) --------------------------------
        sensors_tab = QWidget()
        sensors_layout = QVBoxLayout(sensors_tab)
        sensors_layout.addWidget(QLabel("Sensors"))
        self.sensor_list = SensorActuatorListWidget(SensorConfig, SUPPORTED_SENSOR_KINDS)
        sensors_layout.addWidget(self.sensor_list)
        sensors_layout.addWidget(QLabel("Actuators"))
        self.actuator_list = SensorActuatorListWidget(ActuatorConfig, SUPPORTED_ACTUATOR_KINDS)
        sensors_layout.addWidget(self.actuator_list)
        if config is not None:
            self.sensor_list.from_list(config.sensors)
            self.actuator_list.from_list(config.actuators)
        self._sensors_tab_index = tabs.addTab(_scrollable(sensors_tab), "Sensors / actuators")

        # -- Attitude control (FSW) tab (Phase 2) -----------------------------
        fsw_tab = QWidget()
        fsw_layout = QVBoxLayout(fsw_tab)
        fsw_form = QFormLayout()
        self.fsw_mode_combo = ComboBox()
        self.fsw_mode_combo.setToolTip(
            "Which attitude-control GUIDANCE law this spacecraft runs -- what direction it "
            "tries to point, computed fresh every tick from the real simulated state (never a "
            "fixed, pre-scripted attitude). 'None' means no active control: the spacecraft "
            "coasts under whatever torques are actually turned on (e.g. gravity gradient) with "
            "no corrective response. The hint text below updates with what the selected mode "
            "needs in 'FSW params' underneath."
        )
        self.fsw_mode_combo.addItem(_FSW_MODE_NONE_LABEL, userData=None)
        for mode in SUPPORTED_FSW_MODES:
            self.fsw_mode_combo.addItem(mode, userData=mode)
        if config is not None and config.fsw_mode is not None:
            index = self.fsw_mode_combo.findData(config.fsw_mode)
            if index >= 0:
                self.fsw_mode_combo.setCurrentIndex(index)
        self.fsw_mode_combo.currentIndexChanged.connect(self._on_fsw_mode_changed)
        fsw_form.addRow("FSW mode", self.fsw_mode_combo)
        fsw_layout.addLayout(fsw_form)

        self.fsw_hint_label = QLabel(_fsw_hint_text(self.fsw_mode_combo.currentData()))
        self.fsw_hint_label.setWordWrap(True)
        self.fsw_hint_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        fsw_form.addRow("", self.fsw_hint_label)

        # Guidance parameters for the selected mode: one labelled row each
        # (real user feedback: the old bullet list over a raw JSON box was
        # "bad UI/UX").
        self.fsw_params_group = QGroupBox("Pointing parameters")
        fsw_params_layout = QVBoxLayout(self.fsw_params_group)
        fsw_params_header = QHBoxLayout()
        fsw_params_legend = QLabel("Unticked parameters use the default. Hover a name for details.")
        fsw_params_legend.setStyleSheet(f"color: {PALETTE['text_muted']};")
        fsw_params_header.addWidget(fsw_params_legend, 1)
        self.fsw_reset_template_button = QPushButton("Reset to template")
        self.fsw_reset_template_button.setToolTip("Put this mode's parameters back to a working example.")
        self.fsw_reset_template_button.clicked.connect(self._on_fsw_reset_template)
        fsw_params_header.addWidget(self.fsw_reset_template_button)
        fsw_params_layout.addLayout(fsw_params_header)
        self.fsw_param_form = ParamForm()
        fsw_params_layout.addWidget(self.fsw_param_form)
        fsw_layout.addWidget(self.fsw_params_group)
        self._current_fsw_mode = self.fsw_mode_combo.currentData()
        self._fsw_mode_params: dict = {}
        initial_fsw_params = (dict(config.fsw_params) if config
                              else self._fsw_default_params(self._current_fsw_mode))
        self._build_fsw_form(self._current_fsw_mode, initial_fsw_params)

        self.control_group = QGroupBox("Control gains (MRP feedback)")
        control_layout = QVBoxLayout(self.control_group)
        control_legend = QLabel("Unticked gains use the defaults (K 3.5, P 30, integral off).")
        control_legend.setStyleSheet(f"color: {PALETTE['text_muted']};")
        control_layout.addWidget(control_legend)
        self.control_param_form = ParamForm()
        self.control_param_form.set_specs(_CONTROL_PARAM_SPECS, dict(config.control_params) if config else {})
        control_layout.addWidget(self.control_param_form)
        fsw_layout.addWidget(self.control_group)
        fsw_layout.addStretch(1)

        # comms_pointing (Phase 6 audit fix): previously had NO editor
        # anywhere in this dialog -- opening then OK'ing a spacecraft that
        # already had it set (e.g. template 19's "leo-comms-1") silently
        # DELETED it, since to_dataclass() below always rebuilds a fresh
        # SpacecraftConfig from widget state alone. Placed on this tab
        # (not Power) because its real conflict is with fsw_mode above --
        # comms_pointing OWNS attitude control via its own internal
        # Sun-pointing/ground-station-pointing arbitrator, so the two are
        # mutually exclusive (Scenario.validate() enforces this with a
        # specific error message, surfaced as-is by to_dataclass()'s own
        # config.validate() call rather than duplicated here -- same
        # not-cross-checked-here convention as every other group on this
        # dialog, e.g. momentum_dumping's actuator-kind requirement).
        cp0 = config.comms_pointing if config else None
        self.comms_pointing_group = QGroupBox("Comms pointing: Sun-pointing, ground station when in view")
        self.comms_pointing_group.setCheckable(True)
        self.comms_pointing_group.setToolTip(
            "Checking this ON makes this spacecraft automatically switch its attitude between "
            "Sun-pointing (normal operations) and ground-station-pointing (whenever it's in "
            "real, simulated access to the ground station below) -- it builds and owns its own "
            "guidance internally, so 'FSW mode' above must be left at '(none)'. If 'Comms "
            "power' below is > 0, this spacecraft's 'Power budget' (Power / propulsion / link "
            "budget tab) must also be configured."
        )
        self.comms_pointing_group.setChecked(cp0 is not None)
        # Collapsed to its title while unticked, so an unused group doesn't
        # fill the tab with disabled rows.
        cp_outer = QVBoxLayout(self.comms_pointing_group)
        self._cp_body = QWidget()
        self._cp_body.setObjectName("cpBody")
        self._cp_body.setStyleSheet("QWidget#cpBody { background: transparent; }")
        cp_outer.addWidget(self._cp_body)
        cp_form = QFormLayout(self._cp_body)
        cp_form.setContentsMargins(0, 0, 0, 0)
        self.comms_pointing_group.toggled.connect(self._cp_body.setVisible)
        self._cp_body.setVisible(cp0 is not None)

        self.cp_ground_station_combo = ComboBox()
        self.cp_ground_station_combo.setToolTip(
            "The ground station this spacecraft points its antenna at whenever it has real, "
            "simulated access to it (engine.service's own groundLocation.GroundLocation access "
            "state -- never a fixed, manually-specified time window)."
        )
        if self._ground_station_names:
            for gs_name in self._ground_station_names:
                self.cp_ground_station_combo.addItem(gs_name, userData=gs_name)
        else:
            self.cp_ground_station_combo.addItem("(add a ground station to this scenario first)", userData=None)
            self.cp_ground_station_combo.setEnabled(False)
        if cp0 is not None:
            gs_index = self.cp_ground_station_combo.findData(cp0.target_ground_station)
            if gs_index >= 0:
                self.cp_ground_station_combo.setCurrentIndex(gs_index)
            else:
                # Same stale-reference fallback as pk_chief_combo below --
                # cp0.target_ground_station doesn't match any current
                # ground station name (e.g. renamed/removed since this
                # config was saved). Surface it as its own selectable entry
                # so to_dataclass() still round-trips it (and validate()
                # catches it as a real error) unless the user picks a
                # different one.
                self.cp_ground_station_combo.addItem(
                    f"{cp0.target_ground_station} (not found in this scenario)",
                    userData=cp0.target_ground_station,
                )
                self.cp_ground_station_combo.setCurrentIndex(self.cp_ground_station_combo.count() - 1)
        cp_form.addRow("Ground station", self.cp_ground_station_combo)

        cp_boresight0 = cp0.antenna_boresight_b if cp0 else [0.0, 0.0, 1.0]
        self.cp_boresight_x = _spin(-1.0, 1.0, decimals=4, step=0.1, value=cp_boresight0[0])
        self.cp_boresight_y = _spin(-1.0, 1.0, decimals=4, step=0.1, value=cp_boresight0[1])
        self.cp_boresight_z = _spin(-1.0, 1.0, decimals=4, step=0.1, value=cp_boresight0[2])
        _cp_boresight_tip = (
            "Unit vector (body frame) of the antenna's own pointing direction -- this is the "
            "axis actually aimed at the ground station while comms-pointing mode is active."
        )
        for box in (self.cp_boresight_x, self.cp_boresight_y, self.cp_boresight_z):
            box.setToolTip(_cp_boresight_tip)
        for axis, box in zip("xyz", (self.cp_boresight_x, self.cp_boresight_y, self.cp_boresight_z)):
            box.setPrefix(f"{axis}  ")
        cp_form.addRow("Antenna boresight (body frame B)",
                        _hbox(self.cp_boresight_x, self.cp_boresight_y, self.cp_boresight_z))

        # sun_pointing_axis_b is Optional with a real semantic default
        # (falls back to the power panel's own normal, or [0,0,1] with no
        # power budget configured) -- same "tri-state: a checkbox gates
        # whether the typed value is even used" idiom as viz_model_group's
        # own isChecked() gating _viz_model_to_dataclass_path() below.
        self.cp_sun_axis_default_check = QCheckBox("Sun axis: use the solar-panel normal")
        self.cp_sun_axis_default_check.setChecked(cp0 is None or cp0.sun_pointing_axis_b is None)
        self.cp_sun_axis_default_check.toggled.connect(self._on_cp_sun_axis_default_toggled)
        cp_form.addRow(self.cp_sun_axis_default_check)
        cp_sun_axis0 = (cp0.sun_pointing_axis_b if cp0 and cp0.sun_pointing_axis_b else [0.0, 0.0, 1.0])
        self.cp_sun_axis_x = _spin(-1.0, 1.0, decimals=4, step=0.1, value=cp_sun_axis0[0])
        self.cp_sun_axis_y = _spin(-1.0, 1.0, decimals=4, step=0.1, value=cp_sun_axis0[1])
        self.cp_sun_axis_z = _spin(-1.0, 1.0, decimals=4, step=0.1, value=cp_sun_axis0[2])
        _cp_sun_axis_tip = (
            "Unit vector (body frame) aimed at the Sun during Sun-pointing mode. Only used when "
            "the checkbox above is OFF -- set this to point a DIFFERENT body axis at the Sun "
            "than the power panel's own normal."
        )
        for box in (self.cp_sun_axis_x, self.cp_sun_axis_y, self.cp_sun_axis_z):
            box.setToolTip(_cp_sun_axis_tip)
        for axis, box in zip("xyz", (self.cp_sun_axis_x, self.cp_sun_axis_y, self.cp_sun_axis_z)):
            box.setPrefix(f"{axis}  ")
        cp_form.addRow("Axis to point at the Sun (body frame B)",
                        _hbox(self.cp_sun_axis_x, self.cp_sun_axis_y, self.cp_sun_axis_z))
        self._on_cp_sun_axis_default_toggled(self.cp_sun_axis_default_check.isChecked())

        self.cp_comms_power_w = _spin(0.0, 1.0e5, decimals=2, step=1.0,
                                       value=cp0.comms_power_w if cp0 else 0.0)
        self.cp_comms_power_w.setToolTip(
            "Additional electrical power drawn (on top of 'Power budget' bus idle power) for "
            "exactly as long as ground-station-pointing mode is actually active -- a stand-in "
            "for a downlink transmitter's own power draw. Leave at 0 to model only the attitude "
            "-switching behavior with no extra power draw."
        )
        self.cp_comms_power_w.setSuffix(" W")
        cp_form.addRow("Extra power while pointing", self.cp_comms_power_w)
        # Directly under the FSW mode row, not after the two JSON editors:
        # comms_pointing is the ALTERNATIVE to an FSW mode, and at the
        # bottom of the tab it sat below the fold even when it was the
        # spacecraft's actual, active attitude control (e.g. template 19).
        fsw_layout.insertWidget(fsw_layout.indexOf(self.fsw_params_group), self.comms_pointing_group)
        self.comms_pointing_group.toggled.connect(self._refresh_fsw_hint)
        self._refresh_fsw_hint()

        self._fsw_tab_index = tabs.addTab(_scrollable(fsw_tab), "Attitude control")

        # -- Power budget / RF link budget tab (Phase 4) ----------------------
        # Both are OFF by default (unchecked group box) -- turning one on is
        # the only input needed beyond the numbers themselves; engine.service
        # (power) / engine.link_budget (RF) do the rest. See PowerConfig's
        # and RFLinkConfig's docstrings for exactly what each does and
        # doesn't affect.
        power_tab = QWidget()
        power_layout = QVBoxLayout(power_tab)

        power0 = config.power if config else None
        self.power_group = QGroupBox("Power budget (solar panel + battery)")
        self.power_group.setCheckable(True)
        self.power_group.setToolTip(
            "Checking this ON simulates a real power system for this spacecraft: a solar panel "
            "whose generation depends on the ACTUAL simulated panel-to-Sun angle and eclipse "
            "state each tick (not an estimate), feeding a battery that other loads (bus power, "
            "and comms power if comms_pointing is configured) draw down. Needed for the "
            "Mission Dashboard/Results tab's battery-charge series to mean anything."
        )
        self.power_group.setChecked(power0 is not None)
        power_form = QFormLayout(self.power_group)
        self.panel_area_m2 = _spin(0.001, 1.0e4, decimals=3, step=0.1,
                                    value=power0.panel_area_m2 if power0 else 1.2)
        self.panel_area_m2.setToolTip("Total deployed solar panel area. Bigger = more generated power.")
        self.panel_efficiency = _spin(0.001, 1.0, decimals=4, step=0.01,
                                       value=power0.panel_efficiency if power0 else 0.29)
        self.panel_efficiency.setToolTip(
            "Fraction of incident sunlight actually converted to electrical power (0-1). "
            "~0.28-0.30 is typical for real triple-junction space-grade solar cells."
        )
        panel_normal0 = power0.panel_normal_b if power0 else [0.0, 0.0, 1.0]
        self.panel_normal_x = _spin(-1.0, 1.0, decimals=4, step=0.1, value=panel_normal0[0])
        self.panel_normal_y = _spin(-1.0, 1.0, decimals=4, step=0.1, value=panel_normal0[1])
        self.panel_normal_z = _spin(-1.0, 1.0, decimals=4, step=0.1, value=panel_normal0[2])
        _panel_normal_tip = (
            "Unit vector (in the spacecraft BODY frame) the panel's flat face points along. "
            "Generated power depends on the real angle between this axis and the actual Sun "
            "direction each tick -- straight at the Sun generates the most power, edge-on "
            "generates none. This is also the natural axis for Sun-pointing/Sun-safe FSW modes "
            "to aim at the Sun."
        )
        for box in (self.panel_normal_x, self.panel_normal_y, self.panel_normal_z):
            box.setToolTip(_panel_normal_tip)
        self.bus_idle_power_w = _spin(0.0, 1.0e5, decimals=2, step=1.0,
                                       value=power0.bus_idle_power_w if power0 else PowerConfig.bus_idle_power_w)
        self.bus_idle_power_w.setToolTip(
            "A constant always-on load (avionics/thermal/ADCS housekeeping) that drains the "
            "battery continuously, day and night, regardless of what the panel is generating."
        )
        self.battery_capacity_wh = _spin(0.001, 1.0e6, decimals=2, step=10.0,
                                          value=power0.battery_capacity_wh if power0
                                          else PowerConfig.battery_capacity_wh)
        self.battery_capacity_wh.setToolTip(
            "Total energy the battery can hold. A smaller capacity means the state-of-charge "
            "swings faster and further during each eclipse -- watch for it hitting 0% in the "
            "Results tab if this is set too small for the load."
        )
        self.battery_initial_soc = _spin(0.0, 1.0, decimals=4, step=0.05,
                                          value=power0.battery_initial_soc if power0
                                          else PowerConfig.battery_initial_soc)
        self.battery_initial_soc.setToolTip(
            "Battery charge level at the epoch, as a fraction of capacity above (1.0 = fully "
            "charged, 0.0 = fully depleted). Only affects the starting point -- the simulated "
            "charge/discharge cycle afterward is entirely real generation minus real loads."
        )
        power_form.addRow("Panel area [m^2]", self.panel_area_m2)
        power_form.addRow("Panel efficiency [-]", self.panel_efficiency)
        power_form.addRow("Panel normal (body frame, 3 components)",
                           _hbox(self.panel_normal_x, self.panel_normal_y, self.panel_normal_z))
        power_form.addRow("Bus idle power [W]", self.bus_idle_power_w)
        power_form.addRow("Battery capacity [W*hr]", self.battery_capacity_wh)
        power_form.addRow("Battery initial state of charge [-]", self.battery_initial_soc)
        power_layout.addWidget(self.power_group)

        sk0 = config.station_keeping if config else None
        self.station_keeping_group = QGroupBox("Station keeping (altitude maintenance, delta-V + fuel tracking)")
        self.station_keeping_group.setCheckable(True)
        self.station_keeping_group.setToolTip(
            "Checking this ON adds an automatic controller that fires a low-thrust reboost burn "
            "whenever this spacecraft's altitude decays too far below target, holding it there "
            "and tracking the delta-V/propellant spent doing so. Needs something to actually be "
            "shrinking the orbit to have any visible effect -- turn on 'Enable atmospheric drag' "
            "above too, or this will simply never fire."
        )
        self.station_keeping_group.setChecked(sk0 is not None)
        sk_form = QFormLayout(self.station_keeping_group)
        self.sk_target_altitude_km = _spin(0.001, 1.0e6, decimals=3, step=10.0,
                                            value=sk0.target_altitude_km if sk0 else 500.0)
        self.sk_target_altitude_km.setToolTip(
            "Altitude above the central body's surface this controller tries to hold the "
            "spacecraft at, once decay has pulled it down by the deadband below."
        )
        self.sk_deadband_km = _spin(0.001, 1.0e5, decimals=3, step=0.5, value=sk0.deadband_km if sk0 else 1.0)
        self.sk_deadband_km.setToolTip(
            "How far altitude is allowed to decay below the target before a reboost burn "
            "starts (simple deadband/hysteresis control, not a continuous correction). "
            "Smaller = more frequent, smaller burns; larger = the orbit sags further between "
            "burns, closer to sawtooth decay/reboost."
        )
        self.sk_thrust_n = _spin(1.0e-6, 1.0e4, decimals=6, step=0.001, value=sk0.thrust_n if sk0 else 0.01)
        self.sk_thrust_n.setToolTip(
            "Reboost thruster's thrust level while actively firing (prograde, along the "
            "velocity direction). Higher thrust restores altitude faster but burns propellant "
            "faster for the same delta-V (see Isp below for the actual trade)."
        )
        self.sk_isp_s = _spin(1.0, 1.0e5, decimals=1, step=10.0, value=sk0.isp_s if sk0 else 1500.0)
        self.sk_isp_s.setToolTip(
            "Specific impulse -- the thruster's propellant efficiency (effective exhaust "
            "velocity / g0). Higher Isp means less propellant burned for the same delta-V "
            "(~1500-2000 s is typical for an electric thruster; ~200-300 s for chemical)."
        )
        self.sk_propellant_kg = _spin(0.0, 1.0e5, decimals=3, step=0.1, value=sk0.propellant_kg if sk0 else 2.0)
        self.sk_propellant_kg.setToolTip(
            "Propellant mass available at the epoch, burned down by the rocket equation as "
            "reboost burns fire. Once depleted, this controller stops firing and the orbit is "
            "free to decay -- watch for that in the Results tab if the run is long enough."
        )
        self.sk_eclipse_sunlit_threshold = _spin(0.001, 1.0, decimals=4, step=0.01,
                                                   value=sk0.eclipse_sunlit_threshold if sk0 else 0.99)
        self.sk_eclipse_sunlit_threshold.setToolTip(
            "The real simulated shadow (eclipse) factor must be at or above this before a "
            "reboost burn is allowed to fire -- a stand-in for a solar-electric bus that can't "
            "run its thruster off battery alone during eclipse. 1.0 = must be in full sunlight; "
            "lower values tolerate partial shadow (e.g. penumbra)."
        )
        self.sk_min_on_time_s = _spin(0.0, 86400.0, decimals=1, step=10.0,
                                      value=sk0.min_on_time_s if sk0 else 0.0)
        self.sk_min_on_time_s.setToolTip(
            "Shortest firing this thruster can make [s] -- its minimum impulse bit is thrust x this. "
            "A firing, once started, always lasts at least this long; a correction needing less than "
            "half of one minimum firing is skipped, and one needing more is rounded up to it. 0 = an "
            "ideal thruster. Also applies to phasing-keeping burns on this spacecraft (same thruster). "
            "Electric thrusters are typically minutes, cold-gas/chemical ones milliseconds."
        )
        self.sk_eccentricity_neutral_check = QCheckBox("Eccentricity-neutral burns")
        self.sk_eccentricity_neutral_check.setChecked(bool(sk0.eccentricity_neutral_burns) if sk0 else False)
        self.sk_eccentricity_neutral_check.setToolTip(
            "Skips just enough sunlit arc that a long, eclipse-interrupted burn doesn't change the "
            "orbit's eccentricity (without this, a 15 km reboost of the formation template changed it "
            "by ~1e-3, more than doubling it). Burns take longer, for the same delta-V."
        )
        sk_form.addRow("Target altitude [km]", self.sk_target_altitude_km)
        sk_form.addRow("Deadband below target [km]", self.sk_deadband_km)
        sk_form.addRow("Reboost thrust [N]", self.sk_thrust_n)
        sk_form.addRow("Reboost thruster Isp [s]", self.sk_isp_s)
        sk_form.addRow("Propellant available [kg]", self.sk_propellant_kg)
        sk_form.addRow("Eclipse sunlit threshold [-]", self.sk_eclipse_sunlit_threshold)
        sk_form.addRow("Minimum thruster on-time [s]", self.sk_min_on_time_s)
        sk_form.addRow(self.sk_eccentricity_neutral_check)
        power_layout.addWidget(self.station_keeping_group)

        geo0 = config.geo_station_keeping if config else None
        self.geo_station_keeping_group = QGroupBox("GEO station keeping (east-west and north-south boxes)")
        self.geo_station_keeping_group.setCheckable(True)
        self.geo_station_keeping_group.setToolTip(
            "Keeps a geostationary satellite in its slot: along-track burns hold the longitude in its box, "
            "burns at the nodes keep the inclination under the limit. Earth only; replaces station keeping."
        )
        self.geo_station_keeping_group.setChecked(geo0 is not None)
        geo_form = QFormLayout(self.geo_station_keeping_group)
        self.geo_longitude_deg = _spin(-180.0, 360.0, decimals=3, step=1.0,
                                       value=geo0.target_longitude_deg if geo0 else 10.0)
        self.geo_longitude_deg.setToolTip("East longitude of the slot.")
        self.geo_deadband_deg = _spin(0.001, 5.0, decimals=3, step=0.01,
                                      value=geo0.longitude_deadband_deg if geo0 else 0.05)
        self.geo_deadband_deg.setToolTip("Half-width of the longitude box. Smaller = more east-west burns.")
        self.geo_inclination_max_deg = _spin(0.001, 10.0, decimals=3, step=0.01,
                                             value=geo0.inclination_max_deg if geo0 else 0.05)
        self.geo_inclination_max_deg.setToolTip("A north-south burn fires at the next node once this is passed.")
        self.geo_thrust_n = _spin(1.0e-4, 1.0e3, decimals=4, step=0.5, value=geo0.thrust_n if geo0 else 1.0)
        self.geo_isp_s = _spin(1.0, 1.0e5, decimals=1, step=10.0, value=geo0.isp_s if geo0 else 220.0)
        self.geo_isp_s.setToolTip("~220 s for hydrazine; electric thrusters are 1500 s and more.")
        self.geo_propellant_kg = _spin(0.0, 1.0e5, decimals=3, step=1.0,
                                       value=geo0.propellant_kg if geo0 else 50.0)
        geo_form.addRow("Slot longitude (east) [deg]", self.geo_longitude_deg)
        geo_form.addRow("Longitude box half-width [deg]", self.geo_deadband_deg)
        geo_form.addRow("Inclination limit [deg]", self.geo_inclination_max_deg)
        geo_form.addRow("Thrust [N]", self.geo_thrust_n)
        geo_form.addRow("Thruster Isp [s]", self.geo_isp_s)
        geo_form.addRow("Propellant available [kg]", self.geo_propellant_kg)
        power_layout.addWidget(self.geo_station_keeping_group)

        # Independent of station keeping above -- its own propellant
        # budget/tank (see ConstantThrustConfig's docstring). Available in
        # EITHER simulation mode (not restricted to orbit_only): a
        # continuous, always-on thrust with a fixed direction in a
        # ROTATING orbit frame (VNB or RTN, re-evaluated every tick), for
        # delta-V/propellant budgeting without needing a burn trigger.
        ct0 = config.constant_thrust if config else None
        self.constant_thrust_group = QGroupBox("Constant thrust (continuous, orbit-frame-relative)")
        self.constant_thrust_group.setCheckable(True)
        self.constant_thrust_group.setToolTip(
            "Checking this ON fires a continuous, always-on thruster whose direction is fixed "
            "relative to the orbit (not a fixed inertial direction, so it doesn't drift as the "
            "spacecraft moves) -- e.g. a constant prograde or out-of-plane push, with its own "
            "independent delta-V/propellant budget. Works in either simulation mode (no "
            "attitude model needed), unlike the station-keeping controller above."
        )
        self.constant_thrust_group.setChecked(ct0 is not None)
        ct_form = QFormLayout(self.constant_thrust_group)
        self.ct_frame_combo = ComboBox()
        self.ct_frame_combo.addItems(list(SUPPORTED_THRUST_FRAMES))
        self.ct_frame_combo.setToolTip(
            "VNB: V=velocity direction, N=orbit normal, B=V x N.\n"
            "RTN: R=radial (outward), T=N x R (in-plane, ⊥ R), N=orbit normal.\n"
            "Re-evaluated every tick from the spacecraft's current state."
        )
        if ct0 is not None:
            index = self.ct_frame_combo.findText(ct0.frame)
            if index >= 0:
                self.ct_frame_combo.setCurrentIndex(index)
        ct_form.addRow("Frame", self.ct_frame_combo)
        ct_dir0 = ct0.direction if ct0 else [1.0, 0.0, 0.0]
        self.ct_dir_x = _spin(-1.0, 1.0, decimals=6, step=0.1, value=ct_dir0[0])
        self.ct_dir_y = _spin(-1.0, 1.0, decimals=6, step=0.1, value=ct_dir0[1])
        self.ct_dir_z = _spin(-1.0, 1.0, decimals=6, step=0.1, value=ct_dir0[2])
        _ct_dir_tip = (
            "Unit vector giving the thrust direction, in the rotating Frame selected above -- "
            "re-evaluated every tick from the spacecraft's current state, so this stays e.g. "
            "'always prograde' rather than drifting the way a fixed inertial vector would. "
            "[1,0,0] in VNB is pure prograde (raises the orbit); [0,0,1] in either frame is "
            "pure out-of-plane (changes inclination/RAAN, not altitude)."
        )
        for box in (self.ct_dir_x, self.ct_dir_y, self.ct_dir_z):
            box.setToolTip(_ct_dir_tip)
        ct_form.addRow("Direction [-] (3 components, in Frame above)",
                        _hbox(self.ct_dir_x, self.ct_dir_y, self.ct_dir_z))
        self.ct_thrust_n = _spin(1.0e-6, 1.0e4, decimals=6, step=0.001, value=ct0.thrust_n if ct0 else 0.01)
        self.ct_thrust_n.setToolTip("Constant thrust magnitude, always firing in Direction above.")
        ct_form.addRow("Thrust [N]", self.ct_thrust_n)
        self.ct_isp_s = _spin(1.0, 1.0e5, decimals=1, step=10.0, value=ct0.isp_s if ct0 else 1500.0)
        self.ct_isp_s.setToolTip(
            "Specific impulse -- propellant efficiency (effective exhaust velocity / g0). "
            "Higher Isp burns less propellant for the same thrust/duration."
        )
        ct_form.addRow("Thruster Isp [s]", self.ct_isp_s)
        self.ct_propellant_kg = _spin(0.0, 1.0e5, decimals=3, step=0.1, value=ct0.propellant_kg if ct0 else 2.0)
        self.ct_propellant_kg.setToolTip(
            "Propellant mass available at the epoch -- once depleted (by the rocket equation, "
            "tracked every tick), this thruster stops firing on its own."
        )
        ct_form.addRow("Propellant available [kg]", self.ct_propellant_kg)
        power_layout.addWidget(self.constant_thrust_group)

        # Requires station keeping above -- shares one physical thruster/tank
        # (see schema.scenario.PhasingKeepingConfig's docstring), so this has
        # no thrust/Isp/propellant fields of its own.
        pk0 = config.phasing_keeping if config else None
        self.phasing_keeping_group = QGroupBox("Phasing keeping (constellation-wide, vs. a chief spacecraft)")
        self.phasing_keeping_group.setCheckable(True)
        self.phasing_keeping_group.setToolTip(
            "Checking this ON holds this spacecraft's along-track spacing from a 'chief' "
            "spacecraft at a target distance -- by default via an occasional drift-orbit maneuver "
            "(a small, temporary altitude offset, let it drift, then a restoring burn), or by one "
            "of Basilisk's formation-flying control laws (see 'Control law') -- useful for "
            "spreading satellites evenly around the SAME orbital plane, e.g. a Walker "
            "constellation. REQUIRES 'Station keeping' above to also be enabled: both share "
            "one physical thruster/propellant tank, with altitude-keeping taking priority if "
            "both want to fire on the same tick. While this is on, that station keeping holds "
            "altitude RELATIVE TO THE CHIEF (it mirrors the chief's reboosts; its target "
            "altitude is ignored and its deadband is measured below the chief); with a Basilisk "
            "law it never fires on its own, the law follows the chief instead. Give the "
            "chief its own station keeping. Needs a chief spacecraft in the same scenario "
            "sharing this one's orbital plane and altitude."
        )
        self.phasing_keeping_group.setChecked(pk0 is not None)
        pk_form = QFormLayout(self.phasing_keeping_group)

        self.pk_chief_combo = ComboBox()
        self.pk_chief_combo.setToolTip(
            "The reference spacecraft this one's along-track spacing is measured and held "
            "relative to. Must share this spacecraft's orbital plane and altitude for the "
            "measurement to mean anything."
        )
        if self._other_spacecraft_names:
            for other_name in self._other_spacecraft_names:
                self.pk_chief_combo.addItem(other_name, userData=other_name)
        else:
            self.pk_chief_combo.addItem("(add another spacecraft to this scenario first)", userData=None)
            self.pk_chief_combo.setEnabled(False)
        pk_form.addRow("Chief spacecraft", self.pk_chief_combo)
        self._pk_form = pk_form

        # engine.formation_control: Basilisk's own formation-flying laws as
        # alternatives to the drift-orbit controller.
        self.pk_control_law_combo = ComboBox()
        for label, law in (("Drift orbit (occasional burns)", "drift_orbit"),
                           ("Mean orbital elements (Basilisk meanOEFeedback)", "mean_oe"),
                           ("Hill-frame PD (Basilisk hillFrameRelativeControl)", "hill_pd")):
            self.pk_control_law_combo.addItem(label, userData=law)
        self.pk_control_law_combo.setToolTip(
            "Drift orbit: a few planned burns when the separation leaves its tolerance.\n"
            "Mean orbital elements: continuous feedback on all six mean elements; holds the "
            "separation to tens of metres, for far more delta-V (template 05: 3.3 m/s in 90 days "
            "against 0.014 m/s for the drift orbit). Earth with J2 only.\n"
            "Hill-frame PD: holds a fixed point next to the chief; for close formations "
            "(about a kilometre) with enough thrust -- it fires all the time and can diverge "
            "if the thruster saturates.\n"
            "See User Manual, 'Formation control laws'."
        )
        pk_form.addRow("Control law", self.pk_control_law_combo)

        # One row per stage instead of a comma-separated list.
        self.pk_target_separations = NumberListEditor(
            unit="km", minimum=0.0, maximum=1.0e6, decimals=1, growable=True, row_label="Stage",
            default_value=100.0,  # [km]
        )
        self.pk_target_separations.set_values(list(pk0.target_separation_km) if pk0 else [100.0])
        self.pk_target_separations.setToolTip(
            "Along-track distance to hold ahead of the chief. With several stages, the target "
            "moves to the next one every 'Reconfiguration interval' and holds the last one."
        )
        pk_form.addRow("Target separation", self.pk_target_separations)
        self.pk_reconfiguration_interval_days = _spin(
            0.0, 1.0e5, decimals=2, step=1.0, value=pk0.reconfiguration_interval_days if pk0 else 90.0)
        self.pk_reconfiguration_interval_days.setToolTip(
            "How often the target separation advances to the next entry in the list above. "
            "Ignored (no effect) when only one separation is given."
        )
        pk_form.addRow("Reconfiguration interval [days] (with 2+ stages)",
                        self.pk_reconfiguration_interval_days)
        self.pk_tolerance_fraction = _spin(0.001, 1.0, decimals=4, step=0.01,
                                            value=pk0.tolerance_fraction if pk0 else 0.10)
        self.pk_tolerance_fraction.setToolTip(
            "How far the real separation must drift off target (as a fraction of the current "
            "target) before a correction maneuver starts. Wider = fewer, larger corrections; "
            "narrower = tighter formation-keeping at the cost of firing more often -- there's "
            "no single right answer, it depends on the mission's own tolerance for drift."
        )
        pk_form.addRow("Trigger tolerance [-] (fraction of target)", self.pk_tolerance_fraction)
        self.pk_restore_tolerance_fraction = _spin(0.001, 1.0, decimals=4, step=0.01,
                                                     value=pk0.restore_tolerance_fraction if pk0 else 0.02)
        self.pk_restore_tolerance_fraction.setToolTip(
            "Once a correction is underway, how close to the target counts as 'close enough, "
            "stop drifting' and settle back onto the target orbit -- tighter than the trigger "
            "tolerance above, since this is the actual precision the correction aims for."
        )
        pk_form.addRow("Restore tolerance [-] (fraction of target)", self.pk_restore_tolerance_fraction)
        self.pk_correction_window_days = _spin(0.1, 1.0e4, decimals=2, step=1.0,
                                                value=pk0.correction_window_days if pk0 else 3.0)
        self.pk_correction_window_days.setToolTip(
            "Target time to null a freshly-triggered phasing error -- sets how aggressive the "
            "temporary drift-orbit altitude offset needs to be (a shorter window needs a "
            "bigger, faster offset). Delta-V scales roughly as 1 / window: at ~550 km, closing "
            "50 km takes ~0.13 m/s in 3 days, ~0.38 m/s in 1 day."
        )
        pk_form.addRow("Correction window [days]", self.pk_correction_window_days)
        self.pk_max_drift_days = _spin(0.1, 1.0e4, decimals=2, step=1.0,
                                        value=pk0.max_drift_days if pk0 else 90.0)
        self.pk_max_drift_days.setToolTip(
            "Safety cap: the drift-orbit coast phase is never allowed to run longer than this, "
            "even if the correction hasn't finished -- bounds how long this spacecraft can "
            "spend off its nominal orbit at once."
        )
        pk_form.addRow("Max drift coast [days]", self.pk_max_drift_days)
        self.pk_max_delta_sma_km = _spin(0.001, 1.0e4, decimals=4, step=0.1,
                                          value=pk0.max_delta_semi_major_axis_km if pk0 else 3.0)
        self.pk_max_delta_sma_km.setToolTip(
            "Safety clamp: the temporary semi-major-axis offset used to drift into position is "
            "never allowed to exceed this -- bounds how far the orbit is allowed to change "
            "during a correction."
        )
        pk_form.addRow("Max drift-orbit SMA offset [km]", self.pk_max_delta_sma_km)
        self.pk_mean_oe_gain = _spin(1.0e-3, 1.0e9, decimals=1, step=500.0,
                                      value=pk0.mean_oe_gain if pk0 else 2500.0)
        self.pk_mean_oe_gain.setToolTip(
            "meanOEFeedback's gain on every mean-element error, per kg of spacecraft (the "
            "module outputs a force). 2500 pulls a 5 km error in within a day at 550 km; "
            "a tenth of it is slow, ten times it costs more to hold."
        )
        pk_form.addRow("Element gain [m^2/s^3 per kg]", self.pk_mean_oe_gain)
        self.pk_hill_position_gain = _spin(1.0e-12, 1.0, decimals=7, step=1.0e-6,
                                            value=pk0.hill_position_gain if pk0 else 2.0e-6)
        self.pk_hill_position_gain.setToolTip(
            "Position gain K (same on all three Hill axes). The command is K x position error, "
            "so keep it under the thruster's acceleration for the errors you expect."
        )
        pk_form.addRow("Position gain K [1/s^2]", self.pk_hill_position_gain)
        self.pk_hill_velocity_gain = _spin(1.0e-9, 10.0, decimals=5, step=1.0e-4,
                                            value=pk0.hill_velocity_gain if pk0 else 2.0e-3)
        self.pk_hill_velocity_gain.setToolTip(
            "Velocity gain P (same on all three axes); about 2 x sqrt(K) for a well-damped hold."
        )
        pk_form.addRow("Velocity gain P [1/s]", self.pk_hill_velocity_gain)
        law_index = self.pk_control_law_combo.findData(pk0.control_law if pk0 else "drift_orbit")
        self.pk_control_law_combo.setCurrentIndex(max(law_index, 0))
        self.pk_control_law_combo.currentIndexChanged.connect(self._show_phasing_law_fields)
        self._show_phasing_law_fields()
        if pk0 is not None:
            chief_index = self.pk_chief_combo.findData(pk0.chief_spacecraft)
            if chief_index >= 0:
                self.pk_chief_combo.setCurrentIndex(chief_index)
            else:
                # pk0.chief_spacecraft doesn't match any current spacecraft
                # name (e.g. that spacecraft was renamed or removed since
                # this config was saved). Silently falling back to index 0
                # would swap the chief to whichever spacecraft happens to
                # be first -- wrong, and invisible to the user. Surface the
                # stale name as its own selectable entry instead, so
                # to_dataclass() below still round-trips it (and
                # SpacecraftConfig.validate()/Scenario.validate() catch it
                # as a real error) unless the user explicitly picks a
                # different chief.
                self.pk_chief_combo.addItem(f"{pk0.chief_spacecraft} (not found in this scenario)",
                                             userData=pk0.chief_spacecraft)
                self.pk_chief_combo.setCurrentIndex(self.pk_chief_combo.count() - 1)
        power_layout.addWidget(self.phasing_keeping_group)

        # Requires BOTH a "reaction_wheel" AND a "thruster" actuator on this
        # spacecraft (see schema.scenario.MomentumDumpingConfig's docstring
        # for why mixing those two kinds is otherwise rejected) -- not
        # cross-checked here against the Sensors/actuators tab's current
        # contents, same as every other config on this tab (e.g. phasing
        # -keeping's chief dropdown): SpacecraftConfig.validate() is the
        # single source of truth, surfaced to the user via this dialog's
        # live validity indicator rather than duplicated here.
        md0 = config.momentum_dumping if config else None
        self.momentum_dumping_group = QGroupBox("Momentum dumping (RW desaturation via thrusters)")
        self.momentum_dumping_group.setCheckable(True)
        self.momentum_dumping_group.setToolTip(
            "Checking this ON fires thrusters in short pulses to bleed off reaction-wheel "
            "momentum whenever it builds up too far -- wheels alone can't shed momentum they've "
            "absorbed from persistent external torques (e.g. gravity gradient), so without this "
            "they'd eventually saturate and lose control authority. Thrusters here are used ONLY "
            "for desaturation, never for primary pointing (that stays on the reaction wheels). "
            "REQUIRES both 'reaction_wheel' and 'thruster' actuators configured on this "
            "spacecraft's Sensors/actuators tab."
        )
        self.momentum_dumping_group.setChecked(md0 is not None)
        md_form = QFormLayout(self.momentum_dumping_group)
        self.md_hs_max = _spin(1.0e-6, 1.0e6, decimals=3, step=1.0, value=md0.hs_max if md0 else 50.0)
        self.md_hs_max.setToolTip(
            "Total reaction-wheel angular momentum magnitude that triggers a desaturation "
            "burn. Set this somewhat BELOW the sum of the wheels' own momentum capacities "
            "(their maxMomentum params on the Sensors/actuators tab), so desaturation fires "
            "before any wheel actually saturates, not after."
        )
        md_form.addRow("Momentum threshold [N*m*s]", self.md_hs_max)
        self.md_thr_min_fire_time = _spin(1.0e-4, 100.0, decimals=4, step=0.01,
                                           value=md0.thr_min_fire_time if md0 else 0.02)
        self.md_thr_min_fire_time.setToolTip(
            "Shortest thruster pulse this controller will command -- a real thruster valve "
            "can't open for an arbitrarily short time, so a commanded pulse shorter than this "
            "gets rounded up (or skipped)."
        )
        md_form.addRow("Thruster firing resolution [s]", self.md_thr_min_fire_time)
        self.md_max_counter_value = _spin(1, 100000, decimals=0, step=10,
                                           value=md0.max_counter_value if md0 else 100)
        self.md_max_counter_value.setToolTip(
            "Minimum number of attitude-control cycles to wait between desaturation firings, "
            "even if the momentum threshold is already crossed -- avoids firing thrusters so "
            "often that they fight the reaction wheels' own control authority."
        )
        md_form.addRow("Control periods between firings [-]", self.md_max_counter_value)
        power_layout.addWidget(self.momentum_dumping_group)

        # The alternative desaturation strategy to momentum_dumping above --
        # requires "reaction_wheel" AND "magnetic_torque_rod" actuators
        # instead of "thruster" (see MagneticMomentumManagementConfig's
        # docstring for why the two strategies are mutually exclusive).
        # wheel_speed_biases_rad_s is one labelled box per reaction_wheel
        # actuator (gui.number_list.NumberListEditor), rebuilt whenever the
        # actuator list changes.
        mmm0 = config.magnetic_momentum_management if config else None
        self.magnetic_momentum_management_group = QGroupBox(
            "Magnetic momentum management (RW desaturation via torque rods)"
        )
        self.magnetic_momentum_management_group.setCheckable(True)
        self.magnetic_momentum_management_group.setToolTip(
            "Checking this ON continuously (not in discrete bursts, unlike 'Momentum dumping' "
            "above) biases the reaction wheels' commanded motor torque to drive each wheel's "
            "speed toward a target bias, using whatever magnetic torque Earth's real geomagnetic "
            "field (the WMM model) allows at the spacecraft's current position. The alternative "
            "desaturation strategy to 'Momentum dumping' -- use ONE or the other, never both. "
            "REQUIRES both 'reaction_wheel' and 'magnetic_torque_rod' actuators on this "
            "spacecraft, and an Earth-centered scenario (the WMM field model is Earth-only)."
        )
        self.magnetic_momentum_management_group.setChecked(mmm0 is not None)
        mmm_form = QFormLayout(self.magnetic_momentum_management_group)
        # One labelled box per reaction wheel (real user feedback: the old
        # comma-separated list had to match the wheels' order by position,
        # with nothing on screen showing which number was which wheel).
        self.mmm_wheel_speed_biases = NumberListEditor(
            unit="rad/s", minimum=-1.0e4, maximum=1.0e4, decimals=1,
            empty_text="Add reaction wheels on the Sensors/actuators tab first.",
        )
        self.mmm_wheel_speed_biases.setToolTip(
            "The speed this controller pulls each reaction wheel toward. One row per "
            "'reaction_wheel' actuator on the Sensors/actuators tab."
        )
        self._mmm_initial_biases = list(mmm0.wheel_speed_biases_rad_s) if mmm0 else []
        self._refresh_wheel_bias_rows()
        self.actuator_list.changed.connect(self._refresh_wheel_bias_rows)
        mmm_form.addRow("Wheel speed biases", self.mmm_wheel_speed_biases)
        self.mmm_c_gain = _spin(1.0e-9, 1.0e6, decimals=6, step=0.001, value=mmm0.c_gain if mmm0 else 0.003)
        self.mmm_c_gain.setToolTip(
            "Control gain mapping each wheel's speed error (from its bias above) to a desired "
            "magnetic torque. Higher = more aggressively pulls wheel speed toward the bias, at "
            "the cost of a more aggressive torque-rod command."
        )
        mmm_form.addRow("Control gain [-]", self.mmm_c_gain)
        power_layout.addWidget(self.magnetic_momentum_management_group)

        # Requires a "thruster" actuator on this spacecraft (see
        # schema.scenario.FuelTankConfig's docstring) -- same
        # not-cross-checked-here convention as momentum_dumping/
        # magnetic_momentum_management above.
        ft0 = config.fuel_tank if config else None
        self.fuel_tank_group = QGroupBox("Fuel tank (real propellant depletion for thrusters)")
        self.fuel_tank_group.setCheckable(True)
        self.fuel_tank_group.setToolTip(
            "Checking this ON adds a real Basilisk fuel-tank state effector: any 'thruster' "
            "actuator on this spacecraft draws propellant from it as it fires, and the "
            "spacecraft's own simulated mass (and center of mass, since the tank has a "
            "position) decreases as the tank drains -- unlike station-keeping/constant-thrust's "
            "own simplified propellant bookkeeping above, this feeds back into the real "
            "simulated dynamics. REQUIRES a 'thruster' actuator configured on the "
            "Sensors/actuators tab."
        )
        self.fuel_tank_group.setChecked(ft0 is not None)
        ft_form = QFormLayout(self.fuel_tank_group)
        self.ft_propellant_mass = _spin(0.0, 1.0e6, decimals=3, step=1.0,
                                          value=ft0.propellant_mass_kg if ft0 else 10.0)
        self.ft_propellant_mass.setToolTip("Propellant mass actually loaded in the tank at the epoch.")
        ft_form.addRow("Propellant mass [kg]", self.ft_propellant_mass)
        self.ft_max_propellant_mass = _spin(1.0e-6, 1.0e6, decimals=3, step=1.0,
                                              value=ft0.max_propellant_mass_kg if ft0 else 20.0)
        self.ft_max_propellant_mass.setToolTip(
            "The tank's physical capacity -- must be at least as large as the propellant mass "
            "above (you can load a partially-full tank, never more than it can hold)."
        )
        ft_form.addRow("Tank capacity [kg]", self.ft_max_propellant_mass)
        tank_pos = ft0.tank_position_b_m if ft0 else [0.0, 0.0, 0.0]
        tank_pos_row = QHBoxLayout()
        self.ft_tank_pos_x = _spin(-1.0e3, 1.0e3, decimals=3, step=0.1, value=tank_pos[0])
        self.ft_tank_pos_y = _spin(-1.0e3, 1.0e3, decimals=3, step=0.1, value=tank_pos[1])
        self.ft_tank_pos_z = _spin(-1.0e3, 1.0e3, decimals=3, step=0.1, value=tank_pos[2])
        _ft_tank_pos_tip = (
            "Where the tank physically sits, in the spacecraft body frame (origin at the body "
            "reference point). As the tank drains, the spacecraft's real center of mass shifts "
            "slightly toward or away from this position -- usually a small effect, more "
            "noticeable for a large tank far from the body's own center."
        )
        for box in (self.ft_tank_pos_x, self.ft_tank_pos_y, self.ft_tank_pos_z):
            box.setToolTip(_ft_tank_pos_tip)
        tank_pos_row.addWidget(self.ft_tank_pos_x)
        tank_pos_row.addWidget(self.ft_tank_pos_y)
        tank_pos_row.addWidget(self.ft_tank_pos_z)
        tank_pos_row_widget = QWidget()
        tank_pos_row_widget.setLayout(tank_pos_row)
        ft_form.addRow("Tank position r_TB_B [m] (body frame B)", tank_pos_row_widget)
        power_layout.addWidget(self.fuel_tank_group)

        rf_link0 = config.rf_link if config else None
        self.rf_link_group = QGroupBox("Downlink RF link budget (margin ESTIMATE only)")
        self.rf_link_group.setCheckable(True)
        self.rf_link_group.setToolTip(
            "Checking this ON computes a reported downlink Eb/N0 margin estimate (a simplified "
            "free-space-path-loss budget, evaluated against the real simulated slant range to "
            "each configured ground station) -- for REPORTING only: it does NOT feed back into "
            "the simulated physics (no data-rate/duty-cycle simulation). A positive margin means "
            "the link closes with that much headroom; negative means it doesn't close at that "
            "range with these numbers."
        )
        self.rf_link_group.setChecked(rf_link0 is not None)
        rf_form = QFormLayout(self.rf_link_group)
        self.tx_power_w = _spin(0.001, 1.0e4, decimals=3, step=1.0, value=rf_link0.tx_power_w if rf_link0 else 15.0)
        self.tx_power_w.setToolTip("Downlink transmitter's RF output power. Higher = more margin, longer range.")
        self.frequency_ghz = _spin(0.001, 1.0e3, decimals=6, step=0.1,
                                    value=(rf_link0.frequency_hz / 1.0e9) if rf_link0 else 8.2)
        self.frequency_ghz.setToolTip(
            "Downlink carrier frequency. Higher frequencies suffer more free-space path loss "
            "for the same distance, but typically allow a higher-gain antenna in the same "
            "physical size (common bands: ~2.2 GHz S-band, ~8.2 GHz X-band)."
        )
        self.data_rate_mbps = _spin(1.0e-6, 1.0e6, decimals=6, step=1.0,
                                     value=(rf_link0.data_rate_bps / 1.0e6) if rf_link0 else 1.0)
        self.data_rate_mbps.setToolTip(
            "Downlink data rate. Higher data rate spreads the same received power over more "
            "bits per second, which REDUCES the margin -- there's a direct trade between "
            "downlink speed and link robustness."
        )
        self.tx_antenna_gain_dbi = _spin(-50.0, 100.0, decimals=2, step=1.0,
                                          value=rf_link0.tx_antenna_gain_dbi if rf_link0
                                          else RFLinkConfig.tx_antenna_gain_dbi)
        self.tx_antenna_gain_dbi.setToolTip(
            "Spacecraft downlink antenna's gain -- how much it concentrates its RF power toward "
            "the ground station rather than radiating it evenly in all directions. 0 dBi is an "
            "idealized unity-gain (omnidirectional) antenna."
        )
        self.rf_implementation_loss_db = _spin(0.0, 50.0, decimals=2, step=0.5,
                                                 value=rf_link0.implementation_loss_db if rf_link0 else 2.0)
        self.rf_implementation_loss_db.setToolTip(
            "A lumped catch-all loss (pointing error, polarization mismatch, hardware "
            "imperfection, etc.) subtracted from the link budget as a fixed penalty -- ~2 dB is "
            "a common rough default when these aren't modeled individually."
        )
        self.required_ebno_db = _spin(-50.0, 50.0, decimals=2, step=0.5,
                                       value=rf_link0.required_ebno_db if rf_link0 else 6.0)
        self.required_ebno_db.setToolTip(
            "The minimum Eb/N0 (energy per bit over noise density) the ground receiver's "
            "modulation and coding scheme needs to decode the signal reliably. The reported "
            "margin is the ACTUAL computed Eb/N0 minus this number -- a more robust "
            "modulation/coding scheme needs a lower number here and is easier to close."
        )
        # antenna_beamwidth_deg (Optional[float]): None (the checkbox below
        # UNCHECKED) keeps the pre-existing behavior of every scenario that
        # predates this field -- no pointing-loss term at all. Checking it
        # ON adds a real pointing-loss term to the link margin, driven by
        # this spacecraft's own ACTUAL achieved comms_pointing error (see
        # RFLinkConfig.antenna_beamwidth_deg's own docstring for the
        # parabolic-pattern falloff this applies) -- pairs naturally with
        # the 'Comms pointing' group on the FSW tab, though nothing here
        # enforces that pairing (same not-cross-checked-here convention).
        self.rf_beamwidth_check = QCheckBox("Model antenna pointing loss")
        self.rf_beamwidth_check.setChecked(rf_link0.antenna_beamwidth_deg is not None if rf_link0 else False)
        self.rf_beamwidth_check.toggled.connect(lambda checked: self.rf_beamwidth_deg.setEnabled(checked))
        rf_form.addRow(self.rf_beamwidth_check)
        self.rf_beamwidth_deg = _spin(
            0.001, 180.0, decimals=3, step=1.0,
            value=(rf_link0.antenna_beamwidth_deg if rf_link0 and rf_link0.antenna_beamwidth_deg else 10.0),
        )
        self.rf_beamwidth_deg.setEnabled(self.rf_beamwidth_check.isChecked())
        self.rf_beamwidth_deg.setToolTip(
            "Half-power beamwidth of this spacecraft's downlink antenna pattern -- narrower "
            "(smaller) beamwidths need more precise pointing (via 'Comms pointing' on the FSW "
            "tab) to avoid a real link-margin penalty. Only used while the checkbox above is ON."
        )
        rf_form.addRow("Antenna beamwidth [deg]", self.rf_beamwidth_deg)
        rf_form.addRow("TX power [W]", self.tx_power_w)
        rf_form.addRow("Carrier frequency [GHz]", self.frequency_ghz)
        rf_form.addRow("Data rate [Mbit/s]", self.data_rate_mbps)
        rf_form.addRow("TX antenna gain [dBi]", self.tx_antenna_gain_dbi)
        rf_form.addRow("Implementation/pointing loss [dB]", self.rf_implementation_loss_db)
        rf_form.addRow("Required Eb/N0 [dB]", self.required_ebno_db)
        power_layout.addWidget(self.rf_link_group)
        power_layout.addStretch(1)

        tabs.addTab(_scrollable(power_tab), "Power / propulsion / link budget")

        # -- Vizard 3D model tab (Phase 5) -------------------------------------
        # PURELY COSMETIC -- see SpacecraftConfig.vizard_model_path's
        # docstring. Deliberately its own tab, not folded into another one,
        # so it reads as clearly separate from anything that affects
        # simulated physics.
        viz_model_tab = QWidget()
        viz_model_layout = QVBoxLayout(viz_model_tab)
        viz_model_description_label = QLabel(
            "A 3D model shown in Vizard instead of the default cube. Display only: it never "
            "changes the simulation."
        )
        # See phasing_formation_dialog.py's identical fix (same
        # copy-pasted top-description-QLabel shape, same missing
        # word-wrap) for the real screenshot that found this bug.
        viz_model_description_label.setWordWrap(True)
        viz_model_layout.addWidget(viz_model_description_label)

        model0 = config if config else None
        self.viz_model_group = QGroupBox("Custom 3D model")
        self.viz_model_group.setCheckable(True)
        self.viz_model_group.setChecked(bool(model0.vizard_model_path) if model0 else False)
        viz_model_form = QFormLayout(self.viz_model_group)

        path_row = QHBoxLayout()
        self.viz_model_path_edit = QLineEdit(model0.vizard_model_path if model0 and model0.vizard_model_path else "")
        self.viz_model_path_edit.setPlaceholderText("path to a .obj file, or CUBE / CYLINDER / SPHERE")
        self.viz_model_path_edit.setToolTip(
            "Replaces Vizard's default spacecraft icon (a plain cube) with this model instead -- "
            "either a path to a real .obj 3D model file, or one of the built-in primitive "
            "shapes (CUBE / CYLINDER / SPHERE)."
        )
        path_row.addWidget(self.viz_model_path_edit)
        self.viz_model_browse_button = QPushButton("Browse...")
        self.viz_model_browse_button.clicked.connect(self._on_browse_viz_model)
        path_row.addWidget(self.viz_model_browse_button)
        viz_model_form.addRow("Model path", path_row)

        offset0 = model0.vizard_model_offset_m if model0 else [0.0, 0.0, 0.0]
        self.viz_offset_x = _spin(-1.0e6, 1.0e6, decimals=4, step=0.1, value=offset0[0])
        self.viz_offset_y = _spin(-1.0e6, 1.0e6, decimals=4, step=0.1, value=offset0[1])
        self.viz_offset_z = _spin(-1.0e6, 1.0e6, decimals=4, step=0.1, value=offset0[2])
        _viz_offset_tip = "Shifts the model's origin away from the spacecraft's body reference point, in the body frame."
        for box in (self.viz_offset_x, self.viz_offset_y, self.viz_offset_z):
            box.setToolTip(_viz_offset_tip)
        viz_model_form.addRow("Offset [m] (body frame, 3 components)",
                               _hbox(self.viz_offset_x, self.viz_offset_y, self.viz_offset_z))

        rot0 = model0.vizard_model_rotation_deg if model0 else [0.0, 0.0, 0.0]
        self.viz_rotation_z = _spin(-360.0, 360.0, decimals=3, step=1.0, value=rot0[0])
        self.viz_rotation_y = _spin(-360.0, 360.0, decimals=3, step=1.0, value=rot0[1])
        self.viz_rotation_x = _spin(-360.0, 360.0, decimals=3, step=1.0, value=rot0[2])
        _viz_rotation_tip = (
            "Rotates the model relative to the body frame, applied as a 3-2-1 Euler sequence "
            "(Z first, then Y, then X) -- use this if the model's own built-in orientation "
            "doesn't already match the spacecraft's body axes."
        )
        for box in (self.viz_rotation_z, self.viz_rotation_y, self.viz_rotation_x):
            box.setToolTip(_viz_rotation_tip)
        viz_model_form.addRow("Rotation [deg] (3-2-1 Euler: Z, Y, X)",
                               _hbox(self.viz_rotation_z, self.viz_rotation_y, self.viz_rotation_x))

        scale0 = model0.vizard_model_scale if model0 else [1.0, 1.0, 1.0]
        self.viz_scale_x = _spin(0.0001, 1.0e6, decimals=4, step=0.1, value=scale0[0])
        self.viz_scale_y = _spin(0.0001, 1.0e6, decimals=4, step=0.1, value=scale0[1])
        self.viz_scale_z = _spin(0.0001, 1.0e6, decimals=4, step=0.1, value=scale0[2])
        _viz_scale_tip = "Stretches/shrinks the model along each body axis -- 1.0 keeps its original, modeled size."
        for box in (self.viz_scale_x, self.viz_scale_y, self.viz_scale_z):
            box.setToolTip(_viz_scale_tip)
        viz_model_form.addRow("Scale [-] (body x, y, z axes, 3 components)",
                               _hbox(self.viz_scale_x, self.viz_scale_y, self.viz_scale_z))

        viz_model_layout.addWidget(self.viz_model_group)
        viz_model_layout.addStretch(1)
        tabs.addTab(_scrollable(viz_model_tab), "Vizard model")

        # -- Delta-V and propellant budget inputs (ESA AD10) --------------------
        from .budget_widget import BudgetInputsGroup

        budget_tab = QWidget()
        budget_layout = QVBoxLayout(budget_tab)
        self.budget_group = BudgetInputsGroup(config.propellant_budget if config else None)
        budget_layout.addWidget(self.budget_group)
        budget_layout.addStretch(1)
        tabs.addTab(_scrollable(budget_tab), "Budget (AD10)")

        if self._orbit_only:
            tabs.setTabVisible(self._sensors_tab_index, False)
            tabs.setTabVisible(self._fsw_tab_index, False)
            self.power_group.setChecked(False)
            self.power_group.setVisible(False)
            # momentum_dumping/magnetic_momentum_management/fuel_tank all
            # require specific actuator kinds (SpacecraftConfig.validate())
            # that can only be added on the now-hidden Sensors/actuators
            # tab -- leaving these checkable would be a dead end (checking
            # one and clicking OK always fails validation with no way back
            # to fix it from this dialog), same reasoning as power_group
            # just above.
            self.momentum_dumping_group.setChecked(False)
            self.momentum_dumping_group.setVisible(False)
            self.magnetic_momentum_management_group.setChecked(False)
            self.magnetic_momentum_management_group.setVisible(False)
            self.fuel_tank_group.setChecked(False)
            self.fuel_tank_group.setVisible(False)
            # comms_pointing lives on the now-hidden FSW tab and needs
            # attitude control to mean anything -- same reasoning as
            # fsw_mode/power above (to_dataclass() also force-clears it to
            # None in the _orbit_only branch, not just hiding this widget).
            self.comms_pointing_group.setChecked(False)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer_layout.addWidget(buttons)

        # Real bug, found from a user screenshot: with no explicit size,
        # this dialog opened absurdly small -- even its own first tab's
        # Name/Dry mass rows were clipped behind scrollbars. Unlike
        # propagation_setup_dialog.py's similar (much milder) case,
        # resizing to self.sizeHint() alone would NOT fix this here:
        # every tab is wrapped in its own QScrollArea (see _scrollable()'s
        # own docstring for why), and a QScrollArea's sizeHint() is a
        # small, mostly-arbitrary default -- NOT the wrapped content's
        # real size -- so QDialog's own sizeHint() stays tiny regardless
        # of how much is actually in each tab (confirmed directly: this
        # dialog's sizeHint() measured 530x416 while its own "Orbit /
        # mass" tab content alone needs 572x789, and the widest tab
        # ("Power / propulsion / link budget") needs 715).
        #
        # Picks a width wide enough for every tab's content (so nothing
        # wraps/clips horizontally) and a fixed, generous height -- NOT
        # tall enough to fit the busiest tab without scrolling (that tab
        # alone wants ~1485px, far taller than most screens) -- each
        # tab's own QScrollArea is deliberately there so a busy tab
        # scrolls independently rather than forcing every other tab's
        # dialog that tall (see _scrollable()'s own docstring).
        widest_tab_content = max(tabs.widget(i).widget().sizeHint().width() for i in range(tabs.count()))
        # Also wide enough for the tab bar itself -- sized from content
        # alone, the last tab ("Vizard model") was clipped to a sliver.
        # ensurePolished() first: the theme's bold tab font only applies
        # once the stylesheet polishes the bar, and the unpolished
        # sizeHint() comes out ~100 px short, still scrolling the bar.
        tabs.tabBar().ensurePolished()
        tab_bar_width = tabs.tabBar().sizeHint().width()
        self.resize(max(650, widest_tab_content + 40, tab_bar_width + 40), 700)

    def _on_name_changed(self, text: str) -> None:
        """Live, per-keystroke feedback (theme.py's ``[state="error"]``
        red-border rule, via gui.feedback) for the one field whose
        validity this dialog can check WITHOUT a full
        :meth:`to_dataclass` call -- ``self._other_spacecraft_names`` is
        already known at construction time. Catches the exact mistake
        (an empty or duplicate name) before the user even reaches OK,
        rather than only after :meth:`_on_accept` rejects it.
        """
        name = text.strip()
        if not name:
            mark_invalid(self.name_edit, "Name must not be empty")
        elif name in self._other_spacecraft_names:
            mark_invalid(self.name_edit, f"A spacecraft named {name!r} already exists")
        else:
            clear_invalid(self.name_edit)

    def _on_accept(self) -> None:
        # Real UX bug this used to have: an empty/duplicate name wasn't
        # checked HERE at all -- to_dataclass() doesn't care, so accept()
        # always succeeded, the dialog closed, and only THEN did the
        # caller (_on_add/_on_edit/_on_new_from_template) notice the
        # duplicate and show a QMessageBox -- by which point the dialog
        # was already gone and every edit the user just made was silently
        # discarded. Checking it here, before accept(), keeps the dialog
        # (and the user's edits) open so they can just fix the name.
        name = self.name_edit.text().strip()
        if not name:
            mark_invalid(self.name_edit, "Name must not be empty")
            self.name_edit.setFocus()
            return
        if name in self._other_spacecraft_names:
            mark_invalid(self.name_edit, f"A spacecraft named {name!r} already exists")
            self.name_edit.setFocus()
            return
        try:
            self.to_dataclass()
        except ScenarioValidationError as exc:
            QMessageBox.critical(self, "Invalid spacecraft", str(exc))
            return
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid input", str(exc))
            return
        self.accept()

    @property
    def fsw_params_edit(self) -> QPlainTextEdit:
        """The Pointing parameters' collapsed "Advanced" JSON box."""
        return self.fsw_param_form.params_edit

    @property
    def control_params_edit(self) -> QPlainTextEdit:
        """The Control gains' collapsed "Advanced" JSON box."""
        return self.control_param_form.params_edit

    def _fsw_default_params(self, fsw_mode) -> dict:
        params = _fsw_template_params(fsw_mode)
        if "target_ground_station" in params and self._ground_station_names:
            params["target_ground_station"] = self._ground_station_names[0]
        return params

    def _build_fsw_form(self, fsw_mode, params: dict) -> None:
        specs = _FSW_MODE_PARAM_SPECS.get(fsw_mode, []) if fsw_mode is not None else []
        stations = list(self._ground_station_names)
        options = {
            "target_ground_station": (stations, not stations),
            "target_body": (_TARGET_BODY_CHOICES, True),
        }
        empty = "This mode has no parameters." if fsw_mode is not None else "No attitude control selected."
        self.fsw_param_form.set_specs(specs, params, options=options, empty_text=empty)
        station_box = self.fsw_param_form.include_box("target_ground_station")
        body_box = self.fsw_param_form.include_box("target_body")
        if station_box is not None and body_box is not None:
            # Exactly one target: ticking one unticks the other.
            station_box.toggled.connect(lambda on: on and body_box.setChecked(False))
            body_box.toggled.connect(lambda on: on and station_box.setChecked(False))

    def _on_fsw_mode_changed(self, _index: int) -> None:
        mode = self.fsw_mode_combo.currentData()
        try:
            self._fsw_mode_params[self._current_fsw_mode] = self.fsw_param_form.params()
        except ValueError:
            pass  # unparseable advanced JSON: just don't snapshot it
        self._current_fsw_mode = mode
        self._build_fsw_form(mode, self._fsw_mode_params.get(mode, self._fsw_default_params(mode)))
        self._refresh_fsw_hint()

    def _refresh_fsw_hint(self, *_args) -> None:
        # Comms pointing runs its own guidance AND feeds 'Control gains'
        # into its mrpFeedback loop (engine.service) -- the plain "(none)"
        # hint ("...coasts...") was flatly wrong for a comms_pointing
        # spacecraft such as template 19's.
        mode = self.fsw_mode_combo.currentData()
        comms = self.comms_pointing_group.isChecked() and mode is None
        self.fsw_params_group.setVisible(mode is not None)
        if comms:
            self.fsw_hint_label.setText("Attitude is controlled by Comms pointing below; the control gains "
                                        "still apply.")
            return
        self.fsw_hint_label.setText(_fsw_hint_text(mode))

    def _on_fsw_reset_template(self) -> None:
        mode = self.fsw_mode_combo.currentData()
        self._build_fsw_form(mode, self._fsw_default_params(mode))

    def _on_cp_sun_axis_default_toggled(self, checked: bool) -> None:
        for box in (self.cp_sun_axis_x, self.cp_sun_axis_y, self.cp_sun_axis_z):
            box.setEnabled(not checked)

    @staticmethod
    def _form_params(form: ParamForm, field_label: str) -> dict:
        try:
            return form.params()
        except ValueError as exc:
            raise ValueError(f"{field_label}: {exc}") from exc

    def to_dataclass(self) -> SpacecraftConfig:
        name = self.name_edit.text().strip()
        if self._orbit_only:
            # Tabs/group are hidden above -- force-clear rather than trust
            # their (stale, possibly pre-populated-from-an-existing-config)
            # widget state, so this dialog can never itself produce a
            # config that violates Scenario.simulation_mode's "orbit_only"
            # rule (see that field's docstring), regardless of what was on
            # the spacecraft being edited before the scenario's mode was
            # switched to "orbit_only".
            fsw_mode, fsw_params, sensors, actuators, power, comms_pointing = None, {}, [], [], None, None
        else:
            fsw_mode = self.fsw_mode_combo.currentData()
            fsw_params = self._form_params(self.fsw_param_form, "Pointing parameters")
            missing = _fsw_missing_required_keys(fsw_mode, fsw_params)
            if missing:
                raise ValueError(
                    f"FSW mode {fsw_mode!r} is missing required params key(s): {', '.join(missing)} -- "
                    "tick 'Point at ground station' or 'Point at celestial body'"
                    if fsw_mode == "locationPointing" else
                    f"FSW mode {fsw_mode!r} is missing required params key(s): {', '.join(missing)} -- "
                    "use 'Reset to template' for a working example"
                )
            sensors = self.sensor_list.to_list()
            actuators = self.actuator_list.to_list()
            power = self._power_to_dataclass()
            comms_pointing = self._comms_pointing_to_dataclass()
        config = SpacecraftConfig(
            name=name,
            orbit=self.orbit_widget.to_dataclass(),
            dry_mass_kg=self.dry_mass_kg.value(),
            inertia_kg_m2=[
                self.ixx.value(), 0.0, 0.0,
                0.0, self.iyy.value(), 0.0,
                0.0, 0.0, self.izz.value(),
            ],
            sigma_bn_init=[self.sigma1.value(), self.sigma2.value(), self.sigma3.value()],
            omega_bn_b_init_rad_s=[self.omega1.value(), self.omega2.value(), self.omega3.value()],
            sensors=sensors,
            actuators=actuators,
            fsw_mode=fsw_mode,
            fsw_params=fsw_params,
            control_params=self._form_params(self.control_param_form, "Control gains"),
            power=power,
            comms_pointing=comms_pointing,
            rf_link=self._rf_link_to_dataclass(),
            station_keeping=self._station_keeping_to_dataclass(),
            geo_station_keeping=self._geo_station_keeping_to_dataclass(),
            phasing_keeping=self._phasing_keeping_to_dataclass(),
            constant_thrust=self._constant_thrust_to_dataclass(),
            momentum_dumping=self._momentum_dumping_to_dataclass(),
            magnetic_momentum_management=self._magnetic_momentum_management_to_dataclass(),
            fuel_tank=self._fuel_tank_to_dataclass(),
            propellant_budget=self.budget_group.to_config(),
            enable_drag=self.enable_drag_check.isChecked(),
            drag_coeff=self.drag_coeff.value(),
            drag_area_m2=self.drag_area_m2.value(),
            enable_srp=self.enable_srp_check.isChecked(),
            srp_coeff=self.srp_coeff.value(),
            srp_area_m2=self.srp_area_m2.value(),
            facets=self.facet_table.to_list(),
            enable_gravity_gradient=self.gravity_gradient_check.isChecked(),
            vizard_model_path=self._viz_model_to_dataclass_path(),
            vizard_model_offset_m=[self.viz_offset_x.value(), self.viz_offset_y.value(), self.viz_offset_z.value()],
            vizard_model_rotation_deg=[self.viz_rotation_z.value(), self.viz_rotation_y.value(),
                                        self.viz_rotation_x.value()],
            vizard_model_scale=[self.viz_scale_x.value(), self.viz_scale_y.value(), self.viz_scale_z.value()],
        )
        config.validate()  # raises ScenarioValidationError with a specific message on anything bad
        return config

    def _viz_model_to_dataclass_path(self) -> str | None:
        if not self.viz_model_group.isChecked():
            return None
        path = self.viz_model_path_edit.text().strip()
        return path or None

    def _on_browse_viz_model(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Select a 3D model (.obj)", "", "Wavefront OBJ (*.obj)")
        if path:
            self.viz_model_path_edit.setText(path)

    def _comms_pointing_to_dataclass(self) -> CommsPointingConfig | None:
        if not self.comms_pointing_group.isChecked():
            return None
        target_ground_station = self.cp_ground_station_combo.currentData()
        if target_ground_station is None:
            raise ScenarioValidationError(
                "comms_pointing is enabled but no ground station is selectable -- add a ground "
                "station to this scenario first, or uncheck 'Comms pointing'"
            )
        sun_pointing_axis_b = None if self.cp_sun_axis_default_check.isChecked() else [
            self.cp_sun_axis_x.value(), self.cp_sun_axis_y.value(), self.cp_sun_axis_z.value(),
        ]
        return CommsPointingConfig(
            target_ground_station=target_ground_station,
            antenna_boresight_b=[self.cp_boresight_x.value(), self.cp_boresight_y.value(), self.cp_boresight_z.value()],
            sun_pointing_axis_b=sun_pointing_axis_b,
            comms_power_w=self.cp_comms_power_w.value(),
        )

    def _station_keeping_to_dataclass(self) -> StationKeepingConfig | None:
        if not self.station_keeping_group.isChecked():
            return None
        return StationKeepingConfig(
            target_altitude_km=self.sk_target_altitude_km.value(),
            deadband_km=self.sk_deadband_km.value(),
            thrust_n=self.sk_thrust_n.value(),
            isp_s=self.sk_isp_s.value(),
            propellant_kg=self.sk_propellant_kg.value(),
            eclipse_sunlit_threshold=self.sk_eclipse_sunlit_threshold.value(),
            min_on_time_s=self.sk_min_on_time_s.value(),
            eccentricity_neutral_burns=self.sk_eccentricity_neutral_check.isChecked(),
        )

    def _geo_station_keeping_to_dataclass(self) -> GeoStationKeepingConfig | None:
        if not self.geo_station_keeping_group.isChecked():
            return None
        return GeoStationKeepingConfig(
            target_longitude_deg=self.geo_longitude_deg.value(),
            longitude_deadband_deg=self.geo_deadband_deg.value(),
            inclination_max_deg=self.geo_inclination_max_deg.value(),
            thrust_n=self.geo_thrust_n.value(),
            isp_s=self.geo_isp_s.value(),
            propellant_kg=self.geo_propellant_kg.value(),
        )

    def _constant_thrust_to_dataclass(self) -> ConstantThrustConfig | None:
        if not self.constant_thrust_group.isChecked():
            return None
        return ConstantThrustConfig(
            frame=self.ct_frame_combo.currentText(),
            direction=[self.ct_dir_x.value(), self.ct_dir_y.value(), self.ct_dir_z.value()],
            thrust_n=self.ct_thrust_n.value(),
            isp_s=self.ct_isp_s.value(),
            propellant_kg=self.ct_propellant_kg.value(),
        )

    def _momentum_dumping_to_dataclass(self) -> MomentumDumpingConfig | None:
        if not self.momentum_dumping_group.isChecked():
            return None
        return MomentumDumpingConfig(
            hs_max=self.md_hs_max.value(),
            thr_min_fire_time=self.md_thr_min_fire_time.value(),
            max_counter_value=int(self.md_max_counter_value.value()),
        )

    def _magnetic_momentum_management_to_dataclass(self) -> MagneticMomentumManagementConfig | None:
        if not self.magnetic_momentum_management_group.isChecked():
            return None
        wheel_speed_biases_rad_s = self.mmm_wheel_speed_biases.values()
        if not wheel_speed_biases_rad_s:
            raise ScenarioValidationError(
                "Magnetic momentum management needs at least one reaction wheel -- add one on the "
                "Sensors/actuators tab"
            )
        return MagneticMomentumManagementConfig(
            wheel_speed_biases_rad_s=wheel_speed_biases_rad_s,
            c_gain=self.mmm_c_gain.value(),
        )

    def _refresh_wheel_bias_rows(self) -> None:
        """One bias row per reaction wheel, in actuator-list order (the
        order the engine matches biases by); values follow position."""
        wheels = [a.name for a in self.actuator_list.to_list() if a.kind == "reaction_wheel"]
        current = self.mmm_wheel_speed_biases.values() or self._mmm_initial_biases
        self.mmm_wheel_speed_biases.set_rows(wheels, current)

    def _fuel_tank_to_dataclass(self) -> FuelTankConfig | None:
        if not self.fuel_tank_group.isChecked():
            return None
        return FuelTankConfig(
            propellant_mass_kg=self.ft_propellant_mass.value(),
            max_propellant_mass_kg=self.ft_max_propellant_mass.value(),
            tank_position_b_m=[self.ft_tank_pos_x.value(), self.ft_tank_pos_y.value(), self.ft_tank_pos_z.value()],
        )

    def _show_phasing_law_fields(self) -> None:
        """Only the chosen control law's own settings are shown."""
        law = self.pk_control_law_combo.currentData()
        drift = (self.pk_tolerance_fraction, self.pk_restore_tolerance_fraction, self.pk_correction_window_days,
                 self.pk_max_drift_days, self.pk_max_delta_sma_km)
        rows = [(w, law == "drift_orbit") for w in drift] + [
            (self.pk_mean_oe_gain, law == "mean_oe"),
            (self.pk_hill_position_gain, law == "hill_pd"), (self.pk_hill_velocity_gain, law == "hill_pd")]
        for widget, shown in rows:
            widget.setVisible(shown)
            label = self._pk_form.labelForField(widget)
            if label is not None:
                label.setVisible(shown)

    def _phasing_keeping_to_dataclass(self) -> PhasingKeepingConfig | None:
        if not self.phasing_keeping_group.isChecked():
            return None
        chief = self.pk_chief_combo.currentData()
        if chief is None:
            raise ScenarioValidationError(
                "phasing_keeping is enabled but no chief spacecraft is selectable -- add another "
                "spacecraft to this scenario first, or uncheck 'Phasing keeping'"
            )
        target_separation_km = self.pk_target_separations.values()
        return PhasingKeepingConfig(
            chief_spacecraft=chief,
            target_separation_km=target_separation_km,
            reconfiguration_interval_days=self.pk_reconfiguration_interval_days.value(),
            tolerance_fraction=self.pk_tolerance_fraction.value(),
            restore_tolerance_fraction=self.pk_restore_tolerance_fraction.value(),
            correction_window_days=self.pk_correction_window_days.value(),
            max_drift_days=self.pk_max_drift_days.value(),
            max_delta_semi_major_axis_km=self.pk_max_delta_sma_km.value(),
            control_law=self.pk_control_law_combo.currentData(),
            mean_oe_gain=self.pk_mean_oe_gain.value(),
            hill_position_gain=self.pk_hill_position_gain.value(),
            hill_velocity_gain=self.pk_hill_velocity_gain.value(),
        )

    def _power_to_dataclass(self) -> PowerConfig | None:
        if not self.power_group.isChecked():
            return None
        return PowerConfig(
            panel_area_m2=self.panel_area_m2.value(),
            panel_efficiency=self.panel_efficiency.value(),
            panel_normal_b=[self.panel_normal_x.value(), self.panel_normal_y.value(), self.panel_normal_z.value()],
            bus_idle_power_w=self.bus_idle_power_w.value(),
            battery_capacity_wh=self.battery_capacity_wh.value(),
            battery_initial_soc=self.battery_initial_soc.value(),
        )

    def _rf_link_to_dataclass(self) -> RFLinkConfig | None:
        if not self.rf_link_group.isChecked():
            return None
        return RFLinkConfig(
            tx_power_w=self.tx_power_w.value(),
            frequency_hz=self.frequency_ghz.value() * 1.0e9,
            data_rate_bps=self.data_rate_mbps.value() * 1.0e6,
            tx_antenna_gain_dbi=self.tx_antenna_gain_dbi.value(),
            implementation_loss_db=self.rf_implementation_loss_db.value(),
            required_ebno_db=self.required_ebno_db.value(),
            antenna_beamwidth_deg=self.rf_beamwidth_deg.value() if self.rf_beamwidth_check.isChecked() else None,
        )


def _hbox(*widgets: QWidget) -> QWidget:
    container = QWidget()
    box = QHBoxLayout(container)
    box.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        box.addWidget(w)
    return container


class SpacecraftListWidget(QWidget):
    """A list of spacecraft with Add/Edit/Remove, backed by a plain list
    of :class:`SpacecraftConfig`. Emits :attr:`changed` whenever that list
    changes (add, edit, remove, or reorder).
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._configs: list[SpacecraftConfig] = []
        # Set by the owning ScenarioEditorWidget (see set_central_body_provider)
        # so "Generate Walker constellation..." always uses this scenario's
        # ACTUAL current central body, never an independently-selectable one
        # that could silently drift out of sync with it. Falls back to
        # "earth" when unset (e.g. this widget used standalone in a test).
        self._central_body_provider = None
        # Set by the owning ScenarioEditorWidget (see
        # set_simulation_mode_provider) so every SpacecraftEditorDialog
        # this widget opens reflects the scenario's CURRENT simulation
        # mode. Falls back to "full_attitude" when unset (e.g. this widget
        # used standalone in a test) -- see Scenario.simulation_mode's
        # docstring.
        self._simulation_mode_provider = None
        # Set by the owning ScenarioEditorWidget (see
        # set_ground_station_names_provider) so every SpacecraftEditorDialog
        # this widget opens can populate comms_pointing's
        # target_ground_station combo with this scenario's CURRENT ground
        # stations -- same pattern as _central_body_provider/
        # _simulation_mode_provider above. Falls back to an empty list when
        # unset (e.g. this widget used standalone in a test).
        self._ground_station_names_provider = None
        # Set by the owning ScenarioEditorWidget (see set_epoch_provider)
        # so every SpacecraftEditorDialog this widget opens can pass it
        # straight down to OrbitIcWidget's own "Compute RAAN for LTAN..."
        # button -- same provider pattern as the two above.
        self._epoch_provider = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        # Two rows, not one: all 5 buttons in a single QHBoxLayout needed
        # ~700px to avoid truncating/hiding the last one or two -- more
        # than this panel reliably gets now that MainWindow's splitter
        # gives the left pane less width than the right (see that
        # change's own comment). Row 1 is the everyday list-editing
        # actions; row 2 is the one-off bulk-generation action.
        button_row = QHBoxLayout()
        self.add_button = QPushButton("Add...")
        self.edit_button = QPushButton("Edit...")
        self.remove_button = QPushButton("Remove")
        self.new_from_template_button = QPushButton("New from template...")
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.new_from_template_button)
        button_row.addWidget(self.edit_button)
        button_row.addWidget(self.remove_button)
        layout.addLayout(button_row)

        second_button_row = QHBoxLayout()
        self.generate_constellation_button = QPushButton("Generate Walker constellation...")
        self.generate_phasing_formation_button = QPushButton("Generate phasing formation...")
        second_button_row.addWidget(self.generate_constellation_button)
        second_button_row.addWidget(self.generate_phasing_formation_button)
        second_button_row.addStretch(1)
        layout.addLayout(second_button_row)

        self.add_button.clicked.connect(self._on_add)
        self.new_from_template_button.clicked.connect(self._on_new_from_template)
        self.edit_button.clicked.connect(self._on_edit)
        self.remove_button.clicked.connect(self._on_remove)
        self.generate_constellation_button.clicked.connect(self._on_generate_constellation)
        self.generate_phasing_formation_button.clicked.connect(self._on_generate_phasing_formation)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._on_edit())

    def set_central_body_provider(self, provider) -> None:
        """``provider`` is a zero-argument callable returning the
        scenario's current central-body name, e.g.
        ``lambda: self._gravity.central_body`` from ``ScenarioEditorWidget``.
        """
        self._central_body_provider = provider

    def set_simulation_mode_provider(self, provider) -> None:
        """``provider`` is a zero-argument callable returning the
        scenario's current ``simulation_mode`` ("full_attitude" or
        "orbit_only"), e.g. ``lambda: self.simulation_mode_combo.currentData()``
        from ``ScenarioEditorWidget``.
        """
        self._simulation_mode_provider = provider

    def set_ground_station_names_provider(self, provider) -> None:
        """``provider`` is a zero-argument callable returning this
        scenario's current ground-station names, e.g.
        ``lambda: [gs.name for gs in self.ground_station_list.to_list()]``
        from ``ScenarioEditorWidget``.
        """
        self._ground_station_names_provider = provider

    def set_epoch_provider(self, provider) -> None:
        """``provider`` is a zero-argument callable returning this
        scenario's current ``epoch_utc`` string, e.g.
        ``lambda: self.epoch_edit.text().strip()`` from
        ``ScenarioEditorWidget``.
        """
        self._epoch_provider = provider

    def _simulation_mode(self) -> str:
        return self._simulation_mode_provider() if self._simulation_mode_provider else "full_attitude"

    def _ground_station_names(self) -> list[str]:
        return self._ground_station_names_provider() if self._ground_station_names_provider else []

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for config in self._configs:
            self.list_widget.addItem(QListWidgetItem(config.name))

    def _on_add(self) -> None:
        existing_names = {c.name for c in self._configs}
        dialog = SpacecraftEditorDialog(parent=self, other_spacecraft_names=sorted(existing_names),
                                         simulation_mode=self._simulation_mode(),
                                         ground_station_names=self._ground_station_names(),
                                         epoch_provider=self._epoch_provider)
        # default name must be unique so QListWidget entries stay distinguishable
        base_name = dialog.name_edit.text()
        candidate, n = base_name, 1
        while candidate in existing_names:
            n += 1
            candidate = f"{base_name}-{n}"
        dialog.name_edit.setText(candidate)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.to_dataclass()
            if config.name in existing_names:
                QMessageBox.critical(self, "Duplicate name",
                                      f"A spacecraft named {config.name!r} already exists.")
                return
            self._configs.append(config)
            self._refresh_list()
            self.list_widget.setCurrentRow(len(self._configs) - 1)
            show_toast(self.window(), f"Added spacecraft {config.name!r}")
            self.changed.emit()

    def _on_new_from_template(self) -> None:
        from .spacecraft_template_dialog import SpacecraftTemplateDialog

        picker = SpacecraftTemplateDialog(parent=self)
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        template = picker.selected_template()
        if template is None:
            return

        existing_names = {c.name for c in self._configs}
        prefilled = template.build()
        # default name must be unique so QListWidget entries stay distinguishable
        base_name = prefilled.name
        candidate, n = base_name, 1
        while candidate in existing_names:
            n += 1
            candidate = f"{base_name}-{n}"
        prefilled.name = candidate

        dialog = SpacecraftEditorDialog(config=prefilled, parent=self, other_spacecraft_names=sorted(existing_names),
                                         simulation_mode=self._simulation_mode(),
                                         ground_station_names=self._ground_station_names(),
                                         epoch_provider=self._epoch_provider)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.to_dataclass()
            if config.name in existing_names:
                QMessageBox.critical(self, "Duplicate name",
                                      f"A spacecraft named {config.name!r} already exists.")
                return
            self._configs.append(config)
            self._refresh_list()
            self.list_widget.setCurrentRow(len(self._configs) - 1)
            show_toast(self.window(), f"Added spacecraft {config.name!r} from template")
            self.changed.emit()

    def _on_edit(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        other_names = sorted(c.name for i, c in enumerate(self._configs) if i != row)
        dialog = SpacecraftEditorDialog(config=self._configs[row], parent=self, other_spacecraft_names=other_names,
                                         simulation_mode=self._simulation_mode(),
                                         ground_station_names=self._ground_station_names(),
                                         epoch_provider=self._epoch_provider)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_config = dialog.to_dataclass()
            other_names = {c.name for i, c in enumerate(self._configs) if i != row}
            if new_config.name in other_names:
                QMessageBox.critical(self, "Duplicate name",
                                      f"A spacecraft named {new_config.name!r} already exists.")
                return
            self._configs[row] = new_config
            self._refresh_list()
            self.list_widget.setCurrentRow(row)
            show_toast(self.window(), f"Updated spacecraft {new_config.name!r}")
            self.changed.emit()

    def _on_remove(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        name = self._configs[row].name
        del self._configs[row]
        self._refresh_list()
        show_toast(self.window(), f"Removed spacecraft {name!r}", kind="info")
        self.changed.emit()

    def _on_generate_constellation(self) -> None:
        from ..engine.constellation import generate_walker_constellation
        from .constellation_dialog import WalkerConstellationDialog

        central_body = self._central_body_provider() if self._central_body_provider else "earth"
        dialog = WalkerConstellationDialog([c.name for c in self._configs], central_body=central_body, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        request = dialog.to_request()
        template_name = dialog.selected_template_name()
        if template_name is not None:
            template = next(c for c in self._configs if c.name == template_name)
        else:
            template = SpacecraftConfig(name="template", orbit=OrbitIC(
                type="classical_elements", semi_major_axis_km=7000.0, eccentricity=0.0,
                inclination_deg=0.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0,
            ))

        try:
            generated = generate_walker_constellation(request, template)
        except ScenarioValidationError as exc:
            QMessageBox.critical(self, "Cannot generate constellation", str(exc))
            return

        existing_names = {c.name for c in self._configs}
        colliding = [s.name for s in generated if s.name in existing_names]
        if colliding:
            QMessageBox.critical(self, "Name collision",
                                  f"Generated spacecraft name(s) already exist in this scenario: {colliding}. "
                                  "Change the name prefix and try again.")
            return

        self._configs.extend(generated)
        self._refresh_list()
        self.list_widget.setCurrentRow(len(self._configs) - 1)
        show_toast(self.window(), f"Generated {len(generated)} constellation spacecraft")
        self.changed.emit()

    def _on_generate_phasing_formation(self) -> None:
        from .phasing_formation_dialog import PhasingFormationDialog

        central_body = self._central_body_provider() if self._central_body_provider else "earth"
        dialog = PhasingFormationDialog([c.name for c in self._configs], central_body=central_body, parent=self,
                                        spacecraft=self._configs)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        request = dialog.to_request()
        chief = next(c for c in self._configs if c.name == dialog.selected_chief_name())
        template_name = dialog.selected_template_name()
        template = next((c for c in self._configs if c.name == template_name), chief)

        existing_names = {c.name for c in self._configs}
        if request.follower_name in existing_names:
            QMessageBox.critical(self, "Duplicate name",
                                  f"A spacecraft named {request.follower_name!r} already exists.")
            return

        # engine.formation imports Basilisk lazily (at generate_phasing_follower()
        # call time, not at this module's own import time -- see that
        # module's docstring), so a missing/unbuilt Basilisk only surfaces
        # here, same "clear error, not a traceback" pattern every other
        # Basilisk-needing GUI action already uses (gui.run_worker).
        from ..engine.formation import generate_phasing_follower

        try:
            follower = generate_phasing_follower(request, chief, template, central_body)
        except ImportError as exc:
            QMessageBox.critical(self, "Basilisk not available",
                                  f"Basilisk is not installed/built ({exc}) -- generating a phasing formation "
                                  "needs a real Basilisk build (it computes the follower's orbit via a real "
                                  "Hill-frame state-vector transform, not a hand-rolled equivalent). See "
                                  "SpaceMissionStudio/README.md.")
            return
        except ScenarioValidationError as exc:
            QMessageBox.critical(self, "Cannot generate phasing formation", str(exc))
            return

        chief.station_keeping = dialog.chief_station_keeping()  # the chief section of the dialog
        self._configs.append(follower)
        self._refresh_list()
        self.list_widget.setCurrentRow(len(self._configs) - 1)
        show_toast(self.window(), f"Generated phasing follower {follower.name!r}")
        self.changed.emit()

    def to_list(self) -> list[SpacecraftConfig]:
        return list(self._configs)

    def from_list(self, configs: list[SpacecraftConfig]) -> None:
        self._configs = list(configs)
        self._refresh_list()
