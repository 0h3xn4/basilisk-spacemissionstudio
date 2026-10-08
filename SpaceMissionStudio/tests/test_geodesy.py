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

"""WGS-84 ground-station geodesy (ECSS-E-ST-10-09C 5.4.6a, remediation R05).

Reference values are the published WGS-84 defining and derived constants
(NIMA TR8350.2): semi-minor axis b = 6356752.3142 m, and the prime-vertical
radius at 45 deg, N = a / sqrt(1 - e^2/2).
"""

import math

import numpy as np
import pytest

from spacemissionstudio.engine import geodesy

pytestmark = pytest.mark.requirement("E-ST-10-09C 5.4.6a")


def test_wgs84_equator_and_pole_match_the_defining_constants():
    """A point on the equator at the prime meridian lies at x = a; the pole
    at z = b (published semi-minor axis 6356752.3142 m)."""
    np.testing.assert_allclose(geodesy.geodetic_to_pcpf(0.0, 0.0, 0.0), [6378137.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(geodesy.geodetic_to_pcpf(math.pi / 2, 0.0, 0.0), [0.0, 0.0, 6356752.3142],
                               atol=1e-3)
    assert geodesy.WGS84.semi_minor_axis_m == pytest.approx(6356752.3142, abs=1e-3)  # [m]


def test_wgs84_point_at_45_degrees():
    """At 45 deg the prime-vertical radius is a / sqrt(1 - e^2 / 2) and the
    point lies at N cos(45 deg) horizontally, N (1 - e^2) sin(45 deg) up."""
    e2 = 0.00669437999014  # [-] published WGS-84 first eccentricity squared
    n = 6378137.0 / math.sqrt(1.0 - e2 / 2.0)  # [m]
    assert geodesy.WGS84.eccentricity_squared == pytest.approx(e2, rel=1e-11)
    r = geodesy.geodetic_to_pcpf(math.radians(45.0), math.radians(90.0), 100.0)
    np.testing.assert_allclose(r, [0.0, (n + 100.0) * math.sqrt(0.5), (n * (1 - e2) + 100.0) * math.sqrt(0.5)],
                               atol=1e-6)


@pytest.mark.parametrize("lat_deg, lon_deg, alt_m", [
    (0.0, 0.0, 0.0), (52.52, 13.405, 34.0), (-33.9, 18.4, 1200.0), (89.9, -120.0, 5.0),
    (-89.99, 45.0, 0.0), (45.0, 179.9, 8848.0), (10.0, -75.0, -400.0),
])
def test_geodetic_round_trip(lat_deg, lon_deg, alt_m):
    """pcpf_to_geodetic inverts geodetic_to_pcpf to 1e-9 deg and 1 mm,
    including near the poles."""
    r = geodesy.geodetic_to_pcpf(math.radians(lat_deg), math.radians(lon_deg), alt_m)
    lat, lon, alt = geodesy.pcpf_to_geodetic(r)
    assert math.degrees(lat) == pytest.approx(lat_deg, abs=1e-9)
    assert math.degrees(lon) == pytest.approx(lon_deg, abs=1e-9)
    assert alt == pytest.approx(alt_m, abs=1e-3)


def test_geocentric_latitude_differs_by_at_most_0_19_degrees():
    """The geodetic-geocentric latitude difference peaks at about 0.1924 deg
    (11.5 arcmin) at 45 deg: the size of the error a spherical site makes."""
    diffs = [lat - math.degrees(geodesy.geocentric_latitude(geodesy.geodetic_to_pcpf(math.radians(lat), 0.0, 0.0)))
             for lat in np.arange(0.0, 90.1, 0.5)]
    assert max(diffs) == pytest.approx(0.1924, abs=5e-4)  # [deg]
    assert diffs[90] == pytest.approx(max(diffs), abs=1e-3)  # 45 deg


def test_spherical_bodies_keep_planetocentric_coordinates():
    """Non-Earth central bodies use a sphere of the simulation's radius."""
    moon = geodesy.ellipsoid_for("moon", 1737400.0)
    assert moon.flattening == 0.0
    r = geodesy.geodetic_to_pcpf(math.radians(30.0), 0.0, 0.0, moon)
    np.testing.assert_allclose(r, [1737400.0 * math.cos(math.radians(30.0)), 0.0,
                                   1737400.0 * math.sin(math.radians(30.0))], atol=1e-6)
    assert geodesy.ellipsoid_for("earth", 6378136.6) is geodesy.WGS84


def _direct_geodetic_elevation_azimuth(site_lat, site_lon, site_alt, r_sc):
    """Independent reference: angles from the ellipsoid normal and the
    local North/East unit vectors."""
    site = geodesy.geodetic_to_pcpf(site_lat, site_lon, site_alt)
    up = np.array([math.cos(site_lat) * math.cos(site_lon), math.cos(site_lat) * math.sin(site_lon),
                   math.sin(site_lat)])
    east = np.array([-math.sin(site_lon), math.cos(site_lon), 0.0])
    north = np.cross(up, east)
    d = r_sc - site
    return (math.asin(d @ up / np.linalg.norm(d)), math.atan2(d @ east, d @ north))


def _geocentric_sez(site, r_sc):
    """What Basilisk records: r_BL_L in the site's geocentric SEZ frame."""
    lat_gc = geodesy.geocentric_latitude(site)
    lon = math.atan2(site[1], site[0])
    up = np.array([math.cos(lat_gc) * math.cos(lon), math.cos(lat_gc) * math.sin(lon), math.sin(lat_gc)])
    east = np.array([-math.sin(lon), math.cos(lon), 0.0])
    south = np.cross(east, up)
    d = r_sc - site
    return np.array([d @ south, d @ east, d @ up])


def test_geodetic_elevation_azimuth_matches_an_independent_computation():
    """Converting a geocentric-SEZ vector reproduces the elevation and
    azimuth measured directly from the WGS-84 normal, to 1e-12 rad."""
    rng = np.random.default_rng(1)
    for _ in range(200):
        lat, lon = math.radians(rng.uniform(-89.0, 89.0)), math.radians(rng.uniform(-180.0, 180.0))
        alt = rng.uniform(-100.0, 3000.0)  # [m]
        site = geodesy.geodetic_to_pcpf(lat, lon, alt)
        r_sc = site * (1.0 + rng.uniform(0.0, 6.0)) + rng.normal(0.0, 2e6, 3)  # [m]
        r_l = _geocentric_sez(site, r_sc)
        elevation, azimuth = geodesy.geodetic_elevation_azimuth(r_l, geodesy.geocentric_latitude(site), lat)
        ref_el, ref_az = _direct_geodetic_elevation_azimuth(lat, lon, alt, r_sc)
        assert elevation[0] == pytest.approx(ref_el, abs=1e-12)
        assert math.remainder(azimuth[0] - ref_az, 2 * math.pi) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.requires_basilisk
def test_basilisk_ground_location_uses_the_wgs84_site():
    """fsw.build_ground_location places Basilisk's GroundLocation at the
    WGS-84 position, and the recorded geocentric r_BL_L converts to the
    directly computed geodetic elevation for a spacecraft overhead-ish."""
    from Basilisk.architecture import messaging
    from Basilisk.utilities import SimulationBaseClass, macros

    from spacemissionstudio.engine import fsw
    from spacemissionstudio.schema.scenario import GroundStationConfig

    sim = SimulationBaseClass.SimBaseClass()
    process = sim.CreateNewProcess("p")
    process.addTask(sim.CreateNewTask("t", macros.sec2nano(1.0)))
    planet = messaging.SpicePlanetStateMsgPayload()
    planet.J20002Pfix = np.eye(3).tolist()  # inertial == body-fixed for this check
    planet_msg = messaging.SpicePlanetStateMsg().write(planet)
    gs = GroundStationConfig(name="berlin", latitude_deg=52.52, longitude_deg=13.405, altitude_m=34.0,
                             min_elevation_deg=5.0)
    lat, lon = math.radians(gs.latitude_deg), math.radians(gs.longitude_deg)
    site = geodesy.geodetic_to_pcpf(lat, lon, gs.altitude_m)
    r_sc = site + 7e5 * np.array([math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]) \
        + np.array([3e5, -2e5, 1e5])  # [m]
    sc = messaging.SCStatesMsgPayload()
    sc.r_BN_N = r_sc.tolist()
    sc_msg = messaging.SCStatesMsg().write(sc)
    gl = fsw.build_ground_location(sim, "t", gs, 6378136.6, planet_msg, [sc_msg], central_body="earth")
    recorder = gl.accessOutMsgs[0].recorder()
    sim.AddModelToTask("t", recorder)
    sim.InitializeSimulation()
    sim.ConfigureStopTime(macros.sec2nano(1.0))
    sim.ExecuteSimulation()

    np.testing.assert_allclose(np.asarray(gl.r_LP_P_Init).ravel(), site, atol=1e-6)
    elevation, azimuth = geodesy.geodetic_elevation_azimuth(np.asarray(recorder.r_BL_L).reshape(-1, 3)[-1],
                                                            geodesy.geocentric_latitude(site), lat)
    ref_el, ref_az = _direct_geodetic_elevation_azimuth(lat, lon, gs.altitude_m, r_sc)
    assert elevation[0] == pytest.approx(ref_el, abs=1e-9)
    assert azimuth[0] == pytest.approx(ref_az, abs=1e-9)
    # Basilisk's own (geocentric) elevation differs by the latitude tilt.
    assert abs(recorder.elevation[-1] - ref_el) < math.radians(0.2)
