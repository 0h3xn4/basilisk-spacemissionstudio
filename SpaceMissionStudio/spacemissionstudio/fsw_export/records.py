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

"""Exporting a spacecraft's flight software and checking an earlier export.

:func:`export_flight_software` records the run (Basilisk), writes the C
project and returns the :class:`~spacemissionstudio.schema.scenario.FswExportRecord`
to keep in the scenario. :func:`export_status` compares a record with the
scenario as it is now and with the folder on disk (no Basilisk needed).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..schema.scenario import FswExportRecord
from .catalog import BASILISK_REVISION
from .digest import changed_parts, fsw_config_digest, fsw_config_parts

CURRENT = "current"
STALE = "stale"
MISSING = "missing"
MODIFIED = "modified"
UNKNOWN_SPACECRAFT = "unknown spacecraft"


@dataclass
class ExportStatus:
    state: str  # one of the constants above
    message: str
    changed: List[str] = field(default_factory=list)  # setting groups changed since the export


def export_flight_software(scenario, spacecraft_name: str, out_dir, steps: Optional[int] = None,
                           overwrite: bool = False):
    """Captures and writes the export; returns ``(ExportResult, FswExportRecord)``.
    Raises ``capture.CaptureError`` or ``generate.ExportError`` with the reason."""
    from .capture import DEFAULT_STEPS, capture
    from .generate import generate

    captured = capture(scenario, spacecraft_name, steps=steps or DEFAULT_STEPS)
    result = generate(captured, out_dir, overwrite=overwrite)
    record = FswExportRecord(spacecraft=spacecraft_name, path=str(Path(out_dir)),
                             config_digest=captured.config_digest, exported_utc=result.manifest["exported_utc"],
                             basilisk_revision=BASILISK_REVISION,
                             parts=fsw_config_parts(scenario, spacecraft_name))
    return result, record


def with_record(scenario, record: FswExportRecord) -> list:
    """``scenario.fsw_exports`` with ``record`` replacing any earlier one for its spacecraft."""
    return [r for r in scenario.fsw_exports if r.spacecraft != record.spacecraft] + [record]


def _folder(record: FswExportRecord, base_dir) -> Path:
    path = Path(record.path)
    return path if path.is_absolute() or base_dir is None else Path(base_dir) / path


def export_status(scenario, record: FswExportRecord, base_dir=None) -> ExportStatus:
    """Whether ``record``'s export still matches ``scenario`` and its folder.
    ``base_dir`` resolves a relative path (the scenario file's folder)."""
    if not any(sc.name == record.spacecraft for sc in scenario.spacecraft):
        return ExportStatus(UNKNOWN_SPACECRAFT, f"no spacecraft named {record.spacecraft} in this scenario")
    folder = _folder(record, base_dir)
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        return ExportStatus(MISSING, f"the export folder {folder} or its manifest.json is missing")
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as exc:
        return ExportStatus(MODIFIED, f"manifest.json cannot be read: {exc}")
    if manifest.get("config_digest") != record.config_digest:
        return ExportStatus(MODIFIED, "the folder holds a different export than the one this scenario recorded")
    for relative, digest in manifest.get("files", {}).items():
        target = folder / relative
        try:
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError:
            return ExportStatus(MODIFIED, f"{relative} is missing from the export")
        if actual != digest:
            return ExportStatus(MODIFIED, f"{relative} was changed after the export")
    current = fsw_config_digest(scenario, record.spacecraft)
    if current != record.config_digest:
        changed = changed_parts(record.parts, fsw_config_parts(scenario, record.spacecraft))
        what = ", ".join(changed) if changed else "the flight-software settings"
        return ExportStatus(STALE, f"changed since the export: {what}", changed)
    return ExportStatus(CURRENT, f"matches the scenario (exported {record.exported_utc})")
