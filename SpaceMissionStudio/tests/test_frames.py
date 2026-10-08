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

"""Frame definitions and per-series frames in the run metadata
(ECSS-E-ST-10-09C 5.2.3, 5.3.2, 5.4.1, 5.4.3; remediation R02)."""

import json
from pathlib import Path

import pytest

from spacemissionstudio.engine import frames

pytestmark = pytest.mark.requirement("E-ST-10-09C 5.4.1a", "E-ST-10-09C 5.4.1h", "E-ST-10-09C 5.3.2a")

_TEMPLATES = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"


@pytest.mark.requirement("E-ST-10-09C 5.3.2b", "E-ST-10-09C 5.3.2c")
def test_every_frame_has_a_unique_name_mnemonic_and_origin():
    """Each frame is named, has a unique mnemonic and an origin; the
    inertial frame states its epoch and time scale."""
    definitions = frames.definitions("earth", "ITRF93")
    assert set(definitions) == {"N", "P", "B", "H", "L", "TEME"}
    assert len({d["name"] for d in definitions.values()}) == len(definitions)
    assert all(d["origin"] and d["axes"] for d in definitions.values())
    assert definitions["N"]["epoch"].startswith("J2000.0")
    assert "ITRF93" in definitions["P"]["axes"]
    assert "IAU_MOON" in frames.definitions("moon")["P"]["axes"]


def test_series_frames_follow_the_naming_convention():
    """Suffixes give the frame: _N inertial, _B body, sigma_BN attitude of
    B relative to N, access elevation/azimuth topocentric."""
    names = ["sat.position_N", "sat.body_rate_omega_BN_B", "sat.attitude_sigma_BN", "sat.sun_heading_body",
             "sat.orbit_elements.inclination", "gs.access_to_sat.elevation", "sat.rw_speeds"]
    assert frames.series_frames(names) == {
        "sat.position_N": "N", "sat.body_rate_omega_BN_B": "B", "sat.attitude_sigma_BN": "B relative to N",
        "sat.sun_heading_body": "B", "sat.orbit_elements.inclination": "N", "gs.access_to_sat.elevation": "L"}


@pytest.mark.requires_basilisk
@pytest.mark.requirement("E-ST-10-09C 5.4.2a", "E-ST-10-09C 5.4.2b", "E-ST-10-09C 5.4.3a", "E-ST-10-09C 5.4.3b",
                         "E-ST-10-09C 5.4.4a")
def test_run_metadata_carries_frames_time_scales_and_units(tmp_path):
    """A real run's provenance.json names the time variable and the frames
    of its series, and every series has units ('-' when dimensionless)."""
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(next(_TEMPLATES.glob("19_*.json")))
    scenario.sim_settings.duration_days = 0.01  # [day]
    result = SimulationService(scenario).run()
    provenance = json.loads(Path(result.export_csv(tmp_path)["provenance"]).read_text())
    assert provenance["time_system"]["time_variable"] == "TDB seconds since the scenario epoch"
    assert provenance["frames"]["N"]["name"].startswith("Inertial (EME2000")
    assert provenance["series_frames"]["leo-comms-1.position_N"] == "N"
    assert provenance["series_frames"]["berlin-gs.access_to_leo-comms-1.elevation"] == "L"
    assert "N -> P" in provenance["transformations"]
    assert all(series.units and str(series.units).strip() for series in result.series.values())


@pytest.mark.requirement("E-ST-10-09C 5.3.2d")
def test_each_transformation_has_a_unique_name_between_defined_frames():
    """Transformations are named "Y -> X" once each, between frames that
    :func:`frames.definitions` defines."""
    mnemonics = set(frames.definitions("earth", "ITRF93"))
    pairs = [tuple(name.split(" -> ")) for name in frames.TRANSFORMATIONS]
    assert len(set(pairs)) == len(pairs)
    assert all(len(pair) == 2 and set(pair) <= mnemonics for pair in pairs)


@pytest.mark.requirement("E-ST-10-09C 5.4.1d", "E-ST-10-09C 5.4.1e", "E-ST-10-09C 5.4.1f")
def test_frame_rotations_are_orthonormal_and_right_handed():
    """TEME -> N (the only imported frame) is a proper rotation
    (orthonormal, determinant +1); the topocentric frame is South-East-
    Zenith (S x E = Z) with azimuth from North to East, and its geodetic
    tilt keeps lengths. Orbit inputs are only classical elements,
    cartesian N states and TLEs (TEME), none of them left-handed."""
    import math
    from datetime import datetime

    import numpy as np

    from spacemissionstudio.engine import geodesy, tle
    from spacemissionstudio.schema.scenario import ORBIT_IC_TYPES

    teme = tle.teme_to_eme2000_matrix(datetime(2026, 10, 8))
    np.testing.assert_allclose(teme @ teme.T, np.eye(3), atol=1e-15)
    assert np.linalg.det(teme) == pytest.approx(1.0, abs=1e-15)
    south, east, zenith = np.eye(3)
    np.testing.assert_array_equal(np.cross(south, east), zenith)
    elevation, azimuth = geodesy.geodetic_elevation_azimuth([zenith, -south, east], 0.9, 0.9)
    np.testing.assert_allclose(elevation, [math.pi / 2, 0.0, 0.0], atol=1e-15)
    np.testing.assert_allclose(azimuth[1:], [0.0, math.pi / 2], atol=1e-15)  # North 0, East +90 deg
    theta = 0.003  # [rad] geocentric - geodetic latitude
    tilted_zenith = [math.sin(theta), 0.0, math.cos(theta)]
    elevation, _ = geodesy.geodetic_elevation_azimuth([tilted_zenith], 0.9 + theta, 0.9)
    assert elevation[0] == pytest.approx(math.pi / 2, abs=1e-7)
    assert ORBIT_IC_TYPES == ("classical_elements", "cartesian", "tle")
