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

"""Each bundled template, run for real, does what its description says.

Several templates shipped claims their own setup could not deliver (16
failed at its first command, 19 had no contact for 8 h, 20's sensor never
saw the Sun, 07's battery never moved). The only all-template Basilisk
test strips the Mission Sequence and runs two minutes, so none of that
was caught. These tests run each template as shipped -- shortened only
where the claim allows -- and check its headline claim.
"""

from pathlib import Path

import numpy as np
import pytest

from spacemissionstudio.schema import load_scenario

pytestmark = pytest.mark.requires_basilisk

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"


def _template(prefix):
    return load_scenario(next(_TEMPLATES_DIR.glob(f"{prefix}_*.json")))


def _run(scenario, duration_days=None):
    from spacemissionstudio.engine.service import SimulationService

    if duration_days is not None:
        scenario.sim_settings.duration_days = duration_days
    return SimulationService(scenario).run()


def _at(series, t_s, column=0):
    return float(series.data[int(np.argmin(np.abs(series.time_s - t_s))), column])


def test_16_lambert_transfer_lands_on_its_target():
    """Used to fail at its first command (a report before any propagate);
    the description promises arrival within about 2 m."""
    from spacemissionstudio.engine.mission_engine import MissionEngine

    scenario = _template("16")
    _result, summary = MissionEngine(scenario).run()
    assert [r.label for r in summary.reports] == ["Before transfer", "After transfer (should match target_position_m)"]
    target = np.array(scenario.mission_sequence[2].params["target_position_m"])  # [m]
    assert np.linalg.norm(summary.reports[1].values["sat-1.position_N"] - target) < 5.0  # [m]


def test_19_first_berlin_pass_comes_early_and_switches_the_pointing_mode():
    """Used to start at midnight UTC: no contact for the first 8 h."""
    result = _run(_template("19"), duration_days=25.0 / 1440.0)  # [day] the first pass only
    access = result.series["berlin-gs.access_to_leo-comms-1.has_access"]
    visible = access.data[:, 0] > 0.5
    assert visible.any()
    first_s = float(access.time_s[np.argmax(visible)])  # [s]
    assert 5 * 60 <= first_s <= 15 * 60
    mode = result.series["leo-comms-1.comms_pointing.active_mode"]
    assert _at(mode, first_s + 120.0) == 1.0  # pointing at the station during the pass
    assert _at(mode, first_s - 120.0) == 0.0  # Sun pointing before it


def test_20_thermal_sensor_heats_in_sunlight_and_cools_in_eclipse():
    """therm-1 used to face +X, edge-on to the Sun once Sun-pointed."""
    result = _run(_template("20"), duration_days=70.0 / 1440.0)  # [day] first sunlit arc and eclipse
    therm = result.series["sat-1.sensor.therm-1"]
    start, sunlit_end, eclipse_end = _at(therm, 60.0), _at(therm, 22 * 60.0), _at(therm, 57 * 60.0)  # [C]
    assert sunlit_end > start + 10.0
    assert eclipse_end < sunlit_end - 10.0
    motor = result.series["sat-1.actuator.rw-1.motor_temperature"].data[:, 0]  # [C]
    assert 0.01 < motor.max() - 20.0 < 0.2  # "only ~0.05 C above its 20 C ambient"


def test_07_battery_charges_in_sunlight_and_drains_in_eclipse():
    """Used to start full with a 0 W bus load: flat at 80 Wh all run."""
    result = _run(_template("07"), duration_days=60.0 / 1440.0)  # [day]
    charge = result.series["sat-1.battery_charge"]
    assert _at(charge, 20 * 60.0) > _at(charge, 0.0) + 5.0  # [Wh] charging
    assert _at(charge, 55 * 60.0) < _at(charge, 25 * 60.0) - 3.0  # [Wh] eclipse at the 12 W bus load
    sun = result.series["sat-1.sun_heading_body"]
    assert sun.data[-1, 2] > 0.99  # +Z settled on the Sun


def test_03_geo_altitude_never_trips_the_deadband():
    """The recast lesson: at GEO the averaged altitude barely moves."""
    result = _run(_template("03"), duration_days=3.0)  # [day]
    assert result.series["geo-sat-1.station_keeping.burn_on"].data.max() == 0.0
    smoothed = result.series["geo-sat-1.station_keeping.altitude"].data[:, 1]
    assert np.abs(smoothed - 35786e3).max() < 1.5e3  # [m]


def test_10_uncontrolled_spacecraft_drifts_under_gravity_gradient():
    """Its attitude used to be unrecorded (only visible in Vizard)."""
    result = _run(_template("10"), duration_days=2.0 / 24.0)  # [day]
    sigma = result.series["sat-1.attitude_sigma_BN"]
    assert np.linalg.norm(sigma.data[0]) < 1e-6
    assert np.linalg.norm(sigma.data[-1]) > 0.1


def test_12_thrusters_dump_wheel_momentum():
    result = _run(_template("12"))
    firing = result.series["sat-1.thruster_on_time"].data.max(axis=1) > 0.0
    assert np.count_nonzero(np.diff(firing.astype(int)) == 1) == 3  # "three in the first 4 minutes"
    speeds = result.series["sat-1.rw_speeds"].data  # [rad/s]
    assert speeds[-1, 0] < 0.9 * speeds[0, 0]


def test_17_fuel_tank_drains_about_as_described():
    """On an earlier 10 kg*m^2 bus the thrusters' on-times stayed under their
    20 ms minimum: no propellant used at all."""
    result = _run(_template("17"))
    fuel = result.series["sat-1.fuel_mass_remaining"].data[:, 0]
    assert 0.1e-3 <= fuel[0] - fuel[-1] <= 1.0e-3  # [kg] "about 0.3 g of the 0.5 kg"


def test_11_thrusters_settle_the_attitude_within_a_few_minutes():
    result = _run(_template("11"), duration_days=4.0 / 1440.0)  # [day]
    assert result.series["sat-1.thruster_on_time"].data.max() > 0.02  # [s] real pulses, above the minimum on-time
    sigma = result.series["sat-1.attitude_sigma_BN"]
    assert np.linalg.norm(sigma.data[-1]) < 0.03  # within a few degrees ("about 2 minutes")


def test_08_prograde_burn_raises_the_orbit_on_the_far_side():
    from spacemissionstudio.engine.mission_engine import MissionEngine

    _result, summary = MissionEngine(_template("08")).run()
    before, after = summary.reports
    a_before = before.values["sat-1.orbit_elements.semi_major_axis"][0]  # [m]
    a_after = after.values["sat-1.orbit_elements.semi_major_axis"][0]  # [m]
    # [m] vis-viva: +50 m/s prograde at 400 km raises a by ~88 km (osculating
    # snapshots, after half a day of drag and J2: ~76 km in a real run)
    assert 60e3 < a_after - a_before < 100e3
    assert after.values["sat-1.orbit_elements.eccentricity"][0] > 0.01  # now an ellipse


def test_13_torque_rods_steer_the_wheels_to_their_target_speeds():
    scenario = _template("13")
    result = _run(scenario)
    speeds_rpm = result.series["sat-1.rw_speeds"].data[-1] * 60.0 / (2.0 * np.pi)  # [RPM]
    targets_rpm = np.array(scenario.spacecraft[0].magnetic_momentum_management.wheel_speed_biases_rad_s) \
        * 60.0 / (2.0 * np.pi)  # [RPM]
    assert np.abs(speeds_rpm - targets_rpm).max() < 0.5  # [RPM] "within ~0.5 RPM"


def test_14_css_estimate_settles_on_the_sun_axis():
    result = _run(_template("14"))
    estimate = result.series["sat-1.sun_heading_body_estimated"].data[-1]
    assert estimate[2] / np.linalg.norm(estimate) > 0.98  # near [0, 0, 1]


def test_21_off_centre_array_loads_the_wheels_unless_torque_rods_unload_them():
    """A real run: rods-off stores ~3.2 N*m*s by the end of the day,
    rods-on keeps its wheels under ~80 RPM."""
    result = _run(_template("21"))
    js = 12.0 / (6000.0 * np.pi / 30.0)  # [kg*m^2] HR12 12 N*m*s at 6000 RPM
    stored = {name: np.linalg.norm(result.series[f"{name}.rw_speeds"].data[-1]) * js  # [N*m*s]
              for name in ("rods-off", "rods-on")}
    assert 2.5 < stored["rods-off"] < 4.0  # [N*m*s] "about 3.2 N*m*s stored by the end"
    rods_on_rpm = result.series["rods-on.rw_speeds"].data[-1] * 30.0 / np.pi  # [RPM]
    assert np.abs(rods_on_rpm).max() < 150.0  # [RPM] "stay under ~80 RPM"
    for name in ("rods-off", "rods-on"):
        sun = result.series[f"{name}.sun_heading_body"]
        assert sun.data[sun.time_s > 600.0, 2].min() > 0.99  # still Sun-pointed
