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
Space-weather resolution for Basilisk's ``spaceWeatherData`` module (which
drives ``msisAtmosphere`` for atmospheric drag).

**Real data only** (user requirement: "never ever use synthetic space
weather -- only real atmospheric models and data"). ``source`` is
``"bundled"`` (the default: CelesTrak's ``SW-All`` file shipped with the
app, ``data/spaceweather/SW-All.txt``, or a newer one the startup prompt
downloaded) or ``"local_file"`` (the user's own CelesTrak file). The file
holds observed daily Kp/Ap and F10.7 since 1957, CelesTrak's 45-day
forecast, and NOAA's monthly F10.7 forecast. Past the observations and
the 45-day forecast, solar activity comes from NASA MSFC's prediction
(``data/spaceweather/oct2026f10-prd.txt``, or the study's own file):
monthly 13-month-smoothed F10.7 and Ap at the 95th/50th/5th percentiles,
as ESA's AD10 guideline (EOP-FM/2024-07-177, Sec. 5.9) prescribes, with
its last 132 months repeated past its end. Only months MSFC does not
reach (before its first) fall back to NOAA's monthly F10.7, which has no
Ap: there, Ap is held at the mean of every observed day in the file (user
decision; 12.8). Runs say which of these they used in their warnings; a
run before the record starts is refused.

**Closed-off/offline policy**: SpaceMissionStudio never accesses the
network implicitly at runtime (real user requirement -- "the app must be
completely closed off and offline, only exception is the installation
process"). ``resolve()`` itself NEVER touches the network.

The ONE allowed exception, besides installation itself: a real user
decision later relaxed the policy to also allow "a one-time fetch during
each startup of the app, to store everything that is needed locally so
it can be used later again" -- but ONLY after explicitly asking the user
first, never automatically or silently. :func:`fetch` is that one-time,
explicitly-invoked utility: it downloads a real CelesTrak CSV to a local
cache and returns its path (a no-op, cache-hit return if already fetched
and ``force`` isn't set). It is NEVER called automatically by
:func:`resolve` or anything else in this module -- the only caller is
``gui.startup_fetch_dialog``'s consent-gated startup prompt (see that
module's own docstring), which calls it ONLY after the user clicks
"Fetch now" in a dialog asking first. Once fetched, the result is an
ordinary local file -- point ``local_file_path`` at it (the GUI's
Propagation Setup dialog pre-fills the most recently fetched path as a
convenience) to use it, same as any other user-supplied CSV; no further
network access happens. You can also always download a CelesTrak CSV
(``https://celestrak.org/SpaceData/SW-All.csv`` or ``SW-Last5Years.csv``)
yourself, OUTSIDE this app, at any time, and point ``local_file_path`` at
it directly -- the loader accepts that exact format unmodified (see
"Format note" below).

No Basilisk import in this module -- it is pure standard library + numpy,
fully unit-testable without a Basilisk build (see ``tests/test_spaceweather.py``).

Format note (verified against this checkout's own
``spaceWeatherData.cpp``): the loader parses its CSV by column name,
requiring ``DATE, AP1..AP8, AP_AVG, F10.7_OBS, F10.7_OBS_CENTER81``.
:func:`resolve` writes the run's days in exactly those columns from the
real file (CelesTrak ``.txt`` or ``.csv``; :func:`load_celestrak`).

Solar activity percentile
-------------------------
Past the observations, every day comes from NASA MSFC's prediction at
one of its published percentiles: 95th for a conservative case (ESA
AD10 Sec. 5.9, operations budgets), 50th nominal (AD10, end of life),
5th low. A conservative run is thus the predicted solar cycle at its
95th percentile, not a constant: the cycle's timing still matters.
Schema v3's "conservative" mode, which held F10.7/Ap constant at a
percentile of the historical record, was removed (user requirement: the
conservative case follows ESA's guideline).
"""

from __future__ import annotations

import csv
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

REQUIRED_COLUMNS = (
    "DATE", "AP1", "AP2", "AP3", "AP4", "AP5", "AP6", "AP7", "AP8",
    "AP_AVG", "F10.7_OBS", "F10.7_OBS_CENTER81",
)

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "SpaceMissionStudio" / "spaceweather"

# The two real CelesTrak CSV endpoints :func:`fetch` can download --
# SW-Last5Years (smaller, usually enough to cover a scenario's own date
# range) and SW-All (the full historical record since 1957).
CELESTRAK_URLS = {
    "SW-Last5Years": "https://celestrak.org/SpaceData/SW-Last5Years.csv",
    "SW-All": "https://celestrak.org/SpaceData/SW-All.csv",
}

# A real user report (on a different, bare-urlopen fetch this project
# shares the same pattern with -- see gui.vizard_launcher's own
# _USER_AGENT comment) found urllib's own default User-Agent
# ("Python-urllib/<version>") gets blocked by basic bot-protection on
# hosts that have no issue with the exact same public file downloaded by
# an ordinary browser -- a well-known, standard workaround, not an
# attempt to bypass any real access control on a file CelesTrak already
# publishes for anyone to download.
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# [bytes] CelesTrak's own CSVs are a few MB at most -- cap well above
# that so a legitimate download never trips this, but refuse to buffer an
# unbounded response into memory.
_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024

# Real data shipped with the app: CelesTrak's SW-All (observed since 1957,
# a 45-day daily forecast, NOAA's monthly F10.7 forecast) -- see
# data/spaceweather/README.md for its source and date.
BUNDLED_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "spaceweather" / "SW-All.txt"
# NASA MSFC's solar-cycle prediction (13-month smoothed F10.7 and Ap at the
# 95th/50th/5th percentiles), the source ESA's AD10 guideline
# (EOP-FM/2024-07-177 v3.0, Sec. 5.9) prescribes for future solar activity.
MSFC_BUNDLED_PATH = BUNDLED_DATA_PATH.parent / "oct2026f10-prd.txt"
MSFC_PERCENTILES = (95.0, 50.0, 5.0)  # [%] the columns MSFC publishes, in file order
_MSFC_REPEAT_MONTHS = 132  # AD10 Sec. 5.9: past the file's end, its last 132 months repeat
_PAD_DAYS = 10  # [day] around a run: MSIS reads the previous days' Ap and F10.7

class SpaceWeatherError(Exception):
    """Raised on an unresolvable space-weather request (bad source name,
    local file missing/invalid with no fallback available, etc.) -- never
    a silent empty/garbage file.
    """


@dataclass
class ValidationResult:
    ok: bool
    covers_range: bool
    missing_columns: list
    duplicate_dates: list
    unsorted: bool
    first_date: Optional[str]
    last_date: Optional[str]
    message: str


@dataclass
class ResolvedSpaceWeather:
    path: Path  # the CSV handed to Basilisk
    data_file: Path  # the real data it was built from
    warnings: list = field(default_factory=list)


def validate_file(path, start_utc: datetime, end_utc: datetime) -> ValidationResult:
    """Pre-flight-check a space-weather CSV against exactly what
    ``spaceWeatherData.cpp``'s ``loadSpaceWeatherFile()`` itself requires
    (required columns present by name, ``DATE`` rows unique and sorted
    ascending -- mirroring that C++ loader's own validation so this tool
    can raise a friendly, specific error BEFORE handing the file to
    Basilisk) plus a range check.
    """
    path = Path(path)
    if not path.exists():
        return ValidationResult(False, False, list(REQUIRED_COLUMNS), [], False, None, None,
                                 f"{path} does not exist")

    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        date_idx = header.index("DATE") if "DATE" in header else None

        dates = []
        duplicates = []
        unsorted = False
        seen = set()
        prev = None
        if date_idx is not None:
            for row in reader:
                if not row or date_idx >= len(row):
                    continue
                d = row[date_idx].strip()
                if not d:
                    continue
                dates.append(d)
                if d in seen:
                    duplicates.append(d)
                seen.add(d)
                if prev is not None and d < prev:
                    unsorted = True
                prev = d

    first_date, last_date = (dates[0], dates[-1]) if dates else (None, None)

    covers_range = False
    if first_date and last_date:
        try:
            # Compare calendar dates, not full datetimes: each DATE row is
            # daily-resolution data covering its ENTIRE day, but
            # start_utc/end_utc can carry a non-zero time-of-day (e.g.
            # scenario.epoch_utc="...T14:00:00" -- Scenario.validate()
            # only requires it to parse as ISO 8601, not to be midnight).
            # Comparing full datetimes made a file whose last row is the
            # scenario's own end date fail this check whenever end_utc's
            # time-of-day was after midnight, even though that day's data
            # is genuinely present -- see this module's docstring/audit
            # note.
            covers_range = (
                datetime.strptime(first_date, "%Y-%m-%d").date() <= start_utc.date()
                and datetime.strptime(last_date, "%Y-%m-%d").date() >= end_utc.date()
            )
        except ValueError:
            covers_range = False

    ok = not missing and not duplicates and not unsorted and covers_range
    reasons = []
    if missing:
        reasons.append(f"missing required column(s): {missing}")
    if duplicates:
        reasons.append(f"{len(duplicates)} duplicate DATE row(s)")
    if unsorted:
        reasons.append("DATE rows are not sorted ascending")
    if not covers_range:
        reasons.append(f"file covers {first_date}..{last_date}, scenario needs "
                        f"{start_utc.date()}..{end_utc.date()}")

    return ValidationResult(ok, covers_range, missing, duplicates, unsorted, first_date, last_date,
                             "OK" if ok else "; ".join(reasons))


def fetch(dataset: str = "SW-All", cache_dir: Optional[Path] = None, force: bool = False,
          timeout_s: float = 30.0) -> Path:
    """Download a CelesTrak space-weather CSV to a local cache and return
    its path. Raises :class:`SpaceWeatherError` (never returns a partial/
    corrupt file) on any network/HTTP failure OR a local disk failure
    (can't create the cache directory, can't write the file -- e.g. a
    full or read-only disk) -- a single reporting path for every way this
    can fail, not something the caller needs its own raw-``OSError``
    handling for.

    **Never called automatically** -- see this module's own "Closed-off/
    offline policy" docstring. The only caller in this app is
    ``gui.startup_fetch_dialog``'s consent-gated startup prompt, invoked
    only after the user explicitly agrees to it. Calling this directly
    (e.g. from a script) is the user's own equivalent explicit choice.

    A no-op, cache-hit return (no network at all) if ``dest`` already
    exists and ``force`` is left ``False`` -- repeated calls (e.g. one per
    app startup, if the user agrees each time) don't re-download unless
    the user specifically asked to refresh.
    """
    if dataset not in CELESTRAK_URLS:
        raise SpaceWeatherError(f"unknown CelesTrak dataset {dataset!r}, expected one of {list(CELESTRAK_URLS)}")

    cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SpaceWeatherError(f"could not create cache directory {cache_dir}: {exc}") from exc
    dest = cache_dir / f"{dataset}.csv"
    if dest.exists() and not force:
        return dest

    url = CELESTRAK_URLS[dataset]
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})  # noqa: S310 -- constant https URL
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 -- constant https URL
            # Read one byte past the cap rather than response.read() with no
            # bound: an unbounded read would buffer however much data the
            # server sends (or never sends, tying up memory/the connection)
            # before the timeout/error handling below ever gets a chance to
            # apply -- see _MAX_DOWNLOAD_BYTES.
            data = response.read(_MAX_DOWNLOAD_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SpaceWeatherError(f"could not fetch {url}: {exc}") from exc

    if len(data) > _MAX_DOWNLOAD_BYTES:
        raise SpaceWeatherError(
            f"{url} response exceeded {_MAX_DOWNLOAD_BYTES} bytes -- refusing to buffer an unbounded download"
        )

    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        tmp.write_bytes(data)
        tmp.replace(dest)  # atomic-ish: never leave a half-written file at `dest`
    except OSError as exc:
        # A disk-full/permission failure here is just as much a "this
        # fetch did not succeed" case as a network failure above -- same
        # single SpaceWeatherError reporting path, not a raw OSError the
        # caller (gui.startup_fetch_dialog's worker, in practice) would
        # need its own special handling for.
        raise SpaceWeatherError(f"could not write {dest}: {exc}") from exc
    return dest


def cached_fetch_path(dataset: str = "SW-All", cache_dir: Optional[Path] = None) -> Optional[Path]:
    """Returns the path :func:`fetch` would already have written for
    ``dataset``, if it's actually there -- a pure, no-network check so
    GUI code (e.g. pre-filling the Propagation Setup dialog's local-file
    field with the most recently startup-fetched CSV) can offer it
    without triggering a fetch of its own.
    """
    cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    path = cache_dir / f"{dataset}.csv"
    return path if path.exists() else None


@dataclass
class _DailyRecord:
    ap: tuple  # eight 3-hour Ap values
    ap_avg: float
    f107_obs: float  # [sfu] observed (not 1-AU adjusted), as MSIS wants
    f107_center81: float  # [sfu] observed, 81-day centred average
    kind: str  # "observed", "daily_forecast" or "monthly_forecast"


@dataclass
class CelestrakData:
    """A parsed CelesTrak space-weather file, one record per day."""

    path: Path
    updated: str  # the file's own "UPDATED" stamp, or ""
    days: dict  # datetime.date -> _DailyRecord
    long_term_ap: float  # mean daily Ap over every observed day

    @property
    def first_date(self):
        return min(self.days)

    @property
    def last_date(self):
        return max(self.days)

    def kinds_between(self, start, end) -> set:
        return {rec.kind for day, rec in self.days.items() if start <= day <= end}


# CSSI text format, FORMAT(I4,I3,I3,I5,I3,8I3,I4,8I4,I4,F4.1,I2,I4,F6.1,I2,5F6.1)
# (https://celestrak.org/SpaceData/SpaceWx-format.php): column slices.
_TXT_AP = [(46 + 4 * k, 50 + 4 * k) for k in range(8)]
_TXT_AP_AVG = (78, 82)
_TXT_F107_OBS = (112, 118)
_TXT_CTR81_OBS = (118, 124)


def _number(text: str) -> Optional[float]:
    try:
        return float(text)
    except ValueError:
        return None


def _parse_txt(path: Path):
    """(updated, daily rows, monthly rows) from a CSSI ``.txt`` file."""
    daily, monthly, updated, section = [], [], "", None
    with open(path) as f:
        for line in f:
            if line.startswith("UPDATED"):
                updated = line[len("UPDATED"):].strip()
            elif line.startswith("BEGIN "):
                section = line.split()[1]
            elif line.startswith("END "):
                section = None
            elif section and line[:4].strip().isdigit():
                day = datetime(int(line[0:4]), int(line[4:7]), int(line[7:10])).date()
                f107 = _number(line[slice(*_TXT_F107_OBS)])
                center81 = _number(line[slice(*_TXT_CTR81_OBS)])
                if section == "MONTHLY_PREDICTED":
                    monthly.append((day, f107, center81))
                    continue
                aps = [_number(line[slice(*cols)]) for cols in _TXT_AP]
                ap_avg = _number(line[slice(*_TXT_AP_AVG)])
                kind = "observed" if section == "OBSERVED" else "daily_forecast"
                daily.append((day, aps, ap_avg, f107, center81, kind))
    return updated, daily, monthly


def _parse_csv(path: Path):
    """(updated, daily rows, monthly rows) from a CelesTrak ``.csv`` file
    (``F10.7_DATA_TYPE`` OBS/INT, PRD, PRM) or any CSV with the columns
    Basilisk's loader reads (taken as observed)."""
    daily, monthly = [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in ("DATE", "AP_AVG", "F10.7_OBS", "F10.7_OBS_CENTER81")
                   if c not in (reader.fieldnames or [])]
        if missing:
            raise SpaceWeatherError(f"{path} is missing column(s) {missing}")
        for row in reader:
            try:
                day = datetime.strptime(row["DATE"].strip(), "%Y-%m-%d").date()
            except (ValueError, AttributeError):
                continue
            f107, center81 = _number(row["F10.7_OBS"] or ""), _number(row["F10.7_OBS_CENTER81"] or "")
            data_type = (row.get("F10.7_DATA_TYPE") or "OBS").strip().upper()
            if data_type == "PRM":
                monthly.append((day, f107, center81))
                continue
            aps = [_number(row.get(f"AP{k}") or "") for k in range(1, 9)]
            kind = "daily_forecast" if data_type == "PRD" else "observed"
            daily.append((day, aps, _number(row["AP_AVG"] or ""), f107, center81, kind))
    return "", daily, monthly


_LOADED: dict = {}  # (path, mtime) -> CelestrakData


def load_celestrak(path) -> CelestrakData:
    """Parse a real CelesTrak space-weather file (``.txt`` CSSI format or
    ``.csv``) into daily records. NOAA's monthly F10.7 forecast covers
    every day of its month as published; it has no Ap, so Ap there is
    held at the mean of every observed day in the file -- one fixed
    number from the real record, nothing generated. (MSFC's prediction,
    with its own Ap, takes over wherever it reaches: :func:`_span_days`.)"""
    path = Path(path)
    if not path.exists():
        raise SpaceWeatherError(f"{path} does not exist")
    key = (str(path.resolve()), path.stat().st_mtime)
    if key in _LOADED:
        return _LOADED[key]
    parse = _parse_txt if path.suffix.lower() == ".txt" else _parse_csv
    updated, daily, monthly = parse(path)
    observed_ap = [ap_avg for _, _, ap_avg, _, _, kind in daily if kind == "observed" and ap_avg is not None]
    if not observed_ap:
        raise SpaceWeatherError(f"{path} has no observed Ap values")
    long_term_ap = float(np.mean(observed_ap))
    days: dict = {}
    for day, aps, ap_avg, f107, center81, kind in daily:
        if None in (ap_avg, f107, center81) or None in aps:
            continue  # an incomplete row (e.g. today's, still being observed)
        days[day] = _DailyRecord(tuple(aps), ap_avg, f107, center81, kind)
    for month_start, f107, center81 in monthly:
        if f107 is None or center81 is None:
            continue
        day = month_start
        while day.month == month_start.month:
            if day not in days:
                days[day] = _DailyRecord((long_term_ap,) * 8, long_term_ap, f107, center81, "monthly_forecast")
            day += timedelta(days=1)
    if not days:
        raise SpaceWeatherError(f"{path} has no usable space-weather rows")
    data = CelestrakData(path, updated, days, long_term_ap)
    _LOADED[key] = data
    return data


_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


@dataclass
class MsfcForecast:
    """MSFC's monthly prediction: per month, F10.7 [sfu] and Ap at each of
    :data:`MSFC_PERCENTILES`."""

    path: Path
    months: dict  # date(year, month, 1) -> (f107 tuple, ap tuple), in MSFC_PERCENTILES order

    @property
    def first_month(self):
        return min(self.months)

    @property
    def last_month(self):
        return max(self.months)

    def values(self, month, percentile: float):
        """(F10.7, Ap, repeated) for ``month`` (the first of a month). Past
        the file's end the last 132 months repeat cyclically (AD10 Sec.
        5.9); ``repeated`` says so. None before the file starts."""
        if month < self.first_month:
            return None
        column = MSFC_PERCENTILES.index(float(percentile))
        repeated = False
        last = self.last_month
        if month > last:
            behind = (month.year - last.year) * 12 + month.month - last.month  # [month] past the end
            back = _MSFC_REPEAT_MONTHS - (behind - 1) % _MSFC_REPEAT_MONTHS  # into the last 132 months
            index = last.year * 12 + last.month - 1 - back + 1
            month = date(index // 12, index % 12 + 1, 1)
            repeated = True
        f107, ap = self.months[month]
        return f107[column], ap[column], repeated


def load_msfc(path) -> MsfcForecast:
    """Parse an MSFC prediction table ("TABLE 3 ESTIMATES OF 13-MONTH
    SMOOTH SOLAR ACTIVITY ..."): rows of decimal year, month, then F10.7
    and Ap at the 95.0/50/5.0 percentiles."""
    path = Path(path)
    if not path.exists():
        raise SpaceWeatherError(f"{path} does not exist")
    months = {}
    with open(path) as f:
        for line in f:
            fields = line.split()
            if len(fields) != 8 or fields[1] not in _MONTHS:
                continue
            try:
                year = int(float(fields[0]) + 1e-6)
                numbers = [float(v) for v in fields[2:]]
            except ValueError:
                continue
            months[date(year, _MONTHS.index(fields[1]) + 1, 1)] = (tuple(numbers[:3]), tuple(numbers[3:]))
    if len(months) < _MSFC_REPEAT_MONTHS:
        raise SpaceWeatherError(f"{path} has {len(months)} monthly rows; an MSFC prediction table needs at least "
                                f"{_MSFC_REPEAT_MONTHS} (one solar cycle)")
    return MsfcForecast(path, months)


def real_data_path(source: str, local_file_path: Optional[str] = None, cache_dir: Optional[Path] = None) -> Path:
    """The real data file a ``source`` uses: the user's own file, or for
    ``"bundled"`` the newer of the file shipped with the app and one the
    startup prompt downloaded (newer = later last observed day)."""
    if source == "local_file":
        if not local_file_path:
            raise SpaceWeatherError("space_weather.source is 'local_file' but local_file_path was not set")
        return Path(local_file_path)
    if source != "bundled":
        raise SpaceWeatherError(f"unknown space_weather.source {source!r}")
    best, best_last = BUNDLED_DATA_PATH, None
    for candidate in (BUNDLED_DATA_PATH, cached_fetch_path("SW-All", cache_dir)):
        if candidate is None:
            continue
        try:
            data = load_celestrak(candidate)
        except SpaceWeatherError:
            continue
        last_observed = max((d for d, r in data.days.items() if r.kind == "observed"), default=None)
        if last_observed is not None and (best_last is None or last_observed > best_last):
            best, best_last = candidate, last_observed
    return best


def data_coverage(source: str, local_file_path: Optional[str] = None, cache_dir: Optional[Path] = None,
                  msfc_file_path: Optional[str] = None):
    """(first, last) calendar dates the real data covers; ``last`` is
    None when an MSFC prediction extends it without end (its last 132
    months repeat, AD10 Sec. 5.9)."""
    data = load_celestrak(real_data_path(source, local_file_path, cache_dir))
    msfc = _msfc_or_none(msfc_file_path)
    return data.first_date, None if msfc is not None else data.last_date


def _msfc_or_none(msfc_file_path: Optional[str]) -> Optional[MsfcForecast]:
    """The MSFC prediction: the user's file, else the shipped one."""
    if msfc_file_path:
        return load_msfc(msfc_file_path)
    return load_msfc(MSFC_BUNDLED_PATH) if MSFC_BUNDLED_PATH.exists() else None


def _span_days(data: "CelestrakData", msfc: Optional[MsfcForecast], percentile: float, first, last):
    """Day -> record over ``first``..``last``: observed days and the
    45-day forecast from CelesTrak first, then MSFC's prediction (at
    ``percentile``, 13-month smoothed F10.7 and Ap used for the day and
    its 81-day average alike), then NOAA's monthly forecast for any
    months MSFC does not cover. Raises on a day none of them covers."""
    days = {}
    day = first
    while day <= last:
        record = data.days.get(day)
        if record is None or record.kind == "monthly_forecast":
            values = msfc.values(day.replace(day=1), percentile) if msfc is not None else None
            if values is not None:
                f107, ap, repeated = values
                record = _DailyRecord((ap,) * 8, ap, f107, f107, "msfc_repeated" if repeated else "msfc_forecast")
        if record is None:
            raise SpaceWeatherError(f"no real space-weather data for {day}")
        days[day] = record
        day += timedelta(days=1)
    return days


def _write_basilisk_csv(days: dict, dest_path) -> Path:
    """``days`` (date -> record) in the columns Basilisk's loader reads."""
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(REQUIRED_COLUMNS)
        for day in sorted(days):
            rec = days[day]
            writer.writerow([day.strftime("%Y-%m-%d")] + [f"{v:g}" for v in rec.ap]
                            + [f"{rec.ap_avg:g}", f"{rec.f107_obs:g}", f"{rec.f107_center81:g}"])
    return dest_path


def _resolve_real(source: str, start_utc: datetime, end_utc: datetime, local_file_path: Optional[str],
                  cache_dir: Optional[Path], warnings: list, forecast_percentile: float = 50.0,
                  msfc_file_path: Optional[str] = None) -> "ResolvedSpaceWeather":
    if float(forecast_percentile) not in MSFC_PERCENTILES:
        raise SpaceWeatherError(f"forecast_percentile {forecast_percentile!r} must be one of {MSFC_PERCENTILES}")
    path = real_data_path(source, local_file_path, cache_dir)
    data = load_celestrak(path)
    msfc = _msfc_or_none(msfc_file_path)
    first = (start_utc - timedelta(days=_PAD_DAYS)).date()
    last = (end_utc + timedelta(days=_PAD_DAYS)).date()
    if first < data.first_date or (msfc is None and last > data.last_date):
        end = "" if msfc is not None else f"..{data.last_date}"
        raise SpaceWeatherError(
            f"the real space-weather data ({path.name}) covers {data.first_date}{end}; this run needs "
            f"{first}..{last} (incl. {_PAD_DAYS} days either side) -- move the epoch or shorten the run")
    days = _span_days(data, msfc, forecast_percentile, first, last)
    kinds = {rec.kind for day, rec in days.items() if start_utc.date() <= day <= end_utc.date()}
    stamp = f", updated {data.updated}" if data.updated else ""
    if "daily_forecast" in kinds:
        warnings.append(f"space weather includes CelesTrak's 45-day forecast ({path.name}{stamp})")
    if "monthly_forecast" in kinds:
        warnings.append(f"space weather uses NOAA's monthly F10.7 forecast ({path.name}{stamp}) where MSFC's "
                        f"prediction does not reach, with Ap held at the observed mean of {data.long_term_ap:.1f}")
    if kinds & {"msfc_forecast", "msfc_repeated"}:
        warnings.append(f"space weather uses MSFC's prediction ({msfc.path.name}), {forecast_percentile:g}th "
                        "percentile F10.7 and Ap")
    if "msfc_repeated" in kinds:
        warnings.append(f"past {msfc.last_month:%Y-%m} MSFC's last 132 months repeat (ESA AD10 Sec. 5.9)")
    cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    msfc_tag = f"_{msfc.path.stem}_{int(msfc.path.stat().st_mtime)}" if msfc is not None else ""
    dest = cache_dir / (f"real_{path.stem}_{int(path.stat().st_mtime)}{msfc_tag}_p{forecast_percentile:g}_"
                        f"{first:%Y%m%d}_{last:%Y%m%d}.csv")
    if not dest.exists():
        _write_basilisk_csv(days, dest)
    return ResolvedSpaceWeather(dest, path, warnings)


def resolve(source: str, start_utc: datetime, end_utc: datetime,
            local_file_path: Optional[str] = None, cache_dir: Optional[Path] = None,
            forecast_percentile: float = 50.0, msfc_file_path: Optional[str] = None) -> ResolvedSpaceWeather:
    """Resolve a ``SpaceWeatherConfig`` (see ``schema.scenario``) into a
    CSV Basilisk's ``spaceWeatherData.loadSpaceWeatherFile()`` loads.
    Real data only -- no network here (see this module's docstring):

    * ``source == "bundled"`` (the default): CelesTrak's file shipped
      with the app, or a newer one the startup prompt downloaded;
    * ``source == "local_file"``: the user's own CelesTrak file (``.txt``
      or ``.csv``) or CSV in Basilisk's columns.

    Days past the observations and CelesTrak's 45-day forecast come from
    MSFC's prediction (``msfc_file_path``, else the shipped one) at
    ``forecast_percentile`` (95 conservative, 50 nominal or 5 low; ESA
    AD10 Sec. 5.9: 95 for operations budgets, 50 for end of life),
    repeating its last 132 months past its end. A run outside the data is
    refused.
    """
    warnings: list = []
    return _resolve_real(source, start_utc, end_utc, local_file_path, cache_dir, warnings, forecast_percentile,
                         msfc_file_path)


def resolve_for(config, start_utc: datetime, end_utc: datetime,
                forecast_percentile: Optional[float] = None) -> ResolvedSpaceWeather:
    """:func:`resolve` for a ``schema.scenario.SpaceWeatherConfig``;
    ``forecast_percentile`` overrides the config's (e.g. 50 for an
    end-of-life estimate, AD10 Sec. 5.9)."""
    return resolve(config.source, start_utc, end_utc, local_file_path=config.local_file_path,
                   cache_dir=config.cache_dir, forecast_percentile=config.forecast_percentile if forecast_percentile is None
                   else forecast_percentile, msfc_file_path=config.msfc_file_path)
