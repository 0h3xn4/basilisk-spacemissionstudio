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

"""TLE import: checks, SGP4 to the scenario epoch, TEME of date -> EME2000
(ECSS-E-ST-10-09C 5.3.1b/c, CCSDS 502.0-B-3 4.2.4.9; remediation R03).

References:

* Vallado, *Fundamentals of Astrodynamics and Applications*, 4th ed.
  (2013), TEME -> J2000 worked example: r_TEME = (5094.18016210,
  6127.64465950, 6380.34453270) km, v_TEME = (-4.746131487, 0.785818041,
  5.531931288) km/s on 2004-04-06 07:51:28.386009 UTC give r_J2000 =
  (5102.5096, 6123.01152, 6378.1363) km, v_J2000 = (-4.7432196, 0.7905366,
  5.53375619) km/s (as published, 0.1 m / 0.1 mm/s resolution).
* NAIF SPICE's own IAU 1976 precession / IAU 1980 nutation dynamic frame
  (an independent implementation of the same models).
"""

import math
from datetime import datetime, timedelta

import numpy as np
import pytest
from sgp4.api import Satrec, jday

from spacemissionstudio.engine import tle

pytestmark = pytest.mark.requirement("E-ST-10-09C 5.3.1b", "E-ST-10-09C 5.3.1c", "CCSDS-502.0-B-3 4.2.4.9")

# ISS TLE as printed in the sgp4 package's documentation.
LINE1 = "1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991"
LINE2 = "2 25544  51.6439 211.2001 0007417  17.6667  85.6398 15.50103472202482"


def _corrupt(line, column, char):
    return line[:column] + char + line[column + 1:]


def test_valid_tle_passes_the_checks_and_gives_its_epoch():
    """Checksums, line numbers and catalogue number of a published TLE are
    accepted, and the epoch 19343.69339541 is 2019-12-09 16:38:29.363 UTC."""
    tle.check_lines(LINE1, LINE2)
    epoch = tle.tle_epoch_utc(tle.parse(LINE1, LINE2))
    assert abs((epoch - datetime(2019, 12, 9, 16, 38, 29, 363424)).total_seconds()) < 1e-3


@pytest.mark.parametrize("line1, line2, message", [
    (_corrupt(LINE1, 68, "2"), LINE2, "line 1 checksum"),
    (LINE1, _corrupt(LINE2, 20, "9"), "line 2 checksum"),
    (LINE1[:-1], LINE2, "68 characters"),
    (LINE1, "1" + LINE2[1:], "must start with '2 '"),
    (LINE1, _corrupt(_corrupt(LINE2, 6, "5"), 68, str((int(LINE2[68]) + 1) % 10)), "catalogue numbers differ"),
])
def test_malformed_tles_are_rejected_with_the_reason(line1, line2, message):
    """A changed digit, a truncated line, a swapped line or two different
    satellites raise TLEError naming the problem."""
    with pytest.raises(tle.TLEError, match=message):
        tle.parse(line1, line2)


def test_vallado_teme_to_j2000_example():
    """The TEME-of-date -> EME2000 rotation reproduces Vallado's published
    J2000 vector to its printed resolution."""
    rotation = tle.teme_to_eme2000_matrix(datetime(2004, 4, 6, 7, 51, 28, 386009))
    r = rotation @ np.array([5094.18016210, 6127.64465950, 6380.34453270])  # [km]
    v = rotation @ np.array([-4.746131487, 0.785818041, 5.531931288])  # [km/s]
    np.testing.assert_allclose(r, [5102.5096, 6123.01152, 6378.1363], atol=1e-4)  # [km] = 0.1 m
    np.testing.assert_allclose(v, [-4.7432196, 0.7905366, 5.53375619], atol=1e-7)  # [km/s]
    np.testing.assert_allclose(rotation @ rotation.T, np.eye(3), atol=1e-15)


def _sgp4_teme(epoch):
    jd, fraction = jday(epoch.year, epoch.month, epoch.day, epoch.hour, epoch.minute,
                        epoch.second + epoch.microsecond / 1e6)
    error, r, v = Satrec.twoline2rv(LINE1, LINE2).sgp4(jd, fraction)
    assert error == 0
    return np.array(r), np.array(v)


def test_state_is_propagated_to_the_scenario_epoch():
    """The state is SGP4's at the SCENARIO epoch (not the TLE epoch), rotated
    to EME2000; the TLE age is reported."""
    epoch = datetime(2019, 12, 11, 4, 0, 0)
    state = tle.state_at(LINE1, LINE2, epoch.isoformat())
    r_teme, v_teme = _sgp4_teme(epoch)
    rotation = tle.teme_to_eme2000_matrix(epoch)
    np.testing.assert_allclose(state.r_m, rotation @ r_teme * 1e3, atol=1e-6)
    np.testing.assert_allclose(state.v_m_s, rotation @ v_teme * 1e3, atol=1e-9)
    assert state.age_days == pytest.approx(1.0 + (11 * 3600 + 21 * 60 + 30.637) / 86400.0, abs=1e-6)  # [day]
    # One and a half days of SGP4 move the satellite thousands of km: the
    # state at the TLE epoch (what Basilisk 2.12's satTle2elem returns) is
    # not the state at the scenario epoch.
    at_tle_epoch = tle.state_at(LINE1, LINE2, tle.tle_epoch_utc(tle.parse(LINE1, LINE2)).isoformat())
    assert np.linalg.norm(at_tle_epoch.r_m - state.r_m) > 1e6  # [m]
    assert at_tle_epoch.age_days == pytest.approx(0.0, abs=1e-8)


def test_timezone_aware_epoch_is_converted_to_utc():
    """An epoch with a UTC offset gives the same state as its UTC form."""
    a = tle.state_at(LINE1, LINE2, "2019-12-10T00:00:00")
    b = tle.state_at(LINE1, LINE2, "2019-12-10T02:00:00+02:00")
    np.testing.assert_allclose(a.r_m, b.r_m, atol=1e-9)


def test_sgp4_failure_is_reported():
    """Propagating far enough for the orbit to decay raises TLEError with
    SGP4's reason instead of returning a meaningless state."""
    with pytest.raises(tle.TLEError, match="SGP4 failed"):
        tle.state_at(LINE1, LINE2, (datetime(2019, 12, 9) + timedelta(days=20000)).isoformat())


def test_tle_warnings_flag_old_or_broken_tles():
    """The plausibility checks warn about a TLE more than three days from
    the scenario epoch and about a malformed one; none for a fresh one."""
    from spacemissionstudio.engine.scenario_checks import scenario_warnings
    from spacemissionstudio.schema.scenario import OrbitIC, Scenario, SpacecraftConfig

    def scenario(epoch, line2=LINE2):
        orbit = OrbitIC(type="tle", tle_line1=LINE1, tle_line2=line2)
        return Scenario(name="t", epoch_utc=epoch, spacecraft=[SpacecraftConfig(name="iss", orbit=orbit)])

    assert not [w for w in scenario_warnings(scenario("2019-12-10T00:00:00")) if "TLE" in w]
    old = [w for w in scenario_warnings(scenario("2019-12-20T00:00:00")) if "TLE" in w]
    assert old == ["iss: TLE epoch is 10.3 d before the scenario epoch -- SGP4 accuracy drops with TLE age"]
    broken = [w for w in scenario_warnings(scenario("2019-12-10T00:00:00", _corrupt(LINE2, 20, "9")))
              if "TLE" in w]
    assert broken and "checksum" in broken[0]


@pytest.mark.requires_basilisk
def test_service_uses_the_scenario_epoch_state():
    """engine.service builds a TLE spacecraft at engine.tle's state at the
    scenario epoch."""
    from spacemissionstudio.engine.service import _orbit_ic_to_rv
    from spacemissionstudio.schema.scenario import OrbitIC

    orbit = OrbitIC(type="tle", tle_line1=LINE1, tle_line2=LINE2)
    r, v = _orbit_ic_to_rv(3.986004415e14, orbit, "2019-12-11T04:00:00")
    state = tle.state_at(LINE1, LINE2, "2019-12-11T04:00:00")
    np.testing.assert_allclose(r, state.r_m, atol=0.0)
    np.testing.assert_allclose(v, state.v_m_s, atol=0.0)


@pytest.mark.requires_basilisk
def test_precession_nutation_matches_spice_iau_1976_1980(tmp_path):
    """ERFA's J2000 -> true-of-date matrix agrees with SPICE's
    TRUE_EQUATOR_AND_EQUINOX_OF_DATE frame (EARTH_IAU_1976 precession,
    EARTH_IAU_1980 nutation) to 1e-13 rad at several epochs."""
    import erfa
    from Basilisk.topLevelModules import pyswice
    from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

    from spacemissionstudio.engine.time_system import utc_iso_to_spice_string

    frame_kernel = tmp_path / "sms_tod.tf"
    frame_kernel.write_text("\\begindata\n"
                            "FRAME_SMS_TEST_TOD = 1499001\n"
                            "FRAME_1499001_NAME = 'SMS_TEST_TOD'\n"
                            "FRAME_1499001_CLASS = 5\n"
                            "FRAME_1499001_CLASS_ID = 1499001\n"
                            "FRAME_1499001_CENTER = 399\n"
                            "FRAME_1499001_RELATIVE = 'J2000'\n"
                            "FRAME_1499001_DEF_STYLE = 'PARAMETERIZED'\n"
                            "FRAME_1499001_FAMILY = 'TRUE_EQUATOR_AND_EQUINOX_OF_DATE'\n"
                            "FRAME_1499001_PREC_MODEL = 'EARTH_IAU_1976'\n"
                            "FRAME_1499001_NUT_MODEL = 'EARTH_IAU_1980'\n"
                            "FRAME_1499001_ROTATION_STATE = 'INERTIAL'\n"
                            "\\begintext\n")
    leap_seconds = str(get_path(DataFile.EphemerisData.naif0012))
    pyswice.furnsh_c(leap_seconds)
    pyswice.furnsh_c(str(frame_kernel))
    try:
        for epoch in (datetime(2004, 4, 6, 7, 51, 28), datetime(1990, 1, 1), datetime(2030, 7, 1, 12)):
            et = pyswice.new_doubleArray(1)
            pyswice.str2et_c(utc_iso_to_spice_string(epoch.isoformat()), et)
            out = pyswice.new_doubleArray(9)
            pyswice.pxform_c("J2000", "SMS_TEST_TOD", pyswice.doubleArray_getitem(et, 0), out)
            spice = np.array([pyswice.doubleArray_getitem(out, i) for i in range(9)]).reshape(3, 3)
            t1, t2 = tle._utc_to_tt_jd(epoch)
            ours = erfa.numat(erfa.obl80(t1, t2), *erfa.nut80(t1, t2)) @ erfa.pmat76(t1, t2)
            assert np.abs(spice - ours).max() < 1e-13
            # The equation of the equinoxes completes TEME: dpsi cos(eps_mean).
            dpsi, _ = erfa.nut80(t1, t2)
            teme = tle.teme_to_eme2000_matrix(epoch).T
            np.testing.assert_allclose(teme, erfa.rz(dpsi * math.cos(erfa.obl80(t1, t2)), spice), atol=1e-13)
    finally:
        pyswice.unload_c(str(frame_kernel))  # the leap-second kernel stays: Basilisk may share it
