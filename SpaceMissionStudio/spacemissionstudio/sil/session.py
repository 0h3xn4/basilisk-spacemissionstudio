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

"""The simulation side of the SIL contract: handshake, reset, lock-step
steps, deadlines and timeouts (``SIL_CONTRACT.md`` sections 4 to 8).
Pure Python over a :class:`.transport.Transport`; no Basilisk."""

from __future__ import annotations

import hmac
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .contract import (HEADER_SIZE, ContractError, Frame, FrameType, Hello, PortSpec, SilError, check_crc,
                       decode_header, decode_hello, decode_output, encode_frame, encode_payloads, error_text,
                       port_mismatches)
from .transport import SilLinkClosed, SilTimeout, Transport


@dataclass
class Timeouts:
    handshake_s: float = 30.0  # [s] to connect and send HELLO
    step_s: float = 10.0  # [s] without any answer: the run fails
    deadline_s: Optional[float] = None  # [s] an OUTPUT later than this is a dropped step; None: no deadline
    bye_s: float = 5.0  # [s] for the BYE answer, then the program is stopped


@dataclass
class StepReply:
    execution_ns: int  # the flight software's own step time [ns]
    round_trip_ns: int  # STEP sent to OUTPUT received, on this side [ns]
    outputs: List[Optional[bytes]] = field(default_factory=list)
    telemetry: List[Optional[bytes]] = field(default_factory=list)


@dataclass
class Expected:
    """The flight software this simulation needs."""
    inputs: List[PortSpec]
    outputs: List[PortSpec]
    telemetry: List[PortSpec]
    rate_ns: int


class SimulationSide:
    """Drives one session. Every failure is a :class:`SilError` whose
    message says what happened; the caller then stops the program."""

    def __init__(self, transport: Transport, token: str, expected: Expected, timeouts: Timeouts,
                 describe_exit=lambda: ""):
        self.transport = transport
        self.token = token
        self.expected = expected
        self.timeouts = timeouts
        self.hello: Optional[Hello] = None
        self.late_replies = 0  # OUTPUTs that arrived after their step's deadline
        self._seq = 0
        self._last_heard = time.perf_counter()
        self._header = None
        self._describe_exit = describe_exit  # e.g. "the program exited with status 70: <stderr>"

    # ------------------------------------------------------------------ frames

    def _send(self, kind: FrameType, time_ns: int, payload: bytes = b"", seq: Optional[int] = None) -> int:
        if seq is None:
            seq, self._seq = self._seq, self._seq + 1
        try:
            self.transport.send(encode_frame(Frame(kind, seq, time_ns, payload)), self.timeouts.step_s)
        except SilTimeout:
            raise SilError(f"the flight software took no {kind.name} for {self.timeouts.step_s:.3g} s") from None
        return seq

    def send_error(self, text: str) -> None:
        try:
            self._send(FrameType.ERROR, 0, text.encode("utf-8")[:4000])
        except SilError:
            pass

    def _closed(self, exc: SilLinkClosed) -> SilError:
        detail = self._describe_exit()
        return SilError(f"{exc}{': ' + detail if detail else ''}")

    def _receive(self, timeout_s: Optional[float]) -> Frame:
        """One frame; a broken frame is answered with ERROR and raised."""
        start = time.perf_counter()
        try:
            if self._header is None:  # a header whose payload timed out is kept for the next call
                header = self.transport.receive(HEADER_SIZE, timeout_s)
                try:
                    self._header = decode_header(header)
                except ContractError as exc:
                    self.send_error(str(exc))
                    raise
            kind, seq, length, time_ns, crc = self._header
            remaining = None if timeout_s is None else max(0.0, timeout_s - (time.perf_counter() - start))
            payload = self.transport.receive(length, remaining) if length else b""
            self._header = None
            try:
                check_crc(payload, crc)
            except ContractError as exc:
                self.send_error(str(exc))
                raise
        except SilLinkClosed as exc:
            raise self._closed(exc) from None
        self._last_heard = time.perf_counter()
        if kind == FrameType.ERROR:
            raise SilError(f"the flight software reported an error: {error_text(payload)}")
        return Frame(kind, seq, time_ns, payload)

    def _protocol_error(self, text: str) -> SilError:
        self.send_error(text)
        return ContractError(text)

    # ------------------------------------------------------------------ session

    def handshake(self) -> Hello:
        """Waits for HELLO and checks it; HELLO_ACK, or ERROR and raise."""
        try:
            frame = self._receive(self.timeouts.handshake_s)
        except SilTimeout:
            raise SilError(f"the flight software sent no HELLO within {self.timeouts.handshake_s:.3g} s") from None
        if frame.type != FrameType.HELLO:
            raise self._protocol_error(f"expected HELLO, received {frame.type.name}")
        try:
            hello = decode_hello(frame.payload)
        except ContractError as exc:
            self.send_error(str(exc))
            raise
        if not hmac.compare_digest(hello.token.encode(), self.token.encode()):
            raise self._protocol_error("HELLO carries the wrong session token: this is not the program the "
                                       "simulation started")
        problems = []
        if hello.rate_ns != self.expected.rate_ns:
            problems.append(f"the flight software runs every {hello.rate_ns * 1e-9:.9g} s, the simulation's flight "
                            f"software every {self.expected.rate_ns * 1e-9:.9g} s")
        problems += port_mismatches(self.expected.inputs, hello.inputs, "input")
        problems += port_mismatches(self.expected.outputs, hello.outputs, "output")
        problems += port_mismatches(self.expected.telemetry, hello.telemetry, "telemetry")
        if problems:
            text = "the flight software does not match this spacecraft: " + "; ".join(problems)
            self.send_error(text)
            raise ContractError(text)
        self._send(FrameType.HELLO_ACK, 0, seq=frame.seq)
        self.hello = hello
        return hello

    def _await_reply(self, kind: FrameType, seq: int, time_ns: int, timeout_s: float) -> Frame:
        end = time.perf_counter() + timeout_s
        while True:
            frame = self._receive(max(0.0, end - time.perf_counter()))
            if frame.type == FrameType.OUTPUT and frame.seq < seq:
                continue  # a step answered after its deadline: already counted as dropped
            if frame.type != kind or frame.seq != seq:
                raise self._protocol_error(f"expected {kind.name} for frame {seq}, received {frame.type.name} "
                                           f"for frame {frame.seq}")
            if frame.time_ns != time_ns:
                raise self._protocol_error(f"{kind.name} for frame {seq} carries time {frame.time_ns} ns, "
                                           f"expected {time_ns} ns")
            return frame

    def reset(self, time_ns: int, inputs: Sequence[Optional[bytes]]) -> None:
        seq = self._send(FrameType.RESET, time_ns, encode_payloads(self.expected.inputs, inputs))
        try:
            self._await_reply(FrameType.RESET_ACK, seq, time_ns, self.timeouts.step_s)
        except SilTimeout:
            raise SilError(f"the flight software did not answer RESET within {self.timeouts.step_s:.3g} s") from None

    def step(self, time_ns: int, inputs: Sequence[Optional[bytes]]) -> Optional[StepReply]:
        """The step's outputs, or ``None`` when they missed the deadline
        (a dropped step). Raises :class:`SilError` after ``step_s`` with no
        answer at all."""
        sent = time.perf_counter_ns()
        seq = self._send(FrameType.STEP, time_ns, encode_payloads(self.expected.inputs, inputs))
        wait = self.timeouts.deadline_s if self.timeouts.deadline_s is not None else self.timeouts.step_s
        try:
            frame = self._await_reply(FrameType.OUTPUT, seq, time_ns, wait)
        except SilTimeout:
            silent = time.perf_counter() - self._last_heard
            if self.timeouts.deadline_s is None or silent >= self.timeouts.step_s:
                raise SilError(f"the flight software did not answer for {silent:.3g} s (step at "
                               f"t = {time_ns * 1e-9:.9g} s)") from None
            self.late_replies += 1
            return None
        round_trip = time.perf_counter_ns() - sent
        if self.timeouts.deadline_s is not None and round_trip > self.timeouts.deadline_s * 1e9:
            # Measured late although the wait did not run out: a wait is only
            # as fine as the system's timer (about 15.6 ms on Windows).
            self.late_replies += 1
            return None
        try:
            execution_ns, payloads = decode_output(self.expected.outputs + self.expected.telemetry, frame.payload)
        except ContractError as exc:
            self.send_error(str(exc))
            raise
        n = len(self.expected.outputs)
        return StepReply(execution_ns, round_trip, payloads[:n], payloads[n:])

    def bye(self) -> bool:
        """Ends the session; True when the flight software answered BYE."""
        try:
            seq = self._send(FrameType.BYE, 0)
            end = time.perf_counter() + self.timeouts.bye_s
            while True:
                frame = self._receive(max(0.0, end - time.perf_counter()))
                if frame.type == FrameType.BYE and frame.seq == seq:
                    return True
                if frame.type != FrameType.OUTPUT:
                    return False
        except SilError:
            return False
