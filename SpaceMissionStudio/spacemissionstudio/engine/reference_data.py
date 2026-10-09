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
"""Every reference data file the tool uses, with its source, dates and
checksum (UX/UI guidelines: "the model panel shows each file's version,
date and source"; "a warning when data is out of date").

:func:`inventory` only reads local files; nothing here touches the
network. Downloads stay in their modules (:mod:`.kernels`,
:mod:`.spaceweather`, :mod:`.earth_orientation`), started by the user.
:data:`DOWNLOADS` names what each download fetches, from where and about
how much, so a consent prompt can say so before anything is fetched.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

SPACE_WEATHER_STALE_DAYS = 60  # [day] observed data older than this is flagged


@dataclass
class ReferenceFile:
    kind: str  # "SPICE kernel", "gravity field", "magnetic model", "Earth orientation", ...
    name: str
    status: str  # "ok", "missing", "out of date"
    source: str = ""
    path: str = ""
    size_bytes: Optional[int] = None
    sha256: str = ""
    installed_utc: str = ""
    covers: str = ""  # the dates the data covers, where it has any
    note: str = ""


@dataclass
class Download:
    """What a consented download fetches: shown to the user before it starts."""

    key: str
    title: str
    source: str
    files: List[str] = field(default_factory=list)
    approx_size: str = ""


DOWNLOADS: Dict[str, Download] = {
    "support_data": Download(
        "support_data", "Support data (SPICE kernels, gravity field, magnetic model)",
        "NAIF (naif.jpl.nasa.gov) and the Basilisk repository (raw.githubusercontent.com/AVSLab)",
        ["naif0012.tls", "de430.bsp", "de-403-masses.tpc", "pck00010.tpc", "GGM03S.txt", "WMM2025.COF"],
        "about 116 MB, only the files that are missing"),
    "space_weather": Download(
        "space_weather", "Space weather (observed F10.7 and Ap, 45-day forecast)",
        "CelesTrak, https://celestrak.org/SpaceData/SW-All.csv", ["SW-All.csv"], "about 3 MB"),
    "earth_orientation": Download(
        "earth_orientation", "Earth orientation (IERS-based NAIF Earth PCKs)",
        "NAIF, https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/",
        ["earth_<dates>_combined.bpc", "earth_latest_high_prec.bpc", "their comment files"], "about 36 MB"),
}


def _sha256(path: Path, limit_bytes: int = 32 * 1024 * 1024) -> str:
    """SHA-256 of a file up to ``limit_bytes`` (larger files: empty, as provenance does)."""
    try:
        if path.stat().st_size > limit_bytes:
            return ""
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _mtime_utc(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return ""


def _support_files() -> List[ReferenceFile]:
    try:
        from Basilisk.utilities.supportDataTools import dataFetcher

        from . import kernels
    except ImportError:
        return [ReferenceFile("support data", "SPICE kernels, gravity field, magnetic model", "missing",
                              note="Basilisk is not installed")]
    kinds = {"LocalGravData": "gravity field", "MagneticFieldData": "magnetic model"}
    files = []
    for kernel, status in zip(kernels.ALL_SUPPORT_DATA_FILES, kernels.cached_statuses()):
        rel = dataFetcher.relpath(kernel)
        kind = kinds.get(type(kernel).__name__, "SPICE kernel")
        source = dataFetcher.POOCH.get_url(rel)
        if not status.available:
            files.append(ReferenceFile(kind, kernel.value, "missing", source, note=status.error or ""))
            continue
        path = Path(status.path)
        files.append(ReferenceFile(kind, kernel.value, "ok", source, str(path), path.stat().st_size, _sha256(path),
                                   _mtime_utc(path),
                                   note="checksum checked" if dataFetcher.POOCH.registry.get(rel) else ""))
    return files


def _space_weather_files(today: date) -> List[ReferenceFile]:
    from . import spaceweather

    files = []
    record = spaceweather.installed_record()
    used = spaceweather.real_data_path("bundled")
    for path, source in ((spaceweather.BUNDLED_DATA_PATH, "bundled with SpaceMissionStudio (CelesTrak SW-All)"),
                         (Path(record["path"]) if record else None, record["source"] if record else "")):
        if path is None:
            continue
        try:
            data = spaceweather.load_celestrak(path)
        except spaceweather.SpaceWeatherError as exc:
            files.append(ReferenceFile("space weather", path.name, "missing", source, str(path), note=str(exc)))
            continue
        observed = max((d for d, r in data.days.items() if r.kind == "observed"), default=None)
        stale = observed is not None and (today - observed).days > SPACE_WEATHER_STALE_DAYS
        note = "in use" if Path(path) == Path(used) else "not in use (the other file is newer)"
        files.append(ReferenceFile(
            "space weather", path.name, "out of date" if stale and Path(path) == Path(used) else "ok", source,
            str(path), path.stat().st_size, (record or {}).get("sha256", "") if path != spaceweather.BUNDLED_DATA_PATH
            else _sha256(path), _mtime_utc(path), f"{data.first_date} to {data.last_date} (observed to {observed})",
            note + (f"; observed data end {observed}" if stale else "")))
    msfc = spaceweather.MSFC_BUNDLED_PATH
    files.append(ReferenceFile("solar-activity prediction", msfc.name, "ok" if msfc.exists() else "missing",
                               "bundled with SpaceMissionStudio (NASA MSFC, October 2026)", str(msfc),
                               msfc.stat().st_size if msfc.exists() else None, _sha256(msfc), _mtime_utc(msfc),
                               note="95th, 50th and 5th percentiles (ESA AD10 Sec. 5.9)"))
    return files


def _earth_orientation_files(now: datetime) -> List[ReferenceFile]:
    from . import earth_orientation

    kernels = earth_orientation.installed()
    if not kernels:
        return [ReferenceFile("Earth orientation", "IERS-based Earth PCKs", "missing", earth_orientation.NAIF_PCK_URL,
                              note="runs use IAU_EARTH (about 160 m/day of error at 400 km)")]
    files = []
    for kernel in kernels:
        until = kernel.high_accuracy_until
        stale = kernel.role == "high_precision" and until is not None and until < now
        files.append(ReferenceFile("Earth orientation", Path(kernel.path).name, "out of date" if stale else "ok",
                                   kernel.source, kernel.path, kernel.size_bytes, kernel.sha256, kernel.installed_utc,
                                   (f"high accuracy until {until:%Y-%m-%d}" if kernel.role == "high_precision"
                                    else f"1962-2126, measured to {kernel.last_datum_utc[:10] if kernel.last_datum_utc else '?'}"),
                                   kernel.role.replace("_", " ")))
    return files


def inventory(now: Optional[datetime] = None) -> List[ReferenceFile]:
    """Every reference data file, local reads only. Never raises: a part
    that cannot be read is listed as missing with the reason."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    files: List[ReferenceFile] = []
    for part, args in ((_support_files, ()), (_space_weather_files, (now.date(),)), (_earth_orientation_files, (now,))):
        try:
            files += part(*args)
        except Exception as exc:  # noqa: BLE001 -- the panel must show the rest
            files.append(ReferenceFile(part.__name__.strip("_").replace("_", " "), "-", "missing", note=str(exc)))
    return files
