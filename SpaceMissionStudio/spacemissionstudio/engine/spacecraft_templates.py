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

"""A small curated library of reusable spacecraft "bus" templates.

Per user feedback: a brand-new :class:`schema.scenario.SpacecraftConfig`
starts from ``SpacecraftConfig()``'s bare dataclass defaults (100 kg, a
flat 10 kg*m^2 diagonal inertia, no sensors/actuators/power/attitude
control) -- a placeholder, not anything resembling a real vehicle, forcing
a beginner to invent every number from scratch. Each :class:`SpacecraftTemplate`
here instead ``build()``\\ s a complete, internally-consistent, physically
REASONABLE starting point (mass, inertia, sensors, actuators, power,
attitude mode, drag/SRP) the user can then adjust in the ordinary
spacecraft editor -- exactly like starting a document from a template
instead of a blank page.

Pure Python/schema data, no Basilisk import, matching
``engine.constellation``'s same "pure orbital mechanics/data, no Basilisk
import" split (see that module's docstring) -- this is reusable by the
GUI (``gui.spacecraft_editor``'s "New from template..." button) and would
be equally usable from a headless/CLI path later without needing a
Basilisk build.

Numbers here are ROUNDED, ORDER-OF-MAGNITUDE-REASONABLE engineering
figures for illustration (e.g. each bus's inertia from its box
dimensions/mass), not a specific real flight vehicle's actual
datasheet -- same "don't fabricate precision this project doesn't have"
discipline used elsewhere (see e.g. ``engine.link_budget``'s module
docstring). Pick a template as a STARTING POINT, then adjust for your
actual spacecraft. The ESPA bus's wheels reuse
``gui.sensor_actuator_editor._KIND_PARAM_SPECS``'s "reaction_wheel"
example values; the 150-500 kg buses match the bundled scenario
templates' buses (``scripts/_generate_templates.py``).

Every template's orbit is the same placeholder (~500 km circular,
97.4 deg -- a common sun-synchronous inclination at that altitude): the
"New from template..." flow opens the ordinary
:class:`gui.spacecraft_editor.SpacecraftEditorDialog` right after picking
one, so the user sets the ACTUAL orbit (and name, and anything else) there
via the normal orbit editor, same as always.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

from .facets import box_facets
from ..schema.scenario import (
    ActuatorConfig,
    MagneticMomentumManagementConfig,
    OrbitIC,
    PowerConfig,
    SensorConfig,
    SpacecraftConfig,
)

# Matches gui.sensor_actuator_editor._KIND_PARAM_SPECS["reaction_wheel"]'s
# own example values -- see this module's docstring. Js and maxMomentum are
# mutually exclusive for rw_type="custom" (rwFactory.create() hard-exits
# the whole process if both are given -- confirmed directly against a real
# Basilisk build), so only Js (not maxMomentum) is included here.
_RW_EXAMPLE_PARAMS = {"rw_type": "custom", "Omega_max": 6000.0, "u_max": 0.2, "Js": 0.028}


def _placeholder_orbit() -> OrbitIC:
    return OrbitIC(
        type="classical_elements",
        semi_major_axis_km=6878.0,  # ~500 km altitude
        eccentricity=0.0,
        inclination_deg=97.4,  # sun-synchronous at ~500 km
        raan_deg=0.0,
        arg_periapsis_deg=0.0,
        anomaly_type="true",
        true_anomaly_deg=0.0,
    )


def _three_reaction_wheels() -> List[ActuatorConfig]:
    return [
        ActuatorConfig(kind="reaction_wheel", name="rw-x", params={"gsHat_B": [1.0, 0.0, 0.0], **_RW_EXAMPLE_PARAMS}),
        ActuatorConfig(kind="reaction_wheel", name="rw-y", params={"gsHat_B": [0.0, 1.0, 0.0], **_RW_EXAMPLE_PARAMS}),
        ActuatorConfig(kind="reaction_wheel", name="rw-z", params={"gsHat_B": [0.0, 0.0, 1.0], **_RW_EXAMPLE_PARAMS}),
    ]


def _box_inertia(mass_kg: float, x_m: float, y_m: float, z_m: float) -> List[float]:
    """Row-major principal inertia [kg*m^2] of a uniform box: I_xx =
    m (y^2 + z^2) / 12, and so on."""
    return [round(mass_kg * (y_m ** 2 + z_m ** 2) / 12.0, 1), 0.0, 0.0,
            0.0, round(mass_kg * (x_m ** 2 + z_m ** 2) / 12.0, 1), 0.0,
            0.0, 0.0, round(mass_kg * (x_m ** 2 + y_m ** 2) / 12.0, 1)]


def _sun_safe_bus(mass_kg: float, size_m: tuple, wheel_params: dict, rod_dipole_a_m2: float,
                  drag_area_m2: float, srp_area_m2: float, power: PowerConfig) -> SpacecraftConfig:
    """A three-axis-stabilized bus in Sun-safe pointing: star tracker, IMU,
    a coarse sun sensor and the solar array all on +Z, the axis
    ``sunSafePoint`` turns to the Sun, and three orthogonal wheels. Three
    orthogonal torque rods continuously steer the wheels back toward rest
    against Earth's field (``mtbMomentumManagement``), as on most LEO
    spacecraft of this class, so their momentum never builds up."""
    axes = (("x", [1.0, 0.0, 0.0]), ("y", [0.0, 1.0, 0.0]), ("z", [0.0, 0.0, 1.0]))
    return SpacecraftConfig(
        name="template",
        orbit=_placeholder_orbit(),
        dry_mass_kg=mass_kg,
        inertia_kg_m2=_box_inertia(mass_kg, *size_m),
        enable_drag=True,
        drag_coeff=2.2,
        drag_area_m2=drag_area_m2,
        enable_srp=True,
        srp_coeff=1.3,
        srp_area_m2=srp_area_m2,
        sensors=[
            SensorConfig(kind="star_tracker", name="st-1", params={"noise_arcsec": 5.0}),
            SensorConfig(kind="imu", name="imu-1", params={"gyro_noise_rad_s": 1e-5}),
            SensorConfig(kind="coarse_sun_sensor", name="css-1", params={"nHat_B": [0.0, 0.0, 1.0]}),
        ],
        actuators=[
            *[ActuatorConfig(kind="reaction_wheel", name=f"rw-{axis_name}", params={"gsHat_B": axis, **wheel_params})
              for axis_name, axis in axes],
            *[ActuatorConfig(kind="magnetic_torque_rod", name=f"mtb-{axis_name}",
                             params={"gtHat_B": axis, "max_dipole_a_m2": rod_dipole_a_m2})
              for axis_name, axis in axes],
        ],
        magnetic_momentum_management=MagneticMomentumManagementConfig(
            wheel_speed_biases_rad_s=[0.0, 0.0, 0.0]),  # [rad/s] steer every wheel toward rest
        power=power,
        # The bus and its +Z array as flat plates: drag and SRP follow the
        # attitude. The array sits on the +Z face, so it adds no torque
        # until it is moved off to one side.
        facets=box_facets(size_m, power.panel_area_m2, power.panel_normal_b),
        fsw_mode="sunSafePoint",
        fsw_params={"sHatBdyCmd": [0.0, 0.0, 1.0]},
    )


def _build_microsat_150() -> SpacecraftConfig:
    # 0.8 x 0.8 x 1.0 m -> I = 20.5, 20.5, 16.0 kg*m^2. Wheels the size of
    # the catalog's VRW-D-6; "custom" derives the rotor inertia from
    # maxMomentum/Omega_max.
    return _sun_safe_bus(
        150.0, (0.8, 0.8, 1.0),  # [kg], [m]
        {"rw_type": "custom", "maxMomentum": 6.0, "Omega_max": 6000.0, "u_max": 0.05},  # [N*m*s], [RPM], [N*m]
        rod_dipole_a_m2=15.0,  # [A*m^2] the catalog's MTQ800 class
        drag_area_m2=0.8, srp_area_m2=1.5,
        power=PowerConfig(panel_area_m2=1.0, panel_efficiency=0.29, panel_normal_b=[0.0, 0.0, 1.0],
                          bus_idle_power_w=60.0, battery_capacity_wh=300.0, battery_initial_soc=0.9),
    )


def _build_smallsat_300() -> SpacecraftConfig:
    # 1.2 x 1.2 x 1.5 m -> I = 92.3, 92.3, 72.0 kg*m^2; 12 N*m*s Honeywell HR12 wheels.
    return _sun_safe_bus(
        300.0, (1.2, 1.2, 1.5),  # [kg], [m]
        {"rw_type": "Honeywell_HR12", "maxMomentum": 12.0},  # [N*m*s]
        rod_dipole_a_m2=30.0,  # [A*m^2]
        drag_area_m2=1.8, srp_area_m2=4.0,
        power=PowerConfig(panel_area_m2=2.5, panel_efficiency=0.29, panel_normal_b=[0.0, 0.0, 1.0],
                          bus_idle_power_w=150.0, battery_capacity_wh=700.0, battery_initial_soc=0.9),
    )


def _build_smallsat_500() -> SpacecraftConfig:
    # 1.2 x 1.2 x 1.6 m -> I = 166.7, 166.7, 120.0 kg*m^2; 25 N*m*s Honeywell HR12 wheels.
    return _sun_safe_bus(
        500.0, (1.2, 1.2, 1.6),  # [kg], [m]
        {"rw_type": "Honeywell_HR12", "maxMomentum": 25.0},  # [N*m*s]
        rod_dipole_a_m2=50.0,  # [A*m^2]
        drag_area_m2=2.0, srp_area_m2=6.0,
        power=PowerConfig(panel_area_m2=4.0, panel_efficiency=0.29, panel_normal_b=[0.0, 0.0, 1.0],
                          bus_idle_power_w=250.0, battery_capacity_wh=1200.0, battery_initial_soc=0.9),
    )


def _build_smallsat_espa() -> SpacecraftConfig:
    # ESPA-class smallsat, ~100 kg -- inertia is an illustrative
    # order-of-magnitude figure for a roughly 0.5 m bus, not derived from a
    # specific vehicle's mass properties.
    return SpacecraftConfig(
        name="template",
        orbit=_placeholder_orbit(),
        dry_mass_kg=100.0,
        inertia_kg_m2=[15.0, 0.0, 0.0, 0.0, 15.0, 0.0, 0.0, 0.0, 12.0],
        sensors=[
            SensorConfig(kind="star_tracker", name="st-1", params={"noise_arcsec": 5.0}),
            SensorConfig(kind="coarse_sun_sensor", name="css-1", params={"nHat_B": [0.0, 0.0, 1.0]}),
        ],
        actuators=_three_reaction_wheels(),
        power=PowerConfig(
            panel_area_m2=1.0,
            panel_efficiency=0.29,
            panel_normal_b=[0.0, 0.0, 1.0],
            bus_idle_power_w=25.0,
            battery_capacity_wh=150.0,
            battery_initial_soc=0.9,
        ),
        fsw_mode="inertial3D",
        fsw_params={"sigma_R0N": [0.0, 0.0, 0.0]},
        enable_drag=True,  # SpacecraftConfig's own drag_coeff/drag_area_m2 defaults (2.2, 1.0 m^2) are already
        enable_srp=True,   # a reasonable order-of-magnitude fit for a ~100 kg, ~1 m-class bus -- left as-is.
    )


@dataclass(frozen=True)
class SpacecraftTemplate:
    name: str
    description: str
    build: Callable[[], SpacecraftConfig]


SPACECRAFT_TEMPLATES: List[SpacecraftTemplate] = [
    SpacecraftTemplate(
        "ESPA-class smallsat (100 kg)",
        "100 kg, star tracker + coarse sun sensor + 3 reaction wheels + inertial3D attitude control + a "
        "~1 m-class power budget. Drag+SRP enabled.",
        _build_smallsat_espa,
    ),
    SpacecraftTemplate(
        "Microsatellite (150 kg)",
        "150 kg, 0.8 x 0.8 x 1.0 m. Star tracker, IMU, sun sensor, three 6 N*m*s wheels unloaded by 15 A*m^2 torque rods, a 1 m^2 array "
        "and 300 Wh battery. Starts Sun-safe pointing. Drag+SRP enabled.",
        _build_microsat_150,
    ),
    SpacecraftTemplate(
        "Small satellite (300 kg)",
        "300 kg, 1.2 x 1.2 x 1.5 m. Star tracker, IMU, sun sensor, three 12 N*m*s wheels unloaded by 30 A*m^2 torque rods, a 2.5 m^2 array "
        "and 700 Wh battery. Starts Sun-safe pointing. Drag+SRP enabled.",
        _build_smallsat_300,
    ),
    SpacecraftTemplate(
        "Small satellite (500 kg)",
        "500 kg, 1.2 x 1.2 x 1.6 m. Star tracker, IMU, sun sensor, three 25 N*m*s wheels unloaded by 50 A*m^2 torque rods, a 4 m^2 array "
        "and 1.2 kWh battery. Starts Sun-safe pointing. Drag+SRP enabled.",
        _build_smallsat_500,
    ),
]
