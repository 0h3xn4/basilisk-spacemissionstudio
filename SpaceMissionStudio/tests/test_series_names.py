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


# -- featured_series: the Results tab's one-click suggestions ------------------

def test_featured_series_follow_the_description_in_order():
    from spacemissionstudio.engine.series_names import featured_series

    assert featured_series(load_scenario(_TEMPLATES_DIR / "19_sun_pointing_comms_link.json")) == [
        "berlin-gs.access_to_leo-comms-1.has_access",
        "leo-comms-1.comms_pointing.active_mode",
        "leo-comms-1.comms_pointing.pointing_error_deg",
        "leo-comms-1.battery_charge",
        "berlin-gs.access_to_leo-comms-1.link_margin_db",
    ]


def test_featured_series_expand_shorthand_siblings():
    """ "sat-1.orbit_elements_mean.arg_periapsis and .raan" names two series."""
    from spacemissionstudio.engine.series_names import featured_series

    names = featured_series(load_scenario(_TEMPLATES_DIR / "02_elliptical_orbit_with_perturbations.json"))
    assert names[:2] == ["sat-1.orbit_elements_mean.arg_periapsis", "sat-1.orbit_elements_mean.raan"]


def test_featured_series_skip_names_a_run_will_not_produce():
    from spacemissionstudio.engine.series_names import featured_series

    scenario = load_scenario(_TEMPLATES_DIR / "07_attitude_pointing_with_adcs_hardware.json")
    scenario.description = ("Summary.\n\nWhat to look at:\n- sat-1.rw_speedz (a typo) and sat-1.rw_speeds.\n"
                            "- e.g. 0.5 kg, version 1.2.3.\n\nTry changing:\n- sat-1.battery_charge (not this section)")
    assert featured_series(scenario) == ["sat-1.rw_speeds"]
    scenario.description = ""
    assert featured_series(scenario) == []


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_every_series_a_template_points_at_exists(path):
    """A "What to look at" name that no run produces would be a dead
    suggestion (and a wrong instruction): every dotted name that starts
    with one of the template's own spacecraft or station names, or is a
    ".sibling" shorthand, must resolve to a real series."""
    import re

    from spacemissionstudio.engine.series_names import _what_to_look_at, featured_series

    scenario = load_scenario(path)
    owners = [sc.name for sc in scenario.spacecraft] + [gs.name for gs in scenario.ground_stations]
    featured = featured_series(scenario)
    for line in _what_to_look_at(scenario.description):
        for token in re.findall(r"(?<![\w.-])[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+", line):
            if token.split(".", 1)[0] in owners:
                assert token in featured, (path.name, token)
        siblings = re.findall(r"(?<![\w.-])\.([A-Za-z_][A-Za-z0-9_-]*)", line)
        assert all(any(name.endswith(f".{s}") for name in featured) for s in siblings), (path.name, siblings)


def test_an_uncontrolled_spacecraft_still_records_its_attitude():
    """Template 10's gravity-gradient drift: with no attitude control there
    was no navigation recorder, so no attitude series -- the lesson could
    only be seen in Vizard. It now comes from the spacecraft state."""
    names = expected_series_names(load_scenario(_TEMPLATES_DIR / "10_gravity_gradient_torque.json"))
    assert {"sat-1.attitude_sigma_BN", "sat-1.body_rate_omega_BN_B"} <= set(names)
    assert "sat-1.control_torque" not in names
    orbit_only = expected_series_names(load_scenario(_TEMPLATES_DIR / "01_two_body_circular_orbit.json"))
    assert not any("attitude" in name for name in orbit_only)
