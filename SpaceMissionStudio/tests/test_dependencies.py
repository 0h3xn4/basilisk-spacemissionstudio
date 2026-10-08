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

"""Qualified Basilisk version, its start-up check and the run's
configuration record (ECSS-Q-ST-80C 6.2.4, 6.2.7; remediation R01)."""

import hashlib
import json
import re
from pathlib import Path

import pytest

from spacemissionstudio import dependencies

pytestmark = pytest.mark.requirement("Q-ST-80C 6.2.4", "Q-ST-80C 6.2.7")

_PACKAGING = Path(__file__).resolve().parent.parent / "packaging"


def test_basilisk_check_accepts_only_the_qualified_version():
    """No note for the qualified version; a note naming both versions for
    another; a clear note when Basilisk is missing."""
    assert dependencies.basilisk_check(dependencies.QUALIFIED_BASILISK_VERSION) is None
    note = dependencies.basilisk_check("2.13.0b0")
    assert "2.13.0b0" in note and dependencies.QUALIFIED_BASILISK_VERSION in note


def test_basilisk_check_reports_a_missing_basilisk(monkeypatch):
    """Without Basilisk the check says simulations cannot run."""
    monkeypatch.setattr(dependencies, "basilisk_version", lambda: None)
    assert dependencies.basilisk_check() == "Basilisk is not installed: simulations cannot run"


@pytest.mark.parametrize("installer", ["deb/DEBIAN/postinst", "windows/bootstrap_env.ps1"])
def test_installers_pin_the_qualified_basilisk_version(installer):
    """Every pip install of Basilisk in the installers pins exactly the
    qualified version, so changing one without the other fails here."""
    text = (_PACKAGING / installer).read_text(encoding="utf-8")
    pins = re.findall(r'pip install --quiet "bsk\[all\]([^"]*)"', text)
    assert pins == [f"=={dependencies.QUALIFIED_BASILISK_VERSION}"]


def test_file_record_hashes_small_files_and_flags_missing_ones(tmp_path):
    """A small file gets its size and SHA-256; a missing one is marked."""
    data = tmp_path / "sw.csv"
    data.write_bytes(b"DATE,F10.7\n2026-01-01,150.0\n")
    record = dependencies.file_record(data)
    assert record == {"path": str(data), "size_bytes": len(data.read_bytes()),
                      "sha256": hashlib.sha256(data.read_bytes()).hexdigest()}
    assert dependencies.file_record(tmp_path / "absent.bsp") == {"path": str(tmp_path / "absent.bsp"),
                                                                 "missing": True}


def test_dependency_versions_lists_python_and_installed_packages():
    """Python, platform and numpy (a hard dependency) are always listed."""
    versions = dependencies.dependency_versions()
    assert {"python", "platform", "numpy"} <= set(versions)


@pytest.mark.requires_basilisk
def test_run_provenance_records_the_configuration(tmp_path):
    """A real run's provenance.json carries the Basilisk qualification, the
    dependency versions, the scenario hash and the SPICE kernels used."""
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.schema import load_scenario

    scenario_path = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / \
        "two_body_validation.json"
    scenario = load_scenario(scenario_path)
    scenario.sim_settings.duration_days = 0.01  # [day]
    result = SimulationService(scenario).run()
    paths = result.export_csv(tmp_path)
    provenance = json.loads(Path(paths["provenance"]).read_text())
    assert provenance["qualified_basilisk_version"] == dependencies.QUALIFIED_BASILISK_VERSION
    assert provenance["basilisk_qualified"] == (provenance["basilisk_version"]
                                                == dependencies.QUALIFIED_BASILISK_VERSION)
    assert provenance["dependency_versions"]["numpy"]
    assert provenance["scenario_sha256"] == hashlib.sha256(
        json.dumps(scenario.to_dict(), sort_keys=True).encode("utf-8")).hexdigest()
    kernels = {name: record for name, record in provenance["data_files"].items() if name.startswith("spice:")}
    assert "spice:naif0012.tls" in kernels
    assert all("size_bytes" in record for record in kernels.values())
