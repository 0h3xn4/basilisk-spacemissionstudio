"""Tests for spacemissionstudio.engine.time_system.utc_iso_to_spice_string()
-- Basilisk-free, runs anywhere.
"""

import locale

import pytest


def test_utc_iso_to_spice_string_whole_second():
    from spacemissionstudio.engine.time_system import utc_iso_to_spice_string

    assert utc_iso_to_spice_string("2030-01-01T00:00:00") == "2030 JAN 01 00:00:00.000 (UTC)"


def test_utc_iso_to_spice_string_preserves_sub_second_precision():
    """Regression test for an audit finding: the function used to hardcode
    a literal ".000" in its strftime format string, silently discarding
    any sub-second precision in epoch_utc instead of deriving it from the
    actual value -- schema.scenario.Scenario.validate() only requires
    epoch_utc to parse as ISO 8601, not to be a whole second, so this is a
    real, reachable input shape.
    """
    from spacemissionstudio.engine.time_system import utc_iso_to_spice_string

    assert utc_iso_to_spice_string("2030-01-01T00:00:00.750000") == "2030 JAN 01 00:00:00.750 (UTC)"
    assert utc_iso_to_spice_string("2030-01-01T00:00:00.001000") == "2030 JAN 01 00:00:00.001 (UTC)"


def test_utc_iso_to_spice_string_converts_timezone_aware_input_to_utc():
    """Regression test for an audit finding: Scenario.validate() only
    requires epoch_utc to parse via datetime.fromisoformat(), which also
    accepts a timezone-aware string (e.g. a "+05:00" offset). The function
    used to format that datetime's wall-clock value as-is and still label
    it "(UTC)", silently off by the offset instead of actually converting
    to UTC first.
    """
    from spacemissionstudio.engine.time_system import utc_iso_to_spice_string

    assert utc_iso_to_spice_string("2030-01-01T00:00:00+05:00") == "2029 DEC 31 19:00:00.000 (UTC)"
    assert utc_iso_to_spice_string("2030-01-01T00:00:00+00:00") == "2030 JAN 01 00:00:00.000 (UTC)"


@pytest.mark.parametrize("month,expected", [
    (1, "JAN"), (2, "FEB"), (3, "MAR"), (4, "APR"), (5, "MAY"), (6, "JUN"),
    (7, "JUL"), (8, "AUG"), (9, "SEP"), (10, "OCT"), (11, "NOV"), (12, "DEC"),
])
def test_every_month_uses_the_english_spice_abbreviation(month, expected):
    from spacemissionstudio.engine.time_system import utc_iso_to_spice_string

    assert utc_iso_to_spice_string(f"2030-{month:02d}-15T12:00:00") == f"2030 {expected} 15 12:00:00.000 (UTC)"


def test_month_abbreviation_ignores_the_process_locale():
    """Regression test for a real bug found by audit: the function used
    strftime("%b"), which follows LC_TIME -- and QApplication calls
    setlocale(LC_ALL, "") on Linux, so under a German desktop locale every
    GUI run with a March/May/October/December epoch handed SPICE an
    unparseable "MÄR"/"MAI"/"OKT"/"DEZ". Confirmed directly before the fix:
    "2030 MÄR 01 00:00:00.000 (UTC)".
    """
    from spacemissionstudio.engine.time_system import utc_iso_to_spice_string

    previous = locale.setlocale(locale.LC_TIME)
    try:
        locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")
    except locale.Error:
        pytest.skip("de_DE.UTF-8 locale not installed on this machine")
    try:
        assert utc_iso_to_spice_string("2030-03-01T00:00:00") == "2030 MAR 01 00:00:00.000 (UTC)"
        assert utc_iso_to_spice_string("2030-10-01T00:00:00") == "2030 OCT 01 00:00:00.000 (UTC)"
        assert utc_iso_to_spice_string("2030-12-01T00:00:00") == "2030 DEC 01 00:00:00.000 (UTC)"
    finally:
        locale.setlocale(locale.LC_TIME, previous)


# --- Time scales (ECSS-E-ST-10-09C 5.4.2a, 5.4.4a/b; remediation R02) ---


@pytest.mark.requirement("E-ST-10-09C 5.4.4b")
@pytest.mark.parametrize("date, leap_seconds", [("1999-06-01", 32.0), ("2009-06-01", 34.0), ("2016-06-01", 36.0),
                                                ("2017-01-01", 37.0), ("2030-01-01", 37.0)])
def test_tai_minus_utc_follows_the_leap_second_table(date, leap_seconds):
    """TAI - UTC as published by the IERS (32 s from 1999, 34 s from 2009,
    36 s from mid-2015, 37 s from 2017; no later leap seconds modelled)."""
    from spacemissionstudio.engine.time_system import tai_minus_utc_s

    assert tai_minus_utc_s(date + "T00:00:00") == leap_seconds  # [s]


@pytest.mark.requirement("E-ST-10-09C 5.4.4b")
def test_j2000_epoch_in_utc_is_zero_tdb_seconds():
    """J2000.0 (2000-01-01T12:00:00 TT) is 11:58:55.816 UTC (TAI - UTC = 32 s,
    TT - TAI = 32.184 s); its TDB seconds past J2000 are zero to |TDB - TT|."""
    from spacemissionstudio.engine.time_system import tdb_seconds_past_j2000

    assert abs(tdb_seconds_past_j2000("2000-01-01T11:58:55.816")) < 2e-3  # [s]


@pytest.mark.requires_basilisk
@pytest.mark.requirement("E-ST-10-09C 5.4.4b")
def test_tdb_matches_spice_ephemeris_time():
    """ERFA's UTC -> TDB agrees with SPICE str2et (naif0012) to 50 us at
    several epochs; SPICE uses a shorter TDB - TT series than ERFA."""
    from Basilisk.topLevelModules import pyswice
    from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

    from spacemissionstudio.engine.time_system import tdb_seconds_past_j2000, utc_iso_to_spice_string

    pyswice.furnsh_c(str(get_path(DataFile.EphemerisData.naif0012)))
    for epoch in ("1999-03-04T05:06:07", "2016-12-31T23:59:59", "2017-01-01T00:00:01", "2026-10-08T12:00:00",
                  "2034-06-30T18:30:00"):
        et = pyswice.new_doubleArray(1)
        pyswice.str2et_c(utc_iso_to_spice_string(epoch), et)
        assert tdb_seconds_past_j2000(epoch) == pytest.approx(pyswice.doubleArray_getitem(et, 0), abs=5e-5)


@pytest.mark.requirement("E-ST-10-09C 5.4.4b")
def test_elapsed_simulation_time_converts_to_utc_across_a_leap_second():
    """61 TDB seconds after 2016-12-31T23:59:00 UTC is 2017-01-01T00:00:00
    UTC: the leap second 23:59:60 lies in between."""
    from datetime import datetime

    from spacemissionstudio.engine.time_system import elapsed_to_utc

    times = elapsed_to_utc("2016-12-31T23:59:00", [0.0, 61.0, 121.0])
    assert abs((times[1] - datetime(2017, 1, 1)).total_seconds()) < 1e-5
    assert abs((times[2] - datetime(2017, 1, 1, 0, 1)).total_seconds()) < 1e-5


@pytest.mark.requirement("E-ST-10-09C 5.4.4b")
def test_elapsed_to_utc_round_trips_through_tdb():
    """Converting the UTC back to TDB seconds returns the elapsed time to
    2 us over a year (TDB - TT changes by up to 3.3 ms in between)."""
    import numpy as np

    from spacemissionstudio.engine.time_system import elapsed_to_utc, tdb_seconds_past_j2000

    epoch = "2030-03-20T06:00:00"
    elapsed = np.array([0.0, 3600.0, 86400.0 * 91.3, 86400.0 * 182.6, 86400.0 * 365.0])  # [s]
    start = tdb_seconds_past_j2000(epoch)
    for t, utc in zip(elapsed, elapsed_to_utc(epoch, elapsed)):
        assert tdb_seconds_past_j2000(utc) - start == pytest.approx(t, abs=2e-6)


def test_time_scales_record_names_the_time_variable_and_offsets():
    """The metadata names the time variable and gives TAI - UTC, TT - TAI
    and TDB - TT at the epoch."""
    from spacemissionstudio.engine.time_system import time_scales

    scales = time_scales("2030-01-01T00:00:00")
    assert scales["time_variable"] == "TDB seconds since the scenario epoch"
    assert scales["tai_minus_utc_s"] == 37.0 and scales["tt_minus_tai_s"] == 32.184
    assert abs(scales["tdb_minus_tt_s"]) < 1.7e-3
