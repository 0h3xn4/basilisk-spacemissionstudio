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

"""What a SIL run measured: per-signal residuals against the simulation's
own flight-software modules, timing and dropped steps. Basilisk-free:
:class:`Comparator` reads payload bytes with the layouts the export
records (:func:`..fsw_export.model.leaves`)."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..fsw_export.model import leaves
from .contract import PortSpec

MAX_SAMPLES = 5000  # residual time-series samples kept per signal


@dataclass
class SignalStats:
    """One scalar of one output or telemetry payload."""
    name: str  # "<port>.<field>[<i>]"
    port: str
    kind: str  # "output" or "telemetry"
    max_abs_error: float = 0.0
    rms_error: float = 0.0
    time_of_max_s: float = 0.0  # [s]
    max_abs_reference: float = 0.0
    steps_missing: int = 0  # steps the flight software did not write this port


def timing_summary(values: Sequence[int]) -> Dict[str, float]:
    """Mean, median, 99th percentile, maximum and standard deviation [s]."""
    if not len(values):
        return {"mean_s": 0.0, "p50_s": 0.0, "p99_s": 0.0, "max_s": 0.0, "jitter_s": 0.0}
    data = np.asarray(values, dtype=float) * 1e-9  # [s]
    return {"mean_s": float(data.mean()), "p50_s": float(np.percentile(data, 50)),
            "p99_s": float(np.percentile(data, 99)), "max_s": float(data.max()), "jitter_s": float(data.std())}


@dataclass
class SilReport:
    spacecraft: str
    binary: str
    binary_sha256: str
    fsw_name: str
    fsw_config_digest: str
    scenario_config_digest: str
    contract_version: int
    rate_ns: int
    address_kind: str  # "unix" or "tcp"
    steps: int = 0
    dropped_steps: int = 0
    first_dropped_times_s: List[float] = field(default_factory=list)  # [s], at most 20
    late_replies: int = 0
    round_trip: Dict[str, float] = field(default_factory=dict)  # the simulation's STEP-to-OUTPUT time
    execution: Dict[str, float] = field(default_factory=dict)  # the flight software's own step time
    signals: List[SignalStats] = field(default_factory=list)
    sample_times_s: List[float] = field(default_factory=list)  # [s]
    # signal -> residual at each sample time; only signals that are not zero on both sides for the whole
    # run (unused array slots such as motorTorque[4..35] keep their statistics, not a series)
    residuals: Dict[str, List[float]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    log_tail: str = ""  # the end of what the program wrote to stdout and stderr
    completed: bool = False

    @property
    def max_abs_error(self) -> float:
        provided = [s.max_abs_error for s in self.signals if s.steps_missing < self.steps - self.dropped_steps]
        return max(provided) if provided else 0.0

    @property
    def signals_missing(self) -> int:
        """Signals the flight software never wrote."""
        return sum(1 for s in self.signals if self.steps and s.steps_missing >= self.steps - self.dropped_steps)

    def worst_signals(self, count: int = 10) -> List[SignalStats]:
        return sorted(self.signals, key=lambda s: (-(s.steps_missing > 0), -s.max_abs_error))[:count]

    def summary_lines(self) -> List[str]:
        lines = [f"SIL run of {self.spacecraft} against {self.fsw_name} ({self.binary})",
                 f"  {self.steps} steps, {self.dropped_steps} dropped, contract v{self.contract_version} over "
                 f"{self.address_kind}",
                 f"  round trip: mean {self.round_trip.get('mean_s', 0) * 1e3:.3f} ms, p99 "
                 f"{self.round_trip.get('p99_s', 0) * 1e3:.3f} ms, max {self.round_trip.get('max_s', 0) * 1e3:.3f} ms, "
                 f"jitter {self.round_trip.get('jitter_s', 0) * 1e3:.3f} ms",
                 f"  flight-software step: mean {self.execution.get('mean_s', 0) * 1e6:.1f} us, max "
                 f"{self.execution.get('max_s', 0) * 1e6:.1f} us",
                 f"  largest |residual| {self.max_abs_error:.6g} over {len(self.signals)} signals"
                 + (f"; {self.signals_missing} never written by the flight software" if self.signals_missing else "")]
        for s in self.worst_signals(5):
            missing = f", not written at {s.steps_missing} steps" if s.steps_missing else ""
            lines.append(f"    {s.name:<56} max {s.max_abs_error:.6g} at t = {s.time_of_max_s:.6g} s, "
                         f"rms {s.rms_error:.3g}{missing}")
        lines += [f"  warning: {w}" for w in self.warnings]
        return lines

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "SilReport":
        data = json.loads(text)
        data["signals"] = [SignalStats(**s) for s in data["signals"]]
        return cls(**data)

    def to_result_set(self):
        """The sampled residuals as plottable series, one per port:
        ``<spacecraft>.sil_residual.<port>``, a column per signal."""
        from ..engine.results import ResultSet, TimeSeries

        result = ResultSet(scenario_name=f"{self.spacecraft} SIL residuals")
        by_port: Dict[str, List[str]] = {}
        for stats in self.signals:
            if stats.name in self.residuals:
                by_port.setdefault(stats.port, []).append(stats.name)
        times = np.asarray(self.sample_times_s, dtype=float)
        for port, names in by_port.items():
            data = np.column_stack([np.asarray(self.residuals[n], dtype=float) for n in names]) if times.size else \
                np.zeros((0, len(names)))
            columns = [n[len(port) + 1:] for n in names]
            result.add(TimeSeries(f"{self.spacecraft}.sil_residual.{port}", times, columns, data))
        return result

    def write_residuals_csv(self, path) -> None:
        names = sorted(self.residuals)
        with Path(path).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["time_s"] + names)
            for i, t in enumerate(self.sample_times_s):
                writer.writerow([repr(t)] + [repr(self.residuals[n][i]) for n in names])


class _PortReader:
    """A payload's scalars as one float vector, with their names."""

    def __init__(self, port: PortSpec, layout: dict):
        self.port = port
        self.runs = [(offset, count, np.dtype(kind)) for offset, count, kind, _ in leaves(layout)]
        self.names = []
        for _, count, _, name in leaves(layout):
            self.names += [f"{port.name}.{name}[{i}]" for i in range(count)] if count > 1 else [f"{port.name}.{name}"]

    def values(self, payload: bytes) -> np.ndarray:
        parts = [np.frombuffer(payload, dtype=kind, count=count, offset=offset).astype(np.float64)
                 for offset, count, kind in self.runs]
        return np.concatenate(parts) if parts else np.zeros(0)


class Comparator:
    """Accumulates residual = external - reference for every scalar of the
    output and telemetry ports, step by step."""

    def __init__(self, outputs: List[PortSpec], telemetry: List[PortSpec], layouts: Dict[str, dict],
                 expected_steps: int):
        self.readers = [(_PortReader(p, layouts[p.message_type]), "output") for p in outputs]
        self.readers += [(_PortReader(p, layouts[p.message_type]), "telemetry") for p in telemetry]
        self.stats = [[SignalStats(n, r.port.name, kind) for n in r.names] for r, kind in self.readers]
        self._sum_sq = [np.zeros(len(r.names)) for r, _ in self.readers]
        self._count = [0 for _ in self.readers]
        self._max = [np.zeros(len(r.names)) for r, _ in self.readers]
        self._time_of_max = [np.zeros(len(r.names)) for r, _ in self.readers]
        self._max_ref = [np.zeros(len(r.names)) for r, _ in self.readers]
        self.sample_every = max(1, math.ceil(expected_steps / MAX_SAMPLES))
        self.sample_times: List[float] = []
        self._samples: List[List[np.ndarray]] = [[] for _ in self.readers]
        self.steps = 0

    def add(self, time_s: float, external: Sequence[Optional[bytes]], reference: Sequence[bytes]) -> None:
        """One step: ``external`` (None where the flight software did not
        write the port) against ``reference``, port by port."""
        sample = self.steps % self.sample_every == 0 and len(self.sample_times) < MAX_SAMPLES
        if sample:
            self.sample_times.append(time_s)
        for i, ((reader, _), ext, ref) in enumerate(zip(self.readers, external, reference)):
            ref_values = reader.values(ref)
            np.maximum(self._max_ref[i], np.abs(ref_values), out=self._max_ref[i])
            if ext is None:
                for s in self.stats[i]:
                    s.steps_missing += 1
                if sample:
                    self._samples[i].append(np.full(len(reader.names), np.nan))
                continue
            residual = reader.values(ext) - ref_values
            magnitude = np.abs(residual)
            magnitude[np.isnan(magnitude)] = np.inf  # a NaN on one side only is the worst error there is
            magnitude[np.isnan(ref_values) & np.isnan(residual) & np.isnan(reader.values(ext))] = 0.0
            worse = magnitude > self._max[i]
            self._max[i][worse] = magnitude[worse]
            self._time_of_max[i][worse] = time_s
            self._sum_sq[i] += np.where(np.isfinite(magnitude), magnitude, np.inf) ** 2
            self._count[i] += 1
            if sample:
                self._samples[i].append(residual)
        self.steps += 1

    def finish(self, report: SilReport) -> None:
        report.signals = []
        report.sample_times_s = list(self.sample_times)
        report.residuals = {}
        for i, (reader, _) in enumerate(self.readers):
            rms = np.sqrt(self._sum_sq[i] / self._count[i]) if self._count[i] else np.zeros(len(reader.names))
            samples = np.vstack(self._samples[i]) if self._samples[i] else np.zeros((0, len(reader.names)))
            for j, stats in enumerate(self.stats[i]):
                stats.max_abs_error = float(self._max[i][j])
                stats.rms_error = float(rms[j])
                stats.time_of_max_s = float(self._time_of_max[i][j])
                stats.max_abs_reference = float(self._max_ref[i][j])
                report.signals.append(stats)
                if stats.max_abs_reference > 0.0 or stats.max_abs_error > 0.0 or stats.steps_missing:
                    report.residuals[stats.name] = [float(v) for v in samples[:, j]]
