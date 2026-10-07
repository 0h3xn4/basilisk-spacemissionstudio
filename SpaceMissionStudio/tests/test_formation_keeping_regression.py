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

"""Regression tests for a real user's failed 90-day run of the formation
template (chief + phasing-keeping follower), reproduced against real
Basilisk dynamics with J2 gravity.

That run's follower had a 2 km station-keeping deadband and a 100 km
target separation, while being placed 50 km ahead. Its OWN station-keeping
reboosted it toward an absolute 550 km target at t = 0.07 d. The chief,
whose natural mean altitude was ~545 km, never reboosted, which left a
~5 km semi-major-axis mismatch, i.e. ~6 deg/day of relative drift. The
phasing controller's open-loop "restore" could never remove a mismatch it
hadn't made itself, and a +/-180 deg error wrap was mistaken for "target
reached". The follower lapped the chief for the whole run, and the
divergence guard suspended corrections at day 46.

Same bare-builder pattern (and reasons) as
``tests/test_orbit_maintenance_j2_regression.py``.
"""

from types import SimpleNamespace

import numpy as np
import pytest

pytestmark = pytest.mark.requires_basilisk

_SMA_M = 6928.0e3
_ECC = 0.001
_INC_DEG = 97.59
_RAAN_DEG = 259.03
_DT_S = 30.0  # [s]


def _run_formation(days, target_km, placed_km, follower_deadband_km, chief_deadband_km, thrust_n=0.05,
                   min_on_time_s=0.0):
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, orbitalMotion, simIncludeGravBody
    from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

    from spacemissionstudio.engine.orbit_maintenance import build_phasing_keeping, build_station_keeping
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
        sc.hub.mHub = 105.0  # [kg]
        sc.hub.r_CN_NInit, sc.hub.v_CN_NInit = r_n, v_n
        grav_factory.addBodiesTo(sc)
        scSim.AddModelToTask(task, sc)
        return sc

    chief = make("chief-1", 0.0)
    follower = make("follower-1", np.degrees(placed_km * 1e3 / _SMA_M))

    def station_keeping(tag, sc, deadband_km):
        config = StationKeepingConfig(target_altitude_km=550.0, deadband_km=deadband_km, thrust_n=thrust_n,
                                      isp_s=1500.0, propellant_kg=5.0, min_on_time_s=min_on_time_s)
        return build_station_keeping(scSim, task, tag, sc, earth.mu, earth.radEquator, 100.0, config,
                                     eclipse_out_msg=None)

    chief_sk = station_keeping("chief1", chief, chief_deadband_km)
    follower_sk = station_keeping("follower1", follower, follower_deadband_km)
    phasing_config = PhasingKeepingConfig(
        chief_spacecraft="chief-1", target_separation_km=[target_km], reconfiguration_interval_days=90.0,
        tolerance_fraction=0.1, restore_tolerance_fraction=0.02, correction_window_days=21.0,
        max_drift_days=90.0, max_delta_semi_major_axis_km=3.0,
    )
    phasing = build_phasing_keeping(scSim, task, "follower1", earth.mu, chief, follower, follower_sk, None,
                                    _SMA_M / 1000.0, phasing_config, chief_station_keeping_controller=chief_sk)
    chief_rec, follower_rec = chief.scStateOutMsg.recorder(), follower.scStateOutMsg.recorder()
    scSim.AddModelToTask(task, chief_rec)
    scSim.AddModelToTask(task, follower_rec)
    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(days * 86400.0))
    scSim.ExecuteSimulation()

    def along_track_km(index):
        rho, _ = orbitalMotion.rv2hill(chief_rec.r_BN_N[index], chief_rec.v_BN_N[index],
                                       follower_rec.r_BN_N[index], follower_rec.v_BN_N[index])
        return rho[1] / 1000.0

    return SimpleNamespace(chief_sk=chief_sk, follower_sk=follower_sk, phasing=phasing,
                           along_track_km=along_track_km, samples=len(chief_rec.times()))


def test_follower_does_not_reboost_alone_and_closes_toward_its_target():
    """The exact failing configuration: before the fix the follower's own
    station-keeping fired at t = 0.07 d and the follower ended day 1 about
    500 km BEHIND the chief. Now it never reboosts on its own, the relative
    semi-major axis stays near zero, and the separation moves from the
    50 km placement toward the 100 km target.
    """
    run = _run_formation(days=1.0, target_km=100.0, placed_km=50.0, follower_deadband_km=2.0,
                         chief_deadband_km=15.0)

    assert sum(run.follower_sk.burnLog) == 0
    assert sum(run.chief_sk.burnLog) == 0
    assert abs(run.phasing.lastRelativeSmaM) < 100.0  # [m] was ~7400 m before the fix
    start_km, end_km = run.along_track_km(0), run.along_track_km(run.samples - 1)
    assert 50.0 < end_km < 100.0  # [km] closing on the target, not drifting away
    assert end_km > start_km + 1.0  # [km]
    assert not run.phasing.suspendedDueToNonConvergence
    # Partial-tick thrust: the correction burn lands on its planned relative
    # semi-major axis (-16.7 m here) instead of overshooting by a whole
    # thruster tick (~26 m), as every correction did before.
    assert abs(run.phasing.lastRelativeSmaM - run.phasing._plannedDeltaA) < 3.0  # [m]
    # The new relative-SMA telemetry lines up with every other per-tick log.
    assert len(run.phasing.relativeSmaLog) == len(run.phasing.tLog)


def test_follower_mirrors_a_chief_reboost_so_the_formation_holds():
    """A narrow deadband on BOTH spacecraft makes the chief reboost at
    t = 0.07 d. The follower must reboost in lockstep, not on its own
    schedule, so the 50 km separation survives.
    """
    run = _run_formation(days=1.0, target_km=50.0, placed_km=50.0, follower_deadband_km=2.0,
                         chief_deadband_km=2.0)

    chief_burns, follower_burns = sum(run.chief_sk.burnLog), sum(run.follower_sk.burnLog)
    assert chief_burns > 100  # the chief really did reboost
    assert abs(follower_burns - chief_burns) <= 2
    assert abs(run.along_track_km(run.samples - 1) - 50.0) < 2.0  # [km]


def test_formation_follower_burn_logic():
    from spacemissionstudio.engine.orbit_maintenance import StationKeepingController

    follower = StationKeepingController("follower", mu=3.986004418e14, nominal_alt_m=550e3, deadband_m=2e3,
                                        r_planet_m=6378137.0, thrust_n=0.05, isp_s=1500.0, dry_mass_kg=100.0,
                                        propellant_kg=5.0)
    chief = SimpleNamespace(burnOn=False, lastSmoothAlt=545e3)  # [m]

    # No chief controller to follow: never reboost on its own.
    assert follower._formation_follower_burn_on(500e3, windowFull=True) is False
    follower.formationReference = chief
    # Level with (or above) the chief: no burn, even though far below its OWN 550 km target.
    assert follower._formation_follower_burn_on(545e3, windowFull=True) is False
    # Chief burning: mirror it.
    chief.burnOn = True
    assert follower._formation_follower_burn_on(545e3, windowFull=True) is True
    # Fallen more than the deadband below the chief: safety-floor burn, until level again.
    chief.burnOn = False
    assert follower._formation_follower_burn_on(542e3, windowFull=True) is True
    follower.burnOn = True
    assert follower._formation_follower_burn_on(544.9e3, windowFull=True) is True
    assert follower._formation_follower_burn_on(545.1e3, windowFull=True) is False


@pytest.mark.parametrize("error_deg, drift_sign, expected", [
    (-0.01, 1.0, True),     # genuinely crossed zero
    (0.01, 1.0, False),     # still on the original side
    (179.99, -1.0, False),  # wrapped from -180 to +180: half an orbit away, NOT "reached"
    (-179.99, 1.0, False),
])
def test_zero_crossing_ignores_the_plus_minus_180_wrap(error_deg, drift_sign, expected):
    from spacemissionstudio.engine.orbit_maintenance import _crossed_zero

    assert _crossed_zero(np.radians(error_deg), drift_sign) is expected


@pytest.mark.parametrize("thrust_n, min_on_time_s", [(0.05, 0.0), (0.5, 0.0), (0.05, 120.0)])  # [N], [s]
def test_a_correction_burn_delivers_exactly_its_planned_delta_v(thrust_n, min_on_time_s):
    """A tenfold stronger thruster must not change how much delta-V a
    correction uses: each burn is capped to the delta-V it still needs
    within a task interval, never a whole tick at full thrust. With a
    120 s minimum on-time the correction is rounded up to one 4-tick
    firing, which must be flown in full by the phasing controller alone:
    the follower's station-keeping (sharing the thruster) must not take
    over part of it.
    """
    run = _run_formation(days=0.2, target_km=100.0, placed_km=50.0, follower_deadband_km=15.0,
                         chief_deadband_km=15.0, thrust_n=thrust_n, min_on_time_s=min_on_time_s)
    used_dv = run.phasing._cumulativeDv  # [m/s]
    planned_dv = abs(run.phasing._plannedDeltaA) / _SMA_M * np.sqrt(3.986004418e14 / _SMA_M) / 2.0  # [m/s]
    assert planned_dv > 0.0
    assert used_dv == pytest.approx(planned_dv, rel=0.05)
    assert planned_dv >= run.phasing.thruster.minimum_impulse_dv(thrust_n, 105.0) * (1.0 - 1e-3)  # [m/s]
    assert sum(run.follower_sk.burnLog) == 0
    assert run.follower_sk._cumulativeDv == 0.0


_OWNER = object()  # stands in for the calling controller
_KW = dict(owner=_OWNER, sign=1.0, thrust_n=0.05, mass_kg=100.0, dt_s=30.0, in_sun=True, u_rad=0.0,
           v_mps=7585.0, mean_motion=1.1e-3)  # [N], [kg], [s], [rad], [m/s], [rad/s]


def test_on_time_model_ideal_thruster_fires_only_the_delta_v_still_needed():
    from spacemissionstudio.engine.orbit_maintenance import ThrusterOnTimeModel

    model = ThrusterOnTimeModel()
    thrust, extra, too_small = model.command(want_firing=True, remaining_dv=0.01, **_KW)  # [m/s]
    assert thrust == pytest.approx(0.01 * 100.0 / 30.0)  # [N] average over the tick
    assert extra == 0.0 and not too_small
    assert model.pulseLeftS == pytest.approx(0.0)


def test_on_time_model_rounds_a_small_burn_up_to_one_minimum_firing():
    from spacemissionstudio.engine.orbit_maintenance import ThrusterOnTimeModel

    model = ThrusterOnTimeModel(min_on_time_s=300.0)  # [s]
    needed_dv = 0.05 * 200.0 / 100.0  # [m/s] 200 s of full thrust: more than half of one 300 s firing
    thrust, extra, too_small = model.command(want_firing=True, remaining_dv=needed_dv, **_KW)
    assert thrust == pytest.approx(0.05)  # [N] full thrust...
    assert extra == pytest.approx(0.05 * 100.0 / 100.0)  # [m/s] ...for the 100 s beyond what was needed
    assert not too_small
    # The firing keeps going across ticks even though nobody asks for more.
    ticks = 1
    while model.pulseLeftS > 0.0:
        thrust, _, _ = model.command(want_firing=False, remaining_dv=0.0, **_KW)
        assert thrust == pytest.approx(0.05)
        ticks += 1
    assert ticks == 10  # 300 s / 30 s


def test_on_time_model_skips_a_burn_below_half_an_impulse_bit():
    from spacemissionstudio.engine.orbit_maintenance import ThrusterOnTimeModel

    model = ThrusterOnTimeModel(min_on_time_s=300.0)  # [s]
    thrust, extra, too_small = model.command(want_firing=True, remaining_dv=0.05 * 100.0 / 100.0, **_KW)
    assert thrust == 0.0 and extra == 0.0 and too_small


def test_on_time_model_eclipse_cuts_a_firing_short():
    from spacemissionstudio.engine.orbit_maintenance import ThrusterOnTimeModel

    model = ThrusterOnTimeModel(min_on_time_s=300.0)  # [s]
    model.command(want_firing=True, remaining_dv=None, **_KW)
    assert model.pulseLeftS > 0.0
    thrust, _, _ = model.command(want_firing=True, remaining_dv=None, **{**_KW, "in_sun": False})
    assert thrust == 0.0 and model.pulseLeftS == 0.0


def test_on_time_model_open_ended_firing_outlasts_its_request_until_the_minimum_on_time():
    from spacemissionstudio.engine.orbit_maintenance import ThrusterOnTimeModel

    model = ThrusterOnTimeModel(min_on_time_s=90.0)  # [s]
    assert model.command(want_firing=True, remaining_dv=None, **_KW)[0] == pytest.approx(0.05)
    assert model.command(want_firing=False, remaining_dv=None, **_KW)[0] == pytest.approx(0.05)
    assert model.command(want_firing=False, remaining_dv=None, **_KW)[0] == pytest.approx(0.05)
    assert model.command(want_firing=False, remaining_dv=None, **_KW)[0] == 0.0


def test_eccentricity_gate_waits_for_the_balancing_side_of_the_orbit():
    from spacemissionstudio.engine.orbit_maintenance import ThrusterOnTimeModel

    model = ThrusterOnTimeModel(eccentricity_neutral=True)
    accel = 0.05 / 100.0  # [m/s^2]
    natural_excursion = 4.0 * accel / (_KW["v_mps"] * _KW["mean_motion"])  # [-]
    # Keep firing at u = 0 until the gate refuses: it must refuse, and only
    # once the accumulated change reaches the allowance.
    for _ in range(1000):
        same_side, _, _ = model.command(want_firing=True, remaining_dv=None, **{**_KW, "u_rad": 0.0})
        if same_side == 0.0:
            break
    assert same_side == 0.0  # would push the eccentricity change further out
    assert np.linalg.norm(model.eccVector) == pytest.approx(natural_excursion, rel=0.05)
    opposite_side, _, _ = model.command(want_firing=True, remaining_dv=None, **{**_KW, "u_rad": np.pi})
    assert opposite_side == pytest.approx(0.05)  # [N] cancels it instead
    assert np.linalg.norm(model.eccVector) < natural_excursion


def test_shared_thruster_firing_belongs_to_the_controller_that_started_it():
    """Station-keeping and phasing share one thruster model. A firing one
    of them started must not be continued (and counted) by the other:
    verification caught station-keeping consuming half of every phasing
    firing's on-time and logging it as its own burn."""
    from spacemissionstudio.engine.orbit_maintenance import ThrusterOnTimeModel

    model = ThrusterOnTimeModel(min_on_time_s=300.0)  # [s]
    phasing, station_keeping = object(), object()
    model.command(want_firing=True, remaining_dv=0.15, **{**_KW, "owner": phasing})  # [m/s] a 300 s firing
    assert model.firing_owned_by(phasing) and not model.firing_owned_by(station_keeping)
    thrust, _, _ = model.command(want_firing=True, remaining_dv=None, **{**_KW, "owner": station_keeping})
    assert thrust == 0.0  # busy: no double firing
    ticks = 1
    while model.firing_owned_by(phasing):
        assert model.command(want_firing=False, remaining_dv=0.0, **{**_KW, "owner": phasing})[0] > 0.0
        ticks += 1
    assert ticks == 10  # the full 300 s, uninterrupted
    assert model.command(want_firing=True, remaining_dv=None, **{**_KW, "owner": station_keeping})[0] > 0.0
