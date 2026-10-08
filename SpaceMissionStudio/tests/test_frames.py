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
@pytest.mark.requirement("E-ST-10-09C 5.4.2a", "E-ST-10-09C 5.4.3a", "E-ST-10-09C 5.4.3b")
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
