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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np

from . import environment_models, geodesy, tle

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


def _initial_elements(orbit, epoch_utc: Optional[str] = None):
    """(a [m], e, i, raan, argp, mean anomaly) [rad] -- or None if the
    orbit type isn't supported here. A TLE needs ``epoch_utc``."""
    kind = getattr(orbit, "type", None)
    if kind == "tle":
        if epoch_utc is None:
            return None
        state = tle.state_at(orbit.tle_line1, orbit.tle_line2, epoch_utc)
        return _rv_to_elements(state.r_m, state.v_m_s)
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
        try:
            elements = _initial_elements(sc.orbit, scenario.epoch_utc)
        except tle.TLEError:
            elements = None
        if elements is None:
            continue
        r = _positions(elements, t, with_j2)
        for gs in scenario.ground_stations:
            # WGS-84 site and its ellipsoid normal (ECSS-E-ST-10-09C 5.4.6a).
            lat, lon = math.radians(gs.latitude_deg), math.radians(gs.longitude_deg)
            site = geodesy.geodetic_to_pcpf(lat, lon, gs.altitude_m)
            site_radius, site_longitude = math.hypot(site[0], site[1]), math.atan2(site[1], site[0])
            up = np.stack([math.cos(lat) * np.cos(rotation + lon), math.cos(lat) * np.sin(rotation + lon),
                           np.full_like(rotation, math.sin(lat))], 1)
            d = r - np.stack([site_radius * np.cos(rotation + site_longitude),
                              site_radius * np.sin(rotation + site_longitude), np.full_like(rotation, site[2])], 1)
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
    10 min for 8 min (peak 61 deg)". Empty when passes can't be predicted."""
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
        lines.append(f"{gs.name}: {counted}, first at {format_elapsed(first.start_s)} for "
                     f"{format_elapsed(first.end_s - first.start_s)} (peak {first.peak_elevation_deg:.0f} deg)")
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
    for check in (_pass_warnings, _recording_warnings, _tle_warnings, _gravity_warnings,
                  _formation_law_warnings):
        try:
            warnings += check(scenario)
        except Exception:  # noqa: BLE001, S110 -- a half-edited scenario must never break the Explain tab
            pass
    for sc in scenario.spacecraft:
        try:
            warnings += _spacecraft_warnings(sc)
        except Exception:  # noqa: BLE001, S110 -- same reason
            pass
    return warnings


# [-] samples per series over which recording every step is flagged
# (~1.7 MB per simulated day at full recording for one LEO spacecraft)
_MANY_SAMPLES = 1_000_000


_REENTRY_PERIGEE_KM = 120.0  # [km] perigee counted as re-entry, as engine.lifetime
_EARTH_RADIUS_M = geodesy.WGS84_SEMI_MAJOR_AXIS_M  # [m]


def _orbit_warnings(scenario) -> List[str]:
    """Initial orbits that cannot be flown: a perigee below the surface or
    so low the spacecraft re-enters at once, a position inside Earth, a
    state that escapes (Earth only)."""
    if getattr(scenario.gravity, "central_body", "earth") != "earth":
        return []
    warnings = []
    for sc in scenario.spacecraft:
        orbit = sc.orbit
        kind = getattr(orbit, "type", None)
        if kind == "cartesian":
            r = np.array(orbit.position_km, dtype=float) * 1e3  # [m]
            v = np.array(orbit.velocity_km_s, dtype=float) * 1e3  # [m/s]
            if np.linalg.norm(r) < _EARTH_RADIUS_M:
                warnings.append(f"{sc.name}: the position is inside Earth ({np.linalg.norm(r) / 1e3:.0f} km "
                                "from its centre)")
                continue
            energy = 0.5 * float(v @ v) - _MU_M3_S2 / float(np.linalg.norm(r))  # [m^2/s^2]
            if energy >= 0.0:
                warnings.append(f"{sc.name}: position and velocity give an escape trajectory, not an orbit "
                                "(check the units: km and km/s)")
                continue
        elements = _initial_elements(orbit, scenario.epoch_utc)
        if elements is None:
            continue
        perigee_km = (elements[0] * (1.0 - elements[1]) - _EARTH_RADIUS_M) / 1e3  # [km]
        if perigee_km < 0.0:
            warnings.append(f"{sc.name}: perigee is {-perigee_km:.0f} km below Earth's surface")
        elif perigee_km < _REENTRY_PERIGEE_KM:
            warnings.append(f"{sc.name}: perigee at {perigee_km:.0f} km -- it re-enters within about an orbit")
    return warnings


_COVERAGE_CACHE: dict = {}


def _space_weather_coverage(source, local_file_path, msfc_file_path):
    """``spaceweather.data_coverage``, cached per file and modification
    time: it parses the whole file, and this runs on every edit."""
    from . import spaceweather

    paths = [spaceweather.real_data_path(source, local_file_path), msfc_file_path]
    key = (source, local_file_path, msfc_file_path,
           tuple(Path(p).stat().st_mtime_ns if p and Path(p).exists() else None for p in paths))
    if key not in _COVERAGE_CACHE:
        _COVERAGE_CACHE.clear()
        _COVERAGE_CACHE[key] = spaceweather.data_coverage(source, local_file_path, msfc_file_path=msfc_file_path)
    return _COVERAGE_CACHE[key]


def _run_span(scenario):
    start = datetime.fromisoformat(scenario.epoch_utc.replace("Z", "+00:00"))
    if start.tzinfo is not None:
        start = start.astimezone(timezone.utc).replace(tzinfo=None)
    return start, start + timedelta(days=float(scenario.sim_settings.duration_days))


def _data_coverage_warnings(scenario) -> List[str]:
    """A run outside the installed reference data: the space-weather data
    (drag with NRLMSISE-00) and the IERS Earth orientation files."""
    from . import earth_orientation

    start, end = _run_span(scenario)
    warnings = []
    sw = scenario.space_weather
    drag = any(sc.enable_drag for sc in scenario.spacecraft)
    if drag and getattr(sw, "atmosphere_model", "nrlmsise00") == "nrlmsise00":
        try:
            first, last = _space_weather_coverage(sw.source, sw.local_file_path, sw.msfc_file_path)
        except Exception as exc:  # noqa: BLE001 -- a missing or unreadable file is itself the warning
            warnings.append(f"space weather: {exc}")
        else:
            if start.date() < first:
                warnings.append(f"space weather: the data start {first}, after the epoch -- the run is refused")
            elif last is not None and end.date() > last:
                warnings.append(f"space weather: the data end {last}, before the run ends -- the run is refused")
    if getattr(scenario.gravity, "central_body", "earth") == "earth":
        needs_frame = (scenario.gravity.central_body_degree or 0) >= 2 or bool(scenario.ground_stations)
        kernels = earth_orientation.installed()
        if needs_frame and not kernels:
            warnings.append("Earth orientation: no IERS files installed -- the Earth-fixed frame is IAU_EARTH "
                            "(about 160 m/day of error at 400 km); download them from the Data tab")
        for kernel in kernels:
            until = kernel.high_accuracy_until
            if kernel.role == "high_precision" and until is not None and end > until:
                warnings.append(f"Earth orientation: high accuracy until {until:%Y-%m-%d}; the run goes on into "
                                "predicted values (lower accuracy)")
    return warnings


def plausibility_warnings(scenario) -> List[str]:
    """Checks to show while the scenario is edited (UX/UI guidelines,
    "plausibility checks while typing"): initial orbits that cannot be
    flown, and a run outside the installed reference data. Short lines,
    deterministic rules. Never raises."""
    warnings: List[str] = []
    for check in (_orbit_warnings, _data_coverage_warnings):
        try:
            warnings += check(scenario)
        except Exception:  # noqa: BLE001, S110 -- a half-edited scenario must never break the editor
            pass
    return warnings


def _tle_warnings(scenario) -> List[str]:
    """A TLE that can't be propagated, or whose epoch is far from the
    scenario epoch (ECSS-E-ST-10-09C 5.3.1b: the TLE is propagated by SGP4
    to the scenario epoch, so its age is the propagation span)."""
    warnings = []
    for sc in scenario.spacecraft:
        if getattr(sc.orbit, "type", None) != "tle":
            continue
        try:
            age_days = tle.state_at(sc.orbit.tle_line1, sc.orbit.tle_line2, scenario.epoch_utc).age_days
        except tle.TLEError as exc:
            warnings.append(f"{sc.name}: {exc}")
            continue
        if abs(age_days) > tle.TLE_AGE_WARNING_DAYS:
            side = "before" if age_days > 0 else "after"
            warnings.append(f"{sc.name}: TLE epoch is {abs(age_days):.1f} d {side} the scenario epoch -- "
                            "SGP4 accuracy drops with TLE age")
    return warnings


def _gravity_warnings(scenario) -> List[str]:
    """Drag modelled around a point-mass Earth: J2 (~1e-2 m/s^2 in LEO) is
    left out while a far smaller acceleration is modelled."""
    gravity = scenario.gravity
    if getattr(gravity, "central_body", "earth") != "earth" or (gravity.central_body_degree or 0) >= 2:
        return []
    return [f"{sc.name}: drag is modelled but gravity is a point mass -- J2 is far larger; set the gravity "
            "degree to 2 or more" for sc in scenario.spacecraft if sc.enable_drag]


def gravity_fidelity_notes(scenario) -> List[str]:
    """ECSS-E-ST-10-04C 4.2.1b: the gravity field's truncation should leave
    out no more than the non-gravitational accelerations modelled. One line
    when the field leaves out more than SRP (Earth only; Kaula's-rule
    estimate from :mod:`engine.environment_models`). Never raises."""
    try:
        gravity = scenario.gravity
        if getattr(gravity, "central_body", "earth") != "earth":
            return []
        degree = gravity.central_body_degree or 0
        flux = environment_models.solar_flux_w_m2(scenario.epoch_utc)
        short = []
        for sc in scenario.spacecraft:
            if not sc.enable_srp:
                continue
            try:
                elements = _initial_elements(sc.orbit, scenario.epoch_utc)
            except tle.TLEError:
                elements = None
            if elements is None:
                continue
            perigee_m = elements[0] * (1.0 - elements[1])  # [m]
            srp = environment_models.srp_acceleration(sc.srp_coeff, sc.srp_area_m2, sc.dry_mass_kg, flux)
            omitted = environment_models.gravity_truncation_acceleration(degree, perigee_m)
            if omitted > srp:
                short.append((sc.name, omitted, srp, environment_models.degree_for(perigee_m, srp)))
    except Exception:  # noqa: BLE001 -- a half-edited scenario must never break the Explain tab
        return []
    if not short:
        return []
    who = short[0][0] if len(short) == 1 else f"{len(short)} spacecraft"
    return [f"{who}: gravity degree {degree} leaves out ~{max(s[1] for s in short):.0e} m/s^2, more than SRP "
            f"({min(s[2] for s in short):.0e} m/s^2); degree {max(s[3] for s in short)} matches it "
            "(ECSS-E-ST-10-04C 4.2.1b)"]


def _recording_warnings(scenario) -> List[str]:
    """Recording every step of a long run fills memory; passes shorter than
    the recording interval can fall between samples."""
    settings = scenario.sim_settings
    interval_s = settings.record_interval_s  # [s]
    samples = settings.duration_days * 86400.0 / settings.dynamics_task_rate_s
    if interval_s <= 0.0 and samples > _MANY_SAMPLES:
        return [f"every step is recorded: {samples / 1e6:.1f} million samples per series -- set "
                "'Record every' (e.g. 600 s) to save memory"]
    if interval_s <= 0.0 or not scenario.ground_stations:
        return []
    passes = predict_passes(scenario, horizon_s=min(scenario.sim_settings.duration_days * 86400.0, 86400.0))
    if not passes:
        return []
    shortest = min(p.end_s - p.start_s for p in passes)  # [s]
    if shortest > 3.0 * interval_s:
        return []
    return [f"passes last as little as {format_elapsed(shortest)} but results are recorded every "
            f"{format_elapsed(interval_s)} -- some may show coarsely or not at all"]


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


def _formation_law_warnings(scenario) -> List[str]:
    """Hill-frame PD followers (``phasing_keeping.control_law`` "hill_pd")
    whose thruster cannot keep the law below its limit: holding the
    separation (the law's feedforward at the reference point, 3 n^2 x),
    or the PD command K * error at the start. A saturated PD law in orbit
    diverges (engine.formation_control)."""
    warnings: List[str] = []
    by_name = {sc.name: sc for sc in scenario.spacecraft}
    for sc in scenario.spacecraft:
        pk = sc.phasing_keeping
        chief = by_name.get(pk.chief_spacecraft) if pk is not None else None
        if pk is None or pk.control_law != "hill_pd" or chief is None or sc.station_keeping is None:
            continue
        chief_elements = _initial_elements(chief.orbit, scenario.epoch_utc)
        follower_elements = _initial_elements(sc.orbit, scenario.epoch_utc)
        if chief_elements is None or follower_elements is None:
            continue
        a = chief_elements[0]  # [m]
        accel_max = sc.station_keeping.thrust_n / (sc.dry_mass_kg + sc.station_keeping.propellant_kg)  # [m/s^2]
        theta = pk.target_separation_km[0] * 1e3 / a  # [rad]
        reference = np.array([-a * (1.0 - math.cos(theta)), a * math.sin(theta), 0.0])  # [m]
        hold = 3.0 * _MU_M3_S2 / a ** 3 * abs(reference[0])  # [m/s^2]
        if hold > accel_max:
            warnings.append(f"{sc.name}: hill_pd needs {hold:.1e} m/s^2 to hold {pk.target_separation_km[0]:g} km, "
                            f"more than its thruster's {accel_max:.1e} m/s^2 -- use mean_oe or drift_orbit")
            continue
        times = np.array([0.0, 1.0])  # [s] velocity by difference
        rc, rd = _positions(chief_elements, times, False), _positions(follower_elements, times, False)
        x_hat = rc[0] / np.linalg.norm(rc[0])
        z_hat = np.cross(rc[0], rc[1] - rc[0])
        z_hat /= np.linalg.norm(z_hat)
        offset = rd[0] - rc[0]
        rho = np.array([offset @ x_hat, offset @ np.cross(z_hat, x_hat), offset @ z_hat])  # [m] Hill frame
        command = pk.hill_position_gain * float(np.linalg.norm(rho - reference))  # [m/s^2]
        if command > accel_max:
            warnings.append(f"{sc.name}: hill_pd starts {np.linalg.norm(rho - reference) / 1e3:.2f} km off its "
                            f"reference and asks for {command:.1e} m/s^2, more than the thruster's "
                            f"{accel_max:.1e} m/s^2 -- a saturated PD law can diverge")
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
    if sc.facets and not (sc.enable_drag or sc.enable_srp):
        warnings.append(f"{sc.name}: its facets are unused -- they only shape drag and SRP, and both are off")
    sk = sc.station_keeping
    if sk is not None and not sc.enable_drag and sc.phasing_keeping is None:
        warnings.append(f"{sc.name}: with drag off its average altitude barely drifts, so the "
                        f"{sk.deadband_km:g} km deadband may never trip")
    return warnings
