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

"""One reusable list-editor widget for :class:`schema.scenario.SensorConfig`
and :class:`schema.scenario.ActuatorConfig` -- their shape is identical
(``kind``, ``name``, ``params``), so one generic widget covers both,
parameterized by which item class and which kind whitelist to use.

``params`` is edited through :class:`gui.param_form.ParamForm`: one
labelled row per parameter known to _KIND_PARAM_SPECS (unit in the field,
full description in the tooltip, a checkbox on each optional parameter),
plus a collapsed "Advanced" JSON box for any other key. The schema keeps
``params`` an open dict (see ``schema.scenario.SensorConfig``'s
docstring), so that JSON box is what keeps a key this module doesn't
know yet editable. Real user feedback replaced the earlier layout (a
cramped bullet-list reference over a JSON box, and the device information
as raw text) with this form and a device card.

User feedback (this app's own beginner testing): a blank ``{}`` JSON box
with zero in-dialog guidance meant a user had to already know -- from
reading ``engine/fsw.py``'s source -- which keys a given kind needs, their
units, and which ones are required vs. optional; a missing required key
(e.g. ``coarse_sun_sensor``'s ``nHat_B``) wasn't caught here either, only
much later when the OUTER spacecraft-editor dialog's
``SpacecraftConfig.validate()`` ran, decontextualized from the params box
that actually needs fixing. Fixed by _KIND_PARAM_SPECS below, which drives:
a per-kind help label, a "Reset to template" button that fills the params
box with a working example for the selected kind, and an immediate
required-key check right in this dialog. Keep _KIND_PARAM_SPECS in sync
with ``engine.fsw.attach_sensors()``/``build_reaction_wheels()``'s actual
``params.get()``/``params[...]`` usage when either changes.

Further user feedback specifically on "placement" of sensors/actuators:
every kind's body-frame direction (``nHat_B``, ``gsHat_B``, ``noise_std_
tesla``'s per-axis triple) used to be a bare 3-element JSON array typed
inside the params box, the one thing about "placement" that actually
affects the simulated physics here (Basilisk's coarseSunSensor/
reactionWheel models care about boresight/spin-axis DIRECTION -- there is
no position/mounting-offset or self-shadowing physics in the specific
Basilisk modules this app wires up, so a position field for these would be
cosmetic, not physical; :class:`schema.scenario.PowerConfig`'s
``panel_normal_b`` already got its own X/Y/Z spin boxes in
``gui.spacecraft_editor`` since Phase 1 -- see that dialog -- sensors/
actuators just hadn't caught up). Fixed: any 3-element-list-valued spec in
_KIND_PARAM_SPECS now gets its own X/Y/Z spin-box row (with a Normalize
button, since these are meant to be unit vectors and Basilisk does not
renormalize them), separate from the JSON box, which now only holds the
kind's non-vector keys.
"""

from __future__ import annotations

import html
import re
from typing import NamedTuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
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

from ..engine.device_catalog import catalog_entries_for_kind
from .feedback import clear_invalid, mark_invalid, show_toast
from .param_form import ParamForm
from .theme import PALETTE
from .widgets import ComboBox


class _ParamSpec(NamedTuple):
    key: str
    required: bool
    example: object
    help_text: str  # includes units, where the quantity has physical meaning
    # True for a direction (nHat_B, gsHat_B, tHat_B, ...), where "Normalize"
    # (rescale to unit length, preserving direction) is a meaningful, safe
    # action. False for a 3-element vector that ISN'T a direction -- a
    # position like thruster r_B [m], or a per-axis quantity like
    # magnetometer noise_std_tesla [T] -- where clicking Normalize would
    # silently corrupt the value (e.g. rescale a thruster's location to
    # exactly 1 meter from the body origin). Found while adding "thruster"
    # below: r_B needed its own vector row (same X/Y/Z treatment as every
    # other 3-element param) but must NOT offer Normalize, which this
    # module previously offered unconditionally on every 3-element spec --
    # also fixes the same latent bug already present on magnetometer's
    # noise_std_tesla.
    normalizable: bool = True
    label: str = ""  # short form-row label; filled from _PARAM_LABELS below

    @property
    def is_vector(self) -> bool:
        return isinstance(self.example, list) and len(self.example) == 3


# One entry per SUPPORTED_SENSOR_KINDS/SUPPORTED_ACTUATOR_KINDS value that
# engine.fsw actually builds.
_KIND_PARAM_SPECS: dict[str, list[_ParamSpec]] = {
    "star_tracker": [
        _ParamSpec("noise_arcsec", False, 0.0, "1-sigma attitude noise [arcsec]"),
        # Device-interface realism (real user feedback: "the user should
        # be able to... select from a range of commonly used devices...
        # with faults/saturation/encoders"). All real, Basilisk-native
        # StarTracker/ImuSensor/CoarseSunSensor/Magnetometer fields
        # (StarTracker.walkBounds, ImuSensor.senRotBias/senTransBias/
        # senRotMax/senTransMax/setLSBs, CoarseSunSensor.senBias/
        # maxOutput/minOutput/faultState, Magnetometer.senBias/
        # maxOutput/minOutput/setFaultState/stuckValue/spikeProbability/
        # spikeAmount) -- applied automatically by Basilisk's own
        # UpdateState() every tick once set, exactly like the
        # noise_arcsec/noise_std/etc. fields above, so there is no
        # separate "enable" flag to also set.
        _ParamSpec("bias_walk_bound_arcsec", False, 0.0, "long-run random-walk BOUND on the noise above "
                    "[arcsec] -- 0 (default) means no bounded long-term drift is modeled, only the "
                    "per-tick noise"),
    ],
    "imu": [
        _ParamSpec("gyro_noise_rad_s", False, 0.0, "1-sigma gyro noise [rad/s]"),
        _ParamSpec("accel_noise_m_s2", False, 0.0, "1-sigma accelerometer noise [m/s^2]"),
        _ParamSpec("gyro_bias_rad_s", False, [0.0, 0.0, 0.0], "fixed per-axis gyro bias [rad/s]",
                    normalizable=False),
        _ParamSpec("accel_bias_m_s2", False, [0.0, 0.0, 0.0], "fixed per-axis accelerometer bias [m/s^2]",
                    normalizable=False),
        _ParamSpec("gyro_saturation_rad_s", False, 1000000.0, "gyro output saturation magnitude [rad/s] -- "
                    "effectively unbounded by default"),
        _ParamSpec("accel_saturation_m_s2", False, 1000000.0, "accelerometer output saturation magnitude "
                    "[m/s^2] -- effectively unbounded by default"),
        _ParamSpec("gyro_lsb_rad_s", False, 0.0, "gyro encoder/ADC quantization step size [rad/s] -- 0 "
                    "(default) means effectively continuous, no quantization"),
        _ParamSpec("accel_lsb_m_s2", False, 0.0, "accelerometer encoder/ADC quantization step size "
                    "[m/s^2] -- 0 (default) means effectively continuous, no quantization"),
    ],
    "coarse_sun_sensor": [
        _ParamSpec("nHat_B", True, [1.0, 0.0, 0.0], "sensor boresight direction, body frame, unit vector [-]"),
        _ParamSpec("fov_deg", False, 90.0, "full field of view [deg]"),
        _ParamSpec("noise_std", False, 0.0, "1-sigma output noise (cosine-law output units) [-]"),
        _ParamSpec("bias", False, 0.0, "fixed sensor bias (cosine-law output units) [-]"),
        _ParamSpec("saturation_max", False, 1000000.0, "output saturation upper bound (cosine-law output "
                    "units) [-] -- effectively unbounded by default"),
        _ParamSpec("saturation_min", False, 0.0, "output saturation lower bound (cosine-law output "
                    "units) [-]"),
        _ParamSpec("fault_mode", False, "none", "hardware fault to simulate: 'none' / 'stuck_current' "
                    "(freezes at the last real reading) / 'stuck_max' (freezes at saturation_max) / "
                    "'stuck_rand' (freezes at one random value for the whole run) / 'random' (every "
                    "sample replaced with fresh noise of fault_noise_std)"),
        _ParamSpec("fault_noise_std", False, 0.0, "noise std dev used only when fault_mode='random' [-]"),
    ],
    "magnetometer": [
        _ParamSpec("noise_std_tesla", False, [0.0, 0.0, 0.0], "1-sigma noise per body axis [T]",
                    normalizable=False),
        _ParamSpec("bias_tesla", False, [0.0, 0.0, 0.0], "fixed per-axis bias [T]", normalizable=False),
        _ParamSpec("saturation_tesla", False, 1000000.0, "symmetric output saturation magnitude [T] "
                    "(clips at +/- this value) -- effectively unbounded by default"),
        _ParamSpec("fault_mode", False, "none", "hardware fault to simulate on fault_axis below: 'none' "
                    "/ 'stuck_current' (freezes at the last real reading) / 'stuck_value' (freezes at "
                    "stuck_value_tesla) / 'spiking' (randomly multiplies the true reading by "
                    "spike_amount with probability spike_probability each tick)"),
        _ParamSpec("fault_axis", False, 0, "which body axis (0/1/2) fault_mode above applies to -- a "
                    "real single-axis sensor-element failure does not take out the other two axes"),
        _ParamSpec("stuck_value_tesla", False, 0.0, "value fault_axis freezes at when fault_mode="
                    "'stuck_value' [T]"),
        _ParamSpec("spike_probability", False, 0.1, "per-tick probability of a spike when fault_mode="
                    "'spiking' [-]"),
        _ParamSpec("spike_amount", False, 2.0, "multiplier applied to the true reading on a spike when "
                    "fault_mode='spiking' [-]"),
    ],
    "reaction_wheel": [
        _ParamSpec("gsHat_B", True, [0.0, 0.0, 1.0], "spin-axis direction, body frame, unit vector [-]"),
        _ParamSpec("rw_type", False, "custom",
                    "wheel model name known to Basilisk's simIncludeRW.rwFactory(), e.g. 'Honeywell_HR16'"),
        _ParamSpec("Omega_max", False, 6000.0, "max wheel speed [RPM]"),
        _ParamSpec("u_max", False, 0.2, "max motor torque [N*m]"),
        _ParamSpec("Js", False, 0.028, "wheel inertia about the spin axis [kg*m^2] -- rw_type='custom' can "
                    "derive this from maxMomentum [N*m*s] instead, but NOT both: rwFactory.create() hard"
                    "-exits the whole process if Js and maxMomentum are both set"),
        # Device-interface realism: real simIncludeRW.rwFactory() kwargs,
        # already passed straight through by this app's own
        # engine.fsw._coerce_rw_kwargs() -- these were already wired, just
        # not previously surfaced here for discovery.
        _ParamSpec("useRWfriction", False, False, "enable the internal wheel friction model below -- off "
                    "by default, matching simIncludeRW's own default"),
        _ParamSpec("fCoulomb", False, 0.0, "Coulomb (constant-magnitude) friction torque [N*m] -- only "
                    "applied when useRWfriction is true"),
        _ParamSpec("fStatic", False, 0.0, "static friction torque magnitude [N*m] -- only applied when "
                    "useRWfriction is true"),
        _ParamSpec("cViscous", False, 0.0, "viscous friction coefficient [N*m*s/rad] -- only applied "
                    "when useRWfriction is true"),
        _ParamSpec("betaStatic", False, -1.0, "Stribeck friction coefficient [-] -- positive enables "
                    "Stribeck friction, negative (default) disables it; only relevant when "
                    "useRWfriction is true"),
        # Thermal simulation: an OPTIONAL motor-thermal model
        # (motorThermal.MotorThermal) -- an all-or-nothing group (see
        # schema.scenario.SpacecraftConfig.validate()'s own
        # motor_thermal_* check): set NONE of these four for no thermal
        # model on this wheel (the default, and the common case), or ALL
        # four together to add one. motor_thermal_ambient_temp_c (not
        # listed as its own row -- it has a real 0 C Basilisk-side default
        # and is independently optional even within this group) can still
        # be added by hand in the params box below if needed.
        _ParamSpec("motor_thermal_initial_temp_c", False, 20.0, "starting motor temperature [C] -- set this "
                    "(together with the other three motor_thermal_* fields below) to enable a motor-thermal "
                    "model for this wheel; leave all four unset for none"),
        _ParamSpec("motor_thermal_efficiency", False, 0.7, "mechanical efficiency [-], strictly between 0 "
                    "and 1 -- motorThermal.MotorThermal rejects 1.0 itself (modeled as a real inefficiency), "
                    "not just values above it"),
        _ParamSpec("motor_thermal_ambient_resistance_w_c", False, 5.0, "thermal resistance to the "
                    "surrounding environment [C/W] -- lower means heat dissipates faster"),
        _ParamSpec("motor_thermal_heat_capacity_j_c", False, 50.0, "motor heat capacity [J/C] -- "
                    "mass * specific heat, e.g. a steel motor's specific heat is about 466 J/kg/C"),
    ],
    "thruster": [
        _ParamSpec("r_B", True, [1.0, 0.0, 0.0], "thruster location, body frame [m]", normalizable=False),
        _ParamSpec("tHat_B", True, [1.0, 0.0, 0.0], "thrust direction, body frame, unit vector [-]"),
        _ParamSpec("MaxThrust", True, 1.0, "maximum thrust [N]"),
        _ParamSpec("thruster_type", False, "Blank_Thruster",
                    "thruster model name known to Basilisk's simIncludeThruster.thrusterFactory(), "
                    "e.g. 'MOOG_Monarc_1' -- 'Blank_Thruster' means no type-specific defaults, use the "
                    "params here as-is"),
        _ParamSpec("steadyIsp", False, 220.0, "fuel efficiency [s]"),
        _ParamSpec("MinOnTime", False, 0.020, "minimum on time [s]"),
        # Device-interface realism: a real simIncludeThruster.thrusterFactory()
        # kwarg, already passed straight through by this app's own
        # engine.fsw._coerce_thruster_kwargs() -- already wired, just not
        # previously surfaced here for discovery.
        _ParamSpec("thrusterMagDisp", False, 0.0, "thrust-magnitude manufacturing/performance dispersion, "
                    "applied once at build time [%]"),
    ],
    "magnetic_torque_rod": [
        _ParamSpec("gtHat_B", True, [1.0, 0.0, 0.0], "dipole-axis direction, body frame, unit vector [-]"),
        _ParamSpec("max_dipole_a_m2", True, 0.1, "maximum commandable dipole magnitude [A*m^2]"),
    ],
    # Thermal simulation: models the temperature of ANY flat-plate
    # component (not a specific physical device the way the other kinds
    # above are -- see SUPPORTED_SENSOR_KINDS's own comment), via
    # sensorThermal.SensorThermal, chained into an optional
    # tempMeasurement.TempMeasurement measurement-noise/fault layer below
    # (same device-interface-realism shape as every other sensor kind).
    "thermal": [
        _ParamSpec("nHat_B", True, [0.0, 0.0, 1.0], "face-normal direction, body frame, unit vector [-]"),
        _ParamSpec("area_m2", True, 1.0, "radiative surface area [m^2]"),
        _ParamSpec("absorptivity", True, 0.25, "absorptivity coefficient (0, 1] [-]"),
        _ParamSpec("emissivity", True, 0.34, "emissivity coefficient (0, 1] [-]"),
        _ParamSpec("mass_kg", False, 2.0, "mass [kg] -- defaults to 1 kg if unset"),
        _ParamSpec("specific_heat_j_kg_k", False, 890.0, "specific heat [J/kg/K] -- defaults to 890 "
                    "(aluminum) if unset"),
        _ParamSpec("initial_temp_c", False, 0.0, "starting temperature [C] -- defaults to 30 C if unset"),
        _ParamSpec("power_draw_w", False, 0.0, "internal power dissipated as heat [W] -- 0 (default) means "
                    "none"),
        _ParamSpec("measurement_bias_c", False, 0.0, "fixed measurement bias, always added [C] -- 0 "
                    "(default) means none"),
        _ParamSpec("measurement_noise_std_c", False, 0.0, "1-sigma measurement noise [C] -- 0 (default) "
                    "means none"),
        _ParamSpec("measurement_walk_bound_c", False, 0.0, "long-run random-walk BOUND on the noise above "
                    "[C] -- 0 (default) means no bounded long-term drift is modeled"),
        _ParamSpec("measurement_fault_mode", False, "none", "hardware fault to simulate: 'none' / "
                    "'stuck_current' (freezes at the last real reading) / 'stuck_value' (freezes at "
                    "measurement_stuck_value_c) / 'spiking' (randomly multiplies the reading by "
                    "measurement_spike_amount with probability measurement_spike_probability each tick)"),
        _ParamSpec("measurement_stuck_value_c", False, 0.0, "value measurement_fault_mode='stuck_value' "
                    "freezes at [C]"),
        _ParamSpec("measurement_spike_probability", False, 0.1, "per-tick probability of a spike when "
                    "measurement_fault_mode='spiking' [-]"),
        _ParamSpec("measurement_spike_amount", False, 2.0, "multiplier applied to the reading on a spike "
                    "when measurement_fault_mode='spiking' [-]"),
    ],
}

# Short form-row labels (the full description stays in each row's
# tooltip). Keyed by (kind, key) so the same key can read differently per
# kind; a missing entry falls back to the start of the help text.
_PARAM_LABELS: dict[tuple[str, str], str] = {
    ("star_tracker", "noise_arcsec"): "Attitude noise (1-sigma)",
    ("star_tracker", "bias_walk_bound_arcsec"): "Bias random-walk bound",
    ("imu", "gyro_noise_rad_s"): "Gyro noise (1-sigma)",
    ("imu", "accel_noise_m_s2"): "Accel. noise (1-sigma)",
    ("imu", "gyro_bias_rad_s"): "Gyro bias",
    ("imu", "accel_bias_m_s2"): "Accel. bias",
    ("imu", "gyro_saturation_rad_s"): "Gyro saturation",
    ("imu", "accel_saturation_m_s2"): "Accel. saturation",
    ("imu", "gyro_lsb_rad_s"): "Gyro quantization step",
    ("imu", "accel_lsb_m_s2"): "Accel. quantization step",
    ("coarse_sun_sensor", "nHat_B"): "Boresight direction",
    ("coarse_sun_sensor", "fov_deg"): "Field of view (full)",
    ("coarse_sun_sensor", "noise_std"): "Output noise (1-sigma)",
    ("coarse_sun_sensor", "bias"): "Output bias",
    ("coarse_sun_sensor", "saturation_max"): "Saturation, upper",
    ("coarse_sun_sensor", "saturation_min"): "Saturation, lower",
    ("coarse_sun_sensor", "fault_mode"): "Fault mode",
    ("coarse_sun_sensor", "fault_noise_std"): "Fault noise (random mode)",
    ("magnetometer", "noise_std_tesla"): "Noise per axis (1-sigma)",
    ("magnetometer", "bias_tesla"): "Bias per axis",
    ("magnetometer", "saturation_tesla"): "Saturation",
    ("magnetometer", "fault_mode"): "Fault mode",
    ("magnetometer", "fault_axis"): "Fault axis (0, 1 or 2)",
    ("magnetometer", "stuck_value_tesla"): "Stuck value",
    ("magnetometer", "spike_probability"): "Spike probability per tick",
    ("magnetometer", "spike_amount"): "Spike multiplier",
    ("reaction_wheel", "gsHat_B"): "Spin axis",
    ("reaction_wheel", "rw_type"): "Wheel model",
    ("reaction_wheel", "Omega_max"): "Max wheel speed",
    ("reaction_wheel", "u_max"): "Max motor torque",
    ("reaction_wheel", "Js"): "Rotor inertia (spin axis)",
    ("reaction_wheel", "useRWfriction"): "Friction model",
    ("reaction_wheel", "fCoulomb"): "Coulomb friction",
    ("reaction_wheel", "fStatic"): "Static friction",
    ("reaction_wheel", "cViscous"): "Viscous friction",
    ("reaction_wheel", "betaStatic"): "Stribeck coefficient",
    ("reaction_wheel", "motor_thermal_initial_temp_c"): "Motor start temperature",
    ("reaction_wheel", "motor_thermal_efficiency"): "Motor efficiency",
    ("reaction_wheel", "motor_thermal_ambient_resistance_w_c"): "Motor thermal resistance",
    ("reaction_wheel", "motor_thermal_heat_capacity_j_c"): "Motor heat capacity",
    ("thruster", "r_B"): "Location",
    ("thruster", "tHat_B"): "Thrust direction",
    ("thruster", "MaxThrust"): "Max thrust",
    ("thruster", "thruster_type"): "Thruster model",
    ("thruster", "steadyIsp"): "Specific impulse",
    ("thruster", "MinOnTime"): "Minimum on-time",
    ("thruster", "thrusterMagDisp"): "Thrust dispersion",
    ("magnetic_torque_rod", "gtHat_B"): "Dipole axis",
    ("magnetic_torque_rod", "max_dipole_a_m2"): "Max dipole",
    ("thermal", "nHat_B"): "Face normal",
    ("thermal", "area_m2"): "Radiating area",
    ("thermal", "absorptivity"): "Absorptivity (0-1)",
    ("thermal", "emissivity"): "Emissivity (0-1)",
    ("thermal", "mass_kg"): "Mass",
    ("thermal", "specific_heat_j_kg_k"): "Specific heat",
    ("thermal", "initial_temp_c"): "Start temperature",
    ("thermal", "power_draw_w"): "Internal heat",
    ("thermal", "measurement_bias_c"): "Sensor bias",
    ("thermal", "measurement_noise_std_c"): "Sensor noise (1-sigma)",
    ("thermal", "measurement_walk_bound_c"): "Sensor bias-walk bound",
    ("thermal", "measurement_fault_mode"): "Sensor fault mode",
    ("thermal", "measurement_stuck_value_c"): "Sensor stuck value",
    ("thermal", "measurement_spike_probability"): "Spike probability per tick",
    ("thermal", "measurement_spike_amount"): "Spike multiplier",
}
_KIND_PARAM_SPECS = {
    kind: [spec._replace(label=_PARAM_LABELS.get((kind, spec.key), "")) for spec in specs]
    for kind, specs in _KIND_PARAM_SPECS.items()
}

# Schema-valid (SUPPORTED_ACTUATOR_KINDS) but engine.fsw/engine.service
# raise a specific error if actually configured -- see
# schema.scenario.SUPPORTED_ACTUATOR_KINDS's module-level docstring note.
# Selectable here (so a saved scenario file using one can still be
# opened/edited), but flagged with an in-dialog warning rather than
# letting a beginner discover this only when Run Simulation fails. Empty
# now -- every SUPPORTED_ACTUATOR_KINDS value is wired up by engine.fsw
# (see _CONDITIONAL_ACTUATOR_NOTES below for "magnetic_torque_rod"'s own
# extra requirement, which is a condition, not an "unimplemented" gap).
_UNIMPLEMENTED_ACTUATOR_KINDS = ()

# A kind that IS wired up, but only in a specific role with its own extra
# requirement beyond "needs these params" -- shown as an additional note
# above the normal param hint, not a warning that it's unsimulated.
_CONDITIONAL_ACTUATOR_NOTES = {
    "magnetic_torque_rod": (
        "Used only to unload reaction wheels: turn on Magnetic momentum management (Power / propulsion "
        "tab) and add a reaction wheel."
    ),
}


def _template_params(kind: str) -> dict:
    return {spec.key: spec.example for spec in _KIND_PARAM_SPECS.get(kind, [])}


def _missing_required_keys(kind: str, params: dict) -> list[str]:
    return [spec.key for spec in _KIND_PARAM_SPECS.get(kind, []) if spec.required and spec.key not in params]


def _hint_text(kind: str) -> str:
    """Notes/warnings for a kind (shown as a banner only when there are
    any) -- the per-parameter reference itself is now the form's own
    labels, units and tooltips."""
    if kind in _UNIMPLEMENTED_ACTUATOR_KINDS:
        return (
            f"⚠ {kind!r} is schema-valid but not simulated yet -- engine.service will raise an error at "
            "Run Simulation if this actuator is actually configured on a spacecraft with fsw_mode set. "
            "Pick 'reaction_wheel' for a working actuator."
        )
    note = _CONDITIONAL_ACTUATOR_NOTES.get(kind)
    return f"ℹ {note}" if note else ""


_STATUS_COLORS = {"RFI priority": "success", "RFI": "warning", "Candidate": "text_muted",
                  "Check": "danger", "Development": "warning"}


def _readable_param_names(kind: str, text: str) -> str:
    """``text`` with this kind's parameter keys (``noise_arcsec``) replaced
    by the form's own labels ("Attitude noise (1-sigma)"), so a device
    card reads in the same words as the form beside it."""
    for spec in sorted(_KIND_PARAM_SPECS.get(kind, []), key=lambda s: -len(s.key)):
        if spec.label:
            text = re.sub(rf"(?<![\w.]){re.escape(spec.key)}(?![\w])", spec.label, text)
    return text


def _device_card_html(entry) -> str:
    """A catalog device as a structured card: name, summary, labelled facts
    and small-print conversion notes (real user feedback: the old plain-text
    dump looked "unclear, confusing, all over the place and not
    professional")."""
    esc = html.escape
    status_color = next((PALETTE[color] for prefix, color in _STATUS_COLORS.items()
                         if entry.procurement_status.startswith(prefix)), PALETTE["text_muted"])
    rows = [
        ("Heritage", esc(entry.heritage)),
        ("Procurement", f"<span style='color:{status_color}; font-weight:600;'>"
                        f"{esc(entry.procurement_status)}</span>"),
        ("Export control", esc(entry.itar_free_note)),
        ("Source", f"<a href='{esc(entry.source_url)}'>{esc(entry.source_url)}</a>"),
    ]
    table = "".join(
        f"<tr><td style='color:{PALETTE['text_muted']}; padding:2px 10px 2px 0; white-space:nowrap;'"
        f" valign='top'>{label}</td><td style='padding:2px 0;'>{value}</td></tr>"
        for label, value in rows if value)
    notes = (f"<p style='color:{PALETTE['text_muted']}; margin-top:8px;'>"
             f"<b>How the values were set:</b> {esc(_readable_param_names(entry.kind, entry.notes))}</p>"
             if entry.notes else "")
    return (f"<p style='font-size:115%; font-weight:600; margin:0;'>{esc(entry.manufacturer)} "
            f"{esc(entry.product_name)}</p>"
            f"<p style='color:{PALETTE['text_muted']}; margin:0 0 6px 0;'>{esc(entry.country)}</p>"
            f"<p style='margin:0 0 6px 0;'>{esc(entry.description)}</p>"
            f"<table cellspacing='0'>{table}</table>{notes}")


class _ItemEditorDialog(QDialog):
    """Edit one sensor or actuator: Kind and Name, an optional real device
    from the catalog (shown as a card beside the form), and a form with
    one labelled field per parameter of the kind -- units in the field,
    the full description in its tooltip, and a checkbox on each OPTIONAL
    parameter (unchecked = Basilisk's own default). Parameters the form
    doesn't know are kept in a collapsed "Advanced" JSON box.

    Real user feedback drove this layout: the old dialog crammed a
    bullet-list parameter reference into a small scroll box, dumped the
    device information as raw text, and took most parameters as raw JSON.
    """

    def __init__(self, item_cls, kind_choices, item=None, parent: QWidget | None = None,
                 other_names: list[str] | None = None):
        super().__init__(parent)
        self._item_cls = item_cls
        self._other_names = other_names or []
        # Per-kind snapshot of the form, so switching Kind away and back
        # never loses an edit (only Reset to template may).
        self._kind_params: dict[str, dict] = {}
        if item is not None:
            self._kind_params[item.kind] = dict(item.params)
        self._item_params = dict(item.params) if item is not None else {}
        label = "sensor" if item_cls.__name__ == "SensorConfig" else "actuator"
        self.setWindowTitle(f"Edit {label}" if item is not None else f"New {label}")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        top = QFormLayout()
        self.kind_combo = ComboBox()
        self.kind_combo.setToolTip("Which kind of hardware this is: it sets the parameters below.")
        self.kind_combo.addItems(list(kind_choices))
        if item is not None:
            index = self.kind_combo.findText(item.kind)
            if index >= 0:
                self.kind_combo.setCurrentIndex(index)
        top.addRow("Kind", self.kind_combo)
        self.name_edit = QLineEdit(item.name if item is not None else "")
        self.name_edit.textChanged.connect(self._on_name_changed)
        top.addRow("Name", self.name_edit)
        layout.addLayout(top)

        self.hint_label = QLabel()
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(f"background: {PALETTE['accent_soft']}; border-radius: 4px; padding: 6px;")
        layout.addWidget(self.hint_label)

        body = QHBoxLayout()
        body.setSpacing(14)

        # Left: the catalog picker and the selected device's card.
        self._catalog_container = QWidget()
        catalog_layout = QVBoxLayout(self._catalog_container)
        catalog_layout.setContentsMargins(0, 0, 0, 0)
        catalog_title = QLabel("Start from a real device")
        catalog_title.setStyleSheet("font-weight: 600;")
        catalog_layout.addWidget(catalog_title)
        self.catalog_combo = ComboBox()
        self.catalog_combo.setToolTip("A real, commercially available device for this kind. Its card "
                                      "appears below; Apply fills the parameters with its values.")
        self.catalog_combo.currentIndexChanged.connect(self._on_catalog_selection_changed)
        catalog_layout.addWidget(self.catalog_combo)
        self.apply_catalog_button = QPushButton("Apply device values")
        self.apply_catalog_button.setToolTip("Fill the parameters with the selected device's values "
                                             "(overwrites the current ones).")
        self.apply_catalog_button.clicked.connect(self._on_apply_catalog_entry)
        catalog_layout.addWidget(self.apply_catalog_button)
        self.catalog_info_label = QLabel()
        self.catalog_info_label.setWordWrap(True)
        self.catalog_info_label.setTextFormat(Qt.TextFormat.RichText)
        self.catalog_info_label.setOpenExternalLinks(True)
        self.catalog_info_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.catalog_info_label.setContentsMargins(10, 8, 10, 8)
        card = QFrame()
        card.setObjectName("deviceCard")
        card.setStyleSheet(f"QFrame#deviceCard {{ background: {PALETTE['surface']}; "
                           f"border: 1px solid {PALETTE['border']}; border-radius: 6px; }}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(self.catalog_info_label)
        card_scroll = QScrollArea()
        card_scroll.setWidgetResizable(True)
        card_scroll.setFrameShape(QFrame.Shape.NoFrame)
        card_scroll.setWidget(card)
        self._card_scroll = card_scroll
        catalog_layout.addWidget(card_scroll, 1)
        self._catalog_container.setFixedWidth(340)
        body.addWidget(self._catalog_container)

        # Right: the parameter form.
        params_column = QVBoxLayout()
        params_header = QHBoxLayout()
        params_title = QLabel("Parameters")
        params_title.setStyleSheet("font-weight: 600;")
        params_header.addWidget(params_title)
        params_header.addStretch(1)
        self.reset_template_button = QPushButton("Reset to template")
        self.reset_template_button.setToolTip("Required parameters back to a working example; optional "
                                              "ones back to their defaults.")
        self.reset_template_button.clicked.connect(self._on_reset_template)
        params_header.addWidget(self.reset_template_button)
        params_column.addLayout(params_header)
        legend = QLabel("Optional parameters use Basilisk's default unless ticked. Hover a name for details.")
        legend.setWordWrap(True)
        legend.setStyleSheet(f"color: {PALETTE['text_muted']};")
        params_column.addWidget(legend)
        self.param_form = ParamForm()
        form_holder = QWidget()
        holder_layout = QVBoxLayout(form_holder)
        holder_layout.setContentsMargins(4, 4, 4, 4)
        holder_layout.addWidget(self.param_form)
        holder_layout.addStretch(1)
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_scroll.setWidget(form_holder)
        params_column.addWidget(form_scroll, 1)
        body.addLayout(params_column, 1)
        layout.addLayout(body, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._current_kind = self.kind_combo.currentText()
        initial = (dict(item.params) if item is not None
                   else self._default_params(self._current_kind))
        self._build_form(self._current_kind, initial)
        self._rebuild_catalog_row(self._current_kind)
        self._update_hint(self._current_kind)
        self.kind_combo.currentTextChanged.connect(self._on_kind_changed)
        self.resize(self.sizeHint().expandedTo(QSize(980, 640)))  # [px]

    # -- form ----------------------------------------------------------
    @staticmethod
    def _default_params(kind: str) -> dict:
        """A working starting point: every REQUIRED parameter at its example."""
        return {spec.key: spec.example for spec in _KIND_PARAM_SPECS.get(kind, []) if spec.required}

    @property
    def params_edit(self) -> QPlainTextEdit:
        """The collapsed "Advanced" JSON box (keys the form doesn't cover)."""
        return self.param_form.params_edit

    @property
    def _vector_boxes(self) -> dict:
        return self.param_form.vector_boxes

    def _build_form(self, kind: str, params: dict) -> None:
        self.param_form.set_specs(_KIND_PARAM_SPECS.get(kind, []), params,
                                  empty_text="This kind has no parameters.")

    def _update_hint(self, kind: str) -> None:
        text = _hint_text(kind)
        self.hint_label.setText(text)
        self.hint_label.setVisible(bool(text))

    def _on_kind_changed(self, kind: str) -> None:
        try:
            self._kind_params[self._current_kind] = self.param_form.params()
        except ValueError:
            pass  # unparseable advanced JSON: just don't snapshot it
        self._current_kind = kind
        self._build_form(kind, self._kind_params.get(kind, self._default_params(kind)))
        self._rebuild_catalog_row(kind)
        self._update_hint(kind)

    # -- catalog -------------------------------------------------------
    def _rebuild_catalog_row(self, kind: str) -> None:
        entries = catalog_entries_for_kind(kind)
        self._catalog_container.setVisible(bool(entries))
        self.catalog_combo.blockSignals(True)
        self.catalog_combo.clear()
        self.catalog_combo.addItem("-- none (custom values) --")
        for entry in entries:
            self.catalog_combo.addItem(entry.display_name)
        self.catalog_combo.setCurrentIndex(0)
        self.catalog_combo.blockSignals(False)
        self._current_catalog_entries = entries
        self._on_catalog_selection_changed(0)

    def _on_catalog_selection_changed(self, index: int) -> None:
        entries = getattr(self, "_current_catalog_entries", [])
        if index <= 0 or index - 1 >= len(entries):
            self.catalog_info_label.setText("")
            self._card_scroll.setVisible(False)
            self.apply_catalog_button.setEnabled(False)
            return
        entry = entries[index - 1]
        self._card_scroll.setVisible(True)
        self.apply_catalog_button.setEnabled(True)
        self.catalog_info_label.setText(_device_card_html(entry))

    def _on_apply_catalog_entry(self) -> None:
        entries = getattr(self, "_current_catalog_entries", [])
        index = self.catalog_combo.currentIndex()
        if index <= 0 or index - 1 >= len(entries):
            return
        entry = entries[index - 1]
        params = {**self._default_params(entry.kind), **entry.params}
        self._build_form(entry.kind, params)

    def _on_reset_template(self) -> None:
        kind = self.kind_combo.currentText()
        self._build_form(kind, self._default_params(kind))

    # -- result --------------------------------------------------------
    def _on_name_changed(self, text: str) -> None:
        """Live inline feedback (see gui.feedback / spacecraft_editor.py's
        own ``_on_name_changed`` for the identical pattern this mirrors)."""
        name = text.strip()
        if not name:
            mark_invalid(self.name_edit, "Name must not be empty")
        elif name in self._other_names:
            mark_invalid(self.name_edit, f"{name!r} already exists")
        else:
            clear_invalid(self.name_edit)

    def _on_accept(self) -> None:
        # Validated here, before closing: a duplicate or empty name used to
        # be noticed only by the caller, after every edit was gone.
        name = self.name_edit.text().strip()
        if not name:
            mark_invalid(self.name_edit, "Name must not be empty")
            self.name_edit.setFocus()
            return
        if name in self._other_names:
            mark_invalid(self.name_edit, f"{name!r} already exists")
            self.name_edit.setFocus()
            return
        try:
            self.to_dataclass()
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid params", str(exc))
            return
        self.accept()

    def to_dataclass(self):
        name = self.name_edit.text().strip()
        if not name:
            raise ValueError("name must not be empty")
        kind = self.kind_combo.currentText()
        params = self.param_form.params()
        missing = _missing_required_keys(kind, params)
        if missing:
            raise ValueError(
                f"{kind!r} is missing required params key(s): {', '.join(missing)} -- "
                "use 'Reset to template' for a working example"
            )
        return self._item_cls(kind=kind, name=name, params=params)


class SensorActuatorListWidget(QWidget):
    """A list of :class:`SensorConfig` or :class:`ActuatorConfig` (pass the
    class and its kind whitelist), with Add/Edit/Remove -- mirrors
    :class:`gui.spacecraft_editor.SpacecraftListWidget`'s shape.
    """

    changed = Signal()

    def __init__(self, item_cls, kind_choices, parent: QWidget | None = None):
        super().__init__(parent)
        self._item_cls = item_cls
        self._kind_choices = kind_choices
        self._items: list = []

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

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for item in self._items:
            self.list_widget.addItem(QListWidgetItem(f"{item.kind}: {item.name}"))

    def _existing_names(self, exclude_row: int | None = None) -> set:
        return {item.name for i, item in enumerate(self._items) if i != exclude_row}

    def _on_add(self) -> None:
        dialog = _ItemEditorDialog(self._item_cls, self._kind_choices, parent=self,
                                    other_names=sorted(self._existing_names()))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_item = dialog.to_dataclass()
            if new_item.name in self._existing_names():
                QMessageBox.critical(self, "Duplicate name", f"{new_item.name!r} already exists.")
                return
            self._items.append(new_item)
            self._refresh_list()
            self.list_widget.setCurrentRow(len(self._items) - 1)
            show_toast(self.window(), f"Added {new_item.kind}: {new_item.name!r}")
            self.changed.emit()

    def _on_edit(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        dialog = _ItemEditorDialog(self._item_cls, self._kind_choices, item=self._items[row], parent=self,
                                    other_names=sorted(self._existing_names(exclude_row=row)))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_item = dialog.to_dataclass()
            if new_item.name in self._existing_names(exclude_row=row):
                QMessageBox.critical(self, "Duplicate name", f"{new_item.name!r} already exists.")
                return
            self._items[row] = new_item
            self._refresh_list()
            self.list_widget.setCurrentRow(row)
            show_toast(self.window(), f"Updated {new_item.kind}: {new_item.name!r}")
            self.changed.emit()

    def _on_remove(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        item = self._items[row]
        del self._items[row]
        self._refresh_list()
        show_toast(self.window(), f"Removed {item.kind}: {item.name!r}", kind="info")
        self.changed.emit()

    def to_list(self) -> list:
        return list(self._items)

    def from_list(self, items: list) -> None:
        self._items = list(items)
        self._refresh_list()
