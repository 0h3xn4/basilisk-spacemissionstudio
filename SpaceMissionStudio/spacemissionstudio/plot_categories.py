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

"""Display metadata for every named :class:`engine.results.TimeSeries`
this app is known to produce -- which title/axis label/unit/per-column
names to show it with, and the unit-conversion factor to apply for
DISPLAY only (never for CSV/report export, which always stays in the
series' own raw SI units -- see each call site's own docstring).

Extracted (design-philosophy roadmap item S2, ``docs/ux_roadmap.md``)
out of ``gui/results_widget.py``, which originally defined all of this
itself, so that the new Qt-free, template-driven HTML report generator
(``report.py``) can reuse the EXACT SAME category/unit logic the live
GUI plots use, rather than maintaining a second, separately-evolving
copy of "what does this series mean and what unit should it show in" --
two places computing the same fact that could silently drift out of
sync is exactly the kind of risk this whole design-philosophy audit
exists to catch (``docs/ux_audit.md``). This module itself imports no
Qt/Plotly/Basilisk -- only :class:`engine.results.TimeSeries` -- so
both a GUI widget and a plain CLI report-generation path can depend on
it.

:func:`categorize` is the one public entry point most callers need;
:func:`legacy_display` is its documented fallback for anything
uncategorized. :func:`parse_access_pair` is also exported separately
since ``gui/results_widget.py``'s own access-timeline view (roadmap
item M5) needs the raw ``(station, spacecraft, field)`` tuple, not a
display object.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional

from .engine.results import TimeSeries

_RAD2DEG = 180.0 / math.pi

# "x"/"y"/"z" columns mean the same thing (an inertial-frame or body-frame
# vector component) everywhere they appear in this app's own series
# (position/velocity/body-rate/sun-heading/torque -- see engine.service),
# so every vector-column series below reuses this one label map.
_XYZ_LABELS = {"x": "X", "y": "Y", "z": "Z"}


@dataclass(frozen=True)
class SeriesDisplay:
    """Everything a renderer (a Plotly figure in the GUI, or a report
    table/plot) needs to show one named series descriptively, beyond
    what the bare :class:`TimeSeries` itself already carries -- see
    :func:`categorize`'s own docstring for where these come from.
    ``factor`` multiplies ``series.data`` for display only -- CSV/report
    export never sees it, matching this project's "display choices are
    plot-only" policy. ``standalone_title`` is set for a category
    (access-window/link-margin series) whose own title already names
    every identifying detail -- everything else gets the owning
    spacecraft's name (the series name's own first dotted segment)
    prefixed automatically by the caller. ``wrap_period`` (in display
    units, e.g. 360 for an angle in [0, 360) deg) marks a series that
    wraps around, so a plot breaks its line at each wrap instead of
    drawing a false vertical jump.
    """

    title: str
    y_label: str
    unit: str
    factor: float = 1.0
    columns: Optional[Dict[str, str]] = None
    standalone_title: bool = False
    wrap_period: Optional[float] = None


def _vector_display(name: str) -> Optional[SeriesDisplay]:
    """State-vector and attitude/actuator vector series -- every one of
    these already has ("x","y","z") or equivalent columns in
    ``engine.service``. Position/velocity display in raw meters/m-s (NOT
    km/km-s) per explicit user request ("state vector elements shall be
    displayed in meters for position and m/s for velocity") -- a REVERSAL
    of an earlier blanket km-conversion decision for exactly these two
    series, which real user feedback showed went too far (see
    :func:`legacy_display`). Body rate/torque/etc. are left in
    Basilisk's own native units -- only position/velocity/delta-V/
    altitude/semi-major axis were named in that feedback.
    """
    if name.endswith(".position_N"):
        return SeriesDisplay("Inertial Position (ECI)", "Position", "m", 1.0, dict(_XYZ_LABELS))
    if name.endswith(".velocity_N"):
        return SeriesDisplay("Inertial Velocity (ECI)", "Velocity", "m/s", 1.0, dict(_XYZ_LABELS))
    if name.endswith(".attitude_sigma_BN"):
        return SeriesDisplay("Attitude (MRP, Body to Inertial)", "MRP component", "-")
    if name.endswith(".body_rate_omega_BN_B"):
        return SeriesDisplay("Body Angular Rate", "Angular rate", "rad/s", 1.0, dict(_XYZ_LABELS))
    if name.endswith(".sun_heading_body"):
        return SeriesDisplay("Sun Heading (Body Frame)", "Unit vector component", "-", 1.0, dict(_XYZ_LABELS))
    if name.endswith(".sun_heading_body_estimated"):
        return SeriesDisplay("Sun Heading Estimate (CSS, Body Frame)", "Unit vector component", "-", 1.0,
                              dict(_XYZ_LABELS))
    if name.endswith(".control_torque"):
        return SeriesDisplay("Commanded Control Torque", "Torque", "N*m", 1.0, dict(_XYZ_LABELS))
    if name.endswith(".rw_speeds"):
        return SeriesDisplay("Reaction Wheel Speeds", "Wheel speed", "rad/s")
    if name.endswith(".thruster_on_time"):
        return SeriesDisplay("Thruster On-Times", "Commanded on-time", "s")
    if name.endswith(".fuel_mass_remaining"):
        return SeriesDisplay("Fuel Tank Remaining Mass", "Propellant mass", "kg", 1.0,
                              {"fuel_mass_remaining": "Remaining"})
    if name.endswith(".mtb_dipole_commanded"):
        return SeriesDisplay("Magnetic Torque Rod Commanded Dipole", "Dipole moment", "A*m^2")
    if name.endswith(".battery_charge"):
        return SeriesDisplay("Battery State of Charge", "Charge", "W*hr", 1.0, {"charge": "Charge"})
    if name.endswith(".battery_net_power"):
        return SeriesDisplay("Battery Net Power", "Net power", "W", 1.0, {"net_power": "Net power"})
    if name.endswith(".eclipse.illumination_factor"):
        return SeriesDisplay("Sunlight (Eclipse)", "Fraction of full Sun", "-", 1.0,
                              {"illumination_factor": "Sunlight"})
    return None


def _orbit_element_display(name: str) -> Optional[SeriesDisplay]:
    """The 6 osculating + 6 mean (first-order-J2) Keplerian element
    series ``engine.service._extract_results`` produces --
    ``.orbit_elements.*`` (per-sample ``orbitalMotion.rv2elem``) and
    ``.orbit_elements_mean.*`` (Basilisk's own ``orbitalMotion.clMeanOscMap``,
    osc -> mean, the same analytic J2 short-period-removal its
    ``meanOEFeedback`` FSW module uses).

    Semi-major axis displays in km ("altitudes, semi-major axes shall be
    displayed in km"); the four angles (inclination/RAAN/argument of
    periapsis/true anomaly) display in degrees, matching every angle
    INPUT field this app's own Scenario Editor already uses (e.g.
    ``inclination_deg``) even though ``engine.service`` records them in
    Basilisk's native radians.
    """
    specs = [
        ("semi_major_axis", "Semi-Major Axis", "Semi-major axis", "km", 0.001),
        ("eccentricity", "Eccentricity", "Eccentricity", "-", 1.0),
        ("inclination", "Inclination", "Inclination", "deg", _RAD2DEG),
        ("raan", "RAAN", "RAAN", "deg", _RAD2DEG),
        ("arg_periapsis", "Argument of Periapsis", "Argument of periapsis", "deg", _RAD2DEG),
        ("true_anomaly", "True Anomaly", "True anomaly", "deg", _RAD2DEG),
    ]
    wrapping = ("raan", "arg_periapsis", "true_anomaly")  # [0, 360) deg; inclination stays in [0, 180]
    for field, title_suffix, y_label, unit, factor in specs:
        wrap_period = 360.0 if field in wrapping else None  # [deg]
        if name.endswith(f".orbit_elements.{field}"):
            return SeriesDisplay(f"Osculating {title_suffix}", y_label, unit, factor, wrap_period=wrap_period)
        if name.endswith(f".orbit_elements_mean.{field}"):
            return SeriesDisplay(f"Mean (first-order J2) {title_suffix}", y_label, unit, factor,
                                 wrap_period=wrap_period)
    return None


_CONTROLLER_TITLES = {
    "geo_station_keeping": "GEO Station-Keeping",
    "station_keeping": "Station-Keeping",
    "phasing_keeping": "Phasing-Keeping",
    "constant_thrust": "Constant-Thrust",
}


def _controller_display(name: str) -> Optional[SeriesDisplay]:
    """``"{sc}.<controller>.<field>"`` series from
    ``engine.orbit_maintenance``'s three controllers. ``.delta_v`` is
    handled identically across all three (one shared branch below) and
    ALWAYS displays in raw m/s -- "delta-V shall always be displayed in
    m/s" -- a REVERSAL of an earlier blanket km/s conversion, which real
    user feedback showed was wrong for delta-V specifically even though
    it shares the literal "m/s" unit string with velocity (see
    :func:`legacy_display`).
    """
    for key, label in _CONTROLLER_TITLES.items():
        marker = f".{key}."
        if marker not in name:
            continue
        field = name.rsplit(".", 1)[-1]
        if field == "delta_v":
            return SeriesDisplay(f"{label} Cumulative Delta-V", "Cumulative delta-V", "m/s", 1.0,
                                  {"cumulative_delta_v": "Delta-V"})
        if field == "propellant_remaining":
            return SeriesDisplay(f"{label} Propellant Remaining", "Propellant mass", "kg")
        if field == "altitude":
            return SeriesDisplay(f"{label} Altitude Tracking", "Altitude", "km", 0.001,
                                  {"raw": "Raw", "smoothed": "Smoothed (filtered)"})
        if field == "burn_on":
            return SeriesDisplay(f"{label} Thruster State", "Burn on (1) / off (0)", "-", 1.0,
                                  {"east_west": "East-west", "north_south": "North-south"})
        if field == "longitude":
            return SeriesDisplay(f"{label} Longitude", "East longitude", "deg", _RAD2DEG,
                                  {"raw": "Raw", "smoothed": "One-day fit"})
        if field == "inclination":
            return SeriesDisplay(f"{label} Inclination", "Inclination", "deg", _RAD2DEG)
        if field == "separation_error":
            # Already recorded in degrees (engine.service: units="deg") --
            # factor 1.0, no conversion needed.
            return SeriesDisplay(f"{label} Separation Error", "Angle error", "deg")
        if field == "state":
            return SeriesDisplay(f"{label} Controller State", "State", "-")
        if field == "relative_semi_major_axis":
            return SeriesDisplay(f"{label} Relative Semi-Major Axis (follower - chief)",
                                  "Relative semi-major axis", "m")
        return None
    return None


def _comms_and_thermal_display(name: str) -> Optional[SeriesDisplay]:
    """Template 19's comms-pointing series and the reaction-wheel motor
    thermal model -- both featured in template descriptions, and both
    used to show as raw code names."""
    if name.endswith(".comms_pointing.active_mode"):
        return SeriesDisplay("Pointing Mode (0 Sun, 1 ground station)", "Mode", "-", 1.0,
                              {"active_mode": "Mode"})
    if name.endswith(".comms_pointing.pointing_error_deg"):
        return SeriesDisplay("Pointing Error", "Pointing error", "deg", 1.0,
                              {"pointing_error_deg": "Pointing error"})
    if name.endswith(".motor_temperature") and ".actuator." in name:
        actuator = name[: -len(".motor_temperature")].rsplit(".actuator.", 1)[-1]
        return SeriesDisplay(f"Motor Temperature: {actuator}", "Temperature", "deg C", 1.0,
                              {"temperature": "Temperature"})
    return None


def parse_access_pair(name: str) -> Optional[tuple]:
    """Recovers ``(gs, sc, field)`` from a ``"{gs}.access_to_{sc}.<field>"``
    series name (``engine.service``'s access-analysis loop, plus
    ``engine.link_budget.link_margin_series``) -- the literal
    ``".access_to_"`` separator both producers use -- or ``None`` if
    ``name`` doesn't match that shape. Shared by :func:`_access_pair_display`
    and ``gui.results_widget.ResultsWidget._build_access_timeline_figure``
    (roadmap item M5) so both agree on exactly which series are "an
    access pair series" and how to recover the station/spacecraft names
    from one.
    """
    if ".access_to_" not in name:
        return None
    prefix, _, field = name.rpartition(".")
    gs, sep, sc = prefix.partition(".access_to_")
    if not sep:
        return None
    return gs, sc, field


def _access_pair_display(name: str) -> Optional[SeriesDisplay]:
    """``"{gs}.access_to_{sc}.<field>"`` series -- see
    :func:`parse_access_pair`. Slant range displays in km,
    elevation/azimuth in degrees -- same length/angle display policy as
    everywhere else in this module.
    """
    parsed = parse_access_pair(name)
    if parsed is None:
        return None
    gs, sc, field = parsed
    pair = f"{gs} -> {sc}"
    if field == "has_access":
        return SeriesDisplay(f"Access Window: {pair}", "Has access", "-", 1.0,
                              {"has_access": "Has access"}, standalone_title=True)
    if field == "slant_range":
        return SeriesDisplay(f"Slant Range: {pair}", "Slant range", "km", 0.001, standalone_title=True)
    if field == "elevation":
        return SeriesDisplay(f"Elevation: {pair}", "Elevation angle", "deg", _RAD2DEG, standalone_title=True)
    if field == "azimuth":
        return SeriesDisplay(f"Azimuth: {pair}", "Azimuth angle", "deg", _RAD2DEG, standalone_title=True)
    if field == "link_margin_db":
        return SeriesDisplay(f"Link Margin: {pair}", "Link margin", "dB", 1.0, standalone_title=True)
    return None


def _sensor_display(name: str, series: TimeSeries) -> Optional[SeriesDisplay]:
    """``"{sc}.sensor.{sensor_name}[.accel|.gyro]"`` series -- the sensor
    NAME is user-chosen (``schema.scenario``'s sensor config), so unlike
    every other category here the series name alone can't say which
    sensor TYPE produced it; ``series.columns``/``series.units``
    (already distinct per sensor type in ``engine.service``'s own
    recording code) disambiguate instead.
    """
    if ".sensor." not in name:
        return None
    if name.endswith(".accel"):
        sensor_name = name[: -len(".accel")].rsplit(".sensor.", 1)[-1]
        return SeriesDisplay(f"IMU Accelerometer: {sensor_name}", "Acceleration", series.units, 1.0,
                              dict(_XYZ_LABELS))
    if name.endswith(".gyro"):
        sensor_name = name[: -len(".gyro")].rsplit(".sensor.", 1)[-1]
        return SeriesDisplay(f"IMU Gyroscope: {sensor_name}", "Angular rate", series.units, 1.0,
                              dict(_XYZ_LABELS))
    sensor_name = name.rsplit(".sensor.", 1)[-1]
    if tuple(series.columns) == ("q0", "q1", "q2", "q3"):
        return SeriesDisplay(f"Star Tracker Attitude: {sensor_name}", "Quaternion component", "-")
    if tuple(series.columns) == ("output",):
        return SeriesDisplay(f"Coarse Sun Sensor: {sensor_name}", "Output", "-")
    if series.units == "T":
        return SeriesDisplay(f"Magnetometer: {sensor_name}", "Magnetic field", "T", 1.0, dict(_XYZ_LABELS))
    if tuple(series.columns) == ("temperature",):
        return SeriesDisplay(f"Thermal Sensor: {sensor_name}", "Temperature", "deg C", 1.0,
                              {"temperature": "Temperature"})
    return None


def categorize(name: str, series: TimeSeries) -> Optional[SeriesDisplay]:
    """Display metadata for every series ``engine.service``/
    ``engine.link_budget`` are known to produce -- ``None`` for anything
    else, which :func:`legacy_display` falls back on: raw series name as
    title, ``series.units`` unconverted except the ORIGINAL narrow m/m-s
    -> km/km-s rule this project shipped with before this per-category
    system replaced it. That fallback means an uncategorized/future
    series still renders reasonably -- exactly as it would have before
    this feature existed -- rather than erroring or looking unfinished.
    """
    for fn in (_vector_display, _orbit_element_display, _controller_display, _comms_and_thermal_display,
               _access_pair_display):
        result = fn(name)
        if result is not None:
            return result
    return _sensor_display(name, series)


_LEGACY_UNIT_CONVERSIONS = {"m": ("km", 0.001), "m/s": ("km/s", 0.001)}


def legacy_display(name: str, series: TimeSeries) -> SeriesDisplay:
    display_unit, factor = _LEGACY_UNIT_CONVERSIONS.get(series.units, (series.units, 1.0))
    return SeriesDisplay(title=name, y_label="", unit=display_unit, factor=factor, standalone_title=True)
