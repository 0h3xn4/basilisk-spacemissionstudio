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

"""The SIL transport contract, version 1 (SRS-F-19, SIL_CONTRACT.md),
without Basilisk: the frames, HELLO and the payload blocks, and the
simulation side of a session over real sockets against a scripted flight
software (handshake, lock-step steps, a deadline, timeouts, a closed link,
an error from the flight software, wrong tokens, ports and versions)."""

import os
import socket
import stat
import struct
import sys
import threading
import time
import zlib

import pytest

from spacemissionstudio.sil import contract as c
from spacemissionstudio.sil.session import Expected, SimulationSide, Timeouts
from spacemissionstudio.sil.transport import Listener, SilTimeout

TOKEN = "0123456789abcdef0123456789abcdef"
IN = [c.PortSpec("nav_attOutMsg", "NavAtt", 8, "a" * 16), c.PortSpec("wheels_rwSpeedOutMsg", "RWSpeed", 4, "b" * 16)]
OUT = [c.PortSpec("rw_torqueOutMsg", "ArrayMotorTorque", 8, "c" * 16)]
TLM = [c.PortSpec("guid_attGuidOutMsg", "AttGuid", 8, "d" * 16)]
RATE_NS = 1_000_000_000  # [ns]
KINDS = ["unix", "tcp"] if sys.platform != "win32" else ["tcp"]


def _hello(**changes):
    fields = {"token": TOKEN, "name": "fake", "config_digest": c.UNKNOWN_DIGEST, "rate_ns": RATE_NS,
              "inputs": list(IN), "outputs": list(OUT), "telemetry": list(TLM)}
    fields.update(changes)
    return c.Hello(**fields)


def test_frames_round_trip_and_broken_headers_are_named():
    """A frame encodes to the 28-byte header of section 3 and back; a wrong
    magic, a later version, an unknown type, an oversized length and a
    corrupted payload are each refused with the reason."""
    data = c.encode_frame(c.Frame(c.FrameType.STEP, 7, 123456789, b"abc"))
    assert len(data) == c.HEADER_SIZE + 3 and data[:4] == b"SMSL"
    kind, seq, length, time_ns, crc = c.decode_header(data[:c.HEADER_SIZE])
    assert (kind, seq, length, time_ns, crc) == (c.FrameType.STEP, 7, 3, 123456789, zlib.crc32(b"abc"))
    c.check_crc(b"abc", crc)
    with pytest.raises(c.ContractError, match="CRC"):
        c.check_crc(b"abd", crc)
    header = bytearray(data[:c.HEADER_SIZE])
    for offset, value, reason in ((0, b"XXXX", "magic"), (4, struct.pack("<H", 2), "version 2"),
                                  (6, struct.pack("<H", 99), "unknown frame type"),
                                  (12, struct.pack("<I", c.MAX_PAYLOAD + 1), "limit")):
        broken = bytearray(header)
        broken[offset:offset + len(value)] = value
        with pytest.raises(c.ContractError, match=reason):
            c.decode_header(bytes(broken))
    assert c.decode_header(c.encode_frame(c.Frame(c.FrameType.BYE, 0, 0))[:c.HEADER_SIZE])[4] == 0  # empty: CRC 0


def test_hello_and_payload_blocks_round_trip_and_mismatches_are_listed():
    """HELLO carries the token, name, digest, step and every port; a
    truncated one is refused. Port checks name each difference. Payload
    blocks carry a written flag per port and refuse a wrong size."""
    hello = _hello(name="flight software é")
    assert c.decode_hello(c.encode_hello(hello)) == hello
    with pytest.raises(c.ContractError, match="truncated"):
        c.decode_hello(c.encode_hello(hello)[:-3])
    changed = [IN[0], c.PortSpec("wheels_rwSpeedOutMsg", "RWSpeed", 4, "e" * 16)]
    problems = c.port_mismatches(IN, changed, "input")
    assert len(problems) == 1 and "wheels_rwSpeedOutMsg" in problems[0] and "eeee" in problems[0]
    assert "has 1 ports" in c.port_mismatches(IN, IN[:1], "input")[0]
    assert "named 'x'" in c.port_mismatches(OUT, [c.PortSpec("x", "ArrayMotorTorque", 8, "c" * 16)], "output")[0]
    block = c.encode_payloads(IN, [b"\x01" * 8, None])
    assert block == b"\x01" + b"\x01" * 8 + b"\x00" + bytes(4)
    assert c.decode_payloads(IN, block, "STEP") == [b"\x01" * 8, None]
    with pytest.raises(c.ContractError, match="12 bytes"):
        c.decode_payloads(IN, block[:12], "STEP")
    with pytest.raises(c.ContractError, match="payload of 3 bytes"):
        c.encode_payloads(IN, [b"abc", None])
    execution, payloads = c.decode_output(OUT + TLM, c.encode_output(42, OUT + TLM, [b"\x02" * 8, None]))
    assert execution == 42 and payloads == [b"\x02" * 8, None]


class _FakeFlightSoftware(threading.Thread):
    """A scripted flight software: connects, says HELLO, then answers each
    frame (outputs = the first input's bytes), with optional faults."""

    def __init__(self, address, hello=None, delay_s=0.0, silent_after=None, close_after=None, error_after=None,
                 version=c.CONTRACT_VERSION):
        super().__init__(daemon=True)
        self.address, self.hello = address, hello or _hello()
        self.delay_s, self.silent_after, self.close_after, self.error_after = delay_s, silent_after, close_after, error_after
        self.version = version
        self.received = []
        self.steps = 0

    def _connect(self):
        if self.address.startswith("unix:"):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self.address[5:])
        else:
            host, port = self.address[4:].rsplit(":", 1)
            sock = socket.create_connection((host, int(port)))
        return sock

    def _read(self, sock):
        header = b""
        while len(header) < c.HEADER_SIZE:
            chunk = sock.recv(c.HEADER_SIZE - len(header))
            if not chunk:
                return None
            header += chunk
        kind, seq, length, time_ns, _ = c.decode_header(header)
        payload = b""
        while len(payload) < length:
            payload += sock.recv(length - len(payload))
        self.received.append(kind)
        return kind, seq, time_ns, payload

    def _send(self, sock, kind, seq, time_ns, payload=b""):
        data = bytearray(c.encode_frame(c.Frame(kind, seq, time_ns, payload)))
        data[4:6] = struct.pack("<H", self.version)
        sock.sendall(bytes(data))

    def run(self):
        sock = self._connect()
        try:
            self._send(sock, c.FrameType.HELLO, 0, 0, c.encode_hello(self.hello))
            while True:
                frame = self._read(sock)
                if frame is None:
                    return
                kind, seq, time_ns, payload = frame
                if kind in (c.FrameType.ERROR,):
                    return
                if kind == c.FrameType.RESET:
                    self._send(sock, c.FrameType.RESET_ACK, seq, time_ns)
                elif kind == c.FrameType.STEP:
                    self.steps += 1
                    if self.close_after is not None and self.steps > self.close_after:
                        return
                    if self.error_after is not None and self.steps > self.error_after:
                        self._send(sock, c.FrameType.ERROR, 99, 0, b"BSK_ERROR: wheel model diverged")
                        return
                    if self.silent_after is not None and self.steps > self.silent_after:
                        continue
                    time.sleep(self.delay_s)
                    inputs = c.decode_payloads(IN, payload, "STEP")
                    out = inputs[0] if inputs[0] is not None else bytes(8)
                    self._send(sock, c.FrameType.OUTPUT, seq, time_ns, c.encode_output(1000, OUT + TLM, [out, out]))
                elif kind == c.FrameType.BYE:
                    self._send(sock, c.FrameType.BYE, seq, time_ns)
                    return
        finally:
            sock.close()


def _session(kind, fake_kwargs=None, timeouts=None):
    listener = Listener(kind)
    fake = _FakeFlightSoftware(listener.address, **(fake_kwargs or {}))
    fake.start()
    transport = listener.accept(5.0)
    side = SimulationSide(transport, TOKEN, Expected(list(IN), list(OUT), list(TLM), RATE_NS),
                          timeouts or Timeouts(handshake_s=5.0, step_s=2.0))
    return listener, fake, side


@pytest.mark.parametrize("kind", KINDS)
def test_a_session_runs_lock_step_and_ends_with_bye(kind):
    """Handshake, RESET, three STEPs each answered with that step's outputs
    (the fake echoes its first input), then BYE answered with BYE."""
    listener, fake, side = _session(kind)
    try:
        assert side.handshake().name == "fake"
        side.reset(0, [None, None])
        for step in range(3):
            payload = struct.pack("<d", float(step))
            reply = side.step(step * RATE_NS, [payload, b"\x00" * 4])
            assert reply.outputs == [payload] and reply.telemetry == [payload]
            assert reply.execution_ns == 1000 and reply.round_trip_ns > 0
        assert side.bye()
    finally:
        side.transport.close()
        listener.close()
    fake.join(5.0)
    assert fake.received == [c.FrameType.HELLO_ACK, c.FrameType.RESET] + [c.FrameType.STEP] * 3 + [c.FrameType.BYE]


@pytest.mark.parametrize("hello, reason", [
    (_hello(token="f" * 32), "wrong session token"),
    (_hello(rate_ns=2 * RATE_NS), "runs every 2 s"),
    (_hello(outputs=[c.PortSpec("rw_torqueOutMsg", "ArrayMotorTorque", 16, "9" * 16)]), "16 bytes, layout 9999"),
    (_hello(telemetry=[]), "telemetry: the flight software has 0 ports"),
])
def test_a_flight_software_that_does_not_match_is_refused_with_error(hello, reason):
    """The simulation answers ERROR (the fake receives it) and raises,
    naming the difference: token, step, payload layout, port count."""
    listener, fake, side = _session(KINDS[0], {"hello": hello})
    try:
        with pytest.raises(c.ContractError, match=reason):
            side.handshake()
    finally:
        side.transport.close()
        listener.close()
    fake.join(5.0)
    assert fake.received == [c.FrameType.ERROR]


def test_a_flight_software_speaking_another_contract_version_is_refused():
    """A HELLO whose header says version 2 is refused at the first frame."""
    listener, fake, side = _session(KINDS[0], {"version": 2})
    try:
        with pytest.raises(c.ContractError, match="version 2"):
            side.handshake()
    finally:
        side.transport.close()
        listener.close()


def test_a_late_answer_is_a_dropped_step_and_is_discarded_when_it_arrives():
    """With a 50 ms deadline and a 200 ms flight software, a step returns
    None (dropped); the late OUTPUT is recognised by its sequence number and
    skipped, and the next step gets its own answer."""
    listener, fake, side = _session(KINDS[0], {"delay_s": 0.2},
                                    Timeouts(handshake_s=5.0, step_s=2.0, deadline_s=0.05))
    try:
        side.handshake()
        side.reset(0, [None, None])
        assert side.step(0, [struct.pack("<d", 1.0), bytes(4)]) is None
        assert side.late_replies == 1
        side.timeouts.deadline_s = None
        reply = side.step(RATE_NS, [struct.pack("<d", 2.0), bytes(4)])
        assert reply.outputs == [struct.pack("<d", 2.0)]
    finally:
        side.transport.close()
        listener.close()


@pytest.mark.parametrize("fake_kwargs, timeouts, reason", [
    ({"silent_after": 1}, Timeouts(handshake_s=5.0, step_s=0.3), "did not answer for"),
    ({"silent_after": 1}, Timeouts(handshake_s=5.0, step_s=0.3, deadline_s=0.05), None),
    ({"close_after": 1}, Timeouts(handshake_s=5.0, step_s=2.0), "closed the link"),
    ({"error_after": 1}, Timeouts(handshake_s=5.0, step_s=2.0), "reported an error: BSK_ERROR: wheel model diverged"),
])
def test_timeouts_closed_links_and_flight_software_errors_end_the_run_loudly(fake_kwargs, timeouts, reason):
    """No answer for step_s, a closed link and an ERROR from the flight
    software each raise SilError with the reason. With a deadline, missed
    deadlines are dropped steps until nothing at all has been heard for
    step_s; then it fails too."""
    listener, fake, side = _session(KINDS[0], fake_kwargs, timeouts)
    try:
        side.handshake()
        side.reset(0, [None, None])
        assert side.step(0, [bytes(8), bytes(4)]) is not None
        with pytest.raises(c.SilError, match=reason or "did not answer for"):
            for step in range(1, 100):
                side.step(step * RATE_NS, [bytes(8), bytes(4)])
    finally:
        side.transport.close()
        listener.close()


@pytest.mark.skipif(sys.platform == "win32", reason="Unix-domain sockets")
def test_the_unix_socket_is_private_and_removed_afterwards():
    """The socket's folder is 0700 and the socket 0600 (only this user can
    connect); both are gone after close."""
    listener = Listener("unix")
    path = listener.address[len("unix:"):]
    folder = os.path.dirname(path)
    assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    listener.close()
    assert not os.path.exists(folder)


def test_a_program_that_never_connects_or_exits_first_is_reported():
    """accept() gives up after its timeout, and at once when the program
    has already exited."""
    listener = Listener("tcp")
    try:
        with pytest.raises(SilTimeout, match="did not connect within"):
            listener.accept(0.2)
        with pytest.raises(c.SilError, match="exited with status 1"):
            listener.accept(5.0, lambda: "the program exited with status 1")
    finally:
        listener.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executable bit")
def test_a_program_changed_after_consent_is_refused(tmp_path):
    """The runner hashes the program again just before starting it: one
    replaced after the user confirmed its SHA-256 is never started, and a
    file that is not executable is refused (security analysis S-15)."""
    from spacemissionstudio.sil.runner import SilOptions, file_sha256, run_sil

    program = tmp_path / "fsw_host"
    marker = tmp_path / "started"
    program.write_text(f"#!/bin/sh\ntouch {marker}\n")
    program.chmod(0o755)
    confirmed = file_sha256(program)
    program.write_text(f"#!/bin/sh\ntouch {marker}\necho swapped\n")
    with pytest.raises(c.SilError, match="changed after you confirmed it"):
        run_sil(None, "sat-1", SilOptions(str(program), expected_sha256=confirmed))
    program.chmod(0o644)
    with pytest.raises(c.SilError, match="not executable"):
        run_sil(None, "sat-1", SilOptions(str(program)))
    assert not marker.exists()
