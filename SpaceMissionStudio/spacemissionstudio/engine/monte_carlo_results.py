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

"""What a Monte Carlo batch produced, in a form the GUI and CLI can show.

Basilisk's ``MonteCarlo.Controller`` archives each run as a gzipped
pickle. Loading a pickle runs code, so the tool never reads an archive
it did not just write (security analysis S-04): at the end of a batch,
``engine.monte_carlo.run_monte_carlo`` reads back the files that same
call wrote and saves this module's pickle-free summary next to them --
``batch_results.npz`` (positions and velocities, ``numpy.savez``, read
with ``allow_pickle=False``) and ``batch_results.json`` (the values each
run drew). Everything here works on that summary only, with no Basilisk
import.

The spread is measured against the batch's mean, along the orbit rather
than in straight lines (a straight-line frame would turn a large
along-track spread into a false radial one, as the orbit curves away
from it): at each sample, R points from the central body to the runs'
mean position, W along the mean orbit's angular momentum, and S = W x R.
A run's radial offset is its distance from the central body minus the
runs' mean distance; its along-track offset is the arc, at that mean
distance, by which it leads (+) or trails (-) R in the R-S plane; its
cross-track offset is the arc out of that plane.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .constellation import CENTRAL_BODY_EQUATORIAL_RADIUS_KM
from .results import ResultSet, TimeSeries

SUMMARY_NPZ = "batch_results.npz"
SUMMARY_JSON = "batch_results.json"
SUMMARY_FORMAT = 1
# The summary keeps at most this many samples per run (evenly strided), so
# a long or finely recorded batch of many runs still fits in memory.
MAX_SAMPLES = 2000
# Per-run curves are plotted for at most this many runs; the spread
# series always covers every run.
MAX_PLOTTED_RUNS = 100
OFFSET_COMPONENTS = ("radial", "along_track", "cross_track")


class MonteCarloResultsError(Exception):
    """A batch summary that is missing, of another format, or inconsistent."""


@dataclass
class MonteCarloBatch:
    """Every successful run of one batch on a shared time grid.

    ``positions[sc]``/``velocities[sc]`` have shape (runs, samples, 3), in
    m and m/s in the simulation's inertial frame; row ``k`` is run
    ``runs[k]``. ``drawn[k]`` holds the values that run drew, keyed by a
    readable label ("sat-1 drag coefficient [-]").
    """

    scenario_name: str
    central_body: str
    time_s: np.ndarray
    runs: List[int]
    failed: List[int]
    positions: Dict[str, np.ndarray]
    velocities: Dict[str, np.ndarray]
    drawn: List[Dict[str, float]] = field(default_factory=list)
    epoch_utc: str = ""  # the scenario's epoch, so plots can show dates

    @property
    def spacecraft(self) -> List[str]:
        return list(self.positions)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MonteCarloResultsError(message)


def save(batch: MonteCarloBatch, folder: "str | Path") -> Path:
    """Write the summary into ``folder``; returns the JSON file's path."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    arrays = {"time_s": np.asarray(batch.time_s, dtype=float)}
    for index, name in enumerate(batch.spacecraft):
        arrays[f"r_{index}"] = np.asarray(batch.positions[name], dtype=float)
        arrays[f"v_{index}"] = np.asarray(batch.velocities[name], dtype=float)
    np.savez_compressed(folder / SUMMARY_NPZ, **arrays)
    meta = {
        "format": SUMMARY_FORMAT,
        "scenario_name": batch.scenario_name,
        "central_body": batch.central_body,
        "epoch_utc": batch.epoch_utc,
        "spacecraft": batch.spacecraft,
        "runs": [int(run) for run in batch.runs],
        "failed": [int(run) for run in batch.failed],
        "drawn": batch.drawn,
    }
    path = folder / SUMMARY_JSON
    path.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return path


def has_summary(folder: "str | Path") -> bool:
    folder = Path(folder)
    return (folder / SUMMARY_JSON).is_file() and (folder / SUMMARY_NPZ).is_file()


def load(folder: "str | Path") -> MonteCarloBatch:
    """Read a summary written by :func:`save`. Never unpickles anything."""
    folder = Path(folder)
    _require(has_summary(folder), f"{folder} has no Monte Carlo results ({SUMMARY_JSON} and {SUMMARY_NPZ}); "
             "run the batch with this version of SpaceMissionStudio to create them")
    try:
        meta = json.loads((folder / SUMMARY_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MonteCarloResultsError(f"could not read {folder / SUMMARY_JSON}: {exc}") from exc
    _require(isinstance(meta, dict) and meta.get("format") == SUMMARY_FORMAT,
             f"{folder / SUMMARY_JSON} is not a format-{SUMMARY_FORMAT} Monte Carlo summary")
    try:
        with np.load(folder / SUMMARY_NPZ, allow_pickle=False) as data:
            arrays = {key: data[key] for key in data.files}
    except (OSError, ValueError) as exc:
        raise MonteCarloResultsError(f"could not read {folder / SUMMARY_NPZ}: {exc}") from exc
    names = list(meta.get("spacecraft", []))
    runs = [int(run) for run in meta.get("runs", [])]
    time_s = arrays.get("time_s")
    _require(time_s is not None and time_s.ndim == 1, f"{SUMMARY_NPZ} has no time axis")
    positions, velocities = {}, {}
    for index, name in enumerate(names):
        r, v = arrays.get(f"r_{index}"), arrays.get(f"v_{index}")
        shape = (len(runs), time_s.shape[0], 3)
        _require(r is not None and v is not None and r.shape == shape and v.shape == shape,
                 f"{SUMMARY_NPZ}: the arrays for {name!r} do not match {len(runs)} runs of {time_s.shape[0]} samples")
        positions[name], velocities[name] = r, v
    drawn = meta.get("drawn") or [{} for _ in runs]
    _require(len(drawn) == len(runs), f"{SUMMARY_JSON}: {len(drawn)} drawn-value rows for {len(runs)} runs")
    return MonteCarloBatch(str(meta.get("scenario_name", "")), str(meta.get("central_body", "earth")), time_s,
                           runs, [int(run) for run in meta.get("failed", [])], positions, velocities,
                           [{str(k): float(v) for k, v in row.items()} for row in drawn],
                           str(meta.get("epoch_utc", "")))


def stride_for(samples: int) -> int:
    """Every how many samples :data:`MAX_SAMPLES` keeps."""
    return max(1, -(-samples // MAX_SAMPLES))


def offsets(positions: np.ndarray, velocities: np.ndarray) -> np.ndarray:
    """(runs, samples, 3) radial, along-track and cross-track offsets [m] of
    each run from the batch's mean, curvilinear (see the module docstring)."""
    mean_r = positions.mean(axis=0)  # (samples, 3)
    mean_v = velocities.mean(axis=0)
    radial = mean_r / np.linalg.norm(mean_r, axis=1, keepdims=True)
    normal = np.cross(mean_r, mean_v)
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    along = np.cross(normal, radial)
    distance = np.linalg.norm(positions, axis=2)  # (runs, samples)
    mean_distance = distance.mean(axis=0)
    unit = positions / distance[:, :, None]
    in_plane = np.arctan2(np.einsum("rtk,tk->rt", unit, along), np.einsum("rtk,tk->rt", unit, radial))
    out_of_plane = np.arcsin(np.clip(np.einsum("rtk,tk->rt", unit, normal), -1.0, 1.0))
    return np.stack([distance - mean_distance, mean_distance * in_plane, mean_distance * out_of_plane], axis=-1)


def _equatorial_radius_m(central_body: str) -> float:
    return CENTRAL_BODY_EQUATORIAL_RADIUS_KM.get(central_body, 0.0) * 1e3


def to_result_set(batch: MonteCarloBatch) -> ResultSet:
    """The batch as plottable series, per spacecraft:

    * ``<sc>.monte_carlo.altitude`` [m]: distance above the central body's
      equatorial radius, one column per run;
    * ``<sc>.monte_carlo.radial_offset``, ``.along_track_offset``,
      ``.cross_track_offset`` [m]: each run against the batch mean;
    * ``<sc>.monte_carlo.spread`` [m]: the 1-sigma of the three offsets
      over all runs.

    Per-run series hold the first :data:`MAX_PLOTTED_RUNS` runs.
    """
    result = ResultSet(scenario_name=f"{batch.scenario_name} (Monte Carlo)")
    shown = min(len(batch.runs), MAX_PLOTTED_RUNS)
    columns = [f"run_{run}" for run in batch.runs[:shown]]
    radius_m = _equatorial_radius_m(batch.central_body)
    for name in batch.spacecraft:
        r, v = batch.positions[name], batch.velocities[name]
        altitude = np.linalg.norm(r, axis=2) - radius_m  # (runs, samples)
        result.add(TimeSeries(f"{name}.monte_carlo.altitude", batch.time_s, columns, altitude[:shown].T, "m"))
        rel = offsets(r, v)
        for index, component in enumerate(OFFSET_COMPONENTS):
            result.add(TimeSeries(f"{name}.monte_carlo.{component}_offset", batch.time_s, columns,
                                  rel[:shown, :, index].T, "m"))
        spread = rel.std(axis=0) if len(batch.runs) > 1 else np.zeros_like(rel[0])
        result.add(TimeSeries(f"{name}.monte_carlo.spread", batch.time_s, list(OFFSET_COMPONENTS), spread, "m"))
    return result


@dataclass(frozen=True)
class SpreadSummary:
    """The 1-sigma offsets [m] at the end of the batch, and the altitude range [m]."""

    radial_m: float
    along_track_m: float
    cross_track_m: float
    altitude_min_m: float
    altitude_max_m: float


def final_spread(batch: MonteCarloBatch, spacecraft: str) -> SpreadSummary:
    rel = offsets(batch.positions[spacecraft], batch.velocities[spacecraft])[:, -1, :]
    sigma = rel.std(axis=0) if len(batch.runs) > 1 else np.zeros(3)
    altitude = np.linalg.norm(batch.positions[spacecraft][:, -1, :], axis=1) - _equatorial_radius_m(batch.central_body)
    return SpreadSummary(float(sigma[0]), float(sigma[1]), float(sigma[2]),
                         float(altitude.min()), float(altitude.max()))


def run_table(batch: MonteCarloBatch, spacecraft: Optional[str] = None):
    """(column labels, rows): per run its index, every drawn value, and
    where it ended against the batch mean [km] (for ``spacecraft``, by
    default the first)."""
    spacecraft = spacecraft or batch.spacecraft[0]
    drawn_labels: List[str] = []
    for row in batch.drawn:
        drawn_labels += [label for label in row if label not in drawn_labels]
    final = offsets(batch.positions[spacecraft], batch.velocities[spacecraft])[:, -1, :] / 1e3  # [km]
    outcome_labels = [f"{spacecraft} final {c.replace('_', '-')} offset [km]" for c in OFFSET_COMPONENTS]
    rows = []
    for k, run in enumerate(batch.runs):
        drawn = batch.drawn[k] if k < len(batch.drawn) else {}
        rows.append([float(run)] + [drawn.get(label, float("nan")) for label in drawn_labels]
                    + [float(value) for value in final[k]])
    return ["Run"] + drawn_labels + outcome_labels, rows


def format_km(value_m: float) -> str:
    """A distance [m] as km to 3 significant figures; under a millimetre
    (rounding noise, e.g. runs that do not differ at all) as 0."""
    return "0 km" if abs(value_m) < 1e-3 else f"{value_m / 1e3:.3g} km"


def summary_lines(batch: MonteCarloBatch) -> List[str]:
    """A few lines for the CLI and the log."""
    days = float(batch.time_s[-1]) / 86400.0 if batch.time_s.size else 0.0
    lines = [f"{len(batch.runs)} run(s) summarized over {days:.3g} day(s); failed: {batch.failed or 'none'}"]
    for name in batch.spacecraft:
        s = final_spread(batch, name)
        lines.append(f"{name}: 1-sigma at the end -- along-track {format_km(s.along_track_m)}, "
                     f"radial {format_km(s.radial_m)}, cross-track {format_km(s.cross_track_m)}")
    return lines
