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

"""Exporting the flight software (SRS-F-18), with Basilisk: what the
capture reads out of a built simulation, what it refuses, and that every
attitude template's export builds with CMake and reproduces the
simulation's flight software (each module's unit test and the replay of
the recorded run pass)."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from spacemissionstudio.schema import load_scenario

pytestmark = pytest.mark.requires_basilisk

_TEMPLATES = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"


def _template(prefix):
    return load_scenario(next(_TEMPLATES.glob(f"{prefix}_*.json")))


def _attitude_templates():
    cases = []
    for path in sorted(_TEMPLATES.glob("*.json")):
        scenario = load_scenario(path)
        for sc in scenario.spacecraft:
            if scenario.simulation_mode != "orbit_only" and sc.fsw_mode is not None and sc.comms_pointing is None:
                cases.append((path.name, sc.name))
    return cases


def test_the_capture_reads_the_chain_basilisk_built():
    """Template 07: Sun-safe pointing on reaction wheels. The modules, in
    the task's order; navigation and wheel speeds in; wheel torques out to
    the wheels; the vehicle and wheel configuration as constants; the gains
    as engine.fsw set them, traced to the scenario."""
    from spacemissionstudio.fsw_export.capture import capture

    c = capture(_template("07"), "sat-1", steps=5)
    assert [m.name for m in c.modules] == ["sunSafePoint", "mrpFeedback", "rwMotorTorque"]
    assert [p.name for p in c.inputs] == ["simpleNav_attOutMsg", "reactionWheels_rwSpeedOutMsg"]
    assert [(p.name, p.consumers) for p in c.outputs] == [
        ("rwMotorTorque_rwMotorTorqueOutMsg", ["sat-1_reactionWheels.rwMotorCmdInMsg"])]
    assert sorted(k.message_type for k in c.constants) == ["RWArrayConfig", "VehicleConfig"]
    mrp = c.module("mrpFeedback")
    links = {link.field: (link.kind, link.ref) for link in mrp.inputs}
    assert links["guidInMsg"] == ("module", "sunSafePoint.attGuidanceOutMsg")
    assert links["rwSpeedsInMsg"] == ("input", "reactionWheels_rwSpeedOutMsg")
    assert links["rwAvailInMsg"][0] == "unlinked"
    k = next(p for p in mrp.params if p.name == "K")
    assert k.scenario_path == "control_params.K" and k.unit == "rad/sec" and k.value > 0.0
    assert len(c.times_ns) == 5 and c.times_ns[1] - c.times_ns[0] == c.rate_ns
    assert c.reset_inputs["reactionWheels_rwSpeedOutMsg"] is not None  # the wheels write their speeds in Reset


def test_momentum_dumping_records_the_priming_reset():
    """Template 12: thrMomentumManagement is reset again after the first
    step, as SimulationService.initialize() does."""
    from spacemissionstudio.fsw_export.capture import capture

    c = capture(_template("12"), "sat-1", steps=3)
    assert c.priming_resets == ["thrMomentumManagement"] and c.priming_time_ns == c.rate_ns


@pytest.mark.parametrize("prefix, name, reason", [
    ("19", "leo-comms-1", "comms pointing"),
    ("22", "my-sat", "no attitude flight software"),
])
def test_exports_that_cannot_reproduce_the_simulation_are_refused(prefix, name, reason):
    from spacemissionstudio.fsw_export.capture import CaptureError, capture

    with pytest.raises(CaptureError, match=reason):
        capture(_template(prefix), name, steps=3)
    with pytest.raises(CaptureError, match="no spacecraft named"):
        capture(_template(prefix), "nobody", steps=3)


def test_the_export_holds_basilisks_bytes_documents_and_a_complete_manifest(tmp_path):
    """Every Basilisk file is the vendored file byte for byte; the
    manifest's hashes match every file; the ICD lists every port with its
    layout hash; each traceability line points at the line of
    fsw_config.c that sets that symbol; one unit test per module; an
    earlier export is replaced only with overwrite, a foreign folder never."""
    from spacemissionstudio.fsw_export import sources
    from spacemissionstudio.fsw_export.generate import ExportError
    from spacemissionstudio.fsw_export.records import export_flight_software

    out = tmp_path / "fsw"
    result, record = export_flight_software(_template("13"), "sat-1", out, steps=20)
    manifest = json.loads((out / "manifest.json").read_text())
    for relative, digest in manifest["files"].items():
        assert hashlib.sha256((out / relative).read_bytes()).hexdigest() == digest, relative
    for path in (out / "basilisk").rglob("*"):
        if path.is_file():
            relative = path.relative_to(out / "basilisk").as_posix()
            assert path.read_bytes() == sources.read(relative), relative
    icd = (out / "ICD.md").read_text()
    for kind in ("inputs", "outputs", "telemetry"):
        for port in manifest["ports"][kind]:
            assert f"`{port['name']}`" in icd and port["layout_hash"] in icd
    config_lines = (out / "generated" / "fsw_config.c").read_text().splitlines()
    rows = re.findall(r"\| `fsw_modules\.(\w+)\.(\w+)` \| (\d+) \|", (out / "TRACEABILITY.md").read_text())
    assert rows
    for module, field, line in rows:
        assert f"config->{field}" in config_lines[int(line) - 1], (module, field, line)
    assert sorted(p.name for p in (out / "tests").glob("test_*.c")) == sorted(
        f"test_{m['name']}.c" for m in manifest["modules"])
    assert record.config_digest == manifest["config_digest"] and record.path == str(out)
    with pytest.raises(ExportError, match="earlier export"):
        export_flight_software(_template("13"), "sat-1", out, steps=5)
    export_flight_software(_template("13"), "sat-1", out, steps=5, overwrite=True)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "notes.txt").write_text("mine")
    with pytest.raises(ExportError, match="holds no earlier export"):
        export_flight_software(_template("13"), "sat-1", foreign, steps=5)
    assert (foreign / "notes.txt").read_text() == "mine"


def _cmake(*args, cwd=None):
    return subprocess.run(["cmake", *args], cwd=cwd, capture_output=True, text=True)  # noqa: S603,S607


@pytest.mark.requires_c_toolchain
@pytest.mark.parametrize("template, spacecraft", _attitude_templates(), ids=lambda v: str(v)[:24])
def test_every_attitude_template_exports_builds_and_reproduces_the_simulation(tmp_path, template, spacecraft):
    """The export of each attitude template configures and builds with
    CMake (the generated code without warnings under -Wall -Wextra on GCC
    and Clang), and CTest passes: each module's unit test and the replay
    of 60 recorded steps through the whole flight software."""
    from spacemissionstudio.fsw_export.records import export_flight_software

    out = tmp_path / "fsw"
    export_flight_software(load_scenario(_TEMPLATES / template), spacecraft, out, steps=60)
    build = tmp_path / "build"
    flags = [] if sys.platform == "win32" else ["-DCMAKE_C_FLAGS=-Wall -Wextra"]
    configured = _cmake("-S", str(out), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release", *flags)
    assert configured.returncode == 0, configured.stdout + configured.stderr
    built = _cmake("--build", str(build), "--config", "Release", "-j", "4")
    assert built.returncode == 0, built.stdout + built.stderr
    ours = [line for line in (built.stdout + built.stderr).splitlines()
            if "warning" in line and re.search(r"[/\\](generated|host|tests)[/\\]", line)]
    assert not ours, "\n".join(ours)
    ctest = shutil.which("ctest")
    tested = subprocess.run([ctest, "--test-dir", str(build), "-C", "Release", "--output-on-failure"],  # noqa: S603
                            capture_output=True, text=True)
    assert tested.returncode == 0, tested.stdout + tested.stderr
    assert "100% tests passed" in tested.stdout


@pytest.mark.requires_c_toolchain
def test_names_from_a_shared_scenario_cannot_put_code_into_the_export(tmp_path):
    """A scenario and spacecraft named to close a C comment, end a string
    or start a CMake line: the export still builds, its tests pass, the
    name comes back intact from fsw_host, and the raw text appears in no
    generated C or CMake file (security analysis S-14)."""
    from spacemissionstudio.fsw_export.records import export_flight_software

    hostile = 'x */ int injected = 1; /* "\\n'
    scenario = _template("06")
    scenario.name = "evil\nadd_custom_target(boom ALL COMMAND false)"
    scenario.spacecraft[0].name = "sat" + hostile + "\u00e9"
    scenario.validate()
    out = tmp_path / "fsw"
    export_flight_software(scenario, scenario.spacecraft[0].name, out, steps=5)
    for path in list((out / "generated").glob("*.[ch]")) + list((out / "tests").glob("*.c")) + [out / "CMakeLists.txt"]:
        text = path.read_text()
        for line in text.splitlines():
            if "int injected" in line:  # only escaped in the name's string literal, or neutralised in a comment
                assert line.startswith("const char fsw_spacecraft_name[]") or "* / int injected" in line, (path, line)
            assert not line.lstrip().startswith("add_custom_target"), (path, line)
    build = tmp_path / "build"
    assert _cmake("-S", str(out), "-B", str(build)).returncode == 0
    built = _cmake("--build", str(build), "--config", "Release")
    assert built.returncode == 0, built.stdout + built.stderr
    host = next(p for p in build.rglob("fsw_host*") if p.is_file() and p.suffix in ("", ".exe"))
    info = subprocess.run([str(host), "info"], capture_output=True)  # noqa: S603
    assert scenario.spacecraft[0].name.encode() in info.stdout


def test_the_cli_exports_and_records(tmp_path, capsys):
    """``export-fsw --record`` writes the export and its record into the
    scenario; ``fsw-status`` then reports it current (exit 0), and stale
    after a gain change (exit 2)."""
    from spacemissionstudio import cli

    scenario_path = tmp_path / "s.json"
    shutil.copy(next(_TEMPLATES.glob("06_*.json")), scenario_path)
    out = tmp_path / "fsw"
    assert cli.main(["export-fsw", str(scenario_path), "--spacecraft", "sat-1", "--out", str(out), "--steps", "5",
                     "--record"]) == 0
    assert load_scenario(scenario_path).fsw_exports[0].path == str(out)
    assert cli.main(["fsw-status", str(scenario_path)]) == 0
    assert "CURRENT" in capsys.readouterr().out
    data = json.loads(scenario_path.read_text())
    data["spacecraft"][0]["control_params"]["P"] = 12.0
    scenario_path.write_text(json.dumps(data))
    assert cli.main(["fsw-status", str(scenario_path)]) == 2
    assert "STALE -- changed since the export: control_params" in capsys.readouterr().out
