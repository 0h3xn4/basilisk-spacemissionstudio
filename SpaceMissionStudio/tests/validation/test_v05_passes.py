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
"""V-05: ground-station passes (WGS-84 site, geodetic elevation mask) against
GMAT R2026a's ContactLocator with an ellipsoid horizon (Phase 3, R13).

Pass start and end are where the tool's recorded geodetic elevation
crosses the mask, interpolated linearly between its 10 s samples.
"""

from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
import validation_cases as cases

pytestmark = [pytest.mark.requires_basilisk,
              pytest.mark.requirement("E-ST-10-09C 5.4.6a", "E-ST-40C 5.6.3.1")]

_REAL_EOP_DIR = Path.home() / ".cache" / "SpaceMissionStudio" / "earth_orientation"


def _gmat_passes():
    passes = []
    for line in cases.gmat_reference("contacts_berlin").read_text().splitlines():
        parts = line.split()
        if len(parts) == 9 and parts[1].isalpha():
            start = datetime.strptime(" ".join(parts[0:4]), "%d %b %Y %H:%M:%S.%f")
            end = datetime.strptime(" ".join(parts[4:8]), "%d %b %Y %H:%M:%S.%f")
            passes.append((start, end))
    return passes


def _crossings(t_s, elevation_rad, mask_rad):
    above = elevation_rad >= mask_rad
    edges = np.flatnonzero(np.diff(above.astype(int)))
    times = [t_s[i] + (mask_rad - elevation_rad[i]) / (elevation_rad[i + 1] - elevation_rad[i]) * (t_s[i + 1] - t_s[i])
             for i in edges]
    return list(zip(times[0::2], times[1::2])) if above[0] == 0 else list(zip(times[1::2], times[2::2]))


@pytest.mark.skipif(cases.gmat_reference("contacts_berlin") is None, reason="GMAT contact reference not generated")
def test_pass_times_agree_with_gmat_contact_locator(monkeypatch, record_property):
    """Same number of passes over Berlin in a day, and every start and end
    within 1 s of GMAT's (uses the installed IERS-based Earth orientation,
    as GMAT uses ITRF)."""
    from spacemissionstudio.engine import earth_orientation, time_system
    from spacemissionstudio.engine.service import SimulationService

    if not earth_orientation.installed(_REAL_EOP_DIR):
        pytest.skip("IERS-based Earth orientation files not installed (spacemissionstudio earth-orientation)")
    monkeypatch.setattr(earth_orientation, "DEFAULT_DIR", _REAL_EOP_DIR)
    case = cases.case(cases.CONTACT_CASE)
    result = SimulationService(cases.tool_scenario(case, station=True)).run()
    series = result.series[f"{cases.STATION['name']}.access_to_sat-1.elevation"]
    t_s = np.asarray(series.time_s)
    passes_s = _crossings(t_s, np.asarray(series.data)[:, 0], np.radians(cases.STATION["min_elevation_deg"]))
    tool = [tuple(time_system.elapsed_to_utc(case.epoch_utc, np.array(pair))) for pair in passes_s]
    gmat = _gmat_passes()
    assert len(tool) == len(gmat) == 5
    worst_s = max(abs((a - b).total_seconds()) for t_pass, g_pass in zip(tool, gmat) for a, b in zip(t_pass, g_pass))
    record_property("max_pass_time_difference_s", worst_s)
    print(f"{len(gmat)} passes: largest start/end difference {worst_s:.3f} s")
    assert worst_s < cases.CONTACT_TOLERANCE_S
