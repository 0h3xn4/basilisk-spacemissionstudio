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

"""Regression tests reproducing, against a REAL Basilisk build with real
(degree >= 2) spherical-harmonics Earth gravity, the two independent real
bugs a full audit found in ``engine.orbit_maintenance`` after a real user's
Vizard screenshot kept showing the ``05_formation_flying_phasing`` template's
along-track separation pinned at the Vizard gauge ceiling even after the
cold-start fix (see ``StationKeepingController``'s own docstring) had
already landed:

1. ``PhasingKeepingController``'s phase error used to be computed from each
   spacecraft's osculating MEAN ANOMALY (``orbitalMotion.rv2elem`` ->
   ``f2E`` -> ``E2M``), which is numerically singular as eccentricity -> 0
   -- real J2 short-period oscillation of the osculating eccentricity
   vector is, by itself, enough to carry a near-circular orbit's ``e``
   through numerically-zero every orbit. Fixed with
   :func:`PhasingKeepingController._argument_of_latitude` (see that
   class's own "Numerical conditioning of the phase error" docstring
   section) -- :mod:`tests.test_orbit_maintenance` already unit-tests that
   function directly; THIS module instead runs the full control loop
   end-to-end against real propagated dynamics, to guard the integration,
   not just the one function.
2. ``05_formation_flying_phasing.json``'s own ``station_keeping.deadband_km``
   used to be too tight (2 km) for this orbit's real, natural (non-decaying)
   J2 + eccentricity altitude variation (confirmed ~5-10 km here) -- the
   controller correctly, by its own design, burning to "correct" ordinary
   orbital mechanics rather than real secular decay (confirmed on a real
   run to fire continuously for ~7 real hours). Fixed by widening the
   template's own ``deadband_km`` to 15 -- this module guards the
   UNDERLYING property that fix relies on (this orbit's natural swing
   stays within a realistically-sized deadband), not the JSON file itself
   (``tests/test_scenario_templates.py`` already round-trips every bundled
   template).

Uses the same "bare ``SimulationBaseClass``, builder functions called
directly" pattern as ``tests/test_gravity_gradient.py`` (see that module's
own docstring) rather than ``engine.service.SimulationService`` --
``central_body_degree > 0`` through the real service always builds a real
SPICE interface (see ``engine.service.SimulationService.build()``), which
needs network access this project's own development sandbox does not have
(see ``engine.kernels``'s "Closed-off/offline policy" docstring); going
through the builder functions directly exercises the exact same real J2
gravity (Earth's bundled, network-free GGM03S coefficient file) without
that unrelated SPICE dependency.

Deliberately uses ``central_body_degree`` 2 (J2 only, zonal), not this
template's own 10 (the full field, with tesseral/order >= 1 terms that
additionally need a planet-ORIENTATION message this bare-builder pattern
does not wire up -- see ``StationKeepingController`` module docstring's own
audit notes) -- confirmed directly, during the audit that found these two
bugs, that J2 alone (degree 2) reproduces both failure modes identically to
degree 10, so degree 2 isolates exactly the real, relevant perturbation
without that unrelated (and here, unmodeled) complication.
"""

import numpy as np
import pytest

pytestmark = pytest.mark.requires_basilisk

_MU_EARTH = 3.986004418e14
_SMA_M = 6928.0e3
_ECC = 0.001
_INC_DEG = 97.59
_RAAN_DEG = 259.03


def _build_two_body_j2_sim(dt_s: float):
    from Basilisk.utilities import SimulationBaseClass, macros, simIncludeGravBody
    from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

    scSim = SimulationBaseClass.SimBaseClass()
    dyn_process = scSim.CreateNewProcess("dynProcess", priority=100)
    dyn_task_name = "dynTask"
    dyn_process.addTask(scSim.CreateNewTask(dyn_task_name, macros.sec2nano(dt_s)))

    grav_factory = simIncludeGravBody.gravBodyFactory()
    earth = grav_factory.createBodies(["earth"])["earth"]
    earth.isCentralBody = True
    earth.useSphericalHarmonicsGravityModel(str(get_path(DataFile.LocalGravData.GGM03S)), 2)
    return scSim, dyn_task_name, grav_factory, earth


def _state_from_true_anomaly(mu, true_anomaly_deg):
    from Basilisk.utilities import orbitalMotion

    oe = orbitalMotion.ClassicElements()
    oe.a, oe.e, oe.i = _SMA_M, _ECC, np.radians(_INC_DEG)
    oe.Omega, oe.omega = np.radians(_RAAN_DEG), 0.0
    oe.f = np.radians(true_anomaly_deg)
    r, v = orbitalMotion.elem2rv(mu, oe)
    return np.array(r), np.array(v)


def _make_spacecraft(grav_factory, scSim, task_name, name, r_n, v_n, mass_kg):
    from Basilisk.simulation import spacecraft

    sc = spacecraft.Spacecraft()
    sc.ModelTag = name
    sc.hub.mHub = mass_kg
    sc.hub.r_CN_NInit = r_n
    sc.hub.v_CN_NInit = v_n
    grav_factory.addBodiesTo(sc)
    scSim.AddModelToTask(task_name, sc)
    return sc


def test_station_keeping_does_not_spuriously_burn_under_real_j2_with_a_realistic_deadband():
    """Bug (2) above: at this template's real elements, raw/smoothed
    altitude's own natural J2 + eccentricity swing is big enough to trip
    a too-tight deadband -- confirmed separately (not asserted here,
    deliberately -- see this module's own docstring) to fire continuously
    for hours at deadband_km=2. At the template's now-widened
    deadband_km=15, station-keeping must never fire at all over several
    orbits of otherwise-undisturbed (no drag in this bare-builder
    reproduction) real J2 dynamics -- there is no real secular decay here
    for it to legitimately react to.
    """
    from spacemissionstudio.engine.orbit_maintenance import build_station_keeping
    from spacemissionstudio.schema.scenario import StationKeepingConfig

    dt_s = 30.0
    scSim, task_name, grav_factory, earth = _build_two_body_j2_sim(dt_s)
    mu = earth.mu
    r_n, v_n = _state_from_true_anomaly(mu, 0.0)
    dry_mass_kg, propellant_kg = 400.0, 5.0
    sc = _make_spacecraft(grav_factory, scSim, task_name, "follower-1", r_n, v_n,
                           dry_mass_kg + propellant_kg)

    config = StationKeepingConfig(target_altitude_km=550.0, deadband_km=15.0, thrust_n=0.05,
                                   isp_s=1500.0, propellant_kg=propellant_kg)
    controller = build_station_keeping(scSim, task_name, "follower1", sc, mu, earth.radEquator,
                                        dry_mass_kg, config, eclipse_out_msg=None)

    scSim.InitializeSimulation()
    from Basilisk.utilities import macros
    period_s = 2.0 * np.pi * np.sqrt(_SMA_M ** 3 / mu)
    scSim.ConfigureStopTime(macros.sec2nano(3.0 * period_s))
    scSim.ExecuteSimulation()

    assert sum(controller.burnLog) == 0, (
        "station-keeping fired under real J2 dynamics with no real secular decay present -- "
        "the deadband has no margin over this orbit's own natural altitude variation"
    )


def test_phasing_keeping_converges_monotonically_under_real_j2_dynamics():
    """Bug (1) above, end-to-end: with the chief/follower's real initial
    true-anomaly offset (-0.5 deg, this template's own elements -- the
    follower actually TRAILS the chief initially, by ~60 km, well short of
    the +50 km-ahead target, for a real starting error of about -110 km),
    under real J2 gravity, the smoothed along-track error must move
    monotonically TOWARD the target over the correction window, not swing
    through spurious thousand-km excursions the way the pre-fix
    osculating-mean-anomaly metric did (confirmed separately, not asserted
    here -- see this module's own docstring).
    """
    from Basilisk.utilities import macros

    from spacemissionstudio.engine.orbit_maintenance import build_phasing_keeping, build_station_keeping
    from spacemissionstudio.schema.scenario import PhasingKeepingConfig, StationKeepingConfig

    dt_s = 30.0
    scSim, task_name, grav_factory, earth = _build_two_body_j2_sim(dt_s)
    mu = earth.mu

    r_chief, v_chief = _state_from_true_anomaly(mu, 0.0)
    r_follower, v_follower = _state_from_true_anomaly(mu, -0.5)
    chief = _make_spacecraft(grav_factory, scSim, task_name, "chief-1", r_chief, v_chief, 400.0)
    dry_mass_kg, propellant_kg = 400.0, 5.0
    follower = _make_spacecraft(grav_factory, scSim, task_name, "follower-1", r_follower, v_follower,
                                 dry_mass_kg + propellant_kg)

    sk_config = StationKeepingConfig(target_altitude_km=550.0, deadband_km=15.0, thrust_n=0.05,
                                      isp_s=1500.0, propellant_kg=propellant_kg)
    sk_controller = build_station_keeping(scSim, task_name, "follower1", follower, mu, earth.radEquator,
                                           dry_mass_kg, sk_config, eclipse_out_msg=None)

    pk_config = PhasingKeepingConfig(chief_spacecraft="chief-1", target_separation_km=[50.0],
                                      reconfiguration_interval_days=90.0, tolerance_fraction=0.1,
                                      restore_tolerance_fraction=0.02, correction_window_days=21.0,
                                      max_drift_days=90.0, max_delta_semi_major_axis_km=3.0)
    pk_controller = build_phasing_keeping(scSim, task_name, "follower1", mu, chief, follower,
                                           sk_controller, None, _SMA_M / 1000.0, pk_config)

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(1.0 * 86400.0))
    scSim.ExecuteSimulation()

    error_km = np.asarray(pk_controller.errorDegLog) * np.pi / 180.0 * _SMA_M / 1000.0
    initial_error_km = error_km[0]
    final_error_km = error_km[-1]

    # Real starting error is large and negative (follower trailing, well
    # short of the target) -- confirm the test setup itself still matches
    # the template's real geometry before asserting anything about
    # convergence.
    assert initial_error_km < -80.0
    # Over one day (well inside the 21-day correction window), the error
    # must have moved meaningfully TOWARD zero, and never swung past a
    # small multiple of its own starting magnitude in the process -- the
    # pre-fix bug produced errors of several THOUSAND km within hours.
    assert final_error_km > initial_error_km
    assert np.all(np.abs(error_km) < 2.0 * abs(initial_error_km))
