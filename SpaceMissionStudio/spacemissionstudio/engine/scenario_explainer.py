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

"""Turns a :class:`schema.scenario.Scenario` into a short, STRUCTURED
"recipe" summary (:func:`explain` -> :class:`ScenarioExplanation`) the
GUI renders as stat tiles / colored badges / a per-spacecraft table /
a formation-geometry diagram (:class:`FormationDiagram`, drawn by
``gui.formation_diagram_widget.FormationDiagramWidget``) -- never as
prose. Basilisk-free, independently-testable (same precedent as
:mod:`engine.constellation`'s own docstring describes about itself).

This is the "what is this scenario actually doing, at a glance" layer a
real user asked for directly: the app's bundled templates demonstrate
real fidelity, but a hand-built scenario had no equivalent "here's what
you've configured" summary anywhere in the GUI -- only the hand-written,
narrative ``description`` text the 20 bundled templates carry (which a
from-scratch scenario never has). This module is the ALWAYS-CURRENT,
terse counterpart: it reads the scenario's actual current fields on
every call, never narrative/pedagogical prose.

**Design discipline (do not regress this into prose or a bullet-point
wall -- both were tried and explicitly rejected by a real user before
this structured shape was settled on):** every ``StatTile.value``/
``Badge.label``/``note`` string is ONE short, scannable fragment ("Sun
-synchronous, 97.4 deg" -- not a sentence explaining WHY). Where a term
genuinely needs a definition (Sun-synchronous orbit, spherical-harmonics
gravity, third-body perturbation, phasing), this module does not inline
an explanation -- it points at ``USER_MANUAL.md``'s own glossary
(Section 12) by name, exactly as a bundled template's own hand-written
``description`` text already does elsewhere in this project.

:func:`explain` must NEVER raise -- it is called on every keystroke in
the GUI, often against a mid-edit/genuinely invalid scenario -- and it
builds each section/row CONDITIONALLY, so a trivial from-scratch scenario
renders a short tile row and maybe one badge, not a wall of empty
sections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from . import earth_orientation
from .orbit_design import sun_synchronous_inclination_deg
from .scenario_checks import gravity_fidelity_notes, pass_summary, scenario_warnings

_EARTH_REQUATOR_KM = 6378.1366  # [km] -- same reference value as engine.orbit_design's own

# How close a classical-elements orbit's own inclination must be to the
# computed Sun-synchronous value (at its own semi-major axis/eccentricity)
# to call it "Sun-synchronous" -- wide enough to tolerate the 2-decimal
# rounding every bundled template's own inclination_deg already carries
# (see engine.orbit_design.sun_synchronous_inclination_deg's own comment),
# narrow enough that an unrelated inclination (e.g. 51.6 deg) never matches.
_SSO_TOLERANCE_DEG = 0.1


@dataclass
class StatTile:
    label: str
    value: str


@dataclass
class Badge:
    label: str
    kind: str = "neutral"  # "neutral" | "accent" | "success" | "warning"


@dataclass
class SpacecraftFactRow:
    name: str
    facts: Dict[str, str] = field(default_factory=dict)  # short column_label -> value


@dataclass
class ExplanationSection:
    title: str
    badges: List[Badge] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)  # short relational one-liners only, rare


@dataclass
class FormationDiagram:
    """Everything a along-track phasing-keeping diagram needs to depict
    the real control mechanism -- a target separation held within a
    hysteresis band, not just the two names involved. Deliberately holds
    only ``PhasingKeepingConfig`` fields that are already fixed at
    scenario-design time (no live telemetry -- that's
    ``mission_dashboard_widget``'s job, which needs an actual run):
    ``target_separation_km`` is the FIRST entry of a schedule (the
    initial/current target); ``tolerance_fraction`` is the outer "trigger
    a correction" band, ``restore_tolerance_fraction`` the inner,
    tighter "stop correcting, settled" band -- together they're the
    actual deadband/hysteresis control law, not just one number.
    """

    chief_name: str
    follower_name: str
    target_separation_km: float
    tolerance_fraction: float
    restore_tolerance_fraction: float


@dataclass
class ScenarioExplanation:
    headline: str
    stat_tiles: List[StatTile] = field(default_factory=list)
    sections: List[ExplanationSection] = field(default_factory=list)
    spacecraft_table: List[SpacecraftFactRow] = field(default_factory=list)  # empty if < 2 spacecraft
    formation_diagrams: List[FormationDiagram] = field(default_factory=list)  # one per phasing_keeping spacecraft


def _models_oblateness(gravity) -> bool:
    """Sun-synchronous precession comes from Earth's J2, so it only exists
    when the gravity model includes it (degree 2 or more)."""
    return (gravity is not None and getattr(gravity, "central_body", "") == "earth"
            and (getattr(gravity, "central_body_degree", 0) or 0) >= 2)


def _is_sun_synchronous(orbit, gravity) -> bool:
    if not _models_oblateness(gravity):
        return False
    if getattr(orbit, "type", None) != "classical_elements":
        return False
    sma = orbit.semi_major_axis_km
    inc = orbit.inclination_deg
    if not sma or inc is None or sma <= 0:
        return False
    try:
        target = sun_synchronous_inclination_deg(sma, orbit.eccentricity or 0.0)
    except (ValueError, ArithmeticError, ZeroDivisionError):
        return False
    return abs(inc - target) <= _SSO_TOLERANCE_DEG


def _orbit_summary(orbit, gravity) -> str:
    orbit_type = getattr(orbit, "type", None)
    if orbit_type == "classical_elements":
        sma = orbit.semi_major_axis_km
        inc = orbit.inclination_deg
        if sma is None or inc is None:
            return "Classical elements"
        label = "SSO" if _is_sun_synchronous(orbit, gravity) else "Classical"
        altitude_km = sma - _EARTH_REQUATOR_KM
        return f"{label} {inc:g} deg, {altitude_km:.0f} km alt"
    if orbit_type == "cartesian":
        return "Cartesian state"
    if orbit_type == "tle":
        return "TLE"
    return "Orbit"


# Plain names for the attitude modes (shown instead of their code names).
_FSW_MODE_NAMES = {
    "inertial3D": "Inertial hold",
    "hillPoint": "Orbit-frame (nadir) pointing",
    "velocityPoint": "Velocity pointing",
    "sunSafePoint": "Sun pointing",
    "locationPointing": "Target pointing",
}


def _mode_name(fsw_mode: str) -> str:
    return _FSW_MODE_NAMES.get(fsw_mode, fsw_mode)


def _gravity_summary(gravity) -> str:
    body = gravity.central_body.capitalize()
    if gravity.central_body_degree <= 0:
        body_part = f"Point-mass {body}"
    else:
        body_part = f"Degree-{gravity.central_body_degree} {body}"
    if gravity.third_body_perturbers:
        return f"{body_part} + {'/'.join(b.capitalize() for b in gravity.third_body_perturbers)}"
    return body_part


def _spacecraft_control_summary(sc) -> str:
    parts = []
    if sc.fsw_mode:
        parts.append(_mode_name(sc.fsw_mode))
    if sc.station_keeping is not None:
        parts.append("station-keeping")
    if sc.geo_station_keeping is not None:
        parts.append("GEO station-keeping")
    if sc.phasing_keeping is not None:
        parts.append("phasing-keeping")
    if sc.constant_thrust is not None:
        parts.append("constant-thrust")
    if sc.momentum_dumping is not None:
        parts.append("RW desat (thrusters)")
    if sc.magnetic_momentum_management is not None:
        parts.append("RW desat (torque rods)")
    if not parts:
        return "none"
    return ", ".join(parts)


def _spacecraft_propellant_kg(sc) -> float:
    total = 0.0
    if sc.station_keeping is not None:
        total += sc.station_keeping.propellant_kg
    if sc.geo_station_keeping is not None:
        total += sc.geo_station_keeping.propellant_kg
    if sc.constant_thrust is not None:
        total += sc.constant_thrust.propellant_kg
    if sc.fuel_tank is not None:
        total += sc.fuel_tank.propellant_mass_kg
    return total


def _formation_section(scenario) -> ExplanationSection | None:
    badges: List[Badge] = []
    if any(sc.station_keeping is not None for sc in scenario.spacecraft):
        badges.append(Badge("Station-keeping", "accent"))
    if any(sc.geo_station_keeping is not None for sc in scenario.spacecraft):
        badges.append(Badge("GEO station-keeping (E-W, N-S)", "accent"))
    if any(sc.phasing_keeping is not None for sc in scenario.spacecraft):
        badges.append(Badge("Phasing-keeping", "accent"))
    laws = {sc.phasing_keeping.control_law for sc in scenario.spacecraft if sc.phasing_keeping is not None}
    for law, label in (("mean_oe", "Basilisk mean-element feedback"), ("hill_pd", "Basilisk Hill-frame PD")):
        if law in laws:
            badges.append(Badge(label, "accent"))
    if any(sc.constant_thrust is not None for sc in scenario.spacecraft):
        badges.append(Badge("Constant thrust", "accent"))
    if not badges:
        return None
    notes = []
    no_station_keeping = [sc.name for sc in scenario.spacecraft
                           if sc.phasing_keeping is not None and sc.station_keeping is None]
    if no_station_keeping:
        notes.append(f"{', '.join(no_station_keeping)}: phasing keeping needs station-keeping on the same "
                     "spacecraft (User Manual Sec. 12)")
    return ExplanationSection(title="Formation / orbit maintenance", badges=badges, notes=notes)


def _attitude_section(scenario) -> ExplanationSection | None:
    modes = sorted({sc.fsw_mode for sc in scenario.spacecraft if sc.fsw_mode})
    comms_pointing_count = sum(1 for sc in scenario.spacecraft if sc.comms_pointing is not None)
    if not modes and not comms_pointing_count:
        return None
    badges = [Badge(_mode_name(mode), "accent") for mode in modes]
    if comms_pointing_count:
        badges.append(Badge("Comms pointing", "accent"))
    return ExplanationSection(title="Attitude control", badges=badges)


def _environment_section(scenario) -> ExplanationSection | None:
    badges: List[Badge] = []
    if any(_is_sun_synchronous(sc.orbit, scenario.gravity) for sc in scenario.spacecraft):
        badges.append(Badge("Sun-synchronous", "accent"))
    if any(sc.enable_drag for sc in scenario.spacecraft):
        badges.append(Badge("Drag", "accent"))
    if any(sc.enable_srp for sc in scenario.spacecraft):
        badges.append(Badge("Solar radiation pressure", "accent"))
    if any(sc.enable_gravity_gradient for sc in scenario.spacecraft):
        badges.append(Badge("Gravity gradient", "accent"))
    if any(sc.facets and (sc.enable_drag or sc.enable_srp) for sc in scenario.spacecraft):
        badges.append(Badge("Facet model (drag/SRP torques)", "accent"))
    notes = gravity_fidelity_notes(scenario)
    if getattr(scenario.gravity, "central_body", "") == "earth":
        notes += _earth_frame_notes(scenario)
    if not badges:
        return None
    return ExplanationSection(title="Environment", badges=badges, notes=notes)


def _earth_frame_notes(scenario) -> List[str]:
    """The Earth-fixed frame a run will use and its accuracy
    (engine.earth_orientation, ECSS-E-ST-10-09C 5.4.9f)."""
    try:
        start = datetime.fromisoformat(scenario.epoch_utc)
        if start.tzinfo is not None:
            start = start.astimezone(timezone.utc).replace(tzinfo=None)
        kernels = earth_orientation.installed()
        notes = earth_orientation.notes(start, start + timedelta(days=scenario.sim_settings.duration_days), kernels)
    except Exception:  # noqa: BLE001 -- a half-edited scenario must never break the Explain tab
        return []
    return notes or [f"Earth orientation: {earth_orientation.EARTH_FIXED_FRAME} from IERS data"]


def _power_comms_section(scenario) -> ExplanationSection | None:
    badges: List[Badge] = []
    if any(sc.power is not None for sc in scenario.spacecraft):
        badges.append(Badge("Power budget", "accent"))
    if any(sc.rf_link is not None for sc in scenario.spacecraft):
        badges.append(Badge("RF link budget", "accent"))
    if not badges:
        return None
    return ExplanationSection(title="Power & comms", badges=badges)


def _ground_stations_section(scenario) -> ExplanationSection | None:
    if not scenario.ground_stations:
        return None
    try:
        passes = pass_summary(scenario)  # predicted from the initial orbits -- see engine.scenario_checks
    except Exception:  # noqa: BLE001 -- explain() must never raise
        passes = []
    return ExplanationSection(
        title="Ground stations",
        badges=[Badge(gs.name, "neutral") for gs in scenario.ground_stations],
        notes=passes,
    )


def _checks_section(scenario) -> ExplanationSection | None:
    """Setups that can't do what they're configured for -- shown first, so
    they are seen before a long run (see engine.scenario_checks)."""
    warnings = scenario_warnings(scenario)
    if not warnings:
        return None
    return ExplanationSection(
        title="Check before running",
        badges=[Badge(f"{len(warnings)} to check", "warning")],
        notes=warnings,
    )


def _formation_diagrams(scenario) -> List[FormationDiagram]:
    diagrams = []
    for sc in scenario.spacecraft:
        pk = sc.phasing_keeping
        # The diagram shows the drift-orbit law's trigger/restore band; the
        # Basilisk laws (engine.formation_control) have no band.
        if pk is None or not pk.target_separation_km or pk.control_law != "drift_orbit":
            continue
        diagrams.append(FormationDiagram(
            chief_name=pk.chief_spacecraft,
            follower_name=sc.name,
            target_separation_km=pk.target_separation_km[0],
            tolerance_fraction=pk.tolerance_fraction,
            restore_tolerance_fraction=pk.restore_tolerance_fraction,
        ))
    return diagrams


def _monte_carlo_section(scenario) -> ExplanationSection | None:
    mc = scenario.monte_carlo
    if not mc.enabled:
        return None
    return ExplanationSection(
        title="Monte Carlo",
        badges=[Badge(f"{mc.num_runs} runs", "accent")],
    )


def _duration_label(days: float) -> str:
    """"2.25 h" rather than "0.09375 d" for short runs; minutes under an
    hour, days from 2 d up."""
    if days < 1.0 / 24.0:
        return f"{round(days * 1440.0, 1):g} min"
    if days < 2.0:
        return f"{round(days * 24.0, 2):g} h"
    return f"{round(days, 2):g} d"


def explain(scenario) -> ScenarioExplanation:
    """Never raises -- called on every keystroke in the GUI, often
    against a mid-edit/invalid scenario.
    """
    try:
        return _explain(scenario)
    except Exception:  # noqa: BLE001 -- see docstring: must never raise
        return ScenarioExplanation(headline=getattr(scenario, "name", "") or "(unnamed scenario)")


def _explain(scenario) -> ScenarioExplanation:
    spacecraft = scenario.spacecraft

    stat_tiles = [
        StatTile("Spacecraft", str(len(spacecraft))),
        StatTile("Duration", _duration_label(scenario.sim_settings.duration_days)),
        StatTile("Gravity", _gravity_summary(scenario.gravity)),
    ]
    if len(spacecraft) == 1:
        stat_tiles.append(StatTile("Orbit", _orbit_summary(spacecraft[0].orbit, scenario.gravity)))
    if scenario.simulation_mode != "full_attitude":
        stat_tiles.append(StatTile("Mode", "Orbit only"))

    sections = [s for s in (
        _checks_section(scenario),
        _formation_section(scenario),
        _attitude_section(scenario),
        _environment_section(scenario),
        _power_comms_section(scenario),
        _ground_stations_section(scenario),
        _monte_carlo_section(scenario),
    ) if s is not None]

    spacecraft_table: List[SpacecraftFactRow] = []
    if len(spacecraft) >= 2:
        # Spacecraft with identical facts share one row (a 6-satellite
        # constellation used to repeat the same row six times).
        groups: dict = {}
        for sc in spacecraft:
            propellant_kg = _spacecraft_propellant_kg(sc)
            facts = {
                "Orbit": _orbit_summary(sc.orbit, scenario.gravity),
                "Control": _spacecraft_control_summary(sc),
                "Propellant": f"{propellant_kg:g} kg" if propellant_kg > 0 else "-",
            }
            groups.setdefault(tuple(facts.items()), (facts, []))[1].append(sc.name)
        for facts, names in groups.values():
            if len(names) > 2:
                label = f"{names[0]} ... {names[-1]} ({len(names)})"
            else:
                label = ", ".join(names)
            spacecraft_table.append(SpacecraftFactRow(name=label, facts=facts))

    return ScenarioExplanation(
        headline=scenario.name or "(unnamed scenario)",
        stat_tiles=stat_tiles,
        sections=sections,
        spacecraft_table=spacecraft_table,
        formation_diagrams=_formation_diagrams(scenario),
    )
