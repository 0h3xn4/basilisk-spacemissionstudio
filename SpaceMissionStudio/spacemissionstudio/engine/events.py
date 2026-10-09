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
"""The events of a run, read from its recorded series (UX/UI guidelines:
"events as a timeline with a sortable, exportable table").

One model for every kind: ground-station passes, eclipses, manoeuvre
burns, thruster firings and mode changes. Each :class:`Event` is a
contiguous run of samples where a recorded series says the event is on,
from its first to its last such sample -- the convention the Results
tab's access timeline already uses. Nothing is simulated or estimated
here: a kind of event appears only when the run recorded the series it
comes from.

Basilisk-free: it reads a :class:`engine.results.ResultSet` only.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np

from .results import ResultSet, TimeSeries

ACCESS = "pass"
ECLIPSE = "eclipse"
BURN = "burn"
THRUSTER = "thruster firing"
MODE = "mode"
KINDS = (ACCESS, ECLIPSE, BURN, THRUSTER, MODE)

_UMBRA_SHADOW_FACTOR = 0.01  # [-] below this the Sun is fully hidden (umbra)
# The phasing controller's states (engine.orbit_maintenance.PhasingKeepingController).
_PHASING_IDLE, _PHASING_BURN_OUT, _PHASING_DRIFT, _PHASING_BURN_RESTORE = range(4)
_PHASING_FIRING = 4  # a Basilisk formation law firing (engine.formation_control.FIRING)


@dataclass(frozen=True)
class Event:
    """One event: ``start_s`` to ``end_s`` [s] of elapsed (TDB) time since the epoch."""

    kind: str
    spacecraft: str
    start_s: float  # [s]
    end_s: float  # [s]
    label: str
    detail: str = ""
    other: str = ""  # the ground station of a pass

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s  # [s]

    @property
    def row(self) -> str:
        """The timeline row this event is drawn on."""
        return f"{self.other} - {self.spacecraft}" if self.other else f"{self.spacecraft} {self.kind}"


def intervals(time_s: np.ndarray, on: np.ndarray) -> List[Tuple[int, int]]:
    """``(first, last)`` sample indices of every contiguous run of ``on``."""
    on = np.asarray(on, dtype=bool)
    if on.size == 0:
        return []
    changes = np.flatnonzero(np.diff(np.concatenate([[False], on, [False]]).astype(int)))
    return list(zip(changes[0::2].tolist(), (changes[1::2] - 1).tolist()))


def _column(series: TimeSeries, index: int = 0) -> np.ndarray:
    return series.data[:, index] if series.data.shape[0] else np.zeros(0)


def _spans(series: TimeSeries, on: np.ndarray, make: Callable[[int, int], Event]) -> List[Event]:
    return [make(first, last) for first, last in intervals(series.time_s, on)]


def _delta_v_between(result: ResultSet, name: str, start_s: float, end_s: float) -> Optional[float]:
    """Cumulative delta-V [m/s] gained between two times, from ``name``."""
    series = result.series.get(name)
    if series is None or series.time_s.size == 0:
        return None
    values = _column(series)
    before = values[max(np.searchsorted(series.time_s, start_s, side="left") - 1, 0)]
    after = values[min(np.searchsorted(series.time_s, end_s, side="right"), series.time_s.size - 1)]
    return float(after - before)  # [m/s]


def _passes(result: ResultSet) -> List[Event]:
    events = []
    for name, series in result.series.items():
        prefix, _, part = name.rpartition(".")
        if part != "has_access" or ".access_to_" not in prefix:
            continue
        station, _, spacecraft = prefix.partition(".access_to_")
        elevation = result.series.get(f"{prefix}.elevation")

        def make(first, last, series=series, station=station, spacecraft=spacecraft, elevation=elevation):
            detail = ""
            if elevation is not None and elevation.time_s.shape == series.time_s.shape:
                peak = math.degrees(float(np.max(_column(elevation)[first:last + 1])))  # [deg]
                detail = f"max elevation {peak:.1f} deg"
            return Event(ACCESS, spacecraft, float(series.time_s[first]), float(series.time_s[last]),
                         f"pass over {station}", detail, station)

        events += _spans(series, _column(series) != 0, make)
    return events


def _eclipses(result: ResultSet) -> List[Event]:
    events = []
    for name, series in result.series.items():
        if not name.endswith(".eclipse.illumination_factor"):
            continue
        spacecraft = name[:-len(".eclipse.illumination_factor")]
        factor = _column(series)

        def make(first, last, series=series, spacecraft=spacecraft, factor=factor):
            deepest = float(np.min(factor[first:last + 1]))  # [-]
            label = "umbra" if deepest < _UMBRA_SHADOW_FACTOR else "penumbra"
            return Event(ECLIPSE, spacecraft, float(series.time_s[first]), float(series.time_s[last]),
                         f"eclipse ({label})", f"lowest sunlight {deepest:.0%}")

        events += _spans(series, factor < 1.0, make)
    return events


def _burns(result: ResultSet) -> List[Event]:
    events = []
    for name, series in result.series.items():
        if name.endswith(".station_keeping.burn_on"):
            spacecraft, controller = name[:-len(".station_keeping.burn_on")], "station_keeping"
            columns = [(0, "station-keeping burn")]
        elif name.endswith(".geo_station_keeping.burn_on"):
            spacecraft, controller = name[:-len(".geo_station_keeping.burn_on")], "geo_station_keeping"
            columns = [(0, "east-west burn"), (1, "north-south burn")]
        else:
            continue
        for index, label in columns:
            if index >= series.data.shape[1]:
                continue
            delta_v_name = f"{spacecraft}.{controller}." + (
                {"east-west burn": "east_west.", "north-south burn": "north_south."}.get(label, "") + "delta_v")
            events += _spans(series, _column(series, index) != 0,
                             _burn_maker(result, series, spacecraft, label, delta_v_name))
    for name, series in result.series.items():
        if not name.endswith(".phasing_keeping.state"):
            continue
        spacecraft = name[:-len(".phasing_keeping.state")]
        state = np.rint(_column(series)).astype(int)
        delta_v_name = f"{spacecraft}.phasing_keeping.delta_v"
        events += _spans(series, state == _PHASING_BURN_OUT,
                         _burn_maker(result, series, spacecraft, "phasing burn (start drift)", delta_v_name))
        events += _spans(series, state == _PHASING_BURN_RESTORE,
                         _burn_maker(result, series, spacecraft, "phasing burn (stop drift)", delta_v_name))
        events += _spans(series, state == _PHASING_FIRING,
                         _burn_maker(result, series, spacecraft, "formation control firing", delta_v_name))
    return events


def _burn_maker(result, series, spacecraft, label, delta_v_name):
    def make(first, last):
        start, end = float(series.time_s[first]), float(series.time_s[last])
        delta_v = _delta_v_between(result, delta_v_name, start, end)
        return Event(BURN, spacecraft, start, end, label, "" if delta_v is None else f"delta-V {delta_v:.3f} m/s")
    return make


def _thruster_firings(result: ResultSet) -> List[Event]:
    events = []
    for name, series in result.series.items():
        if not name.endswith(".thruster_on_time") or series.data.shape[0] == 0:
            continue
        spacecraft = name[:-len(".thruster_on_time")]
        firing = np.any(series.data > 0.0, axis=1)

        def make(first, last, series=series, spacecraft=spacecraft):
            fired = [c for i, c in enumerate(series.columns) if np.any(series.data[first:last + 1, i] > 0.0)]
            return Event(THRUSTER, spacecraft, float(series.time_s[first]), float(series.time_s[last]),
                         "thruster firing", ", ".join(fired))

        events += _spans(series, firing, make)
    return events


def _modes(result: ResultSet) -> List[Event]:
    events = []
    for name, series in result.series.items():
        if name.endswith(".comms_pointing.active_mode"):
            spacecraft = name[:-len(".comms_pointing.active_mode")]
            mode = _column(series) > 0.5
            events += _spans(series, mode, lambda f, la, s=series, sc=spacecraft: Event(
                MODE, sc, float(s.time_s[f]), float(s.time_s[la]), "ground-station pointing", "comms mode"))
            events += _spans(series, ~mode, lambda f, la, s=series, sc=spacecraft: Event(
                MODE, sc, float(s.time_s[f]), float(s.time_s[la]), "Sun pointing", "power mode"))
        elif name.endswith(".phasing_keeping.state"):
            spacecraft = name[:-len(".phasing_keeping.state")]
            drifting = np.rint(_column(series)).astype(int) == _PHASING_DRIFT
            events += _spans(series, drifting, lambda f, la, s=series, sc=spacecraft: Event(
                MODE, sc, float(s.time_s[f]), float(s.time_s[la]), "phasing drift", "between the two burns"))
    return events


_EXTRACTORS = (_passes, _eclipses, _burns, _thruster_firings, _modes)


def extract_events(result: Optional[ResultSet]) -> List[Event]:
    """Every event in ``result``, sorted by start time. Never raises: a
    series that cannot be read is skipped (the rest still show)."""
    if result is None:
        return []
    events: List[Event] = []
    for extractor in _EXTRACTORS:
        try:
            events += extractor(result)
        except (ValueError, IndexError, TypeError):
            continue
    return sorted(events, key=lambda e: (e.start_s, e.kind, e.spacecraft, e.label))


def missing_kinds(result: Optional[ResultSet]) -> Dict[str, str]:
    """Kinds this run could not show, and why (the series was not recorded)."""
    names = list(result.series) if result is not None else []
    reasons = {
        ACCESS: ("no ground stations", lambda n: n.endswith(".has_access")),
        ECLIPSE: ("no Sun ephemeris (add 'sun' to the third-body perturbers)",
                  lambda n: n.endswith(".eclipse.illumination_factor")),
        BURN: ("no station-keeping or phasing control", lambda n: n.endswith((".burn_on", ".phasing_keeping.state"))),
        MODE: ("no comms pointing or phasing control",
               lambda n: n.endswith((".comms_pointing.active_mode", ".phasing_keeping.state"))),
    }
    return {kind: why for kind, (why, has) in reasons.items() if not any(has(n) for n in names)}


def write_csv(events: Iterable[Event], path: "str | Path", epoch_utc: Optional[str] = None) -> Path:
    """The events as CSV. With an epoch, UTC start and end columns are added."""
    events = list(events)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    utc = _utc_columns(events, epoch_utc)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["kind", "spacecraft", "ground_station", "event", "start_s", "end_s", "duration_s",
                         "detail"] + (["start_utc", "end_utc"] if utc else []))
        for index, event in enumerate(events):
            writer.writerow([event.kind, event.spacecraft, event.other, event.label, f"{event.start_s:.3f}",
                             f"{event.end_s:.3f}", f"{event.duration_s:.3f}", event.detail]
                            + (list(utc[index]) if utc else []))
    return path


def _utc_columns(events: List[Event], epoch_utc: Optional[str]) -> List[Tuple[str, str]]:
    if not epoch_utc or not events:
        return []
    from . import time_system

    try:
        starts = time_system.elapsed_to_utc(epoch_utc, [e.start_s for e in events])
        ends = time_system.elapsed_to_utc(epoch_utc, [e.end_s for e in events])
    except ValueError:
        return []
    return [(utc_text(s), utc_text(e)) for s, e in zip(starts, ends)]


def utc_text(moment: datetime, timespec: str = "milliseconds") -> str:
    """ISO UTC text rounded (not cut) to ``timespec`` ("seconds" or "milliseconds")."""
    half = timedelta(seconds=0.5) if timespec == "seconds" else timedelta(milliseconds=0.5)
    return (moment + half).isoformat(sep=" ", timespec=timespec)
