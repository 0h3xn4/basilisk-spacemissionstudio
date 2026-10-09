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
"""The runs of this session, kept for comparison (UX/UI guidelines, "run
comparison": "keep finished runs in the session").

Only the last :data:`MAX_RUNS` are kept, as each holds all its series in
memory; they are gone when the app closes (save a run's CSV export to
keep it).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from ..engine.results import ResultSet

MAX_RUNS = 5  # runs kept in memory


@dataclass
class RunRecord:
    number: int  # 1 for the session's first run
    scenario: dict  # Scenario.to_dict() as it ran
    result: ResultSet
    epoch_utc: str
    finished: datetime
    cancelled: bool = False

    @property
    def label(self) -> str:
        name = self.scenario.get("name", "")
        return f"Run {self.number} ({self.finished:%H:%M}{', cancelled' if self.cancelled else ''}): {name}"


class RunHistory:
    def __init__(self, max_runs: int = MAX_RUNS):
        self.runs: List[RunRecord] = []
        self._count = 0
        self._max_runs = max_runs

    def add(self, scenario: dict, result: ResultSet, epoch_utc: str, cancelled: bool = False,
            finished: Optional[datetime] = None) -> RunRecord:
        self._count += 1
        record = RunRecord(self._count, scenario, result, epoch_utc, finished or datetime.now(), cancelled)
        self.runs.append(record)
        del self.runs[:-self._max_runs]
        return record

    def latest(self) -> Optional[RunRecord]:
        return self.runs[-1] if self.runs else None

    def find(self, number: int) -> Optional[RunRecord]:
        return next((r for r in self.runs if r.number == number), None)
