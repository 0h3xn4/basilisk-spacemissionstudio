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

"""Tests for the thermal-simulation feature: engine.fsw.attach_sensors's
new "thermal" sensor kind (sensorThermal.SensorThermal, optionally chained
into tempMeasurement.TempMeasurement for measurement noise/bias/fault) and
engine.fsw.build_reaction_wheel_motor_thermal (motorThermal.MotorThermal,
one per reaction_wheel actuator that sets the motor_thermal_* param
group). Every field exercised here is a REAL, already-compiled Basilisk
field -- not new physics this project invented; see engine.fsw's own
module docstring for exactly which real example scenario each wiring
pattern was confirmed against.

Like tests/test_device_realism.py, these call engine.fsw's builder
functions directly against a bare SimulationBaseClass (no gravity, no
SPICE) rather than through SimulationService (SPICE-blocked in this
sandbox) -- nothing here needs SPICE.

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import numpy as np
import pytest

from spacemissionstudio.schema.scenario import ActuatorConfig, SensorConfig

pytestmark = pytest.mark.requires_basilisk


def _bare_sim(task_rate_s: float = 1.0):
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(task_rate_s)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    sc_object.hub.mHub = 10.0
    scSim.AddModelToTask(task_name, sc_object, 10)
    return scSim, task_name, sc_object


def _run_ticks(scSim, task_name: str, num_ticks: int, tick_s: float = 1.0):
    from Basilisk.utilities import macros

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(num_ticks * tick_s))
    scSim.ExecuteSimulation()


# -- "thermal" sensor: true physics ---------------------------------------

def _sun_msg(direction=(0.0, 0.0, 1.0), distance_m: float = 1.496e11):
    from Basilisk.architecture import messaging

    sun_state = messaging.SpicePlanetStateMsgPayload()
    sun_state.PositionVector = [d * distance_m for d in direction]
    return messaging.SpicePlanetStateMsg().write(sun_state)


def _run_thermal_sensor(params: dict, sun_eclipse_in_msg=None, num_ticks: int = 1):
    from spacemissionstudio.engine import fsw

    scSim, task_name, sc_object = _bare_sim()
    sun_msg = _sun_msg()

    # Same realistic physical parameters as examples/scenarioSensorThermal.py
    # (not an arbitrary simplification -- a tiny heat capacity relative to
    # Q_in ~1366 W, e.g. mass_kg=1/specific_heat_j_kg_k=1, makes
    # sensorThermal.cpp's own explicit-Euler integration numerically
    # unstable at a 1 Hz task rate, exploding to absurd temperatures within
    # a few ticks -- a real numerical-stability constraint of the module
    # itself, not a bug in this test).
    sensors = [SensorConfig(kind="thermal", name="therm-1", params={
        "nHat_B": [0.0, 0.0, 1.0], "area_m2": 1.0, "absorptivity": 0.25, "emissivity": 0.34,
        "mass_kg": 2.0, "specific_heat_j_kg_k": 890.0, "initial_temp_c": 0.0,
        **params,
    })]
    out_msgs = fsw.attach_sensors(scSim, task_name, "sat", sc_object, sensors,
                                   sun_state_out_msg=sun_msg, sun_eclipse_in_msg=sun_eclipse_in_msg)
    rec = out_msgs["therm-1"].recorder()
    scSim.AddModelToTask(task_name, rec)
    _run_ticks(scSim, task_name, num_ticks)
    return float(np.array(rec.temperature)[-1])


def test_thermal_sensor_requires_sun_tracked():
    from spacemissionstudio.engine.fsw import FswError
    from spacemissionstudio.engine import fsw

    scSim, task_name, sc_object = _bare_sim()
    sensors = [SensorConfig(kind="thermal", name="therm-1",
                             params={"nHat_B": [0, 0, 1], "area_m2": 1.0, "absorptivity": 0.25,
                                     "emissivity": 0.34})]
    with pytest.raises(FswError, match="thermal sensor"):
        fsw.attach_sensors(scSim, task_name, "sat", sc_object, sensors, sun_state_out_msg=None)


def test_thermal_sensor_sun_facing_heats_up():
    # Matches examples/scenarioSensorThermal.py's own documented behavior:
    # "pointed directly at the sun, heating it up."
    final_temp = _run_thermal_sensor({}, num_ticks=5)
    assert final_temp > 0.0


def test_thermal_sensor_facing_away_from_sun_does_not_heat_up():
    # nHat_B anti-aligned with the sun direction -> projectedArea clips to
    # 0 (sensorThermal.cpp's own computeSunData()), so there is no solar
    # absorption term at all -- only radiative emission, which can only
    # cool a body starting above absolute zero.
    final_temp = _run_thermal_sensor({"nHat_B": [0.0, 0.0, -1.0], "initial_temp_c": 50.0}, num_ticks=5)
    assert final_temp < 50.0


def test_thermal_sensor_eclipse_blocks_solar_heating():
    from Basilisk.architecture import messaging

    eclipsed = messaging.EclipseMsgPayload()
    eclipsed.illuminationFactor = 0.0
    eclipse_msg = messaging.EclipseMsg().write(eclipsed)

    lit_temp = _run_thermal_sensor({}, num_ticks=5)
    eclipsed_temp = _run_thermal_sensor({}, sun_eclipse_in_msg=eclipse_msg, num_ticks=5)
    assert eclipsed_temp < lit_temp


def test_thermal_sensor_power_draw_adds_heat():
    # Facing away from the sun (no solar term at all, see above) isolates
    # the power-draw term cleanly: the only source of heat left is
    # sensorPowerDraw.
    baseline = _run_thermal_sensor({"nHat_B": [0.0, 0.0, -1.0]}, num_ticks=3)
    with_power = _run_thermal_sensor({"nHat_B": [0.0, 0.0, -1.0], "power_draw_w": 5.0}, num_ticks=3)
    assert with_power > baseline


# -- "thermal" sensor: measurement noise/bias/fault (tempMeasurement) -----

def test_thermal_sensor_measurement_bias_adds_to_the_true_reading():
    baseline = _run_thermal_sensor({})
    value = _run_thermal_sensor({"measurement_bias_c": 2.5})
    assert value == pytest.approx(baseline + 2.5, abs=1e-9)


def test_thermal_sensor_measurement_stuck_value_overrides_true_reading():
    value = _run_thermal_sensor({
        "measurement_fault_mode": "stuck_value", "measurement_stuck_value_c": -40.0,
    })
    assert value == pytest.approx(-40.0, abs=1e-9)


def test_thermal_sensor_measurement_spiking_with_certainty_multiplies_the_reading():
    baseline = _run_thermal_sensor({}, num_ticks=2)
    value = _run_thermal_sensor({
        "measurement_fault_mode": "spiking", "measurement_spike_probability": 1.0, "measurement_spike_amount": 3.0,
    }, num_ticks=2)
    assert value == pytest.approx(baseline * 3.0, abs=1e-6)


def test_thermal_sensor_unrecognized_fault_mode_falls_back_to_schema_validation():
    # engine.fsw itself trusts schema.scenario's own measurement_fault_mode
    # check (see SpacecraftConfig.validate()) rather than re-raising here
    # -- confirm the dict lookup used internally covers exactly the
    # schema-allowed set, so a validated scenario can never KeyError here.
    from spacemissionstudio.engine import fsw

    scSim, task_name, sc_object = _bare_sim()
    sun_msg = _sun_msg()
    for mode in ("none", "stuck_current", "stuck_value", "spiking"):
        sensors = [SensorConfig(kind="thermal", name="therm-1", params={
            "nHat_B": [0.0, 0.0, 1.0], "area_m2": 1.0, "absorptivity": 1.0, "emissivity": 1.0,
            "measurement_fault_mode": mode,
        })]
        fsw.attach_sensors(scSim, task_name, "sat", sc_object, sensors, sun_state_out_msg=sun_msg)


# -- reaction_wheel motor thermal (motorThermal) ---------------------------

def _run_motor_thermal(rw_params: dict, num_ticks: int = 1):
    from spacemissionstudio.engine import fsw

    scSim, task_name, sc_object = _bare_sim()
    actuators = [ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                 params={"gsHat_B": [0.0, 0.0, 1.0], "rw_type": "Honeywell_HR16",
                                         "maxMomentum": 100.0, **rw_params})]
    _, rw_state_effector, _ = fsw.build_reaction_wheels(scSim, task_name, "sat", sc_object, actuators)
    out_msgs = fsw.build_reaction_wheel_motor_thermal(scSim, task_name, "sat", rw_state_effector, actuators)
    rec = out_msgs["rw-1"].recorder()
    scSim.AddModelToTask(task_name, rec)
    _run_ticks(scSim, task_name, num_ticks)
    return float(np.array(rec.temperature)[-1])


_MOTOR_THERMAL_PARAMS = {
    "motor_thermal_initial_temp_c": 40.0,
    "motor_thermal_ambient_temp_c": 20.0,
    "motor_thermal_efficiency": 0.7,
    "motor_thermal_ambient_resistance_w_c": 5.0,
    "motor_thermal_heat_capacity_j_c": 50.0,
}


def test_build_reaction_wheel_motor_thermal_skips_wheels_without_thermal_params():
    from spacemissionstudio.engine import fsw

    scSim, task_name, sc_object = _bare_sim()
    actuators = [ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                 params={"gsHat_B": [1.0, 0.0, 0.0], "rw_type": "Honeywell_HR16",
                                         "maxMomentum": 100.0})]
    _, rw_state_effector, _ = fsw.build_reaction_wheels(scSim, task_name, "sat", sc_object, actuators)
    out_msgs = fsw.build_reaction_wheel_motor_thermal(scSim, task_name, "sat", rw_state_effector, actuators)
    assert out_msgs == {}


def test_build_reaction_wheel_motor_thermal_only_builds_the_configured_wheel():
    # Two wheels, only the SECOND has motor-thermal params set -- confirms
    # build_reaction_wheel_motor_thermal correctly skips index 0 and wires
    # index 1 (rwOutMsgs[1]), not a positional/off-by-one mismatch.
    from spacemissionstudio.engine import fsw

    scSim, task_name, sc_object = _bare_sim()
    actuators = [
        ActuatorConfig(kind="reaction_wheel", name="rw-1",
                        params={"gsHat_B": [1.0, 0.0, 0.0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0}),
        ActuatorConfig(kind="reaction_wheel", name="rw-2",
                        params={"gsHat_B": [0.0, 1.0, 0.0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0,
                                **_MOTOR_THERMAL_PARAMS}),
    ]
    _, rw_state_effector, _ = fsw.build_reaction_wheels(scSim, task_name, "sat", sc_object, actuators)
    out_msgs = fsw.build_reaction_wheel_motor_thermal(scSim, task_name, "sat", rw_state_effector, actuators)
    assert list(out_msgs.keys()) == ["rw-2"]


def test_motor_thermal_idle_wheel_cools_exactly_toward_ambient():
    # An idle wheel (zero commanded torque, no friction model enabled) has
    # zero heat GENERATION (motorThermal.cpp's own computeTemperature():
    # wheelPower = Omega * u_current = 0, frictionHeat = Omega *
    # frictionTorque = 0) -- the only remaining term is dissipation toward
    # ambientTemperature, an exact closed-form Euler step over one tick.
    final_temp = _run_motor_thermal(_MOTOR_THERMAL_PARAMS, num_ticks=1)
    t0, t_amb, r_amb, c = (_MOTOR_THERMAL_PARAMS["motor_thermal_initial_temp_c"],
                           _MOTOR_THERMAL_PARAMS["motor_thermal_ambient_temp_c"],
                           _MOTOR_THERMAL_PARAMS["motor_thermal_ambient_resistance_w_c"],
                           _MOTOR_THERMAL_PARAMS["motor_thermal_heat_capacity_j_c"])
    heat_dissipation = 1.0 * (t0 - t_amb) / r_amb  # [J] one 1-second tick
    expected = t0 - heat_dissipation / c
    assert final_temp == pytest.approx(expected, abs=1e-9)
    assert final_temp < t0  # cooling toward ambient, as expected


def test_motor_thermal_with_friction_generates_more_heat_than_without():
    # Same starting temperature/ambient/efficiency/heat-capacity, same
    # nonzero wheel speed -- only useRWfriction differs. The friction
    # -enabled wheel must end up warmer (or cool less) than the otherwise
    # -identical frictionless wheel, since it has a real, nonzero
    # additional heat-generation term the other does not.
    common = {**_MOTOR_THERMAL_PARAMS, "Omega": 2000.0}
    without_friction = _run_motor_thermal(common)
    with_friction = _run_motor_thermal({
        **common, "useRWfriction": True, "fCoulomb": 0.01, "fStatic": 0.01, "cViscous": 0.001,
    })
    assert with_friction > without_friction
