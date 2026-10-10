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

"""Software-in-the-loop runs (SRS-F-19), with Basilisk and a C toolchain:
the exported flight software flying the spacecraft through the SIL
contract reproduces a normal run exactly (over a Unix socket and over
TCP, with same-step actuation, the momentum-dumping priming reset and a
model between the modules), the adapter template runs and is reported as
writing nothing, and every failure is loud: a program for another
spacecraft, a program that exits, a deadline nobody meets, frames the C
harness refuses, and the CLI."""

import copy
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from spacemissionstudio.schema import load_scenario

pytestmark = [pytest.mark.requires_basilisk, pytest.mark.requires_c_toolchain]

_TEMPLATES = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
_UNIX = "tcp" if sys.platform == "win32" else "unix"


def _template(prefix, minutes):
    scenario = load_scenario(next(_TEMPLATES.glob(f"{prefix}_*.json")))
    scenario.sim_settings.duration_days = minutes / 1440.0  # [day]
    return scenario


def _program(build: Path, name: str) -> Path:
    return next(p for p in build.rglob(f"{name}*") if p.is_file() and p.suffix in ("", ".exe"))


def _export_and_build(scenario, spacecraft, folder: Path, edit=None) -> Path:
    from spacemissionstudio.fsw_export.records import export_flight_software

    export_flight_software(scenario, spacecraft, folder / "export", steps=10)
    if edit is not None:
        edit(folder / "export")
    build = folder / "build"
    for args in (["-S", str(folder / "export"), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release"],
                 ["--build", str(build), "--config", "Release", "-j", "4"]):
        done = subprocess.run(["cmake", *args], capture_output=True, text=True)  # noqa: S603,S607
        assert done.returncode == 0, done.stdout + done.stderr
    return build


@pytest.fixture(scope="module")
def built_07(tmp_path_factory):
    folder = tmp_path_factory.mktemp("sil07")
    return _export_and_build(_template("07", 2), "sat-1", folder)


@pytest.mark.parametrize("prefix, transport", [("06", "tcp"), ("12", _UNIX), ("13", "tcp")])
def test_the_exported_flight_software_in_the_loop_reproduces_the_simulation_exactly(tmp_path, prefix, transport):
    """06 (the command is applied by a model right after the modules, in
    the same step), 12 (momentum dumping: the priming re-Reset) and 13
    (torque rods: models between the modules): flown by the exported
    fsw_host, every residual is zero and every result series equals the
    normal run's, bit for bit."""
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.sil.runner import SilOptions, run_sil

    scenario = _template(prefix, 5)
    build = _export_and_build(scenario, "sat-1", tmp_path)
    normal = SimulationService(copy.deepcopy(scenario)).run()
    result, report = run_sil(scenario, "sat-1", SilOptions(str(_program(build, "fsw_host")), transport=transport))
    assert report.completed and report.address_kind == transport and report.dropped_steps == 0
    assert report.steps == round(5 * 60 / scenario.sim_settings.dynamics_task_rate_s) + 1
    assert report.max_abs_error == 0.0 and report.signals_missing == 0
    assert report.fsw_config_digest == report.scenario_config_digest and not report.warnings
    assert set(result.series) == set(normal.series)
    for name, series in normal.series.items():
        assert np.array_equal(series.data, result.series[name].data, equal_nan=True), name


def test_the_adapter_template_runs_and_is_reported_as_writing_nothing(built_07):
    """As generated, the adapter answers every step without commands: the
    run completes, the wheels get no motor torque, and every signal is
    listed as never written; the report names it as not exported."""
    from spacemissionstudio.sil.runner import SilOptions, run_sil

    result, report = run_sil(_template("07", 2), "sat-1", SilOptions(str(_program(built_07, "fsw_adapter_host"))))
    assert report.completed and report.fsw_name == "adapter template"
    assert report.signals_missing == len(report.signals) > 0
    assert any("not exported from SpaceMissionStudio" in w for w in report.warnings)
    # No motor torque: the wheels only follow the body's motion (about 1e-5 rad/s here), while the
    # simulation's own modules asked for torques that would have spun them up by far more.
    assert np.max(np.abs(result.series["sat-1.rw_speeds"].data)) < 1e-3  # [rad/s]
    torque = next(s for s in report.signals if s.name == "rwMotorTorque_rwMotorTorqueOutMsg.motorTorque[0]")
    assert torque.max_abs_reference > 1e-3  # [N*m]


def test_a_program_for_another_spacecraft_or_that_exits_fails_loudly(built_07, tmp_path):
    """07's flight software against 13's spacecraft: refused at HELLO,
    naming the step and ports that differ, and the program says why it was
    refused. A program that exits at once fails with its exit status."""
    from spacemissionstudio.sil.runner import SilOptions, SilRunError, run_sil
    from spacemissionstudio.sil.session import Timeouts

    with pytest.raises(SilRunError, match="does not match this spacecraft.*runs every 1 s") as refused:
        run_sil(_template("13", 1), "sat-1", SilOptions(str(_program(built_07, "fsw_host"))))
    assert "refused" in refused.value.report.log_tail
    if sys.platform == "win32":
        pytest.skip("needs a POSIX shell script")
    script = tmp_path / "exits.sh"
    script.write_text("#!/bin/sh\necho 'cannot open the star tracker' >&2\nexit 3\n")
    script.chmod(0o755)
    with pytest.raises(SilRunError, match="exited with status 3 \\(cannot open the star tracker\\)"):
        run_sil(_template("07", 1), "sat-1", SilOptions(str(script), timeouts=Timeouts(handshake_s=5.0)))


def test_an_error_in_a_module_reaches_the_simulation_and_stops_the_run(tmp_path):
    """An export whose mrpFeedback has its guidance input left unconnected
    (one line removed from fsw_connect()): the module's own Reset check
    calls _bskError; fsw_host sends it as ERROR before it exits, and the run
    stops naming it, the module's message in the program's output."""
    from spacemissionstudio.sil.runner import SilOptions, SilRunError, run_sil

    def disconnect_guidance(export: Path):
        config = export / "generated" / "fsw_config.c"
        lines = config.read_text().splitlines(keepends=True)
        kept = [line for line in lines if "Msg_C_subscribe(&fsw_modules.mrpFeedback.guidInMsg" not in line]
        assert len(kept) == len(lines) - 1
        config.write_text("".join(kept))

    scenario = _template("07", 1)
    build = _export_and_build(scenario, "sat-1", tmp_path, edit=disconnect_guidance)
    with pytest.raises(SilRunError, match="reported an error: Error: mrpFeedback.guidInMsg wasn't connected") as failed:
        run_sil(scenario, "sat-1", SilOptions(str(_program(build, "fsw_host"))))
    assert "BSK_ERROR: Error: mrpFeedback.guidInMsg wasn't connected" in failed.value.report.log_tail
    replay = subprocess.run([str(_program(build, "fsw_host")), "replay",  # noqa: S603
                             str(tmp_path / "export" / "tests" / "data" / "replay_inputs.trace"),
                             str(tmp_path / "out.trace")], capture_output=True, text=True)
    assert replay.returncode == 70 and "guidInMsg wasn't connected" in replay.stderr


def test_fsw_host_replay_refuses_options_it_cannot_honour(built_07, tmp_path):
    """``fsw_host replay`` with an option missing its value (``--expect``
    last), a tolerance that is not a number >= 0, or an input trace with no
    records exits 2 naming the problem, instead of skipping the comparison
    and reporting success; the recorded replay still matches."""
    host = _program(built_07, "fsw_host")
    data = built_07.parent / "export" / "tests" / "data"
    inputs, expected, out = data / "replay_inputs.trace", data / "replay_expected.trace", tmp_path / "out.trace"

    def replay(*extra):
        return subprocess.run([str(host), "replay", str(inputs), str(out), *extra],  # noqa: S603
                              capture_output=True, text=True)

    for extra, reason in ((["--expect"], "--expect needs a value"),
                          (["--expect", str(expected), "--rtol", "abc"], "--rtol abc is not a number >= 0"),
                          (["--atol", "-1"], "--atol -1 is not a number >= 0")):
        done = replay(*extra)
        assert done.returncode == 2 and reason in done.stderr, (extra, done.stdout, done.stderr)
    header = inputs.read_bytes()  # magic, kind, port count, record count, then 20 bytes per port
    port_count = int.from_bytes(header[12:16], "little")
    empty = tmp_path / "empty.trace"
    empty.write_bytes(header[:16] + bytes(4) + header[20:20 + 20 * port_count])  # the same ports, no records
    done = subprocess.run([str(host), "replay", str(empty), str(out)], capture_output=True, text=True)  # noqa: S603
    assert done.returncode == 2 and "has no reset record" in done.stderr, done.stderr
    done = replay("--expect", str(expected), "--rtol", "1e-9")
    assert done.returncode == 0 and "all outputs match" in done.stdout, done.stdout + done.stderr


def test_a_deadline_no_step_meets_drops_every_step(built_07):
    """With a 100 ns deadline every answer is late: each step counts as
    dropped, the commands stay as they were, and the run still completes."""
    from spacemissionstudio.sil.runner import SilOptions, run_sil
    from spacemissionstudio.sil.session import Timeouts

    _, report = run_sil(_template("07", 1), "sat-1",
                        SilOptions(str(_program(built_07, "fsw_host")), Timeouts(deadline_s=1e-7)))
    assert report.completed and report.dropped_steps == report.steps == 61
    assert report.late_replies == report.dropped_steps and len(report.first_dropped_times_s) == 20


def test_the_c_harness_refuses_frames_that_break_the_contract(built_07):
    """The C side (fsw_sil.c) answers a STEP before RESET, and a frame of
    another contract version, with ERROR and exit status 5."""
    import os
    import secrets
    import struct

    from spacemissionstudio.sil import contract as c
    from spacemissionstudio.sil.transport import Listener

    program = _program(built_07, "fsw_host")
    info = subprocess.run([str(program), "info"], capture_output=True, text=True)  # noqa: S603
    assert "inputs (2)" in info.stdout
    for frame, reason in ((c.encode_frame(c.Frame(c.FrameType.STEP, 1, 0, b"")), "STEP before RESET"),
                          (None, "version 2")):
        listener = Listener("tcp")
        token = secrets.token_hex(16)
        process = subprocess.Popen([str(program), "sil", listener.address], env={**os.environ, c.SESSION_VARIABLE: token},  # noqa: S603
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            transport = listener.accept(10.0)
            frame_in = transport.receive(c.HEADER_SIZE, 10.0)
            kind, _, length, _, _ = c.decode_header(frame_in)
            hello = c.decode_hello(transport.receive(length, 10.0))
            assert kind == c.FrameType.HELLO and hello.token == token and hello.name == "sat-1"
            transport.send(c.encode_frame(c.Frame(c.FrameType.HELLO_ACK, 0, 0)))
            if frame is None:
                frame = bytearray(c.encode_frame(c.Frame(c.FrameType.RESET, 1, 0, b"")))
                frame[4:6] = struct.pack("<H", 2)
            transport.send(bytes(frame))
            kind, _, length, _, _ = c.decode_header(transport.receive(c.HEADER_SIZE, 10.0))
            assert kind == c.FrameType.ERROR and reason in transport.receive(length, 10.0).decode()
            assert process.wait(timeout=10.0) == 5
        finally:
            process.kill()
            process.wait()
            listener.close()


def test_the_cli_runs_sil_writes_the_report_and_gates_on_the_error(built_07, tmp_path, capsys):
    """``sil`` prints the summary and writes the JSON report and residual
    CSV; with --max-error it exits 2 when an output was never written."""
    from spacemissionstudio import cli
    from spacemissionstudio.sil.report import SilReport

    scenario_path = tmp_path / "s.json"
    scenario = _template("07", 1)
    scenario.save(scenario_path)
    report_path = tmp_path / "sil.json"
    assert cli.main(["sil", str(scenario_path), "--spacecraft", "sat-1", "--binary", str(_program(built_07, "fsw_host")),
                     "--report", str(report_path), "--residuals-csv", str(tmp_path / "r.csv"), "--max-error",
                     "0"]) == 0
    out = capsys.readouterr().out
    assert "61 steps, 0 dropped" in out and "largest |residual| 0 " in out
    assert SilReport.from_json(report_path.read_text()).completed and (tmp_path / "r.csv").is_file()
    assert cli.main(["sil", str(scenario_path), "--spacecraft", "sat-1", "--binary",
                     str(_program(built_07, "fsw_adapter_host")), "--max-error", "1"]) == 2
    assert "never written" in capsys.readouterr().err


@pytest.mark.requires_gui
def test_the_gui_worker_reports_the_comparison_then_the_result(built_07, qapp):
    """RunWorker with a SIL request: sil_report (the comparison) before
    finished_ok (the normal results); a refused program gives sil_report
    with the reason, then failed."""
    from spacemissionstudio.gui.run_worker import RunWorker
    from spacemissionstudio.sil.runner import SilOptions

    events = []
    worker = RunWorker(_template("07", 1), sil=("sat-1", SilOptions(str(_program(built_07, "fsw_host")))))
    worker.sil_report.connect(lambda report, failure: events.append(("report", report.steps, failure)))
    worker.finished_ok.connect(lambda result, summary: events.append(("finished", len(result.series) > 0)))
    worker.failed.connect(lambda message: events.append(("failed", message)))
    worker.run()  # on this thread: the signals are delivered at once
    assert events == [("report", 61, ""), ("finished", True)]
    events.clear()
    worker = RunWorker(_template("13", 1), sil=("sat-1", SilOptions(str(_program(built_07, "fsw_host")))))
    worker.sil_report.connect(lambda report, failure: events.append(("report", failure)))
    worker.failed.connect(lambda message: events.append(("failed", message)))
    worker.run()
    assert [e[0] for e in events] == ["report", "failed"] and "does not match" in events[1][1]
