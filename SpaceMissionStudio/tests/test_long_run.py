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

"""Runs past one Basilisk simulation's ~104-day limit, split into segments
(engine.long_run). The Basilisk tests shrink the segment length so a
split run takes seconds, then compare it with the same run done in one
piece."""

from pathlib import Path

import numpy as np
import pytest

from spacemissionstudio.engine import long_run
from spacemissionstudio.engine.results import ResultSet, TimeSeries
from spacemissionstudio.schema.scenario import OrbitIC, Scenario, SimSettings, SpacecraftConfig


def _scenario(duration_days, step_s=10.0):
    return Scenario(name="long", epoch_utc="2030-01-01T00:00:00",
                    sim_settings=SimSettings(duration_days=duration_days, dynamics_task_rate_s=step_s),
                    spacecraft=[SpacecraftConfig(name="sat-1", orbit=OrbitIC(
                        type="classical_elements", semi_major_axis_km=6778.0, eccentricity=0.0,  # [km]
                        inclination_deg=97.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0))])


def test_five_years_splits_into_whole_step_segments_under_the_limit():
    lengths = long_run.segment_lengths_s(_scenario(1826.25, step_s=30.0))  # [day], [s]
    assert len(lengths) == 21
    assert sum(lengths) == pytest.approx(1826.25 * 86400.0)  # [s]
    assert all(length <= 90.0 * 86400.0 for length in lengths)  # [s]
    assert all(length % 30.0 == 0.0 for length in lengths[:-1])  # [s] whole dynamics steps
    assert long_run.needs_segments(_scenario(1826.25)) and not long_run.needs_segments(_scenario(100.0))


def test_the_vizard_view_and_phasing_keeping_are_refused():
    scenario = _scenario(200.0)
    with pytest.raises(long_run.LongRunError, match="turn Vizard off"):
        long_run.check_segmentable(scenario, vizard_request=object())
    long_run.check_segmentable(scenario)


def test_appending_shifts_time_drops_the_repeated_sample_and_offsets_delta_v():
    first = ResultSet(scenario_name="s")
    first.add(TimeSeries("a.position_N", [0.0, 10.0], ("x",), [1.0, 2.0]))
    first.add(TimeSeries("a.station_keeping.delta_v", [0.0, 10.0], ("dv",), [0.0, 0.5]))
    second = ResultSet(scenario_name="s")
    second.add(TimeSeries("a.position_N", [0.0, 10.0], ("x",), [2.0, 3.0]))
    second.add(TimeSeries("a.station_keeping.delta_v", [0.0, 10.0], ("dv",), [0.0, 0.25]))

    merged = long_run._append(None, first, 0.0, {})
    merged = long_run._append(merged, second, 10.0, {"a.station_keeping.delta_v": 0.5})
    assert list(merged.series["a.position_N"].time_s) == [0.0, 10.0, 20.0]
    assert list(merged.series["a.position_N"].data[:, 0]) == [1.0, 2.0, 3.0]
    assert list(merged.series["a.station_keeping.delta_v"].data[:, 0]) == [0.0, 0.5, 0.75]


def _split(monkeypatch, segment_days):
    """Makes any run longer than ``segment_days`` split into segments of
    that length."""
    monkeypatch.setattr(long_run, "SEGMENT_DAYS", segment_days)
    monkeypatch.setattr(SimSettings, "_MAX_SINGLE_RUN_DAYS", segment_days)


def _load_template(name):
    from spacemissionstudio.schema import load_scenario

    return load_scenario(Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
                         / name)


def _attitude_angle_rad(sigma_a, sigma_b):
    """Angle between two MRP attitudes [rad], shadow set or not."""
    def quaternion(sigma):
        s2 = float(np.dot(sigma, sigma))
        return np.concatenate([[(1.0 - s2) / (1.0 + s2)], 2.0 * np.asarray(sigma) / (1.0 + s2)])
    return 2.0 * np.arccos(min(1.0, abs(float(np.dot(quaternion(sigma_a), quaternion(sigma_b))))))


@pytest.mark.requires_basilisk
def test_a_split_drag_orbit_ends_where_the_single_run_does(monkeypatch):
    """Template 18's orbit (J2, drag from generated space weather) with
    station keeping off: two days in one run, then as four half-day
    segments. Both end within 1 m (1e-5 m in a real run)."""
    from spacemissionstudio.engine.service import SimulationService

    scenario = _load_template("18_leo_station_keeping.json")
    scenario.spacecraft[0].station_keeping = None
    scenario.sim_settings.duration_days = 2.0  # [day]
    single = SimulationService(scenario).run().series["leo-sat-1.position_N"]
    _split(monkeypatch, 0.5)  # [day]
    split = SimulationService(scenario).run().series["leo-sat-1.position_N"]

    assert np.all(np.diff(split.time_s) > 0.0)
    assert split.time_s[-1] == pytest.approx(single.time_s[-1])
    assert len(split.time_s) == len(single.time_s)
    assert np.linalg.norm(split.data[-1] - single.data[-1]) < 1.0  # [m]


@pytest.mark.requires_basilisk
def test_station_keeping_carries_on_across_segments(monkeypatch):
    """Template 18 started 1.5 km low, over four days split into one-day
    segments: propellant and delta-V carry on from segment to segment and
    the totals match one run (identical in a real run: 4.71 m/s)."""
    from spacemissionstudio.engine.service import SimulationService

    scenario = _load_template("18_leo_station_keeping.json")
    scenario.spacecraft[0].orbit.semi_major_axis_km -= 1.5  # [km]
    scenario.sim_settings.duration_days = 4.0  # [day]
    single = SimulationService(scenario).run()
    _split(monkeypatch, 1.0)  # [day]
    split = SimulationService(scenario).run()

    dv = split.series["leo-sat-1.station_keeping.delta_v"].data[:, 0]  # [m/s]
    propellant = split.series["leo-sat-1.station_keeping.propellant_remaining"].data[:, 0]  # [kg]
    assert np.all(np.diff(dv) >= 0.0) and np.all(np.diff(propellant) <= 0.0)
    single_dv = single.series["leo-sat-1.station_keeping.delta_v"].data[-1, 0]  # [m/s]
    assert dv[-1] == pytest.approx(single_dv, rel=0.05)
    assert propellant[-1] == pytest.approx(single.series["leo-sat-1.station_keeping.propellant_remaining"].data[-1, 0],
                                           abs=1e-3)  # [kg]


@pytest.mark.requires_basilisk
def test_wheels_attitude_and_battery_carry_on_across_segments(monkeypatch):
    """The 150 kg preset pointing at the Sun with its wheels spun up, over
    two 40-minute segments: wheel speeds, attitude and battery charge
    show no jump at the boundary, and end where one run ends."""
    from spacemissionstudio.engine.orbit_design import raan_for_ltan_deg
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.engine.spacecraft_templates import SPACECRAFT_TEMPLATES
    from spacemissionstudio.schema.scenario import GravityConfig

    spacecraft = next(t for t in SPACECRAFT_TEMPLATES if "150" in t.name).build()
    spacecraft.name = "sat-1"
    spacecraft.orbit = OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,  # [km]
                               inclination_deg=97.6, raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"),
                               arg_periapsis_deg=0.0, true_anomaly_deg=0.0)
    for wheel, rpm in zip([a for a in spacecraft.actuators if a.kind == "reaction_wheel"], (800.0, -600.0, 400.0)):
        wheel.params["Omega"] = rpm  # [RPM]
    scenario = Scenario(name="w", epoch_utc="2030-01-01T00:00:00", simulation_mode="full_attitude",
                        gravity=GravityConfig(central_body="earth", central_body_degree=2,
                                              third_body_perturbers=["sun"]),
                        sim_settings=SimSettings(duration_days=80.0 / 1440.0, dynamics_task_rate_s=1.0),  # [day], [s]
                        spacecraft=[spacecraft])
    single = SimulationService(scenario).run()
    _split(monkeypatch, 40.0 / 1440.0)  # [day]
    split = SimulationService(scenario).run()

    wheels = split.series["sat-1.rw_speeds"]
    boundary = int(np.searchsorted(wheels.time_s, 2400.0))  # [s] first sample of the second segment
    steps = np.abs(np.diff(wheels.data, axis=0)).max(axis=1)  # [rad/s]
    assert steps[boundary - 1] < 0.5 + 3.0 * np.median(steps)  # [rad/s] no jump at the boundary
    assert np.allclose(wheels.data[-1], single.series["sat-1.rw_speeds"].data[-1], atol=0.5)  # [rad/s]

    sigma = split.series["sat-1.attitude_sigma_BN"].data
    assert _attitude_angle_rad(sigma[boundary - 1], sigma[boundary]) < 1e-3  # [rad]
    assert _attitude_angle_rad(sigma[-1], single.series["sat-1.attitude_sigma_BN"].data[-1]) < 1e-3  # [rad]

    charge = split.series["sat-1.battery_charge"].data[:, 0]  # [W*hr]
    assert abs(charge[boundary] - charge[boundary - 1]) < 0.1  # [W*hr]
    assert charge[-1] == pytest.approx(single.series["sat-1.battery_charge"].data[-1, 0], abs=0.1)  # [W*hr]


@pytest.mark.requires_basilisk
def test_live_progress_runs_over_the_whole_split_run_and_cancel_keeps_what_ran(monkeypatch):
    """The GUI path: progress climbs once from 0 to 1 over all segments
    (not once per segment), and cancelling in the second segment returns
    the first segment plus what the second has run so far."""
    from spacemissionstudio.engine.service import SimulationCancelled, SimulationService

    scenario = _scenario(1.0, step_s=30.0)  # [day], [s]
    _split(monkeypatch, 0.25)  # [day]
    fractions = []
    result = SimulationService(scenario).run_live(lambda partial, fraction: fractions.append(fraction))
    assert fractions == sorted(fractions) and fractions[-1] == pytest.approx(1.0)
    assert 50 <= len(fractions) <= 70
    assert result.series["sat-1.position_N"].time_s[-1] == pytest.approx(86400.0)  # [s]

    seen = []
    with pytest.raises(SimulationCancelled) as cancelled:
        SimulationService(scenario).run_live(lambda partial, fraction: seen.append(fraction),
                                             should_cancel=lambda: seen[-1] > 0.4)
    end_s = cancelled.value.partial_result.series["sat-1.position_N"].time_s[-1]  # [s]
    assert 0.25 * 86400.0 < end_s < 0.5 * 86400.0  # [s] stopped in the second segment


def test_recording_every_step_of_a_long_run_is_flagged():
    from spacemissionstudio.engine.scenario_checks import scenario_warnings

    scenario = _scenario(1826.25, step_s=30.0)  # [day], [s]
    assert any("5.3 million samples per series" in w for w in scenario_warnings(scenario))
    scenario.sim_settings.record_interval_s = 600.0  # [s]
    assert not any("samples per series" in w for w in scenario_warnings(scenario))
