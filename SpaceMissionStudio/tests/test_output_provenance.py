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
"""Provenance inside every output (UX/UI guidelines, "provenance on every
output"): plots, CCSDS messages, tables, Monte Carlo archives."""

import json
import struct
import zlib
from pathlib import Path

import pytest

from spacemissionstudio import cli, output_provenance
from spacemissionstudio.engine.results import RunProvenance
from spacemissionstudio.schema import load_scenario

_TEMPLATES = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"


def _png_1x1() -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1 RGB
    pixels = zlib.compress(b"\x00\xff\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


def _provenance() -> RunProvenance:
    return RunProvenance("2.0.0", "2.12.0", "2026-10-09T00:00:00+00:00", "rkf78", 30.0,
                         qualified_basilisk_version="2.12.0", basilisk_qualified=True, scenario_sha256="ab" * 32,
                         data_files={"spice:naif0012.tls": {"path": "/x/naif0012.tls", "sha256": "cd" * 32}})


def test_png_keeps_its_image_and_carries_the_record():
    """The text chunk goes after the header; the image chunks are unchanged."""
    png = _png_1x1()
    record = _provenance().to_dict()
    tagged = output_provenance.png_with_provenance(png, record)
    assert output_provenance.png_provenance(tagged) == record
    assert tagged.endswith(png[33:])  # IDAT and IEND as before
    from PySide6.QtGui import QImage

    image = QImage.fromData(tagged)
    assert not image.isNull() and image.width() == 1


def test_svg_gets_a_metadata_element():
    svg = '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect/></svg>'
    provenance = _provenance()
    tagged = output_provenance.svg_with_provenance(svg, provenance.summary_lines(), provenance.to_dict())
    import xml.etree.ElementTree as ET

    root = ET.fromstring(tagged.split("?>", 1)[1])
    metadata = root.find("{http://www.w3.org/2000/svg}metadata")
    assert metadata is not None and "Scenario SHA-256 " + "ab" * 32 in metadata.text


def test_summary_lines_name_the_versions_the_scenario_and_the_data():
    lines = _provenance().summary_lines()
    assert lines[0] == "SpaceMissionStudio 2.0.0, Basilisk 2.12.0 (qualified)"
    assert any(line == "Scenario SHA-256 " + "ab" * 32 for line in lines)
    assert any(line.startswith("Data naif0012.tls: SHA-256 cd") for line in lines)
    assert all(line.isascii() for line in lines)


def test_opm_export_carries_the_scenario_hash(tmp_path):
    """An OPM written from a scenario (no run) names the tool and the scenario's hash."""
    pytest.importorskip("Basilisk")
    template = sorted(_TEMPLATES.glob("01_*.json"))[0]
    assert cli.main(["ccsds-export", str(template), "--out", str(tmp_path)]) == 0
    text = next(tmp_path.glob("*.opm")).read_text(encoding="ascii")
    digest = output_provenance.scenario_sha256(load_scenario(template))
    assert f"COMMENT Scenario SHA-256 {digest}" in text
    assert cli.main(["ccsds-validate", str(next(tmp_path.glob("*.opm")))]) == 0


@pytest.mark.requires_basilisk
def test_a_run_writes_its_provenance_into_the_oem(tmp_path):
    """The OEM's header comments carry the same scenario hash as provenance.json."""
    template = sorted(_TEMPLATES.glob("01_*.json"))[0]
    scenario = json.loads(template.read_text(encoding="utf-8"))
    scenario["sim_settings"]["duration_days"] = 0.02  # [day]
    path = tmp_path / "short.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    out = tmp_path / "out"
    assert cli.main(["run", str(path), "--out-dir", str(out), "--oem"]) == 0
    record = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
    oem = next(out.glob("*.oem")).read_text(encoding="ascii")
    assert f"COMMENT Scenario SHA-256 {record['scenario_sha256']}" in oem
    assert "COMMENT SpaceMissionStudio" in oem


def test_sidecar_sits_beside_the_output(tmp_path):
    output = tmp_path / "table.csv"
    output.write_text("a,b\n", encoding="utf-8")
    sidecar = output_provenance.write_sidecar(output, {"scenario_sha256": "ef" * 32})
    assert sidecar == tmp_path / "table.csv.provenance.json"
    assert json.loads(sidecar.read_text(encoding="utf-8"))["scenario_sha256"] == "ef" * 32
