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

"""Run a bundled template headlessly and look at what came out (needs Basilisk).

The same three steps as the GUI's Run Simulation, in code:

1. ``load_scenario()`` reads a scenario file (any template, or your own).
2. ``SimulationService(scenario).run()`` builds the Basilisk simulation and
   runs it; a scenario with a Mission Sequence runs through
   ``MissionEngine`` instead, exactly as the GUI and CLI do.
3. The ``ResultSet`` holds one ``TimeSeries`` per plotted quantity
   (``result.series["my-sat.position_N"]``: time in seconds since the
   epoch, a data array, column names and units). ``events.extract_events()``
   lists the passes, eclipses and burns of the Events tab.

Run it from the SpaceMissionStudio folder::

    python3 examples/run_a_template.py                  # template 22, one day
    python3 examples/run_a_template.py 18 --days 3 --csv out
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from spacemissionstudio.schema import load_scenario

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"


def template_path(number: str) -> Path:
    """The bundled template whose file name starts with ``number`` (e.g. "22")."""
    matches = sorted(TEMPLATES_DIR.glob(f"{int(number):02d}_*.json"))
    if not matches:
        raise SystemExit(f"no bundled template {number!r} in {TEMPLATES_DIR}")
    return matches[0]


def run(scenario):
    """Run ``scenario`` the way the GUI does; returns its ``ResultSet``."""
    from spacemissionstudio.engine.service import SimulationService  # imports Basilisk

    service = SimulationService(scenario)
    if scenario.mission_sequence:
        from spacemissionstudio.engine.mission_engine import MissionEngine

        result, summary = MissionEngine(scenario, service=service).run()
        for report in summary.reports:
            print(f"report {report.label!r} at {report.t_s / 60.0:.1f} min")
        return result
    return service.run()


def summarize(result) -> list:
    """One line per series: name, units, and its first and last values."""
    lines = []
    for name in sorted(result.series):
        series = result.series[name]
        if series.data.shape[0] == 0:
            continue
        first, last = series.data[0], series.data[-1]
        lines.append(f"{name} [{series.units}] {series.columns[0]}: "
                     f"{first[0]:.6g} -> {last[0]:.6g} over {series.time_s[-1] / 3600.0:.2f} h")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a bundled template and summarize its results.")
    parser.add_argument("template", nargs="?", default="22", help="template number (default: 22)")
    parser.add_argument("--days", type=float, help="override the run length [day]")
    parser.add_argument("--csv", type=Path, help="also write every series to this folder as CSV")
    args = parser.parse_args(argv)

    from spacemissionstudio.engine import events

    scenario = load_scenario(template_path(args.template))
    if args.days is not None:
        scenario.sim_settings.duration_days = args.days
    scenario.validate()
    print(f"Running {scenario.name!r} for {scenario.sim_settings.duration_days:g} day(s)...")
    result = run(scenario)

    print("\n".join(summarize(result)))
    for event in events.extract_events(result):
        print(f"event: {event.label} ({event.spacecraft}) {event.start_s / 60.0:.1f}-{event.end_s / 60.0:.1f} min")

    for sc in scenario.spacecraft:  # one derived number, as an example of working with the arrays
        position = result.series.get(f"{sc.name}.position_N")
        if position is not None:
            radius_km = np.linalg.norm(position.data, axis=1) / 1e3  # [km]
            print(f"{sc.name}: distance from Earth's centre {radius_km.min():.1f}-{radius_km.max():.1f} km")
    for warning in result.warnings:
        print(f"note: {warning}")
    if args.csv:
        written = result.export_csv(args.csv)
        print(f"Wrote {len(written)} file(s) to {args.csv}")
    return result


if __name__ == "__main__":
    main()
