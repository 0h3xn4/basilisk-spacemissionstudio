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

**Closed-off/offline policy**: SpaceMissionStudio never accesses the
network implicitly at runtime (real user requirement -- "the app must be
completely closed off and offline, only exception is the installation
process"). ``resolve()`` itself NEVER touches the network: ``source`` is
only ever ``"local_file"`` (a real file the user supplies) or
``"synthetic"`` (the default -- a solar-cycle-SHAPED, never a real
forecast, profile generated locally, no file or network needed).

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
``spaceWeatherData.cpp``, not assumed): the loader parses its input CSV by
**column name** from the header row, requiring only
``DATE, AP1..AP8, AP_AVG, F10.7_OBS, F10.7_OBS_CENTER81`` to be present --
extra columns are ignored. A real CelesTrak ``SW-All.csv``/
``SW-Last5Years.csv`` download has those exact column names (plus many
more Basilisk doesn't need), so it can be handed to
``spaceWeatherData.loadSpaceWeatherFile()`` completely unmodified: no
reformatting step exists or is needed in this module.

Conservative ("worst-case") drag margin
----------------------------------------
Real user request: a "95th percentile / +2 sigma" atmospheric-drag margin
for conservative mission-design analysis. There is no such thing built
into Basilisk's ``msisAtmosphere``/``spaceWeatherData`` -- they just
consume whatever daily F10.7/Ap values a CSV gives them -- and this
project has no authoritative source for a specific fixed "worst-case"
F10.7/Ap constant to hand-code (deliberately NOT guessed; see
``AGENTS.md``'s "never guess about Basilisk's API" spirit extended here
to "never guess a specific physical constant either"). Real user
decision: derive it statistically instead, from REAL historical F10.7/Ap
records (never the synthetic generator, which is a fabricated profile,
not observed history; see :func:`compute_worst_case_activity`/
:func:`resolve`'s own docstrings for the refusal that enforces this).
Since the offline policy above removed this module's own ability to pull
that real historical record in automatically, "conservative" mode is now
``source == "local_file"``-only: supply your own real historical CSV
(e.g. a CelesTrak extract downloaded ahead of time, outside this app) via
``local_file_path``.

The result -- :func:`generate_worst_case` -- is a CSV holding F10.7/Ap
CONSTANT at the computed percentile across the whole scenario, not a
single elevated day: the standard way this kind of margin is actually
used in mission design is "assume sustained worst-case activity could
happen at any point in the mission," not "the worst single day in
history, once." ``activity_percentile`` is a plain float (default 95.0,
matching the user's own primary phrasing), not a fixed "P95" concept, so
a user who actually meant mean+2 sigma (~97.7th percentile under a
normal-ish distribution) can dial it there directly -- this module never
silently picks one interpretation over the other.
"""

from __future__ import annotations

import csv
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
# range) and SW-All (the full historical record since 1957, needed for a
# meaningful "conservative" worst-case percentile -- see
# :func:`compute_worst_case_activity`).
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

# Synthetic fallback: an ~11-year solar-cycle envelope with correlated
# day-to-day noise and occasional storm episodes -- shaped like real solar
# activity, NOT a forecast. Ported from
# ../missionAnalysis/generate_space_weather_placeholder.py, generalized to
# take an arbitrary date range instead of reading missionAnalysis's own
# mission_config.py.
#
# The envelope follows the calendar: cycle 25's minimum (December 2019) and
# smoothed maximum (about October 2024), repeated every 11 years, with the
# usual lopsided shape (a faster rise than decline). It used to start every
# run 2 years before a maximum whatever its date, so a 2030-2035 mission --
# really the quiet end of cycle 25 -- saw near-maximum drag.
_PAD_DAYS = 10
_F107_SOLAR_MIN = 70.0  # [sfu]
_F107_SOLAR_MAX = 150.0  # [sfu]
_CYCLE_PERIOD_DAYS = 11.0 * 365.25  # [day]
_CYCLE_MINIMUM = datetime(2019, 12, 1)  # cycle 25 began
_CYCLE_RISE_FRACTION = 0.44  # [-] minimum -> maximum (Oct 2024) as a fraction of the cycle
_SYNTHETIC_VERSION = 2  # bump when the profile changes, so cached files are not reused


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
    path: Path
    is_synthetic: bool
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
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
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


def _f107_base(dates) -> np.ndarray:
    """Smooth F10.7 [sfu] on each date: a cosine rise from the cycle's
    minimum to its maximum, then a slower cosine decline to the next
    minimum."""
    days = np.array([(d - _CYCLE_MINIMUM).total_seconds() / 86400.0 for d in dates])  # [day]
    phase = np.mod(days, _CYCLE_PERIOD_DAYS) / _CYCLE_PERIOD_DAYS  # [-] 0 at minimum
    rise = _CYCLE_RISE_FRACTION
    level = np.where(phase < rise, 0.5 * (1.0 - np.cos(np.pi * phase / rise)),
                     0.5 * (1.0 + np.cos(np.pi * (phase - rise) / (1.0 - rise))))  # [-] 0 min, 1 max
    return _F107_SOLAR_MIN + (_F107_SOLAR_MAX - _F107_SOLAR_MIN) * level


def generate_synthetic(start_utc: datetime, end_utc: datetime, dest_path, seed: int = 42) -> Path:
    """Write a synthetic, solar-cycle-shaped (NOT a real forecast)
    space-weather CSV covering ``[start_utc, end_utc]`` (plus padding) to
    ``dest_path``, in the exact column layout :func:`validate_file`/
    Basilisk's loader expect. Deterministic given the same inputs (fixed
    default seed) so repeated runs of the same scenario are reproducible.
    """
    rng = np.random.default_rng(seed)

    start = start_utc - timedelta(days=_PAD_DAYS)
    end = end_utc + timedelta(days=_PAD_DAYS)
    n_days = (end - start).days + 1
    dates = [start + timedelta(days=i) for i in range(n_days)]
    naive = [d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d for d in dates]
    f107_base = _f107_base(naive)
    noise = np.zeros(n_days)
    for i in range(1, n_days):
        noise[i] = 0.85 * noise[i - 1] + rng.normal(0.0, 3.0)
    f107_obs = np.clip(f107_base + noise, 65.0, 300.0)

    f107_center81 = np.array([
        f107_obs[max(0, i - 40): min(n_days, i + 41)].mean() for i in range(n_days)
    ])

    ap_avg = np.zeros(n_days)
    storm_prob = 0.02 + 0.03 * (f107_base - _F107_SOLAR_MIN) / (_F107_SOLAR_MAX - _F107_SOLAR_MIN)
    day = 0
    while day < n_days:
        if rng.random() < storm_prob[day]:
            duration = rng.integers(1, 4)
            peak = rng.uniform(30.0, 110.0)
            for k in range(duration):
                if day + k < n_days:
                    ap_avg[day + k] = max(ap_avg[day + k], peak * (0.6 ** k))
            day += duration
        else:
            ap_avg[day] = rng.uniform(3.0, 12.0)
            day += 1

    ap_3hr = np.clip(ap_avg[:, None] + rng.normal(0.0, 2.0, size=(n_days, 8)), 0.0, None)

    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["DATE", "AP1", "AP2", "AP3", "AP4", "AP5", "AP6", "AP7", "AP8",
                          "AP_AVG", "F10.7_OBS", "F10.7_OBS_CENTER81"])
        for i, d in enumerate(dates):
            writer.writerow(
                [d.strftime("%Y-%m-%d")]
                + [f"{v:.1f}" for v in ap_3hr[i]]
                + [f"{ap_avg[i]:.1f}", f"{f107_obs[i]:.1f}", f"{f107_center81[i]:.1f}"]
            )
    return dest_path


def _synthetic_cache_path(cache_dir: Optional[Path], start_utc: datetime, end_utc: datetime) -> Path:
    cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    name = f"synthetic_v{_SYNTHETIC_VERSION}_{start_utc:%Y%m%d}_{end_utc:%Y%m%d}.csv"
    return cache_dir / name


# A percentile computed from less than a year of history isn't a
# meaningful "worst case" -- day-to-day/seasonal noise would dominate
# over genuine solar-cycle variability. Not a Basilisk requirement, a
# plain statistical sanity floor for this module's own computation.
_MIN_HISTORICAL_DAYS = 365


def _load_historical_activity(path) -> "tuple[np.ndarray, np.ndarray]":
    """Read ``F10.7_OBS``/``AP_AVG`` as float arrays from a real
    space-weather CSV (CelesTrak's own format, or a user-provided file in
    the same layout) -- rows that fail to parse are skipped, not fatal
    (real CelesTrak extracts have occasional blank/placeholder cells for
    not-yet-observed recent days).
    """
    path = Path(path)
    if not path.exists():
        raise SpaceWeatherError(f"{path} does not exist")

    f107_values: list = []
    ap_values: list = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in ("F10.7_OBS", "AP_AVG") if c not in (reader.fieldnames or [])]
        if missing:
            raise SpaceWeatherError(f"{path} is missing required column(s) {missing} for a historical-activity "
                                     f"percentile computation")
        for row in reader:
            try:
                f107_values.append(float(row["F10.7_OBS"]))
                ap_values.append(float(row["AP_AVG"]))
            except (TypeError, ValueError):
                continue  # blank/placeholder cell -- skip, not fatal

    return np.array(f107_values), np.array(ap_values)


def compute_worst_case_activity(path, percentile: float) -> "tuple[float, float, int]":
    """Return ``(f107_percentile, ap_percentile, n_samples)`` -- the
    requested percentile of ``F10.7_OBS``/``AP_AVG`` across every usable
    row in the REAL historical space-weather CSV at ``path``. Raises
    :class:`SpaceWeatherError` if there isn't enough real history to make
    that a meaningful "worst case" figure (see :data:`_MIN_HISTORICAL_DAYS`)
    -- never silently computes a percentile from a handful of days.
    """
    f107, ap = _load_historical_activity(path)
    if len(f107) < _MIN_HISTORICAL_DAYS:
        raise SpaceWeatherError(
            f"{path} has only {len(f107)} usable day(s) of real F10.7/Ap history -- need at least "
            f"{_MIN_HISTORICAL_DAYS} for a {percentile:.0f}th-percentile 'worst case' figure to be "
            "statistically meaningful (rather than dominated by short-term noise). Use a longer historical "
            "record (CelesTrak's SW-All.csv is the full record since 1957), or set "
            "space_weather.activity_level back to 'nominal'."
        )
    return float(np.percentile(f107, percentile)), float(np.percentile(ap, percentile)), len(f107)


def generate_worst_case(f107_percentile: float, ap_percentile: float, start_utc: datetime, end_utc: datetime,
                         dest_path) -> Path:
    """Write a space-weather CSV holding F10.7/Ap CONSTANT at
    ``f107_percentile``/``ap_percentile`` across ``[start_utc, end_utc]``
    (plus the same padding :func:`generate_synthetic` uses) -- a sustained
    "worst case could happen at any point in the mission" assumption, per
    :func:`compute_worst_case_activity`'s own docstring. AP1..AP8 (the
    eight 3-hour sub-values Basilisk's loader also requires) and
    F10.7_OBS_CENTER81 (the 81-day centered average) are set equal to the
    same percentile values -- consistent with "sustained," not a
    single-day spike riding on an otherwise-nominal 81-day average.
    """
    start = start_utc - timedelta(days=_PAD_DAYS)
    end = end_utc + timedelta(days=_PAD_DAYS)
    n_days = (end - start).days + 1
    dates = [start + timedelta(days=i) for i in range(n_days)]

    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["DATE", "AP1", "AP2", "AP3", "AP4", "AP5", "AP6", "AP7", "AP8",
                          "AP_AVG", "F10.7_OBS", "F10.7_OBS_CENTER81"])
        for d in dates:
            writer.writerow(
                [d.strftime("%Y-%m-%d")]
                + [f"{ap_percentile:.1f}"] * 8
                + [f"{ap_percentile:.1f}", f"{f107_percentile:.1f}", f"{f107_percentile:.1f}"]
            )
    return dest_path


def _worst_case_cache_path(cache_dir: Optional[Path], start_utc: datetime, end_utc: datetime,
                            percentile: float) -> Path:
    cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    name = f"worstcase_p{percentile:g}_{start_utc:%Y%m%d}_{end_utc:%Y%m%d}.csv"
    return cache_dir / name


def _resolve_conservative(source: str, start_utc: datetime, end_utc: datetime,
                           local_file_path: Optional[str], cache_dir: Optional[Path],
                           activity_percentile: float, warnings: list) -> ResolvedSpaceWeather:
    """The ``activity_level == "conservative"`` branch of :func:`resolve` --
    see that function's own docstring. Split out only for readability; not
    meant to be called directly.
    """
    if source == "local_file":
        if not local_file_path:
            raise SpaceWeatherError("space_weather.source is 'local_file' but local_file_path was not set")
        historical_path = Path(local_file_path)
    elif source == "synthetic":
        raise SpaceWeatherError(
            "space_weather.activity_level='conservative' needs REAL historical F10.7/Ap data to compute a "
            "percentile from -- source='synthetic' has none (it's a fabricated solar-cycle-shaped profile, "
            "not observed history). Set source to 'local_file', or activity_level back to 'nominal'."
        )
    else:
        raise SpaceWeatherError(f"unknown space_weather.source {source!r}")

    f107_p, ap_p, n_samples = compute_worst_case_activity(historical_path, activity_percentile)
    path = _worst_case_cache_path(cache_dir, start_utc, end_utc, activity_percentile)
    generate_worst_case(f107_p, ap_p, start_utc, end_utc, path)
    warnings.append(
        f"space weather is a CONSERVATIVE, sustained-worst-case profile: F10.7={f107_p:.1f} sfu, "
        f"Ap={ap_p:.1f}, the {activity_percentile:.0f}th percentile of {n_samples} day(s) of REAL "
        f"historical data from {historical_path.name}, held CONSTANT across the whole scenario duration -- "
        "NOT real observed/forecast data for these specific dates, and by construction higher than almost "
        "all actual days in that historical record."
    )
    return ResolvedSpaceWeather(path, True, warnings)


def resolve(source: str, start_utc: datetime, end_utc: datetime,
            local_file_path: Optional[str] = None, cache_dir: Optional[Path] = None,
            activity_level: str = "nominal", activity_percentile: float = 95.0) -> ResolvedSpaceWeather:
    """Top-level entry point -- resolves a ``SpaceWeatherConfig`` (see
    ``schema.scenario``) into an actual, validated CSV path Basilisk's
    ``spaceWeatherData.loadSpaceWeatherFile()`` can load.

    ``activity_level == "nominal"`` (the default) supports exactly two
    sources (see this module's own "Closed-off/offline policy" docstring
    -- there is no network fetch here or anywhere else in this module):

    * ``source == "local_file"``: use exactly that file; error if missing
      or invalid (no silent fallback -- the user asked for this file).
    * ``source == "synthetic"`` (the default): generate the synthetic
      profile directly -- always available, no file, no network.

    Any other ``source`` value raises :class:`SpaceWeatherError`.

    ``activity_level == "conservative"`` (see this module's own docstring,
    "Conservative ('worst-case') drag margin") instead computes the
    ``activity_percentile``-th percentile of REAL historical F10.7/Ap data
    and returns a CSV holding that value constant across the scenario.
    ``source`` must be ``"local_file"`` for this -- ``source ==
    "synthetic"`` is refused outright here: a percentile computed from a
    fabricated profile is not a real historical "worst case", whatever
    the number comes out to.
    """
    warnings: list = []

    if activity_level not in ("nominal", "conservative"):
        raise SpaceWeatherError(f"unknown space_weather.activity_level {activity_level!r}")

    if activity_level == "conservative":
        return _resolve_conservative(source, start_utc, end_utc, local_file_path, cache_dir,
                                      activity_percentile, warnings)

    if source == "local_file":
        if not local_file_path:
            raise SpaceWeatherError("space_weather.source is 'local_file' but local_file_path was not set")
        result = validate_file(local_file_path, start_utc, end_utc)
        if not result.ok:
            raise SpaceWeatherError(f"{local_file_path} failed validation: {result.message}")
        return ResolvedSpaceWeather(Path(local_file_path), False, warnings)

    if source == "synthetic":
        path = _synthetic_cache_path(cache_dir, start_utc, end_utc)
        generate_synthetic(start_utc, end_utc, path)
        warnings.append("space weather is SYNTHETIC (not real observed/forecast data) -- explicitly requested.")
        return ResolvedSpaceWeather(path, True, warnings)

    raise SpaceWeatherError(f"unknown space_weather.source {source!r}")
