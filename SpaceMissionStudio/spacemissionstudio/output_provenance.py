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
"""Provenance inside output files (UX/UI guidelines, "provenance on every
output": tool and Basilisk versions, the input, the settings and the
reference data that produced a result).

The lines come from :meth:`engine.results.RunProvenance.summary_lines`;
the full record goes as JSON. Formats that can carry it inside the file
do (PNG text chunk, SVG ``<metadata>``, CCSDS ``COMMENT``); the others get
a ``.provenance.json`` file beside them.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence
from xml.sax.saxutils import escape

PNG_KEYWORD = "SpaceMissionStudio provenance"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_with_provenance(png: bytes, record: dict) -> bytes:
    """``png`` with a ``tEXt`` chunk holding ``record`` as JSON, placed
    right after the header chunk (no re-encoding of the image)."""
    if not png.startswith(_PNG_SIGNATURE):
        raise ValueError("not a PNG image")
    ihdr_length = struct.unpack(">I", png[8:12])[0]
    insert_at = 8 + 12 + ihdr_length  # signature, then IHDR: length, type, data, CRC
    body = PNG_KEYWORD.encode("latin-1") + b"\0" + json.dumps(record, sort_keys=True).encode("ascii", "replace")
    chunk = struct.pack(">I", len(body)) + b"tEXt" + body + struct.pack(">I", zlib.crc32(b"tEXt" + body) & 0xFFFFFFFF)
    return png[:insert_at] + chunk + png[insert_at:]


def png_provenance(png: bytes) -> dict:
    """The record :func:`png_with_provenance` stored, or ``{}``."""
    position = 8
    while position + 8 <= len(png):
        length = struct.unpack(">I", png[position:position + 4])[0]
        kind = png[position + 4:position + 8]
        data = png[position + 8:position + 8 + length]
        if kind == b"tEXt" and data.startswith(PNG_KEYWORD.encode("latin-1") + b"\0"):
            return json.loads(data[len(PNG_KEYWORD) + 1:].decode("ascii"))
        position += 12 + length
    return {}


def svg_with_provenance(svg: str, lines: Sequence[str], record: dict) -> str:
    """``svg`` with a ``<metadata>`` element (the summary lines and the JSON
    record) as the first child of its root element."""
    start = svg.find("<svg")
    end = svg.find(">", start)
    if start < 0 or end < 0:
        raise ValueError("not an SVG image")
    metadata = ("<metadata id=\"spacemissionstudio-provenance\">"
                + escape("\n".join(lines)) + "\n" + escape(json.dumps(record, sort_keys=True)) + "</metadata>")
    return svg[:end + 1] + metadata + svg[end + 1:]


def scenario_sha256(scenario) -> str:
    """SHA-256 of the scenario as it is run (its canonical JSON); the same
    hash the run provenance records."""
    return hashlib.sha256(json.dumps(scenario.to_dict(), sort_keys=True).encode("utf-8")).hexdigest()


def scenario_record(scenario) -> dict:
    """Provenance of an output made from a scenario without a simulation
    run (an OPM export, a budget, a lifetime, a Monte Carlo archive)."""
    from . import __version__, dependencies

    return {"spacemissionstudio_version": __version__, "basilisk_version": dependencies.basilisk_version(),
            "qualified_basilisk_version": dependencies.QUALIFIED_BASILISK_VERSION,
            "dependency_versions": dependencies.dependency_versions(),
            "scenario_name": scenario.name, "scenario_sha256": scenario_sha256(scenario),
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def scenario_lines(scenario) -> List[str]:
    """Short ASCII lines of :func:`scenario_record`."""
    record = scenario_record(scenario)
    lines = [f"SpaceMissionStudio {record['spacemissionstudio_version']}, Basilisk {record['basilisk_version']}",
             f"Scenario SHA-256 {record['scenario_sha256']}", f"Made {record['created_utc']}"]
    return [line.encode("ascii", "replace").decode("ascii") for line in lines]


def write_sidecar(output: Path, record: dict) -> Path:
    """``<output>.provenance.json`` beside a file whose format has no room for it."""
    sidecar = Path(f"{output}.provenance.json")
    sidecar.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sidecar
