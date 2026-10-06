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

"""Autosave / crash-recovery for in-progress scenario edits.

Design-philosophy roadmap item M4 (``docs/ux_roadmap.md``), closing the
one real gap ``docs/ux_audit.md``'s Principle 13 finding flagged: a
crash mid-edit lost unsaved work entirely -- only a CLEAN close
(``gui.main_window.MainWindow.closeEvent``'s own
``_confirm_discard_unsaved`` prompt) ever asked about unsaved changes;
anything that took the process down before that point (a Basilisk
crash, a segfault, a killed process) left nothing behind.

This module is deliberately Qt-free (plain functions operating on a
``Scenario``/dict and a filesystem path) so it's unit-testable without a
``QApplication`` -- the same "pure logic, thin Qt wiring in
``main_window.py``" split this project already uses elsewhere (e.g.
``engine/results.py`` vs ``gui/results_widget.py``). ``main_window.py``
owns the ``QTimer`` that calls :func:`write_recovery_file` on a tick,
and the startup check that calls :func:`read_recovery_file`.

One fixed recovery slot, not one per scenario: this app edits exactly
ONE scenario at a time (a single ``MainWindow``, no MDI/multiple-open
-documents), so there's never more than one "the user's current
in-progress edit" to recover -- a single file, under a per-user
directory matching ``logging_setup.py``'s own convention
(``~/.spacemissionstudio/...``), is all that's needed.

Writing it is best-effort: a failure to write (a full disk, a
permissions problem) must never interrupt the user's actual work or
pop an error dialog on every single timer tick -- it's logged and
skipped, same tolerance this feature exists to provide safety margin
for, not a new way for the app to misbehave.

The module-level ``_AUTOSAVE_DIR``/``_RECOVERY_FILE`` constants are
referenced BY NAME inside every function below (never captured as a
bound default argument) specifically so a test can
``monkeypatch.setattr(autosave, "_RECOVERY_FILE", tmp_path / "...")``
and redirect every function here to an isolated location -- this
module must never touch a real user's home directory from an
automated test run.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..schema.scenario import Scenario, ScenarioValidationError

_logger = logging.getLogger(__name__)

_AUTOSAVE_DIR = Path.home() / ".spacemissionstudio" / "autosave"
_RECOVERY_FILE = _AUTOSAVE_DIR / "recovery.json"


@dataclass(frozen=True)
class RecoveryInfo:
    """What :func:`write_recovery_file` saved, as read back by
    :func:`read_recovery_file`. ``scenario`` is already a fully parsed,
    validated :class:`Scenario` (never partially-populated) --
    ``original_path`` is where the user's real save target was (or
    ``None`` for a scenario that had never been saved yet), and
    ``saved_at_utc`` is purely informational, shown in the restore
    prompt so the user can judge whether the recovered state is worth
    keeping.
    """

    scenario: Scenario
    original_path: Optional[Path]
    saved_at_utc: str


def write_recovery_file(scenario: Scenario, original_path: Optional[Path]) -> None:
    """Best-effort -- see module docstring. Called on every autosave
    timer tick while the editor is dirty (``gui.main_window.MainWindow``),
    only once the in-memory scenario has already been confirmed valid
    (the caller runs it through ``ScenarioEditorWidget.to_scenario()``
    first, same validation a real Save does) -- an incomplete edit
    mid-keystroke is never written here, so a recovery file is always
    restorable the exact same way a normal saved scenario file is.
    """
    envelope = {
        "original_path": str(original_path) if original_path is not None else None,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario.to_dict(),
    }
    try:
        _AUTOSAVE_DIR.mkdir(parents=True, exist_ok=True)
        _RECOVERY_FILE.write_text(json.dumps(envelope, indent=2))
    except OSError:
        _logger.warning("Could not write autosave recovery file %s", _RECOVERY_FILE, exc_info=True)


def clear_recovery_file() -> None:
    """Called once a clean state is legitimately reached -- a real
    Save, New, Open, or an explicit "discard unsaved changes" --
    everywhere ``gui.main_window.MainWindow`` already marks the editor
    clean. The whole point of a RECOVERY file is to only exist while
    there's something to recover; leaving a stale one around would
    prompt to restore changes the user already saved or explicitly
    discarded -- exactly the "worse than not having the feature" risk
    the roadmap item itself calls out.
    """
    try:
        _RECOVERY_FILE.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        _logger.warning("Could not remove autosave recovery file %s", _RECOVERY_FILE, exc_info=True)


def read_recovery_file() -> Optional[RecoveryInfo]:
    """Returns the pending recovery info, or ``None`` if there isn't
    one. Missing, unreadable, or corrupt (a partially-written file from
    a crash mid-write, or a hand-edited one) are all treated the same
    way: nothing to offer -- this feature must never itself crash (or
    block startup) on top of the very crash it exists to help recover
    from. Does NOT delete the file on success -- the caller
    (``gui.main_window.MainWindow``) decides whether the user actually
    restored it before calling :func:`clear_recovery_file`, so
    declining the offer doesn't throw the recovery copy away
    immediately (e.g. in case the window is closed without otherwise
    touching the scenario).
    """
    try:
        text = _RECOVERY_FILE.read_text()
    except OSError:
        return None
    try:
        envelope = json.loads(text)
    except json.JSONDecodeError:
        _logger.warning("Autosave recovery file %s is corrupt -- ignoring", _RECOVERY_FILE)
        return None
    if not isinstance(envelope, dict):
        _logger.warning("Autosave recovery file %s is malformed -- ignoring", _RECOVERY_FILE)
        return None
    try:
        from ..schema import migrations  # local import: avoids a cycle at module load time, same as schema.scenario.load_scenario

        scenario_dict = migrations.migrate(envelope["scenario"])
        scenario = Scenario.from_dict(scenario_dict)
        scenario.validate()
    except (KeyError, TypeError, ScenarioValidationError):
        _logger.warning("Autosave recovery file %s is malformed -- ignoring", _RECOVERY_FILE, exc_info=True)
        return None
    original_path_str = envelope.get("original_path")
    return RecoveryInfo(
        scenario=scenario,
        original_path=Path(original_path_str) if original_path_str else None,
        saved_at_utc=envelope.get("saved_at_utc", "an unknown time"),
    )
