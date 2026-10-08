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
"""V-02: the tool's Earth-fixed frame (SPICE ITRF93 from the installed
IERS-based NAIF PCKs, engine/earth_orientation) against IERS 20 C04 Earth
orientation applied with ERFA's IAU 2006/2000A model, and against Vallado's
published ITRF/GCRF example (Phase 3, R13).

Reference: ``tests/data/validation/eopc04_excerpt.txt`` (observed C04
values, every 15th day from 1990). The C04 "old format" dPsi/dEps columns
are offsets from IAU 1980 nutation and are not applied to IAU 2006/2000A.
"""

from pathlib import Path

import erfa
import numpy as np
import pytest
import validation_cases as cases

pytestmark = pytest.mark.requirement("E-ST-10-09C 5.4.9f", "E-ST-10-04C 4.2.1c", "E-ST-40C 5.6.3.1")

_AS2R = np.pi / 180.0 / 3600.0  # [rad/arcsec]
_R_EARTH_M = 6378137.0  # [m] the angle is quoted as a distance at the Earth's surface
_TOLERANCE_M = 1.0  # [m] at the surface (0.16 urad); well below the WGS-84 site and horizon effects (R05)
_REAL_EOP_DIR = Path.home() / ".cache" / "SpaceMissionStudio" / "earth_orientation"

# Vallado's ITRF/GCRF example, UTC 2004-04-06 07:51:28.386009, with its EOP
# (dUT1 -0.4399619 s; xp -0.140682", yp 0.333309"; dX -0.000205", dY -0.000136").
_VALLADO_UTC = (2004, 4, 6, 7, 51, 28.386009)
_VALLADO_EOP = (-0.4399619, -0.140682, 0.333309, -0.000205, -0.000136)  # [s, arcsec x4]
_VALLADO_ITRF_KM = np.array([-1033.4793830, 7901.2952754, 6380.3565958])  # [km]
_VALLADO_GCRF_KM = np.array([5102.508958, 6123.011401, 6378.136928])  # [km]


def _c2t(utc, dut1_s, xp_as, yp_as, dx_as=0.0, dy_as=0.0):
    """ERFA celestial-to-terrestrial matrix (IAU 2006/2000A, CIO based)."""
    u1, u2 = erfa.dtf2d("UTC", *utc)
    t1, t2 = erfa.taitt(*erfa.utctai(u1, u2))
    x, y = erfa.xy06(t1, t2)
    x, y = x + dx_as * _AS2R, y + dy_as * _AS2R
    rc2i = erfa.c2ixys(x, y, erfa.s06(t1, t2, x, y))
    rpom = erfa.pom00(xp_as * _AS2R, yp_as * _AS2R, erfa.sp00(t1, t2))
    return erfa.c2tcio(rc2i, erfa.era00(*erfa.utcut1(u1, u2, dut1_s)), rpom), (t1, t2)


def test_erfa_reproduces_the_published_vallado_example():
    """The reference itself: ERFA with the example's EOP turns its ITRF
    position into its published GCRF position to 1 cm."""
    rc2t, _ = _c2t(_VALLADO_UTC, *_VALLADO_EOP)
    np.testing.assert_allclose(rc2t.T @ _VALLADO_ITRF_KM, _VALLADO_GCRF_KM, atol=1e-5)  # [km]


def _tool_frame(et_values):
    from Basilisk.topLevelModules import pyswice
    from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

    from spacemissionstudio.engine import earth_orientation

    pyswice.furnsh_c(str(get_path(DataFile.EphemerisData.naif0012)))
    for kernel in earth_orientation.installed(_REAL_EOP_DIR):
        pyswice.furnsh_c(str(kernel.path))
    out = pyswice.new_doubleArray(9)
    frames = []
    for et in et_values:
        pyswice.pxform_c("J2000", earth_orientation.EARTH_FIXED_FRAME, et, out)
        frames.append(np.array([pyswice.doubleArray_getitem(out, i) for i in range(9)]).reshape(3, 3))
    return frames


def _et(tt):
    tdb = erfa.tttdb(*tt, erfa.dtdb(*tt, 0.0, 0.0, 0.0, 0.0))
    return ((tdb[0] - 2451545.0) + tdb[1]) * 86400.0  # [s] TDB past J2000


def _needs_files():
    from spacemissionstudio.engine import earth_orientation

    if not earth_orientation.installed(_REAL_EOP_DIR):
        pytest.skip("IERS-based Earth orientation files not installed (spacemissionstudio earth-orientation)")


@pytest.mark.requires_basilisk
def test_tool_earth_frame_agrees_with_iers_c04(record_property):
    """At every excerpt epoch (1990 to the last observed C04 day) the tool's
    J2000 -> ITRF93 rotation agrees with ERFA + C04 to 1 m at the surface."""
    _needs_files()
    rows = np.loadtxt(cases.DATA / "eopc04_excerpt.txt", comments="#")
    references, ets = [], []
    for year, month, day, _mjd, xp, yp, dut1 in rows[:, :7]:
        rc2t, tt = _c2t((int(year), int(month), int(day), 0, 0, 0.0), dut1, xp, yp)
        references.append(rc2t)
        ets.append(_et(tt))
    angles = [np.arccos(np.clip((np.trace(tool @ ref.T) - 1.0) / 2.0, -1.0, 1.0))
              for tool, ref in zip(_tool_frame(ets), references)]
    worst_m = max(angles) * _R_EARTH_M
    record_property("max_difference_at_surface_m", float(worst_m))
    record_property("median_difference_at_surface_m", float(np.median(angles) * _R_EARTH_M))
    print(f"{len(angles)} epochs: max {worst_m:.3f} m, median {np.median(angles) * _R_EARTH_M:.3f} m at the surface")
    assert worst_m < _TOLERANCE_M


@pytest.mark.requires_basilisk
def test_tool_earth_frame_reproduces_the_vallado_example():
    """The example's ITRF position, rotated to J2000 with the tool's frame,
    lands within 1 m of the published GCRF position."""
    _needs_files()
    _rc2t, tt = _c2t(_VALLADO_UTC, *_VALLADO_EOP)
    dcm_PN = _tool_frame([_et(tt)])[0]
    difference_m = np.linalg.norm(dcm_PN.T @ _VALLADO_ITRF_KM - _VALLADO_GCRF_KM) * 1e3
    print(f"Vallado example: {difference_m:.3f} m")
    assert difference_m < _TOLERANCE_M
