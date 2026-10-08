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

"""Every numeric and on/off setting of a scenario, as wizard pages.

A real user found the template "Customize" wizards "very incomplete":
each exposed a hand-picked handful of fields (5-20% of its template's
settings -- template 05's offered no correction window and nothing at
all for the chief). The curated pages stay as the first, "key settings"
part of each wizard; :func:`build_all_settings_pages` then generates the
rest from the scenario itself, so every setting the template contains is
reachable, grouped by spacecraft and component (orbit, station-keeping,
phasing, sensors and actuators, ...).

A setting is addressed by its path in ``Scenario.to_dict()`` (a tuple of
attribute names, dict keys and list indices), which is also how the
scenario file stores it. Numeric vectors are offered one component at a
time. Text settings (names, the epoch, mode names) are not offered: they
need the full editor, which validates them in context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Union

from ..schema.scenario import Scenario

Path = Tuple[Union[str, int], ...]


@dataclass(frozen=True)
class SettingMeta:
    label: str
    suffix: str = ""
    help: str = ""


# Keyed by the setting's own name (the last path element). Units follow
# the schema's own field comments.
_META: Dict[str, SettingMeta] = {
    # Orbit
    "semi_major_axis_km": SettingMeta("Semi-major axis", " km", "Measured from the central body's centre."),
    "eccentricity": SettingMeta("Eccentricity"),
    "inclination_deg": SettingMeta("Inclination", " deg"),
    "raan_deg": SettingMeta("Right ascension of the ascending node", " deg"),
    "arg_periapsis_deg": SettingMeta("Argument of periapsis", " deg"),
    "true_anomaly_deg": SettingMeta("True anomaly at epoch", " deg"),
    "mean_anomaly_deg": SettingMeta("Mean anomaly at epoch", " deg"),
    # Mass, environment
    "dry_mass_kg": SettingMeta("Dry mass", " kg"),
    "inertia_kg_m2": SettingMeta("Inertia", " kg*m^2", "Body-frame inertia tensor about the centre of mass."),
    "drag_area_m2": SettingMeta("Drag area", " m^2"),
    "drag_coeff": SettingMeta("Drag coefficient"),
    "srp_area_m2": SettingMeta("Solar radiation pressure area", " m^2"),
    "srp_coeff": SettingMeta("Solar radiation pressure coefficient"),
    # Facets (FacetConfig)
    "normal_b": SettingMeta("Outward normal", "", "Body-frame direction the facet faces (normalized)."),
    "location_b": SettingMeta("Centre of pressure", " m", "Where the facet's force acts, from the body origin."),
    "specular_coeff": SettingMeta("Specular reflection", "", "Fraction of sunlight reflected mirror-like."),
    "diffuse_coeff": SettingMeta("Diffuse reflection", "", "Fraction of sunlight reflected diffusely."),
    "enable_drag": SettingMeta("Atmospheric drag"),
    "enable_srp": SettingMeta("Solar radiation pressure"),
    "enable_gravity_gradient": SettingMeta("Gravity-gradient torque"),
    "sigma_bn_init": SettingMeta("Initial attitude (MRP)", "", "Modified Rodrigues parameters, body vs inertial."),
    "omega_bn_b_init_rad_s": SettingMeta("Initial body rate", " rad/s"),
    "vizard_model_offset_m": SettingMeta("Vizard model offset", " m"),
    "vizard_model_rotation_deg": SettingMeta("Vizard model rotation", " deg"),
    "vizard_model_scale": SettingMeta("Vizard model scale"),
    # Station-keeping
    "target_altitude_km": SettingMeta("Target altitude", " km"),
    "deadband_km": SettingMeta("Deadband", " km", "How far below the target altitude a reboost starts."),
    "thrust_n": SettingMeta("Thrust", " N"),
    "isp_s": SettingMeta("Specific impulse", " s"),
    "propellant_kg": SettingMeta("Propellant", " kg", "Shared with phasing burns on the same spacecraft."),
    "eclipse_sunlit_threshold": SettingMeta("Sunlit threshold", "", "Illumination fraction above which "
                                            "the thruster may fire (eclipse gating)."),
    "min_on_time_s": SettingMeta("Minimum thruster on-time", " s", "0 = an ideal thruster."),
    "eccentricity_neutral_burns": SettingMeta("Eccentricity-neutral burns", "", "Gate firings so an "
                                              "eclipse-interrupted reboost doesn't change the eccentricity."),
    # Phasing keeping
    "target_separation_km": SettingMeta("Target separation", " km", "Along-track distance ahead of the chief."),
    "reconfiguration_interval_days": SettingMeta("Reconfiguration interval", " days",
                                                 "Only used with more than one target separation."),
    "tolerance_fraction": SettingMeta("Tolerance (fraction of target)", "", "Error that triggers a correction."),
    "restore_tolerance_fraction": SettingMeta("Restore tolerance (fraction of target)", "",
                                              "How close counts as 'arrived'."),
    "correction_window_days": SettingMeta("Correction window", " days", "How long a correction takes: "
                                          "shorter is faster but uses more delta-V (roughly 1 / window)."),
    "max_drift_days": SettingMeta("Maximum drift time", " days"),
    "max_delta_semi_major_axis_km": SettingMeta("Maximum drift-orbit offset", " km"),
    # Momentum management, fuel tank, power, comms
    "hs_max": SettingMeta("Momentum dump threshold", " N*m*s"),
    "max_counter_value": SettingMeta("Dump cycle length (control steps)"),
    "thr_min_fire_time": SettingMeta("Minimum thruster firing time", " s"),
    "c_gain": SettingMeta("Momentum-management gain"),
    "wheel_speed_biases_rad_s": SettingMeta("Wheel speed bias", " rad/s"),
    "propellant_mass_kg": SettingMeta("Propellant mass", " kg"),
    "max_propellant_mass_kg": SettingMeta("Tank capacity", " kg"),
    "tank_position_b_m": SettingMeta("Tank position (body frame)", " m"),
    "battery_capacity_wh": SettingMeta("Battery capacity", " W*h"),
    "battery_initial_soc": SettingMeta("Initial state of charge", "", "Fraction of capacity, 0-1."),
    "bus_idle_power_w": SettingMeta("Bus idle power", " W"),
    "panel_area_m2": SettingMeta("Solar panel area", " m^2"),
    "panel_efficiency": SettingMeta("Solar panel efficiency"),
    "panel_normal_b": SettingMeta("Solar panel normal (body frame)"),
    "antenna_boresight_b": SettingMeta("Antenna boresight (body frame)"),
    "comms_power_w": SettingMeta("Comms power", " W"),
    "antenna_beamwidth_deg": SettingMeta("Antenna beamwidth", " deg"),
    "data_rate_bps": SettingMeta("Data rate", " bit/s"),
    "frequency_hz": SettingMeta("Frequency", " Hz"),
    "implementation_loss_db": SettingMeta("Implementation loss", " dB"),
    "required_ebno_db": SettingMeta("Required Eb/N0", " dB"),
    "tx_antenna_gain_dbi": SettingMeta("Transmit antenna gain", " dBi"),
    "tx_power_w": SettingMeta("Transmit power", " W"),
    # Attitude control
    "K": SettingMeta("Attitude gain K"),
    "P": SettingMeta("Rate gain P"),
    "pHat_B": SettingMeta("Pointing axis (body frame)"),
    "sHatBdyCmd": SettingMeta("Commanded Sun direction (body frame)"),
    "sigma_R0N": SettingMeta("Reference attitude (MRP)"),
    "use_css_estimation": SettingMeta("Estimate Sun heading from coarse sun sensors"),
    # Device parameters not covered by the editor's own descriptions
    "Omega": SettingMeta("Initial wheel speed", " RPM"),
    "maxMomentum": SettingMeta("Maximum wheel momentum", " N*m*s"),
    "motor_thermal_ambient_temp_c": SettingMeta("Motor ambient temperature", " C"),
    "initial_temp_c": SettingMeta("Initial temperature", " C"),
    "mass_kg": SettingMeta("Mass", " kg"),
    "emissivity": SettingMeta("Emissivity"),
    "specific_heat_j_kg_k": SettingMeta("Specific heat", " J/(kg*K)"),
    "power_draw_w": SettingMeta("Power draw", " W"),
    "measurement_noise_std_c": SettingMeta("Measurement noise (1-sigma)", " C"),
    # Ground stations
    "latitude_deg": SettingMeta("Latitude", " deg"),
    "longitude_deg": SettingMeta("Longitude", " deg"),
    "altitude_m": SettingMeta("Altitude", " m"),
    "min_elevation_deg": SettingMeta("Minimum elevation", " deg"),
    "rx_antenna_gain_dbi": SettingMeta("Receive antenna gain", " dBi"),
    "system_noise_temp_k": SettingMeta("System noise temperature", " K"),
    # Mission sequence
    "delta_v_m_s": SettingMeta("Delta-V", " m/s"),
    "duration_days": SettingMeta("Duration", " days"),
    "max_distance_target_m": SettingMeta("Arrival tolerance", " m"),
    "min_orbit_radius_m": SettingMeta("Minimum orbit radius", " m"),
    "target_position_m": SettingMeta("Target position", " m"),
    "time_of_flight_s": SettingMeta("Time of flight", " s"),
    # Monte Carlo, environment, simulation
    "mean": SettingMeta("Mean"),
    "std_deviation": SettingMeta("Standard deviation"),
    "bounds": SettingMeta("Bounds"),
    "enabled": SettingMeta("Enabled"),
    "num_runs": SettingMeta("Number of runs"),
    "thread_count": SettingMeta("Parallel threads"),
    "verbose": SettingMeta("Verbose output"),
    "central_body_degree": SettingMeta("Spherical-harmonics degree", "", "0 = point-mass gravity."),
    "activity_percentile": SettingMeta("Space-weather activity percentile"),
    "dynamics_task_rate_s": SettingMeta("Integration time step", " s", "Too coarse a step can make the "
                                        "dynamics diverge (NaN); keep the template's value unless you know why."),
}

# Optional per-spacecraft blocks, in page order.
_BLOCK_TITLES = {
    "station_keeping": "station-keeping",
    "phasing_keeping": "phasing keeping",
    "constant_thrust": "constant thrust",
    "momentum_dumping": "momentum dumping",
    "magnetic_momentum_management": "magnetic momentum management",
    "fuel_tank": "fuel tank",
    "power": "power",
    "comms_pointing": "comms pointing",
    "rf_link": "RF link",
}
_ATTITUDE_KEYS = {"fsw_params", "control_params", "sigma_bn_init", "omega_bn_b_init_rad_s"}
_SKIPPED_TOP_LEVEL = {"schema_version"}


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _leaf_settings(obj, path: Path = ()) -> List[Tuple[Path, object]]:
    """Every numeric or bool leaf under ``obj`` (an ``asdict`` tree), with
    numeric vectors expanded into one entry per component."""
    out: List[Tuple[Path, object]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not path and key in _SKIPPED_TOP_LEVEL:
                continue
            out.extend(_leaf_settings(value, path + (key,)))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            out.extend(_leaf_settings(value, path + (index,)))
    elif isinstance(obj, bool) or _is_number(obj):
        out.append((path, obj))
    return out


def setting_paths(scenario: Scenario) -> List[Path]:
    """Every adjustable numeric/bool setting in ``scenario``."""
    return [path for path, _ in _leaf_settings(scenario.to_dict())]


def get_setting(scenario: Scenario, path: Path):
    obj = scenario
    for key in path:
        obj = obj[key] if isinstance(obj, (dict, list)) else getattr(obj, key)
    return obj


def set_setting(scenario: Scenario, path: Path, value) -> None:
    obj = get_setting(scenario, path[:-1])
    key = path[-1]
    if isinstance(obj, (dict, list)):
        obj[key] = value
    else:
        setattr(obj, key, value)


def name_is_inertia(path: Path) -> bool:
    return _setting_name(path) == "inertia_kg_m2"


def _setting_name(path: Path) -> str:
    """The setting's own name: the last string element (a vector
    component's name is its vector's)."""
    return next(key for key in reversed(path) if isinstance(key, str))


def _component(path: Path, scenario: Scenario) -> Tuple[str, bool]:
    """(component name, shares a row with its siblings) for a numeric
    vector component, ('', False) for a scalar: 'x'/'y'/'z' for a
    3-vector (one row), 'Ixy' etc. for an inertia tensor, '[2]' otherwise."""
    if not isinstance(path[-1], int):
        return "", False
    vector = get_setting(scenario, path[:-1])
    if not isinstance(vector, list) or not all(_is_number(v) for v in vector):
        return "", False
    index = path[-1]
    if _setting_name(path) == "inertia_kg_m2" and len(vector) == 9:
        return f"I{'xyz'[index // 3]}{'xyz'[index % 3]}", True
    if len(vector) == 3:
        return "xyz"[index], True
    return f"[{index + 1}]", False


def _device_param_label(kind: str, key: str) -> Tuple[str, str]:
    """(label, help) for a sensor/actuator params key, preferring the
    editor's own per-kind description."""
    from .sensor_actuator_editor import _KIND_PARAM_SPECS

    meta = _META.get(key)
    for spec in _KIND_PARAM_SPECS.get(kind, []):
        if spec.key == key:
            if meta:
                return meta.label, meta.suffix, spec.help_text
            # "spin-axis direction, body frame, unit vector [-] -- ..." ->
            # label "Spin-axis direction", no unit; "max wheel speed [RPM]" ->
            # "Max wheel speed", " RPM".
            first = spec.help_text.split(" -- ")[0]
            unit = first[first.rfind("[") + 1:first.rfind("]")] if "[" in first else ""
            short = first.split("[")[0].split(",")[0].strip()
            return short[:1].upper() + short[1:], ("" if unit in ("", "-") else f" {unit}"), spec.help_text
    return (meta.label if meta else key), (meta.suffix if meta else ""), (meta.help if meta else "")


def _page_and_label(path: Path, scenario: Scenario) -> Tuple[str, str, str, str, str]:
    """(page title, group sub-heading, field label, unit suffix, help) for
    one setting. A spacecraft's page titles are "<spacecraft>: <section>"."""
    name = _setting_name(path)
    meta = _META.get(name, SettingMeta(name.replace("_", " ").capitalize()))
    label, suffix, help_text = meta.label, meta.suffix, meta.help
    group = ""
    head = path[0]
    if head == "spacecraft":
        craft = scenario.spacecraft[path[1]]
        part = path[2]
        if part == "orbit":
            page = f"{craft.name}: orbit"
        elif part in ("sensors", "actuators"):
            device = getattr(craft, part)[path[3]]
            label, suffix, help_text = _device_param_label(device.kind, name)
            group = f"{device.name} ({device.kind.replace('_', ' ')})"
            page = f"{craft.name}: sensors & actuators"
        elif part == "facets":
            facet = craft.facets[path[3]]
            group = facet.name
            if name == "area_m2":
                label, suffix = "Area", " m^2"
            page = f"{craft.name}: surface facets"
        elif part in _ATTITUDE_KEYS:
            page = f"{craft.name}: attitude"
        elif part in _BLOCK_TITLES:
            page = f"{craft.name}: {_BLOCK_TITLES[part]}"
        elif part.startswith("vizard_model"):
            page = f"{craft.name}: Vizard model"
        else:
            page = f"{craft.name}: mass & environment"
    elif head == "ground_stations":
        page = "Ground stations"
        group = scenario.ground_stations[path[1]].name
    elif head == "mission_sequence":
        page = "Mission sequence"
        command_path = path[:max(i for i, key in enumerate(path) if key == "params")]
        command = get_setting(scenario, command_path) if "params" in path else None
        if command is not None:
            group = command.label or command.kind
    elif head == "monte_carlo":
        page = "Monte Carlo"
        if len(path) > 2 and path[1] == "dispersions":
            dispersion = scenario.monte_carlo.dispersions[path[2]]
            group = f"Dispersion: {dispersion.spacecraft} {dispersion.quantity}"
    else:
        page = "Environment & simulation"
    return page, group, label, suffix, help_text


def build_all_settings_pages(scenario: Scenario, exclude=frozenset()):
    """Wizard pages covering every setting of ``scenario`` not in
    ``exclude`` (paths already offered by a curated page), in scenario
    order: each spacecraft's pages, then ground stations, mission
    sequence, Monte Carlo and the environment/simulation settings."""
    from .template_wizard import WizardField, WizardPageSpec

    pages: Dict[str, List[WizardField]] = {}
    for path, value in _leaf_settings(scenario.to_dict()):
        if path in exclude or path[:-1] in exclude:
            continue
        if (path[0] == "spacecraft" and str(path[2]).startswith("vizard_model")
                and scenario.spacecraft[path[1]].vizard_model_path is None):
            continue  # no effect without a Vizard model
        page, group, label, suffix, help_text = _page_and_label(path, scenario)
        component, shares_row = _component(path, scenario)
        if component and not shares_row:
            label = f"{label} {component}"
        row_key = repr(path[:-1])
        if shares_row and name_is_inertia(path):  # a 3x3 tensor: one row per tensor row
            row_key += str(path[-1] // 3)
            label = f"{label} ({'xyz'[path[-1] // 3]} row)"
        kind = "bool" if isinstance(value, bool) else ("int" if isinstance(value, int) else "float")
        tooltip = (help_text + "\n\n" if help_text else "") + "Scenario setting: " + ".".join(
            f"[{key}]" if isinstance(key, int) else key for key in path).replace(".[", "[")
        pages.setdefault(page, []).append(WizardField(
            label, tooltip,
            (lambda s, p=path: get_setting(s, p)),
            (lambda s, v, p=path: set_setting(s, p, v)),
            -1.0e15, 1.0e15, decimals=0 if kind == "int" else 3, step=1.0, suffix=suffix, kind=kind,
            help_inline=False, group=group,
            vector_key=row_key if shares_row else "", component=component if shares_row else "",
        ))
    def rank(title: str) -> int:  # spacecraft first, then the scenario-wide sections
        for order, prefix in enumerate(("Ground stations", "Mission sequence", "Monte Carlo",
                                        "Environment & simulation"), start=1):
            if title == prefix:
                return order
        return 0

    titles = sorted(pages, key=rank)  # stable: scenario order within each rank
    return [WizardPageSpec(title=title, intro="", fields=pages[title]) for title in titles]


def vizard_model_settings_hidden(scenario: Scenario) -> List[Path]:
    """Vizard model offset/rotation/scale paths left off the generated
    pages because that spacecraft has no Vizard model (they'd do nothing)."""
    return [path for path in setting_paths(scenario)
            if path[0] == "spacecraft" and str(path[2]).startswith("vizard_model")
            and scenario.spacecraft[path[1]].vizard_model_path is None]
