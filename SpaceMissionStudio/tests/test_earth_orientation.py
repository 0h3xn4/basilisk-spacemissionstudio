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

"""IERS-based Earth orientation files (ECSS-E-ST-10-09C 5.4.9f; remediation
R04): install, import, manifest, rollback, notes, and -- when the real NAIF
files are installed on this machine -- a run's Earth frame equal to SPICE's
ITRF93. No test touches the network (fetch is tested with a stub)."""

import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from spacemissionstudio.engine import earth_orientation as eo

pytestmark = pytest.mark.requirement("E-ST-10-09C 5.4.9f", "E-ST-10-04C 4.2.1c")

_REAL_DIR = Path(os.path.expanduser("~")) / ".cache" / "SpaceMissionStudio" / "earth_orientation"
_COMMENT = ("Coverage\n\n   ET Start time:             2000 JAN 01 00:01:04.183 TDB\n"
            "   UTC Epoch of last datum:   2026 OCT 07 00:00:00.000 UTC\n")


def _fake_pck(path: Path, payload: bytes = b"\0" * 64) -> Path:
    path.write_bytes(b"DAF/PCK " + payload)
    return path


def test_parse_last_datum_reads_the_naif_comment():
    """The last-datum line of a NAIF comment file is read as UTC."""
    assert eo.parse_last_datum(_COMMENT) == datetime(2026, 10, 7)
    assert eo.parse_last_datum("no such line") is None


def test_import_writes_a_manifest_with_hash_and_last_datum(tmp_path):
    """Imported files are installed with size, SHA-256, source and the last
    datum from the .cmt beside them, combined first in load order."""
    source = tmp_path / "media"
    source.mkdir()
    high = _fake_pck(source / "earth_latest_high_prec.bpc")
    (source / "earth_latest_high_prec.cmt").write_text(_COMMENT)
    combined = _fake_pck(source / "earth_1962_260806_2126_combined.bpc", b"\1" * 64)
    kernels = eo.import_files([high, combined], tmp_path / "eop")
    assert [k.role for k in kernels] == ["combined", "high_precision"]
    assert kernels[1].last_datum_utc == "2026-10-07T00:00:00"
    assert kernels[1].high_accuracy_until == datetime(2026, 12, 16)
    assert kernels[0].last_datum_utc is None
    manifest = json.loads((tmp_path / "eop" / "manifest.json").read_text())
    assert {Path(entry["source"]).name for entry in manifest} == {high.name, combined.name}
    import hashlib
    assert kernels[1].sha256 == hashlib.sha256(high.read_bytes()).hexdigest()


def test_a_file_that_is_not_a_binary_pck_is_refused(tmp_path):
    """A text file renamed to .bpc is rejected; nothing is installed."""
    bad = tmp_path / "earth_latest_high_prec.bpc"
    bad.write_text("not a kernel")
    with pytest.raises(eo.EarthOrientationError, match="not a binary PCK"):
        eo.import_files([bad], tmp_path / "eop")
    assert eo.installed(tmp_path / "eop") == []


def test_a_new_install_keeps_the_previous_files_for_rollback(tmp_path):
    """Installing again moves the old files aside; rollback restores them."""
    eop = tmp_path / "eop"
    first = _fake_pck(tmp_path / "earth_latest_high_prec.bpc", b"old" * 20)
    eo.import_files([first], eop)
    old_hash = eo.installed(eop)[0].sha256
    second_dir = tmp_path / "new"
    second_dir.mkdir()
    eo.import_files([_fake_pck(second_dir / "earth_latest_high_prec.bpc", b"new" * 20)], eop)
    assert eo.installed(eop)[0].sha256 != old_hash
    restored = eo.rollback(eop)
    assert [k.sha256 for k in restored] == [old_hash]
    with pytest.raises(eo.EarthOrientationError, match="no previous"):
        eo.rollback(eop)


def test_a_changed_file_is_not_used(tmp_path):
    """A file whose size no longer matches the manifest is left out."""
    eop = tmp_path / "eop"
    eo.import_files([_fake_pck(tmp_path / "earth_latest_high_prec.bpc")], eop)
    (eop / "earth_latest_high_prec.bpc").write_bytes(b"DAF/PCK truncated")
    assert eo.installed(eop) == []


def test_fetch_downloads_the_current_naif_files(tmp_path, monkeypatch):
    """fetch picks the newest combined file and the high-precision file from
    the NAIF listing and installs both with their comments (network stubbed)."""
    listing = ('<a href="earth_1962_250806_2125_combined.bpc"> <a href="earth_1962_260806_2126_combined.bpc"> '
               '<a href="earth_latest_high_prec.bpc">')
    served = {eo.NAIF_PCK_URL: listing.encode(),
              eo.NAIF_PCK_URL + "earth_1962_260806_2126_combined.bpc": b"DAF/PCK " + b"c" * 32,
              eo.NAIF_PCK_URL + "earth_1962_260806_2126_combined.cmt": _COMMENT.replace("OCT 07", "AUG 06").encode(),
              eo.NAIF_PCK_URL + "earth_latest_high_prec.bpc": b"DAF/PCK " + b"h" * 32,
              eo.NAIF_PCK_URL + "earth_latest_high_prec.cmt": _COMMENT.encode()}
    requested = []
    monkeypatch.setattr(eo, "_get", lambda url, timeout_s: requested.append(url) or served[url])
    kernels = eo.fetch(tmp_path / "eop")
    assert [Path(k.path).name for k in kernels] == ["earth_1962_260806_2126_combined.bpc", "earth_latest_high_prec.bpc"]
    assert kernels[0].last_datum_utc == "2026-08-06T00:00:00"
    assert all(url.startswith(eo.NAIF_PCK_URL) for url in requested)
    assert not list((tmp_path / "eop").glob("*.part"))


def test_user_files_take_precedence_over_the_install_wide_ones(tmp_path, monkeypatch):
    """installed() uses the user's directory when it has files, else the
    install-wide one the installers fill."""
    monkeypatch.setattr(eo, "DEFAULT_DIR", tmp_path / "user")
    monkeypatch.setattr(eo, "SYSTEM_DIR", tmp_path / "system")
    assert eo.installed() == []
    eo.import_files([_fake_pck(tmp_path / "earth_latest_high_prec.bpc")], tmp_path / "system")
    assert Path(eo.installed()[0].path).parent == tmp_path / "system"
    source = tmp_path / "u"
    source.mkdir()
    eo.import_files([_fake_pck(source / "earth_latest_high_prec.bpc", b"u" * 64)], tmp_path / "user")
    assert Path(eo.installed()[0].path).parent == tmp_path / "user"


def test_notes_name_the_fallback_and_the_predicted_span(tmp_path):
    """No files: the IAU model is named. A run past the high-accuracy span
    says from when it is predicted; a run inside it gets no note."""
    start, end = datetime(2026, 11, 1), datetime(2027, 1, 1)
    assert eo.notes(start, end, []) == ["Earth orientation: IAU rotation model, no IERS data installed"]
    kernel = eo.EOPKernel(role="high_precision", path="x", source="t", size_bytes=1, sha256="0", installed_utc="",
                          last_datum_utc="2026-10-07T00:00:00")
    assert eo.notes(start, end, [kernel]) == ["Earth orientation: ITRF93, predicted (low accuracy) for after 2026-12-16"]
    assert eo.notes(datetime(2030, 1, 1), datetime(2030, 2, 1), [kernel]) == [
        "Earth orientation: ITRF93, predicted (low accuracy) for the whole run"]
    assert eo.notes(start, datetime(2026, 12, 1), [kernel]) == []


@pytest.mark.requires_basilisk
@pytest.mark.skipif(not eo.installed(_REAL_DIR), reason="real NAIF Earth PCKs not installed on this machine")
def test_a_run_uses_spice_itrf93_as_the_earth_frame(monkeypatch):
    """With the real NAIF files installed, a run's Earth state message
    carries SPICE's J2000 -> ITRF93 rotation, which differs from IAU_EARTH,
    and the provenance lists the files."""
    from Basilisk.topLevelModules import pyswice
    from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.engine.time_system import utc_iso_to_spice_string
    from spacemissionstudio.schema import load_scenario

    monkeypatch.setattr(eo, "DEFAULT_DIR", _REAL_DIR)
    scenario = load_scenario(Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios"
                             / "templates" / "19_sun_pointing_comms_link.json")
    scenario.epoch_utc = "2026-06-01T00:00:00"
    scenario.sim_settings.duration_days = 0.01  # [day]
    service = SimulationService(scenario)
    result = service.run()
    assert service.earth_frame == "ITRF93"
    earth = service.spice_object.planetStateOutMsgs[0].read()
    assert {name for name in result.provenance.data_files if name.startswith("earth_orientation:")}

    for path in [get_path(DataFile.EphemerisData.naif0012), get_path(DataFile.EphemerisData.pck00010)] + \
            [k.path for k in eo.installed(_REAL_DIR)]:
        pyswice.furnsh_c(str(path))
    et = pyswice.new_doubleArray(1)
    pyswice.str2et_c(utc_iso_to_spice_string(scenario.epoch_utc), et)
    t_end = result.series["leo-comms-1.position_N"].time_s[-1]  # [s]

    def rotation(frame):
        out = pyswice.new_doubleArray(9)
        pyswice.pxform_c("J2000", frame, pyswice.doubleArray_getitem(et, 0) + t_end, out)
        return np.array([pyswice.doubleArray_getitem(out, i) for i in range(9)]).reshape(3, 3)

    np.testing.assert_allclose(np.array(earth.J20002Pfix), rotation("ITRF93"), atol=1e-12)
    difference = np.array(earth.J20002Pfix) @ rotation("IAU_EARTH").T
    assert np.degrees(np.arccos((np.trace(difference) - 1.0) / 2.0)) > 1e-3  # [deg] the frames really differ
