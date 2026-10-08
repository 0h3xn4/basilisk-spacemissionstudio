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

"""Tests for engine.scenario_checks -- pre-run pass prediction and
warnings. No Basilisk needed."""

import math
import time
from pathlib import Path

import numpy as np
import pytest

from spacemissionstudio.engine.scenario_checks import pass_summary, predict_passes, scenario_warnings
from spacemissionstudio.schema import load_scenario

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"


def _template(prefix):
    return load_scenario(next(_TEMPLATES_DIR.glob(f"{prefix}_*.json")))


@pytest.mark.requirement("E-ST-10-09C 5.4.6a")
def test_template_19_passes_match_an_independent_propagation():
    """Reference: the full Basilisk run of template 19 with the WGS-84 site
    (ECSS-E-ST-10-09C 5.4.6a; scratch check 2026-10-08) gives geodetic
    elevation above 10 deg at 10.4-18.2 min (peak 61.6 deg) and
    106.8-111.8 min (peak 16.1 deg). The prediction samples every 30 s, so
    its peak of a high pass is up to ~1.5 deg low."""
    passes = predict_passes(_template("19"))
    assert [(p.station, p.spacecraft) for p in passes] == [("berlin-gs", "leo-comms-1")] * 2
    for got, (start_min, end_min, peak_deg) in zip(passes, [(10.4, 18.2, 61.6), (106.8, 111.8, 16.1)]):
        assert got.start_s / 60 == pytest.approx(start_min, abs=1.0)  # [min]
        assert got.end_s / 60 == pytest.approx(end_min, abs=1.0)  # [min]
        assert got.peak_elevation_deg == pytest.approx(peak_deg, abs=2.0)  # [deg]
    assert pass_summary(_template("19")) == ["berlin-gs: 2 passes, first at 10 min for 8 min (peak 60 deg)"]


def test_a_cartesian_orbit_predicts_the_same_passes():
    from spacemissionstudio.schema.scenario import OrbitIC

    scenario = _template("19")
    o = scenario.spacecraft[0].orbit
    a = o.semi_major_axis_km  # [km]
    v = math.sqrt(398600.4415 / a)  # [km/s] circular
    i, raan, u = math.radians(o.inclination_deg), math.radians(o.raan_deg), math.radians(o.true_anomaly_deg)
    rot = np.array([[math.cos(raan), -math.sin(raan) * math.cos(i)], [math.sin(raan), math.cos(raan) * math.cos(i)],
                    [0.0, math.sin(i)]])
    r_km = rot @ np.array([a * math.cos(u), a * math.sin(u)])
    v_km_s = rot @ np.array([-v * math.sin(u), v * math.cos(u)])
    expected = [(p.start_s, p.end_s) for p in predict_passes(scenario)]
    scenario.spacecraft[0].orbit = OrbitIC(type="cartesian", position_km=list(r_km), velocity_km_s=list(v_km_s))
    got = [(p.start_s, p.end_s) for p in predict_passes(scenario)]
    assert len(got) == len(expected)
    for (s1, e1), (s2, e2) in zip(got, expected):
        assert s1 == pytest.approx(s2, abs=60.0) and e1 == pytest.approx(e2, abs=60.0)  # [s]


def test_unsupported_cases_predict_nothing_rather_than_guess():
    scenario = _template("19")
    scenario.gravity.central_body = "mars"
    assert predict_passes(scenario) is None and pass_summary(scenario) == []
    assert predict_passes(_template("01")) is None  # no ground stations


def test_a_late_first_pass_and_no_pass_at_all_are_both_flagged():
    scenario = _template("19")
    scenario.epoch_utc = "2030-01-01T00:00:00"  # the old epoch: first pass ~8.2 h in
    scenario.sim_settings.duration_days = 0.5
    assert scenario_warnings(scenario) == ["berlin-gs: the first pass only comes at 8.2 h of a 12.0 h run"]
    scenario.sim_settings.duration_days = 0.25
    assert scenario_warnings(scenario) == [
        "berlin-gs: no pass in this run -- the first comes at 8.2 h; change the epoch or lengthen the run"]
    scenario.ground_stations[0].min_elevation_deg = 89.9  # practically never
    assert scenario_warnings(scenario)[0].startswith("berlin-gs: no pass in this run or the 2 days after it")
    assert scenario_warnings(_template("19")) == []


def test_mission_sequence_runs_skip_the_pass_check():
    """Their length comes from the commands, not sim_settings.duration_days."""
    from spacemissionstudio.schema.command import Command

    scenario = _template("19")
    scenario.epoch_utc = "2030-01-01T00:00:00"
    scenario.mission_sequence = [Command(kind="propagate", params={"stop_condition": "duration",
                                                                    "duration_days": 0.5})]
    assert scenario_warnings(scenario) == []


def test_a_sun_pointing_spacecraft_whose_sun_sensor_faces_away_is_flagged():
    """Templates 07 and 20 shipped their only sun sensor on +X while Sun
    pointing turned +Z to the Sun."""
    scenario = _template("07")
    assert scenario_warnings(scenario) == []
    css = next(s for s in scenario.spacecraft[0].sensors if s.kind == "coarse_sun_sensor")
    css.params["nHat_B"] = [1.0, 0.0, 0.0]
    assert scenario_warnings(scenario) == [
        "sat-1: no sun sensor faces the Sun-pointing axis, so none sees the Sun once pointed"]


def test_station_keeping_without_drag_is_flagged():
    """An altitude-hold deadband with nothing to decay the orbit never trips
    (the lesson template 03 used to teach, before it got real GEO control)."""
    from spacemissionstudio.schema.scenario import StationKeepingConfig

    scenario = _template("18")
    sc = scenario.spacecraft[0]
    assert scenario_warnings(scenario) == []  # drag on
    sc.enable_drag = False
    assert scenario_warnings(scenario) == [
        f"{sc.name}: with drag off its average altitude barely drifts, so the "
        f"{sc.station_keeping.deadband_km:g} km deadband may never trip"]
    assert isinstance(sc.station_keeping, StationKeepingConfig)


def test_every_template_is_checked_quickly_and_none_is_flagged():
    for path in sorted(_TEMPLATES_DIR.glob("*.json")):
        scenario = load_scenario(path)
        start = time.perf_counter()
        warnings = scenario_warnings(scenario)
        pass_summary(scenario)
        assert time.perf_counter() - start < 0.5, path.name  # [s] runs on every edit in the Explain tab
        assert not warnings, (path.name, warnings)


def test_a_half_edited_scenario_never_raises():
    scenario = _template("19")
    scenario.spacecraft[0].orbit.semi_major_axis_km = None
    scenario.spacecraft[0].sensors = None
    assert isinstance(scenario_warnings(scenario), list)
