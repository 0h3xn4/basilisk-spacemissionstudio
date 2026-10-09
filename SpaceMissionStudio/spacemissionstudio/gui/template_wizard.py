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

"""A "Customize" dialog for each bundled template
mission (``spacemissionstudio/scenarios/templates/``) -- built in response to
a direct request that a user be able to "recreate the desired scenario
themselves or even tweak some parameters a little bit" from a template,
without first learning the full ``ScenarioEditorWidget`` form (every
field on every spacecraft/sensor/actuator/mission-sequence command).

Deliberately a CURATED subset, not a generic reflection of every
dataclass field: each :class:`TemplateWizardSpec` below exposes only the
handful of parameters that template's own ``description`` already calls
out under "Try changing:" (see ``scripts/_generate_templates.py``), each
with its own plain-language label/help text -- a focused, approachable
flow, not a second copy of the full editor. ``gui/load_scenario_widget.py``
shows one standalone "Customize: <template name>..." button for every
template with a registered spec here; every other template still only
opens straight into the full editor via the existing "Open Template"
button, unchanged.

Every bundled template ('01' through '20') has a registered spec. The
first pass covered three representative ones ('03' GEO station-keeping,
'18' LEO station-keeping, '07' full attitude + hardware + power) to
validate the spec format and the UX before this full rollout -- adding a
template's spec is just another :class:`TemplateWizardSpec` entry in
:data:`_SPECS` below; the wizard machinery itself
(:class:`TemplateCustomizeWizard`) is already generic over any spec.
Not every field is a literal copy of its template's own "Try changing:"
text: a few (e.g. '06'/'11'/'15's initial attitude tip, in place of a
fsw_mode STRING swap; '04's constellation altitude/inclination applied
uniformly across every generated satellite, in place of a
total_satellites/num_planes REGENERATION) were chosen as the closest
SAFE, scalar-field equivalent instead -- each such substitution is
explained in that spec's own ``intro``/comment. Two things no spec here
ever exposes, even when a template's own "Try changing:" mentions them:
``fsw_mode`` (switching it needs a structurally different fsw_params
set, not a spin-box edit) and ``dynamics_task_rate_s`` (several
templates' own comments document a real, confirmed NaN-divergence risk
from setting this too coarse -- see HISTORY.md).

The wizard operates on an in-memory COPY of the template's ``Scenario``
(via ``Scenario.from_dict(scenario.to_dict())``, the same round-trip
``tests/test_scenario_templates.py`` already trusts) -- the original
template file on disk is never touched, matching how "Open Template"
itself already behaves (templates are read-only starting points, saved
elsewhere via File > Save As). ``result_scenario()`` returns that copy
with every page's values applied; the caller (``MainWindow``) is
responsible for validating it and opening it in the full editor (see
``gui/main_window.py``'s ``_on_load_scenario_customized``) -- the exact
same "hand off a Scenario, let the one real editor own validation/save"
split every other GUI-vs-schema boundary in this app already uses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QScrollArea, QVBoxLayout, QWidget,
)

from ..schema.scenario import Scenario, SimSettings
from .theme import PALETTE
from .widgets import PreciseDoubleSpinBox
from .wizard_settings import build_all_settings_pages, setting_paths, get_setting

# SpacecraftConfig.orbit.semi_major_axis_km (OrbitIC, "classical_elements")
# is measured from the central body's CENTER, while
# StationKeepingConfig.target_altitude_km is measured from its surface --
# used below for DISPLAY purposes only (showing an initial altitude in a
# spin box) -- confirmed directly against a real Basilisk build
# (simIncludeGravBody.gravBodyFactory().createEarth().radEquator ==
# 6378136.6 m). Earth-specific; fine for this first pass (every current
# station_keeping/Walker-constellation template is Earth-centered) -- a
# non-Earth central body would need this generalized if a future
# template needs it.
#
# NEVER used to compute a field's WRITE-BACK value (see
# _set_leo_altitude_km's own comment for why: '03'/'18's own
# scripts/_generate_templates.py builders hand-picked a simpler "6378.0"
# round number instead of this precise constant, so recomputing
# semi_major_axis_km from this constant on every accept() -- even with
# zero user edits -- silently drifted it by ~137 m; a real bug, caught by
# this module's own round-trip regression tests).
_EARTH_RADIUS_KM = 6378.1366


@dataclass(frozen=True)
class WizardField:
    """One spin-box on one wizard page. ``get``/``set`` close over
    whichever dataclass field(s) this knob actually represents -- some
    are a single ``SpacecraftConfig`` attribute, others (like '18's
    altitude, above) touch more than one field together so the Scenario
    never passes through an inconsistent intermediate state.
    """

    label: str
    help_text: str
    get: Callable[[Scenario], float]
    set: Callable[[Scenario, float], None]
    minimum: float
    maximum: float
    decimals: int = 3
    step: float = 1.0
    suffix: str = ""
    kind: str = "float"  # "float", "int" (whole number) or "bool" (a checkbox)
    help_inline: bool = True  # show a one-line hint beside the field (help_text is always the tooltip)
    group: str = ""  # sub-heading shown above this field when it differs from the previous field's
    # Consecutive fields with the same vector_key share one row (one box
    # per component, each prefixed by its ``component`` name).
    vector_key: str = ""
    component: str = ""
    # Short inline hint (at most _MAX_HINT_CHARS). Without one, help_text
    # itself is shown when it is that short, otherwise only the tooltip.
    hint: str = ""

    @property
    def inline_hint(self) -> str:
        if not self.help_inline:
            return ""
        if self.hint:
            return self.hint
        return self.help_text if len(self.help_text) <= _MAX_HINT_CHARS else ""


# Real user feedback: two- and three-line help paragraphs in small grey
# type beside each field were "cramped". Inline hints are one short line;
# the full explanation is the field's tooltip.
_MAX_HINT_CHARS = 60


@dataclass(frozen=True)
class WizardPageSpec:
    title: str
    intro: str
    fields: List[WizardField]


@dataclass(frozen=True)
class TemplateWizardSpec:
    template_filename: str
    pages: List[WizardPageSpec]


def _sc(scenario: Scenario):
    """Every current wizard spec is single-spacecraft -- this is the one
    place that assumption lives, so a future multi-spacecraft template's
    spec would only need its own get/set closures, not a change here.
    """
    return scenario.spacecraft[0]


def _rw_max_momentum(scenario: Scenario) -> float:
    return float(_sc(scenario).actuators[0].params["maxMomentum"])


def _set_rw_max_momentum(scenario: Scenario, value: float) -> None:
    # Applied uniformly to every reaction wheel -- '07's own three wheels
    # are built symmetrically (orthogonal spin axes, identical
    # maxMomentum), and keeping them identical here avoids the wizard
    # silently creating an asymmetric wheel set a user never asked for.
    for actuator in _sc(scenario).actuators:
        if actuator.kind == "reaction_wheel":
            actuator.params["maxMomentum"] = value


def _thermal_sensor(scenario: Scenario):
    # Found by kind, not a fixed index -- '20' has 4 sensors (star_tracker/
    # imu/coarse_sun_sensor/thermal, in that order), so sensors[3] would
    # work today but silently break if that order ever changed.
    return next(s for s in _sc(scenario).sensors if s.kind == "thermal")


def _rw_with_motor_thermal(scenario: Scenario):
    # Found by which wheel actually has the motor_thermal_* group set --
    # '20' deliberately configures it on only ONE of its three wheels (see
    # that template's own description), so this must not just be
    # actuators[0].
    return next(a for a in _sc(scenario).actuators
                if a.kind == "reaction_wheel" and "motor_thermal_initial_temp_c" in a.params)


def _leo_altitude_km(scenario: Scenario) -> float:
    return float(_sc(scenario).station_keeping.target_altitude_km)


def _set_leo_altitude_km(scenario: Scenario, value: float) -> None:
    sc = _sc(scenario)
    # Derives the radius offset from this scenario's OWN current
    # (pre-edit) semi_major_axis_km/target_altitude_km, rather than
    # applying _EARTH_RADIUS_KM fresh -- '18's own
    # scripts/_generate_templates.py builder used a simpler "6378.0"
    # round number, not that precise constant, so applying the constant
    # directly here silently drifted semi_major_axis_km by ~137 m on
    # EVERY accept(), even with zero edits (a real bug, caught by this
    # module's own round-trip regression tests). Reading both fields
    # before mutating either preserves whatever offset the template was
    # actually built with, exactly, regardless of which convention it
    # happens to use.
    radius_offset_km = sc.orbit.semi_major_axis_km - sc.station_keeping.target_altitude_km
    sc.station_keeping.target_altitude_km = value
    sc.orbit.semi_major_axis_km = value + radius_offset_km


def _follower(scenario: Scenario):
    """'05's own two-spacecraft template -- the one with phasing_keeping
    (always paired with its own station_keeping -- see
    PhasingKeepingConfig's own docstring) is the one every wizard field
    for this template targets; 'chief-1' has neither.
    """
    return next(sc for sc in scenario.spacecraft if sc.phasing_keeping is not None)


def _walker_altitude_km(scenario: Scenario) -> float:
    return float(scenario.spacecraft[0].orbit.semi_major_axis_km - _EARTH_RADIUS_KM)


def _set_walker_altitude_km(scenario: Scenario, value: float) -> None:
    # Applied uniformly to EVERY generated satellite -- a real Walker
    # constellation shares one altitude/inclination across every plane
    # and satellite by construction (engine.constellation.
    # generate_walker_constellation), only RAAN/mean-anomaly differ
    # between them, so this preserves that shared-altitude invariant
    # rather than making one satellite's orbit inconsistent with the rest.
    for sc in scenario.spacecraft:
        sc.orbit.semi_major_axis_km = value + _EARTH_RADIUS_KM


def _walker_inclination_deg(scenario: Scenario) -> float:
    return float(scenario.spacecraft[0].orbit.inclination_deg)


def _set_walker_inclination_deg(scenario: Scenario, value: float) -> None:
    for sc in scenario.spacecraft:
        sc.orbit.inclination_deg = value


def _thruster_max_thrust(scenario: Scenario) -> float:
    return float(_sc(scenario).actuators[0].params["MaxThrust"])


def _set_thruster_max_thrust(scenario: Scenario, value: float) -> None:
    # Applied uniformly to every thruster -- same "keep a symmetric
    # hardware layout symmetric" reasoning as _set_rw_max_momentum above.
    for actuator in _sc(scenario).actuators:
        if actuator.kind == "thruster":
            actuator.params["MaxThrust"] = value


def _css_fov_deg(scenario: Scenario) -> float:
    return float(_sc(scenario).sensors[0].params["fov_deg"])


def _set_css_fov_deg(scenario: Scenario, value: float) -> None:
    for sensor in _sc(scenario).sensors:
        if sensor.kind == "coarse_sun_sensor":
            sensor.params["fov_deg"] = value


# Matches scripts/_generate_templates.py's own "_RPM_TO_RAD_S = math.pi
# / 30.0" exactly -- name, value, AND operation direction (that script
# always MULTIPLIES by this to go RPM -> rad/s). _wheel_bias_rpm's get()
# below divides by this SAME constant (never a separately-precomputed
# reciprocal, e.g. "30.0 / math.pi") specifically so a true no-op
# round-trip (rpm = rad_s / _RPM_TO_RAD_S; rad_s_back = rpm *
# _RPM_TO_RAD_S) is bit-exact, not just numerically close -- confirmed
# directly: using a separately-precomputed reciprocal instead left a
# ~7e-15 (a few ULP) discrepancy after one round trip, invisible at this
# field's own display precision but caught by this module's own
# byte-for-byte round-trip regression tests (a real bug, now fixed).
_RPM_TO_RAD_S = math.pi / 30.0


def _wheel_bias_rpm(index: int):
    """One of '13's 4 wheel_speed_biases_rad_s entries, exposed in RPM
    (matching the template's own docstring, which always talks about
    "800/600/400/200 RPM", never the underlying rad/s) -- a closure
    factory (not 4 hand-written functions) since all 4 fields share the
    identical get/set shape, differing only by list index.
    """
    def get(scenario: Scenario) -> float:
        return _sc(scenario).magnetic_momentum_management.wheel_speed_biases_rad_s[index] / _RPM_TO_RAD_S

    def set_(scenario: Scenario, value: float) -> None:
        biases = _sc(scenario).magnetic_momentum_management.wheel_speed_biases_rad_s
        biases[index] = value * _RPM_TO_RAD_S

    return get, set_


def _array_facets(scenario: Scenario):
    """'21's solar-array facets (front and back) on BOTH spacecraft: the
    two are copies, so an array change keeps the comparison fair."""
    return [f for sc in scenario.spacecraft for f in sc.facets if f.name.startswith("array")]


def _set_array_offset_y(scenario: Scenario, value: float) -> None:
    for facet in _array_facets(scenario):
        facet.location_b[1] = value


def _set_array_area(scenario: Scenario, value: float) -> None:
    for facet in _array_facets(scenario):
        facet.area_m2 = value


def _set_rod_dipole(scenario: Scenario, value: float) -> None:
    for sc in scenario.spacecraft:
        for actuator in sc.actuators:
            if actuator.kind == "magnetic_torque_rod":
                actuator.params["max_dipole_a_m2"] = value


def _rod_dipole(scenario: Scenario) -> float:
    return float(next(a.params["max_dipole_a_m2"] for sc in scenario.spacecraft for a in sc.actuators
                      if a.kind == "magnetic_torque_rod"))


def _set_geo_slot_longitude(scenario: Scenario, value: float) -> None:
    """Moves '03's slot AND its starting point: a slot change with the
    satellite left behind would read as a huge drift to correct."""
    sc = _sc(scenario)
    shift = value - sc.geo_station_keeping.target_longitude_deg  # [deg]
    sc.geo_station_keeping.target_longitude_deg = value
    sc.orbit.true_anomaly_deg = (sc.orbit.true_anomaly_deg + shift) % 360.0


def _wheel_omega_rpm(index: int):
    """One of '12's 4 reaction wheels' own initial Omega (RPM, matching
    simIncludeRW.py's own units for this parameter directly, unlike '13's
    biases above) -- same closure-factory reasoning as _wheel_bias_rpm.
    """
    def get(scenario: Scenario) -> float:
        return float(_sc(scenario).actuators[index].params.get("Omega", 0.0))

    def set_(scenario: Scenario, value: float) -> None:
        _sc(scenario).actuators[index].params["Omega"] = value

    return get, set_


def _maneuver_command(scenario: Scenario):
    return next(c for c in scenario.mission_sequence if c.kind == "maneuver")


def _coast_command(scenario: Scenario, label_substring: str):
    return next(c for c in scenario.mission_sequence if c.kind == "propagate" and label_substring in (c.label or ""))


def _lambert_command(scenario: Scenario):
    return next(c for c in scenario.mission_sequence if c.kind == "lambert_transfer")


def _lambert_coast_command(scenario: Scenario):
    """The coast to arrival: the first propagate AFTER the transfer burn
    (the template also coasts to the burn point before it)."""
    sequence = scenario.mission_sequence
    after_burn = sequence[sequence.index(_lambert_command(scenario)) + 1:]
    return next(c for c in after_burn if c.kind == "propagate")


def _lambert_target_range_m(scenario: Scenario) -> float:
    return abs(_lambert_command(scenario).params["target_position_m"][0])


def _set_lambert_target_range_m(scenario: Scenario, value: float) -> None:
    # target_position_m is along -X only in this template (see its own
    # build script) -- preserves that direction, only the magnitude
    # (range from the central body's center) is this field's own concern.
    _lambert_command(scenario).params["target_position_m"][0] = -value


def _lambert_tof_s(scenario: Scenario) -> float:
    return float(_lambert_command(scenario).params["time_of_flight_s"])


def _set_lambert_tof_s(scenario: Scenario, value: float) -> None:
    # The coast-to-arrival propagate command's own duration_days must
    # stay in lockstep with time_of_flight_s, or the template's own
    # "after transfer" report would snapshot the state at the WRONG
    # time -- not actually at the arrival point lambert_transfer solved
    # for, silently breaking this template's entire "lands almost
    # exactly at target_position_m" lesson.
    _lambert_command(scenario).params["time_of_flight_s"] = value
    _lambert_coast_command(scenario).params["duration_days"] = value / 86400.0


_SPECS: Dict[str, TemplateWizardSpec] = {
    "03_geo_station_keeping.json": TemplateWizardSpec(
        template_filename="03_geo_station_keeping.json",
        pages=[
            WizardPageSpec(
                title="Slot and boxes",
                intro="Where the satellite is kept, and how tightly.",
                fields=[
                    WizardField(
                        "Target longitude", "The slot's east longitude. The satellite starts there too.",
                        lambda s: _sc(s).geo_station_keeping.target_longitude_deg, _set_geo_slot_longitude,
                        -180.0, 360.0, decimals=2, step=5.0, suffix=" deg",
                        hint="Near 75 E or 255 E (stable points) burns are rare",
                    ),
                    WizardField(
                        "Longitude box", "Half-width of the east-west box around the slot.",
                        lambda s: _sc(s).geo_station_keeping.longitude_deadband_deg,
                        lambda s, v: setattr(_sc(s).geo_station_keeping, "longitude_deadband_deg", v),
                        0.01, 5.0, decimals=3, step=0.01, suffix=" deg",
                        hint="Smaller = more frequent east-west burns",
                    ),
                    WizardField(
                        "Inclination limit", "A north-south burn fires when the inclination passes this.",
                        lambda s: _sc(s).geo_station_keeping.inclination_max_deg,
                        lambda s, v: setattr(_sc(s).geo_station_keeping, "inclination_max_deg", v),
                        0.01, 10.0, decimals=3, step=0.01, suffix=" deg",
                        hint="Smaller = more frequent north-south burns",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Thruster and propellant",
                intro="One chemical thruster set for both kinds of burn.",
                fields=[
                    WizardField(
                        "Thrust", "Each burn's thrust.",
                        lambda s: _sc(s).geo_station_keeping.thrust_n,
                        lambda s, v: setattr(_sc(s).geo_station_keeping, "thrust_n", v),
                        0.01, 100.0, decimals=3, step=0.5, suffix=" N",
                    ),
                    WizardField(
                        "Specific impulse", "Higher uses less propellant for the same delta-V.",
                        lambda s: _sc(s).geo_station_keeping.isp_s,
                        lambda s, v: setattr(_sc(s).geo_station_keeping, "isp_s", v),
                        50.0, 5000.0, decimals=0, step=10.0, suffix=" s", hint="Higher uses less propellant",
                    ),
                    WizardField(
                        "Propellant", "Propellant on board at the start.",
                        lambda s: _sc(s).geo_station_keeping.propellant_kg,
                        lambda s, v: setattr(_sc(s).geo_station_keeping, "propellant_kg", v),
                        0.1, 1000.0, decimals=2, step=5.0, suffix=" kg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro='Longer runs show more correction burns.',
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 3650.0, decimals=2, step=1.0, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "18_leo_station_keeping.json": TemplateWizardSpec(
        template_filename="18_leo_station_keeping.json",
        pages=[
            WizardPageSpec(
                title="Orbit altitude",
                intro='Lower means more drag and more frequent corrections: the biggest setting here.',
                fields=[
                    WizardField(
                        "Altitude", "Target (and starting) altitude above the Earth's surface.",
                        _leo_altitude_km, _set_leo_altitude_km,
                        200.0, 2000.0, decimals=1, step=10.0, suffix=" km",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Spacecraft drag properties",
                intro="How much drag force the satellite's own shape/mass produces.",
                fields=[
                    WizardField(
                        "Drag area", "Cross-sectional area exposed to the atmosphere.",
                        lambda s: _sc(s).drag_area_m2,
                        lambda s, v: setattr(_sc(s), "drag_area_m2", v),
                        0.01, 100.0, decimals=2, step=0.1, suffix=" m^2",
                    ),
                    WizardField(
                        "Drag coefficient", "A dimensionless shape factor -- most satellites fall "
                        "between about 2.0 and 2.5.",
                        lambda s: _sc(s).drag_coeff,
                        lambda s, v: setattr(_sc(s), "drag_coeff", v),
                        1.0, 4.0, decimals=2, step=0.1, hint='Shape factor; most satellites are 2.0 to 2.5',
                    ),
                ],
            ),
            WizardPageSpec(
                title="Station-keeping controller",
                intro="How aggressively the deadband thruster corrects altitude decay.",
                fields=[
                    WizardField(
                        "Deadband", "How far the satellite may decay below target altitude before a "
                        "correction burn starts -- tighter means more frequent, smaller burns.",
                        lambda s: _sc(s).station_keeping.deadband_km,
                        lambda s, v: setattr(_sc(s).station_keeping, "deadband_km", v),
                        0.05, 50.0, decimals=2, step=0.1, suffix=" km",
                        hint="Decay allowed before a burn; smaller = more, smaller burns",
                    ),
                    WizardField(
                        "Thrust", "The station-keeping thruster's thrust magnitude.",
                        lambda s: _sc(s).station_keeping.thrust_n,
                        lambda s, v: setattr(_sc(s).station_keeping, "thrust_n", v),
                        0.001, 10.0, decimals=3, step=0.01, suffix=" N",
                    ),
                    WizardField(
                        "Specific impulse", "Thruster efficiency -- higher uses less propellant per "
                        "unit of delta-V.",
                        lambda s: _sc(s).station_keeping.isp_s,
                        lambda s, v: setattr(_sc(s).station_keeping, "isp_s", v),
                        50.0, 5000.0, decimals=0, step=50.0, suffix=" s", hint='Higher uses less propellant',
                    ),
                    WizardField(
                        "Propellant budget", "Total propellant available for station-keeping over the run.",
                        lambda s: _sc(s).station_keeping.propellant_kg,
                        lambda s, v: setattr(_sc(s).station_keeping, "propellant_kg", v),
                        0.01, 100.0, decimals=2, step=0.1, suffix=" kg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro='Longer runs show more cumulative decay.',
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 365.0, decimals=2, step=1.0, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "07_attitude_pointing_with_adcs_hardware.json": TemplateWizardSpec(
        template_filename="07_attitude_pointing_with_adcs_hardware.json",
        pages=[
            WizardPageSpec(
                title="Reaction wheels",
                intro="Applied to all three (identical, orthogonal-axis) wheels together.",
                fields=[
                    WizardField(
                        "Max momentum", "Each wheel's momentum storage capacity before it saturates "
                        "and needs desaturating.",
                        _rw_max_momentum, _set_rw_max_momentum,
                        1.0, 1000.0, decimals=1, step=10.0, suffix=" N*m*s",
                        hint="Momentum each wheel stores before it saturates",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Power budget",
                intro="The solar array and battery backing this spacecraft's power draw.",
                fields=[
                    WizardField(
                        "Panel area", "Total solar panel area.",
                        lambda s: _sc(s).power.panel_area_m2,
                        lambda s, v: setattr(_sc(s).power, "panel_area_m2", v),
                        0.01, 50.0, decimals=2, step=0.1, suffix=" m^2",
                    ),
                    WizardField(
                        "Battery capacity", "Total energy storage.",
                        lambda s: _sc(s).power.battery_capacity_wh,
                        lambda s, v: setattr(_sc(s).power, "battery_capacity_wh", v),
                        1.0, 10000.0, decimals=1, step=10.0, suffix=" W*hr",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.001, 365.0, decimals=4, step=0.01, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "01_two_body_circular_orbit.json": TemplateWizardSpec(
        template_filename="01_two_body_circular_orbit.json",
        pages=[
            WizardPageSpec(
                title="Orbit",
                intro="The basic two-body orbit this whole template is about.",
                fields=[
                    WizardField(
                        "Semi-major axis", "Higher means a slower, longer-period orbit (Kepler's third law).",
                        lambda s: _sc(s).orbit.semi_major_axis_km,
                        lambda s, v: setattr(_sc(s).orbit, "semi_major_axis_km", v),
                        6500.0, 100000.0, decimals=1, step=100.0, suffix=" km",
                        hint="Higher = slower, longer-period orbit",
                    ),
                    WizardField(
                        "Inclination", "Watch the ground track in Vizard change with this.",
                        lambda s: _sc(s).orbit.inclination_deg,
                        lambda s, v: setattr(_sc(s).orbit, "inclination_deg", v),
                        0.0, 180.0, decimals=2, step=1.0, suffix=" deg",
                    ),
                    WizardField(
                        "Eccentricity", "0 is circular -- see '02' for a non-circular example.",
                        lambda s: _sc(s).orbit.eccentricity,
                        lambda s, v: setattr(_sc(s).orbit, "eccentricity", v),
                        0.0, 0.9, decimals=4, step=0.01, hint='0 is circular',
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.01, 365.0, decimals=2, step=0.5, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "02_elliptical_orbit_with_perturbations.json": TemplateWizardSpec(
        template_filename="02_elliptical_orbit_with_perturbations.json",
        pages=[
            WizardPageSpec(
                title="Orbit",
                intro="The eccentric (GTO-like) orbit J2/third-body precession acts on.",
                fields=[
                    WizardField(
                        "Semi-major axis", "Higher means a slower, longer-period orbit.",
                        lambda s: _sc(s).orbit.semi_major_axis_km,
                        lambda s, v: setattr(_sc(s).orbit, "semi_major_axis_km", v),
                        6500.0, 100000.0, decimals=1, step=500.0, suffix=" km",
                    ),
                    WizardField(
                        "Eccentricity", "How elongated the orbit is -- 0.7 here is a real GTO-like value.",
                        lambda s: _sc(s).orbit.eccentricity,
                        lambda s, v: setattr(_sc(s).orbit, "eccentricity", v),
                        0.0, 0.95, decimals=4, step=0.01, hint='How elongated; 0.7 is GTO-like',
                    ),
                    WizardField(
                        "Inclination", "The orbit plane's tilt from the equator.",
                        lambda s: _sc(s).orbit.inclination_deg,
                        lambda s, v: setattr(_sc(s).orbit, "inclination_deg", v),
                        0.0, 180.0, decimals=2, step=1.0, suffix=" deg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Gravity fidelity",
                intro="How much of Earth's own non-spherical gravity to model.",
                fields=[
                    WizardField(
                        "Spherical-harmonics degree", "0 is the perturbation-free point-mass case "
                        "(compare against this template's own precession lesson); this template ships at 10.",
                        lambda s: float(s.gravity.central_body_degree),
                        lambda s, v: setattr(s.gravity, "central_body_degree", int(round(v))),
                        0.0, 20.0, decimals=0, step=2.0, hint='0 = point mass (no J2); this template uses 10',
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro='Longer runs make the J2 and third-body precession more visible.',
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 30.0, decimals=2, step=0.5, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "04_walker_constellation.json": TemplateWizardSpec(
        template_filename="04_walker_constellation.json",
        pages=[
            WizardPageSpec(
                title="Constellation geometry",
                intro="Applied to every satellite. Change the satellite count with Generate Walker constellation.",
                fields=[
                    WizardField(
                        "Altitude", "Every satellite's shared orbital altitude above Earth's surface.",
                        _walker_altitude_km, _set_walker_altitude_km,
                        # decimals=4, not 1: this field is DERIVED
                        # (semi_major_axis_km minus _EARTH_RADIUS_KM, see
                        # that constant's own comment) -- at decimals=1
                        # the spin box rounds away the sub-meter
                        # remainder from that subtraction, so even an
                        # unedited round-trip silently drifted
                        # semi_major_axis_km by ~0.4 m (a real bug,
                        # caught by this module's own round-trip
                        # regression tests). _EARTH_RADIUS_KM is
                        # Basilisk's own precise earth.radEquator, so at
                        # decimals=4 this template's own 700 km altitude
                        # now displays as a clean "700.0000", not
                        # "700.0004".
                        200.0, 2000.0, decimals=4, step=10.0, suffix=" km",
                        hint="Above the surface, shared by every satellite",
                    ),
                    WizardField(
                        "Inclination", "Every satellite's shared orbit-plane tilt from the equator.",
                        _walker_inclination_deg, _set_walker_inclination_deg,
                        0.0, 180.0, decimals=2, step=1.0, suffix=" deg",
                        hint="Orbit tilt, shared by every satellite",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 30.0, decimals=2, step=0.5, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "05_formation_flying_phasing.json": TemplateWizardSpec(
        template_filename="05_formation_flying_phasing.json",
        pages=[
            WizardPageSpec(
                title="Formation geometry",
                intro='How far ahead of chief-1 the follower holds station, along-track.',
                fields=[
                    WizardField(
                        "Target separation", "The along-track distance follower-1 holds ahead of chief-1. "
                        "Always positive: the follower leads.",
                        lambda s: _follower(s).phasing_keeping.target_separation_km[0],
                        lambda s, v: _follower(s).phasing_keeping.target_separation_km.__setitem__(0, v),
                        1.0, 1000.0, decimals=2, step=5.0, suffix=" km",
                        hint="Distance the follower holds ahead of the chief",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Station-keeping controller",
                intro="follower-1's altitude-holding burns, which phasing needs.",
                fields=[
                    WizardField(
                        "Deadband", "How far 'follower-1' may decay below target altitude before a "
                        "correction burn starts.",
                        lambda s: _follower(s).station_keeping.deadband_km,
                        lambda s, v: setattr(_follower(s).station_keeping, "deadband_km", v),
                        0.05, 50.0, decimals=2, step=0.1, suffix=" km",
                        hint="Decay allowed before a correction burn",
                    ),
                    WizardField(
                        "Thrust", "The station-keeping thruster's thrust magnitude.",
                        lambda s: _follower(s).station_keeping.thrust_n,
                        lambda s, v: setattr(_follower(s).station_keeping, "thrust_n", v),
                        0.001, 10.0, decimals=3, step=0.01, suffix=" N",
                    ),
                    WizardField(
                        "Specific impulse", "Thruster efficiency -- higher uses less propellant per "
                        "unit of delta-V.",
                        lambda s: _follower(s).station_keeping.isp_s,
                        lambda s, v: setattr(_follower(s).station_keeping, "isp_s", v),
                        50.0, 5000.0, decimals=0, step=50.0, suffix=" s", hint='Higher uses less propellant',
                    ),
                    WizardField(
                        "Propellant budget", "Total propellant available, shared between "
                        "station-keeping and phasing burns.",
                        lambda s: _follower(s).station_keeping.propellant_kg,
                        lambda s, v: setattr(_follower(s).station_keeping, "propellant_kg", v),
                        0.01, 100.0, decimals=2, step=0.1, suffix=" kg",
                        hint="Shared by station-keeping and phasing burns",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        # upper bound matches SimSettings._MAX_DURATION_DAYS; past
                        # 100 days the run is split into segments (engine/long_run.py)
                        0.1, SimSettings._MAX_DURATION_DAYS, decimals=2, step=1.0, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "06_attitude_pointing_basic.json": TemplateWizardSpec(
        template_filename="06_attitude_pointing_basic.json",
        pages=[
            WizardPageSpec(
                title="Initial attitude tip",
                intro='The starting error the controller removes.',
                fields=[
                    WizardField(
                        "Sigma X", "MRP attitude-error component (body-to-reference), X axis.",
                        lambda s: _sc(s).sigma_bn_init[0],
                        lambda s, v: _sc(s).sigma_bn_init.__setitem__(0, v),
                        -0.9, 0.9, decimals=3, step=0.05, hint='Starting attitude error (MRP)',
                    ),
                    WizardField(
                        "Sigma Y", "MRP attitude-error component (body-to-reference), Y axis.",
                        lambda s: _sc(s).sigma_bn_init[1],
                        lambda s, v: _sc(s).sigma_bn_init.__setitem__(1, v),
                        -0.9, 0.9, decimals=3, step=0.05, hint='Starting attitude error (MRP)',
                    ),
                    WizardField(
                        "Sigma Z", "MRP attitude-error component (body-to-reference), Z axis.",
                        lambda s: _sc(s).sigma_bn_init[2],
                        lambda s, v: _sc(s).sigma_bn_init.__setitem__(2, v),
                        -0.9, 0.9, decimals=3, step=0.05, hint='Starting attitude error (MRP)',
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro='Kept short on purpose: this template needs a fine time step.',
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.001, 1.0, decimals=4, step=0.01, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "08_mission_sequence_orbit_raise.json": TemplateWizardSpec(
        template_filename="08_mission_sequence_orbit_raise.json",
        pages=[
            WizardPageSpec(
                title="Burn",
                intro='Size of the single prograde burn.',
                fields=[
                    WizardField(
                        "Delta-V (prograde)", "Positive raises the opposite side of the orbit; negative "
                        "(retrograde) lowers it instead.",
                        lambda s: _maneuver_command(s).params["delta_v_m_s"][0],
                        lambda s, v: _maneuver_command(s).params["delta_v_m_s"].__setitem__(0, v),
                        -500.0, 500.0, decimals=2, step=5.0, suffix=" m/s",
                        hint="Positive raises the far side; negative lowers it",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Mission timeline",
                intro="How long each coast segment runs, before and after the burn.",
                fields=[
                    WizardField(
                        "Coast before burn", "How long to propagate before the maneuver command fires.",
                        lambda s: _coast_command(s, "before").params["duration_days"],
                        lambda s, v: _coast_command(s, "before").params.__setitem__("duration_days", v),
                        0.01, 5.0, decimals=3, step=0.05, suffix=" days",
                    ),
                    WizardField(
                        "Coast after burn", "How long to propagate after the maneuver command fires.",
                        lambda s: _coast_command(s, "after").params["duration_days"],
                        lambda s, v: _coast_command(s, "after").params.__setitem__("duration_days", v),
                        0.01, 5.0, decimals=3, step=0.05, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "09_monte_carlo_dispersion_analysis.json": TemplateWizardSpec(
        template_filename="09_monte_carlo_dispersion_analysis.json",
        pages=[
            WizardPageSpec(
                title="Monte Carlo batch",
                intro='Each run draws its own dry mass from this distribution.',
                fields=[
                    WizardField(
                        "Number of runs", "More runs give a smoother distribution of outcomes, at "
                        "proportional runtime cost.",
                        lambda s: float(s.monte_carlo.num_runs),
                        lambda s, v: setattr(s.monte_carlo, "num_runs", int(round(v))),
                        1.0, 1000.0, decimals=0, step=5.0,
                        hint="More runs = smoother statistics, longer runtime",
                    ),
                    WizardField(
                        "Mean mass", "The normal distribution's own mean dry mass.",
                        lambda s: s.monte_carlo.dispersions[0].mean,
                        lambda s, v: setattr(s.monte_carlo.dispersions[0], "mean", v),
                        1.0, 1.0e6, decimals=2, step=10.0, suffix=" kg",
                    ),
                    WizardField(
                        "Std deviation", "A wider spread means more extreme cases appear in the batch.",
                        lambda s: s.monte_carlo.dispersions[0].std_deviation,
                        lambda s, v: setattr(s.monte_carlo.dispersions[0], "std_deviation", v),
                        0.0, 500.0, decimals=2, step=5.0, suffix=" kg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long each of the batch's cases propagates.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time, per case.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 30.0, decimals=2, step=0.5, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "10_gravity_gradient_torque.json": TemplateWizardSpec(
        template_filename="10_gravity_gradient_torque.json",
        pages=[
            WizardPageSpec(
                title="Inertia spread",
                intro='Equal inertias give zero gravity-gradient torque; more spread, stronger effect.',
                fields=[
                    WizardField(
                        "Ixx", "Body-X principal moment of inertia.",
                        lambda s: _sc(s).inertia_kg_m2[0],
                        lambda s, v: _sc(s).inertia_kg_m2.__setitem__(0, v),
                        0.1, 1.0e5, decimals=2, step=1.0, suffix=" kg*m^2",
                    ),
                    WizardField(
                        "Iyy", "Body-Y principal moment of inertia.",
                        lambda s: _sc(s).inertia_kg_m2[4],
                        lambda s, v: _sc(s).inertia_kg_m2.__setitem__(4, v),
                        0.1, 1.0e5, decimals=2, step=1.0, suffix=" kg*m^2",
                    ),
                    WizardField(
                        "Izz", "Body-Z principal moment of inertia.",
                        lambda s: _sc(s).inertia_kg_m2[8],
                        lambda s, v: _sc(s).inertia_kg_m2.__setitem__(8, v),
                        0.1, 1.0e5, decimals=2, step=1.0, suffix=" kg*m^2",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Orbit altitude",
                intro='Gravity-gradient torque falls off as 1/r^3: much stronger in low orbit.',
                fields=[
                    WizardField(
                        "Semi-major axis", "Lower means a stronger gravity-gradient effect.",
                        lambda s: _sc(s).orbit.semi_major_axis_km,
                        lambda s, v: setattr(_sc(s).orbit, "semi_major_axis_km", v),
                        6500.0, 50000.0, decimals=1, step=100.0, suffix=" km",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.1, 10.0, decimals=2, step=0.1, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "11_thruster_attitude_control.json": TemplateWizardSpec(
        template_filename="11_thruster_attitude_control.json",
        pages=[
            WizardPageSpec(
                title="Thruster strength",
                intro='Applied to all 8 thrusters; weaker ones take longer to correct an error.',
                fields=[
                    WizardField(
                        "Max thrust", "Each thruster's own maximum thrust.",
                        _thruster_max_thrust, _set_thruster_max_thrust,
                        0.001, 100.0, decimals=3, step=0.1, suffix=" N",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Initial attitude tip",
                intro='The starting error from the commanded attitude.',
                fields=[
                    WizardField(
                        "Sigma X", "MRP attitude-error component, X axis.",
                        lambda s: _sc(s).sigma_bn_init[0],
                        lambda s, v: _sc(s).sigma_bn_init.__setitem__(0, v),
                        -0.9, 0.9, decimals=3, step=0.05,
                    ),
                    WizardField(
                        "Sigma Y", "MRP attitude-error component, Y axis.",
                        lambda s: _sc(s).sigma_bn_init[1],
                        lambda s, v: _sc(s).sigma_bn_init.__setitem__(1, v),
                        -0.9, 0.9, decimals=3, step=0.05,
                    ),
                    WizardField(
                        "Sigma Z", "MRP attitude-error component, Z axis.",
                        lambda s: _sc(s).sigma_bn_init[2],
                        lambda s, v: _sc(s).sigma_bn_init.__setitem__(2, v),
                        -0.9, 0.9, decimals=3, step=0.05,
                    ),
                ],
            ),
        ],
    ),
    "12_reaction_wheel_momentum_dumping.json": TemplateWizardSpec(
        template_filename="12_reaction_wheel_momentum_dumping.json",
        pages=[
            WizardPageSpec(
                title="Desaturation threshold",
                intro='Desaturation burns fire once total wheel momentum crosses this.',
                fields=[
                    WizardField(
                        "Momentum threshold", "A lower threshold triggers desaturation sooner and more often.",
                        lambda s: _sc(s).momentum_dumping.hs_max,
                        lambda s, v: setattr(_sc(s).momentum_dumping, "hs_max", v),
                        1.0, 1000.0, decimals=1, step=5.0, suffix=" N*m*s",
                        hint="Lower = desaturates sooner and more often",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Initial wheel speeds",
                intro='Speeds close to the wheel limit desaturate almost at once.',
                fields=[
                    WizardField("Wheel 1", "rw-1's initial spin rate.", *_wheel_omega_rpm(0),
                                 0.0, 6000.0, decimals=1, step=100.0, suffix=" RPM"),
                    WizardField("Wheel 2", "rw-2's initial spin rate.", *_wheel_omega_rpm(1),
                                 0.0, 6000.0, decimals=1, step=100.0, suffix=" RPM"),
                    WizardField("Wheel 3", "rw-3's initial spin rate.", *_wheel_omega_rpm(2),
                                 0.0, 6000.0, decimals=1, step=100.0, suffix=" RPM"),
                    WizardField("Wheel 4", "rw-4's initial spin rate.", *_wheel_omega_rpm(3),
                                 0.0, 6000.0, decimals=1, step=100.0, suffix=" RPM"),
                ],
            ),
        ],
    ),
    "13_magnetic_torque_rod_momentum_management.json": TemplateWizardSpec(
        template_filename="13_magnetic_torque_rod_momentum_management.json",
        pages=[
            WizardPageSpec(
                title="Wheel speed targets",
                intro='The speed each wheel is steered toward using the torque rods.',
                fields=[
                    WizardField("Wheel 1 target", "rw-1's target speed.", *_wheel_bias_rpm(0),
                                 0.0, 5000.0, decimals=1, step=50.0, suffix=" RPM"),
                    WizardField("Wheel 2 target", "rw-2's target speed.", *_wheel_bias_rpm(1),
                                 0.0, 5000.0, decimals=1, step=50.0, suffix=" RPM"),
                    WizardField("Wheel 3 target", "rw-3's target speed.", *_wheel_bias_rpm(2),
                                 0.0, 5000.0, decimals=1, step=50.0, suffix=" RPM"),
                    WizardField("Wheel 4 target", "rw-4's target speed.", *_wheel_bias_rpm(3),
                                 0.0, 5000.0, decimals=1, step=50.0, suffix=" RPM"),
                ],
            ),
            WizardPageSpec(
                title="Control gain and orbit",
                intro='How hard the torque rods react, and the field they work with.',
                fields=[
                    WizardField(
                        "Control gain", "A larger gain reacts faster but can overshoot/oscillate.",
                        lambda s: _sc(s).magnetic_momentum_management.c_gain,
                        lambda s, v: setattr(_sc(s).magnetic_momentum_management, "c_gain", v),
                        0.0001, 1.0, decimals=5, step=0.0005,
                    ),
                    WizardField(
                        "Orbit inclination", "A near-equatorial orbit sees a weaker, less "
                        "favorably-oriented geomagnetic field than a higher-inclination one.",
                        lambda s: _sc(s).orbit.inclination_deg,
                        lambda s, v: setattr(_sc(s).orbit, "inclination_deg", v),
                        0.0, 180.0, decimals=2, step=5.0, suffix=" deg",
                        hint="Higher gives the torque rods a better field to use",
                    ),
                ],
            ),
        ],
    ),
    "14_css_sun_heading_estimation.json": TemplateWizardSpec(
        template_filename="14_css_sun_heading_estimation.json",
        pages=[
            WizardPageSpec(
                title="Sensor field of view",
                intro='Applied to all 8 sun sensors; narrower means fewer lit, a poorer estimate.',
                fields=[
                    WizardField(
                        "Field of view", "Each sensor's own half-cone field of view.",
                        _css_fov_deg, _set_css_fov_deg,
                        10.0, 180.0, decimals=1, step=5.0, suffix=" deg",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro="How long to propagate.",
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.001, 10.0, decimals=4, step=0.01, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "15_celestial_body_pointing.json": TemplateWizardSpec(
        template_filename="15_celestial_body_pointing.json",
        pages=[
            WizardPageSpec(
                title="Target pointing axis",
                intro='The body axis kept pointed at the Moon.',
                fields=[
                    WizardField(
                        "pHat X", "Pointing-axis component, body X.",
                        lambda s: _sc(s).fsw_params["pHat_B"][0],
                        lambda s, v: _sc(s).fsw_params["pHat_B"].__setitem__(0, v),
                        -1.0, 1.0, decimals=3, step=0.1,
                    ),
                    WizardField(
                        "pHat Y", "Pointing-axis component, body Y.",
                        lambda s: _sc(s).fsw_params["pHat_B"][1],
                        lambda s, v: _sc(s).fsw_params["pHat_B"].__setitem__(1, v),
                        -1.0, 1.0, decimals=3, step=0.1,
                    ),
                    WizardField(
                        "pHat Z", "Pointing-axis component, body Z.",
                        lambda s: _sc(s).fsw_params["pHat_B"][2],
                        lambda s, v: _sc(s).fsw_params["pHat_B"].__setitem__(2, v),
                        -1.0, 1.0, decimals=3, step=0.1,
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro='Kept short on purpose: this template needs a fine time step.',
                fields=[
                    WizardField(
                        "Duration", "Total simulated time.",
                        lambda s: s.sim_settings.duration_days,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v),
                        0.001, 1.0, decimals=4, step=0.01, suffix=" days",
                    ),
                ],
            ),
        ],
    ),
    "16_lambert_transfer.json": TemplateWizardSpec(
        template_filename="16_lambert_transfer.json",
        pages=[
            WizardPageSpec(
                title="Transfer target",
                intro='Where and when the transfer arrives; the coast after it follows automatically.',
                fields=[
                    WizardField(
                        "Coast to burn point", "How long to coast before the transfer burn.",
                        lambda s: _coast_command(s, "burn point").params["duration_days"] * 86400.0,
                        lambda s, v: _coast_command(s, "burn point").params.__setitem__("duration_days",
                                                                                         v / 86400.0),
                        10.0, 100000.0, decimals=1, step=10.0, suffix=" s",
                        hint="Where on the orbit the burn happens",
                    ),
                    WizardField(
                        "Target range", "Distance from the central body's center (along the same "
                        "-X direction this template already targets).",
                        _lambert_target_range_m, _set_lambert_target_range_m,
                        1.0e5, 1.0e8, decimals=0, step=1000.0, suffix=" m",
                        hint="Distance from the central body's centre",
                    ),
                    WizardField(
                        "Time of flight", "Very short times need very large (often rejected) delta-Vs.",
                        _lambert_tof_s, _set_lambert_tof_s,
                        10.0, 100000.0, decimals=1, step=10.0, suffix=" s",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Transfer constraints",
                intro='Checks a solved transfer must pass.',
                fields=[
                    WizardField(
                        "Max distance from target", "Reject a solution whose arrival misses the target "
                        "position by more than this.",
                        lambda s: _lambert_command(s).params["max_distance_target_m"],
                        lambda s, v: _lambert_command(s).params.__setitem__("max_distance_target_m", v),
                        1.0, 1.0e6, decimals=1, step=10.0, suffix=" m",
                        hint="Reject a solution that misses the target by more",
                    ),
                    WizardField(
                        "Min orbit radius", "Reject any transfer trajectory that would dip below this "
                        "radius (e.g. through the central body's own surface).",
                        lambda s: _lambert_command(s).params["min_orbit_radius_m"],
                        lambda s, v: _lambert_command(s).params.__setitem__("min_orbit_radius_m", v),
                        1.0e5, 1.0e8, decimals=0, step=1000.0, suffix=" m",
                        hint="Reject transfers that dip below this radius",
                    ),
                ],
            ),
        ],
    ),
    "17_fuel_tank_depletion.json": TemplateWizardSpec(
        template_filename="17_fuel_tank_depletion.json",
        pages=[
            WizardPageSpec(
                title="Fuel tank",
                intro='Start below about 0.185 kg of propellant to see the tank run dry mid-burn.',
                fields=[
                    WizardField(
                        "Initial propellant", "How much propellant the tank starts with.",
                        lambda s: _sc(s).fuel_tank.propellant_mass_kg,
                        lambda s, v: setattr(_sc(s).fuel_tank, "propellant_mass_kg", v),
                        0.001, 100.0, decimals=3, step=0.05, suffix=" kg",
                    ),
                    WizardField(
                        "Tank capacity", "The tank's own maximum propellant mass.",
                        lambda s: _sc(s).fuel_tank.max_propellant_mass_kg,
                        lambda s, v: setattr(_sc(s).fuel_tank, "max_propellant_mass_kg", v),
                        0.001, 100.0, decimals=3, step=0.05, suffix=" kg",
                    ),
                ],
            ),
        ],
    ),
    "19_sun_pointing_comms_link.json": TemplateWizardSpec(
        template_filename="19_sun_pointing_comms_link.json",
        pages=[
            WizardPageSpec(
                title="Ground-station pass geometry",
                intro='How easily the spacecraft gets and keeps a link with berlin-gs.',
                fields=[
                    WizardField(
                        "Minimum elevation", "The lowest elevation angle (above the local horizon) "
                        "counted as real access -- lower means longer, more frequent, but lower "
                        "-quality passes.",
                        lambda s: s.ground_stations[0].min_elevation_deg,
                        lambda s, v: setattr(s.ground_stations[0], "min_elevation_deg", v),
                        0.0, 89.0, decimals=1, step=5.0, suffix=" deg",
                        hint="Lowest elevation counted as a pass",
                    ),
                ],
            ),
            WizardPageSpec(
                title="RF link / antenna pointing",
                intro='How much pointing error during mode switches costs in link margin.',
                fields=[
                    WizardField(
                        "Antenna beamwidth", "The downlink antenna's half-power beamwidth -- "
                        "narrower means a pointing error costs MORE link margin.",
                        lambda s: _sc(s).rf_link.antenna_beamwidth_deg,
                        lambda s, v: setattr(_sc(s).rf_link, "antenna_beamwidth_deg", v),
                        1.0, 180.0, decimals=1, step=5.0, suffix=" deg",
                        hint="Narrower = pointing errors cost more margin",
                    ),
                    WizardField(
                        "Comms transmitter power", "Extra electrical power the downlink "
                        "transmitter draws from the battery, only while actually "
                        "ground-station-pointing.",
                        lambda s: _sc(s).comms_pointing.comms_power_w,
                        lambda s, v: setattr(_sc(s).comms_pointing, "comms_power_w", v),
                        0.0, 200.0, decimals=1, step=5.0, suffix=" W",
                        hint="Extra draw while pointing at the station",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Simulation length",
                intro='Longer runs show more passes but record more data.',
                fields=[
                    WizardField(
                        "Duration", "Total simulated time. Berlin's next passes come about 13 h after the first two.",
                        lambda s: s.sim_settings.duration_days * 24.0,
                        lambda s, v: setattr(s.sim_settings, "duration_days", v / 24.0),
                        0.5, 336.0, decimals=2, step=0.25, suffix=" h",
                        hint="Next Berlin passes come about 13 h later",
                    ),
                ],
            ),
        ],
    ),
    "20_thermal_simulation.json": TemplateWizardSpec(
        template_filename="20_thermal_simulation.json",
        pages=[
            WizardPageSpec(
                title="Thermal sensor",
                intro="therm-1: an outside component's temperature through sunlight and eclipse.",
                fields=[
                    WizardField(
                        "Surface area", "Larger means more solar absorption AND more radiative "
                        "emission -- both scale together.",
                        lambda s: _thermal_sensor(s).params["area_m2"],
                        lambda s, v: _thermal_sensor(s).params.__setitem__("area_m2", v),
                        0.001, 10.0, decimals=3, step=0.01, suffix=" m^2",
                        hint="More solar heating and more radiative cooling",
                    ),
                    WizardField(
                        "Mass", "Combined with specific heat below, this is the sensor's thermal "
                        "mass -- larger means a slower, smoother response to each sunlight/eclipse "
                        "transition.",
                        lambda s: _thermal_sensor(s).params["mass_kg"],
                        lambda s, v: _thermal_sensor(s).params.__setitem__("mass_kg", v),
                        0.01, 50.0, decimals=2, step=0.1, suffix=" kg",
                        hint="With specific heat, the thermal mass: larger = slower",
                    ),
                    WizardField(
                        "Internal power draw", "Electrical power dissipated as heat inside the "
                        "sensor itself -- adds a constant heating term on top of the solar one.",
                        lambda s: _thermal_sensor(s).params["power_draw_w"],
                        lambda s, v: _thermal_sensor(s).params.__setitem__("power_draw_w", v),
                        0.0, 50.0, decimals=2, step=0.5, suffix=" W", hint='Heat generated inside the sensor',
                    ),
                ],
            ),
            WizardPageSpec(
                title="Reaction wheel motor thermal",
                intro="rw-1's motor heating from spin losses, separate from the sensor.",
                fields=[
                    WizardField(
                        "Motor efficiency", "Closer to 1.0 means less waste heat and a flatter "
                        "temperature curve -- 1.0 itself is rejected (modeled as a real "
                        "inefficiency).",
                        lambda s: _rw_with_motor_thermal(s).params["motor_thermal_efficiency"],
                        lambda s, v: _rw_with_motor_thermal(s).params.__setitem__(
                            "motor_thermal_efficiency", v),
                        0.01, 0.99, decimals=2, step=0.05,
                        hint="Closer to 1 = less waste heat (1.0 not allowed)",
                    ),
                    WizardField(
                        "Ambient thermal resistance", "Lower means heat dissipates to the "
                        "surroundings faster -- the motor temperature settles closer to ambient.",
                        lambda s: _rw_with_motor_thermal(s).params["motor_thermal_ambient_resistance_w_c"],
                        lambda s, v: _rw_with_motor_thermal(s).params.__setitem__(
                            "motor_thermal_ambient_resistance_w_c", v),
                        0.1, 100.0, decimals=2, step=0.5, suffix=" C/W",
                        hint="Lower = settles closer to ambient",
                    ),
                ],
            ),
        ],
    ),
    "21_disturbance_torques.json": TemplateWizardSpec(
        template_filename="21_disturbance_torques.json",
        pages=[
            WizardPageSpec(
                title="Solar array",
                intro="Applied to both spacecraft, so they stay identical apart from the rods.",
                fields=[
                    WizardField(
                        "Array offset (body y)", "How far the array's centre of pressure sits to one side "
                        "of the centre of mass. 0 removes the solar-pressure torque.",
                        lambda s: _array_facets(s)[0].location_b[1], _set_array_offset_y,
                        -10.0, 10.0, decimals=2, step=0.25, suffix=" m",
                        hint="0 = no torque from the array",
                    ),
                    WizardField(
                        "Array area", "Area of the array's front (and back) facet.",
                        lambda s: _array_facets(s)[0].area_m2, _set_array_area,
                        0.1, 50.0, decimals=2, step=0.5, suffix=" m^2",
                        hint="Torque grows with area",
                    ),
                ],
            ),
            WizardPageSpec(
                title="Torque rods",
                intro="rods-on's three torque rods.",
                fields=[
                    WizardField(
                        "Rod strength", "Each rod's largest magnetic dipole.",
                        _rod_dipole, _set_rod_dipole,
                        0.5, 500.0, decimals=1, step=5.0, suffix=" A*m^2",
                        hint="Weaker rods let more momentum build up",
                    ),
                ],
            ),
        ],
    ),
}


def get_wizard_spec(template_filename: str) -> Optional[TemplateWizardSpec]:
    """``None`` means this template has no curated wizard yet -- callers
    (``LoadScenarioWidget``) fall back to the plain "Open Template" flow,
    exactly as they did before this feature existed.
    """
    return _SPECS.get(template_filename)


class _WizardFieldPage(QFrame):
    """One section's fields (a curated page, or a generated one), drawn
    as a compact card on the dialog's single scrolling page."""

    def __init__(self, page_spec: WizardPageSpec, scenario: Scenario, parent=None, heading_text: str = ""):
        super().__init__(parent)
        self.setObjectName("wizardSection")
        self.setStyleSheet(f"QFrame#wizardSection {{ background: {PALETTE['surface']}; "
                           f"border: 1px solid {PALETTE['border']}; border-radius: 0px; }}")  # Carbon tile
        self._title = page_spec.title
        self._scenario = scenario
        self._fields = page_spec.fields
        self._boxes: list = []
        self._initial: list = []
        self._rows: list = []  # (field row index, help row index or None) per field
        self._group_rows: list = []  # (heading row index, group name)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(4)
        heading = QLabel(heading_text or page_spec.title)
        heading.setStyleSheet("font-weight: 600; font-size: 110%; border: none;")
        outer.addWidget(heading)
        if page_spec.intro:
            intro = QLabel(page_spec.intro)
            intro.setWordWrap(True)
            intro.setStyleSheet(f"color: {PALETTE['text_muted']}; border: none;")
            outer.addWidget(intro)
        self._form = QFormLayout()
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._form.setHorizontalSpacing(16)
        # A row too wide for the dialog puts its field under the label instead of
        # forcing sideways scrolling (large fonts, high DPI, the Windows CI).
        self._form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self._form.setVerticalSpacing(6)
        outer.addLayout(self._form)

        group = None
        row_box_layout = None
        previous_vector = None
        for field_spec in self._fields:
            if field_spec.group and field_spec.group != group:
                group = field_spec.group
                group_label = QLabel(group)
                group_label.setStyleSheet("font-weight: 600; margin-top: 6px; border: none;")
                self._group_rows.append((self._form.rowCount(), group))
                self._form.addRow(group_label)
            value = field_spec.get(scenario)
            if field_spec.kind == "bool":
                box = QCheckBox()
                box.setChecked(bool(value))
            else:
                box = PreciseDoubleSpinBox()
                box.setRange(field_spec.minimum, field_spec.maximum)
                box.setDecimals(0 if field_spec.kind == "int" else field_spec.decimals)
                box.setSingleStep(field_spec.step)
                box.setSuffix(field_spec.suffix)
                if field_spec.component:
                    box.setPrefix(f"{field_spec.component}  ")
                box.setValue(value)
                # A fixed, readable width: the size hint is computed from the
                # range (+/-1e15 for a generated field), and stretching every
                # box across the dialog wasted space and hurt scanning.
                box.setFixedWidth(150 if field_spec.vector_key else 200)
            box.setToolTip(field_spec.help_text)
            label = QLabel(field_spec.label)
            label.setToolTip(field_spec.help_text)
            label.setStyleSheet("border: none;")
            # The form puts a label at the top of its row; with a box-tall
            # label and the box pinned to the top too, the label's text lines
            # up with the value instead of sitting above it.
            label.setMinimumHeight(box.sizeHint().height())
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            help_row = None
            if field_spec.vector_key and field_spec.vector_key == previous_vector:
                row_box_layout.addWidget(box)  # same vector: one row
                field_row = self._rows[-1][0]
            else:
                field_row = self._form.rowCount()
                # The field, then (for curated fields) its help text to the
                # RIGHT on the same row, using the width instead of a
                # narrow wrapped column underneath.
                holder = QWidget()
                # Scoped to the holder itself: an unscoped rule cascaded to
                # the spin box inside and erased its border, so the values
                # no longer looked editable (real user feedback).
                holder.setObjectName("wizardRow")
                holder.setStyleSheet("QWidget#wizardRow { background: transparent; border: none; }")
                row_box_layout = QHBoxLayout(holder)
                row_box_layout.setContentsMargins(0, 0, 0, 0)
                row_box_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
                row_box_layout.addWidget(box)
                if field_spec.inline_hint:
                    # One short line in normal-size type, centred on the box;
                    # the full explanation is the tooltip.
                    help_label = QLabel(field_spec.inline_hint)
                    # Wraps only when the dialog is too narrow for one line (large fonts, high DPI,
                    # the Windows CI): the card then shrinks instead of scrolling sideways.
                    help_label.setWordWrap(True)
                    help_label.setToolTip(field_spec.help_text)
                    help_label.setMinimumHeight(box.sizeHint().height())
                    help_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    help_label.setStyleSheet(f"color: {PALETTE['text_muted']}; border: none;")
                    row_box_layout.addSpacing(12)
                    row_box_layout.addWidget(help_label, 1)
                self._form.addRow(label, holder)
            previous_vector = field_spec.vector_key or None
            self._rows.append((field_row, help_row))
            self._boxes.append(box)
            self._initial.append(self._box_value(field_spec, box))

    def title(self) -> str:
        return self._title

    def filter(self, text: str) -> int:
        """Show only fields whose label or device group (or the section
        title) contains ``text``; returns how many are shown."""
        text = text.strip().lower()
        section_match = not text or text in self._title.lower()
        shown = 0
        visible_groups = set()
        for field_spec, (field_row, help_row) in zip(self._fields, self._rows):
            visible = (section_match or text in field_spec.label.lower()
                       or text in field_spec.group.lower())
            self._form.setRowVisible(field_row, visible)
            if help_row is not None:
                self._form.setRowVisible(help_row, visible)
            if visible:
                visible_groups.add(field_spec.group)
            shown += visible
        for row, group in self._group_rows:
            self._form.setRowVisible(row, group in visible_groups)
        return shown

    @staticmethod
    def _box_value(field_spec: WizardField, box):
        if field_spec.kind == "bool":
            return box.isChecked()
        if field_spec.kind == "int":
            return int(round(box.value()))
        return box.value()

    def apply_to_scenario(self) -> None:
        """Writes every field the user CHANGED back into the Scenario this
        section was built from -- called on OK (see
        TemplateCustomizeWizard.accept()), not live on every edit.
        Unchanged fields are left alone, so a derived curated field (e.g.
        '18's altitude, which moves two settings) can never be overwritten
        by an untouched one.
        """
        for field_spec, box, initial in zip(self._fields, self._boxes, self._initial):
            value = self._box_value(field_spec, box)
            if value != initial:
                field_spec.set(self._scenario, value)


def _paths_set_by(spec: TemplateWizardSpec, scenario: Scenario) -> set:
    """Setting paths a curated field changes, found by nudging each field
    on a copy -- these are left off the generated pages so no setting is
    offered twice."""
    paths = setting_paths(scenario)
    base = {path: get_setting(scenario, path) for path in paths}
    touched = set()
    for page in spec.pages:
        for field_spec in page.fields:
            trial = Scenario.from_dict(scenario.to_dict())
            value = field_spec.get(trial)
            try:
                field_spec.set(trial, (not value) if field_spec.kind == "bool" else value * 1.37 + 0.11)
            except (ValueError, TypeError, ZeroDivisionError):
                continue
            touched |= {path for path in paths if get_setting(trial, path) != base[path]}
    return touched


class TemplateCustomizeWizard(QDialog):
    """Customize a template before opening it: every section (the
    template's curated key settings first, then every other setting
    grouped by spacecraft and component -- see gui.wizard_settings) as
    compact cards on ONE scrolling page, with a table of contents on the
    left (click to jump; it follows the scroll) and a filter box. Built
    from a COPY of ``base_scenario`` (see this module's own docstring) --
    call :meth:`result_scenario` after ``exec()`` returns ``Accepted``.

    Real UX feedback shaped this: the curated pages alone were "very
    incomplete"; stepping through 16 pages with Next was no better; and
    showing one section at a time left a one-field section ("Reaction
    wheels") as a nearly empty dialog with an 800 px wide field.
    """

    def __init__(self, base_scenario: Scenario, spec: TemplateWizardSpec, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Customize: {base_scenario.name}")
        self._scenario = Scenario.from_dict(base_scenario.to_dict())
        self._field_pages: List[_WizardFieldPage] = []
        self._current_index = 0

        generated = build_all_settings_pages(self._scenario, exclude=_paths_set_by(spec, self._scenario))
        self._sections = QListWidget()
        self._sections.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_rows: List[int] = []  # list row of each section, in section order
        self._groups: List[tuple] = []  # (heading row, [section indices]) for each heading
        self._headings: List[QLabel] = []  # heading label above each group's first card

        sections_widget = QWidget()
        self._sections_layout = QVBoxLayout(sections_widget)
        self._sections_layout.setContentsMargins(0, 0, 8, 0)
        self._sections_layout.setSpacing(10)

        def add_heading(text: str) -> None:
            self._groups.append((self._sections.count(), []))
            item = QListWidgetItem(text)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            self._sections.addItem(item)
            heading = QLabel(text)
            heading.setStyleSheet(f"font-weight: 700; font-size: 120%; color: {PALETTE['text']}; "
                                  "margin-top: 4px;")
            self._sections_layout.addWidget(heading)
            self._headings.append(heading)

        def add_section(page_spec: WizardPageSpec, list_text: str) -> None:
            page = _WizardFieldPage(page_spec, self._scenario, self, heading_text=list_text)
            self._field_pages.append(page)
            self._sections_layout.addWidget(page)
            self._list_rows.append(self._sections.count())
            self._groups[-1][1].append(len(self._field_pages) - 1)
            item = QListWidgetItem("    " + list_text)
            item.setData(Qt.ItemDataRole.UserRole, len(self._field_pages) - 1)
            self._sections.addItem(item)

        add_heading("Key settings")
        for page_spec in spec.pages:
            add_section(page_spec, page_spec.title)
        group = None
        for page_spec in generated:
            owner, _, section = page_spec.title.partition(": ")
            heading, text = (owner, section) if section else ("Scenario", owner)
            if heading != group:
                add_heading(heading)
                group = heading
            add_section(page_spec, text[:1].upper() + text[1:])
        self._sections_layout.addStretch(1)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidget(sections_widget)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scrolled)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter settings, e.g. 'correction'")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._on_filter_changed)
        self._sections.itemClicked.connect(self._on_section_clicked)
        self._select_list_row(0)

        hint = QLabel("Change any setting, then open the result in the editor. The template file itself "
                      "is never changed.")
        hint.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Open in editor")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        left = QVBoxLayout()
        left.addWidget(self._filter)
        left.addWidget(self._sections)
        body = QHBoxLayout()
        body.addLayout(left)
        body.addWidget(self._scroll, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(body)
        layout.addWidget(buttons)

        list_width = min(self._sections.sizeHintForColumn(0) + 40, 260)
        self._sections.setFixedWidth(list_width)
        self._filter.setFixedWidth(list_width)
        widest = max((p.sizeHint().width() for p in self._field_pages), default=0)
        self.resize(min(max(760, list_width + widest + 70), 1100), 680)

    # -- section access (kept small and explicit for callers/tests) ------
    def pageIds(self) -> List[int]:  # noqa: N802 -- mirrors the old QWizard API
        return list(range(len(self._field_pages)))

    def page(self, page_id: int) -> _WizardFieldPage:
        return self._field_pages[page_id]

    def current_page(self) -> _WizardFieldPage:
        return self._field_pages[self._current_index]

    def show_page(self, page_id: int) -> None:
        """Scroll section ``page_id`` to the top and highlight it."""
        self._current_index = page_id
        self._select_list_row(page_id)
        self._scroll.widget().layout().activate()
        bar = self._scroll.verticalScrollBar()
        bar.blockSignals(True)  # this section is current, whatever the scroll position works out to
        bar.setValue(self._field_pages[page_id].y())
        bar.blockSignals(False)

    def _select_list_row(self, page_id: int) -> None:
        if self._list_rows:
            self._sections.blockSignals(True)
            self._sections.setCurrentRow(self._list_rows[page_id])
            self._sections.blockSignals(False)

    def _on_section_clicked(self, item) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            self.show_page(index)

    def _on_scrolled(self, value: int) -> None:
        """Keep the table of contents on the section at the top of the view."""
        visible = [i for i, page in enumerate(self._field_pages) if not page.isHidden()]
        current = next((i for i in reversed(visible) if self._field_pages[i].y() <= value + 20),
                       visible[0] if visible else 0)
        if current != self._current_index:
            self._current_index = current
            self._select_list_row(current)

    def _on_filter_changed(self, text: str) -> None:
        first_match = None
        for index, page in enumerate(self._field_pages):
            shown = page.filter(text)
            page.setVisible(shown > 0)
            self._sections.item(self._list_rows[index]).setHidden(shown == 0)
            if shown and first_match is None:
                first_match = index
        for (heading_row, section_indices), heading in zip(self._groups, self._headings):
            hidden = all(self._sections.item(self._list_rows[i]).isHidden() for i in section_indices)
            self._sections.item(heading_row).setHidden(hidden)
            heading.setVisible(not hidden)
        if first_match is not None:
            self.show_page(first_match)

    def accept(self) -> None:
        for page in self._field_pages:
            page.apply_to_scenario()
        super().accept()

    def result_scenario(self) -> Scenario:
        return self._scenario
