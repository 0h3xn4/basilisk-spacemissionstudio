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
from typing import Dict, List

from .orbit_design import sun_synchronous_inclination_deg

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


def _is_sun_synchronous(orbit) -> bool:
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


def _orbit_summary(orbit) -> str:
    orbit_type = getattr(orbit, "type", None)
    if orbit_type == "classical_elements":
        sma = orbit.semi_major_axis_km
        inc = orbit.inclination_deg
        if sma is None or inc is None:
            return "Classical elements"
        label = "SSO" if _is_sun_synchronous(orbit) else "Classical"
        altitude_km = sma - _EARTH_REQUATOR_KM
        return f"{label} {inc:g} deg, {altitude_km:.0f} km alt"
    if orbit_type == "cartesian":
        return "Cartesian state"
    if orbit_type == "tle":
        return "TLE"
    return "Orbit"


def _gravity_summary(gravity) -> str:
    if gravity.central_body_degree <= 0:
        body_part = f"Point-mass {gravity.central_body}"
    else:
        body_part = f"Degree-{gravity.central_body_degree} {gravity.central_body}"
    if gravity.third_body_perturbers:
        return f"{body_part} + {'/'.join(gravity.third_body_perturbers)}"
    return body_part


def _spacecraft_control_summary(sc) -> str:
    parts = []
    if sc.fsw_mode:
        parts.append(sc.fsw_mode)
    if sc.station_keeping is not None:
        parts.append("station-keeping")
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
    if sc.constant_thrust is not None:
        total += sc.constant_thrust.propellant_kg
    if sc.fuel_tank is not None:
        total += sc.fuel_tank.propellant_mass_kg
    return total


def _formation_section(scenario) -> ExplanationSection | None:
    badges: List[Badge] = []
    if any(sc.station_keeping is not None for sc in scenario.spacecraft):
        badges.append(Badge("Station-keeping", "accent"))
    if any(sc.phasing_keeping is not None for sc in scenario.spacecraft):
        badges.append(Badge("Phasing-keeping", "accent"))
    if any(sc.constant_thrust is not None for sc in scenario.spacecraft):
        badges.append(Badge("Constant thrust", "accent"))
    if not badges:
        return None
    notes = []
    no_station_keeping = [sc.name for sc in scenario.spacecraft
                           if sc.phasing_keeping is not None and sc.station_keeping is None]
    if no_station_keeping:
        notes.append(f"{', '.join(no_station_keeping)}: phasing_keeping with no station_keeping "
                      "(needs it on the SAME spacecraft -- see User Manual Sec. 12, 'Station-keeping')")
    return ExplanationSection(title="Formation / orbit maintenance", badges=badges, notes=notes)


def _attitude_section(scenario) -> ExplanationSection | None:
    modes = sorted({sc.fsw_mode for sc in scenario.spacecraft if sc.fsw_mode})
    comms_pointing_count = sum(1 for sc in scenario.spacecraft if sc.comms_pointing is not None)
    if not modes and not comms_pointing_count:
        return None
    badges = [Badge(mode, "neutral") for mode in modes]
    if comms_pointing_count:
        badges.append(Badge("Comms pointing", "accent"))
    return ExplanationSection(title="Attitude control", badges=badges)


def _environment_section(scenario) -> ExplanationSection | None:
    badges: List[Badge] = []
    if any(_is_sun_synchronous(sc.orbit) for sc in scenario.spacecraft):
        badges.append(Badge("Sun-synchronous", "accent"))
    if any(sc.enable_drag for sc in scenario.spacecraft):
        badges.append(Badge("Drag ON", "warning"))
    if any(sc.enable_srp for sc in scenario.spacecraft):
        badges.append(Badge("SRP ON", "warning"))
    if any(sc.enable_gravity_gradient for sc in scenario.spacecraft):
        badges.append(Badge("Gravity gradient", "neutral"))
    if not badges:
        return None
    return ExplanationSection(title="Environment", badges=badges)


def _power_comms_section(scenario) -> ExplanationSection | None:
    badges: List[Badge] = []
    if any(sc.power is not None for sc in scenario.spacecraft):
        badges.append(Badge("Power budget", "success"))
    if any(sc.rf_link is not None for sc in scenario.spacecraft):
        badges.append(Badge("RF link budget", "success"))
    if not badges:
        return None
    return ExplanationSection(title="Power & comms", badges=badges)


def _ground_stations_section(scenario) -> ExplanationSection | None:
    if not scenario.ground_stations:
        return None
    names = ", ".join(gs.name for gs in scenario.ground_stations)
    return ExplanationSection(
        title="Ground stations",
        badges=[Badge(f"{len(scenario.ground_stations)} station(s)", "neutral")],
        notes=[names],
    )


def _formation_diagrams(scenario) -> List[FormationDiagram]:
    diagrams = []
    for sc in scenario.spacecraft:
        pk = sc.phasing_keeping
        if pk is None or not pk.target_separation_km:
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
        StatTile("Duration", f"{scenario.sim_settings.duration_days:g} d"),
        StatTile("Gravity", _gravity_summary(scenario.gravity)),
    ]
    if len(spacecraft) == 1:
        stat_tiles.append(StatTile("Orbit", _orbit_summary(spacecraft[0].orbit)))
    if scenario.simulation_mode != "full_attitude":
        stat_tiles.append(StatTile("Mode", "Orbit only"))

    sections = [s for s in (
        _formation_section(scenario),
        _attitude_section(scenario),
        _environment_section(scenario),
        _power_comms_section(scenario),
        _ground_stations_section(scenario),
        _monte_carlo_section(scenario),
    ) if s is not None]

    spacecraft_table: List[SpacecraftFactRow] = []
    if len(spacecraft) >= 2:
        for sc in spacecraft:
            propellant_kg = _spacecraft_propellant_kg(sc)
            spacecraft_table.append(SpacecraftFactRow(
                name=sc.name,
                facts={
                    "Orbit": _orbit_summary(sc.orbit),
                    "Control": _spacecraft_control_summary(sc),
                    "Propellant": f"{propellant_kg:g} kg" if propellant_kg > 0 else "-",
                },
            ))

    return ScenarioExplanation(
        headline=scenario.name or "(unnamed scenario)",
        stat_tiles=stat_tiles,
        sections=sections,
        spacecraft_table=spacecraft_table,
        formation_diagrams=_formation_diagrams(scenario),
    )
