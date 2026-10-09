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
"""Undo and redo of scenario edits (UX/UI guidelines, "undo and redo").

The history holds whole scenarios (``Scenario.to_dict()``, valid or not:
a scenario being built from scratch is invalid until it has a
spacecraft), one per settled edit: the main window records the scenario
once typing pauses. A field being typed in keeps its own Ctrl+Z for its
text. Loading or starting a scenario starts a new history.
"""

from __future__ import annotations

import copy
from typing import List, Optional

MAX_STEPS = 100  # undo steps kept


class ScenarioHistory:
    """A linear undo history of scenario snapshots."""

    def __init__(self, max_steps: int = MAX_STEPS):
        self._states: List[dict] = []
        self._index = -1
        self._max_steps = max_steps

    def reset(self, state: Optional[dict]) -> None:
        """Start again from ``state`` (or from nothing)."""
        self._states = [copy.deepcopy(state)] if state is not None else []
        self._index = len(self._states) - 1

    def record(self, state: dict) -> bool:
        """Add ``state`` after the current one, dropping any redo; False if
        it equals the current state (nothing changed)."""
        if self._index >= 0 and self._states[self._index] == state:
            return False
        del self._states[self._index + 1:]
        self._states.append(copy.deepcopy(state))
        if len(self._states) > self._max_steps + 1:
            del self._states[0]
        self._index = len(self._states) - 1
        return True

    def replace_current(self, state: dict) -> None:
        """Make ``state`` the current entry without touching undo or redo
        (after a restore, the editor's own reading of the restored scenario)."""
        if self._index < 0:
            self.reset(state)
        else:
            self._states[self._index] = copy.deepcopy(state)

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return self._index < len(self._states) - 1

    def undo(self) -> Optional[dict]:
        if not self.can_undo():
            return None
        self._index -= 1
        return copy.deepcopy(self._states[self._index])

    def redo(self) -> Optional[dict]:
        if not self.can_redo():
            return None
        self._index += 1
        return copy.deepcopy(self._states[self._index])
