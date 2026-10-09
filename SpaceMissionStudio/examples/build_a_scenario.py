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

"""Build a scenario in Python, check it, and save it -- no Basilisk needed.

Everything the GUI's Scenario Editor edits is a plain dataclass in
``spacemissionstudio.schema.scenario``: a ``Scenario`` holds the
environment (gravity, space weather, run settings), its spacecraft (each
with an orbit, mass properties and optional hardware) and its ground
stations. ``Scenario.validate()`` gives the same plain-language errors as
the editor's validation line, and ``save()`` writes the JSON file that
File > Open reads.

Run it from the SpaceMissionStudio folder::

    python3 examples/build_a_scenario.py my_first_mission.json

then open ``my_first_mission.json`` in the GUI, or run it with
``spacemissionstudio run my_first_mission.json --out-dir out``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from spacemissionstudio.engine.orbit_design import raan_for_ltan_deg, sun_synchronous_inclination_deg
from spacemissionstudio.engine.scenario_explainer import explain
from spacemissionstudio.schema.scenario import (
    GravityConfig,
    GroundStationConfig,
    OrbitIC,
    Scenario,
    ScenarioValidationError,
    SimSettings,
    SpacecraftConfig,
)

EARTH_RADIUS_KM = 6378.0  # [km] the round figure the bundled templates use
EPOCH_UTC = "2030-01-01T08:30:00"


def build_scenario(altitude_km: float = 550.0, duration_days: float = 1.0) -> Scenario:
    """One 150 kg satellite in a Sun-synchronous orbit (10:30 local time of
    the ascending node) at ``altitude_km`` [km], with drag, solar pressure
    and a ground station in Berlin: the shape of template 22."""
    semi_major_axis_km = EARTH_RADIUS_KM + altitude_km  # [km]
    satellite = SpacecraftConfig(
        name="my-sat",
        orbit=OrbitIC(
            type="classical_elements",
            semi_major_axis_km=semi_major_axis_km,
            eccentricity=0.0,
            # Sun-synchronous: the inclination at which Earth's oblateness
            # turns the orbit plane once a year, in step with the Sun.
            inclination_deg=sun_synchronous_inclination_deg(semi_major_axis_km),
            raan_deg=raan_for_ltan_deg(EPOCH_UTC, ltan_hour=10.5),
            arg_periapsis_deg=0.0,
            true_anomaly_deg=0.0,
        ),
        dry_mass_kg=150.0,  # [kg]
        inertia_kg_m2=[20.5, 0.0, 0.0, 0.0, 20.5, 0.0, 0.0, 0.0, 16.0],  # [kg*m^2] a 0.8 x 0.8 x 1.0 m box
        enable_drag=True,
        drag_coeff=3.0,  # [-] ESA AD10's value for operations
        drag_area_m2=0.8,  # [m^2]
        enable_srp=True,
        srp_coeff=1.3,  # [-]
        srp_area_m2=1.5,  # [m^2]
    )
    berlin = GroundStationConfig(name="berlin-gs", latitude_deg=52.52, longitude_deg=13.405,  # [deg]
                                 altitude_m=34.0, min_elevation_deg=10.0)  # [m], [deg]
    return Scenario(
        name="My first mission",
        description="Built with examples/build_a_scenario.py.",
        epoch_utc=EPOCH_UTC,
        simulation_mode="orbit_only",  # trajectories only; "full_attitude" adds pointing and hardware
        gravity=GravityConfig(central_body="earth", central_body_degree=10, third_body_perturbers=["sun", "moon"]),
        sim_settings=SimSettings(duration_days=duration_days, dynamics_task_rate_s=30.0),  # [day], [s]
        spacecraft=[satellite],
        ground_stations=[berlin],
        # space_weather keeps its default: the real solar and geomagnetic
        # data shipped with the app, driving the NRLMSISE-00 atmosphere.
    )


def describe(scenario: Scenario) -> list:
    """The Explain tab's summary of ``scenario``, as lines of text."""
    explanation = explain(scenario)
    lines = [explanation.headline]
    lines += [f"  {tile.label}: {tile.value}" for tile in explanation.stat_tiles]
    for section in explanation.sections:
        badges = ", ".join(badge.label for badge in section.badges)
        lines.append(f"  {section.title}: {badges}" if badges else f"  {section.title}")
        lines += [f"    {note}" for note in section.notes]
    return lines


def main(argv=None) -> Path:
    parser = argparse.ArgumentParser(description="Build, check and save a scenario (no Basilisk needed).")
    parser.add_argument("output", type=Path, nargs="?", default=Path("my_first_mission.json"),
                        help="where to write the scenario (default: my_first_mission.json)")
    parser.add_argument("--altitude-km", type=float, default=550.0, help="orbit altitude [km]")
    parser.add_argument("--days", type=float, default=1.0, help="how long to simulate [day]")
    args = parser.parse_args(argv)

    scenario = build_scenario(args.altitude_km, args.days)
    try:
        scenario.validate()
    except ScenarioValidationError as exc:  # e.g. --days 0
        parser.error(str(exc))
    scenario.save(args.output)
    print("\n".join(describe(scenario)))
    print(f"Saved {args.output}")
    return args.output


if __name__ == "__main__":
    main()
