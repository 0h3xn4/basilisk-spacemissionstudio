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


def test_03_geo_slot_is_held_in_longitude_and_inclination():
    """A real 45-day run: east-west burns at days 12.5, 21.4, 31.1, 36.9, north-
    south burns at days 16.4 and 30.4. 32 days covers three and two of them."""
    result = _run(_template("03"), duration_days=32.0)  # [day]
    prefix = "geo-sat-1.geo_station_keeping."
    longitude = np.degrees(result.series[prefix + "longitude"].data[:, 1])  # [deg] one-day fit
    assert 9.945 < np.nanmin(longitude) and np.nanmax(longitude) < 10.055  # [deg] box 10 +/- 0.05
    inclination = np.degrees(result.series[prefix + "inclination"].data[:, 0])  # [deg]
    assert inclination[0] < 1e-3  # starts in Earth's true equator
    assert inclination.max() < 0.053  # [deg] limit 0.05
    burns = result.series[prefix + "burn_on"].data > 0.5
    starts = [np.count_nonzero(np.diff(burns[:, col].astype(int)) == 1) for col in (0, 1)]
    assert starts == [3, 2]  # [east-west, north-south]


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
    """A real run: rods-off stores ~1.7 N*m*s by the end of the day (1.72,
    rw-x -815 RPM), rods-on keeps its wheels under ~20 RPM (18.7): January
    2030 on NASA MSFC's 50th-percentile prediction, Cd 3.0 (re-measured
    after F-07 and F-09, compliance/drag_remeasure.md)."""
    result = _run(_template("21"))
    js = 12.0 / (6000.0 * np.pi / 30.0)  # [kg*m^2] HR12 12 N*m*s at 6000 RPM
    stored = {name: np.linalg.norm(result.series[f"{name}.rw_speeds"].data[-1]) * js  # [N*m*s]
              for name in ("rods-off", "rods-on")}
    assert 1.5 < stored["rods-off"] < 1.9  # [N*m*s] "about 1.7 N*m*s stored by the end"
    rods_on_rpm = result.series["rods-on.rw_speeds"].data[-1] * 30.0 / np.pi  # [RPM]
    assert np.abs(rods_on_rpm).max() < 25.0  # [RPM] "stay under ~20 RPM"
    for name in ("rods-off", "rods-on"):
        sun = result.series[f"{name}.sun_heading_body"]
        assert sun.data[sun.time_s > 600.0, 2].min() > 0.99  # still Sun-pointed


def test_22_starter_has_four_berlin_passes_and_a_sun_synchronous_plane():
    """The starter's description: four Berlin passes in its day, the first
    10-18 min in, and the mean orbit plane turning ~1 deg a day."""
    result = _run(_template("22"))
    access = result.series["berlin-gs.access_to_my-sat.has_access"]
    visible = np.concatenate([[0], (access.data[:, 0] > 0.5).astype(int), [0]])
    starts = access.time_s[np.flatnonzero(np.diff(visible) == 1)]  # [s]
    assert len(starts) == 4
    assert 9 * 60 <= starts[0] <= 12 * 60  # [s]
    raan = result.series["my-sat.orbit_elements_mean.raan"]
    rate_deg_day = np.degrees(raan.data[-1, 0] - raan.data[0, 0]) / (raan.time_s[-1] / 86400.0)  # [deg/day]
    assert 0.9 < rate_deg_day < 1.1  # Sun-synchronous: 0.986 deg/day


def test_23_mission_sequence_reports_at_the_pass_and_the_wheels_unload():
    """Reports at pass start and end (about 10 and 18 min in); the wheels
    spin up to turn to the Sun, then the torque rods bring them back."""
    from spacemissionstudio.engine.mission_engine import MissionEngine

    result, summary = MissionEngine(_template("23")).run()
    assert [r.label for r in summary.reports] == ["Pass start", "Pass end"]
    start_s, end_s = (r.t_s for r in summary.reports)  # [s]
    assert 9 * 60 <= start_s <= 12 * 60 and 16 * 60 <= end_s <= 20 * 60
    margin = summary.reports[0].values["berlin-gs.access_to_smallsat-1.link_margin_db"][0]  # [dB]
    assert 8.0 < margin < 14.0  # "11 dB at the 10 deg edge of the pass"
    rpm = np.abs(result.series["smallsat-1.rw_speeds"].data) * 30.0 / np.pi  # [RPM]
    assert 200.0 < rpm.max() < 400.0  # "up to ~300 RPM"
    assert rpm[-1].max() < 5.0  # [RPM] "back near zero"
    assert result.series["smallsat-1.sun_heading_body"].data[-1, 2] > 0.99  # Sun-pointed


def test_24_mean_element_control_holds_tens_of_metres():
    """Within ~65 m after the first day, at a few tenths of a m/s; three of
    its fourteen days."""
    result = _run(_template("24"), duration_days=3.0)  # [day]
    error = result.series["follower-1.phasing_keeping.separation_error"]
    error_m = np.radians(error.data[:, 0]) * 6928.0e3  # [m] along-track arc on the chief's orbit
    assert np.abs(error_m[error.time_s > 86400.0]).max() < 80.0  # [m]
    delta_v = result.series["follower-1.phasing_keeping.delta_v"].data[-1, 0]  # [m/s]
    assert 0.1 < delta_v < 0.5  # [m/s] 0.20 the first day, 0.46 in 14 days
    force = result.series["follower-1.phasing_keeping.force"].data  # [N] commanded, applied
    assert force[:, 0].max() < 0.01  # requests of a few mN, under the 50 mN thruster


def test_26_the_memory_overflows_between_berlin_pass_groups_and_the_patch_link_holds():
    """The first day: the 3 Gbit memory is full by about 12 h in and data
    is lost; Berlin's link closes throughout its passes, with ~16 dB at the
    best and ~3.7 dB at the 10 deg edge, 65 deg off the patch's boresight."""
    result = _run(_template("26"), duration_days=1.0)  # [day]
    stored = result.series["eo-sat.data_handling.stored"]
    full = stored.time_s[stored.data[:, 0] > 3.0e9 - 0.1e9]  # [s] within 0.1 Gbit of the capacity
    assert full.size and 10.0 * 3600.0 < full[0] < 13.0 * 3600.0
    assert result.series["eo-sat.data_handling.data_lost"].data[-1, 0] > 0.0
    pair = "berlin-gs.access_to_eo-sat"
    margin = result.series[f"{pair}.link_margin_db"].data[:, 0]  # [dB]
    assert 15.0 < np.nanmax(margin) < 17.5 and 2.5 < np.nanmin(margin) < 4.5
    angle = result.series[f"{pair}.antenna_off_boresight"].data[:, 0]  # [deg]
    assert 60.0 < angle[np.nanargmin(margin)] < 68.0
    access = result.series[f"{pair}.has_access"].data[:, 0]
    assert np.array_equal(result.series[f"{pair}.link_closed"].data[:, 0], access)
