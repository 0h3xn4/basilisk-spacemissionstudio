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


"""Software-in-the-loop: runs a spacecraft's flight software as an
external program against the Basilisk dynamics (User Manual, "Running
the flight software in the loop"; ``compliance/docs/SRS.md`` SRS-F-19).

* :mod:`.contract` -- the SIL transport contract, version 1: frames and
  payloads (``fsw_export/templates/SIL_CONTRACT.md``).
* :mod:`.transport` -- the byte stream: Unix-domain socket or TCP on
  127.0.0.1, swappable.
* :mod:`.session` -- the simulation side of a session: handshake,
  lock-step steps, deadlines and timeouts.
* :mod:`.report` -- residuals, timing and dropped steps.
* :mod:`.runner` -- starts the program and runs the scenario with the
  bridge in the task (needs Basilisk).
"""
