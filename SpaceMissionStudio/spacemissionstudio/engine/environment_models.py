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

"""Environment constants and checks (ECSS-E-ST-10-04C 4.2.1b, 6.2.1a;
remediation R06). Basilisk-free.

* **Solar radiation:** total solar irradiance 1361 W/m^2 at 1 AU
  (ECSS-E-ST-10-04C Table 6-2), scaled by 1/r^2 with the Earth-Sun
  distance (1316 W/m^2 at aphelion, 1407 W/m^2 at perihelion).
* **Thermal sensor (Basilisk 2.12 sensorThermal):** the module uses a
  fixed 1366 W/m^2 at any Sun distance and a Stefan-Boltzmann value of
  5.76051e-8 W/m^2/K^4 (1.6 % above the CODATA value), neither of which is
  settable (both measured by ``tests/test_environment_models.py``).
  :func:`sensor_thermal_inputs` corrects for both through the module's own
  inputs: absorptivity, emissivity, power draw and mass are scaled so the
  module's heat balance equals the one with the standard constants.
* **Gravity truncation:** :func:`gravity_truncation_acceleration` is an
  order-of-magnitude estimate (Kaula's rule, 1e-5/n^2 per normalised
  coefficient, and the actual J2 for degree 2) of the acceleration a field
  truncated at a given degree leaves out, for comparison with the
  non-gravitational accelerations modelled (4.2.1b).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

TOTAL_SOLAR_IRRADIANCE_W_M2 = 1361.0  # [W/m^2] at 1 AU, ECSS-E-ST-10-04C Table 6-2
SPACE_SINK_TEMPERATURE_K = 3.0  # [K] ECSS-E-ST-10-04C 6.2.1c
STEFAN_BOLTZMANN_W_M2_K4 = 5.670374419e-8  # [W/m^2/K^4] CODATA 2018
SPEED_OF_LIGHT_M_S = 299792458.0  # [m/s]

# Basilisk 2.12 sensorThermal's built-in constants (sensorThermal.cpp).
BASILISK_SENSOR_THERMAL_FLUX_W_M2 = 1366.0  # [W/m^2] at any Sun distance
BASILISK_SENSOR_THERMAL_SIGMA_W_M2_K4 = 5.76051e-8  # [W/m^2/K^4]

_EARTH_GM_M3_S2 = 3.986004415e14  # [m^3/s^2] GGM03S
_EARTH_RADIUS_M = 6378136.3  # [m] GGM03S reference radius
_EARTH_J2 = 1.08263e-3  # [-]
_KAULA_MAX_DEGREE = 2000


def _days_from_j2000(epoch_utc: str) -> float:
    epoch = datetime.fromisoformat(epoch_utc)
    if epoch.tzinfo is not None:
        epoch = epoch.astimezone(timezone.utc).replace(tzinfo=None)
    return (epoch - datetime(2000, 1, 1, 12)).total_seconds() / 86400.0  # [day]


def sun_distance_au(epoch_utc: str) -> float:
    """Earth-Sun distance [AU]: the Astronomical Almanac's low-precision
    formula (about 1e-4 AU; checked against DE430 in the tests)."""
    g = math.radians(357.528 + 0.9856003 * _days_from_j2000(epoch_utc))  # [rad] mean anomaly
    return 1.00014 - 0.01671 * math.cos(g) - 0.00014 * math.cos(2.0 * g)


def solar_flux_w_m2(epoch_utc: str) -> float:
    """Solar flux at Earth's distance on ``epoch_utc`` [W/m^2]."""
    return TOTAL_SOLAR_IRRADIANCE_W_M2 / sun_distance_au(epoch_utc) ** 2


@dataclass(frozen=True)
class SensorThermalInputs:
    """Values to give Basilisk's sensorThermal so its heat balance is the
    standard one; ``scale`` is the common factor applied (<= 1)."""

    absorptivity: float  # [-]
    emissivity: float  # [-]
    power_draw_w: float  # [W]
    mass_kg: float  # [kg]
    scale: float  # [-]


def sensor_thermal_inputs(absorptivity: float, emissivity: float, power_draw_w: float, mass_kg: float,
                          solar_flux: float) -> SensorThermalInputs:
    """Inputs for sensorThermal that reproduce

        m c dT/dt = alpha F A_proj + P - eps sigma A T^4

    with the real solar flux ``F`` and the CODATA ``sigma``. The module
    computes alpha' 1366 A_proj + P' - eps' 5.76051e-8 A T^4 over m' c, so
    alpha' = k alpha F / 1366, eps' = k eps sigma / 5.76051e-8, P' = k P and
    m' = k m reproduce it exactly for any k > 0; k is the largest value
    <= 1 that keeps alpha' and eps' within the module's (0, 1] limit.
    """
    alpha = absorptivity * solar_flux / BASILISK_SENSOR_THERMAL_FLUX_W_M2
    eps = emissivity * STEFAN_BOLTZMANN_W_M2_K4 / BASILISK_SENSOR_THERMAL_SIGMA_W_M2_K4
    scale = min(1.0, 1.0 / alpha if alpha > 0.0 else 1.0, 1.0 / eps if eps > 0.0 else 1.0)
    return SensorThermalInputs(alpha * scale, eps * scale, power_draw_w * scale, mass_kg * scale, scale)


def gravity_truncation_acceleration(degree: int, radius_m: float) -> float:
    """Estimated acceleration [m/s^2] left out by an Earth gravity field
    truncated at ``degree`` (0 = point mass) at ``radius_m``."""
    total = 0.0
    surface = _EARTH_GM_M3_S2 / radius_m ** 2  # [m/s^2]
    ratio = _EARTH_RADIUS_M / radius_m
    for n in range(max(degree, 1) + 1, _KAULA_MAX_DEGREE + 1):
        if n == 2:
            term = 3.0 * _EARTH_J2 * surface * ratio ** 2
        else:
            term = surface * (n + 1) * ratio ** n * (1e-5 / n ** 2) * math.sqrt(2 * n + 1)
        total += term * term
        if n > 2 and term < 1e-20:
            break
    return math.sqrt(total)


def srp_acceleration(srp_coeff: float, area_m2: float, mass_kg: float, solar_flux: float) -> float:
    """Cannonball solar radiation pressure acceleration [m/s^2]."""
    return solar_flux / SPEED_OF_LIGHT_M_S * srp_coeff * area_m2 / mass_kg


def degree_for(radius_m: float, acceleration_m_s2: float, max_degree: int = 180) -> int:
    """Smallest degree whose estimated truncation acceleration is at or below
    ``acceleration_m_s2`` (``max_degree`` if none is)."""
    for degree in range(0, max_degree + 1):
        if gravity_truncation_acceleration(degree, radius_m) <= acceleration_m_s2:
            return degree
    return max_degree
