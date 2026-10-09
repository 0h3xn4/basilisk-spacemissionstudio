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

"""Where each exported value comes from: the scenario field, the GUI
control that edits it, or the tool's fixed choice in ``engine.fsw``.

The generator writes this into the export's traceability table (GUI
parameter -> scenario path -> config symbol -> source file). A module
field that is not listed here keeps the value the Basilisk module starts
with (its constructor zeroes the configuration struct), which the table
says.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

_EDITOR = "Spacecraft editor"
_POINTING = f"{_EDITOR} > Attitude control > Pointing parameters"
_GAINS = f"{_EDITOR} > Attitude control > Control gains (MRP feedback)"
_DUMPING = f"{_EDITOR} > Power / propulsion > Momentum dumping"
_MTB = f"{_EDITOR} > Sensors / actuators > Magnetic momentum management"


@dataclass(frozen=True)
class Source:
    scenario_path: Optional[str]  # under spacecraft[<name>]; None for the tool's own constant
    gui: str  # where the user edits it, or "-"
    note: str = ""


MODULE_FIELDS: Dict[Tuple[str, str], Source] = {
    ("inertial3D", "sigma_R0N"): Source("fsw_params.sigma_R0N", f"{_POINTING}: Target attitude (MRP)"),
    ("velocityPoint", "mu"): Source(None, "-", "gravitational parameter of gravity.central_body (Basilisk)"),
    ("sunSafePoint", "sHatBdyCmd"): Source("fsw_params.sHatBdyCmd", f"{_POINTING}: Axis to point at the Sun"),
    ("sunSafePoint", "minUnitMag"): Source("fsw_params.min_unit_mag", f"{_POINTING}: Min. sun-sensor signal"),
    ("sunSafePoint", "sunAxisSpinRate"): Source("fsw_params.sun_axis_spin_rate_rad_s",
                                                f"{_POINTING}: Spin rate about the Sun axis"),
    ("locationPointing", "pHat_B"): Source("fsw_params.pHat_B", f"{_POINTING}: Pointing axis"),
    ("locationPointing", "useBoresightRateDamping"): Source(None, "-", "fixed at 1 by engine.fsw.build_guidance"),
    ("mrpFeedback", "K"): Source("control_params.K", f"{_GAINS}: Attitude gain K",
                                 "when unset: engine.fsw's default, scaled by the inertia"),
    ("mrpFeedback", "P"): Source("control_params.P", f"{_GAINS}: Rate gain P",
                                 "when unset: engine.fsw's default, scaled by the inertia"),
    ("mrpFeedback", "Ki"): Source("control_params.Ki", f"{_GAINS}: Integral gain Ki", "when unset: -1 (off)"),
    ("mrpFeedback", "integralLimit"): Source("control_params.integral_limit", f"{_GAINS}: Integral limit"),
    ("rwMotorTorque", "controlAxes_B"): Source(None, "-", "fixed: all three body axes (engine.fsw)"),
    ("thrForceMapping", "controlAxes_B"): Source(None, "-", "fixed: all three body axes (engine.fsw)"),
    ("thrForceMapping", "thrForceSign"): Source(None, "-", "fixed at 1 (engine.fsw)"),
    ("thrForceMapping", "angErrThresh"): Source(None, "-", "3.15 for momentum dumping (engine.fsw), else 0"),
    ("thrFiringSchmitt", "thrMinFireTime"): Source(None, "-", "fixed at 0.002 s (engine.fsw)"),
    ("thrFiringSchmitt", "level_on"): Source(None, "-", "fixed at 0.75 (engine.fsw)"),
    ("thrFiringSchmitt", "level_off"): Source(None, "-", "fixed at 0.25 (engine.fsw)"),
    ("thrMomentumManagement", "hs_min"): Source("momentum_dumping.hs_max", f"{_DUMPING}: hs_max"),
    ("thrMomentumDumping", "maxCounterValue"): Source("momentum_dumping.max_counter_value",
                                                      f"{_DUMPING}: max_counter_value"),
    ("thrMomentumDumping", "thrMinFireTime"): Source("momentum_dumping.thr_min_fire_time",
                                                     f"{_DUMPING}: thr_min_fire_time"),
    ("tamComm", "dcm_BS"): Source(None, "-", "fixed: identity (engine.fsw)"),
    ("mtbMomentumManagement", "wheelSpeedBiases"): Source("magnetic_momentum_management.wheel_speed_biases_rad_s",
                                                          f"{_MTB}: wheel speed biases"),
    ("mtbMomentumManagement", "cGain"): Source("magnetic_momentum_management.c_gain", f"{_MTB}: c_gain"),
}

# The fixed configuration messages, by payload type.
CONSTANT_MESSAGES: Dict[str, Source] = {
    "VehicleConfig": Source("inertia_kg_m2", f"{_EDITOR} > Orbit / mass > Principal moments of inertia",
                            "plus each flexible solar array's undeflected inertia (engine.solar_arrays)"),
    "RWArrayConfig": Source("actuators[kind=reaction_wheel].params", f"{_EDITOR} > Sensors / actuators",
                            "through Basilisk's simIncludeRW.rwFactory"),
    "THRArrayConfig": Source("actuators[kind=thruster].params", f"{_EDITOR} > Sensors / actuators",
                             "through Basilisk's simIncludeThruster.thrusterFactory"),
    "MTBArrayConfig": Source("actuators[kind=magnetic_torque_rod].params", f"{_EDITOR} > Sensors / actuators"),
    "CSSConfig": Source("sensors[kind=coarse_sun_sensor].params.nHat_B", f"{_EDITOR} > Sensors / actuators"),
}


def module_field_source(python_name: str, field: str) -> Optional[Source]:
    return MODULE_FIELDS.get((python_name, field))
