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
