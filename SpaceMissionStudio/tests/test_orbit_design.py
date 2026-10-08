"""Tests for spacemissionstudio.engine.orbit_design -- no Basilisk import,
runs anywhere. Turns the reference-value checks documented in these
functions' own docstrings (previously only "verified directly" in prose)
into real pytest asserts.
"""

import pytest

from spacemissionstudio.engine.orbit_design import (
    DEFAULT_LTAN_HOUR,
    raan_for_ltan_deg,
    sun_synchronous_inclination_deg,
)


def test_sun_synchronous_inclination_matches_known_reference_value():
    # engine.spacecraft_templates._placeholder_orbit()'s own
    # "inclination_deg=97.4  # sun-synchronous at ~500 km" comment.
    assert sun_synchronous_inclination_deg(6878.1366) == pytest.approx(97.40, abs=0.01)


def test_sun_synchronous_inclination_increases_with_altitude():
    # A higher orbit needs a steeper (more retrograde) inclination to
    # keep the same nodal regression rate -- real, well-known behavior,
    # not just "doesn't crash".
    low = sun_synchronous_inclination_deg(6778.0)
    high = sun_synchronous_inclination_deg(7178.0)
    assert high > low


def test_sun_synchronous_inclination_accepts_nonzero_eccentricity():
    # Template 05's own orbit (a=6928 km, e=0.001) -- must not raise, and
    # should stay close to the circular-orbit value at the same altitude.
    circular = sun_synchronous_inclination_deg(6928.0, 0.0)
    eccentric = sun_synchronous_inclination_deg(6928.0, 0.001)
    assert eccentric == pytest.approx(circular, abs=0.1)


@pytest.mark.parametrize("epoch_utc,expected_ra_deg", [
    ("2000-03-20T12:00:00", 0.0),    # vernal equinox
    ("2030-06-21T12:00:00", 90.0),   # summer solstice
    ("2030-09-23T06:00:00", 180.0),  # autumnal equinox
])
def test_raan_for_ltan_at_noon_matches_known_sun_right_ascension(epoch_utc, expected_ra_deg):
    # RAAN at a 12:00 (noon) LTAN equals the Sun's own right ascension
    # exactly, by definition of local solar time -- the real,
    # independently-known reference points this module's own docstring
    # claims accuracy against (within 0.25 deg).
    got = raan_for_ltan_deg(epoch_utc, ltan_hour=12.0)
    assert got == pytest.approx(expected_ra_deg % 360.0, abs=0.25)


def test_raan_for_ltan_default_matches_1030_am():
    assert DEFAULT_LTAN_HOUR == 10.5
    noon = raan_for_ltan_deg("2030-01-01T00:00:00", ltan_hour=12.0)
    default = raan_for_ltan_deg("2030-01-01T00:00:00")
    # 10:30 is 1.5 hours before noon -> 1.5 * 15 deg/hr = 22.5 deg less RAAN.
    assert (noon - default) % 360.0 == pytest.approx(22.5, abs=1.0e-6)


def test_raan_for_ltan_wraps_into_0_360():
    for ltan_hour in (0.0, 6.0, 12.0, 18.0, 23.99):
        got = raan_for_ltan_deg("2030-01-01T00:00:00", ltan_hour=ltan_hour)
        assert 0.0 <= got < 360.0
