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

"""Time scales of a run (ECSS-E-ST-10-09C 5.4.2a, 5.4.4a/b; remediation R02)
and epoch string formatting.

**Time scales and their relationships** (all computed with ERFA, the SOFA
library; cross-checked against SPICE in ``tests/test_time_system.py``):

* **UTC** -- the scenario epoch (``Scenario.epoch_utc``) and every calendar
  date shown to the user.
* **TAI** = UTC + (TAI - UTC), the leap-second count (37 s since
  2017-01-01, the last leap second in both ERFA's table and naif0012.tls;
  later leap seconds, if any are announced, are not modelled).
* **TT** = TAI + 32.184 s.
* **TDB** = TT + (TDB - TT), the periodic relativistic term (|TDB - TT| <
  1.7 ms; ERFA ``dtdb`` at the geocentre).

**The simulation's time variable** is TDB: Basilisk's spiceInterface sets
SPICE ephemeris time (ET, TDB seconds past J2000) to ET(epoch) + t, so every
result series' ``time_s`` is **TDB seconds since the scenario epoch**.
:func:`elapsed_to_utc` converts it back to UTC for display.

**Epoch string formatting:**

``schema.scenario.Scenario.epoch_utc`` (an ISO 8601 UTC string) is the ONE
stored representation of a scenario's epoch. Basilisk's SPICE-backed
modules want it as a SPICE time string instead; :func:`utc_iso_to_spice_string`
is the single place that conversion happens (``engine.service`` feeds its
result to ``spiceInterface``/``simHelpers``, which do the actual ET math).

Basilisk-free: pure ``datetime`` formatting. This module used to also
carry its own SPICE ET/TAI/TT conversion helpers (``utc_to_et``,
``epoch_times``, ``build_epoch_msg``, ...), but nothing in the app ever
called them, and their module-level ``pyswice`` import made even this one
live function un-importable without a Basilisk build.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from typing import Dict, Sequence

import erfa
import numpy as np

# Fixed English month abbreviations -- NOT strftime("%b"), which follows
# the process's LC_TIME locale. QApplication calls setlocale(LC_ALL, "")
# at construction on Linux, so under e.g. a German desktop locale "%b"
# yields "Mär"/"Mai"/"Okt"/"Dez", which SPICE's time parser rejects --
# every GUI run with an epoch in one of those months would fail.
_MONTH_ABBREVIATIONS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                        "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def utc_iso_to_spice_string(epoch_utc: str) -> str:
    """``'2030-01-01T00:00:00'`` -> a SPICE-recognizable time string
    (``'2030 JAN 01 00:00:00.000 (UTC)'``). Any sub-second precision in
    ``epoch_utc`` (schema.scenario.Scenario.validate() only requires it to
    parse as ISO 8601, not to be a whole second) is preserved to
    millisecond resolution -- ``dt.microsecond`` rounded down to
    milliseconds, not a literal ``.000`` that would silently discard it.
    """
    dt = datetime.fromisoformat(epoch_utc)
    if dt.tzinfo is not None:
        # Scenario.validate() only requires epoch_utc to parse via
        # datetime.fromisoformat() -- it does not reject a timezone-aware
        # string (e.g. "...+05:00"). The output is labeled "(UTC)", so a
        # tz-aware value must be CONVERTED to UTC here, not have its offset
        # silently dropped (which would format the original wall-clock time
        # under a UTC label, off by the offset amount).
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    millis = dt.microsecond // 1000
    month = _MONTH_ABBREVIATIONS[dt.month - 1]
    return f"{dt.year:04d} {month} {dt.day:02d} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}.{millis:03d} (UTC)"


TT_MINUS_TAI_S = 32.184  # [s] by definition
LAST_LEAP_SECOND_UTC = "2017-01-01"  # in ERFA's table and naif0012.tls
_J2000_JD = 2451545.0  # [day]


def _naive_utc(epoch_utc) -> datetime:
    epoch = datetime.fromisoformat(epoch_utc) if isinstance(epoch_utc, str) else epoch_utc
    if epoch.tzinfo is not None:
        epoch = epoch.astimezone(timezone.utc).replace(tzinfo=None)
    return epoch


def _quiet(function, *args):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", erfa.ErfaWarning)  # "dubious year" for epochs past ERFA's table
        return function(*args)


def tai_minus_utc_s(epoch_utc) -> float:
    """Leap-second count TAI - UTC [s] on ``epoch_utc``."""
    epoch = _naive_utc(epoch_utc)
    return float(_quiet(erfa.dat, epoch.year, epoch.month, epoch.day, 0.0))


def utc_to_tdb_jd(epoch_utc):
    """Two-part TDB Julian date of a UTC epoch (ISO string or naive datetime)."""
    epoch = _naive_utc(epoch_utc)
    u1, u2 = _quiet(erfa.dtf2d, "UTC", epoch.year, epoch.month, epoch.day, epoch.hour, epoch.minute,
                    epoch.second + epoch.microsecond / 1e6)
    a1, a2 = _quiet(erfa.utctai, u1, u2)
    t1, t2 = erfa.taitt(a1, a2)
    return erfa.tttdb(t1, t2, _tdb_minus_tt_s(t1, t2))


def _tdb_minus_tt_s(t1, t2):
    """TDB - TT [s] at the geocentre (scalar or array two-part TT date)."""
    fraction = ((np.asarray(t1) - 0.5) % 1.0 + t2) % 1.0  # [day] fraction of the day, adequate here
    return erfa.dtdb(t1, t2, fraction, 0.0, 0.0, 0.0)


def tdb_seconds_past_j2000(epoch_utc) -> float:
    """SPICE ephemeris time (TDB seconds past J2000) of a UTC epoch."""
    d1, d2 = utc_to_tdb_jd(epoch_utc)
    return ((d1 - _J2000_JD) + d2) * 86400.0


def elapsed_to_utc(epoch_utc, elapsed_tdb_s: Sequence[float]):
    """UTC datetimes of simulation times (TDB seconds since ``epoch_utc``):
    epoch + t minus the change of (TDB - UTC) since the epoch, i.e. of the
    periodic TDB - TT term and of the leap-second count."""
    epoch = _naive_utc(epoch_utc)
    t = np.atleast_1d(np.asarray(elapsed_tdb_s, dtype=float))  # [s]
    base = np.datetime64(epoch, "us")
    approx = base + np.round(t * 1e6).astype(np.int64).astype("timedelta64[us]")
    # TDB - TT has no daily terms at the geocentre: evaluated every 6 h and
    # interpolated linearly (error < 0.1 us).
    tt1, tt2 = _quiet(erfa.utctai, *_quiet(erfa.dtf2d, "UTC", epoch.year, epoch.month, epoch.day, epoch.hour,
                                           epoch.minute, epoch.second + epoch.microsecond / 1e6))
    tt1, tt2 = erfa.taitt(tt1, tt2)
    days = t / 86400.0  # [day]
    grid = np.linspace(days.min(), days.max(), max(2, int((days.max() - days.min()) * 4) + 2))  # [day]
    grid_offset = _tdb_minus_tt_s(np.full_like(grid, tt1), tt2 + grid)  # [s]
    tdb_change = np.interp(days, grid, grid_offset) - _tdb_minus_tt_s(tt1, tt2)  # [s]
    dates = approx.astype("datetime64[D]")
    years = dates.astype("datetime64[Y]").astype(np.int64) + 1970
    months = dates.astype("datetime64[M]").astype(np.int64) % 12 + 1
    day_of_month = (dates - dates.astype("datetime64[M]")).astype(np.int64) + 1
    leap_change = _quiet(erfa.dat, years, months, day_of_month, 0.0) - tai_minus_utc_s(epoch)  # [s]
    correction = np.round((tdb_change + leap_change) * 1e6).astype(np.int64).astype("timedelta64[us]")
    return (approx - correction).astype(object)


def time_scales(epoch_utc) -> Dict[str, object]:
    """The scenario epoch on every scale and the offsets between them, for
    output metadata."""
    epoch = _naive_utc(epoch_utc)
    u1, u2 = _quiet(erfa.dtf2d, "UTC", epoch.year, epoch.month, epoch.day, epoch.hour, epoch.minute,
                    epoch.second + epoch.microsecond / 1e6)
    a1, a2 = _quiet(erfa.utctai, u1, u2)
    t1, t2 = erfa.taitt(a1, a2)
    tdb_minus_tt = _tdb_minus_tt_s(t1, t2)
    return {
        "time_variable": "TDB seconds since the scenario epoch",
        "epoch_utc": epoch.isoformat(),
        "epoch_tdb_seconds_past_j2000": tdb_seconds_past_j2000(epoch),
        "tai_minus_utc_s": tai_minus_utc_s(epoch),
        "tt_minus_tai_s": TT_MINUS_TAI_S,
        "tdb_minus_tt_s": float(tdb_minus_tt),
        "last_leap_second_utc": LAST_LEAP_SECOND_UTC,
        "conversions": "ERFA (SOFA): dat, utctai, taitt, dtdb",
    }
