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
"""One time cursor shared by every view of a run (UX/UI guidelines, "one
shared time cursor across views").

The main window owns one :class:`TimeCursor`. The plots, the event
timeline, the dashboard and the mission output follow it, and each of
them can set it (a click or drag on a plot or the timeline, a row in a
table). ``None`` means "no cursor": the views show the end of the run.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal


class TimeCursor(QObject):
    """Elapsed (TDB) seconds since the scenario epoch, or ``None``."""

    changed = Signal(object)  # the new time [s], or None

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._time_s: Optional[float] = None

    @property
    def time_s(self) -> Optional[float]:
        return self._time_s

    def set_time(self, time_s: Optional[float]) -> None:
        """Move the cursor; emits :attr:`changed` only when it moves."""
        time_s = None if time_s is None else float(time_s)  # [s]
        if time_s == self._time_s:
            return
        self._time_s = time_s
        self.changed.emit(time_s)

    def clear(self) -> None:
        self.set_time(None)


def describe(time_s: Optional[float], epoch_utc: Optional[str] = None) -> str:
    """``T+1.250 h (2026-01-01 01:15:00 UTC)``; elapsed only without an epoch."""
    if time_s is None:
        return "No time cursor: the views show the end of the run."
    text = f"T+{time_s / 3600.0:.3f} h"
    if epoch_utc:
        from ..engine import time_system
        from ..engine.events import utc_text

        try:
            text += f" ({utc_text(time_system.elapsed_to_utc(epoch_utc, [time_s])[0], 'seconds')} UTC)"
        except ValueError:
            pass
    return text
