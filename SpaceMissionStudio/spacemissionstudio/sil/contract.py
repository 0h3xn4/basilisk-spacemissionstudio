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

"""The SIL transport contract, version 1: frames and their payloads.

The normative description is ``SIL_CONTRACT.md`` (in
``fsw_export/templates/`` and in every export); this module and the C
harness (``generated/fsw_sil.c``) both implement it, and the tests check
each against the other. Pure Python, no Basilisk.

Every frame is a 28-byte little-endian header and a payload::

    offset  size  field
    0       4     magic "SMSL"
    4       2     contract version (1)
    6       2     frame type
    8       4     sequence number
    12      4     payload length in bytes (at most MAX_PAYLOAD)
    16      8     simulation time [ns]
    24      4     CRC-32 of the payload (as zlib.crc32)
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Sequence, Tuple

CONTRACT_VERSION = 1
MAGIC = b"SMSL"
HEADER = struct.Struct("<4sHHIIQI")
HEADER_SIZE = HEADER.size  # 28 bytes
MAX_PAYLOAD = 16 * 1024 * 1024  # bytes
SESSION_VARIABLE = "SMS_SIL_TOKEN"  # the environment variable that carries the session token
TOKEN_LENGTH = 32  # hex characters
DIGEST_LENGTH = 64  # hex characters; all zeros when the flight software has no SpaceMissionStudio configuration
UNKNOWN_DIGEST = "0" * DIGEST_LENGTH


class FrameType(IntEnum):
    HELLO = 1  # flight software -> simulation: who it is and its ports
    HELLO_ACK = 2  # simulation -> flight software: the ports match
    RESET = 3  # simulation -> flight software: inputs written at reset; reset the flight software
    RESET_ACK = 4  # flight software -> simulation
    STEP = 5  # simulation -> flight software: this step's inputs; run one step
    OUTPUT = 6  # flight software -> simulation: the step's outputs and telemetry
    ERROR = 7  # either way: a message, then the sender closes
    BYE = 8  # simulation -> flight software, answered with BYE: the run is over


class SilError(RuntimeError):
    """A SIL run cannot go on; the message says why."""


class ContractError(SilError):
    """A frame or handshake that does not follow the contract."""


@dataclass(frozen=True)
class Frame:
    type: FrameType
    seq: int
    time_ns: int
    payload: bytes = b""


def encode_frame(frame: Frame) -> bytes:
    if len(frame.payload) > MAX_PAYLOAD:
        raise ContractError(f"payload of {len(frame.payload)} bytes is over the {MAX_PAYLOAD}-byte limit")
    return HEADER.pack(MAGIC, CONTRACT_VERSION, int(frame.type), frame.seq & 0xFFFFFFFF, len(frame.payload),
                       frame.time_ns, zlib.crc32(frame.payload)) + frame.payload


def decode_header(data: bytes) -> Tuple[FrameType, int, int, int, int]:
    """``(type, seq, length, time_ns, crc)``; raises :class:`ContractError`
    for a wrong magic, contract version, type or length."""
    magic, version, kind, seq, length, time_ns, crc = HEADER.unpack(data)
    if magic != MAGIC:
        raise ContractError(f"not a SIL frame (magic {magic!r}, expected {MAGIC!r})")
    if version != CONTRACT_VERSION:
        raise ContractError(f"the flight software speaks SIL contract version {version}; "
                            f"this SpaceMissionStudio speaks version {CONTRACT_VERSION}")
    try:
        frame_type = FrameType(kind)
    except ValueError:
        raise ContractError(f"unknown frame type {kind}") from None
    if length > MAX_PAYLOAD:
        raise ContractError(f"frame payload of {length} bytes is over the {MAX_PAYLOAD}-byte limit")
    return frame_type, seq, length, time_ns, crc


def check_crc(payload: bytes, crc: int) -> None:
    if zlib.crc32(payload) != crc:
        raise ContractError("frame payload fails its CRC-32")


# ----------------------------------------------------------------------------- HELLO


@dataclass(frozen=True)
class PortSpec:
    """One port as both sides describe it."""
    name: str
    message_type: str
    size: int  # bytes
    layout_hash: str  # 16 hex digits (fsw_export.model.layout_hash)


@dataclass
class Hello:
    token: str  # what the simulation put in SESSION_VARIABLE
    name: str  # the flight software's own name
    config_digest: str  # 64 hex digits, or UNKNOWN_DIGEST
    rate_ns: int  # the step the flight software expects
    inputs: List[PortSpec] = field(default_factory=list)
    outputs: List[PortSpec] = field(default_factory=list)
    telemetry: List[PortSpec] = field(default_factory=list)


def _short_text(text: str, what: str) -> bytes:
    data = text.encode("utf-8")
    if len(data) > 255:
        raise ContractError(f"{what} is longer than 255 bytes")
    return bytes([len(data)]) + data


def encode_hello(hello: Hello) -> bytes:
    if len(hello.token) != TOKEN_LENGTH or len(hello.config_digest) != DIGEST_LENGTH:
        raise ContractError("token or configuration digest has the wrong length")
    name = hello.name.encode("utf-8")
    if len(name) > 0xFFFF:
        raise ContractError("name is too long")
    out = bytearray(hello.token.encode("ascii") + struct.pack("<H", len(name)) + name)
    out += hello.config_digest.encode("ascii") + struct.pack("<QIII", hello.rate_ns, len(hello.inputs),
                                                             len(hello.outputs), len(hello.telemetry))
    for port in hello.inputs + hello.outputs + hello.telemetry:
        if len(port.layout_hash) != 16:
            raise ContractError(f"{port.name}: a layout hash has 16 hex digits")
        out += _short_text(port.name, "a port name") + _short_text(port.message_type, "a message type")
        out += struct.pack("<I", port.size) + port.layout_hash.encode("ascii")
    return bytes(out)


class _Reader:
    def __init__(self, data: bytes):
        self.data, self.at = data, 0

    def take(self, n: int) -> bytes:
        if self.at + n > len(self.data):
            raise ContractError("HELLO is truncated")
        chunk = self.data[self.at:self.at + n]
        self.at += n
        return chunk

    def unpack(self, fmt: str):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))

    def ascii(self, n: int) -> str:
        try:
            return self.take(n).decode("ascii")
        except UnicodeDecodeError:
            raise ContractError("HELLO holds a non-ASCII token, digest or layout hash") from None

    def text(self, n: int) -> str:
        try:
            return self.take(n).decode("utf-8")
        except UnicodeDecodeError:
            raise ContractError("HELLO holds a name that is not UTF-8") from None


def decode_hello(data: bytes) -> Hello:
    r = _Reader(data)
    token = r.ascii(TOKEN_LENGTH)
    (name_length,) = r.unpack("<H")
    name = r.text(name_length)
    digest = r.ascii(DIGEST_LENGTH)
    rate_ns, n_in, n_out, n_tlm = r.unpack("<QIII")
    if n_in + n_out + n_tlm > 4096:
        raise ContractError("HELLO declares more than 4096 ports")
    ports = []
    for _ in range(n_in + n_out + n_tlm):
        (length,) = r.unpack("<B")
        port_name = r.text(length)
        (length,) = r.unpack("<B")
        message_type = r.text(length)
        (size,) = r.unpack("<I")
        ports.append(PortSpec(port_name, message_type, size, r.ascii(16)))
    if r.at != len(data):
        raise ContractError(f"HELLO has {len(data) - r.at} bytes after its last port")
    return Hello(token, name, digest, rate_ns, ports[:n_in], ports[n_in:n_in + n_out], ports[n_in + n_out:])


def port_mismatches(expected: Sequence[PortSpec], actual: Sequence[PortSpec], kind: str) -> List[str]:
    """Each way ``actual`` differs from ``expected`` (names, order, types,
    sizes, layout hashes), as sentences; empty when they match."""
    problems = []
    if len(actual) != len(expected):
        problems.append(f"{kind}: the flight software has {len(actual)} ports, the simulation {len(expected)}")
    for index, (want, got) in enumerate(zip(expected, actual)):
        if got.name != want.name:
            problems.append(f"{kind} {index}: named {got.name!r}, expected {want.name!r}")
        elif got.message_type != want.message_type:
            problems.append(f"{kind} {want.name}: carries {got.message_type}, expected {want.message_type}")
        elif got.size != want.size or got.layout_hash != want.layout_hash:
            problems.append(f"{kind} {want.name}: {want.message_type} payload of {got.size} bytes, layout "
                            f"{got.layout_hash}; the simulation's is {want.size} bytes, layout {want.layout_hash}")
    return problems


# ----------------------------------------------------------------------------- RESET, STEP, OUTPUT


def encode_payloads(ports: Sequence[PortSpec], payloads: Sequence[Optional[bytes]]) -> bytes:
    """Per port, in order: a written flag (0 or 1), then the payload's
    bytes (zeros when not written)."""
    out = bytearray()
    for port, payload in zip(ports, payloads):
        if payload is None:
            out += b"\x00" + bytes(port.size)
        else:
            if len(payload) != port.size:
                raise ContractError(f"{port.name}: payload of {len(payload)} bytes, expected {port.size}")
            out += b"\x01" + payload
    return bytes(out)


def decode_payloads(ports: Sequence[PortSpec], data: bytes, what: str) -> List[Optional[bytes]]:
    expected = sum(1 + p.size for p in ports)
    if len(data) != expected:
        raise ContractError(f"{what} carries {len(data)} bytes of payloads, the ports need {expected}")
    out, at = [], 0
    for port in ports:
        flag = data[at]
        if flag not in (0, 1):
            raise ContractError(f"{what}: {port.name} has written flag {flag}")
        out.append(data[at + 1:at + 1 + port.size] if flag else None)
        at += 1 + port.size
    return out


OUTPUT_PREFIX = struct.Struct("<Q")  # the flight software's own step execution time [ns]


def encode_output(execution_ns: int, ports: Sequence[PortSpec], payloads: Sequence[Optional[bytes]]) -> bytes:
    return OUTPUT_PREFIX.pack(execution_ns) + encode_payloads(ports, payloads)


def decode_output(ports: Sequence[PortSpec], data: bytes) -> Tuple[int, List[Optional[bytes]]]:
    if len(data) < OUTPUT_PREFIX.size:
        raise ContractError("OUTPUT is shorter than its execution-time field")
    (execution_ns,) = OUTPUT_PREFIX.unpack_from(data)
    return execution_ns, decode_payloads(ports, data[OUTPUT_PREFIX.size:], "OUTPUT")


def error_text(payload: bytes) -> str:
    return payload.decode("utf-8", "replace")[:2000]
