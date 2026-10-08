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
"""V-04: the tool's orbit propagation against GMAT R2026a (Phase 3, R13).

Each case of ``validation_cases.PROPAGATION_CASES`` is run by the tool as a
user would run it (10 s dynamics step, RKF78) and compared with the GMAT
reference in ``tests/data/validation/gmat/`` at GMAT's own UTC report
times. The tool's states are interpolated to those times (cubic Hermite
on position and velocity, under 1 mm at a 10 s spacing).
"""

from datetime import datetime, timedelta
from pathlib import Path

import erfa
import numpy as np
import pytest
import validation_cases as cases

pytestmark = [pytest.mark.requires_basilisk,
              pytest.mark.requirement("E-ST-40C 5.6.3.1", "E-ST-40C 5.6.4.1", "Q-ST-80C 7.1.7a")]

def _tool_run(case):
    from spacemissionstudio.engine.service import SimulationService

    result = SimulationService(cases.tool_scenario(case)).run()
    position, velocity = result.series["sat-1.position_N"], result.series["sat-1.velocity_N"]
    return np.asarray(position.time_s), np.asarray(position.data) / 1e3, np.asarray(velocity.data) / 1e3


def _hermite(t, x, v, tq):
    i = np.clip(np.searchsorted(t, tq) - 1, 0, len(t) - 2)
    h = (t[i + 1] - t[i])[:, None]
    s = ((tq - t[i]) / h[:, 0])[:, None]
    return ((2 * s ** 3 - 3 * s ** 2 + 1) * x[i] + (s ** 3 - 2 * s ** 2 + s) * h * v[i]
            + (-2 * s ** 3 + 3 * s ** 2) * x[i + 1] + (s ** 3 - s ** 2) * h * v[i + 1])


def _gmat_elapsed_tdb_s(case, utc_mjd):
    """GMAT's UTC report times as the tool's elapsed TDB seconds."""
    from spacemissionstudio.engine import time_system

    t0 = time_system.tdb_seconds_past_j2000(case.epoch_utc)
    out = []
    for mjd in utc_mjd:
        y, mo, d, fraction = erfa.jd2cal(2430000.0, mjd)
        utc = datetime(y, mo, d) + timedelta(microseconds=round(fraction * 86400e6))
        out.append(time_system.tdb_seconds_past_j2000(utc.isoformat()) - t0)
    return np.array(out)


_REAL_EOP_DIR = Path.home() / ".cache" / "SpaceMissionStudio" / "earth_orientation"


@pytest.mark.parametrize("case", [c for c in cases.PROPAGATION_CASES if cases.gmat_reference(c.name)],
                         ids=lambda c: c.name)
def test_propagation_agrees_with_gmat(case, monkeypatch, record_property):
    """Two checks over the whole arc, each within the case's tolerance
    (validation_cases.py):

    * implementation: tool and GMAT states at the same elapsed integration
      time (GMAT integrates in TAI seconds, the tool in TDB seconds);
    * as a user sees it: states at the same UTC instant, allowing in
      addition for that time-argument difference (|t_TDB - t_TAI| times
      the speed; Phase 3 finding F-05).

    Cases with an Earth field use the installed IERS-based ITRF93 files
    (as GMAT uses ITRF with IERS EOP); without them the tool falls back to
    IAU_EARTH, 1.5 mrad away, and a degree-20 LEO orbit differs by about
    160 m after a day (finding F-06), so those cases are skipped.
    """
    from spacemissionstudio.engine import earth_orientation

    if case.degree:
        if not earth_orientation.installed(_REAL_EOP_DIR):
            pytest.skip("IERS-based Earth orientation files not installed (spacemissionstudio earth-orientation)")
        monkeypatch.setattr(earth_orientation, "DEFAULT_DIR", _REAL_EOP_DIR)
    gmat = np.loadtxt(cases.gmat_reference(case.name))
    t, x, v = _tool_run(case)
    elapsed_s = np.arange(len(gmat)) * cases.OUTPUT_STEP_S  # [s] GMAT's own integration time
    tdb_s = _gmat_elapsed_tdb_s(case, gmat[:, 0])  # [s] the same UTC instants in the tool's time
    keep = np.maximum(elapsed_s, tdb_s) <= t[-1] + 1e-6
    implementation_m = np.linalg.norm(_hermite(t, x, v, elapsed_s[keep]) - gmat[keep, 1:4], axis=1).max() * 1e3
    same_utc_m = np.linalg.norm(_hermite(t, x, v, tdb_s[keep]) - gmat[keep, 1:4], axis=1).max() * 1e3
    allowance_m = np.abs(tdb_s - elapsed_s).max() * np.linalg.norm(v, axis=1).max() * 1e3
    record_property("implementation_difference_m", float(implementation_m))
    record_property("same_utc_difference_m", float(same_utc_m))
    record_property("time_argument_allowance_m", float(allowance_m))
    print(f"{case.name}: implementation {implementation_m:.3f} m, same UTC {same_utc_m:.3f} m "
          f"(time-argument allowance {allowance_m:.3f} m, tolerance {case.tolerance_m} m)")
    assert implementation_m < case.tolerance_m
    assert same_utc_m < case.tolerance_m + allowance_m
