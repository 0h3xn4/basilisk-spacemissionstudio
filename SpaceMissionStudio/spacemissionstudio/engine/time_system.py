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

"""Epoch string formatting.

``schema.scenario.Scenario.epoch_utc`` (an ISO 8601 UTC string) is the ONE
stored representation of a scenario's epoch. Basilisk's SPICE-backed
modules want it as a SPICE time string instead; :func:`utc_iso_to_spice_string`
is the single place that conversion happens (``engine.service`` feeds its
result to ``spiceInterface``/``simHelpers``, which do the actual ET math).

Basilisk-free: pure ``datetime`` formatting. This module used to also
carry its own SPICE ET/TAI/TT conversion helpers (``utc_to_et``,
``epoch_times``, ``build_epoch_msg``, ...), but nothing in the app ever
called them, and their module-level ``pyswice`` import made even this one
live function un-importable without a Basilisk build.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Fixed English month abbreviations -- NOT strftime("%b"), which follows
# the process's LC_TIME locale. QApplication calls setlocale(LC_ALL, "")
# at construction on Linux, so under e.g. a German desktop locale "%b"
# yields "Mär"/"Mai"/"Okt"/"Dez", which SPICE's time parser rejects --
# every GUI run with an epoch in one of those months would fail.
_MONTH_ABBREVIATIONS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                        "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def utc_iso_to_spice_string(epoch_utc: str) -> str:
    """``'2030-01-01T00:00:00'`` -> a SPICE-recognizable time string
    (``'2030 JAN 01 00:00:00.000 (UTC)'``). Any sub-second precision in
    ``epoch_utc`` (schema.scenario.Scenario.validate() only requires it to
    parse as ISO 8601, not to be a whole second) is preserved to
    millisecond resolution -- ``dt.microsecond`` rounded down to
    milliseconds, not a literal ``.000`` that would silently discard it.
    """
    dt = datetime.fromisoformat(epoch_utc)
    if dt.tzinfo is not None:
        # Scenario.validate() only requires epoch_utc to parse via
        # datetime.fromisoformat() -- it does not reject a timezone-aware
        # string (e.g. "...+05:00"). The output is labeled "(UTC)", so a
        # tz-aware value must be CONVERTED to UTC here, not have its offset
        # silently dropped (which would format the original wall-clock time
        # under a UTC label, off by the offset amount).
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    millis = dt.microsecond // 1000
    month = _MONTH_ABBREVIATIONS[dt.month - 1]
    return f"{dt.year:04d} {month} {dt.day:02d} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}.{millis:03d} (UTC)"
