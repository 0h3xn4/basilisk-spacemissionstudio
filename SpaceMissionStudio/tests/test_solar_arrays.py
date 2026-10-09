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

"""Flexible solar arrays (SRS-F-09): the hinge geometry, inertia and
spring the configuration maps to, the schema's checks, and -- with
Basilisk -- the frequency, damping, sign, mass and power a run shows."""

import dataclasses
import json
import math

import numpy as np
import pytest

from spacemissionstudio.engine import solar_arrays
from spacemissionstudio.engine.scenario_explainer import explain
from spacemissionstudio.engine.series_names import expected_series_names
from spacemissionstudio.schema.scenario import (GeoStationKeepingConfig, GravityConfig, OrbitIC, PowerConfig, Scenario,
                                                ScenarioValidationError, SimSettings, SolarArrayConfig,
                                                SpacecraftConfig, StationKeepingConfig)


def _wing(name="wing+y", sign=1.0, **overrides):
    values = dict(name=name, mass_kg=5.0, span_m=1.2, width_m=0.6, hinge_position_b=[0.0, 0.4 * sign, 0.0],
                  deploy_direction_b=[0.0, sign, 0.0], normal_b=[0.0, 0.0, 1.0], first_mode_hz=1.0,
                  damping_ratio=0.02)  # [kg], [m], [m], [m], [Hz], [-]
    values.update(overrides)
    return SolarArrayConfig(**values)


def _scenario(arrays, **settings):
    orbit = OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0, inclination_deg=97.6,
                    raan_deg=48.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0)  # [km], [deg]
    sc = SpacecraftConfig(name="sat", orbit=orbit, dry_mass_kg=150.0,
                          inertia_kg_m2=[20.5, 0, 0, 0, 20.5, 0, 0, 0, 16.0], solar_arrays=arrays)  # [kg], [kg*m^2]
    return Scenario(name="flex", epoch_utc="2030-01-01T08:30:00", spacecraft=[sc],
                    gravity=GravityConfig(central_body="earth"),
                    sim_settings=SimSettings(**{"duration_days": 0.01, **settings}))


# -- what the configuration maps to -------------------------------------------------

def test_the_hinge_frame_puts_the_hinge_along_both_faces_common_edge():
    """h1 points back from the tip, h3 is the cell-side normal, h2 = h3 x h1
    is the hinge line; a right-handed orthonormal frame."""
    dcm = solar_arrays.dcm_hb(_wing())
    assert dcm @ dcm.T == pytest.approx(np.eye(3))
    assert np.linalg.det(dcm) == pytest.approx(1.0)
    assert dcm[0] == pytest.approx([0.0, -1.0, 0.0])  # h1 = -deploy direction
    assert dcm[1] == pytest.approx([1.0, 0.0, 0.0])  # hinge line along +x
    assert dcm[2] == pytest.approx([0.0, 0.0, 1.0])  # h3 = normal


def test_the_hinge_spring_and_damper_give_the_configured_mode():
    """With the hub held fixed: sqrt(k / J) = 2 pi f and c / (2 sqrt(k J)) = zeta,
    J being the plate's inertia about its hinge line."""
    wing = _wing(first_mode_hz=0.4, damping_ratio=0.03)
    j = 5.0 * 1.2 ** 2 / 12.0 + 5.0 * 0.6 ** 2  # [kg*m^2] about the centre, plus m d^2
    assert solar_arrays.hinge_inertia_kg_m2(wing) == pytest.approx(j)
    k, c = solar_arrays.hinge_stiffness_damping(wing)
    assert math.sqrt(k / j) == pytest.approx(2.0 * math.pi * 0.4)
    assert c / (2.0 * math.sqrt(k * j)) == pytest.approx(0.03)


def test_the_flight_software_inertia_adds_each_undeflected_array_about_the_body_origin():
    """A 5 kg, 1.2 x 0.6 m wing centred 1.0 m out along +y, by hand."""
    scenario = _scenario([_wing()])
    inertia = np.asarray(solar_arrays.fsw_inertia_kg_m2(scenario.spacecraft[0])).reshape(3, 3)
    m, length, width, r = 5.0, 1.2, 0.6, 1.0  # [kg], [m], [m], [m]
    assert inertia[0, 0] == pytest.approx(20.5 + m * length ** 2 / 12.0 + m * r ** 2)
    assert inertia[1, 1] == pytest.approx(20.5 + m * width ** 2 / 12.0)
    assert inertia[2, 2] == pytest.approx(16.0 + m * (length ** 2 + width ** 2) / 12.0 + m * r ** 2)
    assert inertia - np.diag(np.diag(inertia)) == pytest.approx(np.zeros((3, 3)), abs=1e-12)


def test_the_hub_carries_the_dry_mass_less_the_arrays_plus_every_propellant():
    """The same helper engine.service and engine.monte_carlo use. Monte
    Carlo's version used to leave out the GEO station-keeping propellant."""
    from spacemissionstudio.engine.monte_carlo import _propellant_offset_kg

    sc = _scenario([_wing(), _wing("wing-y", -1.0)]).spacecraft[0]
    sc.station_keeping = StationKeepingConfig(target_altitude_km=550.0, deadband_km=0.5, thrust_n=0.05,
                                              isp_s=220.0, propellant_kg=3.0)  # [km], [km], [N], [s], [kg]
    sc.geo_station_keeping = GeoStationKeepingConfig(target_longitude_deg=10.0, thrust_n=0.05, isp_s=220.0,
                                                     propellant_kg=2.0)  # [deg], [N], [s], [kg]
    assert solar_arrays.hub_mass_kg(sc) == pytest.approx(150.0 - 10.0 + 3.0 + 2.0)
    assert _propellant_offset_kg(sc) == pytest.approx(3.0 + 2.0 - 10.0)


# -- schema -----------------------------------------------------------------------------

def test_a_scenario_with_arrays_round_trips_through_json():
    scenario = _scenario([_wing(), _wing("wing-y", -1.0, generates_power=False, initial_deflection_deg=2.0)])
    scenario.validate()
    back = Scenario.from_dict(json.loads(json.dumps(dataclasses.asdict(scenario))))
    assert back.spacecraft[0].solar_arrays == scenario.spacecraft[0].solar_arrays


@pytest.mark.parametrize("change, message", [
    (lambda s: setattr(s.spacecraft[0].solar_arrays[0], "normal_b", [0.0, 1.0, 1.0]), "perpendicular"),
    (lambda s: setattr(s.spacecraft[0].solar_arrays[0], "mass_kg", 150.0), "dry_mass_kg is the whole"),
    (lambda s: setattr(s.spacecraft[0].solar_arrays[0], "first_mode_hz", 0.0), "first_mode_hz must be > 0"),
    (lambda s: setattr(s.spacecraft[0].solar_arrays[0], "damping_ratio", 1.0), r"damping_ratio must be in \[0, 1\)"),
    (lambda s: s.spacecraft[0].solar_arrays.append(_wing()), "names must be unique"),
    (lambda s: setattr(s.sim_settings, "integrator", "rk2"), "adaptive integrator"),
    (lambda s: setattr(s, "simulation_mode", "orbit_only"), "'orbit_only'"),
])
def test_bad_array_settings_are_refused_plainly(change, message):
    scenario = _scenario([_wing()])
    change(scenario)
    with pytest.raises(ScenarioValidationError, match=message):
        scenario.validate()


def test_the_explain_tab_warns_when_samples_alias_the_flexing():
    """A 1 Hz mode sampled every 1 s shows as a false slow oscillation."""
    section = next(s for s in explain(_scenario([_wing()])).sections if s.title == "Flexible solar arrays")
    assert section.notes == ["sat: 1 array, 5 kg, first mode from 1 Hz"]
    assert any(b.kind == "warning" for b in section.badges)
    fine = _scenario([_wing()], dynamics_task_rate_s=0.1)  # [s]
    section = next(s for s in explain(fine).sections if s.title == "Flexible solar arrays")
    assert not any(b.kind == "warning" for b in section.badges)


def test_predicted_series_include_each_array():
    scenario = _scenario([_wing()])
    scenario.spacecraft[0].power = PowerConfig(panel_area_m2=0.5, panel_efficiency=0.29)  # [m^2], [-]
    names = expected_series_names(scenario)
    for part in ("deflection", "deflection_rate", "power"):
        assert f"sat.solar_array.wing+y.{part}" in names


# -- in Basilisk ------------------------------------------------------------------------

def _run(scenario):
    from spacemissionstudio.engine.service import SimulationService

    service = SimulationService(scenario)
    return service, service.run()


@pytest.mark.requires_basilisk
def test_with_the_hub_held_fixed_the_array_rings_at_its_mode_and_damps_at_its_ratio():
    """An all but immovable hub (1e6 kg, 1e7 kg*m^2): released from 2 deg,
    the array oscillates at first_mode_hz and its log decrement gives
    damping_ratio, both within 1 %."""
    scenario = _scenario([_wing(first_mode_hz=0.8, damping_ratio=0.03, initial_deflection_deg=2.0)],
                         duration_days=30.0 / 86400.0, dynamics_task_rate_s=0.02)  # [day], [s]
    sc = scenario.spacecraft[0]
    sc.dry_mass_kg = 1.0e6  # [kg]
    sc.inertia_kg_m2 = [1.0e7, 0, 0, 0, 1.0e7, 0, 0, 0, 1.0e7]  # [kg*m^2]
    _service, result = _run(scenario)
    series = result.series["sat.solar_array.wing+y.deflection"]
    theta, t = series.data[:, 0], series.time_s
    peaks = [i for i in range(1, len(theta) - 1) if theta[i - 1] < theta[i] >= theta[i + 1] and theta[i] > 0]
    period = np.mean(np.diff(t[peaks]))  # [s]
    omega_d = 2.0 * math.pi / period  # [rad/s] damped
    decrement = np.mean(np.log(theta[peaks][:-1] / theta[peaks][1:]))
    zeta = decrement / math.sqrt(4.0 * math.pi ** 2 + decrement ** 2)
    omega_n = omega_d / math.sqrt(1.0 - zeta ** 2)
    assert theta[0] == pytest.approx(math.radians(2.0))
    assert omega_n / (2.0 * math.pi) == pytest.approx(0.8, rel=0.01)
    assert zeta == pytest.approx(0.03, rel=0.01)


@pytest.mark.requires_basilisk
def test_a_positive_deflection_turns_the_tip_toward_the_cell_side_and_the_mass_adds_up():
    """The sign the schema documents, read off Basilisk's own panel state
    (its centre of mass, 0.6 m out, rises by 0.6 sin(theta) toward the
    normal); and the spacecraft's total mass is still dry_mass_kg."""
    from Basilisk.utilities import RigidBodyKinematics as rbk

    from spacemissionstudio.engine.service import SimulationService

    scenario = _scenario([_wing(initial_deflection_deg=30.0)], duration_days=0.2 / 86400.0,
                         dynamics_task_rate_s=0.1)  # [day], [s]
    service = SimulationService(scenario)
    service.build(initialize=False)
    handle = service.spacecraft_handles["sat"]
    effector = next(e for e in handle.solar_arrays.effectors if hasattr(e, "hingedRigidBodyOutMsg"))
    panel_log = effector.hingedRigidBodyConfigLogOutMsg.recorder()  # the message is written only when linked
    hub_log = handle.sc_object.scStateOutMsg.recorder()
    for recorder in (panel_log, hub_log):
        service.scSim.AddModelToTask(service.dyn_task_name, recorder)
    service.scSim.InitializeSimulation()
    result = service.run()
    theta = result.series["sat.solar_array.wing+y.deflection"].data[0, 0]  # [rad]
    offset_n = np.asarray(panel_log.r_BN_N)[0] - np.asarray(hub_log.r_BN_N)[0]  # [m]
    centre_b = np.asarray(rbk.MRP2C(np.asarray(hub_log.sigma_BN)[0])) @ offset_n
    assert theta == pytest.approx(math.radians(30.0))
    assert centre_b == pytest.approx([0.0, 0.4 + 0.6 * math.cos(theta), 0.6 * math.sin(theta)], abs=1e-6)
    assert handle.sc_object.scMassOutMsg.read().massSC == pytest.approx(150.0)  # [kg]


@pytest.mark.requires_basilisk
def test_an_array_generates_power_facing_its_own_way():
    """Two wings with opposite cell sides on an uncontrolled hub: neither
    exceeds area x efficiency x solar flux, and together they charge the
    battery more than the body panel alone."""
    def run(arrays):
        scenario = _scenario(arrays, duration_days=0.02, dynamics_task_rate_s=1.0)  # [day], [s]
        scenario.gravity.third_body_perturbers = ["sun"]
        scenario.spacecraft[0].power = PowerConfig(panel_area_m2=0.2, panel_efficiency=0.29, bus_idle_power_w=0.0,
                                                   battery_capacity_wh=500.0, battery_initial_soc=0.5)
        return _run(scenario)[1]

    with_arrays = run([_wing(), _wing("wing-y", -1.0, normal_b=[0.0, 0.0, -1.0])])
    without = run([])
    ceiling_w = 1.2 * 0.6 * 0.29 * 1420.0  # [W] January flux is ~1408 W/m^2
    powers = [with_arrays.series[f"sat.solar_array.{n}.power"].data[:, 0] for n in ("wing+y", "wing-y")]
    assert all(p.max() <= ceiling_w and p.min() >= 0.0 for p in powers)
    assert max(p.max() for p in powers) > 0.0
    assert (with_arrays.series["sat.battery_charge"].data[-1, 0]
            > without.series["sat.battery_charge"].data[-1, 0])


@pytest.mark.requires_basilisk
def test_the_deflection_carries_across_long_run_segments(monkeypatch):
    """Two minutes in one run, then as two one-minute segments: the
    deflection at the end agrees."""
    from spacemissionstudio.engine import long_run

    def scenario():
        return _scenario([_wing(first_mode_hz=0.05, damping_ratio=0.01, initial_deflection_deg=5.0)],
                         duration_days=120.0 / 86400.0, dynamics_task_rate_s=0.5)  # [day], [s]

    single = _run(scenario())[1].series["sat.solar_array.wing+y.deflection"]
    monkeypatch.setattr(long_run, "SEGMENT_DAYS", 60.0 / 86400.0)  # [day]
    monkeypatch.setattr(SimSettings, "_MAX_SINGLE_RUN_DAYS", 60.0 / 86400.0)  # [day]
    split = _run(scenario())[1].series["sat.solar_array.wing+y.deflection"]
    assert split.time_s[-1] == pytest.approx(single.time_s[-1])
    assert split.data[-1, 0] == pytest.approx(single.data[-1, 0], abs=1e-6)  # [rad]
