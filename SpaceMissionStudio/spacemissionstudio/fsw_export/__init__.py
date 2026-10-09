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

"""Flight-software export: packages a spacecraft's Basilisk C flight
software as a standalone C project (User Manual, "Exporting the flight
software"; ``compliance/docs/SRS.md`` SRS-F-18).

* :mod:`.catalog` -- the C modules that can be exported (pure data).
* :mod:`.sources` -- the Basilisk sources, vendored unchanged from the
  pinned revision and checked on every read.
* :mod:`.capture` -- reads the flight software out of a built
  simulation and records a short run (needs Basilisk).
* :mod:`.generate` -- writes the C project from a capture (no Basilisk).
* :mod:`.digest` -- the configuration hash that flags a stale export.
"""
