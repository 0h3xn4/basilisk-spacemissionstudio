# SIL transport contract, version 1

How SpaceMissionStudio (the **simulation**) runs a flight software (the
**flight software**: this export's `fsw_host`, the adapter's
`fsw_adapter_host`, or any program that follows this document)
software-in-the-loop, one step at a time against the Basilisk dynamics.

This document is the contract. Two implementations follow it and are
tested against each other: `spacemissionstudio/sil/contract.py` and
`spacemissionstudio/sil/session.py` (simulation side), and
`generated/fsw_sil.c` with `generated/fsw_transport_socket.c` (flight
software side).

## 1 Roles and start-up

1. The simulation creates a listening endpoint, starts the flight
   software as `<program> sil <address>` with the session token in the
   environment variable `SMS_SIL_TOKEN`, and waits for it to connect.
2. The flight software connects to `<address>` and sends `HELLO`.
3. The simulation checks `HELLO` (section 4) and answers `HELLO_ACK`, or
   `ERROR` with the reason, then closes.
4. The simulation sends `RESET` once, then one `STEP` per simulation
   step. The flight software answers each with `RESET_ACK` or `OUTPUT`.
5. At the end the simulation sends `BYE`; the flight software answers
   `BYE` and exits with status 0.

The program is started directly (no shell), with exactly these two
arguments, in the folder that holds it.

## 2 Addresses and transport

| Address | Meaning | Platforms |
|---|---|---|
| `unix:<path>` | Unix-domain stream socket at `<path>` | Linux, macOS |
| `tcp:127.0.0.1:<port>` | TCP on the loopback interface | every platform (the default on Windows) |

The simulation creates a Unix-domain socket in a new folder only its own
user can open (mode 0700; the socket itself mode 0600) and removes both at
the end. A TCP endpoint listens on 127.0.0.1 only; there, as everywhere,
the session token in `HELLO` is what tells the simulation that the
program it started is the one that connected.

The protocol needs a reliable, ordered byte stream and nothing else. A
serial line or a UDP link with its own framing can replace the socket:
on the flight-software side fill in an `FswTransport` (`generated/fsw_transport.h`:
`send`, `receive`, `close`) with your own functions; on the simulation
side implement `spacemissionstudio.sil.transport.Transport`.

## 3 Frames

All integers are little-endian. Every frame is a 28-byte header and a
payload:

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | magic, the ASCII bytes `SMSL` |
| 4 | 2 | contract version: `1` |
| 6 | 2 | frame type (table below) |
| 8 | 4 | sequence number |
| 12 | 4 | payload length in bytes, at most 16 777 216 |
| 16 | 8 | simulation time [ns] |
| 24 | 4 | CRC-32 of the payload (IEEE 802.3, as `zlib.crc32`; 0 for an empty payload) |

| Type | Name | From | Payload |
|---|---|---|---|
| 1 | `HELLO` | flight software | section 4 |
| 2 | `HELLO_ACK` | simulation | empty |
| 3 | `RESET` | simulation | input block (section 5) |
| 4 | `RESET_ACK` | flight software | empty |
| 5 | `STEP` | simulation | input block |
| 6 | `OUTPUT` | flight software | section 6 |
| 7 | `ERROR` | either | UTF-8 text, the reason |
| 8 | `BYE` | simulation, then flight software | empty |

**Sequence numbers.** Each side numbers the frames it starts from 0 up,
by one. A reply (`HELLO_ACK`, `RESET_ACK`, `OUTPUT`, the flight software's
`BYE`) carries the sequence number and the time of the frame it answers.

**Errors.** A receiver that finds a wrong magic, an unknown version or
type, a length over the limit, a failing CRC, a payload of the wrong size
or a frame it does not expect at that point sends `ERROR` with the reason
and closes the link. Either side may send `ERROR` at any time, for
instance when a flight-software module reports an error; the other side
reports the text and closes. There is no recovery inside a session.

**Versions.** The version in every header must equal the receiver's own.
A later contract version will change that number; a flight software built
for version 1 and a simulation that speaks version 2 refuse each other
with `ERROR` at the first frame.

## 4 HELLO and the port check

| Size | Field |
|---|---|
| 32 | session token, the ASCII value of `SMS_SIL_TOKEN` |
| 2 | name length *n* |
| *n* | the flight software's name, UTF-8 (shown to the user) |
| 64 | configuration digest, hex: the SpaceMissionStudio configuration hash the flight software was exported with, or 64 `0` |
| 8 | step [ns] the flight software runs at |
| 4, 4, 4 | number of input, output and telemetry ports |
| per port | 1 + name, 1 + message type (each a length byte, then UTF-8), 4 payload size [bytes], 16 layout hash (hex) |

Ports come in this order: inputs, outputs, telemetry, each in the order
of the export's ICD.

The simulation answers `HELLO_ACK` only when:

- the token is the one it gave this process;
- the step equals the simulation's flight-software step;
- the input, output and telemetry ports have the same names, in the same
  order, with the same message types, payload sizes and layout hashes as
  the spacecraft's own flight software in this scenario.

The layout hash (`spacemissionstudio.fsw_export.model.layout_hash`)
identifies a payload type together with its exact binary layout: field
names, offsets, element types and array shapes. Matching hashes mean the
payload bytes can be copied as they are. Otherwise the answer is `ERROR`
naming every mismatch.

A configuration digest different from the scenario's is not an error. The
simulation shows it, because the flight software then runs with other
parameters than the simulation's own modules.

## 5 RESET, STEP and the input block

The input block holds, for each input port in `HELLO` order, a written
flag (1 byte, `0` or `1`) and then the payload (the port's size in bytes;
zeros when the flag is 0).

- `RESET` (time: the reset time) carries the inputs as they stood when
  the simulation had reset every model. The flight software writes the
  ports whose flag is 1, then resets. A second `RESET` starts the flight
  software over.
- `STEP` (time: the step's time) carries the inputs of this step, as the
  simulation's own flight-software modules read them. The flight
  software writes the ports whose flag is 1, runs one step and answers
  `OUTPUT`.

## 6 OUTPUT

| Size | Field |
|---|---|
| 8 | the flight software's own execution time for this step [ns], from a monotonic clock |
| ... | the output block: output ports then telemetry ports, each a written flag and the payload, as in section 5 |

Latency is the same step: the simulation applies a step's outputs to the
actuators in that same step, where its own last flight-software module
runs (see "Timing" in the export's ICD).

## 7 What the simulation does with the outputs

- **Outputs** (actuator commands) replace the simulation's own commands,
  so the external flight software flies the spacecraft. An output whose
  flag is 0 leaves the previous command in place (zeros before the first).
- **Telemetry** is only compared.
- The spacecraft's own flight-software modules keep running on the same
  inputs (the reference). Every output and telemetry value is compared
  with them each step: residual = external - reference.

## 8 Deadlines and timeouts

- **Handshake timeout** (default 30 s): the program must connect and
  send `HELLO` within this time.
- **Step deadline** (optional, off by default): an `OUTPUT` that arrives
  later counts as a dropped step. The previous commands stay in place,
  and the late `OUTPUT`, recognised by its sequence number, is discarded
  when it arrives. The simulation reads while it sends, so a flight
  software whose writes of late `OUTPUT`s fill the link never waits on
  the simulation: a plain blocking write is enough.
- **Step timeout** (default 10 s): no answer at all within this time
  ends the run with an error. So do an exited program, a closed link and
  any `ERROR`.

The simulation stops the program at the end of the run, and kills it if
it has not exited 5 s after `BYE`.
