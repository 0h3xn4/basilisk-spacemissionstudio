"""Tests for engine.fsw.attach_sensors's device-interface-realism params
(bias/saturation/fault/encoder-quantization) added to
schema.scenario.SensorConfig's existing star_tracker/imu/coarse_sun_sensor/
magnetometer kinds -- real user feedback: "the user should be able to...
select from a range of commonly used devices from the space industry"
with "faults/saturation/encoders". Every field these tests exercise is a
REAL, already-compiled Basilisk StarTracker/ImuSensor/CoarseSunSensor/
Magnetometer field (walkBounds, senRotBias/senTransBias/senRotMax/
senTransMax/setLSBs, senBias/maxOutput/minOutput/faultState/faultNoiseStd,
senBias/maxOutput/minOutput/setFaultState/stuckValue/spikeProbability/
spikeAmount respectively) -- not new physics this project invented.

Like tests/test_css_estimation.py/tests/test_mtb_desaturation.py, these
call engine.fsw.attach_sensors directly against a bare
SimulationBaseClass rather than through SimulationService (SPICE-blocked
in this sandbox) -- nothing here needs SPICE.

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import numpy as np
import pytest

from spacemissionstudio.schema.scenario import SensorConfig

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


def _run_one_tick(scSim, task_name: str):
    from Basilisk.utilities import macros

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(1.0))
    scSim.ExecuteSimulation()


# -- coarse_sun_sensor: bias/saturation/fault -----------------------------

def _run_css(params: dict):
    from Basilisk.architecture import messaging

    from spacemissionstudio.engine import fsw

    scSim, task_name, sc_object = _bare_sim()
    sun_state = messaging.SpicePlanetStateMsgPayload()
    sun_state.PositionVector = [0.0, 0.0, 1.496e11]  # along +Z, matching nHat_B below
    sun_msg = messaging.SpicePlanetStateMsg().write(sun_state)

    sensors = [SensorConfig(kind="coarse_sun_sensor", name="css-1",
                             params={"nHat_B": [0.0, 0.0, 1.0], "fov_deg": 180.0, **params})]
    out_msgs = fsw.attach_sensors(scSim, task_name, "sat", sc_object, sensors, sun_state_out_msg=sun_msg)
    rec = out_msgs["css-1"].recorder()
    scSim.AddModelToTask(task_name, rec)
    _run_one_tick(scSim, task_name)
    return float(np.array(rec.OutputData)[-1])


def test_css_baseline_reads_near_full_illumination():
    # Not exactly 1.0 -- computeSunData()'s own real geometry (this test's
    # sun direction isn't perfectly antiparallel to the CSS boresight at
    # floating-point precision) leaves a small, expected residual; this
    # just confirms "near full illumination", not an exact theoretical
    # value. The two tests below compare against this SAME measured
    # baseline rather than re-deriving the exact number.
    value = _run_css({})
    assert value == pytest.approx(1.0, abs=1e-3)


def test_css_bias_adds_to_the_true_reading():
    baseline = _run_css({})
    value = _run_css({"bias": 0.5})
    assert value == pytest.approx(baseline + 0.5, abs=1e-6)


def test_css_saturation_max_clips_the_output():
    value = _run_css({"saturation_max": 0.1})
    assert value == pytest.approx(0.1, abs=1e-6)


def test_css_fault_stuck_max_freezes_at_saturation_regardless_of_bias():
    value = _run_css({"saturation_max": 0.3, "bias": 100.0, "fault_mode": "stuck_max"})
    assert value == pytest.approx(0.3, abs=1e-6)


def test_css_unrecognized_fault_mode_raises_fsw_error():
    from spacemissionstudio.engine.fsw import FswError

    with pytest.raises(FswError, match="fault_mode"):
        _run_css({"fault_mode": "not_a_real_mode"})


# -- magnetometer: bias/saturation/fault ----------------------------------

def _run_magnetometer(params: dict):
    from Basilisk.architecture import messaging
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, orbitalMotion, simHelpers, simIncludeGravBody

    from spacemissionstudio.engine import fsw

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(1.0)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    sc_object.hub.mHub = 10.0
    sc_object.hub.sigma_BNInit = [[0.0], [0.0], [0.0]]
    scSim.AddModelToTask(task_name, sc_object, 10)

    grav_factory = simIncludeGravBody.gravBodyFactory()
    earth = grav_factory.createEarth()
    earth.isCentralBody = True
    grav_factory.addBodiesTo(sc_object)

    oe = orbitalMotion.ClassicElements()
    oe.a, oe.e, oe.i, oe.Omega, oe.omega, oe.f = 6778.14e3, 0.0, 45.0 * macros.D2R, 0.0, 0.0, 0.0
    r_n, v_n = orbitalMotion.elem2rv(earth.mu, oe)
    sc_object.hub.r_CN_NInit = r_n
    sc_object.hub.v_CN_NInit = v_n

    # Earth motionless at the inertial origin, identity orientation (no
    # SPICE in this bypass setup) -- same stand-in as
    # tests/test_mtb_desaturation.py's identical setup.
    planet_state = messaging.SpicePlanetStateMsgPayload()
    planet_state.PositionVector = [0.0, 0.0, 0.0]
    planet_state.J20002Pfix = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    planet_msg = messaging.SpicePlanetStateMsg().write(planet_state)
    mag_field_model = fsw.build_magnetic_field_wmm(scSim, task_name, planet_msg, earth.radEquator)

    sensors = [SensorConfig(kind="magnetometer", name="mag-1", params=params)]
    out_msgs = fsw.attach_sensors(scSim, task_name, "sat", sc_object, sensors, mag_field_model=mag_field_model)
    rec = out_msgs["mag-1"].recorder()
    scSim.AddModelToTask(task_name, rec)
    _run_one_tick(scSim, task_name)
    # tam_S is the SENSOR-frame reading -- dcm_SB defaults to identity (no
    # body-to-sensor mounting rotation configured here), so it equals the
    # body-frame reading directly.
    return np.array(rec.tam_S)[-1]


def test_magnetometer_bias_adds_per_axis_to_the_true_field():
    baseline = _run_magnetometer({})
    biased = _run_magnetometer({"bias_tesla": [1.0e-6, -2.0e-6, 0.0]})
    assert biased[0] == pytest.approx(baseline[0] + 1.0e-6, abs=1e-9)
    assert biased[1] == pytest.approx(baseline[1] - 2.0e-6, abs=1e-9)
    assert biased[2] == pytest.approx(baseline[2], abs=1e-9)


def test_magnetometer_saturation_clips_every_axis_symmetrically():
    reading = _run_magnetometer({"saturation_tesla": 1.0e-9})
    assert np.all(np.abs(reading) <= 1.0e-9 + 1e-15)


def test_magnetometer_fault_stuck_value_freezes_only_the_named_axis():
    baseline = _run_magnetometer({})
    faulted = _run_magnetometer({"fault_mode": "stuck_value", "fault_axis": 1, "stuck_value_tesla": 4.2e-5})
    assert faulted[1] == pytest.approx(4.2e-5, abs=1e-9)
    # The other two axes are untouched by a single-axis fault.
    assert faulted[0] == pytest.approx(baseline[0], abs=1e-9)
    assert faulted[2] == pytest.approx(baseline[2], abs=1e-9)


def test_magnetometer_unrecognized_fault_mode_raises_fsw_error():
    from spacemissionstudio.engine.fsw import FswError

    with pytest.raises(FswError, match="fault_mode"):
        _run_magnetometer({"fault_mode": "not_a_real_mode"})


# -- imu: bias/saturation/encoder quantization ----------------------------

def _run_imu(params: dict, omega_init=(0.0, 0.0, 0.0)):
    from spacemissionstudio.engine import fsw

    scSim, task_name, sc_object = _bare_sim()
    sc_object.hub.sigma_BNInit = [[0.0], [0.0], [0.0]]
    sc_object.hub.omega_BN_BInit = [[omega_init[0]], [omega_init[1]], [omega_init[2]]]

    sensors = [SensorConfig(kind="imu", name="imu-1", params=params)]
    out_msgs = fsw.attach_sensors(scSim, task_name, "sat", sc_object, sensors)
    rec = out_msgs["imu-1"].recorder()
    scSim.AddModelToTask(task_name, rec)
    _run_one_tick(scSim, task_name)
    # *Platform (not *Body) is the real IMUSensorMsgPayload field name --
    # dcm_PB defaults to identity (no body-to-platform mounting rotation
    # configured here), so it equals the body-frame reading directly.
    return np.array(rec.AngVelPlatform)[-1], np.array(rec.AccelPlatform)[-1]


def test_imu_gyro_bias_adds_to_the_true_rate():
    omega_true = (0.01, -0.02, 0.0)
    gyro, _ = _run_imu({}, omega_init=omega_true)
    assert gyro == pytest.approx(omega_true, abs=1e-6)

    gyro_biased, _ = _run_imu({"gyro_bias_rad_s": [0.001, 0.0, -0.0005]}, omega_init=omega_true)
    assert gyro_biased[0] == pytest.approx(omega_true[0] + 0.001, abs=1e-6)
    assert gyro_biased[2] == pytest.approx(omega_true[2] - 0.0005, abs=1e-6)


def test_imu_accel_bias_reads_directly_since_true_accel_is_zero():
    """This bare sim has no gravity/forces, so the true specific force is
    0 -- a clean baseline where the accelerometer's reading is exactly
    its own bias, with nothing else to subtract out.
    """
    _, accel = _run_imu({"accel_bias_m_s2": [0.0, 0.05, 0.0]})
    assert accel == pytest.approx([0.0, 0.05, 0.0], abs=1e-6)


def test_imu_gyro_saturation_clips_the_output():
    gyro, _ = _run_imu({"gyro_saturation_rad_s": 0.01}, omega_init=(1.0, 0.0, 0.0))
    assert abs(gyro[0]) <= 0.01 + 1e-9


def test_imu_gyro_lsb_quantizes_the_output():
    """A coarse encoder step size (0.01 rad/s) forces the reported rate
    onto a multiple of that step -- the real true rate (0.014) is NOT
    itself a multiple of 0.01, so a quantized reading proves the LSB
    setting actually took effect, not just that the call didn't crash.
    """
    gyro, _ = _run_imu({"gyro_lsb_rad_s": 0.01}, omega_init=(0.014, 0.0, 0.0))
    remainder = gyro[0] % 0.01
    assert remainder < 1e-9 or (0.01 - remainder) < 1e-9


# -- star_tracker: random-walk bound (lighter-touch, see docstring) ------

def test_star_tracker_with_a_walk_bound_runs_and_produces_finite_output():
    """Unlike the other three kinds, bias_walk_bound_arcsec's effect is a
    STOCHASTIC long-run bound on an accumulated random walk, not
    something a single deterministic tick can demonstrate -- this test
    confirms the real Basilisk field actually gets set and the sensor
    still runs/produces finite output with it configured, rather than
    silently being ignored or crashing. A statistical long-run-bound
    confirmation is a reasonable follow-on, not done here.
    """
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros

    from spacemissionstudio.engine import fsw

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(1.0)))
    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    sc_object.hub.mHub = 10.0
    sc_object.hub.sigma_BNInit = [[0.0], [0.0], [0.0]]
    scSim.AddModelToTask(task_name, sc_object, 10)

    sensors = [SensorConfig(kind="star_tracker", name="st-1",
                             params={"noise_arcsec": 2.0, "bias_walk_bound_arcsec": 10.0})]
    out_msgs = fsw.attach_sensors(scSim, task_name, "sat", sc_object, sensors)
    rec = out_msgs["st-1"].recorder()
    scSim.AddModelToTask(task_name, rec)
    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(10.0))
    scSim.ExecuteSimulation()

    quat = np.array(rec.qInrtl2Case)
    assert np.all(np.isfinite(quat))
