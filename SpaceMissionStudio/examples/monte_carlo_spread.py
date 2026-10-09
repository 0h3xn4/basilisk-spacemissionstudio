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

"""Run a Monte Carlo batch, then read its results back (the batch needs Basilisk).

Run Monte Carlo... (GUI) and ``spacemissionstudio monte-carlo`` (CLI) save
each run to the folder you choose. Next to Basilisk's own archive (pickles,
which only the batch that wrote them reads), the tool writes a summary
anyone can read safely: ``batch_results.npz`` (every run's position and
velocity) and ``batch_results.json`` (the values each run drew). The GUI's
Monte Carlo tab shows it; this script reads it with
``spacemissionstudio.engine.monte_carlo_results`` and prints how far apart
the runs end up, day by day.

Run it from the SpaceMissionStudio folder::

    python3 examples/monte_carlo_spread.py --runs 20 --archive mc_out
    python3 examples/monte_carlo_spread.py --read mc_out        # results you already have
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from spacemissionstudio.engine import monte_carlo_results as mcr
from spacemissionstudio.schema import load_scenario

TEMPLATE = (Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
            / "25_monte_carlo_orbit_and_drag_dispersions.json")


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


def daily_spread(batch: mcr.MonteCarloBatch, spacecraft: str = "sat-1") -> dict:
    """{day: (radial, along-track, cross-track) 1-sigma spread [km]}, once a
    day and at the end, measured along the orbit from the mean of the runs."""
    rel = mcr.offsets(batch.positions[spacecraft], batch.velocities[spacecraft])  # [m]
    end_day = float(batch.time_s[-1]) / 86400.0  # [day]
    spread = {}
    for day in [*np.arange(1.0, end_day, 1.0), end_day]:
        row = min(int(np.searchsorted(batch.time_s, day * 86400.0 - 1.0)), batch.time_s.size - 1)
        spread[round(float(day), 3)] = tuple(float(s) / 1e3 for s in rel[:, row, :].std(axis=0))
    return spread


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description="Run template 25's Monte Carlo batch and print its spread.")
    parser.add_argument("--archive", type=Path, default=Path("mc_out"), help="folder the batch saves to")
    parser.add_argument("--read", type=Path, help="only read the results already in this folder")
    parser.add_argument("--runs", type=int, default=20, help="number of runs (default: 20)")
    parser.add_argument("--days", type=float, default=3.0, help="length of each run [day] (default: 3)")
    parser.add_argument("--threads", type=int, default=1, help="runs in parallel (default: 1)")
    args = parser.parse_args(argv)

    folder = args.read or args.archive
    if args.read is None:
        run_batch(folder, args.runs, args.days, args.threads)
    batch = mcr.load(folder)
    cd = [drawn["sat-1 drag coefficient [-]"] for drawn in batch.drawn if "sat-1 drag coefficient [-]" in drawn]
    if cd:
        print(f"{len(batch.runs)} runs; drag coefficients drawn between {min(cd):.2f} and {max(cd):.2f}")
    spread = daily_spread(batch)
    for day, (radial, along, cross) in spread.items():
        print(f"day {day:5.2f}: 1-sigma {along:7.1f} km along track, {radial:5.2f} km radial, "
              f"{cross:5.2f} km cross-track")
    return spread


if __name__ == "__main__":
    main()
