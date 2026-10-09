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

r"""
Flexible solar arrays (``schema.scenario.SolarArrayConfig``): one
Basilisk ``hingedRigidBodyStateEffector`` per array, wired as
``examples/scenarioHingedRigidBody.py`` and, for its power,
``examples/scenarioDeployingPanel.py`` wire them.

Basilisk's hinge frame H (``dcm_HB`` from the body frame) has the hinge
along h2; the panel frame S is H turned by the hinge angle theta about h2,
and the panel's centre of mass lies ``d`` along -s1 from the hinge
(``hingedRigidBodyStateEffector.cpp``: ``r_SP = r_HB - d * sHat1``). So,
from the configuration:

* h1 = -deploy_direction, h3 = normal, h2 = h3 x h1 (the hinge line);
* ``d`` = span / 2, the centre of a uniform panel;
* ``IPntS_S`` = a uniform thin plate's inertia about its centre:
  m w^2 / 12 about s1, m L^2 / 12 about s2 (the flapping axis),
  m (L^2 + w^2) / 12 about s3;
* the hinge spring ``k`` and damper ``c`` give the configured first mode
  with the hub held fixed: with ``J = I_s2 + m d^2`` about the hinge,
  ``k = J (2 pi f)^2`` and ``c = 2 zeta sqrt(k J)``.

A positive theta turns the tip toward +s3, the cell side
(``initial_deflection_deg``).

The arrays' mass is part of ``SpacecraftConfig.dry_mass_kg``, so the hub
gets the rest (:func:`hub_mass_kg`); the flight software's inertia
(``VehicleConfigMsg``, ``mrpFeedback``) is the hub's plus the undeflected
arrays' (:func:`fsw_inertia_kg_m2`), what a real spacecraft's FSW would
carry.

Everything above the Basilisk import inside :func:`build_solar_arrays` is
Basilisk-free, for ``engine.monte_carlo`` and the GUI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

import numpy as np


def _unit(vector) -> np.ndarray:
    v = np.asarray(vector, dtype=float)
    return v / np.linalg.norm(v)


def dcm_hb(array) -> np.ndarray:
    """Body-to-hinge-frame DCM: rows h1, h2, h3 in body components."""
    h1 = -_unit(array.deploy_direction_b)
    h3 = _unit(array.normal_b)
    h3 = h3 - h1 * float(h1 @ h3)  # exactly perpendicular (validation allows 1e-3)
    h3 = h3 / np.linalg.norm(h3)
    h2 = np.cross(h3, h1)
    return np.vstack([h1, h2, h3])


def plate_inertia_kg_m2(array) -> np.ndarray:
    """A uniform thin plate's inertia about its centre, in the panel frame S."""
    m, length, width = array.mass_kg, array.span_m, array.width_m
    return np.diag([m * width ** 2 / 12.0, m * length ** 2 / 12.0, m * (length ** 2 + width ** 2) / 12.0])


def hinge_inertia_kg_m2(array) -> float:
    """The panel's inertia about its hinge line [kg*m^2]."""
    return float(plate_inertia_kg_m2(array)[1, 1]) + array.mass_kg * (array.span_m / 2.0) ** 2


def hinge_stiffness_damping(array):
    """(k [N*m/rad], c [N*m*s/rad]) giving ``first_mode_hz`` and
    ``damping_ratio`` with the hub held fixed."""
    j = hinge_inertia_kg_m2(array)
    k = j * (2.0 * math.pi * array.first_mode_hz) ** 2
    return k, 2.0 * array.damping_ratio * math.sqrt(k * j)


def arrays_mass_kg(sc_config) -> float:
    return float(sum(array.mass_kg for array in sc_config.solar_arrays))


def hub_mass_offset_kg(sc_config) -> float:
    """What ``engine.service`` puts in ``hub.mHub`` beyond ``dry_mass_kg``:
    the station-keeping, GEO station-keeping and constant-thrust propellant,
    less the flexible arrays (a state effector's mass is its own)."""
    offset = 0.0
    for block in (sc_config.station_keeping, sc_config.geo_station_keeping, sc_config.constant_thrust):
        if block is not None:
            offset += block.propellant_kg
    return offset - arrays_mass_kg(sc_config)


def hub_mass_kg(sc_config) -> float:
    """The hub's initial mass [kg] (``hub.mHub``)."""
    return sc_config.dry_mass_kg + hub_mass_offset_kg(sc_config)


def fsw_inertia_kg_m2(sc_config) -> List[float]:
    """The hub's inertia plus each undeflected array's, about the body
    origin, row-major -- the inertia the flight software uses."""
    total = np.asarray(sc_config.inertia_kg_m2, dtype=float).reshape(3, 3)
    for array in sc_config.solar_arrays:
        dcm = dcm_hb(array)  # theta = 0: S = H
        centre = np.asarray(array.hinge_position_b, dtype=float) + array.span_m / 2.0 * _unit(array.deploy_direction_b)
        about_centre = dcm.T @ plate_inertia_kg_m2(array) @ dcm
        total = total + about_centre + array.mass_kg * (float(centre @ centre) * np.eye(3) - np.outer(centre, centre))
    return [float(v) for v in total.reshape(-1)]


@dataclass
class SolarArrayHandle:
    """What :func:`build_solar_arrays` built, per array, in order."""

    names: List[str] = field(default_factory=list)
    effectors: list = field(default_factory=list)
    state_recorders: list = field(default_factory=list)
    power_recorders: list = field(default_factory=list)  # None where an array generates no power


def build_solar_arrays(scSim, task_name: str, tag: str, sc_config, sc_object, record, battery=None,
                       sun_state_msg=None, eclipse_msg=None, panel_efficiency: float = 0.0) -> SolarArrayHandle:
    """Adds ``sc_config.solar_arrays`` to ``sc_object``; with ``battery``,
    each power-generating array also feeds it through its own
    ``simpleSolarPanel`` on the array's own state."""
    from Basilisk.simulation import hingedRigidBodyStateEffector, simpleSolarPanel

    handle = SolarArrayHandle()
    for array in sc_config.solar_arrays:
        effector = hingedRigidBodyStateEffector.HingedRigidBodyStateEffector()
        effector.ModelTag = f"{tag}Array_{array.name}"
        effector.mass = array.mass_kg  # [kg]
        effector.IPntS_S = plate_inertia_kg_m2(array).tolist()  # [kg*m^2]
        effector.d = array.span_m / 2.0  # [m]
        effector.k, effector.c = hinge_stiffness_damping(array)
        effector.r_HB_B = [[float(v)] for v in array.hinge_position_b]  # [m]
        effector.dcm_HB = dcm_hb(array).tolist()
        effector.thetaInit = math.radians(array.initial_deflection_deg)  # [rad]
        effector.thetaDotInit = math.radians(array.initial_rate_deg_s)  # [rad/s]
        sc_object.addStateEffector(effector)
        recorder = record(effector.hingedRigidBodyOutMsg)
        scSim.AddModelToTask(task_name, recorder)
        power_recorder = None
        if battery is not None and array.generates_power:
            panel = simpleSolarPanel.SimpleSolarPanel()
            panel.ModelTag = f"{tag}ArrayPower_{array.name}"
            panel.setPanelParameters([0.0, 0.0, 1.0], array.span_m * array.width_m, panel_efficiency)  # s3: cells
            panel.stateInMsg.subscribeTo(effector.hingedRigidBodyConfigLogOutMsg)
            panel.sunInMsg.subscribeTo(sun_state_msg)
            if eclipse_msg is not None:
                panel.sunEclipseInMsg.subscribeTo(eclipse_msg)
            scSim.AddModelToTask(task_name, panel, 50)  # before the battery (40), as the body panel
            battery.addPowerNodeToModel(panel.nodePowerOutMsg)
            power_recorder = record(panel.nodePowerOutMsg)
            scSim.AddModelToTask(task_name, power_recorder)
            handle.effectors.append(panel)
        handle.names.append(array.name)
        handle.effectors.append(effector)
        handle.state_recorders.append(recorder)
        handle.power_recorders.append(power_recorder)
    return handle
