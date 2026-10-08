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

"""Sun-synchronous orbit design helpers -- pure ``math``/``datetime``,
Basilisk-free (same "independently-testable, no Basilisk import needed"
precedent as :mod:`engine.constellation`'s own docstring describes about
itself).

Moved here (Phase 6 audit fix) from ``scripts/_generate_templates.py``,
where these were originally written as the dev-only template generator's
own private helpers -- real, verified orbital-mechanics functions that
happened to be trapped somewhere the running app could never import them.
That meant 12 of the 20 bundled templates used a Sun-synchronous orbit a
user could SEE in the GUI but never actually reproduce by hand when
building a bespoke scenario from scratch (there was no way to compute the
matching inclination/RAAN without reading this project's own source). The
generator script now imports these from here instead of defining its own
copy, so there's exactly one implementation and zero drift risk between
the bundled templates and whatever the GUI computes.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

# J2/Req/mu below are Basilisk's own real Earth constants, confirmed
# directly against a real build (not guessed):
#   from Basilisk.utilities import orbitalMotion, simIncludeGravBody
#   orbitalMotion.J2_EARTH == 0.001082616
#   simIncludeGravBody.gravBodyFactory().createEarth().radEquator == 6378136.6 [m]
#   simIncludeGravBody.gravBodyFactory().createEarth().mu == 398600436000000.0 [m^3/s^2]
# Matches gui.template_wizard's own already-established _EARTH_RADIUS_KM
# constant exactly (same source).
_EARTH_J2 = 0.001082616  # [-]
_EARTH_REQUATOR_KM = 6378.1366  # [km]
_EARTH_MU_KM3_S2 = 398600.436  # [km^3/s^2]
_TROPICAL_YEAR_DAYS = 365.2421897  # [day] mean interval between vernal equinoxes

# Default LTAN used throughout this project's bundled templates -- the
# most common real operational choice for Earth-observation/commercial
# smallsats ("SSO (10:30 AM) orbits").
DEFAULT_LTAN_HOUR = 10.5  # [hr]


def sun_synchronous_inclination_deg(semi_major_axis_km: float, eccentricity: float = 0.0) -> float:
    """The real inclination (deg) whose J2 secular nodal regression rate
    exactly matches the mean Sun's own apparent eastward motion
    (360 deg / tropical year) -- the defining property of a Sun
    -synchronous orbit (RAAN drifts in step with the Sun, so local solar
    time at the ascending node stays constant year-round).

    Standard first-order J2 secular RAAN-rate formula (e.g. Vallado,
    *Fundamentals of Astrodynamics and Applications*):
    ``dRAAN/dt = -1.5 * n * J2 * (Req/p)^2 * cos(i)``, ``n = sqrt(mu/a^3)``,
    ``p = a*(1-e^2)``. Solved here for ``i`` given the target rate.

    Verified directly against this project's own existing reference value
    (not just derived in the abstract): evaluates to 97.40 deg at a
    6878.1366 km semi-major axis (500 km altitude circular) -- matching
    ``engine.spacecraft_templates._placeholder_orbit()``'s own
    ``inclination_deg=97.4  # sun-synchronous at ~500 km`` comment exactly.
    """
    a = semi_major_axis_km
    p = a * (1.0 - eccentricity**2)
    mean_motion = math.sqrt(_EARTH_MU_KM3_S2 / a**3)  # [rad/s]
    target_raan_rate = 2.0 * math.pi / (_TROPICAL_YEAR_DAYS * 86400.0)  # [rad/s]
    cos_i = -target_raan_rate / (1.5 * mean_motion * _EARTH_J2 * (_EARTH_REQUATOR_KM / p) ** 2)
    # Rounded to 2 decimal places: real orbit-insertion dispersion and the
    # first-order J2-only model above both dwarf anything past this
    # precision, so carrying more digits would be false precision -- and
    # it keeps this value exactly representable by the Customize wizard's
    # own 2-decimal inclination spin box (template_wizard.py).
    return round(math.degrees(math.acos(cos_i)), 2)


def _sun_right_ascension_deg(epoch_utc: str) -> float:
    """The Sun's real right ascension (deg, J2000-ish mean-of-date frame)
    at ``epoch_utc`` -- the Astronomical Almanac's own "low precision
    formula for the Sun" (accurate to about 0.01 deg through 2050;
    e.g. Vallado section 5.1 reproduces the identical formula), not a
    guess: verified directly here against three real, independently-known
    reference points before being trusted -- the Sun's RA is 0 deg at the
    vernal equinox, 90 deg at the summer solstice, and 180 deg at the
    autumnal equinox, and this function reproduces all three to within
    0.25 deg (``2000-03-20T12:00``, ``2030-06-21T12:00``,
    ``2030-09-23T06:00``).
    """
    days_since_j2000 = (datetime.fromisoformat(epoch_utc) - datetime(2000, 1, 1, 12, 0, 0)).total_seconds() / 86400.0
    mean_longitude_deg = (280.460 + 0.9856474 * days_since_j2000) % 360.0
    mean_anomaly_rad = math.radians((357.528 + 0.9856003 * days_since_j2000) % 360.0)
    ecliptic_longitude_rad = math.radians((
        mean_longitude_deg
        + 1.915 * math.sin(mean_anomaly_rad)
        + 0.020 * math.sin(2.0 * mean_anomaly_rad)
    ) % 360.0)
    obliquity_rad = math.radians(23.439 - 0.0000004 * days_since_j2000)
    ra_rad = math.atan2(math.cos(obliquity_rad) * math.sin(ecliptic_longitude_rad), math.cos(ecliptic_longitude_rad))
    return math.degrees(ra_rad) % 360.0


def raan_for_ltan_deg(epoch_utc: str, ltan_hour: float = DEFAULT_LTAN_HOUR) -> float:
    """RAAN (deg) that gives an ascending node at local time of ascending
    node ``ltan_hour`` (24h clock) at ``epoch_utc`` -- standard relation
    ``RAAN = RA_sun + 15 deg/hr * (LTAN - 12h)`` (RAAN equals the Sun's own
    RA exactly at a 12:00/noon LTAN, by definition of local solar time).
    """
    raan = (_sun_right_ascension_deg(epoch_utc) + 15.0 * (ltan_hour - 12.0)) % 360.0
    return round(raan, 2)


_TT_MINUS_UTC_S = 69.184  # [s] 32.184 s + 37 leap seconds (constant since 2017)


def geostationary_elements_deg(epoch_utc: str, east_longitude_deg: float):
    """(inclination, RAAN, true anomaly) [deg] of a circular orbit lying in
    Earth's TRUE equator, over ``east_longitude_deg`` at ``epoch_utc``,
    expressed in the J2000 frame the simulation integrates in.

    Earth's pole has precessed away from J2000's z axis (IAU_EARTH, as in
    SPICE's pck00010: alpha0 = -0.641 T, delta0 = 90 - 0.557 T deg, T in
    Julian centuries from J2000), so "equatorial" is ~0.17 deg inclined in
    J2000 by 2030. The node of the true equator sits at alpha0 + 90 deg, and
    the prime meridian is W = 190.147 + 360.9856235 d deg past it.
    """
    epoch = datetime.fromisoformat(epoch_utc)
    if epoch.tzinfo is not None:
        epoch = epoch.astimezone(timezone.utc).replace(tzinfo=None)
    days = ((epoch - datetime(2000, 1, 1, 12)).total_seconds() + _TT_MINUS_UTC_S) / 86400.0  # [day] TDB
    centuries = days / 36525.0
    alpha0 = -0.641 * centuries  # [deg]
    delta0 = 90.0 - 0.557 * centuries  # [deg]
    prime_meridian = 190.147 + 360.9856235 * days  # [deg]
    return 90.0 - delta0, (alpha0 + 90.0) % 360.0, (prime_meridian + east_longitude_deg) % 360.0
