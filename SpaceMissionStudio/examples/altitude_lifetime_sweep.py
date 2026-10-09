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

"""A parameter sweep: orbital lifetime against altitude (needs Basilisk).

Takes template 22's satellite, moves it to each altitude (keeping the
orbit Sun-synchronous) and asks the End of Life tab's estimator when drag
brings it down, from the scenario's own atmosphere and the real solar
activity record and forecast shipped with the app. The pattern -- load a
scenario, change one field in a loop, compute something -- works for any
setting.

Run it from the SpaceMissionStudio folder::

    python3 examples/altitude_lifetime_sweep.py --altitudes 400,450,500,550
"""

from __future__ import annotations

import argparse
from pathlib import Path

from spacemissionstudio.engine.orbit_design import sun_synchronous_inclination_deg
from spacemissionstudio.schema import load_scenario

TEMPLATE = (Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
            / "22_starter_first_leo_satellite.json")
EARTH_RADIUS_KM = 6378.0  # [km] the round figure the bundled templates use
DISPOSAL_RULE_YEARS = 5.0  # [year] ESA's Zero Debris approach and the FCC


def lifetime_years(altitude_km: float, max_years: float) -> tuple:
    """(years to re-entry, re-entered within ``max_years``) at ``altitude_km`` [km]."""
    from spacemissionstudio.engine.lifetime import spacecraft_lifetime  # imports Basilisk

    scenario = load_scenario(TEMPLATE)
    orbit = scenario.spacecraft[0].orbit
    orbit.semi_major_axis_km = EARTH_RADIUS_KM + altitude_km  # [km]
    orbit.inclination_deg = sun_synchronous_inclination_deg(orbit.semi_major_axis_km)
    # The end-of-life drag coefficient (ESA AD10: 2.2), as the End of Life tab uses by default.
    result = spacecraft_lifetime(scenario, scenario.spacecraft[0].name, max_years=max_years, drag_coeff=2.2)
    return result.lifetime_years, result.reentered


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description="Orbital lifetime against altitude.")
    parser.add_argument("--altitudes", default="400,450,500,550",
                        help="comma-separated altitudes [km] (default: 400,450,500,550)")
    parser.add_argument("--max-years", type=float, default=30.0, help="how far ahead to look [year]")
    args = parser.parse_args(argv)

    lifetimes = {}
    print(f"{'altitude':>9}  {'lifetime':>12}  within {DISPOSAL_RULE_YEARS:g} years?")
    for altitude_km in (float(a) for a in args.altitudes.split(",")):
        years, reentered = lifetime_years(altitude_km, args.max_years)
        lifetimes[altitude_km] = years if reentered else None
        shown = f"{years:8.2f} yr" if reentered else f"> {args.max_years:g} yr"
        verdict = "yes" if reentered and years <= DISPOSAL_RULE_YEARS else "no"
        print(f"{altitude_km:6.0f} km  {shown:>12}  {verdict}")
    return lifetimes


if __name__ == "__main__":
    main()
