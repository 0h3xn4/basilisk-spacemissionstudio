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

"""Environment constants and checks (ECSS-E-ST-10-04C 4.2.1b, 6.2.1a;
remediation R06).

The Table 6-2 values are 1361 W/m^2 at 1 AU, 1316 W/m^2 at aphelion and
1407 W/m^2 at perihelion. The sensorThermal checks measure Basilisk's own
constants from equilibrium temperatures, so a Basilisk release that
changes them fails here.
"""

import math

import numpy as np
import pytest

from spacemissionstudio.engine import environment_models as env

pytestmark = pytest.mark.requirement("E-ST-10-04C 6.2.1a", "E-ST-10-04C 4.2.1b")

_AU_M = 149597870700.0  # [m]


def test_solar_flux_follows_table_6_2():
    """1361 W/m^2 at 1 AU; near perihelion (early January) and aphelion
    (early July) the 1/r^2 flux matches Table 6-2's 1407 and 1316 W/m^2."""
    assert env.TOTAL_SOLAR_IRRADIANCE_W_M2 == 1361.0  # [W/m^2]
    assert env.solar_flux_w_m2("2026-01-03T12:00:00") == pytest.approx(1407.0, abs=2.0)  # [W/m^2]
    assert env.solar_flux_w_m2("2026-07-04T12:00:00") == pytest.approx(1316.0, abs=2.0)  # [W/m^2]


@pytest.mark.requires_basilisk
def test_sun_distance_matches_de430():
    """The almanac formula agrees with the DE430 Earth-Sun distance to
    2e-4 AU (0.04 % in flux) across a year."""
    from Basilisk.topLevelModules import pyswice
    from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

    from spacemissionstudio.engine.time_system import utc_iso_to_spice_string

    for kernel in (DataFile.EphemerisData.naif0012, DataFile.EphemerisData.de430):
        pyswice.furnsh_c(str(get_path(kernel)))
    for month in range(1, 13):
        epoch = f"2027-{month:02d}-15T00:00:00"
        et = pyswice.new_doubleArray(1)
        pyswice.str2et_c(utc_iso_to_spice_string(epoch), et)
        position = pyswice.new_doubleArray(3)
        light_time = pyswice.new_doubleArray(1)
        pyswice.spkpos_c("SUN", pyswice.doubleArray_getitem(et, 0), "J2000", "NONE", "EARTH", position,
                         light_time)
        distance_au = np.linalg.norm([pyswice.doubleArray_getitem(position, i) for i in range(3)]) * 1e3 / _AU_M
        assert env.sun_distance_au(epoch) == pytest.approx(distance_au, abs=2e-4)


def test_thermal_inputs_reproduce_the_standard_heat_balance():
    """The scaled inputs give, in Basilisk's own equation (1366 W/m^2,
    sigma 5.76051e-8), the same heat flows as the standard constants, also
    when the absorptivity would exceed 1 (common scale factor)."""
    for alpha, eps, flux in ((0.3, 0.8, 1361.0), (1.0, 0.9, 1407.0), (0.95, 1.0, 1316.0)):
        corrected = env.sensor_thermal_inputs(alpha, eps, 5.0, 2.0, flux)
        assert 0.0 < corrected.absorptivity <= 1.0 and 0.0 < corrected.emissivity <= 1.0
        k = corrected.scale
        assert corrected.absorptivity * env.BASILISK_SENSOR_THERMAL_FLUX_W_M2 == pytest.approx(k * alpha * flux)
        assert corrected.emissivity * env.BASILISK_SENSOR_THERMAL_SIGMA_W_M2_K4 == pytest.approx(
            k * eps * env.STEFAN_BOLTZMANN_W_M2_K4)
        assert corrected.power_draw_w == pytest.approx(k * 5.0) and corrected.mass_kg == pytest.approx(k * 2.0)
    assert env.sensor_thermal_inputs(1.0, 0.9, 0.0, 1.0, 1407.0).scale < 1.0  # alpha 1 at perihelion


def _basilisk_equilibrium_k(n_hat, absorptivity, emissivity, power_w, mass_kg, sun_distance_m):
    from Basilisk.architecture import messaging
    from Basilisk.simulation import sensorThermal
    from Basilisk.utilities import SimulationBaseClass, macros

    sim = SimulationBaseClass.SimBaseClass()
    sim.CreateNewProcess("p").addTask(sim.CreateNewTask("t", macros.sec2nano(0.5)))
    sun = messaging.SpicePlanetStateMsgPayload()
    sun.PositionVector = [sun_distance_m, 0.0, 0.0]
    sun_msg = messaging.SpicePlanetStateMsg().write(sun)
    sc = messaging.SCStatesMsgPayload()
    sc_msg = messaging.SCStatesMsg().write(sc)
    mod = sensorThermal.SensorThermal()
    mod.nHat_B = n_hat
    mod.sensorArea = 1.0  # [m^2]
    mod.sensorAbsorptivity, mod.sensorEmissivity = absorptivity, emissivity
    mod.sensorMass, mod.sensorSpecificHeat = mass_kg, 100.0  # [kg], [J/kg/K]
    mod.T_0 = 20.0  # [C]
    mod.sensorPowerDraw = power_w
    mod.sensorPowerStatus = 1
    mod.sunInMsg.subscribeTo(sun_msg)
    mod.stateInMsg.subscribeTo(sc_msg)
    sim.AddModelToTask("t", mod)
    recorder = mod.temperatureOutMsg.recorder()
    sim.AddModelToTask("t", recorder)
    sim.InitializeSimulation()
    sim.ConfigureStopTime(macros.sec2nano(4000.0))
    sim.ExecuteSimulation()
    return recorder.temperature[-1] + 273.15  # [K]


@pytest.mark.requires_basilisk
def test_basilisk_2_12_sensor_thermal_constants_are_as_documented():
    """Equilibrium temperatures of Basilisk's sensorThermal give sigma =
    5.76051e-8 W/m^2/K^4 and 1366 W/m^2 at both 1 AU and 2 AU (no distance
    scaling) -- the constants engine.environment_models corrects for."""
    t_power = _basilisk_equilibrium_k([-1.0, 0.0, 0.0], 1.0, 1.0, 400.0, 1.0, _AU_M)
    sigma = 400.0 / t_power ** 4
    assert sigma == pytest.approx(env.BASILISK_SENSOR_THERMAL_SIGMA_W_M2_K4, rel=1e-5)
    for distance in (_AU_M, 2.0 * _AU_M):
        flux = sigma * _basilisk_equilibrium_k([1.0, 0.0, 0.0], 1.0, 1.0, 0.0, 1.0, distance) ** 4
        assert flux == pytest.approx(env.BASILISK_SENSOR_THERMAL_FLUX_W_M2, rel=1e-5)


@pytest.mark.requires_basilisk
def test_corrected_sensor_thermal_reaches_the_standard_equilibrium():
    """With the corrected inputs Basilisk's sensorThermal settles at the
    temperature the Table 6-2 flux and the CODATA sigma give:
    T^4 = (alpha F + P) / (eps sigma), here at perihelion with alpha = 1."""
    alpha, eps, power, flux = 1.0, 0.85, 50.0, 1407.0
    corrected = env.sensor_thermal_inputs(alpha, eps, power, 1.0, flux)
    temperature = _basilisk_equilibrium_k([1.0, 0.0, 0.0], corrected.absorptivity, corrected.emissivity,
                                          corrected.power_draw_w, corrected.mass_kg, _AU_M)
    expected = ((alpha * flux + power) / (eps * env.STEFAN_BOLTZMANN_W_M2_K4)) ** 0.25  # [K]
    assert temperature == pytest.approx(expected, abs=0.01)  # [K]


def test_gravity_truncation_estimate():
    """A point mass leaves out the J2 acceleration (~1e-2 m/s^2 in LEO);
    the estimate falls with degree and with altitude, and degree_for
    inverts it."""
    leo = 6378136.3 + 500e3  # [m]
    assert env.gravity_truncation_acceleration(0, leo) == pytest.approx(
        3.0 * 1.08263e-3 * 3.986004415e14 / leo ** 2 * (6378136.3 / leo) ** 2, rel=1e-3)
    values = [env.gravity_truncation_acceleration(n, leo) for n in (2, 10, 30, 70)]
    assert values == sorted(values, reverse=True)
    assert env.gravity_truncation_acceleration(10, 42164e3) < env.gravity_truncation_acceleration(10, leo) * 1e-6
    target = 3e-8  # [m/s^2]
    degree = env.degree_for(leo, target)
    assert env.gravity_truncation_acceleration(degree, leo) <= target < env.gravity_truncation_acceleration(
        degree - 1, leo)
    assert env.srp_acceleration(1.0, 1.0, 1.0, 1361.0) == pytest.approx(1361.0 / 299792458.0)
    assert math.isfinite(env.gravity_truncation_acceleration(180, 6378136.3 + 200e3))


def test_point_mass_with_drag_is_a_warning_and_srp_fidelity_a_note():
    """Drag around a point-mass Earth is a warning; a field that leaves out
    more than SRP is an Explain-tab note naming the degree that would match."""
    from spacemissionstudio.engine.scenario_checks import gravity_fidelity_notes, scenario_warnings
    from spacemissionstudio.schema.scenario import GravityConfig, OrbitIC, Scenario, SpacecraftConfig

    orbit = OrbitIC(type="classical_elements", semi_major_axis_km=6878.1366, eccentricity=0.001,
                    inclination_deg=97.4, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0)
    sc = SpacecraftConfig(name="sat", orbit=orbit, enable_drag=True, enable_srp=True)
    point_mass = Scenario(name="t", epoch_utc="2027-01-01T00:00:00", spacecraft=[sc],
                          gravity=GravityConfig(central_body="earth", central_body_degree=0))
    assert any("point mass" in w for w in scenario_warnings(point_mass))
    degree_10 = Scenario(name="t", epoch_utc="2027-01-01T00:00:00", spacecraft=[sc],
                         gravity=GravityConfig(central_body="earth", central_body_degree=10))
    assert not any("point mass" in w for w in scenario_warnings(degree_10))
    notes = gravity_fidelity_notes(degree_10)
    assert len(notes) == 1 and notes[0].startswith("sat: gravity degree 10 leaves out") and "4.2.1b" in notes[0]


def test_gravity_degree_above_the_field_maximum_is_rejected_by_the_schema():
    """Degree 181 fails validation naming the field and the GGM03S limit,
    instead of failing inside Basilisk at run time."""
    from spacemissionstudio.schema.scenario import GravityConfig, ScenarioValidationError

    GravityConfig(central_body="earth", central_body_degree=180).validate()
    with pytest.raises(ScenarioValidationError, match="central_body_degree must be <= 180"):
        GravityConfig(central_body="earth", central_body_degree=181).validate()
