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


"""What a run's data handling did (``engine.data_handling``), read back
from its series: Basilisk-free, for the CLI and any other summary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .results import ResultSet


@dataclass
class DataBudget:
    """One spacecraft's totals over a run [bit]."""

    spacecraft: str
    generated: float
    downlinked: float
    lost: float
    stored_end: float
    capacity_full: bool  # the memory was full at some point


def budgets(result: ResultSet) -> List[DataBudget]:
    """The data totals of every spacecraft that has data handling."""
    found = []
    for name in sorted(result.series):
        if not name.endswith(".data_handling.data_generated"):
            continue
        sc = name[:-len(".data_handling.data_generated")]
        last = {part: float(result.series[f"{sc}.data_handling.{part}"].data[-1, 0])
                for part in ("data_generated", "data_downlinked", "data_lost")}
        stored = result.series[f"{sc}.data_handling.stored"].data[:, 0]
        found.append(DataBudget(sc, last["data_generated"], last["data_downlinked"], last["data_lost"],
                                float(stored[-1]), last["data_lost"] > 0))
    return found


def summary_lines(result: ResultSet) -> List[str]:
    """One line per spacecraft: generated, downlinked, lost, left on board."""
    return [f"{b.spacecraft}: generated {b.generated / 1e9:.4g} Gbit, downlinked {b.downlinked / 1e9:.4g}, "
            f"lost to a full memory {b.lost / 1e9:.4g}, on board at the end {b.stored_end / 1e9:.4g}"
            for b in budgets(result)]
