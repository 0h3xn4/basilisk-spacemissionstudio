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

r"""
Typed simulation result containers, independent of how the data was
produced -- :class:`engine.service.SimulationService` builds :class:`TimeSeries`/
:class:`ResultSet` from Basilisk recorders, and
:class:`engine.mission_engine.MissionEngine` builds :class:`ReportEntry`/
:class:`CommandSummary` from executing a scenario's ``mission_sequence``
-- but nothing in this module imports Basilisk, so it is fully
unit-testable here with synthetic arrays (see ``tests/test_results.py``)
and reusable by both the future GUI (for plotting/tables) and headless/
batch runs (for CSV export) without either one depending on the other.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np


class ResultsError(Exception):
    """Raised on malformed result data (mismatched array lengths, etc.) --
    never silently truncated or NaN-padded.
    """


@dataclass(frozen=True)
class RunProvenance:
    """What produced a :class:`ResultSet` -- design-philosophy audit
    finding (``docs/ux_audit.md``, "no run provenance captured with
    results"): without this, two runs made months apart (possibly after
    a Basilisk/SpaceMissionStudio upgrade silently changed a module
    default) are indistinguishable after the fact, and a result can't be
    traced back to what actually produced it.

    Populated once per :class:`~spacemissionstudio.engine.service.SimulationService`
    instance, by that module (this one stays Basilisk-free -- see this
    file's own module docstring). Monte Carlo batches
    (``engine.monte_carlo``) bypass :class:`ResultSet` entirely (they
    archive raw Basilisk-retained data through
    ``Basilisk.utilities.MonteCarlo.RetentionPolicy``, a separate path),
    so this is only ever populated for an ordinary ``run()``/``run_live()``
    result -- :attr:`ResultSet.provenance` stays ``None`` otherwise.
    """

    spacemissionstudio_version: str
    basilisk_version: str
    run_started_utc: str  # ISO 8601, when SimulationService.build() started
    integrator: str  # schema.scenario.SimSettings.integrator
    dynamics_task_rate_s: float  # [s] schema.scenario.SimSettings.dynamics_task_rate_s
    # Every Basilisk SysModel (every sensor/fault/noise model this app
    # builds) keeps its own class's fixed default RNGSeed
    # (architecture/_GeneralModuleFiles/sys_model.h: 0x1badcad1) unless a
    # Monte Carlo batch explicitly disperses seeds -- confirmed directly
    # against that header and against engine.monte_carlo.py's own
    # setShouldDisperseSeeds(True) call, which is the ONE place seeds are
    # ever varied. So an ordinary run (this field is only ever populated
    # for one) is always bit-for-bit deterministic against the same
    # scenario -- recorded explicitly here rather than left implicit, so
    # that fact is visible without reading this comment.
    rng_seed_note: str = (
        "deterministic: every sensor/fault/noise model used Basilisk's own default "
        "SysModel RNGSeed (0x1badcad1) -- seeds are only ever dispersed during a Monte Carlo batch, "
        "which does not produce a ResultSet"
    )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TimeSeries:
    """One named, multi-column time history (e.g. inertial position, in
    which case ``columns == ("x", "y", "z")`` and ``data`` has shape
    ``(n_samples, 3)``), plus the units it's in -- carried explicitly so a
    plot/export never has to guess.
    """

    name: str
    time_s: np.ndarray  # shape (n,), seconds since scenario epoch
    columns: Sequence[str]
    data: np.ndarray  # shape (n, len(columns))
    units: str = ""

    def __post_init__(self) -> None:
        self.time_s = np.asarray(self.time_s, dtype=float)
        self.data = np.asarray(self.data, dtype=float)
        if self.data.ndim == 1:
            # A recorder that never logged a single sample (e.g.
            # engine.mission_engine.MissionEngine.run() on a
            # mission_sequence with no propagate command in it at all --
            # ExecuteSimulation() is never called, so Basilisk's own
            # recorder .r_BN_N-style accessor returns a bare 1-D array of
            # shape (0,) rather than (0, len(columns)), losing the column
            # count entirely) can't be told apart from a genuinely
            # single-column series by shape alone once it's empty -- trust
            # the caller-supplied `columns` for the column count in that
            # case rather than guessing 1 (confirmed reachable directly
            # against a real Basilisk build; not a hypothetical).
            self.data = self.data.reshape(0, len(self.columns)) if self.data.shape[0] == 0 \
                else self.data.reshape(-1, 1)
        if self.data.shape[0] != self.time_s.shape[0]:
            raise ResultsError(
                f"TimeSeries {self.name!r}: time_s has {self.time_s.shape[0]} samples but "
                f"data has {self.data.shape[0]} rows -- these must match"
            )
        if self.data.shape[1] != len(self.columns):
            raise ResultsError(
                f"TimeSeries {self.name!r}: data has {self.data.shape[1]} columns but "
                f"{len(self.columns)} column names were given ({list(self.columns)})"
            )

    def to_csv(self, path: "str | Path") -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            header = ["time_s"] + [f"{c}" + (f"_{self.units}" if self.units else "") for c in self.columns]
            writer.writerow(header)
            for t, row in zip(self.time_s, self.data):
                writer.writerow([f"{t:.9g}"] + [f"{v:.9g}" for v in row])
        return path


# Design-philosophy audit finding (docs/ux_audit.md, "no active
# conservation/drift diagnostic"): the only numerical-health signal this
# app had was translating a hard Basilisk integrator crash (NaN/inf) into
# a clear error -- a FINITE but wrong result (e.g. a too-coarse timestep
# drifting silently, not crashing) shipped with no flag at all. These
# generous, deliberately coarse tolerances exist to catch a genuine
# blowup/instability (orders of magnitude), not to grade an integrator's
# own fine-grained truncation error -- see
# engine.service.SimulationService._extract_results()'s own gate for
# exactly when this is even called (only a verified-two-body-only
# spacecraft/scenario; every perturbation/thrust source is excluded
# there specifically because it would make a real, non-conserved energy
# change look like a false positive here).
_DEFAULT_CONSERVATION_TOLERANCE = 0.01  # [-] 1% -- see module comment above


def conservation_drift_warnings(name: str, mu: float, r_m: np.ndarray, v_m: np.ndarray,
                                 energy_tol: float = _DEFAULT_CONSERVATION_TOLERANCE,
                                 momentum_tol: float = _DEFAULT_CONSERVATION_TOLERANCE) -> List[str]:
    """Checks specific orbital energy (``v^2/2 - mu/r``) and orbital
    angular momentum magnitude (``|r x v|``) for drift away from their
    own first-sample value, over the recorded ``r_m``/``v_m`` time
    history -- both are EXACTLY conserved for true two-body (point-mass,
    unperturbed, unthrusted) motion, so a drift beyond ``energy_tol``/
    ``momentum_tol`` (a fraction of each quantity's own initial
    magnitude) on a scenario that IS two-body-only almost always means a
    numerical-integration problem, not real physics.

    Pure NumPy -- no Basilisk import, callable directly with synthetic
    arrays in a test. Returns an empty list when everything is within
    tolerance (including when there are fewer than 2 samples -- nothing
    to compare drift against yet). Never raises: this is a diagnostic,
    not a validation failure -- see :attr:`ResultSet.warnings`'s own
    docstring for why a caller should never treat a non-empty result as
    fatal.
    """
    warnings: List[str] = []
    if r_m.shape[0] < 2:
        return warnings
    r_mag = np.linalg.norm(r_m, axis=1)
    v_mag = np.linalg.norm(v_m, axis=1)
    specific_energy = 0.5 * v_mag ** 2 - mu / r_mag
    h_mag = np.linalg.norm(np.cross(r_m, v_m), axis=1)

    energy_scale = mu / max(r_mag[0], 1.0)  # [J/kg] the 1 m floor only matters for a degenerate r_mag[0] == 0
    energy_drift = float(np.max(np.abs(specific_energy - specific_energy[0]))) / energy_scale
    if energy_drift > energy_tol:
        warnings.append(
            f"{name}: specific orbital energy drifted {energy_drift:.1%} from its initial value over "
            f"this run (tolerance {energy_tol:.0%}) -- this spacecraft's gravity/perturbation config is "
            "two-body-only, so energy should stay constant; a drift this large usually means a "
            "numerical-integration problem (try a finer sim_settings.dynamics_task_rate_s or a "
            "higher-order integrator), not real physics."
        )

    momentum_scale = max(float(h_mag[0]), 1e-12)
    momentum_drift = float(np.max(np.abs(h_mag - h_mag[0]))) / momentum_scale
    if momentum_drift > momentum_tol:
        warnings.append(
            f"{name}: orbital angular momentum magnitude drifted {momentum_drift:.1%} from its initial "
            f"value over this run (tolerance {momentum_tol:.0%}) -- same two-body-only reasoning as the "
            "energy check above."
        )
    return warnings


@dataclass
class ResultSet:
    """Every :class:`TimeSeries` produced by one simulation run, keyed by
    name (e.g. ``"sat-1.position_N"``, ``"sat-1.velocity_N"``). One
    :class:`ResultSet` per completed :meth:`engine.service.SimulationService.run`
    call.
    """

    scenario_name: str
    series: Dict[str, TimeSeries] = field(default_factory=dict)
    # None unless a real SimulationService.run()/run_live() populated it
    # (see RunProvenance's own docstring for why Monte Carlo batches never
    # set this) -- every ResultSet built by hand in a test, or by
    # mission_engine's own propagate-free paths, is unaffected.
    provenance: Optional[RunProvenance] = None
    # Informational only -- NEVER raised as an exception, never blocks a
    # run (see conservation_drift_warnings's own docstring for exactly
    # when/why this can be non-empty). Populated by
    # engine.service.SimulationService._extract_results() for whichever
    # spacecraft its own two-body-only gate applies to; empty for every
    # other spacecraft/scenario shape, and always empty for a hand-built
    # ResultSet (e.g. in a test).
    warnings: List[str] = field(default_factory=list)

    def add(self, series: TimeSeries) -> None:
        if series.name in self.series:
            raise ResultsError(f"a TimeSeries named {series.name!r} was already added to this ResultSet")
        self.series[series.name] = series

    def export_csv(self, out_dir: "str | Path") -> Dict[str, Path]:
        """Write one CSV per series into ``out_dir`` (created if needed),
        plus a ``provenance.json`` sidecar when :attr:`provenance` is set
        -- a separate file, not an extra header/row in each CSV, so the
        existing per-series CSV format (and anything already parsing it)
        is completely unchanged. Returns ``{series_name: written_path}``
        (``"provenance"`` included as a key when that file was written).
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = {name: ts.to_csv(out_dir / f"{name}.csv") for name, ts in self.series.items()}
        if self.provenance is not None:
            provenance_path = out_dir / "provenance.json"
            provenance_path.write_text(json.dumps(self.provenance.to_dict(), indent=2))
            paths["provenance"] = provenance_path
        return paths


@dataclass
class ReportEntry:
    """One ``engine.mission_engine.Command(kind="report")``'s result: a
    snapshot (not a time history -- see ``MissionEngine._run_report``'s
    own docstring) of the requested series' most recent values at the
    mission time this report command ran. Defined here (Basilisk-free),
    not in ``engine.mission_engine`` (which imports ``engine.service`` ->
    Basilisk at module level), so it and :class:`CommandSummary` stay
    unit-testable with synthetic data the same way :class:`TimeSeries`/
    :class:`ResultSet` already are.
    """

    label: Optional[str]
    t_s: float  # [s] elapsed mission time when this report ran
    values: Dict[str, np.ndarray]


@dataclass
class CommandSummary:
    """Everything a ``mission_sequence`` run produced beyond the raw
    :class:`ResultSet`: one :class:`ReportEntry` per executed ``report``
    command, in execution order (so a ``report`` inside an ``if``/
    ``while`` only appears when that branch/iteration actually ran), plus
    a count of every command actually executed (a ``while`` body run 5
    times counts each of those 5 runs separately, matching how many times
    each command really affected the simulation). Built by
    ``engine.mission_engine.MissionEngine.run()``.
    """

    reports: List[ReportEntry] = field(default_factory=list)
    commands_executed: int = 0

    def export_csv(self, path: "str | Path") -> Path:
        """Writes every :class:`ReportEntry` to one CSV at ``path``, long
        format (one row per scalar component of every requested series in
        every report -- ``report_index, t_s, label, series, component,
        value``) rather than one column per series: different ``report``
        commands can request different series with different shapes (a
        3-vector position alongside a scalar mass, say), so there is no
        single fixed set of columns a wide-format table could use across
        every row. Matches :meth:`TimeSeries.to_csv`'s own formatting
        convention (``%.9g``) for consistency with the per-series CSVs
        :meth:`ResultSet.export_csv` already writes.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["report_index", "t_s", "label", "series", "component", "value"])
            for report_index, report in enumerate(self.reports):
                for series_name, values in report.values.items():
                    flat = np.asarray(values).reshape(-1)
                    for component_index, value in enumerate(flat):
                        writer.writerow([
                            report_index, f"{report.t_s:.9g}", report.label or "", series_name,
                            component_index, f"{float(value):.9g}",
                        ])
        return path
