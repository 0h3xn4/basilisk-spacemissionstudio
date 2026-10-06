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

"""Tests for engine.service._is_two_body_only -- the (deliberately
conservative) gate deciding when engine.results.conservation_drift_warnings
is even meaningful to run (see that function's own docstring and this
project's docs/ux_audit.md/ux_roadmap.md for the design-philosophy finding
this closes).

Marked ``requires_basilisk`` purely because importing engine.service at
all needs a Basilisk install (module-level ``from Basilisk...`` imports)
-- _is_two_body_only itself is pure schema-object logic, no Basilisk APIs
called, no SimulationService built/run.
"""

import pytest

from spacemissionstudio.schema.command import Command
from spacemissionstudio.schema.scenario import (
    ActuatorConfig,
    ConstantThrustConfig,
    GravityConfig,
    OrbitIC,
    Scenario,
    SpacecraftConfig,
    StationKeepingConfig,
)

pytestmark = pytest.mark.requires_basilisk


def _orbit():
    return OrbitIC(type="cartesian", position_km=[7000.0, 0.0, 0.0], velocity_km_s=[0.0, 7.5, 0.0])


def _scenario(**overrides):
    defaults = dict(
        name="conservation test", epoch_utc="2030-01-01T00:00:00",
        spacecraft=[SpacecraftConfig(name="sat-1", orbit=_orbit())],
    )
    defaults.update(overrides)
    return Scenario(**defaults)


def _is_two_body_only(scenario, sc_config):
    from spacemissionstudio.engine.service import _is_two_body_only as fn

    return fn(scenario, sc_config)


def test_true_for_plain_point_mass_no_perturbers():
    scenario = _scenario()
    assert _is_two_body_only(scenario, scenario.spacecraft[0]) is True


def test_true_with_a_reaction_wheel_actuator():
    # Reaction wheels apply TORQUE only (no net translational force on
    # the center of mass) -- must not disqualify the check, unlike a
    # "thruster" actuator.
    sc = SpacecraftConfig(name="sat-1", orbit=_orbit(), fsw_mode="sunSafePoint",
                            actuators=[ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                                       params={"gsHat_B": [1, 0, 0], "rw_type": "Honeywell_HR16",
                                                               "maxMomentum": 100.0})])
    scenario = _scenario(spacecraft=[sc])
    assert _is_two_body_only(scenario, sc) is True


def test_false_for_nonzero_gravity_degree():
    scenario = _scenario(gravity=GravityConfig(central_body="earth", central_body_degree=10))
    assert _is_two_body_only(scenario, scenario.spacecraft[0]) is False


def test_false_for_third_body_perturbers():
    scenario = _scenario(gravity=GravityConfig(central_body="earth", third_body_perturbers=["sun"]))
    assert _is_two_body_only(scenario, scenario.spacecraft[0]) is False


def test_false_for_enable_drag():
    sc = SpacecraftConfig(name="sat-1", orbit=_orbit(), enable_drag=True)
    scenario = _scenario(spacecraft=[sc])
    assert _is_two_body_only(scenario, sc) is False


def test_false_for_enable_srp():
    sc = SpacecraftConfig(name="sat-1", orbit=_orbit(), enable_srp=True)
    scenario = _scenario(spacecraft=[sc])
    assert _is_two_body_only(scenario, sc) is False


def test_false_for_station_keeping():
    sc = SpacecraftConfig(name="sat-1", orbit=_orbit(), station_keeping=StationKeepingConfig(
        target_altitude_km=500.0, deadband_km=2.0, thrust_n=0.1, isp_s=200.0, propellant_kg=1.0,
    ))
    scenario = _scenario(spacecraft=[sc])
    assert _is_two_body_only(scenario, sc) is False


def test_false_for_constant_thrust():
    sc = SpacecraftConfig(name="sat-1", orbit=_orbit(), constant_thrust=ConstantThrustConfig(
        thrust_n=0.01, frame="VNB", direction=[1.0, 0.0, 0.0], isp_s=1500.0, propellant_kg=0.5,
    ))
    scenario = _scenario(spacecraft=[sc])
    assert _is_two_body_only(scenario, sc) is False


def test_false_for_thruster_actuator():
    sc = SpacecraftConfig(name="sat-1", orbit=_orbit(), fsw_mode="inertial3D",
                            actuators=[ActuatorConfig(kind="thruster", name="t-1",
                                                       params={"r_B": [1, 0, 0], "tHat_B": [1, 0, 0],
                                                               "MaxThrust": 1.0})])
    scenario = _scenario(spacecraft=[sc])
    assert _is_two_body_only(scenario, sc) is False


def test_false_when_mission_sequence_is_present():
    # A maneuver/lambert_transfer command applies a deliberate,
    # instantaneous delta-V -- a real, legitimate "jump" this drift
    # check cannot tell apart from a numerical error, so the whole
    # scenario is excluded, not just the targeted spacecraft.
    scenario = _scenario(mission_sequence=[
        Command(kind="maneuver", params={"spacecraft": "sat-1", "delta_v_m_s": [1.0, 0.0, 0.0]}),
    ])
    assert _is_two_body_only(scenario, scenario.spacecraft[0]) is False
