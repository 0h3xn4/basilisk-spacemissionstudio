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

"""One-off generator for spacemissionstudio/scenarios/templates/*.json -- run
directly (``python3 scripts/_generate_templates.py``) whenever a template
needs regenerating after a schema change. Not part of the installed
package and not imported by anything else; building the templates through
``schema.scenario`` dataclasses + ``Scenario.validate()`` (rather than
hand-writing JSON) is what guarantees they're actually schema-valid --
this script is the source of truth for that construction logic, kept
around instead of thrown away so future schema/field changes have a clear
place to regenerate from.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from spacemissionstudio.engine.constellation import WalkerConstellationRequest, generate_walker_constellation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _template_descriptions import DESCRIPTIONS  # noqa: E402 -- short, user-facing; see that module
from spacemissionstudio.engine.facets import box_facets
from spacemissionstudio.engine.propellant_budget import OPERATIONS_DRAG_COEFF  # 3.0: ESA AD10 Sec. 5.2
from spacemissionstudio.engine.orbit_design import (
    geostationary_elements_deg,
    raan_for_ltan_deg,
    sun_synchronous_inclination_deg,
)
from spacemissionstudio.schema.scenario import (
    CommsPointingConfig,
    DispersionConfig,
    FuelTankConfig,
    GeoStationKeepingConfig,
    GravityConfig,
    GroundStationConfig,
    MagneticMomentumManagementConfig,
    MomentumDumpingConfig,
    MonteCarloConfig,
    OrbitIC,
    PhasingKeepingConfig,
    PowerConfig,
    RFLinkConfig,
    Scenario,
    SensorConfig,
    ActuatorConfig,
    SimSettings,
    SpacecraftConfig,
    SpaceWeatherConfig,
    StationKeepingConfig,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"

_RPM_TO_RAD_S = math.pi / 30.0


def _box_inertia(mass_kg: float, size_m: tuple) -> list:
    """Row-major principal inertia [kg*m^2] of a uniform box of ``size_m``
    (x, y, z) [m]: I_xx = m (y^2 + z^2) / 12, and so on."""
    x, y, z = size_m
    return [round(mass_kg * (y * y + z * z) / 12.0, 1), 0.0, 0.0,
            0.0, round(mass_kg * (x * x + z * z) / 12.0, 1), 0.0,
            0.0, 0.0, round(mass_kg * (x * x + y * y) / 12.0, 1)]


# Every template flies a 100-500 kg spacecraft, the class this app is for.
# Three buses, each with an inertia derived from its own mass and size:
_MICROSAT_MASS_KG = 150.0  # [kg]
_MICROSAT_SIZE_M = (0.8, 0.8, 1.0)  # [m] -> I = 20.5, 20.5, 16.0 kg*m^2
_SMALLSAT_MASS_KG = 300.0  # [kg]
_SMALLSAT_SIZE_M = (1.2, 1.2, 1.5)  # [m] -> I = 92.3, 92.3, 72.0 kg*m^2
_LARGE_SMALLSAT_MASS_KG = 500.0  # [kg]
_LARGE_SMALLSAT_SIZE_M = (1.2, 1.2, 1.6)  # [m] -> I = 166.7, 166.7, 120.0 kg*m^2

# A 6 N*m*s, 50 mN*m wheel at up to 6000 RPM: the size of the VECTRONIC
# VRW-D-6 in engine/device_catalog.py, which suits the 150 kg bus. "custom"
# derives the rotor inertia from maxMomentum/Omega_max, so any maxMomentum
# a wizard sets stays valid (a named Honeywell type accepts only three).
_MICROSAT_WHEEL = {"rw_type": "custom", "maxMomentum": 6.0, "Omega_max": 6000.0, "u_max": 0.05}


def _corner_thrusters(half_size_m: tuple, max_thrust_n: float, **extra) -> list:
    """Eight thrusters on the bus corners, two per couple axis (the layout
    of Basilisk's examples/BskSim, scaled to this bus). Returns one
    thruster ``params`` dict each."""
    hx, hy, hz = half_size_m
    positions = [[-hx, -hy, hz], [hx, -hy, -hz], [hx, -hy, hz], [hx, hy, -hz],
                 [hx, hy, hz], [-hx, hy, -hz], [-hx, hy, hz], [-hx, -hy, -hz]]
    directions = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                  [-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0]]
    return [{"r_B": pos, "tHat_B": direction, "MaxThrust": max_thrust_n, **extra}
            for pos, direction in zip(positions, directions)]

# Skewed-pyramid 4-wheel layout, beta=52deg -- the exact spin axes
# examples/scenarioMtbMomentumManagement.py uses, computed here (not
# copied as decimals) so the values stay traceably derived from that
# same beta angle.
_MTB_DEMO_BETA_RAD = 52.0 * math.pi / 180.0
_MTB_DEMO_RW_AXES = [
    [0.0, math.cos(_MTB_DEMO_BETA_RAD), math.sin(_MTB_DEMO_BETA_RAD)],
    [0.0, math.sin(_MTB_DEMO_BETA_RAD), -math.cos(_MTB_DEMO_BETA_RAD)],
    [math.cos(_MTB_DEMO_BETA_RAD), -math.sin(_MTB_DEMO_BETA_RAD), 0.0],
    [-math.cos(_MTB_DEMO_BETA_RAD), -math.sin(_MTB_DEMO_BETA_RAD), 0.0],
]

# -- Sun-synchronous (10:30 AM LTAN) orbit + Berlin ground station ---------
# Real user request: templates should default to a realistic Sun
# -synchronous orbit (10:30 AM local time of ascending node -- the most
# common real operational choice for Earth-observation/commercial
# smallsats) and a Berlin, Germany ground station, wherever a template's
# own lesson doesn't specifically need something else (GEO/Walker
# -coverage/transfer-trajectory geometry, or a sun-angle/geomagnetic-field
# -sensitive demo whose numeric claims were confirmed against its CURRENT
# orbit -- see each affected build_*() function's own comment for which
# templates keep their existing orbit and why).
#
# sun_synchronous_inclination_deg()/raan_for_ltan_deg() used to be defined
# HERE, as this dev-only generator script's own private helpers -- moved
# to engine.orbit_design (Phase 6 audit fix) so the running app can import
# the exact same, already-verified implementation these 12 templates rely
# on, instead of a user having no way to reproduce a Sun-synchronous orbit
# by hand when building a bespoke scenario from scratch. See that
# module's own docstring for the full verification details (J2 secular
# RAAN-rate derivation, the three real Sun-right-ascension reference
# points). This is a pure import -- zero behavior change here.


def _berlin_ground_station(**overrides) -> GroundStationConfig:
    """Berlin, Germany (city-center reference: Alexanderplatz, ~34 m
    above the WGS84 ellipsoid) -- the real user-requested baseline ground
    station for every template that has one.
    """
    params = dict(name="berlin-gs", latitude_deg=52.5200, longitude_deg=13.4050, altitude_m=34.0,
                  min_elevation_deg=10.0)
    params.update(overrides)
    return GroundStationConfig(**params)


def _real_space_weather() -> SpaceWeatherConfig:
    """Drag from NRLMSISE-00 driven by real data shipped with the app
    (``source="bundled"``: CelesTrak's observed record, then NASA MSFC's
    50th-percentile prediction, the nominal case) -- a fresh instance per
    call, since ``SpaceWeatherConfig`` is mutable. Solar activity
    "Conservative" in Propagation setup is MSFC's 95th percentile (ESA
    AD10 Sec. 5.9, operations).
    """
    return SpaceWeatherConfig(source="bundled", atmosphere_model="nrlmsise00", forecast_percentile=50.0)


def _save(scenario: Scenario, filename: str) -> None:
    scenario.validate()  # fail loudly here, not for whoever opens the file later
    path = OUT_DIR / filename
    scenario.save(path)
    print(f"wrote {path}")


def build_01_two_body_circular_orbit() -> Scenario:
    return Scenario(
        name="01 - Two-body circular orbit",
        description=(
            DESCRIPTIONS["01"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=1.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6778.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_LARGE_SMALLSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_LARGE_SMALLSAT_MASS_KG, _LARGE_SMALLSAT_SIZE_M),
            ),
        ],
    )


def build_02_elliptical_orbit_with_perturbations() -> Scenario:
    return Scenario(
        name="02 - Elliptical orbit with perturbations",
        description=(
            DESCRIPTIONS["02"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=3.0, dynamics_task_rate_s=1.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=24396.0, eccentricity=0.7,
                               inclination_deg=28.5, raan_deg=0.0, arg_periapsis_deg=180.0, true_anomaly_deg=0.0),
                dry_mass_kg=_LARGE_SMALLSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_LARGE_SMALLSAT_MASS_KG, _LARGE_SMALLSAT_SIZE_M),
            ),
        ],
    )


def build_03_geo_station_keeping() -> Scenario:
    # A 500 kg spacecraft in the 10 deg E slot (a European one), held in a
    # +/-0.05 deg longitude box and below 0.05 deg inclination. It starts in
    # Earth's TRUE equator (engine.orbit_design.geostationary_elements_deg):
    # i = 0 in J2000 is already ~0.17 deg inclined to it by 2030, which the
    # first real run showed as an immediate north-south burn. a = 42166.2 km
    # is the geosynchronous radius once J2 is included. Confirmed in a real
    # Basilisk run, see tests/test_template_claims.py.
    epoch = "2030-01-01T00:00:00"
    inclination_deg, raan_deg, true_anomaly_deg = geostationary_elements_deg(epoch, 10.0)
    return Scenario(
        name="03 - GEO station-keeping",
        description=(
            DESCRIPTIONS["03"]
        ),
        epoch_utc=epoch,
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=45.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="geo-sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=42166.2, eccentricity=0.0,
                               inclination_deg=inclination_deg, raan_deg=raan_deg, arg_periapsis_deg=0.0,
                               true_anomaly_deg=true_anomaly_deg),
                dry_mass_kg=_LARGE_SMALLSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_LARGE_SMALLSAT_MASS_KG, _LARGE_SMALLSAT_SIZE_M),
                enable_srp=True, srp_coeff=1.3, srp_area_m2=8.0,
                geo_station_keeping=GeoStationKeepingConfig(
                    target_longitude_deg=10.0, longitude_deadband_deg=0.05, inclination_max_deg=0.05,
                    thrust_n=1.0, isp_s=220.0, propellant_kg=50.0,  # [N], [s] (hydrazine), [kg]
                ),
            ),
        ],
    )


def build_04_walker_constellation() -> Scenario:
    # 700 km is genuinely drag-relevant LEO altitude -- drag/SRP enabled
    # on the shared template so generate_walker_constellation() copies it
    # onto every satellite (see this function's own description update
    # below for the reasoning).
    template = SpacecraftConfig(
        name="placeholder",  # replaced per-satellite by generate_walker_constellation()
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=1.0, eccentricity=0.0,
                       inclination_deg=0.0, raan_deg=0.0, arg_periapsis_deg=0.0, mean_anomaly_deg=0.0,
                       anomaly_type="mean"),
        dry_mass_kg=180.0,
        inertia_kg_m2=_box_inertia(180.0, _MICROSAT_SIZE_M),
        enable_drag=True, drag_coeff=OPERATIONS_DRAG_COEFF, drag_area_m2=1.0,
        enable_srp=True, srp_coeff=1.3, srp_area_m2=1.0,
    )
    request = WalkerConstellationRequest(
        total_satellites=6, num_planes=2, phasing_factor=1, altitude_km=700.0, inclination_deg=53.0,
        pattern="delta", name_prefix="leo",
    )
    spacecraft = generate_walker_constellation(request, template)
    return Scenario(
        name="04 - Walker delta constellation",
        description=(
            DESCRIPTIONS["04"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=1.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        space_weather=_real_space_weather(),
        spacecraft=spacecraft,
    )


def build_05_formation_flying_phasing() -> Scenario:
    return Scenario(
        name="05 - Formation flying (phasing control)",
        description=(
            DESCRIPTIONS["05"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        # third_body_perturbers=["sun", "moon"]: follower-1's station_keeping
        # (below, required by phasing_keeping) needs the real eclipse shadow
        # factor for its eclipse-gated reboost burn, which needs a sun
        # ephemeris -- see engine.service.SimulationService.build()'s own
        # SimulationServiceError if this is missing (caught on a real run:
        # this template originally had an empty third_body_perturbers list).
        # "moon" added alongside "sun" for full-perturbation realism (see
        # this function's own description update above).
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        # duration_days=90.0 -- a real user pointed out that a short run here
        # isn't interesting: phasing_keeping's whole point is the LONG-TERM
        # along-track drift/correction cycle and its accumulated delta-V, and
        # a 24-day run (an earlier revision of this template) never drifts
        # far enough to trigger even one correction -- confirmed directly
        # against a real Basilisk run (degree-10 Earth gravity, no Sun/Moon/
        # drag): over 90 days the separation drifts to phasing_keeping's 10%
        # tolerance band around day 28, which fires one real correction that
        # brings it back in ~2.4 days, keeping it within ~45-52 km for
        # ~0.014 m/s of phasing delta-V (re-verified with the 3-day default
        # correction window; 21 days gave ~0.003 m/s over ~2 weeks) -- exactly the
        # "drift, then correct" behavior this controller exists to show, not
        # visible at 24 days.
        #
        # 90 days (not longer) is also a real platform ceiling, not just a
        # stylistic choice: Basilisk's own nanoToSec() (C++,
        # src/architecture/utilities/macroDefinitions.h) can only exactly
        # represent a nanosecond count up to 2**53 ns (~104.25 days) as a
        # double; past that it prints a stderr error on EVERY call and
        # returns NaN, poisoning all downstream time-dependent math (hit
        # directly in this audit with a 180-day test run: simulated time
        # barely progressed past the cliff at all). 90 days stays safely
        # clear of that limit with margin -- see SimSettings.validate()'s
        # own upper bound on duration_days, added for exactly this reason.
        sim_settings=SimSettings(duration_days=90.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        space_weather=_real_space_weather(),
        spacecraft=[
            SpacecraftConfig(
                name="chief-1",
                # eccentricity=0.001, not 0.0 -- both orbits used to be exactly
                # circular, which crashed on a real run: orbitalMotion.rv2elem()
                # (used by engine.orbit_maintenance.PhasingKeepingController to
                # measure each spacecraft's along-track phase) only trusts its
                # stable near-circular formula below e=1e-11, and this
                # template's own sun third-body perturbation and commanded
                # thrust are enough to push a nominally-circular orbit's real,
                # propagated eccentricity above that -- at which point rv2elem()
                # silently falls back to measuring phase from the eccentricity
                # VECTOR's direction, which is numerically meaningless (noise
                # -dominated) once eccentricity is that close to zero. A small,
                # deliberate eccentricity (0.001) keeps rv2elem() safely on its
                # normal, stable branch for SMA/e/i recovery -- but
                # PhasingKeepingController no longer uses rv2elem()'s own
                # (e, omega, f) decomposition for its phase error AT ALL (see
                # that class's own "Numerical conditioning of the phase error"
                # docstring section: it was found, by audit against a real
                # Basilisk build with real J2 active on exactly these elements,
                # to be independently singular at this same e -> 0 regime no
                # matter how small a deliberate eccentricity is chosen --
                # replaced with a numerically robust argument-of-latitude
                # computed directly from r/v).
                #
                # The "~7 km of altitude variation -- well inside
                # station_keeping's deadband once smoothed over one orbital
                # period" claim this comment used to make here was WRONG,
                # also found only once checked against a real Basilisk build
                # with real (degree >= 2) spherical-harmonics gravity active:
                # a one-orbital-period boxcar average of the RAW osculating
                # altitude at these elements converges to a STABLE ~545 km,
                # not the ~550 km target -- a genuine ~5 km secular offset
                # between the osculating semi-major axis this orbit is
                # initialized with and the true time-averaged radius under
                # real J2 (confirmed stable across 1/2/3/5/10-orbital-period
                # windows alike, so this is not averaging noise/bias from an
                # imperfect window length -- it is real), on top of which
                # J2's own short-period altitude oscillation adds further
                # swing. A 2 km deadband has no margin over either -- see
                # station_keeping's own deadband_km below, widened for
                # exactly this reason.
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                               inclination_deg=sun_synchronous_inclination_deg(6928.0, 0.001),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=400.0,
                inertia_kg_m2=_box_inertia(400.0, _SMALLSAT_SIZE_M),
                enable_drag=True, drag_coeff=OPERATIONS_DRAG_COEFF, drag_area_m2=1.0,
                enable_srp=True, srp_coeff=1.3, srp_area_m2=1.0,
                # chief-1 needs its OWN station_keeping too -- a real
                # design bug, found from direct user feedback: a "chief"
                # that holds no altitude at all isn't a chief, it's just an
                # uncontrolled object the follower happens to be phased
                # against -- and it directly contradicts
                # engine.formation.py's own stated design for this exact
                # two-spacecraft shape ("the two-satellite 'chief holds
                # station, follower holds formation' case
                # 05_formation_flying_phasing.json demonstrates by hand" --
                # see that module's own docstring, written when this
                # template was first built but never actually implemented
                # here). Same hardware as follower-1's own station_keeping
                # below -- a realistic "sister satellite" pair, not a
                # special case.
                station_keeping=StationKeepingConfig(
                    target_altitude_km=550.0, deadband_km=15.0, thrust_n=0.05, isp_s=1500.0, propellant_kg=5.0,
                ),
            ),
            SpacecraftConfig(
                name="follower-1",
                # anomaly_type="mean", mean_anomaly_deg=0.413509 (not
                # true_anomaly_deg=-0.5) -- a real design-intent bug, found
                # from direct user feedback: the ORIGINAL -0.5 deg offset put
                # follower-1 trailing chief-1 by ~60 km while
                # phasing_keeping's target_separation_km=50.0 (below) is
                # defined as a LEADING separation (see
                # PhasingKeepingController's own docstring: always a
                # positive, "B leads A" distance) -- so the default run
                # didn't demonstrate "hold a fixed formation distance with a
                # small margin of error" at all; it demonstrated a one-time,
                # 110 km realignment maneuver that passes close by the chief
                # on the way (see duration_days's own comment below for that
                # whole investigation). phasing_keeping is a FORMATION
                # -KEEPING controller, not a rendezvous/phasing-transfer
                # planner -- its correct default demo is steady-state
                # maintenance, not a transition between two different
                # relative states.
                #
                # Fixed by placing follower-1's own initial mean anomaly
                # EXACTLY at the target separation from chief-1's (chief is
                # at true_anomaly_deg=0.0 above, which for ANY eccentricity
                # is exactly mean anomaly 0.0 too -- true and mean anomaly
                # are identically 0 at periapsis, no approximation here):
                # along_track_rad = target_separation_km * 1000 / chief_sma_m
                #                 = 50000 / 6928000 = 0.0072171 rad
                #                 = 0.413509 deg
                # -- the exact same arc-length relation both
                # engine.orbit_maintenance.SeparationSchedule and
                # engine.formation.generate_phasing_follower() already use
                # (the latter is this exact fix's own precedent: the
                # "Generate phasing formation..." GUI generator has ALWAYS
                # placed a new follower exactly at its target separation --
                # "Achieved to that exact value ... confirmed against a real
                # Basilisk run" per that function's own docstring -- this
                # template's hand-authored JSON was simply never updated to
                # match that same, already-correct design). Starting exactly
                # on target means the run now shows what phasing_keeping
                # actually does in normal operation: small, periodic
                # corrections holding the separation within
                # tolerance_fraction of target as real perturbations
                # (differential drag from follower-1's extra propellant
                # mass, J2, Sun/Moon) nudge it off -- never a large
                # transition, never passing the chief.
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                               inclination_deg=sun_synchronous_inclination_deg(6928.0, 0.001),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, anomaly_type="mean", mean_anomaly_deg=0.413509),
                dry_mass_kg=400.0,
                inertia_kg_m2=_box_inertia(400.0, _SMALLSAT_SIZE_M),
                enable_drag=True, drag_coeff=OPERATIONS_DRAG_COEFF, drag_area_m2=1.0,
                enable_srp=True, srp_coeff=1.3, srp_area_m2=1.0,
                station_keeping=StationKeepingConfig(
                    # deadband_km=15.0, not 2.0 -- widened by audit (see the
                    # orbit= comment above): this orbit's own real, natural
                    # (non-decaying) J2 + eccentricity altitude variation is
                    # already ~5-10 km, which a 2 km deadband has no margin
                    # over at all, so the smoothed altitude reads "below
                    # target" from legitimate orbital mechanics alone -- not
                    # real secular (e.g. drag) decay -- and the controller
                    # (correctly, by its own design) burns to correct it,
                    # confirmed on a real Basilisk run to fire continuously
                    # for ~7 real hours straight at deadband_km=2.0. Standard
                    # industry practice for a real deadband is to size it
                    # with margin over an orbit's own natural short-period
                    # variation, not just "as tight as the mission can
                    # tolerate" -- 15 km comfortably covers this orbit's
                    # natural swing while still catching genuine drag decay
                    # (this template's own enable_drag=True) well before it
                    # could matter.
                    target_altitude_km=550.0, deadband_km=15.0, thrust_n=0.05, isp_s=1500.0, propellant_kg=5.0,
                ),
                phasing_keeping=PhasingKeepingConfig(
                    chief_spacecraft="chief-1", target_separation_km=[50.0],
                ),
            ),
        ],
    )


def build_06_attitude_pointing_basic() -> Scenario:
    return Scenario(
        name="06 - Basic attitude pointing (idealized actuation)",
        description=(
            DESCRIPTIONS["06"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        # Gravity harmonics/third-body added for realism (invisible to the
        # attitude-pointing lesson below); drag/SRP deliberately NOT
        # enabled -- this template's own role is to stay the SIMPLE
        # version ('07' is explicitly "the realistic counterpart").
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        # dynamics_task_rate_s=0.1 (NOT the schema's own 10.0 default, and
        # NOT this template's previous 1.0): confirmed directly against a
        # real Basilisk build that idealized-actuation mrpFeedback control
        # (engine/fsw.py's DEFAULT_MRP_GAINS, K=3.5/P=30 -- lifted from
        # Basilisk's own examples/BskSim reference, which runs its FSW task
        # at fswRate=0.1s) goes numerically unstable -- sigma_BN reaches
        # NaN within ~15 task ticks -- at 1.0s with this template's inertia
        # (then 12.5 kg*m^2), because mrpFeedback's commanded torque is a
        # zero-order hold applied for the WHOLE task period: a coarser
        # period needs a proportionally weaker P relative to inertia to stay
        # discrete-time stable (see _osculating_elements()'s own
        # SimulationServiceError message in engine/service.py, which already
        # names exactly this failure mode). 0.1s matches the reference
        # fswRate this K/P pair is tuned against and was confirmed stable
        # (no NaN) over this template's full duration. See HISTORY.md for
        # the full investigation -- this is a general risk for ANY
        # idealized-actuation spacecraft left on a coarse
        # dynamics_task_rate_s, not specific to this template.
        sim_settings=SimSettings(duration_days=0.05, dynamics_task_rate_s=0.1, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6928.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_SMALLSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_SMALLSAT_MASS_KG, _SMALLSAT_SIZE_M),
                sigma_bn_init=[0.1, 0.2, -0.15],
                omega_bn_b_init_rad_s=[0.001, -0.001, 0.0005],
                fsw_mode="hillPoint",
            ),
        ],
    )


def build_07_attitude_pointing_with_adcs_hardware() -> Scenario:
    return Scenario(
        name="07 - Attitude pointing with real ADCS hardware",
        description=(
            DESCRIPTIONS["07"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        # third_body_perturbers=["sun", "moon"]: sat-1's PowerConfig (below)
        # needs the real eclipse shadow factor for its solar-panel power
        # generation, which needs a sun ephemeris -- same reasoning as '05'
        # -- and sunSafePoint's own sun-pointing already conceptually wants
        # a real sun to point at. See engine.service.SimulationService.
        # build()'s own SimulationServiceError if this is missing (caught
        # on a real run: this template originally had an empty
        # third_body_perturbers list). "moon" added alongside "sun" for
        # full-perturbation realism (see this function's own description
        # update above).
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=0.05, dynamics_task_rate_s=1.0, integrator="rkf78"),
        space_weather=_real_space_weather(),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6928.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_MICROSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_MICROSAT_MASS_KG, _MICROSAT_SIZE_M),
                enable_drag=True, drag_coeff=OPERATIONS_DRAG_COEFF, drag_area_m2=1.0,
                enable_srp=True, srp_coeff=1.3, srp_area_m2=1.0,
                sigma_bn_init=[0.1, 0.2, -0.15],
                omega_bn_b_init_rad_s=[0.001, -0.001, 0.0005],
                sensors=[
                    SensorConfig(kind="star_tracker", name="st-1", params={"noise_arcsec": 5.0}),
                    SensorConfig(kind="imu", name="imu-1", params={"gyro_noise_rad_s": 1e-5}),
                    # +Z: the face sunSafePoint turns to the Sun (its default
                    # sHatBdyCmd); a +X sensor would see it edge-on, i.e. never.
                    SensorConfig(kind="coarse_sun_sensor", name="css-1", params={"nHat_B": [0.0, 0.0, 1.0]}),
                ],
                actuators=[
                    ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                    params={"gsHat_B": [1.0, 0.0, 0.0], **_MICROSAT_WHEEL}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-2",
                                    params={"gsHat_B": [0.0, 1.0, 0.0], **_MICROSAT_WHEEL}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-3",
                                    params={"gsHat_B": [0.0, 0.0, 1.0], **_MICROSAT_WHEEL}),
                ],
                fsw_mode="sunSafePoint",
                # No control_params: the default gains are scaled to this
                # bus's inertia (engine.fsw._default_mrp_gains_for_inertia).
                # The unscaled K=3.5/P=30 (tuned for a 900 kg*m^2 spacecraft)
                # left an earlier 5 kg*m^2 version of this template in a
                # 30-degree oscillation.
                # A 12 W bus load and a battery starting at 80%: with the old
                # 0 W load and a full battery, charge sat flat at 80 Wh for
                # the whole run (confirmed in a real Basilisk run). Now it
                # charges to full in sunlight and drains ~6 Wh per eclipse.
                power=PowerConfig(panel_area_m2=0.3, panel_efficiency=0.28, battery_capacity_wh=80.0,
                                  bus_idle_power_w=12.0, battery_initial_soc=0.8),
            ),
        ],
    )


def build_08_mission_sequence_orbit_raise() -> Scenario:
    from spacemissionstudio.schema.command import Command

    return Scenario(
        name="08 - Mission sequence: impulsive orbit raise",
        description=(
            DESCRIPTIONS["08"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=1.0, dynamics_task_rate_s=10.0, integrator="rkf78"),
        space_weather=_real_space_weather(),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6778.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_LARGE_SMALLSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_LARGE_SMALLSAT_MASS_KG, _LARGE_SMALLSAT_SIZE_M),
                enable_drag=True, drag_coeff=OPERATIONS_DRAG_COEFF, drag_area_m2=1.0,
                enable_srp=True, srp_coeff=1.3, srp_area_m2=1.0,
            ),
        ],
        mission_sequence=[
            Command(kind="propagate", label="Coast before burn",
                    params={"stop_condition": "duration", "duration_days": 0.1}),
            Command(kind="report", label="Before burn", params={"series": []}),
            Command(kind="maneuver", label="Prograde raise burn",
                    params={"spacecraft": "sat-1", "delta_v_m_s": [50.0, 0.0, 0.0], "frame": "vnb"}),
            Command(kind="propagate", label="Coast after burn",
                    params={"stop_condition": "duration", "duration_days": 0.5}),
            Command(kind="report", label="After burn", params={"series": []}),
        ],
    )


def build_09_monte_carlo_dispersion_analysis() -> Scenario:
    return Scenario(
        name="09 - Monte Carlo dispersion analysis",
        description=(
            DESCRIPTIONS["09"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=1.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6778.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_LARGE_SMALLSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_LARGE_SMALLSAT_MASS_KG, _LARGE_SMALLSAT_SIZE_M),
            ),
        ],
        monte_carlo=MonteCarloConfig(
            enabled=True, num_runs=20, thread_count=1,
            dispersions=[
                DispersionConfig(spacecraft="sat-1", quantity="dry_mass_kg", kind="normal",
                                   mean=500.0, std_deviation=25.0),
            ],
        ),
    )


def build_10_gravity_gradient_torque() -> Scenario:
    return Scenario(
        name="10 - Gravity gradient torque (uncontrolled)",
        description=(
            DESCRIPTIONS["10"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        # Point-mass gravity only, no third-body perturbers, no drag/SRP --
        # isolates the gravity-gradient effect from every other torque/
        # perturbation source, same "isolate the one concept" role as '01'/
        # '06'/'09'.
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=0.5, dynamics_task_rate_s=5.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6778.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                # An elongated 1 x 1 x 2 m bus: the spread between Izz and
                # Ixx/Iyy is what gravity gradient acts on.
                dry_mass_kg=_LARGE_SMALLSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_LARGE_SMALLSAT_MASS_KG, (1.0, 1.0, 2.0)),  # [kg*m^2] 208.3/208.3/83.3
                sigma_bn_init=[0.0, 0.0, 0.0],
                omega_bn_b_init_rad_s=[0.0, 0.0, 0.0],
                enable_gravity_gradient=True,
            ),
        ],
    )


def build_11_thruster_attitude_control() -> Scenario:
    return Scenario(
        name="11 - Attitude control via thrusters (no reaction wheels)",
        description=(
            DESCRIPTIONS["11"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=0.01, dynamics_task_rate_s=0.5, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_SMALLSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_SMALLSAT_MASS_KG, _SMALLSAT_SIZE_M),
                sigma_bn_init=[0.3, 0.2, -0.1],
                omega_bn_b_init_rad_s=[0.0, 0.0, 0.0],
                fsw_mode="inertial3D",
                fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
                # Default (inertia-scaled) gains. On an earlier 10 kg*m^2
                # version they asked for on-times below the thrusters' 20 ms
                # minimum, so the thrusters barely fired; on this bus they
                # do not.
                actuators=[
                    ActuatorConfig(kind="thruster", name=f"thr-{i + 1}", params=params)
                    for i, params in enumerate(_corner_thrusters((0.6, 0.6, 0.75), 1.0))  # [m], [N]
                ],
            ),
        ],
    )


def build_12_reaction_wheel_momentum_dumping() -> Scenario:
    return Scenario(
        name="12 - Reaction wheel momentum dumping",
        description=(
            DESCRIPTIONS["12"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=0.01, dynamics_task_rate_s=1.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6928.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_LARGE_SMALLSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_LARGE_SMALLSAT_MASS_KG, _LARGE_SMALLSAT_SIZE_M),
                sigma_bn_init=[0.0, 0.0, 0.0],
                omega_bn_b_init_rad_s=[0.0, 0.0, 0.0],
                fsw_mode="inertial3D",
                fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
                actuators=[
                    ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                     params={"gsHat_B": [0.7071, 0.0, 0.7071], "rw_type": "Honeywell_HR12",
                                             "maxMomentum": 12.0, "Omega": 4000.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-2",
                                     params={"gsHat_B": [0.0, 0.7071, 0.7071], "rw_type": "Honeywell_HR12",
                                             "maxMomentum": 12.0, "Omega": 2000.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-3",
                                     params={"gsHat_B": [-0.7071, 0.0, 0.7071], "rw_type": "Honeywell_HR12",
                                             "maxMomentum": 12.0, "Omega": 3500.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-4",
                                     params={"gsHat_B": [0.0, -0.7071, 0.7071], "rw_type": "Honeywell_HR12",
                                             "maxMomentum": 12.0, "Omega": 0.0}),
                    *[
                        ActuatorConfig(kind="thruster", name=f"desat-{i + 1}", params=params)
                        for i, params in enumerate(_corner_thrusters(
                            (0.6, 0.6, 0.8), 1.0, thruster_type="MOOG_Monarc_1"))  # [m], [N]
                    ],
                ],
                momentum_dumping=MomentumDumpingConfig(hs_max=9.6, thr_min_fire_time=0.02, max_counter_value=100),  # [N*m*s], [s]
            ),
        ],
    )


def build_13_magnetic_torque_rod_momentum_management() -> Scenario:
    return Scenario(
        name="13 - Reaction wheel momentum management via magnetic torque rods",
        description=(
            DESCRIPTIONS["13"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=120.0 / 1440.0, dynamics_task_rate_s=2.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.14, eccentricity=0.0,
                               inclination_deg=45.0, raan_deg=60.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_MICROSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_MICROSAT_MASS_KG, _MICROSAT_SIZE_M),
                sigma_bn_init=[0.1, 0.2, -0.3],
                omega_bn_b_init_rad_s=[0.001, -0.01, 0.03],
                fsw_mode="inertial3D",
                fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
                actuators=[
                    *[
                        ActuatorConfig(kind="reaction_wheel", name=f"rw-{i + 1}",
                                         params={"gsHat_B": axis, **_MICROSAT_WHEEL})
                        for i, axis in enumerate(_MTB_DEMO_RW_AXES)
                    ],
                    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-1",
                                     params={"gtHat_B": [1.0, 0.0, 0.0], "max_dipole_a_m2": 15.0}),
                    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-2",
                                     params={"gtHat_B": [0.0, 1.0, 0.0], "max_dipole_a_m2": 15.0}),
                    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-3",
                                     params={"gtHat_B": [0.0, 0.0, 1.0], "max_dipole_a_m2": 15.0}),
                    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-4",
                                     params={"gtHat_B": [0.70710678, 0.70710678, 0.0], "max_dipole_a_m2": 15.0}),
                ],
                magnetic_momentum_management=MagneticMomentumManagementConfig(
                    wheel_speed_biases_rad_s=[
                        800.0 * _RPM_TO_RAD_S, 600.0 * _RPM_TO_RAD_S, 400.0 * _RPM_TO_RAD_S, 200.0 * _RPM_TO_RAD_S,
                    ],
                    c_gain=0.003,
                ),
            ),
        ],
    )


def build_14_css_sun_heading_estimation() -> Scenario:
    return Scenario(
        name="14 - Sun-heading estimation from coarse sun sensors",
        description=(
            DESCRIPTIONS["14"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        # "sun" must be SPICE-tracked (third_body_perturbers) -- the CSS
        # estimation chain's sunInMsg needs the same SpicePlanetStateMsg
        # simpleNav's own truth sun direction uses (see engine.service.py's
        # SimulationServiceError guard for this exact requirement).
        gravity=GravityConfig(central_body="earth", central_body_degree=0, third_body_perturbers=["sun"]),
        sim_settings=SimSettings(duration_days=2160.0 / 86400.0, dynamics_task_rate_s=1.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_MICROSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_MICROSAT_MASS_KG, _MICROSAT_SIZE_M),
                sigma_bn_init=[0.1, 0.2, -0.15],
                omega_bn_b_init_rad_s=[0.001, -0.001, 0.0005],
                sensors=[
                    SensorConfig(kind="coarse_sun_sensor", name=f"css-{i + 1}",
                                   params={"nHat_B": nhat, "fov_deg": 160.0})
                    for i, nhat in enumerate([
                        [0.0, 0.707107, 0.707107], [0.707107, 0.0, 0.707107],
                        [0.0, -0.707107, 0.707107], [-0.707107, 0.0, 0.707107],
                        [0.0, -0.965926, -0.258819], [-0.707107, -0.353553, -0.612372],
                        [0.0, 0.258819, -0.965926], [0.707107, -0.353553, -0.612372],
                    ])
                ],
                actuators=[
                    ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                     params={"gsHat_B": [1.0, 0.0, 0.0], **_MICROSAT_WHEEL}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-2",
                                     params={"gsHat_B": [0.0, 1.0, 0.0], **_MICROSAT_WHEEL}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-3",
                                     params={"gsHat_B": [0.0, 0.0, 1.0], **_MICROSAT_WHEEL}),
                ],
                fsw_mode="sunSafePoint",
                fsw_params={"sHatBdyCmd": [0.0, 0.0, 1.0], "use_css_estimation": True},
            ),
        ],
    )


def build_15_celestial_body_pointing() -> Scenario:
    return Scenario(
        name="15 - Direct celestial-body pointing (Moon)",
        description=(
            DESCRIPTIONS["15"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        # dynamics_task_rate_s=0.1: idealized (no actuator hardware)
        # mrpFeedback control with DEFAULT_MRP_GAINS needs this fine a rate
        # to stay discrete-time stable -- see '06's own comment and
        # HISTORY.md for the full investigation; confirmed directly for
        # this exact locationPointing/target_body combination in
        # tests/test_location_pointing_target_body.py.
        sim_settings=SimSettings(duration_days=0.05, dynamics_task_rate_s=0.1, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6928.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_SMALLSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_SMALLSAT_MASS_KG, _SMALLSAT_SIZE_M),
                sigma_bn_init=[0.1, 0.2, -0.15],
                omega_bn_b_init_rad_s=[0.001, -0.001, 0.0005],
                fsw_mode="locationPointing",
                fsw_params={"target_body": "moon", "pHat_B": [0.0, 0.0, 1.0]},
            ),
        ],
    )


def build_16_lambert_transfer() -> Scenario:
    from spacemissionstudio.schema.command import Command

    r_earth_m = 6378.0e3
    # Same timing as examples/scenarioLambertSolver.py: burn a quarter
    # orbit in, arrive half an orbit in. Burning at t = 0 instead puts the
    # transfer arc below Earth's surface (~6366 km), which
    # min_orbit_radius_m rejects; the coast also gives the first report
    # something recorded to show.
    maneuver_time_s = 2490.0  # [s] a quarter of the 9952 s orbit
    time_of_flight_s = 2490.0  # [s]

    return Scenario(
        name="16 - Lambert transfer: solving for a point-to-point delta-V",
        description=(
            DESCRIPTIONS["16"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=0.2, dynamics_task_rate_s=10.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=10000.0, eccentricity=0.001,
                               inclination_deg=5.0, raan_deg=10.0, arg_periapsis_deg=10.0, true_anomaly_deg=10.0),
                dry_mass_kg=330.0,
                inertia_kg_m2=_box_inertia(330.0, _SMALLSAT_SIZE_M),
            ),
        ],
        mission_sequence=[
            Command(kind="propagate", label="Coast to burn point",
                    params={"stop_condition": "duration", "duration_days": maneuver_time_s / 86400.0}),
            Command(kind="report", label="Before transfer", params={"series": []}),
            Command(kind="lambert_transfer", label="Lambert transfer burn", params={
                "spacecraft": "sat-1",
                "target_position_m": [-(r_earth_m + 200.0e3), 0.0, 0.0],
                "time_of_flight_s": time_of_flight_s,
                "max_distance_target_m": 500.0,
                "min_orbit_radius_m": r_earth_m,
            }),
            Command(kind="propagate", label="Coast to arrival",
                    params={"stop_condition": "duration", "duration_days": time_of_flight_s / 86400.0}),
            Command(kind="report", label="After transfer (should match target_position_m)", params={"series": []}),
        ],
    )


def build_17_fuel_tank_depletion() -> Scenario:
    return Scenario(
        name="17 - Real propellant depletion (fuel tank)",
        description=(
            DESCRIPTIONS["17"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        sim_settings=SimSettings(duration_days=0.01, dynamics_task_rate_s=0.5, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_SMALLSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_SMALLSAT_MASS_KG, _SMALLSAT_SIZE_M),
                sigma_bn_init=[0.3, 0.2, -0.1],
                omega_bn_b_init_rad_s=[0.0, 0.0, 0.0],
                fsw_mode="inertial3D",
                fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
                # Default (inertia-scaled) gains. On an earlier 10 kg*m^2
                # version they asked for on-times below the thrusters' 20 ms
                # minimum, so the thrusters barely fired; on this bus they
                # do not.
                actuators=[
                    ActuatorConfig(kind="thruster", name=f"thr-{i + 1}", params=params)
                    for i, params in enumerate(_corner_thrusters((0.6, 0.6, 0.75), 1.0))  # [m], [N]
                ],
                fuel_tank=FuelTankConfig(propellant_mass_kg=0.5, max_propellant_mass_kg=1.0),
            ),
        ],
    )


def build_18_leo_station_keeping() -> Scenario:
    # Verification note (see this function's own description string
    # below for the user-facing version): this sandbox has no route to
    # CelesTrak, so the shipped nrlmsise00 atmosphere model's exact decay
    # rate couldn't be re-verified end-to-end here (same gap as '04'/'05'
    # already document). The station_keeping/drag parameters below WERE
    # tuned and confirmed against a real Basilisk build, bypassing SPICE
    # the same way tests/test_mtb_desaturation.py does, using
    # engine.orbit_maintenance.build_station_keeping() directly against a
    # bare SimulationBaseClass with a real dragDynamicEffector fed by
    # ExponentialAtmosphere -- NOT the shipped nrlmsise00 model, but
    # re-parameterized with a realistic ~400 km reference density
    # (~2.8e-12 kg/m^3, moderate solar activity) and a LEO-appropriate
    # ~60 km scale height (ExponentialAtmosphere's own built-in Earth
    # preset uses an 8.5 km scale height -- correct near the surface, but
    # it underestimates LEO density by roughly 15 orders of magnitude and
    # produces no meaningful decay at all over weeks). With that
    # realistic density, these parameters produced 2-3 real reboost burns
    # over the same 14-day window as '03' and used well under the
    # propellant_kg budget below -- the dragDynamicEffector/
    # StationKeepingController code paths themselves are the SAME
    # already-shipped, already-verified code every other enable_drag
    # template uses, only the verification harness differs.
    return Scenario(
        name="18 - LEO station-keeping",
        description=(
            DESCRIPTIONS["18"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=14.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        space_weather=_real_space_weather(),
        spacecraft=[
            SpacecraftConfig(
                name="leo-sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6778.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=120.0,
                inertia_kg_m2=_box_inertia(120.0, _MICROSAT_SIZE_M),
                enable_drag=True, drag_coeff=OPERATIONS_DRAG_COEFF, drag_area_m2=1.5,
                station_keeping=StationKeepingConfig(
                    target_altitude_km=400.0, deadband_km=1.0, thrust_n=0.05, isp_s=1500.0,
                    propellant_kg=2.0,
                ),
            ),
        ],
    )


# 08:30 UTC: Berlin is near this orbit's ~09:50-local crossing, so the
# first pass comes ~10 min in (see build_19's comment).
_COMMS_EPOCH_UTC = "2030-01-01T08:30:00"


def build_19_sun_pointing_comms_link() -> Scenario:
    # Verification note (see this function's own user-facing description
    # below for the short version): this sandbox has no Basilisk build, so
    # nothing here could be run end-to-end. The ONE piece of numeric tuning
    # this template reuses -- idealized-torque mrpFeedback control on
    # dynamics_task_rate_s=0.1s with the inertia-scaled default gains --
    # is the EXACT combination '06' already confirmed stable against a real
    # Basilisk build (see build_06_attitude_pointing_basic()'s own comment);
    # comms_pointing only supports idealized actuation (see
    # engine.service's own scope note at the comms_pointing branch), so no
    # actuators are configured here, matching that constraint. What is NOT
    # independently re-confirmed here: that this same combo stays stable
    # through MUCH LARGER-angle slews (Sun-pointing <-> ground-station
    # -pointing can be up to a ~180-degree reorientation, not '06's small
    # initial offset) over a much longer run. MRP feedback's own
    # commanded-torque term is naturally bounded regardless of angle size
    # (sigma_BR's magnitude never exceeds 1, with the shadow-set switch
    # keeping it there), which is why this risk is believed low -- but
    # please report back if a real run shows otherwise.
    #
    # Ground-station pass geometry. A Sun-synchronous orbit crosses a given
    # latitude only at two fixed LOCAL times: for this 10:30-LTAN orbit,
    # Berlin (52.5 N) passes under it around 09:50 and 23:10 local solar
    # time. The old midnight-UTC epoch (00:50 in Berlin) therefore put the
    # first pass ~8.2 h into a 12 h run -- real user report: "there's never
    # ground station contact". The epoch is now 08:30 UTC (09:23 in
    # Berlin), so with true_anomaly_deg=0 the first pass starts ~10 min in
    # (sunlit, ~61 deg peak elevation) and a second, low one (~16 deg)
    # follows one orbit later, ~107 min in. Found by searching epoch and
    # starting anomaly with a J2 orbit model and the IAU_EARTH rotation
    # SPICE uses (pck00010), then checked with an RK4 J2 propagation; not
    # yet confirmed in a Basilisk run in this sandbox (no SPICE kernels).
    # tests/test_scenario_templates.py re-checks the geometry offline.
    return Scenario(
        name="19 - Sun-pointing spacecraft with automatic ground-station comms link",
        description=(
            DESCRIPTIONS["19"]
        ),
        epoch_utc=_COMMS_EPOCH_UTC,
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=135.0 / 1440.0, dynamics_task_rate_s=0.1, integrator="rkf78"),
        ground_stations=[
            _berlin_ground_station(rx_antenna_gain_dbi=35.0, system_noise_temp_k=150.0),
        ],
        spacecraft=[
            SpacecraftConfig(
                name="leo-comms-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6928.0),
                               raan_deg=raan_for_ltan_deg(_COMMS_EPOCH_UTC),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_MICROSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_MICROSAT_MASS_KG, _MICROSAT_SIZE_M),
                sigma_bn_init=[0.2, -0.1, 0.15],
                omega_bn_b_init_rad_s=[0.001, -0.001, 0.0005],
                power=PowerConfig(
                    panel_area_m2=0.4, panel_efficiency=0.28, panel_normal_b=[0.0, 0.0, 1.0],
                    bus_idle_power_w=8.0, battery_capacity_wh=40.0, battery_initial_soc=0.9,
                ),
                rf_link=RFLinkConfig(
                    tx_power_w=5.0, frequency_hz=2.2e9, data_rate_bps=5.0e6, tx_antenna_gain_dbi=6.0,
                    required_ebno_db=10.0, antenna_beamwidth_deg=30.0,
                ),
                comms_pointing=CommsPointingConfig(
                    # A different body axis than power.panel_normal_b ([0,0,1], above) --
                    # the downlink patch antenna sits on a different face than the solar
                    # panel, so Sun-pointing and ground-station-pointing are genuinely
                    # different whole-body attitudes, not the same axis re-aimed twice.
                    target_ground_station="berlin-gs", antenna_boresight_b=[1.0, 0.0, 0.0],
                    comms_power_w=15.0,
                ),
            ),
        ],
    )


def build_20_thermal_simulation() -> Scenario:
    # Verification note (same sandbox limitation as every other template's
    # own comment): no Basilisk build exists here, so this couldn't be run
    # end-to-end in this environment. sunSafePoint control uses the same
    # bus, wheels and inertia-scaled default gains as '07';
    # the "thermal" sensor/motor-thermal physical parameters themselves
    # (area_m2/absorptivity/emissivity/mass_kg/specific_heat_j_kg_k) were
    # run for real against this project's own Basilisk venv in
    # tests/test_thermal_simulation.py (realistic values, not the
    # numerically-unstable simplification an early draft of that test
    # file briefly used -- see that test module's own comment on why a
    # tiny heat capacity explodes sensorThermal's explicit-Euler
    # integration at a 1 Hz task rate).
    return Scenario(
        name="20 - Thermal simulation: sensor heating/cooling + reaction-wheel motor heat",
        description=(
            DESCRIPTIONS["20"]
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        # duration_days=0.3 (~7.2 hours) at this orbit's ~100-minute period
        # covers roughly 4 full orbits -- several complete sunlight/eclipse
        # cycles for therm-1's temperature to visibly track, without the
        # dataset size of a much longer run.
        sim_settings=SimSettings(duration_days=0.3, dynamics_task_rate_s=1.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6928.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=_MICROSAT_MASS_KG,
                inertia_kg_m2=_box_inertia(_MICROSAT_MASS_KG, _MICROSAT_SIZE_M),
                sigma_bn_init=[0.1, 0.2, -0.15],
                omega_bn_b_init_rad_s=[0.001, -0.001, 0.0005],
                sensors=[
                    SensorConfig(kind="star_tracker", name="st-1", params={"noise_arcsec": 5.0}),
                    SensorConfig(kind="imu", name="imu-1", params={"gyro_noise_rad_s": 1e-5}),
                    # +Z: the face sunSafePoint turns to the Sun (its default
                    # sHatBdyCmd); a +X sensor would see it edge-on, i.e. never.
                    SensorConfig(kind="coarse_sun_sensor", name="css-1", params={"nHat_B": [0.0, 0.0, 1.0]}),
                    # A small (0.05 m^2), externally-mounted panel sharing
                    # the CSS's own sun-facing +Z normal, so it genuinely
                    # tracks this spacecraft's real sunlight/eclipse cycle.
                    # It used to face +X, which sunSafePoint holds edge-on
                    # to the Sun: zero projected area, so no solar heating
                    # at all once the attitude settled.
                    SensorConfig(kind="thermal", name="therm-1", params={
                        "nHat_B": [0.0, 0.0, 1.0], "area_m2": 0.05, "absorptivity": 0.25, "emissivity": 0.34,
                        "mass_kg": 0.3, "specific_heat_j_kg_k": 890.0, "initial_temp_c": 0.0,
                        "power_draw_w": 0.5, "measurement_noise_std_c": 0.2,
                    }),
                ],
                actuators=[
                    ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                    params={"gsHat_B": [1.0, 0.0, 0.0], **_MICROSAT_WHEEL,
                                            # Optional motor-thermal model
                                            # -- see this template's own
                                            # description above for why
                                            # only this ONE wheel has it.
                                            "motor_thermal_initial_temp_c": 20.0,
                                            "motor_thermal_ambient_temp_c": 20.0,
                                            "motor_thermal_efficiency": 0.7,
                                            "motor_thermal_ambient_resistance_w_c": 5.0,
                                            "motor_thermal_heat_capacity_j_c": 50.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-2",
                                    params={"gsHat_B": [0.0, 1.0, 0.0], **_MICROSAT_WHEEL}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-3",
                                    params={"gsHat_B": [0.0, 0.0, 1.0], **_MICROSAT_WHEEL}),
                ],
                fsw_mode="sunSafePoint",
                power=PowerConfig(panel_area_m2=0.3, panel_efficiency=0.28, battery_capacity_wh=80.0),
            ),
        ],
    )


def build_21_disturbance_torques() -> Scenario:
    # Two copies of one 300 kg Sun-pointing spacecraft, flown side by side:
    # a facet model with the 2.5 m^2 array on a boom 1.5 m off to +Y, so
    # solar pressure (and drag) push off-centre. "rods-off" has only its
    # wheels, which soak up that torque all day; "rods-on" also has torque
    # rods steering its wheels back to rest. Confirmed in a real Basilisk
    # run (see tests/test_template_claims.py).
    epoch = "2030-01-01T00:00:00"
    semi_major_axis_km = 6378.0 + 450.0  # [km] low enough for drag torque to matter too

    def spacecraft(name: str, with_rods: bool) -> SpacecraftConfig:
        axes = (("x", [1.0, 0.0, 0.0]), ("y", [0.0, 1.0, 0.0]), ("z", [0.0, 0.0, 1.0]))
        actuators = [ActuatorConfig(kind="reaction_wheel", name=f"rw-{axis_name}",
                                    params={"gsHat_B": axis, "rw_type": "Honeywell_HR12", "maxMomentum": 12.0})
                     for axis_name, axis in axes]
        if with_rods:
            actuators += [ActuatorConfig(kind="magnetic_torque_rod", name=f"mtb-{axis_name}",
                                         params={"gtHat_B": axis, "max_dipole_a_m2": 30.0})  # [A*m^2]
                          for axis_name, axis in axes]
        return SpacecraftConfig(
            name=name,
            orbit=OrbitIC(type="classical_elements", semi_major_axis_km=semi_major_axis_km, eccentricity=0.0,
                          inclination_deg=sun_synchronous_inclination_deg(semi_major_axis_km),
                          raan_deg=raan_for_ltan_deg(epoch), arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
            dry_mass_kg=_SMALLSAT_MASS_KG,
            inertia_kg_m2=_box_inertia(_SMALLSAT_MASS_KG, _SMALLSAT_SIZE_M),
            enable_drag=True, enable_srp=True,
            facets=box_facets(_SMALLSAT_SIZE_M, 2.5, (0.0, 0.0, 1.0), (0.0, 1.5, 0.75),  # [m], [m^2]
                              drag_coeff=OPERATIONS_DRAG_COEFF),
            sensors=[SensorConfig(kind="coarse_sun_sensor", name="css-1", params={"nHat_B": [0.0, 0.0, 1.0]})],
            actuators=actuators,
            magnetic_momentum_management=(MagneticMomentumManagementConfig(wheel_speed_biases_rad_s=[0.0] * 3)
                                          if with_rods else None),
            fsw_mode="sunSafePoint",
            fsw_params={"sHatBdyCmd": [0.0, 0.0, 1.0]},
        )

    return Scenario(
        name="21 - Disturbance torques from a facet model",
        description=DESCRIPTIONS["21"],
        epoch_utc=epoch,
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=2, third_body_perturbers=["sun"]),
        sim_settings=SimSettings(duration_days=1.0, dynamics_task_rate_s=10.0, integrator="rkf78"),
        space_weather=_real_space_weather(),
        spacecraft=[spacecraft("rods-off", False), spacecraft("rods-on", True)],
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _save(build_01_two_body_circular_orbit(), "01_two_body_circular_orbit.json")
    _save(build_02_elliptical_orbit_with_perturbations(), "02_elliptical_orbit_with_perturbations.json")
    _save(build_03_geo_station_keeping(), "03_geo_station_keeping.json")
    _save(build_04_walker_constellation(), "04_walker_constellation.json")
    _save(build_05_formation_flying_phasing(), "05_formation_flying_phasing.json")
    _save(build_06_attitude_pointing_basic(), "06_attitude_pointing_basic.json")
    _save(build_07_attitude_pointing_with_adcs_hardware(), "07_attitude_pointing_with_adcs_hardware.json")
    _save(build_08_mission_sequence_orbit_raise(), "08_mission_sequence_orbit_raise.json")
    _save(build_09_monte_carlo_dispersion_analysis(), "09_monte_carlo_dispersion_analysis.json")
    _save(build_10_gravity_gradient_torque(), "10_gravity_gradient_torque.json")
    _save(build_11_thruster_attitude_control(), "11_thruster_attitude_control.json")
    _save(build_12_reaction_wheel_momentum_dumping(), "12_reaction_wheel_momentum_dumping.json")
    _save(build_13_magnetic_torque_rod_momentum_management(),
          "13_magnetic_torque_rod_momentum_management.json")
    _save(build_14_css_sun_heading_estimation(), "14_css_sun_heading_estimation.json")
    _save(build_15_celestial_body_pointing(), "15_celestial_body_pointing.json")
    _save(build_16_lambert_transfer(), "16_lambert_transfer.json")
    _save(build_17_fuel_tank_depletion(), "17_fuel_tank_depletion.json")
    _save(build_18_leo_station_keeping(), "18_leo_station_keeping.json")
    _save(build_19_sun_pointing_comms_link(), "19_sun_pointing_comms_link.json")
    _save(build_20_thermal_simulation(), "20_thermal_simulation.json")
    _save(build_21_disturbance_torques(), "21_disturbance_torques.json")


if __name__ == "__main__":
    main()
