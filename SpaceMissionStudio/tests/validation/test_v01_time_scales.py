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
"""V-01: the tool's UTC -> TAI -> TT -> TDB conversion (engine/time_system,
ERFA) against GMAT R2026a's own implementation and leap-second table, at
the epochs of ``validation_cases.TIME_EPOCHS`` (Phase 3, R13)."""

import numpy as np
import pytest
import validation_cases as cases

pytestmark = pytest.mark.requirement("E-ST-10-09C 5.4.4b", "E-ST-40C 5.6.3.1", "Q-ST-80C 7.1.7a")

_REFERENCE = cases.gmat_reference("time_scales")


@pytest.mark.skipif(_REFERENCE is None, reason="GMAT time-scale reference not generated")
def test_time_scale_offsets_agree_with_gmat(record_property):
    """TAI-UTC (leap seconds), TT-TAI and the periodic TDB-TT agree with
    GMAT to the stated tolerances at every epoch."""
    from spacemissionstudio.engine import time_system

    gmat = np.loadtxt(_REFERENCE)
    assert len(gmat) == len(cases.TIME_EPOCHS)
    worst = dict.fromkeys(cases.TIME_TOLERANCE_S, 0.0)
    for epoch, (utc, tai, tt, tdb) in zip(cases.TIME_EPOCHS, gmat):
        tool = time_system.time_scales(epoch)
        differences = {"tai_minus_utc": tool["tai_minus_utc_s"] - (tai - utc) * 86400.0,
                       "tt_minus_tai": tool["tt_minus_tai_s"] - (tt - tai) * 86400.0,
                       "tdb_minus_tt": tool["tdb_minus_tt_s"] - (tdb - tt) * 86400.0}
        for key, value in differences.items():
            worst[key] = max(worst[key], float(abs(value)))
            assert abs(value) < cases.TIME_TOLERANCE_S[key], (epoch, key, value)
    for key, value in worst.items():
        record_property(f"max_{key}_difference_s", value)
    print("largest differences [s]:", {k: f"{v:.2e}" for k, v in worst.items()})


def test_tdb_series_reproduces_sofas_own_test_value():
    """The TDB-TT series the tool uses (ERFA dtdb, Fairhead and Bretagnon)
    gives SOFA's published regression value (t_sofa_c.c, iauDtdb) to 1e-15 s;
    GMAT's two-term formula is not accurate enough to check it."""
    import erfa

    value = erfa.dtdb(2448939.5, 0.123, 0.76543, 5.0123, 5525.242, 3190.0)  # [s]
    assert value == pytest.approx(-0.1280368005936998991e-2, abs=1e-15)
