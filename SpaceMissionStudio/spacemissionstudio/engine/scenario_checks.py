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

"""Quick, Basilisk-free checks of a scenario BEFORE it runs.

* :func:`predict_passes` -- ground-station passes from each spacecraft's
  initial orbit, so a scenario whose stations are never in view says so up
  front. Real user report behind it: template 19 "never" had contact; its
  Sun-synchronous orbit only crossed Berlin's latitude ~8 h into the run.
* :func:`scenario_warnings` -- short warnings for setups that can't do
  what they're configured for (no pass in the run, no sun sensor on the
  Sun-pointing face, a station-keeping deadband with no drag to trip it).

The orbit model is a Keplerian orbit plus J2's secular drift (only when
the gravity model includes J2, matching what the simulation will model);
stations sit on a spherical Earth, as Basilisk's ``groundLocation``
places them; Earth rotates per the IAU_EARTH model SPICE uses (pck00010).
Maneuvers, drag and higher-order gravity are ignored, so predictions are
for the orbit as configured -- typically within a minute over a few hours
in LEO. Everything here must stay fast (the Explain tab calls it on every
edit) and must never raise for a half-edited scenario: unsupported cases
(a non-Earth central body, TLE orbits) return ``None``/no warning.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np

_MU_M3_S2 = 3.986004415e14  # [m^3/s^2] Earth, as Basilisk's simIncludeGravBody uses
_R_EARTH_M = 6378.1366e3  # [m] equatorial radius, as engine.service gives groundLocation
_J2 = 1.0826e-3  # [-]
_TT_MINUS_UTC_S = 69.184  # [s] 32.184 s + 37 leap seconds (constant since 2017)
_STEP_S = 30.0  # [s] sample spacing; a LEO pass above 10 deg lasts several minutes
_MAX_HORIZON_S = 7 * 86400.0  # [s] keep long runs cheap; passes beyond this aren't counted
_LOOKAHEAD_S = 2 * 86400.0  # [s] how far past the run to look for "first pass in ..."


@dataclass
class GroundPass:
    station: str
    spacecraft: str
    start_s: float  # [s] since the scenario epoch
    end_s: float  # [s]
    peak_elevation_deg: float  # [deg]


def _initial_elements(orbit):
    """(a [m], e, i, raan, argp, mean anomaly) [rad] -- or None if the
    orbit type isn't supported here."""
    kind = getattr(orbit, "type", None)
    if kind == "classical_elements":
        a = orbit.semi_major_axis_km * 1e3
        e = orbit.eccentricity or 0.0
        if orbit.anomaly_type == "mean":
            mean_anomaly = math.radians(orbit.mean_anomaly_deg or 0.0)
        else:
            nu = math.radians(orbit.true_anomaly_deg or 0.0)
            ecc_anomaly = 2.0 * math.atan(math.sqrt((1 - e) / (1 + e)) * math.tan(nu / 2.0))
            mean_anomaly = ecc_anomaly - e * math.sin(ecc_anomaly)
        return (a, e, math.radians(orbit.inclination_deg), math.radians(orbit.raan_deg),
                math.radians(orbit.arg_periapsis_deg), mean_anomaly)
    if kind == "cartesian":
        r = np.array(orbit.position_km, dtype=float) * 1e3
        v = np.array(orbit.velocity_km_s, dtype=float) * 1e3
        return _rv_to_elements(r, v)
    return None


def _rv_to_elements(r, v):
    h = np.cross(r, v)
    node = np.cross([0.0, 0.0, 1.0], h)
    rn, vn = np.linalg.norm(r), np.linalg.norm(v)
    e_vec = ((vn ** 2 - _MU_M3_S2 / rn) * r - np.dot(r, v) * v) / _MU_M3_S2
    e = float(np.linalg.norm(e_vec))
    a = 1.0 / (2.0 / rn - vn ** 2 / _MU_M3_S2)
    if e >= 1.0 or a <= 0.0:
        return None
    i = math.acos(max(-1.0, min(1.0, h[2] / np.linalg.norm(h))))
    raan = math.atan2(node[1], node[0]) if np.linalg.norm(node) > 1e-9 else 0.0
    # Argument of latitude u and true anomaly nu; argp = u - nu (works for
    # circular and equatorial orbits, where the separate angles are arbitrary).
    node_hat = np.array([math.cos(raan), math.sin(raan), 0.0])
    u = math.atan2(np.dot(np.cross(node_hat, r), h) / np.linalg.norm(h), np.dot(node_hat, r))
    if e > 1e-9:
        nu = math.atan2(np.dot(np.cross(e_vec, r), h) / np.linalg.norm(h), np.dot(e_vec, r))
    else:
        nu = u
    ecc_anomaly = 2.0 * math.atan(math.sqrt((1 - e) / (1 + e)) * math.tan(nu / 2.0))
    return a, e, i, raan, u - nu, ecc_anomaly - e * math.sin(ecc_anomaly)


def _positions(elements, t, with_j2: bool):
    """Inertial positions [m] at times ``t`` [s], shape (len(t), 3)."""
    a, e, i, raan0, argp0, m0 = elements
    n = math.sqrt(_MU_M3_S2 / a ** 3)  # [rad/s]
    raan_dot = argp_dot = m_dot_extra = 0.0
    if with_j2:
        k = 1.5 * _J2 * (_R_EARTH_M / (a * (1 - e ** 2))) ** 2 * n
        raan_dot = -k * math.cos(i)
        argp_dot = k * (2.0 - 2.5 * math.sin(i) ** 2)
        m_dot_extra = k * math.sqrt(1 - e ** 2) * (1.0 - 1.5 * math.sin(i) ** 2)
    raan = raan0 + raan_dot * t
    argp = argp0 + argp_dot * t
    mean_anomaly = m0 + (n + m_dot_extra) * t
    ecc_anomaly = mean_anomaly.copy() if e < 0.8 else np.full_like(mean_anomaly, math.pi)
    for _ in range(12):  # Newton on Kepler's equation
        ecc_anomaly -= (ecc_anomaly - e * np.sin(ecc_anomaly) - mean_anomaly) / (1 - e * np.cos(ecc_anomaly))
    nu = 2.0 * np.arctan2(math.sqrt(1 + e) * np.sin(ecc_anomaly / 2), math.sqrt(1 - e) * np.cos(ecc_anomaly / 2))
    radius = a * (1 - e * np.cos(ecc_anomaly))
    u = argp + nu
    cos_i, sin_i = math.cos(i), math.sin(i)
    return radius[:, None] * np.stack([
        np.cos(raan) * np.cos(u) - np.sin(raan) * np.sin(u) * cos_i,
        np.sin(raan) * np.cos(u) + np.cos(raan) * np.sin(u) * cos_i,
        np.sin(u) * sin_i,
    ], 1)


def _earth_rotation_angle(epoch_utc: str, t):
    """Angle [rad] of Earth's prime meridian from the inertial x axis
    (IAU_EARTH: the equator's node sits at alpha0 + 90 deg = 90 deg)."""
    epoch = datetime.fromisoformat(epoch_utc)
    if epoch.tzinfo is not None:
        epoch = epoch.astimezone(timezone.utc).replace(tzinfo=None)
    days_tdb = ((epoch - datetime(2000, 1, 1, 12)).total_seconds() + _TT_MINUS_UTC_S) / 86400.0  # [day] from J2000
    return np.radians(90.0 + 190.147 + 360.9856235 * (days_tdb + t / 86400.0))


def predict_passes(scenario, horizon_s: Optional[float] = None) -> Optional[List[GroundPass]]:
    """Passes above each station's minimum elevation, for every
    station/spacecraft pair, from t = 0 to ``horizon_s`` (default: the run,
    capped at a week). ``None`` when this can't be predicted (non-Earth
    central body, or no station/spacecraft)."""
    gravity = scenario.gravity
    if getattr(gravity, "central_body", "earth") != "earth" or not scenario.ground_stations or not scenario.spacecraft:
        return None
    if horizon_s is None:
        horizon_s = scenario.sim_settings.duration_days * 86400.0
    horizon_s = min(max(horizon_s, _STEP_S), _MAX_HORIZON_S + _LOOKAHEAD_S)
    t = np.arange(0.0, horizon_s + _STEP_S, _STEP_S)
    rotation = _earth_rotation_angle(scenario.epoch_utc, t)
    with_j2 = (gravity.central_body_degree or 0) >= 2
    passes: List[GroundPass] = []
    for sc in scenario.spacecraft:
        elements = _initial_elements(sc.orbit)
        if elements is None:
            continue
        r = _positions(elements, t, with_j2)
        for gs in scenario.ground_stations:
            lat, lon = math.radians(gs.latitude_deg), math.radians(gs.longitude_deg)
            up = np.stack([math.cos(lat) * np.cos(rotation + lon), math.cos(lat) * np.sin(rotation + lon),
                           np.full_like(rotation, math.sin(lat))], 1)
            d = r - (_R_EARTH_M + gs.altitude_m) * up
            elevation = np.degrees(np.arcsin(np.sum(d * up, 1) / np.linalg.norm(d, axis=1)))
            visible = np.concatenate([[False], elevation >= gs.min_elevation_deg, [False]])
            edges = np.flatnonzero(np.diff(visible.astype(np.int8)))
            for start, end in zip(edges[0::2], edges[1::2]):
                passes.append(GroundPass(gs.name, sc.name, float(t[start]), float(t[end - 1]),
                                         float(elevation[start:end].max())))
    passes.sort(key=lambda p: p.start_s)
    return passes


def format_elapsed(seconds: float) -> str:
    """Short elapsed-time label: "10 min", "8.2 h", "3.5 d"."""
    if seconds < 120 * 60:
        return f"{seconds / 60:.0f} min"
    if seconds < 48 * 3600:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} d"


def pass_summary(scenario) -> List[str]:
    """One short line per station, e.g. "berlin-gs: 2 passes, first at
    10 min (peak 61 deg)". Empty when passes can't be predicted."""
    passes = predict_passes(scenario)
    if passes is None:
        return []
    run_s = scenario.sim_settings.duration_days * 86400.0
    lines = []
    for gs in scenario.ground_stations:
        mine = [p for p in passes if p.station == gs.name and p.start_s <= run_s]
        if not mine:
            continue
        first = mine[0]
        counted = f"{len(mine)} pass{'es' if len(mine) != 1 else ''}"
        if run_s > _MAX_HORIZON_S:
            counted += " in the first week"
        lines.append(f"{gs.name}: {counted}, first at {format_elapsed(first.start_s)} "
                     f"(peak {first.peak_elevation_deg:.0f} deg)")
    return lines


def _sun_axis(sc):
    """Body axis the spacecraft keeps on the Sun, or None if it doesn't
    Sun-point."""
    if sc.fsw_mode == "sunSafePoint":
        return np.array((sc.fsw_params or {}).get("sHatBdyCmd", [0.0, 0.0, 1.0]), dtype=float)
    if sc.comms_pointing is not None:
        axis = sc.comms_pointing.sun_pointing_axis_b
        if axis is None and sc.power is not None:
            axis = sc.power.panel_normal_b
        return None if axis is None else np.array(axis, dtype=float)
    return None


def scenario_warnings(scenario) -> List[str]:
    """Short warnings for setups that can't do what they're configured
    for. Never raises."""
    warnings: List[str] = []
    try:
        warnings += _pass_warnings(scenario)
    except Exception:  # noqa: BLE001 -- a half-edited scenario must never break the Explain tab
        pass
    for sc in scenario.spacecraft:
        try:
            warnings += _spacecraft_warnings(sc)
        except Exception:  # noqa: BLE001 -- same reason
            pass
    return warnings


def _pass_warnings(scenario) -> List[str]:
    if scenario.mission_sequence:
        return []  # the run's length comes from its commands, not sim_settings
    run_s = scenario.sim_settings.duration_days * 86400.0
    passes = predict_passes(scenario, horizon_s=min(run_s, _MAX_HORIZON_S) + _LOOKAHEAD_S)
    if passes is None:
        return []
    warnings = []
    for gs in scenario.ground_stations:
        mine = [p for p in passes if p.station == gs.name]
        if any(p.start_s <= run_s for p in mine):
            if mine[0].start_s > 0.5 * run_s:
                warnings.append(f"{gs.name}: the first pass only comes at {format_elapsed(mine[0].start_s)} of "
                                f"a {format_elapsed(run_s)} run")
            continue
        if mine:
            warnings.append(f"{gs.name}: no pass in this run -- the first comes at "
                            f"{format_elapsed(mine[0].start_s)}; change the epoch or lengthen the run")
        else:
            warnings.append(f"{gs.name}: no pass in this run or the 2 days after it -- check the orbit "
                            "and the station's minimum elevation")
    return warnings


def _spacecraft_warnings(sc) -> List[str]:
    warnings = []
    axis = _sun_axis(sc)
    css = [s for s in sc.sensors if s.kind == "coarse_sun_sensor"]
    if axis is not None and css and np.linalg.norm(axis) > 0:
        axis = axis / np.linalg.norm(axis)

        def facing(sensor):
            normal = np.array(sensor.params.get("nHat_B", [0.0, 0.0, 0.0]), dtype=float)
            norm = np.linalg.norm(normal)
            return norm > 0 and float(np.dot(normal / norm, axis)) > 0.5

        if not any(facing(s) for s in css):
            warnings.append(f"{sc.name}: no sun sensor faces the Sun-pointing axis, so none sees the Sun "
                            "once pointed")
    sk = sc.station_keeping
    if sk is not None and not sc.enable_drag and sc.phasing_keeping is None:
        warnings.append(f"{sc.name}: with drag off its average altitude barely drifts, so the "
                        f"{sk.deadband_km:g} km deadband may never trip")
    return warnings
