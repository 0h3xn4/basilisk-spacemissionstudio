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

"""A Hohmann transfer written as a Mission Sequence (needs Basilisk).

Shows how the GUI's Mission Sequence editor works underneath: a list of
``Command`` objects run in order. Here: burn prograde, coast until
apoapsis (an event, not a fixed time), burn prograde again to
circularize, then coast one orbit. Each ``report`` command records a
snapshot, as on the Mission Output tab.

Gravity is a point mass, so the result can be checked against the
textbook formulas: the final orbit is circular at the target altitude to
within about 0.3 km (the second burn fires at the first 10 s step past
apoapsis, not exactly on it). ``--j2`` adds Earth's oblateness, which
makes the radius swing by about 10 km over each orbit.

Run it from the SpaceMissionStudio folder::

    python3 examples/hohmann_transfer.py --from-km 550 --to-km 700
"""

from __future__ import annotations

import argparse
import math

import numpy as np

from spacemissionstudio.schema.command import Command
from spacemissionstudio.schema.scenario import GravityConfig, OrbitIC, Scenario, SimSettings, SpacecraftConfig

MU_EARTH_M3_S2 = 3.986004415e14  # [m^3/s^2] Basilisk's Earth gravitational parameter
EARTH_RADIUS_KM = 6378.0  # [km] the round figure the bundled templates use


def hohmann(r1_m: float, r2_m: float):
    """The two prograde burns [m/s] and the coast between them [s] that
    move a circular orbit of radius ``r1_m`` to one of ``r2_m`` [m]."""
    transfer_sma_m = (r1_m + r2_m) / 2.0  # [m]
    dv1 = math.sqrt(MU_EARTH_M3_S2 / r1_m) * (math.sqrt(r2_m / transfer_sma_m) - 1.0)  # [m/s]
    dv2 = math.sqrt(MU_EARTH_M3_S2 / r2_m) * (1.0 - math.sqrt(r1_m / transfer_sma_m))  # [m/s]
    coast_s = math.pi * math.sqrt(transfer_sma_m ** 3 / MU_EARTH_M3_S2)  # [s] half the transfer orbit
    return dv1, dv2, coast_s


def build_scenario(from_km: float, to_km: float, j2: bool = False) -> Scenario:
    r1_m, r2_m = (EARTH_RADIUS_KM + from_km) * 1e3, (EARTH_RADIUS_KM + to_km) * 1e3  # [m]
    dv1, dv2, _coast_s = hohmann(r1_m, r2_m)
    final_period_days = 2.0 * math.pi * math.sqrt(r2_m ** 3 / MU_EARTH_M3_S2) / 86400.0  # [day]
    sat = "sat-1"
    return Scenario(
        name="Hohmann transfer",
        description="Built with examples/hohmann_transfer.py.",
        epoch_utc="2030-01-01T00:00:00",
        simulation_mode="orbit_only",
        gravity=GravityConfig(central_body="earth", central_body_degree=2 if j2 else 0),
        sim_settings=SimSettings(duration_days=1.0, dynamics_task_rate_s=10.0),  # [day], [s] (the sequence sets the length)
        spacecraft=[SpacecraftConfig(
            name=sat,
            orbit=OrbitIC(type="classical_elements", semi_major_axis_km=r1_m / 1e3, eccentricity=0.0,
                          inclination_deg=51.6, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),  # [deg]
            dry_mass_kg=150.0,  # [kg]
        )],
        mission_sequence=[
            # "vnb": x along the velocity, so [dv, 0, 0] is a prograde burn.
            Command(kind="maneuver", label="Burn 1: raise apoapsis",
                    params={"spacecraft": sat, "delta_v_m_s": [dv1, 0.0, 0.0], "frame": "vnb"}),
            Command(kind="propagate", label="Coast to apoapsis",
                    params={"stop_condition": "event", "event_kind": "apoapsis", "spacecraft": sat}),
            Command(kind="report", label="At apoapsis", params={"series": []}),
            Command(kind="maneuver", label="Burn 2: circularize",
                    params={"spacecraft": sat, "delta_v_m_s": [dv2, 0.0, 0.0], "frame": "vnb"}),
            Command(kind="propagate", label="One orbit on the new circle",
                    params={"stop_condition": "duration", "duration_days": final_period_days}),
            Command(kind="report", label="End", params={"series": []}),
        ],
    )


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description="A Hohmann transfer as a Mission Sequence.")
    parser.add_argument("--from-km", type=float, default=550.0, help="starting circular altitude [km]")
    parser.add_argument("--to-km", type=float, default=700.0, help="target circular altitude [km]")
    parser.add_argument("--j2", action="store_true", help="add Earth's oblateness (J2) to the gravity model")
    args = parser.parse_args(argv)

    from spacemissionstudio.engine.mission_engine import MissionEngine  # imports Basilisk
    from spacemissionstudio.engine.service import SimulationService

    scenario = build_scenario(args.from_km, args.to_km, args.j2)
    scenario.validate()
    r1_m, r2_m = (EARTH_RADIUS_KM + args.from_km) * 1e3, (EARTH_RADIUS_KM + args.to_km) * 1e3  # [m]
    dv1, dv2, coast_s = hohmann(r1_m, r2_m)
    print(f"Textbook: burns of {dv1:.2f} and {dv2:.2f} m/s, {coast_s / 60.0:.1f} min apart")

    result, summary = MissionEngine(scenario, service=SimulationService(scenario)).run()
    for report in summary.reports:
        radius_km = np.linalg.norm(report.values["sat-1.position_N"]) / 1e3  # [km]
        print(f"{report.label:>12}: t = {report.t_s / 60.0:6.1f} min, altitude {radius_km - EARTH_RADIUS_KM:.1f} km")

    position = result.series["sat-1.position_N"]
    last_orbit = position.time_s >= summary.reports[0].t_s  # after the second burn, at apoapsis
    radius_km = np.linalg.norm(position.data[last_orbit], axis=1) / 1e3  # [km]
    print(f"Final orbit: altitude {radius_km.min() - EARTH_RADIUS_KM:.2f} to "
          f"{radius_km.max() - EARTH_RADIUS_KM:.2f} km (target {args.to_km:g} km)")
    return {"coast_s": summary.reports[0].t_s, "final_radius_km": radius_km, "target_radius_km": r2_m / 1e3}


if __name__ == "__main__":
    main()
