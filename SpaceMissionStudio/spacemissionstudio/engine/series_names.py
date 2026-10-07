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

"""The result-series names a scenario will produce, worked out before a run.

Basilisk-free. Used by the mission sequence editor's Report command, which
used to ask the user to type series names from memory (and a wrong name
fails the run). :func:`expected_series_names` mirrors
``engine.service.SimulationService._extract_results`` and the build-time
conditions that decide which recorders exist -- keep the two in sync. A
Basilisk test (``tests/test_series_names.py``) compares this prediction
with a real run's series for every bundled template.
"""

from __future__ import annotations

from typing import List

from ..schema.scenario import Scenario

_ELEMENTS = ("semi_major_axis", "eccentricity", "inclination", "raan", "arg_periapsis", "true_anomaly")


def _spacecraft_series(scenario: Scenario, sc) -> List[str]:
    name = sc.name
    names = [f"{name}.position_N", f"{name}.velocity_N"]
    names += [f"{name}.orbit_elements.{element}" for element in _ELEMENTS]
    gravity = scenario.gravity
    if gravity.central_body == "earth" and gravity.central_body_degree >= 2:
        names += [f"{name}.orbit_elements_mean.{element}" for element in _ELEMENTS]

    if sc.fsw_mode is not None:
        names += [f"{name}.attitude_sigma_BN", f"{name}.body_rate_omega_BN_B", f"{name}.sun_heading_body",
                  f"{name}.control_torque"]
        if sc.fsw_mode == "sunSafePoint" and sc.fsw_params.get("use_css_estimation"):
            names.append(f"{name}.sun_heading_body_estimated")
        wheels = [a for a in sc.actuators if a.kind == "reaction_wheel"]
        thrusters = [a for a in sc.actuators if a.kind == "thruster"]
        if wheels:
            names.append(f"{name}.rw_speeds")
            names += [f"{name}.actuator.{wheel.name}.motor_temperature" for wheel in wheels
                      if "motor_thermal_initial_temp_c" in wheel.params]
            if sc.momentum_dumping is not None:
                names.append(f"{name}.thruster_on_time")
                if sc.fuel_tank is not None:
                    names.append(f"{name}.fuel_mass_remaining")
            if sc.magnetic_momentum_management is not None:
                names.append(f"{name}.mtb_dipole_commanded")
        elif thrusters:
            names.append(f"{name}.thruster_on_time")
            if sc.fuel_tank is not None:
                names.append(f"{name}.fuel_mass_remaining")
    elif sc.comms_pointing is not None:
        names += [f"{name}.attitude_sigma_BN", f"{name}.body_rate_omega_BN_B", f"{name}.sun_heading_body",
                  f"{name}.control_torque"]

    for sensor in sc.sensors:
        series = f"{name}.sensor.{sensor.name}"
        if sensor.kind == "imu":
            names += [f"{series}.accel", f"{series}.gyro"]
        elif sensor.kind in ("star_tracker", "coarse_sun_sensor", "magnetometer", "thermal"):
            names.append(series)

    if sc.power is not None:
        names += [f"{name}.battery_charge", f"{name}.battery_net_power"]
    if sc.station_keeping is not None:
        names += [f"{name}.station_keeping.{part}"
                  for part in ("altitude", "burn_on", "propellant_remaining", "delta_v")]
    if sc.phasing_keeping is not None:
        names += [f"{name}.phasing_keeping.{part}"
                  for part in ("separation_error", "state", "delta_v", "relative_semi_major_axis")]
    if sc.constant_thrust is not None:
        names += [f"{name}.constant_thrust.propellant_remaining", f"{name}.constant_thrust.delta_v"]
    if sc.comms_pointing is not None:
        names += [f"{name}.comms_pointing.active_mode", f"{name}.comms_pointing.pointing_error_deg"]
    return names


def expected_series_names(scenario: Scenario) -> List[str]:
    """Every series name a run of ``scenario`` produces, sorted.

    Never raises on a half-edited scenario: a spacecraft whose settings
    can't be read is skipped rather than failing the whole list.
    """
    names: List[str] = []
    for sc in scenario.spacecraft:
        try:
            names += _spacecraft_series(scenario, sc)
        except (AttributeError, TypeError):
            continue
    for station in scenario.ground_stations:
        for sc in scenario.spacecraft:
            prefix = f"{station.name}.access_to_{sc.name}"
            names += [f"{prefix}.{part}" for part in ("has_access", "slant_range", "elevation", "azimuth")]
            if sc.rf_link is not None:
                names.append(f"{prefix}.link_margin_db")
    return sorted(dict.fromkeys(names))
