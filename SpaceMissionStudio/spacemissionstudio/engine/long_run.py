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

"""Runs longer than one Basilisk simulation can hold.

Basilisk keeps simulated time in integer nanoseconds and converts it to
seconds with ``nanoToSec()``, which returns NaN past 2**53 ns (~104.25
days; ``src/architecture/utilities/macroDefinitions.h``). A longer run is
therefore a chain of segments of at most :data:`SEGMENT_DAYS`, each a fresh
simulation starting where the last one ended:

* epoch moved on by the time already flown;
* each spacecraft's position and velocity (as a Cartesian state), attitude,
  body rate and wheel speeds;
* remaining propellant (station-keeping, GEO station-keeping, constant
  thrust, fuel tank) and battery charge;
* thermal-sensor and wheel-motor temperatures (from their last recorded
  value);
* the data in each instrument's memory partition (``data_handling``);
* each flexible solar array's deflection and its rate.

Results are stitched into one :class:`ResultSet` on one time axis;
cumulative delta-V series, and the generated, downlinked and lost data
counts, carry on from where the previous segment left off. Space weather is resolved once for the whole span, so a run past
the real data's last date is refused before the first segment.

A spacecraft that re-enters ends the run there (see
``SimulationService._execute_until``). Not carried, so restarted at each
boundary: controllers' internal
filters (the station-keeping altitude smoothing refills over one orbit,
the GEO drift fit over one day) and sensor noise sequences. Phasing
keeping (its state machine and schedule), mission sequences, Monte Carlo
batches and the live Vizard view are refused for segmented runs.
"""

from __future__ import annotations

import copy
import math
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

import numpy as np

from ..schema.scenario import OrbitIC, Scenario, SimSettings, SpaceWeatherConfig
from . import time_system
from .results import ResultSet, TimeSeries

SEGMENT_DAYS = 90.0  # [day] safely under Basilisk's ~104.25-day nanoToSec() limit
_RAD_S_TO_RPM = 30.0 / math.pi


class LongRunError(Exception):
    """A scenario this module cannot split into segments."""


def needs_segments(scenario: Scenario) -> bool:
    """True when ``scenario`` is longer than one Basilisk run can hold."""
    return scenario.sim_settings.duration_days > SimSettings._MAX_SINGLE_RUN_DAYS


def segment_lengths_s(scenario: Scenario) -> List[float]:
    """Segment durations [s]: whole dynamics steps of at most SEGMENT_DAYS,
    the last one taking the remainder."""
    step_s = scenario.sim_settings.dynamics_task_rate_s
    full_s = math.floor(SEGMENT_DAYS * 86400.0 / step_s) * step_s  # [s]
    total_s = scenario.sim_settings.duration_days * 86400.0  # [s]
    lengths = []
    while total_s - sum(lengths) > 1e-6:
        lengths.append(min(full_s, total_s - sum(lengths)))
    return lengths


def check_segmentable(scenario: Scenario, vizard_request=None) -> None:
    """Raises :class:`LongRunError` for what cannot be split. Mission
    sequences and phasing keeping are also refused by
    ``Scenario.validate()``; checked again here for scenarios built in code."""
    if scenario.mission_sequence:
        raise LongRunError("a mission sequence runs as one simulation, at most "
                           f"{SimSettings._MAX_SINGLE_RUN_DAYS:g} days -- shorten it, or remove the sequence")
    if any(sc.phasing_keeping is not None for sc in scenario.spacecraft):
        raise LongRunError(f"phasing keeping runs as one simulation, at most {SimSettings._MAX_SINGLE_RUN_DAYS:g} "
                           "days (its correction state and schedule are not carried between segments)")
    if vizard_request is not None:
        raise LongRunError(f"the Vizard view covers one simulation, at most {SimSettings._MAX_SINGLE_RUN_DAYS:g} "
                           "days -- turn Vizard off for longer runs")


def _parse_epoch(epoch_utc: str) -> datetime:
    epoch = datetime.fromisoformat(epoch_utc)
    if epoch.tzinfo is not None:
        epoch = epoch.astimezone(timezone.utc).replace(tzinfo=None)
    return epoch


def _whole_span_space_weather(scenario: Scenario):
    """One resolved file for the whole run (only matters with drag on an
    NRLMSISE atmosphere), handed to every segment as a local file: the
    whole span is checked against the data's dates up front. Returns the
    segments' config and the resolver's warnings (what the data is)."""
    sw_config = scenario.space_weather
    if sw_config.atmosphere_model != "nrlmsise00" or not any(sc.enable_drag for sc in scenario.spacecraft):
        return sw_config, []
    from . import spaceweather

    start = _parse_epoch(scenario.epoch_utc)
    end = start + timedelta(days=scenario.sim_settings.duration_days)
    resolved = spaceweather.resolve_for(sw_config, start, end)
    return SpaceWeatherConfig(source="local_file", local_file_path=str(resolved.path), cache_dir=sw_config.cache_dir,
                              atmosphere_model=sw_config.atmosphere_model), \
        list(resolved.warnings)


def _carry_state(segment: Scenario, service, result: ResultSet) -> Dict[str, float]:
    """Moves each spacecraft in ``segment`` (in place) to where ``service``
    ended. Returns each delta-V series' final value, to offset the next
    segment's."""
    for sc in segment.spacecraft:
        handle = service.spacecraft_handles[sc.name]
        state = handle.sc_object.scStateOutMsg.read()
        sc.orbit = OrbitIC(type="cartesian", position_km=[v / 1e3 for v in state.r_BN_N],
                           velocity_km_s=[v / 1e3 for v in state.v_BN_N])
        sc.sigma_bn_init = [float(v) for v in state.sigma_BN]
        sc.omega_bn_b_init_rad_s = [float(v) for v in state.omega_BN_B]
        if handle.rw_speed_out_msg is not None:
            speeds = handle.rw_speed_out_msg.read().wheelSpeeds  # [rad/s]
            wheels = [a for a in sc.actuators if a.kind == "reaction_wheel"]
            for index, wheel in enumerate(wheels):
                wheel.params["Omega"] = float(speeds[index]) * _RAD_S_TO_RPM  # [RPM]
        if handle.station_keeping_controller is not None:
            sc.station_keeping.propellant_kg = float(handle.station_keeping_controller.propellant)
        if handle.geo_station_keeping_controller is not None:
            sc.geo_station_keeping.propellant_kg = float(handle.geo_station_keeping_controller.propellant)
        if handle.constant_thrust_controller is not None:
            sc.constant_thrust.propellant_kg = float(handle.constant_thrust_controller.propellant)
        if handle.fuel_tank_effector is not None:
            sc.fuel_tank.propellant_mass_kg = float(handle.fuel_tank_effector.fuelTankOutMsg.read().fuelMass)
        if handle.battery_module is not None and sc.power is not None:
            stored_j = float(handle.battery_module.batPowerOutMsg.read().storageLevel)  # [J]
            sc.power.battery_initial_soc = min(1.0, max(0.0, stored_j / (sc.power.battery_capacity_wh * 3600.0)))
        if handle.solar_arrays is not None:
            effectors = [e for e in handle.solar_arrays.effectors if hasattr(e, "hingedRigidBodyOutMsg")]
            for array, effector in zip(sc.solar_arrays, effectors):
                state = effector.hingedRigidBodyOutMsg.read()
                array.initial_deflection_deg = math.degrees(float(state.theta))  # [deg]
                array.initial_rate_deg_s = math.degrees(float(state.thetaDot))  # [deg/s]
        if handle.data_handling is not None:
            from .data_handling import BITS_PER_GBIT, stored_bits_by_instrument

            stored = stored_bits_by_instrument(handle.data_handling.storage, handle.data_handling.instrument_names)
            for instrument in sc.data_handling.instruments:
                instrument.initial_data_gbit = stored[instrument.name] / BITS_PER_GBIT  # [Gbit]
        for sensor in sc.sensors:
            series = result.series.get(f"{sc.name}.sensor.{sensor.name}")
            if sensor.kind == "thermal" and series is not None and len(series.data):
                sensor.params["initial_temp_c"] = float(series.data[-1, 0])  # [C]
        for actuator in sc.actuators:
            series = result.series.get(f"{sc.name}.actuator.{actuator.name}.motor_temperature")
            if series is not None and len(series.data):
                actuator.params["motor_thermal_initial_temp_c"] = float(series.data[-1, 0])  # [C]
    return {name: float(ts.data[-1, 0]) for name, ts in result.series.items()
            if _is_cumulative(name) and len(ts.data)}


_CUMULATIVE_SUFFIXES = (".delta_v", ".data_generated", ".data_downlinked", ".data_lost")


def _is_cumulative(name: str) -> bool:
    """A series that counts up from 0 in each segment and must continue
    from the previous segment's total."""
    return name.endswith(_CUMULATIVE_SUFFIXES)


def _append(merged: Optional[ResultSet], part: ResultSet, offset_s: float,
            dv_offsets: Dict[str, float]) -> ResultSet:
    """``part`` shifted by ``offset_s`` [s] and appended to ``merged``.
    A sample at a segment's t = 0 repeats the previous segment's last one
    and is dropped."""
    if merged is None:
        merged = ResultSet(scenario_name=part.scenario_name, provenance=part.provenance)
    for warning in part.warnings:
        if warning not in merged.warnings:
            merged.warnings.append(warning)
    for name, ts in part.series.items():
        time_s = ts.time_s + offset_s
        data = ts.data + dv_offsets.get(name, 0.0) if _is_cumulative(name) else ts.data
        previous = merged.series.get(name)
        if previous is None:
            merged.series[name] = TimeSeries(name, time_s, ts.columns, data, units=ts.units)
            continue
        if len(time_s) and len(previous.time_s) and abs(time_s[0] - previous.time_s[-1]) < 1e-6:
            time_s, data = time_s[1:], data[1:]
        merged.series[name] = TimeSeries(name, np.concatenate([previous.time_s, time_s]), ts.columns,
                                         np.concatenate([previous.data, data]), units=ts.units)
    return merged


_BASILISK_DEFAULT_SEED = 0x1badcad1  # GaussMarkov's RNGSeed when none is set (gauss_markov.cpp)


def _seed_navigation_errors(scenario: Scenario, segment: Scenario, index: int) -> None:
    """Each segment is a new simulation, so its navigation-error random
    walk starts again from zero; a seed per segment (the scenario's, or
    Basilisk's default, plus the segment number) keeps it from repeating
    the same sequence every segment."""
    for original, copied in zip(scenario.spacecraft, segment.spacecraft):
        if original.navigation_error is not None:
            base = original.navigation_error.seed if original.navigation_error.seed is not None else \
                _BASILISK_DEFAULT_SEED
            copied.navigation_error.seed = (base + index) % 2 ** 32


def run_segmented(scenario: Scenario, on_progress: Optional[Callable[[ResultSet, float], None]] = None,
                  should_cancel: Optional[Callable[[], bool]] = None, vizard_request=None) -> ResultSet:
    """Runs ``scenario`` as a chain of segments (see this module's
    docstring). ``on_progress(partial, fraction)`` and ``should_cancel``
    behave as for :meth:`SimulationService.run_live`, over the whole run."""
    from .service import SimulationCancelled, SimulationService

    check_segmentable(scenario, vizard_request)
    lengths = segment_lengths_s(scenario)
    total_s = sum(lengths)  # [s]
    epoch = _parse_epoch(scenario.epoch_utc)
    segment = copy.deepcopy(scenario)
    segment.space_weather, weather_warnings = _whole_span_space_weather(scenario)
    merged: Optional[ResultSet] = None
    dv_offsets: Dict[str, float] = {}
    offset_s = 0.0  # [s]
    for index, length_s in enumerate(lengths):
        # The simulation counts TDB seconds (engine.time_system): the next
        # segment starts at the UTC of ET(epoch) + offset, not epoch + offset.
        segment.epoch_utc = time_system.elapsed_to_utc(epoch, [offset_s])[0].isoformat()
        segment.sim_settings.duration_days = length_s / 86400.0  # [day]
        _seed_navigation_errors(scenario, segment, index)
        service = SimulationService(segment)
        if on_progress is None and should_cancel is None:
            part = service.run()
        else:
            done_before = offset_s

            def progress(partial, fraction, done_before=done_before, length_s=length_s):
                if on_progress is not None:
                    so_far = _shallow(merged) if merged is not None else None
                    on_progress(_append(so_far, partial, done_before, dv_offsets),
                                (done_before + fraction * length_s) / total_s)

            # Spread ~60 progress callbacks over the WHOLE run, not 60 per segment.
            live_step_s = max(segment.sim_settings.dynamics_task_rate_s, total_s / 60.0)
            try:
                part = service.run_live(progress, live_step_s=live_step_s, should_cancel=should_cancel)
            except SimulationCancelled as exc:
                raise SimulationCancelled(_append(merged, exc.partial_result, offset_s, dv_offsets)) from None
        merged = _append(merged, part, offset_s, dv_offsets)
        if service.reentry is not None:
            name, t_s = service.reentry
            merged.warnings = [w for w in merged.warnings if not w.startswith(f"{name} re-entered")]
            merged.warnings.append(f"{name} re-entered: below 100 km at t = {(offset_s + t_s) / 86400.0:.2f} days "
                                   "-- the run stopped there")
            break
        if index < len(lengths) - 1:
            finals = _carry_state(segment, service, part)
            dv_offsets = {name: dv_offsets.get(name, 0.0) + value for name, value in finals.items()}
        offset_s += length_s
    for warning in weather_warnings:
        if warning not in merged.warnings:
            merged.warnings.insert(0, warning)
    return merged


def _shallow(result: ResultSet) -> ResultSet:
    """A copy whose series dict can be extended without touching ``result``."""
    copied = ResultSet(scenario_name=result.scenario_name, provenance=result.provenance,
                       warnings=list(result.warnings))
    copied.series = dict(result.series)
    return copied
