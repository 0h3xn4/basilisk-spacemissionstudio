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
from pathlib import Path

from spacemissionstudio.engine.constellation import WalkerConstellationRequest, generate_walker_constellation
from spacemissionstudio.engine.orbit_design import raan_for_ltan_deg, sun_synchronous_inclination_deg
from spacemissionstudio.schema.scenario import (
    CommsPointingConfig,
    DispersionConfig,
    FuelTankConfig,
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

_INERTIA_SMALL = [5.0, 0.0, 0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 5.0]
_INERTIA_MEDIUM = [12.5, 0.0, 0.0, 0.0, 12.5, 0.0, 0.0, 0.0, 7.5]
_RPM_TO_RAD_S = math.pi / 30.0

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


def _conservative_drag_margin() -> SpaceWeatherConfig:
    """A nominal, synthetic atmospheric-drag environment -- a fresh
    instance per call (like ``list(_INERTIA_SMALL)`` above, not a single
    shared object, since ``SpaceWeatherConfig`` is mutable) for every
    template where drag is physically relevant (a LEO altitude) and
    doesn't undermine that template's own stated lesson (see each
    ``build_*()`` function's own comment for why some are, or aren't,
    drag-enabled at all).

    This used to compute a real ``activity_level="conservative"``
    sustained-worst-case margin from real historical CelesTrak data
    (``source="celestrak"``). The app's closed-off/offline policy (see
    ``engine/spaceweather.py``'s own docstring) removed that network fetch
    entirely -- "conservative" mode is now ``local_file``-only, and these
    bundled templates ship no historical CSV to point it at. Rather than
    fabricate a fake "real historical" file, these templates honestly fall
    back to the synthetic, solar-cycle-shaped generator at the default
    ``activity_level="nominal"``. A user who wants the real worst-case
    margin back can still get it: download a CelesTrak CSV themselves
    (outside this app) and set ``space_weather.source="local_file"``,
    ``activity_level="conservative"``, ``local_file_path=<that file>`` in
    the Scenario Editor.
    """
    return SpaceWeatherConfig(source="synthetic", atmosphere_model="nrlmsise00", activity_level="nominal")


def _save(scenario: Scenario, filename: str) -> None:
    scenario.validate()  # fail loudly here, not for whoever opens the file later
    path = OUT_DIR / filename
    scenario.save(path)
    print(f"wrote {path}")


def build_01_two_body_circular_orbit() -> Scenario:
    return Scenario(
        name="01 - Two-body circular orbit",
        description=(
            "The simplest possible orbit: a single spacecraft in a circular low-Earth orbit around a "
            "point-mass Earth (no J2, no drag, no third-body gravity, no attitude dynamics -- "
            "simulation_mode is 'orbit_only'). This is the orbital-mechanics equivalent of a 'hello "
            "world' -- a clean two-body Keplerian orbit with nothing else going on.\n\n"
            "What to look at: plot 'sat-1.position_N' after running -- it traces a perfect circle in "
            "the orbit plane. The orbital period should match Kepler's third law, "
            "T = 2*pi*sqrt(a^3/mu), for a = 6778 km and Earth's mu (~398600.4418 km^3/s^2): about "
            "5554 s (~92.6 minutes), so a 1-day run completes about 15.5 orbits.\n\n"
            "Try changing: the semi_major_axis_km (higher = slower, longer period), the "
            "inclination_deg (watch the ground track in Vizard change), or the eccentricity (still "
            "0 here -- see '02 - Elliptical orbit with perturbations' for a non-circular example).\n\n"
            "Orbit is Sun-synchronous (inclination_deg derived via "
            "engine.orbit_design.sun_synchronous_inclination_deg() from this real J2 "
            "formula, not a round number picked by hand) at a 10:30 AM local time of ascending node "
            "(raan_deg via raan_for_ltan_deg(), same module) -- the most common real choice for an "
            "Earth-observation/commercial smallsat, and the new default baseline orbit for this "
            "template catalog's generic LEO examples. Both helpers are importable directly "
            "(``from spacemissionstudio.engine.orbit_design import ...``) -- a bespoke scenario "
            "built from scratch can reproduce this exact orbit without reading this template's own "
            "source."
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
                dry_mass_kg=500.0,
            ),
        ],
    )


def build_02_elliptical_orbit_with_perturbations() -> Scenario:
    return Scenario(
        name="02 - Elliptical orbit with perturbations",
        description=(
            "A geostationary transfer orbit (GTO)-like eccentric orbit, with Earth's oblateness (J2 "
            "and higher-order terms, via 10th-degree spherical harmonics) and third-body gravity from "
            "the Sun and Moon all switched on. Drag is deliberately NOT enabled here (unlike other "
            "templates updated for full perturbations) -- this one's whole point is isolating J2 + "
            "third-body precession cleanly (see 'What to look at' below); a third perturbation source "
            "would muddy that specific visual lesson. dynamics_task_rate_s is deliberately fine (1.0 s) "
            "here: coarser rates "
            "introduce real truncation error into the spherical-harmonics gravity term itself (see "
            "this project's own HISTORY.md, 'What Phase 6 (Mission Sequence architecture) adds', for the "
            "measured effect of this on a real Basilisk run) -- always use a fine rate together with "
            "central_body_degree > 0, not just for point-mass orbits.\n\n"
            "What to look at: plot 'sat-1.position_N' and watch the orbit visibly precess over the "
            "3-day run -- J2 causes the right ascension of the ascending node (RAAN) to regress and "
            "the argument of periapsis to rotate, effects a pure two-body orbit ('01') never shows. "
            "Compare 'sat-1.velocity_N' magnitude at periapsis vs. apoapsis to see orbital speed vary "
            "with a large eccentricity (0.7) -- much faster near Earth, much slower far away.\n\n"
            "Try changing: central_body_degree back to 0 to see the perturbation-free case for "
            "comparison, or third_body_perturbers to just [\"moon\"] or [\"sun\"] to isolate each "
            "effect."
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
                dry_mass_kg=1000.0,
            ),
        ],
    )


def build_03_geo_station_keeping() -> Scenario:
    return Scenario(
        name="03 - GEO station-keeping",
        description=(
            "A geostationary communications satellite that actively maintains its altitude against "
            "real perturbations (Sun/Moon third-body gravity and solar radiation pressure -- the "
            "actual drivers of GEO longitude/altitude drift in practice) using a simple deadband "
            "thrust controller: it fires station_keeping's thruster whenever the propagated altitude "
            "drifts more than deadband_km from target_altitude_km, burning propellant tracked in "
            "propellant_kg.\n\n"
            "What to look at: run the CLI ('spacemissionstudio run ... --out-dir out') and check "
            "command_summary/results for the propellant used over the 14-day run (see this project's "
            "README, 'Running the CLI', for the station-keeping summary output) -- a real budget "
            "question a mission designer has to answer: how much propellant does a decade of GEO "
            "station-keeping cost?\n\n"
            "Try changing: deadband_km (tighter = more frequent, smaller burns), thrust_n/isp_s (a "
            "more efficient thruster uses less propellant per correction), or removing "
            "third_body_perturbers/enable_srp to see how much slower the drift becomes without them "
            "(and how rarely the controller then needs to fire).\n\n"
            "central_body_degree is 10 (not 0) despite GEO altitude: geosynchronous longitude drift "
            "is driven in real life partly by Earth's own longitudinal (tesseral) gravity anomalies, "
            "not just Sun/Moon/SRP -- a real GEO perturbation this spherical-harmonics degree can "
            "represent. Atmospheric drag is deliberately NOT enabled -- physically negligible at "
            "42164 km (no meaningful atmosphere there); enabling it would misrepresent the physics, "
            "not add realism."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=14.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        spacecraft=[
            SpacecraftConfig(
                name="geo-sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=42164.0, eccentricity=0.0,
                               inclination_deg=0.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=1200.0,
                enable_srp=True, srp_coeff=1.3, srp_area_m2=15.0,
                station_keeping=StationKeepingConfig(
                    target_altitude_km=35786.0, deadband_km=5.0, thrust_n=0.5, isp_s=1600.0,
                    propellant_kg=50.0,
                ),
            ),
        ],
    )


def build_04_walker_constellation() -> Scenario:
    # 700 km is genuinely drag-relevant LEO altitude -- drag/SRP enabled
    # on the shared template so generate_walker_constellation() copies it
    # onto every satellite (see this function's own description update
    # below for the reasoning and the conservative-margin caveat).
    template = SpacecraftConfig(
        name="placeholder",  # replaced per-satellite by generate_walker_constellation()
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=1.0, eccentricity=0.0,
                       inclination_deg=0.0, raan_deg=0.0, arg_periapsis_deg=0.0, mean_anomaly_deg=0.0,
                       anomaly_type="mean"),
        dry_mass_kg=180.0,
        enable_drag=True, drag_coeff=2.2, drag_area_m2=1.0,
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
            "A small 6-satellite Walker delta constellation (2 orbital planes, 3 satellites per "
            "plane, phasing factor 1) at 700 km altitude / 53 deg inclination -- generated "
            "programmatically via engine.constellation.generate_walker_constellation() rather than "
            "hand-written, exactly how the GUI's 'Generate Walker constellation...' dialog "
            "(gui/constellation_dialog.py, off the spacecraft list's own button) and "
            "'spacemissionstudio generate-constellation' CLI subcommand build one.\n\n"
            "What to look at: open this in the GUI and look at Vizard's ground track (or plot each "
            "satellite's 'position_N' series) -- the 2 planes are spread 180 deg apart in RAAN "
            "('delta' pattern; a 'star' pattern spreads them over 360 deg total instead), and "
            "satellites within a plane are evenly spaced by mean anomaly, offset between planes by "
            "the phasing factor. This is the standard way real LEO broadband/imaging constellations "
            "(the thing 'Starlink-shell-like' parameters like these are modeled after) achieve "
            "repeatable global coverage with a minimal satellite count.\n\n"
            "Try changing: total_satellites/num_planes (regenerate via the CLI/GUI, not by hand "
            "-editing this file's spacecraft list) to see how coverage geometry changes, or "
            "phasing_factor to change how planes interleave relative to each other.\n\n"
            "Updated to include 10th-degree spherical-harmonics gravity, Sun/Moon third-body gravity, "
            "atmospheric drag, and solar radiation pressure on every satellite -- a 700 km Walker "
            "constellation genuinely experiences all of these. Drag uses a nominal, SYNTHETIC "
            "(solar-cycle-shaped, not a real forecast) space-weather profile, generated entirely "
            "locally -- see engine/spaceweather.py's own 'Closed-off/offline policy' docstring: this "
            "app makes no network calls at runtime, so a CONSERVATIVE, percentile-based worst-case "
            "margin (which needs real historical F10.7/Ap data) isn't available out of the box here "
            "anymore. To get that margin back, download a CelesTrak CSV yourself (outside this app) "
            "and set space_weather.source='local_file', activity_level='conservative', "
            "local_file_path=<that file> in the Scenario Editor."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=1.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        space_weather=_conservative_drag_margin(),
        spacecraft=spacecraft,
    )


def build_05_formation_flying_phasing() -> Scenario:
    return Scenario(
        name="05 - Formation flying (phasing control)",
        description=(
            "Two spacecraft in near-identical, Sun-synchronous orbits: 'follower-1' holds a FIXED "
            "in-track separation 50 km AHEAD of chief 'chief-1' (target_separation_km is always a "
            "positive, 'B leads A' distance -- see PhasingKeepingController's own docstring) using "
            "phasing_keeping -- a closed-loop controller that measures the along-track separation and "
            "fires small along-track burns to correct DRIFT away from that target, not to transition "
            "between two different relative states. chief-1 runs station_keeping to hold the "
            "formation's altitude; follower-1's own station_keeping (phasing_keeping always needs it on "
            "the SAME spacecraft -- one shared thruster and tank) holds altitude RELATIVE to chief-1, "
            "mirroring chief-1's reboosts rather than reboosting on its own: two independent reboosts "
            "would leave a km-scale semi-major-axis mismatch that drifts the pair apart by degrees per "
            "day (see PhasingKeepingConfig's own docstring).\n\n"
            "What to look at: follower-1 starts EXACTLY at the 50 km target (see the orbit= comment "
            "below for the exact math) -- this is formation-KEEPING, not a rendezvous/phasing-transfer "
            "maneuver, so the separation starts right on target and the interesting behavior is the "
            "LONG-TERM drift/correction cycle over the full 90-day run, not an instant snapshot. "
            "Confirmed on a real Basilisk run (degree-10 Earth gravity, without the Sun/Moon/drag "
            "this template also enables): small real perturbations make the separation drift slowly "
            "away from 50 km; it reaches phasing_keeping's 10% tolerance band (45 km) around day 28, "
            "which fires ONE small along-track correction that drifts it back toward 50 km in ~2.4 "
            "days (phasing_keeping.correction_window_days = 3), and keeps it within ~45-52 km for the "
            "whole run, for only ~0.014 m/s of phasing delta-V in total -- this "
            "IS the point of phasing_keeping: a formation mostly drifts on its own and the controller "
            "only steps in once drift exceeds the tolerance band, rather than fighting every tiny "
            "perturbation continuously. A shorter run (try duration_days=24.0) stays inside the "
            "tolerance band the whole time and never shows a correction at all. 'spacemissionstudio "
            "run' prints a phasing delta-V breakdown in its station-keeping summary (see README, "
            "'Running the CLI').\n\n"
            "Try changing: target_separation_km (a schedule -- see PhasingKeepingConfig; a single "
            "-element list holds one separation for the whole run, more elements step through a "
            "schedule), phasing_keeping.tolerance_fraction (tighter triggers a correction sooner), "
            "phasing_keeping.correction_window_days (how long a correction takes: delta-V scales "
            "roughly as 1 / window -- here 21 days cost ~0.003 m/s, 3 days ~0.014 m/s), "
            "sim_settings.duration_days (shorter than ~35 days and no correction will fire at all; "
            "SimSettings.validate() caps this at 100.0 days -- see that method's own comment for why), "
            "or follower-1's own starting mean_anomaly_deg to begin with a deliberate mismatch and "
            "watch phasing_keeping correct it back onto target sooner.\n\n"
            "Updated to include 10th-degree spherical-harmonics gravity, Sun/Moon third-body gravity, "
            "atmospheric drag, and solar radiation pressure on both spacecraft (identically, so any "
            "chief/follower difference in behavior is real physics, not asymmetric configuration) -- "
            "drag uses a nominal, SYNTHETIC (solar-cycle-shaped, not a real forecast) space-weather "
            "profile generated entirely locally, no network access needed (see "
            "engine/spaceweather.py's own 'Closed-off/offline policy' docstring: this app makes no "
            "network calls at runtime, so a real-historical-data CONSERVATIVE margin isn't available "
            "out of the box here anymore -- see template 04's own description for how to restore it "
            "via a self-supplied local CelesTrak CSV).\n\n"
            "Audit history (most recent first): a real user found the phasing too slow -- the "
            "correction window was 21 days, so closing 50 km to a 100 km target took three weeks. "
            "The default is now 3 days (~0.13 m/s for that 50 km, verified with Basilisk). Before "
            "that, a real user's 90-day run of an edited copy of this "
            "template (follower-1 targeting 100 km with a 2 km station-keeping deadband) had "
            "follower-1 lapping chief-1 for the whole run. follower-1's own station-keeping had "
            "reboosted it alone to its absolute 550 km target, ~5 km above this orbit's natural "
            "~545 km mean altitude, and the phasing controller's open-loop restore burns could never "
            "undo a mismatch they hadn't made. Fixed: follower station-keeping now mirrors the chief, "
            "and phasing burns are sized from the MEASURED relative semi-major axis (exported as "
            "follower-1.phasing_keeping.relative_semi_major_axis), and are no longer rounded up to "
            "whole 30 s thruster ticks (each correction used to overshoot ~10x). Before that, a real user "
            "pointed out that a short run here isn't "
            "interesting -- phasing_keeping's whole point is the long-term drift/correction cycle and "
            "its accumulated delta-V, neither of which a 24-day run (the previous duration_days) ever "
            "shows. Fixed by moving to duration_days=90.0 (see that field's own comment below), "
            "verified on a real Basilisk run to show two real correction cycles and nonzero delta-V, "
            "while staying safely clear of a separately-discovered real Basilisk platform limit: "
            "nanoToSec() (C++, src/architecture/utilities/macroDefinitions.h) can only exactly "
            "represent nanosecond counts up to 2**53 (~104.25 days) as a double, so a duration much "
            "beyond 90 days risks silently poisoning the whole run with NaN time (see duration_days's "
            "own comment below, and SimSettings.validate()'s new upper bound, added specifically to "
            "catch this before it can happen through any scenario, bundled or user-built). A real user "
            "pointed out that this template's own design didn't actually match 'maintain a fixed "
            "distance with a margin of error' -- "
            "follower-1 used to start ~60 km BEHIND chief-1 while targeting 50 km AHEAD, which made "
            "the default run demonstrate a one-time ~110 km realignment (passing close by the chief "
            "on the way) rather than steady-state formation-keeping, and chief-1 had no station_keeping "
            "of its own at all, contradicting engine.formation.py's own stated 'chief holds station, "
            "follower holds formation' design for this exact two-spacecraft shape. Both fixed (see the "
            "orbit=/station_keeping= comments below) -- engine.formation.generate_phasing_follower() "
            "(the 'Generate phasing formation...' GUI generator) already placed a NEW follower exactly "
            "on its target separation; this template's hand-authored JSON simply hadn't been updated "
            "to match that same, already-correct design. Earlier in the same investigation: two real "
            "bugs in PhasingKeepingController/StationKeepingController themselves (a numerically "
            "singular phase-error metric at low eccentricity, fixed with a robust argument-of-latitude "
            "computation -- see that class's own docstring; and a station_keeping deadband too tight "
            "for this orbit's natural J2/eccentricity altitude swing, widened to 15 km) plus a "
            "duration_days that was shorter than its own correction_window_days. The REMAINING "
            "untested piece is the real Sun/Moon third-body perturbation specifically (this sandbox "
            "has no route to the NAIF SPICE kernel host needed to include it in these audits' own "
            "verification runs, which used degree-2 Earth-only gravity) -- please report back if "
            "behavior still looks off with that included."
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
        space_weather=_conservative_drag_margin(),
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
                enable_drag=True, drag_coeff=2.2, drag_area_m2=1.0,
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
                enable_drag=True, drag_coeff=2.2, drag_area_m2=1.0,
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
            "A spacecraft pointing its body frame to track the local vertical/local horizontal frame "
            "(fsw_mode 'hillPoint' -- nadir-pointing, the natural first attitude-control example: see "
            "engine/fsw.py's own docstring, copied from examples/scenarioAttitudeGuidance.py) with NO "
            "sensors or actuators configured -- with no 'reaction_wheel' actuators present, the "
            "control torque is applied directly to the hub via an idealized ExtForceTorque effector "
            "(see engine/fsw.py's build_idealized_actuation()), skipping real hardware modeling "
            "entirely so this example is only about the pointing CONCEPT. See '07' for the same idea "
            "with real ADCS hardware in the loop.\n\n"
            "The spacecraft starts tipped away from the target attitude (sigma_bn_init is non-zero) "
            "with a small initial body rate -- watch the attitude error converge to zero as the "
            "controller (mrpFeedback, closing the loop on simpleNav's truth attitude) drives it to "
            "track hillPoint's commanded frame.\n\n"
            "What to look at: this scenario's own attitude state isn't in the CSV export series by "
            "default; add a 'report' mission_sequence command (see '08') or inspect "
            "sat-1.omega_BN_B/attitude state directly via the schema/engine layer if you extend this "
            "-- or simplest, watch it converge visually in Vizard's live attitude indicator.\n\n"
            "Try changing: fsw_mode to 'velocityPoint' (tracks the velocity vector instead of nadir) "
            "or 'inertial3D' (points at a fixed inertial attitude, ignoring the orbit entirely) to "
            "compare pointing behaviors."
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
        # (_INERTIA_MEDIUM), because mrpFeedback's commanded torque is a
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
                dry_mass_kg=300.0,
                inertia_kg_m2=list(_INERTIA_MEDIUM),
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
            "The realistic counterpart to '06': the same pointing problem, but with an actual ADCS "
            "hardware suite modeled -- a star tracker and IMU for attitude/rate sensing, a coarse sun "
            "sensor, and three reaction wheels (orthogonal spin axes) providing the real control "
            "torque instead of an idealized effector, plus a solar array + battery power budget "
            "(power draw from the sensors/wheels isn't modeled per-component here, but this shows how "
            "a full spacecraft config -- attitude AND power -- fits together). fsw_mode 'sunSafePoint' "
            "is a safe-mode-style controller that points a body axis at the Sun using simpleNav's own "
            "Sun-direction output (see engine/fsw.py's docstring for why no separate sensor message "
            "is strictly required even though a coarse_sun_sensor is configured here for realism).\n\n"
            "What to look at: this is the shape a real small-sat's SpacecraftConfig looks like in "
            "practice -- compare it side-by-side with '06' to see exactly what real hardware adds "
            "(sensors/actuators/power blocks) on top of the bare pointing-mode concept.\n\n"
            "Try changing: the reaction wheels' Js/u_max/maxMomentum (see the GUI's sensor/actuator "
            "editor for the full per-kind parameter list and units), or swap fsw_mode to "
            "'locationPointing' with fsw_params={'target_ground_station': '<name>'} once a "
            "ground_stations entry exists in this scenario.\n\n"
            "Updated to include 10th-degree spherical-harmonics gravity, Sun/Moon third-body gravity, "
            "atmospheric drag, and solar radiation pressure -- consistent with this template's own "
            "role as the 'realistic counterpart' to '06'. Drag uses a nominal, SYNTHETIC "
            "(solar-cycle-shaped, not a real forecast) space-weather profile, generated entirely "
            "locally, no network access needed (see engine/spaceweather.py's own 'Closed-off/offline "
            "policy' docstring -- see template 04's own description for how to restore a real "
            "historical-data CONSERVATIVE margin via a self-supplied local CelesTrak CSV)."
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
        space_weather=_conservative_drag_margin(),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6928.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=50.0,
                enable_drag=True, drag_coeff=2.2, drag_area_m2=1.0,
                enable_srp=True, srp_coeff=1.3, srp_area_m2=1.0,
                inertia_kg_m2=list(_INERTIA_SMALL),
                sigma_bn_init=[0.1, 0.2, -0.15],
                omega_bn_b_init_rad_s=[0.001, -0.001, 0.0005],
                sensors=[
                    SensorConfig(kind="star_tracker", name="st-1", params={"noise_arcsec": 5.0}),
                    SensorConfig(kind="imu", name="imu-1", params={"gyro_noise_rad_s": 1e-5}),
                    SensorConfig(kind="coarse_sun_sensor", name="css-1", params={"nHat_B": [1.0, 0.0, 0.0]}),
                ],
                actuators=[
                    ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                    params={"gsHat_B": [1.0, 0.0, 0.0], "rw_type": "Honeywell_HR16",
                                            "maxMomentum": 100.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-2",
                                    params={"gsHat_B": [0.0, 1.0, 0.0], "rw_type": "Honeywell_HR16",
                                            "maxMomentum": 100.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-3",
                                    params={"gsHat_B": [0.0, 0.0, 1.0], "rw_type": "Honeywell_HR16",
                                            "maxMomentum": 100.0}),
                ],
                fsw_mode="sunSafePoint",
                # DEFAULT_MRP_GAINS (engine/fsw.py: K=3.5, P=30.0) is lifted
                # directly from Basilisk's own examples/BskSim reference
                # (BSK_Fsw.py's mrpFeedbackRWs), which is tuned for THAT
                # example's 900 kg*m^2 spacecraft (BSK_Dynamics.py's I_sc).
                # Applied unscaled to this template's 5 kg*m^2 _INERTIA_SMALL
                # hub, it is roughly 180x too stiff for this inertia and
                # produces a persistent, non-decaying ~30-degree pointing
                # oscillation (confirmed directly against a real Basilisk
                # build: sigma_BN never settles, even from a dead-rest
                # initial rate, over a 1500s run) -- bounded by RW torque
                # saturation rather than NaN, but not a real "pointed and
                # holding" safe mode. Scaled by this template's inertia
                # relative to that reference (K,P both x (5/900)) converges
                # cleanly instead (confirmed: sub-1e-6-degree final pointing
                # error over the same run). See HISTORY.md for the full
                # investigation -- this gain/inertia mismatch is a general
                # risk for ANY small-sat-scale spacecraft left on
                # DEFAULT_MRP_GAINS, not specific to this template.
                control_params={"K": 0.0194, "P": 0.167},
                power=PowerConfig(panel_area_m2=0.3, panel_efficiency=0.28, battery_capacity_wh=80.0),
            ),
        ],
    )


def build_08_mission_sequence_orbit_raise() -> Scenario:
    from spacemissionstudio.schema.command import Command

    return Scenario(
        name="08 - Mission sequence: impulsive orbit raise",
        description=(
            "Introduces the Mission Sequence layer (Resources/Mission Sequence/Output -- see this "
            "project's HISTORY.md, 'What Phase 6 (Mission Sequence architecture) adds'): rather than one "
            "single propagate-to-duration run, this scenario is a time-ordered list of commands, "
            "editable as a tree in the GUI's 'Mission sequence' panel: coast, snapshot the orbit "
            "state, apply a single prograde impulsive delta-V, coast again, snapshot again. The "
            "maneuver command applies delta_v_m_s in the 'vnb' frame (velocity/normal/binormal -- "
            "'inertial' applies it directly in the N frame instead, useful when you already know the "
            "exact inertial-frame vector you want), so [50, 0, 0] here means '+50 m/s prograde', the "
            "simplest kind of orbit-raising burn.\n\n"
            "What to look at: run it and check the 'Mission Output' tab (or, from the CLI, "
            "command_summary.csv) -- the two 'report' commands snapshot sat-1.position_N/velocity_N "
            "before and after the burn. A prograde burn on a circular orbit raises the OPPOSITE side "
            "of the orbit into an ellipse -- the orbit is no longer circular after the burn, with a "
            "higher apoapsis where the spacecraft now moves slower and a periapsis back at the "
            "original altitude.\n\n"
            "Try changing: delta_v_m_s's magnitude (bigger burn = bigger apoapsis raise) or sign "
            "(negative = retrograde, LOWERS the opposite side of the orbit instead), or add a second "
            "maneuver command half an orbit later to circularize at the new higher altitude -- a "
            "genuine two-burn Hohmann transfer, built entirely from this project's own mission "
            "-sequence commands.\n\n"
            "Updated to include 10th-degree spherical-harmonics gravity, Sun/Moon third-body gravity, "
            "atmospheric drag, and solar radiation pressure -- physically relevant at 400 km, and this "
            "template's own lesson (the Mission Sequence command layer / maneuver mechanics) doesn't "
            "depend on a clean two-body baseline the way '01'/'09' deliberately do. Drag uses a "
            "nominal, SYNTHETIC (solar-cycle-shaped, not a real forecast) space-weather profile, "
            "generated entirely locally, no network access needed (see engine/spaceweather.py's own "
            "'Closed-off/offline policy' docstring -- see template 04's own description for how to "
            "restore a real historical-data CONSERVATIVE margin via a self-supplied local CelesTrak "
            "CSV)."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=1.0, dynamics_task_rate_s=10.0, integrator="rkf78"),
        space_weather=_conservative_drag_margin(),
        spacecraft=[
            SpacecraftConfig(
                name="sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6778.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=500.0,
                enable_drag=True, drag_coeff=2.2, drag_area_m2=1.0,
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
            "The same circular LEO orbit as '01', but run as a Monte Carlo batch of 20 cases instead "
            "of a single deterministic run: each case's dry_mass_kg is independently redrawn from a "
            "normal distribution (mean 500 kg, std deviation 25 kg -- a stand-in for, e.g., propellant "
            "-loading or manufacturing-tolerance uncertainty). This is the basic pattern behind real "
            "uncertainty-quantification questions: 'given that I don't know this spacecraft's exact "
            "mass to the kilogram, how much does that affect the outcome I care about?'\n\n"
            "What to look at: run via the GUI's 'Run Monte Carlo...' action (or "
            "'spacemissionstudio monte-carlo') and pick an archive directory -- each of the 20 runs is "
            "archived separately, so you can compare e.g. final position across cases to see how much "
            "(or how little) an 5% mass uncertainty actually perturbs the resulting orbit over a "
            "1-day propagation (physically: not much, for pure two-body motion -- mass doesn't affect "
            "trajectory at all, only propellant-consuming maneuvers/drag/SRP would show sensitivity; "
            "try enabling one of those, or add an 'attitude_sigma_bn' dispersion, to see a case where "
            "it does matter).\n\n"
            "Try changing: num_runs (more runs = a smoother distribution of outcomes, at proportional "
            "runtime cost), std_deviation (a wider spread), or add a second DispersionConfig with "
            "quantity='attitude_sigma_bn'/kind='uniform_euler_mrp' for an initial-attitude dispersion "
            "instead (needs simulation_mode='full_attitude')."
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
                dry_mass_kg=500.0,
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
            "A spacecraft with NO attitude control (fsw_mode is None) and an elongated, non-spherical "
            "inertia tensor (Ixx=Iyy=12.5, Izz=7.5 kg*m^2) with SpacecraftConfig.enable_gravity_gradient "
            "set -- Basilisk's real GravityGradientEffector, the torque the central body's own gravity "
            "exerts across a spacecraft's non-uniform mass distribution. With zero initial body rate "
            "and no other torque source, a spacecraft normally stays frozen at its initial attitude for "
            "the entire run (see '06'/'07' for what active control looks like); this one does NOT, "
            "because gravity gradient torque is real physics, not a bug.\n\n"
            "What to look at: this is a Basilisk-truth-level effect, not exposed as a named result "
            "series when fsw_mode is None (see engine.service.SimulationService.run()'s own docstring) "
            "-- the clearest way to see it is tests/test_gravity_gradient.py's own technique (reading "
            "scStateOutMsg.sigma_BN directly), or simply watching the spacecraft's attitude indicator "
            "drift in Vizard over the run instead of staying locked to its starting orientation. For a "
            "spherically-symmetric inertia (Ixx=Iyy=Izz), this torque is identically zero -- try setting "
            "all three equal and confirm it stays frozen again.\n\n"
            "Try changing: the inertia spread (more elongated = stronger torque), the orbit altitude "
            "(gravity gradient torque falls off as 1/r^3 -- much stronger effect in a very low orbit "
            "than at GEO), or enable fsw_mode='inertial3D' with reaction wheels (see '07') to see an "
            "active controller simply reject this as one more disturbance torque."
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
                dry_mass_kg=500.0,
                inertia_kg_m2=list(_INERTIA_MEDIUM),
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
            "The thruster counterpart to '06'/'07': instead of reaction wheels or an idealized "
            "actuator, this spacecraft points itself using eight real ACS thrusters (an 8-thruster "
            "corner-mounted cube layout, the same real configuration "
            "examples/scenarioAttitudeFeedback2T_TH.py/scenarioMomentumDumping.py ship) via Basilisk's "
            "real thrForceMapping -> thrFiringSchmitt -> thrusterDynamicEffector chain (see "
            "engine.fsw.build_thrusters/build_thruster_force_mapping). fsw_mode 'inertial3D' commands a "
            "fixed inertial attitude; the spacecraft starts tipped away from it with a small initial "
            "body rate.\n\n"
            "What to look at: result series '{sat-1}.thruster_on_time' (one column per thruster, "
            "seconds) shows which thrusters fired and for how long as the controller worked to null "
            "the attitude error -- compare against '07''s '{sat-1}.rw_speeds' to see the equivalent "
            "signal for the reaction-wheel case. In Vizard, thruster plumes render natively "
            "(engine.vizard.enable_vizard's thr_effectors_by_spacecraft) when a thruster is firing.\n\n"
            "Try changing: each actuator's MaxThrust (weaker thrusters take longer to null the same "
            "attitude error), or the thruster layout itself (fewer than 6 well-placed thrusters cannot "
            "produce a pure torque about all three axes -- thrForceMapping will report a degraded/"
            "saturated solution)."
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
                dry_mass_kg=100.0,
                inertia_kg_m2=[10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0],
                sigma_bn_init=[0.3, 0.2, -0.1],
                omega_bn_b_init_rad_s=[0.0, 0.0, 0.0],
                fsw_mode="inertial3D",
                fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
                actuators=[
                    ActuatorConfig(kind="thruster", name=f"thr-{i + 1}",
                                     params={"r_B": pos, "tHat_B": direction, "MaxThrust": 1.0})
                    for i, (pos, direction) in enumerate(zip(
                        [[-1, -1, 1.28], [1, -1, -1.28], [1, -1, 1.28], [1, 1, -1.28],
                         [1, 1, 1.28], [-1, 1, -1.28], [-1, 1, 1.28], [-1, -1, -1.28]],
                        [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                         [-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0]],
                    ))
                ],
            ),
        ],
    )


def build_12_reaction_wheel_momentum_dumping() -> Scenario:
    return Scenario(
        name="12 - Reaction wheel momentum dumping",
        description=(
            "A spacecraft under normal reaction-wheel attitude control (fsw_mode 'inertial3D', same "
            "control chain as '07') whose four wheels start out already heavily spun up (the same "
            "pre-saturated Omega values as examples/scenarioMomentumDumping.py) -- MomentumDumpingConfig "
            "(hs_max=80 N*m*s) fires an 8-thruster desaturation cluster via thrMomentumManagement -> "
            "thrForceMapping -> thrMomentumDumping (engine.fsw.build_momentum_dumping) to bleed the "
            "excess momentum off, while the SAME reaction wheels stay in control of attitude the whole "
            "time -- the thrusters here never do attitude control, only desaturation. "
            "engine.service.SimulationService.build() automatically primes one dynamics tick and "
            "re-Resets the desaturation module before the real run starts, a real Basilisk requirement "
            "confirmed against this checkout's own build (see engine.fsw.build_momentum_dumping's "
            "docstring) -- nothing about that is visible here, it just works.\n\n"
            "What to look at: result series '{sat-1}.rw_speeds' should show all four wheel speeds "
            "dropping in sharp steps (each step is one desaturation firing) rather than staying flat or "
            "climbing; '{sat-1}.thruster_on_time' shows exactly when the desaturation thrusters fired.\n\n"
            "Try changing: momentum_dumping.hs_max (a lower threshold triggers desaturation sooner/more "
            "often), the wheels' initial Omega (closer to maxMomentum = desaturates almost immediately), "
            "or remove momentum_dumping entirely to see the wheel speeds never decrease on their own."
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
                dry_mass_kg=2500.0,
                inertia_kg_m2=[1700.0, 0.0, 0.0, 0.0, 1700.0, 0.0, 0.0, 0.0, 1800.0],
                sigma_bn_init=[0.0, 0.0, 0.0],
                omega_bn_b_init_rad_s=[0.0, 0.0, 0.0],
                fsw_mode="inertial3D",
                fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
                actuators=[
                    ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                     params={"gsHat_B": [0.7071, 0.0, 0.7071], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0, "Omega": 4000.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-2",
                                     params={"gsHat_B": [0.0, 0.7071, 0.7071], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0, "Omega": 2000.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-3",
                                     params={"gsHat_B": [-0.7071, 0.0, 0.7071], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0, "Omega": 3500.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-4",
                                     params={"gsHat_B": [0.0, -0.7071, 0.7071], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0, "Omega": 0.0}),
                    *[
                        ActuatorConfig(kind="thruster", name=f"desat-{i + 1}",
                                         params={"r_B": pos, "tHat_B": direction, "MaxThrust": 5.0,
                                                 "thruster_type": "MOOG_Monarc_5"})
                        for i, (pos, direction) in enumerate(zip(
                            [[-1, -1, 1.28], [1, -1, -1.28], [1, -1, 1.28], [1, 1, -1.28],
                             [1, 1, 1.28], [-1, 1, -1.28], [-1, 1, 1.28], [-1, -1, -1.28]],
                            [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                             [-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0]],
                        ))
                    ],
                ],
                momentum_dumping=MomentumDumpingConfig(hs_max=80.0, thr_min_fire_time=0.02, max_counter_value=100),
            ),
        ],
    )


def build_13_magnetic_torque_rod_momentum_management() -> Scenario:
    return Scenario(
        name="13 - Reaction wheel momentum management via magnetic torque rods",
        description=(
            "The alternative desaturation strategy to '12': instead of waiting for total momentum to "
            "cross a threshold and firing a discrete thruster burst, this spacecraft's four reaction "
            "wheels (same skewed-pyramid layout as examples/scenarioMtbMomentumManagement.py) are "
            "CONTINUOUSLY biased toward target speeds (800/600/400/200 RPM) the whole run, using four "
            "magnetic torque rods and the real geomagnetic field (Basilisk's WMM model) via "
            "MagneticMomentumManagementConfig (engine.fsw.build_mtb_desaturation: a dedicated "
            "magnetometer + tamComm feed mtbMomentumManagement, which sits BETWEEN rwMotorTorque and "
            "the RW hardware, modifying the commanded motor torque). No control-allocation conflict "
            "with the fsw_mode='inertial3D' attitude pointing running at the same time -- magnetic "
            "torque rods never do attitude control here, only this continuous momentum bias.\n\n"
            "What to look at: result series '{sat-1}.rw_speeds' should climb from zero and settle near "
            "800/600/400/200 RPM (converted: ~83.8/62.8/41.9/20.9 rad/s) over the ~2 hour run -- "
            "confirmed by direct experimentation against a real Basilisk build to converge to within "
            "about 0.5 RPM of each target. Compare the SHAPE of this convergence against '12''s sharp, "
            "discrete desaturation steps -- same underlying problem (reaction wheels accumulating "
            "momentum), two structurally different real Basilisk solutions.\n\n"
            "Try changing: wheel_speed_biases_rad_s (different target speeds per wheel), c_gain (a "
            "larger gain reacts faster but can overshoot/oscillate), or the orbit inclination (a "
            "near-equatorial orbit sees a weaker, less favorably-oriented geomagnetic field than a "
            "higher-inclination one, which can slow convergence noticeably)."
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
                dry_mass_kg=10.0,
                inertia_kg_m2=[0.02 / 3, 0.0, 0.0, 0.0, 0.1256 / 3, 0.0, 0.0, 0.0, 0.1256 / 3],
                sigma_bn_init=[0.1, 0.2, -0.3],
                omega_bn_b_init_rad_s=[0.001, -0.01, 0.03],
                fsw_mode="inertial3D",
                fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
                control_params={"K": 0.0001, "P": 0.002},
                actuators=[
                    *[
                        ActuatorConfig(kind="reaction_wheel", name=f"rw-{i + 1}",
                                         params={"gsHat_B": axis, "rw_type": "BCT_RWP015", "Omega_max": 5000.0})
                        for i, axis in enumerate(_MTB_DEMO_RW_AXES)
                    ],
                    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-1",
                                     params={"gtHat_B": [1.0, 0.0, 0.0], "max_dipole_a_m2": 0.1}),
                    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-2",
                                     params={"gtHat_B": [0.0, 1.0, 0.0], "max_dipole_a_m2": 0.1}),
                    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-3",
                                     params={"gtHat_B": [0.0, 0.0, 1.0], "max_dipole_a_m2": 0.1}),
                    ActuatorConfig(kind="magnetic_torque_rod", name="mtb-4",
                                     params={"gtHat_B": [0.70710678, 0.70710678, 0.0], "max_dipole_a_m2": 0.1}),
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
            "Real sun-direction ESTIMATION (not truth) feeding a closed attitude-control loop: eight "
            "coarse_sun_sensor devices in a cube layout (same directions as "
            "examples/BskSim/models/BSK_Dynamics.py's SetCSSConstellation()) feed a dedicated "
            "CSSConstellation + cssWlsEst weighted-least-squares estimator (engine.fsw."
            "build_css_sun_estimation), and fsw_params['use_css_estimation']=True routes that ESTIMATE "
            "(rather than simpleNav's truth) into fsw_mode 'sunSafePoint''s sunDirectionInMsg -- the "
            "same architecture as examples/BskSim/scenarios/scenario_AttEclipse.py's real reference "
            "(cssWlsEst -> sunSafePoint -> mrpFeedback -> reaction wheels).\n\n"
            "control_params is deliberately NOT left at engine.fsw.DEFAULT_MRP_GAINS (K=3.5/P=30): that "
            "default is lifted directly from Basilisk's own BSK_Fsw.py reference, tuned for THAT "
            "example's 900 kg*m^2 spacecraft. Applied unscaled to this template's 5 kg*m^2 hub it is "
            "roughly 180x too stiff -- confirmed directly against a real Basilisk build to produce a "
            "persistent, non-decaying ~30-degree pointing oscillation (bounded by RW torque saturation, "
            "not a crash, but never actually 'pointed and holding'). Scaling K and P by this hub's "
            "inertia relative to that reference (both x 5/900) converges cleanly instead -- confirmed: "
            "sub-1e-6-degree final pointing error. See HISTORY.md for the full investigation; this "
            "gain/inertia mismatch is a general risk for ANY small-sat-scale spacecraft left on "
            "DEFAULT_MRP_GAINS, worth checking on every new fsw_mode spacecraft this small, not "
            "something specific to CSS estimation.\n\n"
            "What to look at: '{sat-1}.sun_heading_body_estimated' (the CSS estimate) should settle near "
            "[0, 0, 1] in the body frame as sunSafePoint drives the commanded body +Z axis "
            "(sHatBdyCmd) onto the real sun direction -- compare its early, still-converging samples "
            "against its settled final value to see the estimate itself stabilize as the attitude "
            "stops moving. The WLS estimate's accuracy is purely geometry-dependent (how many of the "
            "8 sensors are actually sunlit for the current sun direction, confirmed directly against a "
            "real Basilisk build: an under-determined 2-of-8-illuminated case gave 14.5 degrees of "
            "error, a well-conditioned 4-of-8 case gave an exact 0.0-degree match with zero sensor "
            "noise) -- real hardware has exactly this coverage gap, it is not something to 'fix' here.\n\n"
            "Try changing: the coarse_sun_sensor fov_deg values (a narrower FOV sees fewer sensors "
            "illuminated at once, degrading the WLS conditioning), or fsw_params['use_css_estimation'] "
            "to False to compare against simpleNav's noise-free truth sun direction instead."
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
                dry_mass_kg=50.0,
                inertia_kg_m2=list(_INERTIA_SMALL),
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
                                     params={"gsHat_B": [1.0, 0.0, 0.0], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-2",
                                     params={"gsHat_B": [0.0, 1.0, 0.0], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-3",
                                     params={"gsHat_B": [0.0, 0.0, 1.0], "rw_type": "Honeywell_HR16",
                                             "maxMomentum": 100.0}),
                ],
                fsw_mode="sunSafePoint",
                fsw_params={"sHatBdyCmd": [0.0, 0.0, 1.0], "use_css_estimation": True},
                control_params={"K": 0.0194, "P": 0.167},
            ),
        ],
    )


def build_15_celestial_body_pointing() -> Scenario:
    return Scenario(
        name="15 - Direct celestial-body pointing (locationPointing + target_body)",
        description=(
            "fsw_mode 'locationPointing' has TWO target options: '07'-style pointing at a ground "
            "station (fsw_params['target_ground_station']), or pointing straight at a celestial body "
            "(fsw_params['target_body']) -- this template is the second one. A body-fixed axis "
            "(pHat_B, here the spacecraft +Z) stays pointed at the Moon throughout the orbit, built via "
            "engine.fsw.build_ephemeris_converter() (SpicePlanetStateMsg -> EphemerisMsg -> "
            "locationPointing.celBodyInMsg), the same converter + guidance pairing as Basilisk's own "
            "examples/scenarioAsteroidArrival.py (there pointing an antenna at Earth and a camera at an "
            "asteroid; here, at the Moon). target_body must name gravity.central_body or one of "
            "gravity.third_body_perturbers -- 'moon' is SPICE-tracked here for exactly that reason.\n\n"
            "What to look at: there is no separate result series for the body-to-target pointing error "
            "yet (add a 'report' mission_sequence command on sat-1.attitude_sigma_bn, see '08', or watch "
            "Vizard's live attitude indicator) -- but unlike '06'/'07's hillPoint/sunSafePoint, the "
            "target direction here keeps changing as the Moon moves along its own orbit while the "
            "spacecraft moves along its much faster one, so the commanded attitude is never constant.\n\n"
            "Try changing: target_body to 'sun' (already SPICE-tracked here too) to compare a much "
            "farther, slower-moving target's pointing behavior against the Moon's; or pHat_B to a "
            "different body axis to re-point a different physical location on the spacecraft (e.g. a "
            "antenna mounted off the +Z face) at the same target."
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
                dry_mass_kg=300.0,
                inertia_kg_m2=list(_INERTIA_MEDIUM),
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
    time_of_flight_s = 2490.0

    return Scenario(
        name="16 - Lambert transfer: solving for a point-to-point delta-V",
        description=(
            "A new Mission Sequence command kind: 'lambert_transfer' solves for whatever impulsive "
            "delta-V takes the spacecraft from its CURRENT state to target_position_m after "
            "time_of_flight_s, via Basilisk's own lambertPlanner -> lambertSolver -> lambertValidator "
            "chain (engine.mission_engine.MissionEngine._run_lambert_transfer), then applies it "
            "immediately -- unlike '08's 'maneuver' command, you specify WHERE you want to end up, not "
            "the delta-V itself. Same underlying 3 Basilisk modules, same validation/reporting "
            "philosophy as Basilisk's own examples/scenarioLambertSolver.py.\n\n"
            "This exact configuration (orbit, target_position_m, time_of_flight_s) was confirmed "
            "directly against a real Basilisk build to land within floating-point noise (sub-millimeter) "
            "of target_position_m when the resulting delta-V is propagated forward by time_of_flight_s -- "
            "not a hand-picked-to-look-plausible example.\n\n"
            "What to look at: the 'Mission Output' tab's two 'report' commands snapshot "
            "sat-1.position_N before and after the transfer -- after propagating for time_of_flight_s, "
            "the 'after' position should sit almost exactly at target_position_m "
            f"([{-(r_earth_m + 200.0e3):.0f}, 0, 0] m here).\n\n"
            "Try changing: target_position_m (any reachable point works, not just ones near the current "
            "orbit), time_of_flight_s (very short times need very large, often rejected, delta-Vs -- try "
            "making it unreasonably small to see lambert_transfer raise a clear "
            "'lambertValidator reported' error instead of silently doing nothing), or "
            "min_orbit_radius_m (set it to the central body's own radius to reject any transfer "
            "trajectory that would dip through the surface)."
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
            ),
        ],
        mission_sequence=[
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
            "The exact same 8-thruster attitude control setup as '11' (inertial3D pointing, the real "
            "thrForceMapping -> thrFiringSchmitt -> thrusterDynamicEffector chain), with a real "
            "FuelTankConfig added -- Basilisk's own fuelTank state effector (engine.fsw.build_fuel_tank, "
            "confirmed against examples/MultiSatBskSim/modelsMultiSat/BSK_MultiSatDynamics.py's own "
            "SetFuelTank()) now tracks REAL propellant depletion as the thrusters fire, reading the same "
            "mass-flow rate (mDot = F / (steadyIsp * g0)) each thruster already computes for its own "
            "physics -- unlike this app's older station-keeping/phasing/constant-thrust propellant "
            "bookkeeping (engine.orbit_maintenance, a hand-rolled Python estimate), this is Basilisk's "
            "own state effector doing the real physics, including the resulting center-of-mass shift as "
            "propellant depletes.\n\n"
            "This exact configuration was confirmed directly against a real Basilisk build: the "
            "spacecraft's attitude error converges from its initial tip (sigma norm ~0.37) to near-zero "
            "(~0.002) within about 100-150 seconds, consuming roughly 0.185 kg of the tank's 0.5 kg "
            "starting load during that active correction burn -- then '{sat-1}.fuel_mass_remaining' goes "
            "flat once the attitude has converged and the thrusters stop firing, a clean before "
            "/during/after depletion curve.\n\n"
            "What to look at: result series '{sat-1}.fuel_mass_remaining' alongside '{sat-1}"
            ".thruster_on_time' -- the fuel-depletion curve's steep drop should line up exactly with the "
            "period where thrusters are actively firing, then both go flat together.\n\n"
            "Try changing: fuel_tank.propellant_mass_kg (set it below the ~0.185 kg this convergence "
            "burn needs to see what happens when the tank runs dry mid-maneuver -- thrusterDynamicEffector "
            "keeps commanding thrust, but fuelTank has nothing left to give), or each thruster's "
            "steadyIsp (a lower Isp burns through the same delta-V budget using more propellant, a "
            "higher Isp less)."
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
                dry_mass_kg=100.0,
                inertia_kg_m2=[10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0],
                sigma_bn_init=[0.3, 0.2, -0.1],
                omega_bn_b_init_rad_s=[0.0, 0.0, 0.0],
                fsw_mode="inertial3D",
                fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
                actuators=[
                    ActuatorConfig(kind="thruster", name=f"thr-{i + 1}",
                                     params={"r_B": pos, "tHat_B": direction, "MaxThrust": 1.0})
                    for i, (pos, direction) in enumerate(zip(
                        [[-1, -1, 1.28], [1, -1, -1.28], [1, -1, 1.28], [1, 1, -1.28],
                         [1, 1, 1.28], [-1, 1, -1.28], [-1, 1, 1.28], [-1, -1, -1.28]],
                        [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                         [-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0]],
                    ))
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
            "The direct LEO counterpart to '03' (GEO station-keeping): a 400 km small satellite "
            "actively maintaining its altitude against atmospheric drag -- the actual dominant driver "
            "of LEO altitude decay, the same way Sun/Moon/SRP drive GEO drift in '03' -- using the "
            "exact same station_keeping deadband thrust controller. Unlike GEO's typically-infrequent "
            "corrections, LEO drag is continuous and altitude-dependent (denser air lower down means "
            "faster decay), so this spacecraft needs noticeably more frequent, smaller corrections.\n\n"
            "What to look at: same as '03' -- run the CLI and check command_summary/results for "
            "propellant used over the 14-day run, and compare the number/frequency of burns against "
            "'03's GEO case in the station-keeping summary (README, 'Running the CLI'). The contrast "
            "is the lesson: GEO drift is slow and the deadband is wide (5 km) because the perturbing "
            "forces are weak and roughly constant; LEO drag is faster and the deadband here is tight "
            "(1 km) because a satellite this low can lose multiple km of altitude in days, not years.\n\n"
            "Try changing: the orbit's semi_major_axis_km (lower = thicker atmosphere = much faster "
            "decay = more frequent burns -- try 350 km or 300 km to see the effect accelerate "
            "sharply), drag_area_m2/drag_coeff (a satellite with more cross-sectional area per unit "
            "mass decays faster), or deadband_km (tighter means more frequent, smaller corrections, "
            "the same trade '03' suggests for GEO).\n\n"
            "enable_srp is deliberately OFF here (unlike '04'/'05', which enable it alongside drag): "
            "the point of this template, like '03's point about GEO, is to isolate the ONE dominant "
            "perturbation (drag) rather than mix in a secondary effect SRP is at this altitude. Uses "
            "the same nominal, SYNTHETIC (solar-cycle-shaped, not a real forecast) nrlmsise00 "
            "space-weather profile as '04'/'05'/'07'/'08' -- generated entirely locally, no network "
            "access needed (see engine/spaceweather.py's own 'Closed-off/offline policy' docstring; "
            "see template 04's own description for how to restore a real historical-data "
            "CONSERVATIVE margin via a self-supplied local CelesTrak CSV). NOTE: like '05', this "
            "template's exact "
            "decay rate under the real nrlmsise00 model has NOT been re-verified against a real "
            "multi-day Basilisk run in this development sandbox (no route to the NAIF SPICE kernel "
            "host or CelesTrak here) -- the station_keeping/drag parameters were instead tuned and "
            "confirmed against a bypass-SPICE build using a realistically-reparameterized simple "
            "exponential atmosphere model (2-3 real reboost burns over 14 days, well under budget); "
            "please report back if the real nrlmsise00 propellant budget looks off."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=14.0, dynamics_task_rate_s=30.0, integrator="rkf78"),
        space_weather=_conservative_drag_margin(),
        spacecraft=[
            SpacecraftConfig(
                name="leo-sat-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6778.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=120.0,
                enable_drag=True, drag_coeff=2.2, drag_area_m2=1.5,
                station_keeping=StationKeepingConfig(
                    target_altitude_km=400.0, deadband_km=1.0, thrust_n=0.05, isp_s=1500.0,
                    propellant_kg=2.0,
                ),
            ),
        ],
    )


def build_19_sun_pointing_comms_link() -> Scenario:
    # Verification note (see this function's own user-facing description
    # below for the short version): this sandbox has no Basilisk build, so
    # nothing here could be run end-to-end. The ONE piece of numeric tuning
    # this template reuses -- idealized-torque mrpFeedback control on
    # _INERTIA_MEDIUM at dynamics_task_rate_s=0.1s with DEFAULT_MRP_GAINS --
    # is the EXACT combination '06' already confirmed stable against a real
    # Basilisk build (see build_06_attitude_pointing_basic()'s own comment);
    # comms_pointing only supports idealized actuation (see
    # engine.service's own scope note at the comms_pointing branch), so no
    # actuators are configured here, matching that constraint. What is NOT
    # independently re-confirmed here: that this same combo stays stable
    # through MUCH LARGER-angle slews (Sun-pointing <-> ground-station
    # -pointing can be up to a ~180-degree reorientation, not '06's small
    # initial offset) over a much longer, 12-hour run. MRP feedback's own
    # commanded-torque term is naturally bounded regardless of angle size
    # (sigma_BR's magnitude never exceeds 1, with the shadow-set switch
    # keeping it there), which is why this risk is believed low -- but
    # please report back if a real run shows otherwise.
    #
    # Ground-station pass geometry: sun_synchronous_inclination_deg(6928.0)
    # (see that function's own derivation/verification comment) is
    # near-polar and covers every longitude under the station's latitude
    # band within about one nodal period regardless of the exact RAAN
    # chosen, so this doesn't depend on fine-tuning raan_deg/true_anomaly_deg
    # against a specific station longitude the way, say, a GEO
    # station-keeping template would -- but the exact NUMBER and duration of
    # passes over half a day couldn't be independently re-confirmed against
    # a real Basilisk run here either. If a run shows zero access windows,
    # the most likely fix is sim_settings.duration_days (try 1.0 instead of
    # 0.5) rather than the orbit geometry itself.
    return Scenario(
        name="19 - Sun-pointing spacecraft with automatic ground-station comms link",
        description=(
            "An integrated small-satellite mission: 'leo-comms-1' normally points its solar panel "
            "normal at the real, live Sun (fsw_mode-equivalent 'sunSafePoint' behavior, continuously "
            "tracking the actual Sun direction, never a fixed inertial attitude) to maximize power "
            "generation. Whenever this spacecraft comes into REAL, geometry-driven access of the "
            "'berlin-gs' ground station (Basilisk's own groundLocation.GroundLocation elevation-mask "
            "access analysis -- never a manually-specified time window), comms_pointing "
            "(schema.scenario.CommsPointingConfig) automatically takes over and re-points the "
            "spacecraft's antenna boresight at the ground station instead, switching back to "
            "Sun-pointing the instant access ends. This is schema_version's newest capability: see "
            "engine.fsw.build_comms_pointing()'s docstring for how the switch works -- only the "
            "attitude REFERENCE changes; the spacecraft's own integrated attitude state is never reset, "
            "so the existing closed-loop mrpFeedback controller physically SLEWS between the two "
            "targets across every transition (watch sat.attitude_sigma_BN step continuously across an "
            "access-start/access-end boundary -- never jump) rather than snapping instantly.\n\n"
            "Power (schema.scenario.PowerConfig) and an RF downlink (schema.scenario.RFLinkConfig, "
            "with a beamwidth-dependent antenna-pointing-loss term) respond to this real, simulated "
            "behavior, not independent canned numbers: solar generation depends on the spacecraft's "
            "actual attitude (panel-to-sun angle) and real eclipse state every tick; the comms "
            "transmitter's extra comms_power_w draws from the SAME battery only while ground-station "
            "-pointing is actually active; and the downlink's link margin (engine.link_budget) is "
            "computed from the REAL simulated slant range AND the spacecraft's own actually-achieved "
            "antenna pointing error -- not an assumption of perfect boresight. Crucially, the link "
            "margin series is gated on BOTH real geometric access (gs.access_to_sat.has_access) AND "
            "the spacecraft having actually switched into ground-station-pointing mode "
            "(sat.comms_pointing.active_mode) -- so a margin value only appears once there's an "
            "actual attempted link, and during the slew right after a pass begins, the still-large "
            "antenna pointing error can legitimately show a DEGRADED or even negative margin even "
            "though hasAccess is already true: this is the 'geometric visibility vs actual RF link "
            "availability' distinction made concrete, not just asserted.\n\n"
            "What to look at: after running, find one access window in "
            "'berlin-gs.access_to_leo-comms-1.has_access' and, across that SAME window, cross-plot: "
            "'leo-comms-1.comms_pointing.active_mode' (0 -> 1 at access start, back to 0 at access "
            "end), 'leo-comms-1.comms_pointing.pointing_error_deg' (large right at the transition, "
            "decaying toward ~0 as the slew converges), 'leo-comms-1.power.battery_soc' (dips a bit "
            "faster while comms_power_w is drawing, recovers once Sun-pointing resumes and the panel "
            "is well-illuminated), and 'berlin-gs.access_to_leo-comms-1.link_margin_db' (should be "
            "poor/undefined right at the transition, then settle to a healthy positive margin once "
            "pointing converges, and should also visibly worsen as elevation drops toward the pass's "
            "edges -- real free-space-path-loss growing with slant range). Compare against a window "
            "with NO access at all, where active_mode should stay continuously 0 and link_margin_db "
            "should be entirely NaN (no link attempted).\n\n"
            "Try changing: berlin-gs's min_elevation_deg (lower = longer, more frequent but lower "
            "-quality passes), rf_link.antenna_beamwidth_deg (narrower = pointing error matters MORE, "
            "a bigger dip in margin during each transition's slew), comms_pointing.comms_power_w "
            "(higher = a more visible battery drain during each pass), or sim_settings.duration_days "
            "(longer = more passes, at the cost of a bigger recorded dataset -- see the generator "
            "script's own comment on why this template doesn't go beyond 0.5 days by default).\n\n"
            "Known, deliberately-not-used upgrade path: Basilisk's own source tree has a more "
            "physically-complete, compiled antenna + link-budget pair "
            "(src/simulation/communication/simpleAntenna, .../linkBudget -- a real 2D-Gaussian-beam "
            "antenna pattern computing pointing loss from true 3D spacecraft/ground antenna geometry, "
            "plus FSPL and ITU-R P.676 atmospheric attenuation). This template deliberately does NOT "
            "use it: no example scenario anywhere in this checkout exercises those modules yet, so "
            "there's no reference usage to confirm the wiring against -- unlike every other module "
            "this project uses. This template's simplified, already-proven, Basilisk-free "
            "engine.link_budget.py is used instead (now extended with its own, textbook parabolic "
            "-pattern pointing-loss approximation, not the real antenna geometry). A real future "
            "upgrade would swap this template's RFLinkConfig/link_budget wiring for those native "
            "modules once a reference example exists to validate the integration against."
        ),
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=0.5, dynamics_task_rate_s=0.1, integrator="rkf78"),
        ground_stations=[
            _berlin_ground_station(rx_antenna_gain_dbi=35.0, system_noise_temp_k=150.0),
        ],
        spacecraft=[
            SpacecraftConfig(
                name="leo-comms-1",
                orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                               inclination_deg=sun_synchronous_inclination_deg(6928.0),
                               raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
                dry_mass_kg=60.0,
                inertia_kg_m2=list(_INERTIA_MEDIUM),
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
    # end-to-end in this environment. sunSafePoint + idealized-ish hardware
    # control reuses the EXACT control_params/_INERTIA_SMALL combination
    # '07'/'15' already confirmed stable against a real Basilisk build
    # (see build_07_attitude_pointing_with_adcs_hardware()'s own comment);
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
            "Adds Basilisk's real thermal modules on top of '07's own ADCS hardware suite: a "
            "'thermal' sensor (sensorThermal.SensorThermal) models the temperature of an externally "
            "-mounted component (e.g. a star-tracker baffle or avionics panel) as it heats under "
            "direct sunlight and cools in Earth's shadow -- real radiative absorption/emission plus "
            "an internal power-to-heat draw, not an analytical estimate; its own optional "
            "measurement_* params add noise/bias/fault on top, same device-interface-realism shape "
            "as every other sensor kind (see schema.scenario's own SUPPORTED_SENSOR_KINDS comment). "
            "Separately, 'rw-1' also carries an OPTIONAL motor-thermal model "
            "(motorThermal.MotorThermal, the motor_thermal_* params) -- a reaction wheel generates "
            "real heat from motor inefficiency and friction, independent of whether any 'thermal' "
            "sensor is configured at all; 'rw-2'/'rw-3' deliberately have none set, showing this is "
            "per-wheel opt-in, not an all-or-nothing spacecraft setting.\n\n"
            "What to look at: 'sat-1.sensor.therm-1.temperature' should visibly rise while the orbit "
            "is in sunlight and fall across each eclipse pass (compare its timing against this "
            "spacecraft's own eclipse windows, inferred from where power.battery_soc stops "
            "recharging) -- a handful of full orbits are simulated specifically so more than one "
            "heating/cooling cycle is visible. 'sat-1.actuator.rw-1.motor_temperature' separately "
            "drifts toward motor_thermal_ambient_temp_c as the wheel spins (friction/inefficiency "
            "heat vs. ambient dissipation), decoupled from the sensor's own sun-driven cycle.\n\n"
            "Try changing: therm-1's nHat_B (a face pointed away from the Sun-pointing axis sees a "
            "very different, possibly inverted, heating pattern -- see sunSafePoint's own "
            "sHatBdyCmd below for which body axis is actually Sun-pointed), area_m2/absorptivity/"
            "emissivity/mass_kg/specific_heat_j_kg_k (a larger mass_kg*specific_heat_j_kg_k heat "
            "capacity makes the whole temperature curve respond more slowly/smoothly to each "
            "sunlight/eclipse transition), or rw-1's motor_thermal_efficiency (closer to 1.0 means "
            "less waste heat, a flatter motor-temperature curve -- note 1.0 itself is rejected, see "
            "that field's own validation message).\n\n"
            "Known, deliberately-not-used real Basilisk capability: engine.fsw.attach_sensors's own "
            "'thermal' kind does not yet expose sensorThermal's sensorStatusInMsg (a DeviceStatusMsg "
            "that can turn sensorPowerDraw on/off at run time, e.g. tied to a duty cycle) -- this "
            "template's power_draw_w is a constant, always-on draw instead. A real future upgrade "
            "would wire a DeviceStatusMsg source (this app has none today) to that input."
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
                dry_mass_kg=50.0,
                inertia_kg_m2=list(_INERTIA_SMALL),
                sigma_bn_init=[0.1, 0.2, -0.15],
                omega_bn_b_init_rad_s=[0.001, -0.001, 0.0005],
                sensors=[
                    SensorConfig(kind="star_tracker", name="st-1", params={"noise_arcsec": 5.0}),
                    SensorConfig(kind="imu", name="imu-1", params={"gyro_noise_rad_s": 1e-5}),
                    SensorConfig(kind="coarse_sun_sensor", name="css-1", params={"nHat_B": [1.0, 0.0, 0.0]}),
                    # A small (0.05 m^2), externally-mounted panel sharing
                    # the CSS's own sun-facing normal, so it genuinely
                    # tracks this spacecraft's real sunlight/eclipse cycle
                    # rather than always reading near-zero projected area.
                    SensorConfig(kind="thermal", name="therm-1", params={
                        "nHat_B": [1.0, 0.0, 0.0], "area_m2": 0.05, "absorptivity": 0.25, "emissivity": 0.34,
                        "mass_kg": 0.3, "specific_heat_j_kg_k": 890.0, "initial_temp_c": 0.0,
                        "power_draw_w": 0.5, "measurement_noise_std_c": 0.2,
                    }),
                ],
                actuators=[
                    ActuatorConfig(kind="reaction_wheel", name="rw-1",
                                    params={"gsHat_B": [1.0, 0.0, 0.0], "rw_type": "Honeywell_HR16",
                                            "maxMomentum": 100.0,
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
                                    params={"gsHat_B": [0.0, 1.0, 0.0], "rw_type": "Honeywell_HR16",
                                            "maxMomentum": 100.0}),
                    ActuatorConfig(kind="reaction_wheel", name="rw-3",
                                    params={"gsHat_B": [0.0, 0.0, 1.0], "rw_type": "Honeywell_HR16",
                                            "maxMomentum": 100.0}),
                ],
                fsw_mode="sunSafePoint",
                # Same inertia-scaled gains as '07'/'15' (_INERTIA_SMALL,
                # 5 kg*m^2) -- see build_07_attitude_pointing_with_adcs_hardware()'s
                # own comment for the real-Basilisk-confirmed derivation.
                control_params={"K": 0.0194, "P": 0.167},
                power=PowerConfig(panel_area_m2=0.3, panel_efficiency=0.28, battery_capacity_wh=80.0),
            ),
        ],
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


if __name__ == "__main__":
    main()
