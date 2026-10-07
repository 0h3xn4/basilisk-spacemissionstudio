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

"""Tests for engine.series_names.expected_series_names -- the pre-run
prediction behind the Report command's series pick-list."""

from pathlib import Path

import pytest

from spacemissionstudio.engine.series_names import expected_series_names
from spacemissionstudio.schema import load_scenario

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
_TEMPLATE_PATHS = sorted(_TEMPLATES_DIR.glob("*.json"))


def test_template_05_matches_a_real_run():
    """The exact series set of a real template-05 run (the user's own
    results export: 40 CSV files)."""
    names = expected_series_names(load_scenario(_TEMPLATES_DIR / "05_formation_flying_phasing.json"))
    elements = ("arg_periapsis", "eccentricity", "inclination", "raan", "semi_major_axis", "true_anomaly")
    expected = set()
    for sc in ("chief-1", "follower-1"):
        expected |= {f"{sc}.position_N", f"{sc}.velocity_N"}
        expected |= {f"{sc}.orbit_elements.{e}" for e in elements}
        expected |= {f"{sc}.orbit_elements_mean.{e}" for e in elements}
        expected |= {f"{sc}.station_keeping.{p}" for p in ("altitude", "burn_on", "delta_v", "propellant_remaining")}
    expected |= {f"follower-1.phasing_keeping.{p}"
                 for p in ("delta_v", "relative_semi_major_axis", "separation_error", "state")}
    assert set(names) == expected
    assert len(names) == 40


def test_devices_and_ground_stations_add_their_series():
    names = expected_series_names(load_scenario(_TEMPLATES_DIR / "19_sun_pointing_comms_link.json"))
    assert "leo-comms-1.comms_pointing.active_mode" in names
    assert "leo-comms-1.battery_charge" in names
    assert any(n.endswith(".access_to_leo-comms-1.link_margin_db") for n in names)
    imu = expected_series_names(load_scenario(_TEMPLATES_DIR / "07_attitude_pointing_with_adcs_hardware.json"))
    assert any(n.endswith(".gyro") for n in imu) and any(n.endswith(".rw_speeds") for n in imu)


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_names_are_sorted_and_unique(path):
    names = expected_series_names(load_scenario(path))
    assert names == sorted(set(names))


@pytest.mark.requires_basilisk
@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_prediction_matches_a_real_run(path):
    """The prediction must equal the series a real (shortened) run
    produces -- a wrong name would make a Report command fail."""
    from spacemissionstudio.engine.service import SimulationService

    scenario = load_scenario(path)
    scenario.mission_sequence = []
    scenario.monte_carlo.enabled = False
    scenario.sim_settings.duration_days = 120.0 / 86400.0  # [day] two minutes
    result = SimulationService(scenario).run()
    assert sorted(result.series) == expected_series_names(scenario)
