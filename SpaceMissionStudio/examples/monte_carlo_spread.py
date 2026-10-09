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

"""Run a Monte Carlo batch, then read its archive back (needs Basilisk).

Run Monte Carlo... (GUI) and ``spacemissionstudio monte-carlo`` (CLI) save
each run to an archive folder: ``runN.json`` with the values that run
drew, and Basilisk's own record of every spacecraft's position and
velocity. This script runs template 25 (or reads a folder you already
have) and prints how far apart the runs end up along the orbit, day by
day.

Run it from the SpaceMissionStudio folder::

    python3 examples/monte_carlo_spread.py --runs 20 --archive mc_out
    python3 examples/monte_carlo_spread.py --read mc_out        # an existing archive
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from spacemissionstudio.schema import load_scenario

TEMPLATE = (Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
            / "25_monte_carlo_orbit_and_drag_dispersions.json")
_NS_PER_S = 1e9  # Basilisk records time in nanoseconds


def run_batch(archive: Path, runs: int, days: float, threads: int) -> None:
    from spacemissionstudio.engine.monte_carlo import run_monte_carlo  # imports Basilisk

    scenario = load_scenario(TEMPLATE)
    scenario.monte_carlo.num_runs = runs
    scenario.monte_carlo.thread_count = threads
    scenario.sim_settings.duration_days = days
    scenario.validate()
    print(f"Running {runs} case(s) of {scenario.name!r}, {days:g} day(s) each...")
    failed = run_monte_carlo(scenario, scenario.monte_carlo, archive)
    if failed:
        raise SystemExit(f"runs {failed} failed; see the log")


def along_track_spread(archive: Path, spacecraft: str = "sat-1") -> dict:
    """{day: 1-sigma along-track spread [km]} across every run in ``archive``,
    once a day and at the end."""
    from Basilisk.utilities.MonteCarlo.Controller import Controller

    controller = Controller.load(str(archive))
    run_count = len(list(archive.glob("run*.json")))
    positions, velocities = [], []
    for index in range(run_count):
        messages = controller.getRetainedData(index)["messages"]
        positions.append(messages[f"{spacecraft}.scState.r_BN_N"])  # rows: [time ns, x, y, z] [m]
        velocities.append(messages[f"{spacecraft}.scState.v_BN_N"])  # [m/s]
    time_s = positions[0][:, 0] / _NS_PER_S
    end_day = time_s[-1] / 86400.0  # [day]
    spread = {}
    for day in [*np.arange(1.0, end_day, 1.0), end_day]:
        row = int(np.searchsorted(time_s, day * 86400.0 - 1.0))
        r = np.array([p[min(row, len(p) - 1), 1:4] for p in positions])  # [m]
        v = np.array([w[min(row, len(w) - 1), 1:4] for w in velocities])  # [m/s]
        along = v.mean(axis=0) / np.linalg.norm(v.mean(axis=0))  # the mean direction of flight
        spread[round(float(day), 3)] = float(((r - r.mean(axis=0)) @ along).std()) / 1e3  # [km]
    return spread


def drawn_values(archive: Path) -> list:
    """Each run's drawn values, from its ``runN.json``."""
    return [json.loads(path.read_text()) for path in sorted(archive.glob("run*.json"),
                                                            key=lambda p: int(p.stem[3:]))]


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description="Run template 25's Monte Carlo batch and print its spread.")
    parser.add_argument("--archive", type=Path, default=Path("mc_out"), help="archive folder to write")
    parser.add_argument("--read", type=Path, help="only read this existing archive folder")
    parser.add_argument("--runs", type=int, default=20, help="number of runs (default: 20)")
    parser.add_argument("--days", type=float, default=3.0, help="length of each run [day] (default: 3)")
    parser.add_argument("--threads", type=int, default=1, help="runs in parallel (default: 1)")
    args = parser.parse_args(argv)

    archive = args.read or args.archive
    if args.read is None:
        run_batch(archive, args.runs, args.days, args.threads)
    cd = [float(next(v for k, v in run.items() if k.endswith("dragCoeff"))) for run in drawn_values(archive)]
    if cd:
        print(f"{len(cd)} runs; drag coefficients drawn between {min(cd):.2f} and {max(cd):.2f}")
    spread = along_track_spread(archive)
    for day, km in spread.items():
        print(f"day {day:5.2f}: runs spread {km:7.1f} km along track (1-sigma)")
    return spread


if __name__ == "__main__":
    main()
