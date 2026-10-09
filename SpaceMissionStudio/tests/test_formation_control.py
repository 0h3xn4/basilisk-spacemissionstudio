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
"""Basilisk's formation-flying flight software as a phasing-keeping
control law (``PhasingKeepingConfig.control_law``,
``engine.formation_control``): the schema, the plausibility warning, the
events and series it adds, and real Basilisk runs of both laws behind the
follower's thrust-limited thruster.

The runs use the bare-builder pattern of
``tests/test_formation_keeping_regression.py`` (J2 gravity, the template-05
orbit, no drag), so each takes seconds rather than a full service run.
"""

import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from spacemissionstudio.engine import events, scenario_checks, series_names
from spacemissionstudio.engine.results import ResultSet, TimeSeries
from spacemissionstudio.schema.scenario import Scenario, ScenarioValidationError

_TEMPLATE_05 = (Path(__file__).resolve().parents[1] / "spacemissionstudio" / "scenarios" / "templates"
                / "05_formation_flying_phasing.json")
_SMA_M = 6928.0e3  # [m] template 05
_ECC = 0.001  # [-]
_INC_DEG = 97.59  # [deg]
_RAAN_DEG = 259.03  # [deg]
_DT_S = 30.0  # [s]
_MASS_KG = 405.0  # [kg] 400 kg dry + 5 kg propellant, as template 05


def _template_05(control_law: str, **phasing) -> dict:
    data = json.loads(_TEMPLATE_05.read_text(encoding="utf-8"))
    data["spacecraft"][1]["phasing_keeping"].update(control_law=control_law, **phasing)
    return data


# -- Schema, checks, events, series (no Basilisk needed) ---------------------


def test_drift_orbit_stays_the_default_and_older_files_still_load():
    """A scenario saved before the control_law field existed runs the
    drift-orbit controller, as before."""
    data = _template_05("drift_orbit")
    for key in ("control_law", "mean_oe_gain", "hill_position_gain", "hill_velocity_gain"):
        data["spacecraft"][1]["phasing_keeping"].pop(key, None)
    scenario = Scenario.from_dict(data)
    scenario.validate()
    assert scenario.spacecraft[1].phasing_keeping.control_law == "drift_orbit"


@pytest.mark.parametrize("control_law", ["mean_oe", "hill_pd"])
def test_the_basilisk_laws_validate_and_round_trip(control_law):
    """Both Basilisk laws are valid on template 05 and survive a save and load."""
    scenario = Scenario.from_dict(_template_05(control_law, mean_oe_gain=1234.0, hill_position_gain=3e-6))
    scenario.validate()
    again = Scenario.from_dict(json.loads(json.dumps(scenario.to_dict())))
    pk = again.spacecraft[1].phasing_keeping
    assert (pk.control_law, pk.mean_oe_gain, pk.hill_position_gain) == (control_law, 1234.0, 3e-6)


@pytest.mark.parametrize("change, message", [
    ({"control_law": "pid"}, "control_law"),
    ({"mean_oe_gain": 0.0}, "mean_oe_gain"),
    ({"hill_position_gain": -1.0}, "hill_position_gain"),
    ({"hill_velocity_gain": float("nan")}, "hill_velocity_gain"),
])
def test_an_unknown_law_or_a_non_positive_gain_is_rejected(change, message):
    """Each new field is checked, and the error names it."""
    data = _template_05("drift_orbit")
    data["spacecraft"][1]["phasing_keeping"].update(change)
    with pytest.raises(ScenarioValidationError, match=message):
        Scenario.from_dict(data).validate()


def test_mean_oe_needs_earth_j2_in_the_dynamics():
    """meanOEFeedback maps to mean elements with Earth's J2; with point-mass
    gravity that mapping would add a J2 motion the run does not have."""
    data = _template_05("mean_oe")
    data["gravity"]["central_body_degree"] = 0
    with pytest.raises(ScenarioValidationError, match="J2"):
        Scenario.from_dict(data).validate()
    data["spacecraft"][1]["phasing_keeping"]["control_law"] = "hill_pd"
    Scenario.from_dict(data).validate()  # the Hill-frame law needs only mu


def test_hill_pd_is_flagged_where_its_thruster_cannot_hold_the_separation():
    """Template 05's 0.05 N thruster on 405 kg gives 1.2e-4 m/s^2; holding
    50 km with the Hill-frame law takes 6.5e-4 m/s^2 (3 n^2 a (1 - cos theta))."""
    warnings = scenario_checks.scenario_warnings(Scenario.from_dict(_template_05("hill_pd")))
    assert any("hill_pd needs 6.5e-04 m/s^2 to hold 50 km" in w for w in warnings)
    assert not [w for w in scenario_checks.scenario_warnings(Scenario.from_dict(_template_05("mean_oe")))
                if "hill_pd" in w]


def test_hill_pd_is_flagged_when_it_starts_too_far_off_for_its_thruster():
    """A 1 km formation placed 50 m off: K * error = 2e-6 * 50 = 1e-4 m/s^2,
    under the thruster's 1.2e-4, so no warning; 5 km off (1e-2) is flagged."""
    data = _template_05("hill_pd", target_separation_km=[1.0])
    follower_orbit = data["spacecraft"][1]["orbit"]
    for placed_km, flagged in ((1.05, False), (6.0, True)):
        follower_orbit["mean_anomaly_deg"] = math.degrees(placed_km * 1e3 / _SMA_M)
        warnings = [w for w in scenario_checks.scenario_warnings(Scenario.from_dict(data)) if "hill_pd" in w]
        assert bool(warnings) is flagged, warnings
        if flagged:
            assert "saturated PD law can diverge" in warnings[0]


def test_firings_of_a_basilisk_law_become_burn_events():
    """State 4 (engine.formation_control.FIRING) is a "formation control firing"."""
    t = np.arange(6, dtype=float) * 60.0  # [s]
    result = ResultSet("test")
    result.add(TimeSeries("f.phasing_keeping.state", t, ("state",), np.array([0, 4, 4, 0, 4, 0], dtype=float)))
    result.add(TimeSeries("f.phasing_keeping.delta_v", t, ("cumulative_delta_v",),
                          np.array([0, 0.1, 0.2, 0.2, 0.3, 0.3])))
    burns = [e for e in events.extract_events(result) if e.kind == events.BURN]
    assert [(e.label, e.start_s, e.end_s) for e in burns] == [
        ("formation control firing", 60.0, 120.0), ("formation control firing", 240.0, 240.0)]
    assert burns[0].detail == "delta-V 0.200 m/s"


def test_only_the_basilisk_laws_add_the_force_series():
    """The commanded/applied force series exists only for the Basilisk laws."""
    for control_law, expected in (("drift_orbit", False), ("mean_oe", True), ("hill_pd", True)):
        names = series_names.expected_series_names(Scenario.from_dict(_template_05(control_law)))
        assert ("follower-1.phasing_keeping.force" in names) is expected


# -- Real Basilisk runs ------------------------------------------------------


def _run(control_law, days, target_km, placed_km, thrust_n=0.05, min_on_time_s=0.0, **gains):
    """Chief and follower on template 05's orbit with J2; the follower's
    separation held by ``control_law`` through its station-keeping thruster."""
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, orbitalMotion, simIncludeGravBody
    from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

    from spacemissionstudio.engine.formation_control import build_formation_control
    from spacemissionstudio.engine.orbit_maintenance import build_station_keeping
    from spacemissionstudio.schema.scenario import PhasingKeepingConfig, StationKeepingConfig

    scSim = SimulationBaseClass.SimBaseClass()
    process = scSim.CreateNewProcess("dynProcess", priority=100)
    task = "dynTask"
    process.addTask(scSim.CreateNewTask(task, macros.sec2nano(_DT_S)))
    grav_factory = simIncludeGravBody.gravBodyFactory()
    earth = grav_factory.createBodies(["earth"])["earth"]
    earth.isCentralBody = True
    earth.useSphericalHarmonicsGravityModel(str(get_path(DataFile.LocalGravData.GGM03S)), 2)

    def make(name, mean_anomaly_deg):
        oe = orbitalMotion.ClassicElements()
        oe.a, oe.e, oe.i = _SMA_M, _ECC, np.radians(_INC_DEG)
        oe.Omega, oe.omega = np.radians(_RAAN_DEG), 0.0
        oe.f = orbitalMotion.E2f(orbitalMotion.M2E(np.radians(mean_anomaly_deg), _ECC), _ECC)
        r_n, v_n = orbitalMotion.elem2rv(earth.mu, oe)
        sc = spacecraft.Spacecraft()
        sc.ModelTag = name
        sc.hub.mHub = _MASS_KG
        sc.hub.r_CN_NInit, sc.hub.v_CN_NInit = r_n, v_n
        grav_factory.addBodiesTo(sc)
        scSim.AddModelToTask(task, sc)
        return sc

    chief = make("chief-1", 0.0)
    follower = make("follower-1", np.degrees(placed_km * 1e3 / _SMA_M))
    sk_config = StationKeepingConfig(target_altitude_km=550.0, deadband_km=2.0, thrust_n=thrust_n, isp_s=1500.0,
                                     propellant_kg=5.0, min_on_time_s=min_on_time_s)
    follower_sk = build_station_keeping(scSim, task, "follower1", follower, earth.mu, earth.radEquator,
                                        _MASS_KG - 5.0, sk_config, eclipse_out_msg=None)
    config = PhasingKeepingConfig(chief_spacecraft="chief-1", target_separation_km=[target_km],
                                  control_law=control_law, **gains)
    bridge = build_formation_control(scSim, task, "follower1", earth.mu, chief, follower, follower_sk, None,
                                     _SMA_M / 1000.0, config, central_radius_m=earth.radEquator,
                                     j2=orbitalMotion.J2_EARTH)
    chief_rec, follower_rec = chief.scStateOutMsg.recorder(), follower.scStateOutMsg.recorder()
    scSim.AddModelToTask(task, chief_rec)
    scSim.AddModelToTask(task, follower_rec)
    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(days * 86400.0))
    scSim.ExecuteSimulation()

    def hill_km(index):
        rho, _ = orbitalMotion.rv2hill(chief_rec.r_BN_N[index], chief_rec.v_BN_N[index],
                                       follower_rec.r_BN_N[index], follower_rec.v_BN_N[index])
        return np.asarray(rho) / 1000.0

    return SimpleNamespace(bridge=bridge, follower_sk=follower_sk, hill_km=hill_km,
                           samples=len(chief_rec.times()))


@pytest.mark.requires_basilisk
def test_mean_oe_pulls_a_5_km_error_in_and_holds_50_km():
    """meanOEFeedback, gain 2500 m^2/s^3 per kg: the follower placed at
    55 km reaches 50 km within a day (2.6 m/s measured in the 5-day study
    in HISTORY.md) and then holds it to tens of metres."""
    run = _run("mean_oe", days=1.5, target_km=50.0, placed_km=55.0)
    along_track_km = run.hill_km(run.samples - 1)[1]
    assert abs(along_track_km - 50.0) < 0.5  # [km]
    assert abs(run.bridge.errorDegLog[-1]) < 0.002  # [deg] one-orbit mean, ~0.25 km
    assert 1.5 < run.bridge.deltaVLog[-1] < 4.0  # [m/s]
    assert sum(run.follower_sk.burnLog) == 0  # the law, not station keeping, moved the follower
    assert max(run.bridge.appliedForceLog) <= 0.05 + 1e-12  # [N] never above the thruster
    # Propellant follows the rocket equation for the delta-V flown.
    used_kg = 5.0 - run.follower_sk.propellant
    expected_kg = _MASS_KG * (1.0 - math.exp(-run.bridge.deltaVLog[-1] / (1500.0 * 9.80665)))
    assert used_kg == pytest.approx(expected_kg, rel=0.01)


@pytest.mark.requires_basilisk
def test_hill_pd_holds_a_close_formation_within_its_thrust_limit():
    """hillFrameRelativeControl with Basilisk's documented gains holds a
    1 km formation placed 50 m off to metres, without saturating the
    0.05 N thruster. It fights every natural relative motion, so it keeps
    firing (about 0.9 m/s per day measured at 1 km)."""
    run = _run("hill_pd", days=0.5, target_km=1.0, placed_km=1.05)
    rho = run.hill_km(run.samples - 1)
    assert abs(rho[1] - 1.0) < 0.01 and abs(rho[0]) < 0.01  # [km] along-track and radial
    assert max(run.bridge.commandedForceLog) < 0.05  # [N] unsaturated
    assert 0.1 < run.bridge.deltaVLog[-1] < 1.0  # [m/s]
    assert 4 in run.bridge.stateLog  # FIRING


@pytest.mark.requires_basilisk
def test_a_request_above_the_thrust_is_cut_to_the_thrust():
    """A 5 km error makes the Hill-frame law ask for ~40 N; the bridge
    applies 0.05 N in the requested direction."""
    run = _run("hill_pd", days=0.02, target_km=1.0, placed_km=6.0)
    assert max(run.bridge.commandedForceLog) > 1.0  # [N]
    assert max(run.bridge.appliedForceLog) == pytest.approx(0.05)  # [N]


@pytest.mark.requires_basilisk
def test_requests_under_half_a_minimum_impulse_bit_are_not_fired():
    """Holding on target, meanOEFeedback asks for ~1e-4 N: 0.06 s of a
    0.05 N thruster per 30 s tick, under half of a 300 s minimum on-time,
    so the thruster stays off (ThrusterOnTimeModel)."""
    run = _run("mean_oe", days=0.1, target_km=50.0, placed_km=50.0, min_on_time_s=300.0)
    assert max(run.bridge.commandedForceLog) > 0.0
    assert max(run.bridge.appliedForceLog) == 0.0
    assert run.bridge.deltaVLog[-1] == 0.0


@pytest.mark.requires_basilisk
def test_no_thrust_in_eclipse_and_none_without_propellant():
    """The bridge's own gates, driven message by message: a 1 N request is
    cut to the thruster's 0.05 N in sunlight, and dropped in eclipse or
    with an empty tank."""
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque

    from spacemissionstudio.engine.constellation import SeparationSchedule
    from spacemissionstudio.engine.formation_control import FormationControlBridge
    from spacemissionstudio.engine.orbit_maintenance import StationKeepingController

    sk = StationKeepingController(name="sk", mu=3.986004418e14, nominal_alt_m=550e3, deadband_m=2e3,
                                  r_planet_m=6378e3, thrust_n=0.05, isp_s=1500.0, dry_mass_kg=400.0,
                                  propellant_kg=5.0)
    bridge = FormationControlBridge(
        name="fc", control_law="mean_oe", mu=3.986004418e14, nominal_a_m=_SMA_M,
        separation_schedule=SeparationSchedule([50.0], 0.0, _SMA_M), thrust_n=0.05, isp_s=1500.0,
        dry_mass_kg=400.0, dv_budget_mps=10.0, eclipse_sunlit_threshold=0.99)
    bridge.extForceEffectorB = extForceTorque.ExtForceTorque()
    bridge.altitudeControllerB = sk
    bridge.thruster = sk.thruster
    messages = []

    def publish(msg_type, payload_type, reader, **fields):
        payload = payload_type()
        for key, value in fields.items():
            setattr(payload, key, value)
        msg = msg_type().write(payload)
        reader.subscribeTo(msg)
        messages.append(msg)  # keep alive

    v = math.sqrt(3.986004418e14 / _SMA_M)  # [m/s]
    publish(messaging.SCStatesMsg, messaging.SCStatesMsgPayload, bridge.scStateInMsgA,
            r_BN_N=[_SMA_M, 0.0, 0.0], v_BN_N=[0.0, v, 0.0])
    publish(messaging.SCStatesMsg, messaging.SCStatesMsgPayload, bridge.scStateInMsgB,
            r_BN_N=[_SMA_M * math.cos(0.01), _SMA_M * math.sin(0.01), 0.0],
            v_BN_N=[-v * math.sin(0.01), v * math.cos(0.01), 0.0])
    publish(messaging.CmdForceInertialMsg, messaging.CmdForceInertialMsgPayload, bridge.forceInMsg,
            forceRequestInertial=[0.0, 1.0, 0.0])
    eclipse = messaging.EclipseMsg()
    bridge.eclipseInMsgB.subscribeTo(eclipse)

    def tick(seconds, illumination):
        payload = messaging.EclipseMsgPayload()
        setattr(payload, "illuminationFactor" if hasattr(payload, "illuminationFactor") else "shadowFactor",
                illumination)
        eclipse.write(payload)
        bridge.UpdateState(int(seconds * 1e9))
        return np.asarray(bridge.extForceEffectorB.extForce_N).flatten()

    bridge.Reset(0)
    assert np.allclose(tick(30.0, 1.0), [0.0, 0.05, 0.0])  # [N] cut to the thruster, direction kept
    assert np.allclose(tick(60.0, 0.0), 0.0)  # eclipse
    sk.propellant = 0.0
    assert np.allclose(tick(90.0, 1.0), 0.0)  # empty tank
    assert bridge.stateLog == [] or set(bridge.stateLog) <= {0, 4}


@pytest.mark.requires_basilisk
def test_the_hill_reference_lies_on_the_chiefs_circular_orbit():
    """The reference point is ``s`` of arc ahead on the chief's circle, not
    ``y = s`` on the straight along-track axis."""
    from spacemissionstudio.engine.formation_control import hill_reference_position_m

    x, y, z = hill_reference_position_m(_SMA_M, 50e3 / _SMA_M)
    assert (x + _SMA_M) ** 2 + y ** 2 == pytest.approx(_SMA_M ** 2, rel=1e-12)
    assert x == pytest.approx(-180.4, abs=0.1) and z == 0.0  # [m] 50 km of arc drops 180 m


@pytest.mark.requires_basilisk
def test_a_scenario_with_a_basilisk_law_builds_and_runs_through_the_service():
    """The service wires the chosen law for a real scenario (template 05 for
    ten minutes) and records its series."""
    from spacemissionstudio.engine.service import SimulationService

    data = copy.deepcopy(_template_05("mean_oe"))
    data["sim_settings"]["duration_days"] = 600.0 / 86400.0
    scenario = Scenario.from_dict(data)
    scenario.validate()
    result = SimulationService(scenario).run()
    force = result.series["follower-1.phasing_keeping.force"]
    assert force.columns == ("commanded", "applied")
    assert np.all(force.data[:, 1] <= 0.05 + 1e-12)  # [N]
