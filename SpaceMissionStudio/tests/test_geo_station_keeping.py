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

"""GEO station-keeping: schema (no Basilisk) and the controller's pieces
(Basilisk)."""

import math

import pytest

from spacemissionstudio.engine.orbit_design import geostationary_elements_deg
from spacemissionstudio.schema.scenario import (
    GeoStationKeepingConfig,
    GravityConfig,
    OrbitIC,
    Scenario,
    ScenarioValidationError,
    SpacecraftConfig,
    StationKeepingConfig,
)


def _geo_spacecraft(**overrides):
    inclination, raan, anomaly = geostationary_elements_deg("2030-01-01T00:00:00", 10.0)
    defaults = dict(
        name="geo", dry_mass_kg=500.0,
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=42166.2, eccentricity=0.0,
                      inclination_deg=inclination, raan_deg=raan, arg_periapsis_deg=0.0, true_anomaly_deg=anomaly),
        geo_station_keeping=GeoStationKeepingConfig(target_longitude_deg=10.0, thrust_n=1.0, isp_s=220.0,
                                                    propellant_kg=50.0))
    defaults.update(overrides)
    return SpacecraftConfig(**defaults)


def test_true_equator_placement_follows_iau_earth():
    """pck00010's IAU_EARTH pole at 2030-01-01: alpha0 = -0.641 T, delta0 =
    90 - 0.557 T deg with T = 0.30 Julian centuries."""
    inclination, raan, anomaly = geostationary_elements_deg("2030-01-01T00:00:00", 10.0)
    centuries = (10957.5 * 86400.0 + 69.184) / 86400.0 / 36525.0  # [-] J2000 to 2030-01-01: 30 years, 8 leap days
    assert inclination == pytest.approx(0.557 * centuries, abs=1e-6)  # [deg]
    assert raan == pytest.approx(90.0 - 0.641 * centuries, abs=1e-6)  # [deg]
    _, _, anomaly_20 = geostationary_elements_deg("2030-01-01T00:00:00", 20.0)
    assert (anomaly_20 - anomaly) % 360.0 == pytest.approx(10.0)  # [deg] east is +anomaly


@pytest.mark.parametrize("change, message", [
    ({"longitude_deadband_deg": 0.0}, "longitude_deadband_deg must be in"),
    ({"inclination_max_deg": 20.0}, "inclination_max_deg must be in"),
    ({"thrust_n": 0.0}, "thrust_n must be > 0"),
    ({"target_longitude_deg": 400.0}, "target_longitude_deg must be in"),
])
def test_bad_settings_are_rejected(change, message):
    spacecraft = _geo_spacecraft()
    for key, value in change.items():
        setattr(spacecraft.geo_station_keeping, key, value)
    with pytest.raises(ScenarioValidationError, match=message):
        spacecraft.validate()


def test_it_replaces_altitude_station_keeping_and_is_earth_only():
    with pytest.raises(ScenarioValidationError, match="replaces station_keeping"):
        _geo_spacecraft(station_keeping=StationKeepingConfig(target_altitude_km=35786.0, deadband_km=5.0,
                                                            thrust_n=1.0, isp_s=220.0, propellant_kg=1.0)).validate()
    scenario = Scenario(name="g", epoch_utc="2030-01-01T00:00:00", simulation_mode="orbit_only",
                        gravity=GravityConfig(central_body="mars"), spacecraft=[_geo_spacecraft()])
    with pytest.raises(ScenarioValidationError, match="geo_station_keeping is Earth-only"):
        scenario.validate()
    assert Scenario.from_dict(Scenario(name="g", epoch_utc="2030-01-01T00:00:00", simulation_mode="orbit_only",
                                       spacecraft=[_geo_spacecraft()]).to_dict()).spacecraft[0] == _geo_spacecraft()


@pytest.mark.requires_basilisk
def test_triaxiality_drift_points_at_the_stable_longitudes():
    """Unstable at ~345 E and ~165 E, stable at ~75 E and ~255 E. At 10 E
    a free run measured +0.00113 deg/day^2 against this formula's +0.0013."""
    from spacemissionstudio.engine.geo_station_keeping import longitude_acceleration

    def accel(lon_deg):  # [deg/day^2]
        return math.degrees(longitude_acceleration(math.radians(lon_deg), 42166.2e3, 6378.1363e3)) * 86400.0 ** 2

    assert accel(10.0) == pytest.approx(0.0013, rel=0.05)
    for stable in (75.07, 255.07):
        assert accel(stable - 5.0) > 0.0 > accel(stable + 5.0)  # pulled back toward it from both sides
    for unstable in (-14.93, 165.07):
        assert accel(unstable - 5.0) < 0.0 < accel(unstable + 5.0)  # pushed away on both sides


@pytest.mark.requires_basilisk
def test_drift_fit_ignores_the_daily_libration():
    """A plain straight line over one day picks up the eccentricity
    libration as a slope bias of up to ~1.9 x its amplitude per day."""
    import numpy as np

    from spacemissionstudio.engine.geo_station_keeping import _OMEGA_EARTH, _SIDEREAL_DAY_S, \
        GeoStationKeepingController

    controller = GeoStationKeepingController("c", 3.986004415e14, 6378.1363e3,
                                             _geo_spacecraft().geo_station_keeping, 500.0)
    drift = math.radians(0.01) / 86400.0  # [rad/s] 0.01 deg/day
    amplitude = math.radians(0.02)  # [rad] daily libration
    times = np.arange(0.0, _SIDEREAL_DAY_S + 30.0, 30.0)  # [s]
    controller._historyStartT = 0.0
    controller._history = [(t, 1e-4 + drift * t + amplitude * math.sin(_OMEGA_EARTH * t + 0.7)) for t in times]
    _, fitted = controller._drift_fit(times[-1])
    assert fitted == pytest.approx(drift, rel=0.02)
    naive = np.polyfit(times, [e for _, e in controller._history], 1)[0]
    assert abs(naive - drift) > 0.5 * drift  # what the first version did
