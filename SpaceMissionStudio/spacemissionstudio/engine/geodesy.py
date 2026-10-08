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

"""Geodetic coordinates of ground stations (ECSS-E-ST-10-09C 5.4.6a).

Basilisk-free. Defines the reference surface every ground-station
coordinate refers to:

* **Earth:** the WGS-84 ellipsoid, semi-major axis 6378137.0 m and inverse
  flattening 298.257223563 (NIMA TR8350.2). Latitude is *geodetic*
  (angle between the ellipsoid normal and the equatorial plane, positive
  north); altitude is height above the ellipsoid along that normal.
* **Other central bodies:** a sphere of the body's equatorial radius as
  used by the simulation; latitude is planetocentric.

For both, longitude is positive east of the prime meridian of the body's
body-fixed frame (for Earth the SPICE ``IAU_EARTH`` frame), and the North
Pole is the positive z axis of that frame (the body's rotation axis,
pointing to the side from which the rotation is counter-clockwise).

``groundLocation.GroundLocation`` (Basilisk 2.12) places a site given by
latitude/longitude on a sphere, so :mod:`engine.fsw` passes it the WGS-84
position through its public ``specifyLocationPCPF`` instead. That module
still builds its local horizon frame from the site's *geocentric*
direction, so the elevation and azimuth it reports are geocentric;
:func:`geodetic_elevation_azimuth` converts them to geodetic ones from the
recorded ``r_BL_L`` vector. The difference is at most about 0.19 deg
(at 45 deg latitude).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

import numpy as np

WGS84_SEMI_MAJOR_AXIS_M = 6378137.0  # [m] NIMA TR8350.2
WGS84_INVERSE_FLATTENING = 298.257223563  # [-] NIMA TR8350.2


@dataclass(frozen=True)
class Ellipsoid:
    """Reference surface of geodetic coordinates. ``inverse_flattening``
    0 means a sphere of radius ``semi_major_axis_m``."""

    name: str
    semi_major_axis_m: float  # [m]
    inverse_flattening: float = 0.0  # [-]

    @property
    def flattening(self) -> float:
        return 1.0 / self.inverse_flattening if self.inverse_flattening else 0.0

    @property
    def eccentricity_squared(self) -> float:
        f = self.flattening
        return f * (2.0 - f)

    @property
    def semi_minor_axis_m(self) -> float:
        return self.semi_major_axis_m * (1.0 - self.flattening)

    def describe(self) -> str:
        """Short label, e.g. "WGS-84 (a = 6378137.0 m, 1/f = 298.257223563)"."""
        if self.inverse_flattening:
            return f"{self.name} (a = {self.semi_major_axis_m:.1f} m, 1/f = {self.inverse_flattening})"
        return f"{self.name} (R = {self.semi_major_axis_m:.1f} m)"


WGS84 = Ellipsoid("WGS-84", WGS84_SEMI_MAJOR_AXIS_M, WGS84_INVERSE_FLATTENING)


def ellipsoid_for(central_body: str, equatorial_radius_m: float) -> Ellipsoid:
    """WGS-84 for Earth; for any other body a sphere of the radius the
    simulation uses for it."""
    if central_body == "earth":
        return WGS84
    return Ellipsoid(f"{central_body} sphere", equatorial_radius_m)


def geodetic_to_pcpf(latitude_rad: float, longitude_rad: float, altitude_m: float,
                     ellipsoid: Ellipsoid = WGS84) -> np.ndarray:
    """Body-fixed Cartesian position [m] of a geodetic point."""
    e2 = ellipsoid.eccentricity_squared
    s, c = math.sin(latitude_rad), math.cos(latitude_rad)
    n = ellipsoid.semi_major_axis_m / math.sqrt(1.0 - e2 * s * s)  # [m] prime-vertical radius
    return np.array([(n + altitude_m) * c * math.cos(longitude_rad),
                     (n + altitude_m) * c * math.sin(longitude_rad),
                     (n * (1.0 - e2) + altitude_m) * s])


def pcpf_to_geodetic(r_m, ellipsoid: Ellipsoid = WGS84) -> Tuple[float, float, float]:
    """Geodetic latitude [rad], longitude [rad] and altitude [m] of a
    body-fixed position (fixed-point iteration, converged to below 1e-12 rad)."""
    x, y, z = (float(v) for v in r_m)
    e2 = ellipsoid.eccentricity_squared
    a = ellipsoid.semi_major_axis_m
    p = math.hypot(x, y)
    longitude = math.atan2(y, x)
    latitude = math.atan2(z, p * (1.0 - e2))
    for _ in range(50):
        s = math.sin(latitude)
        n = a / math.sqrt(1.0 - e2 * s * s)
        altitude = p / math.cos(latitude) - n if abs(latitude) < math.pi / 4 else z / s - n * (1.0 - e2)
        new = math.atan2(z, p * (1.0 - e2 * n / (n + altitude)))
        if abs(new - latitude) < 1e-13:
            latitude = new
            break
        latitude = new
    s = math.sin(latitude)
    n = a / math.sqrt(1.0 - e2 * s * s)
    altitude = p / math.cos(latitude) - n if abs(latitude) < math.pi / 4 else z / s - n * (1.0 - e2)
    return latitude, longitude, altitude


def geocentric_latitude(r_m) -> float:
    """Angle [rad] of a body-fixed position above the equatorial plane."""
    x, y, z = (float(v) for v in r_m)
    return math.atan2(z, math.hypot(x, y))


def geodetic_elevation_azimuth(r_BL_L_m, geocentric_latitude_rad: float,
                               geodetic_latitude_rad: float) -> Tuple[np.ndarray, np.ndarray]:
    """Geodetic elevation and azimuth [rad] from Basilisk's
    ``AccessMsgPayload.r_BL_L`` (spacecraft relative to the site in the
    site's geocentric South-East-Zenith frame).

    The geodetic SEZ frame is the geocentric one rotated about East by
    (geocentric - geodetic) latitude. Azimuth is measured from North
    towards East, in [-pi, pi], as Basilisk does.
    """
    r = np.atleast_2d(np.asarray(r_BL_L_m, dtype=float))
    theta = geocentric_latitude_rad - geodetic_latitude_rad  # [rad]
    c, s = math.cos(theta), math.sin(theta)
    south = c * r[:, 0] - s * r[:, 2]
    east = r[:, 1]
    zenith = s * r[:, 0] + c * r[:, 2]
    norm = np.sqrt(south * south + east * east + zenith * zenith)
    with np.errstate(invalid="ignore", divide="ignore"):
        elevation = np.arcsin(np.where(norm > 0.0, zenith / norm, 0.0))
    azimuth = np.arctan2(east, -south)
    return elevation, azimuth
