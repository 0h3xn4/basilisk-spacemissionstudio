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

"""The configuration hash that tells whether an export is stale.

It covers exactly the scenario settings ``engine.fsw`` builds the flight
software from, for one spacecraft, plus the export format and Basilisk
revision. Changing an orbit, a duration or another spacecraft leaves an
export current; changing a gain, a pointing mode, an actuator or the
inertia makes it stale. ``tests/test_fsw_export.py`` checks both
directions field by field.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass

from .catalog import BASILISK_REVISION

# Bumped when the generated package changes in a way that needs a re-export.
EXPORT_FORMAT_VERSION = 1

_SPACECRAFT_FIELDS = ("fsw_mode", "fsw_params", "control_params", "actuators", "inertia_kg_m2", "solar_arrays",
                      "magnetic_momentum_management", "momentum_dumping", "comms_pointing")
_SENSOR_KINDS = ("coarse_sun_sensor",)  # the only sensors the exported chain reads configuration from (CSSConfig)


def _plain(value):
    if is_dataclass(value):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, float):
        return repr(value)  # exact
    return value


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def fsw_config_parts(scenario, spacecraft_name: str) -> dict:
    """``{setting group: 16 hex digits}`` -- what :func:`fsw_config_digest`
    hashes, kept per group so a stale export can say what changed. Raises
    ``KeyError`` for an unknown spacecraft."""
    spacecraft = next((sc for sc in scenario.spacecraft if sc.name == spacecraft_name), None)
    if spacecraft is None:
        raise KeyError(spacecraft_name)
    content = {
        "export format": EXPORT_FORMAT_VERSION,
        "Basilisk revision": BASILISK_REVISION,
        "dynamics step": _plain(float(scenario.sim_settings.dynamics_task_rate_s)),
        "central body": scenario.gravity.central_body,
        "coarse sun sensors": [_plain(s) for s in spacecraft.sensors if s.kind in _SENSOR_KINDS],
    }
    content.update({name: _plain(getattr(spacecraft, name)) for name in _SPACECRAFT_FIELDS})
    return {name: hashlib.sha256(_canonical(value).encode()).hexdigest()[:16] for name, value in content.items()}


def fsw_config_digest(scenario, spacecraft_name: str) -> str:
    """64 hex digits over :func:`fsw_config_parts`; raises ``KeyError`` for
    an unknown spacecraft."""
    return hashlib.sha256(_canonical(fsw_config_parts(scenario, spacecraft_name)).encode()).hexdigest()


def changed_parts(old: dict, new: dict) -> list:
    """The setting groups whose hash differs, in a stable order."""
    return sorted(name for name in set(old) | set(new) if old.get(name) != new.get(name))
