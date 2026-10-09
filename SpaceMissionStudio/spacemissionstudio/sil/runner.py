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

"""Runs a spacecraft's flight software as an external program,
software-in-the-loop, against the Basilisk dynamics (SRS-F-19).

The scenario runs as it always does (results, plots, Vizard), with three
additions:

* **The bridge**, a SysModel added right after the spacecraft's last
  flight-software module (:class:`_BridgeSimulation` adds it as the
  service builds the task, so it runs at that module's priority, next in
  order). Each step it reads the inputs as the modules read them, sends
  them to the program, waits for its outputs, compares them with what the
  modules just wrote, and writes the program's actuator commands into
  the modules' output messages, which the actuators read.
* **The reset tap**, last in the task, which keeps the inputs as they
  stand once every model has reset (the program's RESET).
* **The comparison** (:mod:`.report`).

The spacecraft's own modules keep running: they are the reference, and
they see the same inputs as the program. The program flies the
spacecraft through its commands. The same-step latency holds because
:func:`..fsw_export.capture.read_graph` refuses a chain where any model
between the first and the last module would see a difference.
"""

from __future__ import annotations

import copy
import ctypes
import hashlib
import os
import secrets
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from .contract import CONTRACT_VERSION, SESSION_VARIABLE, UNKNOWN_DIGEST, PortSpec, SilError
from .report import Comparator, SilReport, timing_summary
from .session import Expected, SimulationSide, Timeouts
from .transport import Listener

_LOG_TAIL = 4000  # characters of the program's output kept in the report


@dataclass
class SilOptions:
    binary: str
    timeouts: Timeouts = field(default_factory=Timeouts)
    transport: str = "auto"  # "auto", "unix" or "tcp"
    expected_sha256: Optional[str] = None  # what the user agreed to run; checked again before launch


class SilCancelled(Exception):
    """The user stopped the run; what was simulated and compared so far."""

    def __init__(self, partial_result, report: SilReport):
        super().__init__("SIL run cancelled")
        self.partial_result = partial_result
        self.report = report


class SilRunError(SilError):
    """The run failed; ``report`` holds what was measured and the program's output."""

    def __init__(self, message: str, report: Optional[SilReport]):
        super().__init__(message)
        self.report = report


def file_sha256(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_binary(path) -> Path:
    """The program as an absolute path, or :class:`SilError` saying why it
    cannot be run."""
    binary = Path(path).expanduser()
    if not binary.is_file():
        raise SilError(f"{binary} is not a file")
    if sys.platform != "win32" and not os.access(binary, os.X_OK):
        raise SilError(f"{binary} is not executable")
    return binary.resolve()


def check_runnable(scenario, spacecraft_name: str) -> None:
    """:class:`SilError` when this scenario's spacecraft cannot be run in
    the loop."""
    from ..engine import long_run
    from ..fsw_export.capture import CaptureError, check_exportable

    try:
        check_exportable(scenario, spacecraft_name)
    except CaptureError as exc:
        raise SilError(str(exc)) from None
    if long_run.needs_segments(scenario):
        raise SilError("SIL runs one simulation; this run is longer than one segment. Shorten the duration.")


def _bytes_at(address: int, size: int) -> bytes:
    return ctypes.string_at(address, size)


def _port_specs(graph, ports) -> List[PortSpec]:
    return [PortSpec(p.name, p.message_type, graph.message_types[p.message_type].size,
                     graph.message_types[p.message_type].hash) for p in ports]


def _make_classes():
    """The Basilisk-side classes, defined only once Basilisk is imported."""
    from Basilisk.architecture import messaging, sysModel
    from Basilisk.utilities import SimulationBaseClass

    class Bridge(sysModel.SysModel):
        def __init__(self):
            super().__init__()
            self.ModelTag = "silBridge"
            self.pending = True  # not yet in the task
            self.failure: Optional[BaseException] = None
            self.session: Optional[SimulationSide] = None

        def configure(self, graph, session, comparator, reset_tap, report):
            self.session, self.comparator, self.reset_tap, self.report = session, comparator, reset_tap, report
            self.inputs = [graph.input_source[p.name] for p in graph.inputs]
            keys = [p.producer for p in graph.outputs + graph.telemetry]
            self.reference = [graph.output_sizes[k] for k in keys]
            self.writers = []
            for port in graph.outputs:
                container = graph.output_container[port.producer]
                producer = next(m for m in graph.fsw_models if graph.names[id(m)] == port.producer.split(".")[0])
                payload = getattr(messaging, f"{port.message_type}MsgPayload")()
                self.writers.append((container, payload, int(payload.this), graph.message_types[port.message_type].size,
                                     int(producer.moduleID)))
            self.held = [bytes(size) for _, _, _, size, _ in self.writers]
            self.reset_sent = False
            self.round_trips: List[int] = []
            self.executions: List[int] = []

        def UpdateState(self, CurrentSimNanos):  # noqa: N802,N803 -- Basilisk's names
            if self.session is None or self.failure is not None:
                return
            try:
                self._step(int(CurrentSimNanos))
            except BaseException as exc:
                self.failure = exc
                raise

        def _step(self, time_ns: int) -> None:
            if not self.reset_sent:
                self.session.reset(self.reset_tap.time_ns, self.reset_tap.payloads)
                self.reset_sent = True
            reply = self.session.step(time_ns, [_bytes_at(a, s) for a, s in self.inputs])
            if reply is None:
                self.report.dropped_steps += 1
                if len(self.report.first_dropped_times_s) < 20:
                    self.report.first_dropped_times_s.append(time_ns * 1e-9)
            else:
                reference = [_bytes_at(a, s) for a, s in self.reference]
                self.comparator.add(time_ns * 1e-9, reply.outputs + reply.telemetry, reference)
                self.round_trips.append(reply.round_trip_ns)
                self.executions.append(reply.execution_ns)
                for i, payload in enumerate(reply.outputs):
                    if payload is not None:
                        self.held[i] = payload
            for (container, payload, address, size, module_id), data in zip(self.writers, self.held):
                ctypes.memmove(address, data, size)
                container.write(payload, time_ns, module_id)

    class ResetTap(sysModel.SysModel):
        """Last in the task: the inputs once every model has reset."""

        def __init__(self, graph):
            super().__init__()
            self.ModelTag = "silBridgeResetTap"
            self.graph = graph
            self.payloads: List[Optional[bytes]] = []
            self.time_ns = 0
            self.done = False

        def Reset(self, CurrentSimNanos):  # noqa: N802,N803 -- Basilisk's names
            if self.done:
                return
            self.done = True
            self.time_ns = int(CurrentSimNanos)
            for port in self.graph.inputs:
                container, address, size = self.graph.input_container[port.name]
                written = bool(container.headerPointer.isWritten)
                self.payloads.append(_bytes_at(address, size) if written else None)

    def simulation_class(after_tag: str, bridge):
        class BridgeSimulation(SimulationBaseClass.SimBaseClass):
            """SimBaseClass that adds ``bridge`` right after the model
            tagged ``after_tag``, at that model's priority."""

            def AddModelToTask(self, TaskName, NewModel, ModelData=None, ModelPriority=-1):  # noqa: N802,N803
                super().AddModelToTask(TaskName, NewModel, ModelData, ModelPriority)
                if bridge.pending and str(getattr(NewModel, "ModelTag", "")) == after_tag:
                    bridge.pending = False
                    priority = ModelData if isinstance(ModelData, int) else ModelPriority
                    super().AddModelToTask(TaskName, bridge, priority)

        return BridgeSimulation

    return Bridge, ResetTap, simulation_class


class _Program:
    """The external flight software as a child process."""

    def __init__(self, binary: Path, address: str, token: str):
        self.log_dir = tempfile.TemporaryDirectory(prefix="sms-sil-log-")
        self.log_path = Path(self.log_dir.name) / "fsw.log"
        self._log = self.log_path.open("wb")
        env = dict(os.environ)
        env[SESSION_VARIABLE] = token
        self.process = subprocess.Popen(  # noqa: S603 -- no shell; the path the user confirmed, two fixed arguments
            [str(binary), "sil", address], cwd=str(binary.parent), env=env, stdin=subprocess.DEVNULL,
            stdout=self._log, stderr=subprocess.STDOUT)

    def exit_reason(self) -> Optional[str]:
        code = self.process.poll()
        if code is None:
            return None
        tail = self.log_tail().strip().splitlines()
        return f"the program exited with status {code}" + (f" ({tail[-1]})" if tail else "")

    def log_tail(self) -> str:
        try:
            self._log.flush()
            data = self.log_path.read_bytes()
        except OSError:
            return ""
        return data[-_LOG_TAIL:].decode("utf-8", "replace")

    def stop(self, wait_s: float) -> None:
        if self.process.poll() is None:
            try:
                self.process.wait(timeout=wait_s)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5.0)

    def close(self) -> None:
        self._log.close()
        self.log_dir.cleanup()


def run_sil(scenario, spacecraft_name: str, options: SilOptions, vizard_request=None,
            on_progress: Optional[Callable] = None, should_cancel: Optional[Callable[[], bool]] = None):
    """Runs ``scenario`` with ``spacecraft_name``'s flight software in
    ``options.binary``. Returns ``(ResultSet, SilReport)``; raises
    :class:`SilRunError` (with the report so far) when the run fails, and
    :class:`SilCancelled` when ``should_cancel`` stops it."""
    binary = check_binary(options.binary)
    sha256 = file_sha256(binary)
    if options.expected_sha256 is not None and sha256 != options.expected_sha256:
        raise SilError(f"{binary} changed after you confirmed it (SHA-256 {sha256[:16]}..., confirmed "
                       f"{options.expected_sha256[:16]}...); start the run again")

    from ..engine.service import SimulationCancelled, SimulationService
    from ..fsw_export.capture import CaptureError, read_graph
    from ..fsw_export.digest import fsw_config_digest

    check_runnable(scenario, spacecraft_name)
    run = copy.deepcopy(scenario)
    notes = []
    if run.mission_sequence:
        notes.append("mission sequence not run in SIL: the set duration only")
        run.mission_sequence = []
    if run.monte_carlo.enabled:
        notes.append("Monte Carlo off in SIL: one nominal run")
        run.monte_carlo.enabled = False

    Bridge, ResetTap, simulation_class = _make_classes()
    try:
        dry = SimulationService(copy.deepcopy(run))
        dry.build(initialize=False)
        last_tag = read_graph(dry, spacecraft_name).last_tag
        del dry
        bridge = Bridge()
        service = SimulationService(run, vizard_request=vizard_request,
                                    simulation_class=simulation_class(last_tag, bridge))
        service.build(initialize=False)
        if bridge.pending:
            raise SilError(f"the SIL bridge could not be placed after {last_tag}")
        graph = read_graph(service, spacecraft_name)
    except CaptureError as exc:
        raise SilError(str(exc)) from None

    expected = Expected(_port_specs(graph, graph.inputs), _port_specs(graph, graph.outputs),
                        _port_specs(graph, graph.telemetry), graph.rate_ns)
    scenario_digest = fsw_config_digest(scenario, spacecraft_name)
    report = SilReport(spacecraft=spacecraft_name, binary=str(binary), binary_sha256=sha256, fsw_name="",
                       fsw_config_digest="", scenario_config_digest=scenario_digest,
                       contract_version=CONTRACT_VERSION, rate_ns=graph.rate_ns, address_kind="", warnings=notes)
    layouts = {name: mtype.layout for name, mtype in graph.message_types.items()}
    duration_s = run.sim_settings.duration_days * 86400.0  # [s]
    comparator = Comparator(expected.outputs, expected.telemetry, layouts,
                            int(duration_s * 1e9 // graph.rate_ns) + 1)
    reset_tap = ResetTap(graph)
    service.scSim.AddModelToTask(service.dyn_task_name, reset_tap, -10**6)

    listener = Listener(options.transport)
    report.address_kind = listener.kind
    token = secrets.token_hex(16)
    program = _Program(binary, listener.address, token)
    session = None
    result = None
    try:
        try:
            transport = listener.accept(options.timeouts.handshake_s, program.exit_reason)
        except SilError as exc:
            raise SilError(f"{binary.name} did not connect: {exc}") from None
        session = SimulationSide(transport, token, expected, options.timeouts, program.exit_reason)
        hello = session.handshake()
        report.fsw_name = hello.name
        report.fsw_config_digest = hello.config_digest
        if hello.config_digest == UNKNOWN_DIGEST:
            report.warnings.append("not exported from SpaceMissionStudio (no configuration digest)")
        elif hello.config_digest != scenario_digest:
            report.warnings.append("stale export: built from another configuration than this scenario's")
        bridge.configure(graph, session, comparator, reset_tap, report)
        service.initialize()
        try:
            result = service.run_live(on_progress or (lambda partial, fraction: None), should_cancel=should_cancel)
        except SimulationCancelled as exc:
            _finish(report, bridge, comparator)
            report.warnings.append("cancelled before the end")
            session.bye()
            program.stop(options.timeouts.bye_s)
            raise SilCancelled(exc.partial_result, report) from None
        except Exception as exc:  # noqa: BLE001 -- the bridge's own failure is the one to report
            if bridge.failure is not None:
                raise SilError(str(bridge.failure)) from None
            raise SilError(f"the simulation failed: {exc}") from None
        _finish(report, bridge, comparator)
        report.completed = True
        session.bye()
        program.stop(options.timeouts.bye_s)
        return result, report
    except SilError as exc:
        if session is not None:
            session.send_error(f"the simulation stopped the run: {exc}")
        _finish(report, bridge, comparator)
        program.stop(0.5)
        report.log_tail = program.log_tail()
        raise SilRunError(str(exc), report) from None
    finally:
        program.stop(0.5)
        if not report.log_tail:
            report.log_tail = program.log_tail()
        if session is not None:
            session.transport.close()
        listener.close()
        program.close()


def _finish(report: SilReport, bridge, comparator: Comparator) -> None:
    comparator.finish(report)
    report.steps = comparator.steps + report.dropped_steps
    report.late_replies = bridge.session.late_replies if bridge.session is not None else 0
    report.round_trip = timing_summary(getattr(bridge, "round_trips", []))
    report.execution = timing_summary(getattr(bridge, "executions", []))
