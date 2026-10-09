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
"""Re-measure the drag figures published before the geodetic-altitude
correction (SRelD K-01; findings F-07 and F-09).

``HISTORY.md`` quotes drag-dependent results that were measured by hand,
before F-07 (NRLMSISE-00 fed a spherical instead of a geodetic altitude)
and F-09 (parallel runs could read a half-written space-weather file).
This script repeats each of them with the current tool, so the old and
new values can be set side by side. Everything uses the bundled real
space weather (CelesTrak observations, NASA MSFC predictions).

Basilisk runs (each in its own child process, through
``SimulationService.run()``, which splits runs past Basilisk's limit into
segments, as the command line does):

* ``sk2030_p50``: template 18's spacecraft from 2030-01-01 for five
  years, MSFC 50th percentile, Cd 2.2, 5 kg of propellant at Isp 1500 s,
  recorded every 600 s.
* ``sk2030_p95``: the same at the 95th percentile and Cd 3.0 (AD10
  operations).
* ``sk2033_p95``: launched 2033-01-01, 95th percentile, Cd 3.0, a 20 kg
  tank so it never runs dry (the altitude trade's worst launch).
* ``decay300``: template 18's spacecraft from 300 km without station
  keeping, Cd 2.2, against the lifetime estimate.
* ``t05`` and ``t21``: templates 05 and 21 as shipped, for the figures
  their descriptions quote.

Estimates (no Basilisk run): the drag make-up estimate per year for the
three five-year cases, the launch-delay sweep and the altitude trade of
template 18, and the disposal search from 550 km at the end of 2034.

Usage::

    python compliance/tools/remeasure_drag.py [--case NAME ...] [--workers N] [--write]

``--write`` stores the results in ``compliance/drag_remeasure.md`` and
``compliance/drag_remeasure.json``.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import json
import multiprocessing
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT.parent
TEMPLATES = TOOL / "spacemissionstudio" / "scenarios" / "templates"

YEAR_S = 365.25 * 86400.0  # [s]
FIVE_YEARS_DAYS = 5.0 * 365.25  # [day]
SPACECRAFT = "leo-sat-1"

# five-year station-keeping case: (epoch, MSFC percentile [-], Cd [-], propellant [kg])
STATION_KEEPING_CASES = {
    "sk2030_p50": ("2030-01-01T00:00:00", 50.0, 2.2, 5.0),
    "sk2030_p95": ("2030-01-01T00:00:00", 95.0, 3.0, 5.0),
    "sk2033_p95": ("2033-01-01T00:00:00", 95.0, 3.0, 20.0),
}
SK_ISP_S = 1500.0  # [s]
SK_RECORD_S = 600.0  # [s]
DECAY_ALTITUDE_KM = 300.0  # [km]
DECAY_DAYS = 40.0  # [day]
DISPOSAL_ALTITUDE_KM = 550.0  # [km]
DISPOSAL_EOL_UTC = datetime(2035, 1, 1)  # end of a 2030-2035 mission
DISPOSAL_TARGET_YEARS = 5.0  # [year] Zero Debris / FCC rule

# the values HISTORY.md published before F-07 and F-09, for the comparison
PUBLISHED = {
    "sk2030_p50": {"years_m_s": [25.7, 23.0, 39.7, 77.5, 109.1], "total_m_s": 274.9, "burns": 364,
                   "propellant_used_kg": 2.31},
    "sk2030_p95": {"years_m_s": [39.3, 41.7, 121.8, 263.4, 134.4], "total_m_s": 600.5, "burns": 676,
                   "dry_day": 1595.8, "reentry_day": 1633.3},
    "sk2033_p95": {"years_m_s": [230.9, 324.3, 320.8, 275.5, 182.2], "total_m_s": 1333.6, "burns": 1520,
                   "estimate_years_m_s": [223.9, 311.0, 302.0, 255.9, 170.8], "estimate_total_m_s": 1263.7},
    "decay300": {"basilisk_days": 25.43, "estimate_days": 25.66},
    "t05": {"exit_day": 19.9, "return_day": 23.1, "band_km": [48.9, 51.6], "delta_v_m_s": 0.0136},
    "t21": {"rods_off_n_m_s": 2.02, "rods_off_rw_x_rpm": -938.0, "rods_on_max_rpm": 28.2},
    "sweep": {"in_plane_m_s": [815.8, 1125.9, 1377.0, 1450.1, 1306.9, 1026.1],
              "propellant_kg": [8.61, 12.33, 15.53, 16.50, 14.62, 11.10]},
    "trade": {"altitude_km": [350, 400, 450, 500, 550], "in_plane_m_s": [3213, 1450, 690, 342, 175],
              "disposal_m_s": [0, 0, 0, 6.4, 29.7], "propellant_kg": [46.4, 16.5, 7.18, 3.49, 2.02]},
    "disposal": {"perigee_km": 513.0, "delta_v_m_s": 6.8},
}
BASILISK_CASES = (*STATION_KEEPING_CASES, "decay300", "t05", "t21")
ESTIMATE_CASES = ("makeup", "sweep", "trade", "disposal")


def _template(prefix: str):
    from spacemissionstudio.schema import load_scenario

    return load_scenario(next(TEMPLATES.glob(f"{prefix}_*.json")))


def station_keeping_scenario(case: str):
    """Template 18 set up for one five-year case of :data:`STATION_KEEPING_CASES`."""
    epoch, percentile, drag_coeff, propellant_kg = STATION_KEEPING_CASES[case]
    scenario = _template("18")
    scenario.epoch_utc = epoch
    scenario.space_weather.forecast_percentile = percentile
    scenario.sim_settings.duration_days = FIVE_YEARS_DAYS
    scenario.sim_settings.record_interval_s = SK_RECORD_S
    spacecraft = scenario.spacecraft[0]
    spacecraft.drag_coeff = drag_coeff
    spacecraft.station_keeping.propellant_kg = propellant_kg
    spacecraft.station_keeping.isp_s = SK_ISP_S
    return scenario


def decay_scenario():
    """Template 18's spacecraft from 300 km, no station keeping, Cd 2.2
    (as ``tests/test_lifetime.py`` sets it up)."""
    from spacemissionstudio.engine import lifetime

    scenario = _template("18")
    spacecraft = scenario.spacecraft[0]
    spacecraft.orbit.semi_major_axis_km = lifetime.REQ_EARTH_M / 1e3 + DECAY_ALTITUDE_KM  # [km]
    spacecraft.station_keeping = None
    spacecraft.drag_coeff = 2.2  # [-]
    scenario.sim_settings.duration_days = DECAY_DAYS
    scenario.sim_settings.record_interval_s = 300.0  # [s]
    return scenario


def _value_at(series, t_s: float) -> float:
    return float(np.interp(t_s, series.time_s, series.data[:, 0]))


def _burns(cumulative_m_s: np.ndarray) -> int:
    """Number of burns: runs of samples over which the cumulative delta-V grows."""
    growing = np.diff(cumulative_m_s) > 1e-9
    return int(np.count_nonzero(growing[1:] & ~growing[:-1]) + (1 if growing.size and growing[0] else 0))


def _summarise_station_keeping(result) -> dict:
    dv = result.series[f"{SPACECRAFT}.station_keeping.delta_v"]
    propellant = result.series[f"{SPACECRAFT}.station_keeping.propellant_remaining"].data[:, 0]
    altitude = result.series[f"{SPACECRAFT}.station_keeping.altitude"]
    end_s = float(result.series[f"{SPACECRAFT}.position_N"].time_s[-1])
    marks = [k * YEAR_S for k in range(6)]
    cumulative = [_value_at(dv, t) for t in marks]
    held = altitude.data[altitude.time_s > 86400.0, 1] / 1e3  # [km] smoothed, after the first day
    dry = np.flatnonzero(propellant <= 1e-9)
    return {
        "end_day": round(end_s / 86400.0, 1),
        "years_m_s": [round(b - a, 1) for a, b in zip(cumulative[:-1], cumulative[1:])],
        "years_complete": [end_s >= t - 1.0 for t in marks[1:]],
        "total_m_s": round(float(dv.data[-1, 0]), 1),
        "burns": _burns(dv.data[:, 0]),
        "propellant_used_kg": round(float(propellant[0] - propellant[-1]), 2),
        "propellant_left_kg": round(float(propellant[-1]), 2),
        "dry_day": round(float(dv.time_s[dry[0]]) / 86400.0, 1) if dry.size else None,
        "held_km": [round(float(held.min()), 1), round(float(held.max()), 1)] if held.size else None,
        "warnings": [w for w in result.warnings if "re-entered" in w or "dry" in w or "propellant" in w],
    }


def _summarise_decay(result, scenario) -> dict:
    from spacemissionstudio.engine import lifetime

    estimate = lifetime.spacecraft_lifetime(scenario, SPACECRAFT)
    sma = result.series[f"{SPACECRAFT}.orbit_elements_mean.semi_major_axis"]
    ecc = result.series[f"{SPACECRAFT}.orbit_elements_mean.eccentricity"].data[:, 0]
    perigee_km = (sma.data[:, 0] * (1.0 - ecc) - lifetime.REQ_EARTH_M) / 1e3
    with np.errstate(invalid="ignore"):
        below = perigee_km <= lifetime.REENTRY_ALTITUDE_KM
    basilisk_days = float(sma.time_s[np.argmax(below)]) / 86400.0 if below.any() else None
    estimate_days = estimate.lifetime_s / 86400.0 if estimate.reentered else None
    return {"basilisk_days": None if basilisk_days is None else round(basilisk_days, 2),
            "estimate_days": None if estimate_days is None else round(estimate_days, 2),
            "difference_percent": (None if basilisk_days is None or estimate_days is None
                                   else round(100.0 * (estimate_days / basilisk_days - 1.0), 1))}


def _summarise_t05(result, scenario) -> dict:
    follower = next(sc for sc in scenario.spacecraft if sc.phasing_keeping is not None)
    target_km = follower.phasing_keeping.target_separation_km[0]  # [km]
    tolerance = follower.phasing_keeping.tolerance_fraction  # [-]
    chief = result.series[f"{follower.phasing_keeping.chief_spacecraft}.position_N"]
    own = result.series[f"{follower.name}.position_N"]
    separation_km = np.linalg.norm(own.data - chief.data, axis=1) / 1e3  # [km] straight line
    days = own.time_s / 86400.0
    outside = np.abs(separation_km - target_km) > tolerance * target_km
    exit_index = int(np.argmax(outside)) if outside.any() else None
    back_index = None
    if exit_index is not None and (~outside[exit_index:]).any():
        back_index = exit_index + int(np.argmax(~outside[exit_index:]))
    after = separation_km[back_index:] if back_index is not None else np.array([])
    return {"exit_day": None if exit_index is None else round(float(days[exit_index]), 1),
            "return_day": None if back_index is None else round(float(days[back_index]), 1),
            "band_km": [round(float(after.min()), 1), round(float(after.max()), 1)] if after.size else None,
            "delta_v_m_s": round(float(result.series[f"{follower.name}.phasing_keeping.delta_v"].data[-1, 0]), 4)}


def _summarise_t21(result) -> dict:
    wheel_inertia = 12.0 / (6000.0 * np.pi / 30.0)  # [kg*m^2] HR12: 12 N*m*s at 6000 RPM
    off = result.series["rods-off.rw_speeds"].data[-1]  # [rad/s]
    on = result.series["rods-on.rw_speeds"].data[-1]  # [rad/s]
    return {"rods_off_n_m_s": round(float(np.linalg.norm(off) * wheel_inertia), 2),
            "rods_off_rw_x_rpm": round(float(off[0] * 30.0 / np.pi), 0),
            "rods_on_max_rpm": round(float(np.abs(on).max() * 30.0 / np.pi), 1)}


def run_basilisk_case(case: str) -> dict:
    """One Basilisk case, run in this (child) process.

    :param case: a name from :data:`BASILISK_CASES`.
    :return: the case's figures, wall time [s] and peak memory [MiB].
    """
    from spacemissionstudio.engine.service import SimulationService

    if case in STATION_KEEPING_CASES:
        scenario = station_keeping_scenario(case)
    elif case == "decay300":
        scenario = decay_scenario()
    else:
        scenario = _template(case[1:])
    start = time.perf_counter()
    result = SimulationService(copy.deepcopy(scenario)).run()
    wall_s = time.perf_counter() - start
    if case in STATION_KEEPING_CASES:
        figures = _summarise_station_keeping(result)
    elif case == "decay300":
        figures = _summarise_decay(result, scenario)
    elif case == "t05":
        figures = _summarise_t05(result, scenario)
    else:
        figures = _summarise_t21(result)
    figures.update(case=case, wall_min=round(wall_s / 60.0, 1), peak_mib=_peak_mib())
    return figures


def _peak_mib():
    try:
        import resource
    except ImportError:  # Windows
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0), 0)


def makeup_estimates() -> dict:
    """The drag make-up estimate per year for each five-year case."""
    from spacemissionstudio.engine import lifetime

    estimates = {}
    for case, (epoch, percentile, drag_coeff, _kg) in STATION_KEEPING_CASES.items():
        scenario = station_keeping_scenario(case)
        makeup = lifetime.drag_makeup(scenario, scenario.spacecraft[0], datetime.fromisoformat(epoch), 5.0,
                                      forecast_percentile=percentile, drag_coeff=drag_coeff)
        cumulative = [0.0] + [float(np.interp(k * YEAR_S, makeup.time_s, makeup.cumulative_m_s)) for k in range(1, 6)]
        estimates[case] = {"years_m_s": [round(b - a, 1) for a, b in zip(cumulative[:-1], cumulative[1:])],
                           "total_m_s": round(makeup.delta_v_m_s, 1), "years": round(makeup.years, 2)}
    return estimates


def sweep_estimate() -> dict:
    """Template 18's launch-delay sweep (95th percentile, its own Cd 3.0, no run)."""
    from spacemissionstudio.engine import propellant_budget

    sweep = propellant_budget.launch_delay_sweep(_template("18"), SPACECRAFT)
    return {"launch_year": [case.launch_utc.year for case in sweep.cases],
            "in_plane_m_s": [round(case.delta_v_of("Operations", "In-plane"), 1) for case in sweep.cases],
            "propellant_kg": [round(case.budget.total_propellant_kg, 2) for case in sweep.cases],
            "worst_year": sweep.worst.launch_utc.year}


def trade_estimate(workers: int) -> dict:
    """Template 18's altitude trade at its default altitudes."""
    from spacemissionstudio.engine import propellant_budget

    trade = propellant_budget.altitude_trade(_template("18"), SPACECRAFT, workers=workers)
    return {"altitude_km": [round(case.altitude_km) for case in trade.altitudes],
            "inclination_deg": [round(case.inclination_deg, 2) for case in trade.altitudes],
            "worst_year": [case.worst.launch_utc.year for case in trade.altitudes],
            "in_plane_m_s": [round(case.worst.delta_v_of("Operations", "In-plane"), 1) for case in trade.altitudes],
            "disposal_m_s": [round(case.worst.delta_v_of("End of life", ""), 1) for case in trade.altitudes],
            "propellant_kg": [round(case.worst.budget.total_propellant_kg, 2) for case in trade.altitudes],
            "tank_kg": trade.tank_kg,
            "lowest_fitting_km": None if trade.lowest_fitting is None else round(trade.lowest_fitting.altitude_km)}


def disposal_estimate() -> dict:
    """The disposal search from 550 km at the end of a 2030-2035 mission,
    for template 18's spacecraft with its 2 kg of propellant aboard."""
    from spacemissionstudio.engine import propellant_budget

    scenario, _inclination = propellant_budget._at_altitude(_template("18"), SPACECRAFT, DISPOSAL_ALTITUDE_KM)
    spacecraft = scenario.spacecraft[0]
    mass_kg = spacecraft.dry_mass_kg + spacecraft.station_keeping.propellant_kg  # [kg]
    delta_v, perigee_km, years, _notes = propellant_budget.uncontrolled_reentry_delta_v(
        scenario, spacecraft, DISPOSAL_EOL_UTC, mass_kg, DISPOSAL_TARGET_YEARS)
    return {"delta_v_m_s": round(float(delta_v), 1), "perigee_km": round(float(perigee_km), 0),
            "lifetime_years": round(float(years), 2),
            "mass_kg": mass_kg}


def _change(new, old) -> str:
    if new is None or old in (None, 0):
        return "-"
    return f"{100.0 * (new / old - 1.0):+.1f}%"


def report(results: dict, host: dict) -> str:
    """The comparison as Markdown."""
    lines = [f"# Drag figures re-measured after F-07 and F-09 ({date.today().isoformat()})", "",
             "Generated by `compliance/tools/remeasure_drag.py` (SRelD K-01). \"Published\" is the value",
             "`HISTORY.md` gave before the corrections; \"now\" is this run, on the bundled real space",
             "weather (CelesTrak observations, NASA MSFC predictions).", "",
             "| Item | Value |", "|---|---|"]
    lines += [f"| {key} | {value} |" for key, value in host.items()]
    for case in STATION_KEEPING_CASES:
        if case not in results:
            continue
        r, old = results[case], PUBLISHED[case]
        epoch, percentile, drag_coeff, kg = STATION_KEEPING_CASES[case]
        lines += ["", f"## {case}: from {epoch[:10]}, MSFC {percentile:g}th percentile, Cd {drag_coeff:g}, {kg:g} kg", "",
                  "| Delta-V [m/s] | Year 1 | Year 2 | Year 3 | Year 4 | Year 5 | Total |", "|---|---|---|---|---|---|---|",
                  "| Published | " + " | ".join(f"{v:g}" for v in old["years_m_s"]) + f" | {old['total_m_s']:g} |",
                  "| Now | " + " | ".join(f"{v:g}" + ("" if done else "*") for v, done in
                                         zip(r["years_m_s"], r["years_complete"])) + f" | {r['total_m_s']:g} |",
                  "| Change | " + " | ".join(_change(n, o) for n, o in zip(r["years_m_s"], old["years_m_s"]))
                  + f" | {_change(r['total_m_s'], old['total_m_s'])} |"]
        if "makeup" in results:
            est = results["makeup"][case]
            lines += ["| Estimate now | " + " | ".join(f"{v:g}" for v in est["years_m_s"]) + f" | {est['total_m_s']:g} |",
                      "| Estimate against run | " + " | ".join(_change(e, n) for e, n in zip(est["years_m_s"], r["years_m_s"]))
                      + f" | {_change(est['total_m_s'], r['total_m_s'])} |"]
        lines += ["", f"Run: ended day {r['end_day']}, {r['burns']} burns (published {old['burns']}), "
                  f"{r['propellant_used_kg']} kg used, {r['propellant_left_kg']} kg left, tank dry on day "
                  f"{r['dry_day'] if r['dry_day'] is not None else '-'} (published {old.get('dry_day', '-')}); "
                  f"held {r['held_km']} km; {r['wall_min']} min, {r['peak_mib']} MiB peak. * = year cut short."]
        lines += [f"- {w}" for w in r["warnings"]]
    if "decay300" in results:
        r, old = results["decay300"], PUBLISHED["decay300"]
        lines += ["", "## decay300: 300 km, no station keeping, Cd 2.2, from 2030-01-01", "",
                  "| Re-entry [day] | Basilisk | Estimate | Estimate against run |", "|---|---|---|---|",
                  f"| Published | {old['basilisk_days']} | {old['estimate_days']} | {_change(old['estimate_days'], old['basilisk_days'])} |",
                  f"| Now | {r['basilisk_days']} | {r['estimate_days']} | {r['difference_percent']:+.1f}% |"
                  if r["difference_percent"] is not None else f"| Now | {r['basilisk_days']} | {r['estimate_days']} | - |"]
    if "t05" in results:
        r, old = results["t05"], PUBLISHED["t05"]
        lines += ["", "## t05: template 05, follower 50 km ahead", "",
                  "| | Leaves band [day] | Back [day] | Then held [km] | Phasing delta-V [m/s] |", "|---|---|---|---|---|",
                  f"| Published | {old['exit_day']} | {old['return_day']} | {old['band_km']} | {old['delta_v_m_s']} |",
                  f"| Now | {r['exit_day']} | {r['return_day']} | {r['band_km']} | {r['delta_v_m_s']} |"]
    if "t21" in results:
        r, old = results["t21"], PUBLISHED["t21"]
        lines += ["", "## t21: template 21, one day", "",
                  "| | Rods off: stored [N*m*s] | Rods off: rw-x [RPM] | Rods on: largest wheel [RPM] |", "|---|---|---|---|",
                  f"| Published | {old['rods_off_n_m_s']} | {old['rods_off_rw_x_rpm']:g} | {old['rods_on_max_rpm']} |",
                  f"| Now | {r['rods_off_n_m_s']} | {r['rods_off_rw_x_rpm']:g} | {r['rods_on_max_rpm']} |"]
    if "sweep" in results:
        r, old = results["sweep"], PUBLISHED["sweep"]
        lines += ["", "## Launch-delay sweep, template 18 (95th percentile, Cd 3.0, no run)", "",
                  "| Launch | " + " | ".join(str(y) for y in r["launch_year"]) + " |",
                  "|---|" + "---|" * len(r["launch_year"]),
                  "| In-plane, published [m/s] | " + " | ".join(f"{v:g}" for v in old["in_plane_m_s"]) + " |",
                  "| In-plane, now [m/s] | " + " | ".join(f"{v:g}" for v in r["in_plane_m_s"]) + " |",
                  "| Propellant, published [kg] | " + " | ".join(f"{v:g}" for v in old["propellant_kg"]) + " |",
                  "| Propellant, now [kg] | " + " | ".join(f"{v:g}" for v in r["propellant_kg"]) + " |",
                  "", f"Worst launch now: {r['worst_year']}."]
    if "trade" in results:
        r, old = results["trade"], PUBLISHED["trade"]
        lines += ["", "## Altitude trade, template 18 (worst launch per altitude)", "",
                  "| Altitude [km] | " + " | ".join(str(a) for a in r["altitude_km"]) + " |",
                  "|---|" + "---|" * len(r["altitude_km"]),
                  "| Inclination [deg] | " + " | ".join(f"{v:g}" for v in r["inclination_deg"]) + " |",
                  "| Worst launch | " + " | ".join(str(v) for v in r["worst_year"]) + " |",
                  "| In-plane, published [m/s] | " + " | ".join(f"{v:g}" for v in old["in_plane_m_s"]) + " |",
                  "| In-plane, now [m/s] | " + " | ".join(f"{v:g}" for v in r["in_plane_m_s"]) + " |",
                  "| Disposal, published [m/s] | " + " | ".join(f"{v:g}" for v in old["disposal_m_s"]) + " |",
                  "| Disposal, now [m/s] | " + " | ".join(f"{v:g}" for v in r["disposal_m_s"]) + " |",
                  "| Propellant, published [kg] | " + " | ".join(f"{v:g}" for v in old["propellant_kg"]) + " |",
                  "| Propellant, now [kg] | " + " | ".join(f"{v:g}" for v in r["propellant_kg"]) + " |",
                  "", f"Tank {r['tank_kg']} kg; lowest altitude that fits now: {r['lowest_fitting_km'] or 'none'}."]
    if "disposal" in results:
        r, old = results["disposal"], PUBLISHED["disposal"]
        lines += ["", f"## Disposal from {DISPOSAL_ALTITUDE_KM:g} km at {DISPOSAL_EOL_UTC.date()} ({r['mass_kg']:g} kg, "
                  f"{DISPOSAL_TARGET_YEARS:g}-year target)", "",
                  "| | Perigee [km] | Delta-V [m/s] | Lifetime [year] |", "|---|---|---|---|",
                  f"| Published | ~{old['perigee_km']:g} | {old['delta_v_m_s']} | 4.9-5.0 |",
                  f"| Now | {r['perigee_km']:g} | {r['delta_v_m_s']} | {r['lifetime_years']} |"]
    return "\n".join(lines) + "\n"


def machine() -> dict:
    """The PC as this script sees it."""
    import importlib.metadata as metadata
    import platform

    try:
        basilisk = metadata.version("bsk")
    except metadata.PackageNotFoundError:
        basilisk = "not installed"
    return {"os": platform.platform(), "cpus": os.cpu_count(), "python": platform.python_version(),
            "basilisk": basilisk}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", nargs="*", choices=(*BASILISK_CASES, *ESTIMATE_CASES),
                        help="cases to run (default: all)")
    parser.add_argument("--workers", type=int, default=3, help="parallel Basilisk runs (and altitude-trade workers)")
    parser.add_argument("--write", action="store_true", help="store the results in compliance/drag_remeasure.*")
    args = parser.parse_args(argv)
    chosen = args.case or [*BASILISK_CASES, *ESTIMATE_CASES]
    results: dict = {}
    # longest first, so the five-year runs start at once
    basilisk = [case for case in BASILISK_CASES if case in chosen]
    context = multiprocessing.get_context("spawn")
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers, mp_context=context,
                                                max_tasks_per_child=1) as pool:
        futures = {pool.submit(run_basilisk_case, case): case for case in basilisk}
        if "makeup" in chosen:
            results["makeup"] = makeup_estimates()
        if "sweep" in chosen:
            results["sweep"] = sweep_estimate()
        if "disposal" in chosen:
            results["disposal"] = disposal_estimate()
        for future in concurrent.futures.as_completed(futures):
            results[futures[future]] = future.result()
            print(f"done: {futures[future]}", flush=True)
    if "trade" in chosen:
        results["trade"] = trade_estimate(args.workers)
    text = report(results, machine())
    print(text)
    if args.write:
        (ROOT / "drag_remeasure.md").write_text(text, encoding="utf-8")
        (ROOT / "drag_remeasure.json").write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
