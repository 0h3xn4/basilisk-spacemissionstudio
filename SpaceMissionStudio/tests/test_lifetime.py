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

"""Orbital lifetime (engine.lifetime). The Basilisk tests compare it with
full Basilisk decay runs of template 18's spacecraft."""

import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from spacemissionstudio.engine import lifetime
from spacemissionstudio.engine.facets import box_facets
from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

_TEMPLATES = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"


def _circular(altitude_km):
    return lifetime.MeanOrbit(lifetime.REQ_EARTH_M + altitude_km * 1e3, 0.0, math.radians(97.0), 0.0, 0.0)


def test_a_deorbit_burn_matches_the_vis_viva_equation():
    """Lowering a 550 km circular orbit's perigee to 250 km: vis-viva at
    apogee before and after gives 80.6 m/s; the lowered orbit has exactly
    that perigee and keeps its apogee."""
    orbit = _circular(550.0)
    delta_v, propellant, lowered = lifetime.deorbit_burn(orbit, 250.0, 122.0, 1500.0)  # [km], [kg], [s]
    r_apo, r_peri = orbit.semi_major_axis_m, lifetime.REQ_EARTH_M + 250e3  # [m]
    mu = lifetime.MU_EARTH_M3_S2
    expected = math.sqrt(mu / r_apo) - math.sqrt(mu * (2.0 / r_apo - 2.0 / (r_apo + r_peri)))  # [m/s]
    assert delta_v == pytest.approx(expected, rel=1e-9)
    assert lowered.perigee_altitude_km == pytest.approx(250.0, abs=1e-6)  # [km]
    assert lowered.apogee_altitude_km == pytest.approx(550.0, abs=1e-6)  # [km]
    assert propellant == pytest.approx(122.0 * (1.0 - math.exp(-delta_v / (1500.0 * 9.80665))))  # [kg]


def test_no_burn_is_needed_when_the_perigee_is_already_low_enough():
    assert lifetime.deorbit_burn(_circular(200.0), 250.0, 100.0, 1500.0)[:2] == (0.0, 0.0)


def test_facets_use_the_tumbling_average_area():
    """A convex body's mean projected area is a quarter of its surface."""
    spacecraft = SpacecraftConfig(name="s", orbit=OrbitIC(type="cartesian", position_km=[7000.0, 0.0, 0.0],
                                                          velocity_km_s=[0.0, 7.5, 0.0]),
                                  facets=box_facets((1.0, 2.0, 3.0)))  # [m]
    area, drag_coeff = lifetime.drag_properties(spacecraft)
    assert area == pytest.approx(2.0 * (1.0 * 2.0 + 2.0 * 3.0 + 1.0 * 3.0) / 4.0)  # [m^2]
    assert drag_coeff == pytest.approx(2.2)


def test_sidereal_angle_at_j2000_is_the_standard_value():
    assert math.degrees(lifetime._gmst_rad(datetime(2000, 1, 1, 12))) == pytest.approx(280.46061837)


def test_rule_checks_need_an_actual_reentry():
    result = lifetime.LifetimeResult(True, 4.0 * 365.25 * 86400.0, np.zeros(2), np.zeros(2), np.zeros(2),
                                     datetime(2030, 1, 1))
    assert result.meets(lifetime.ZERO_DEBRIS_YEARS) and result.reentry_utc.year == 2034
    result.reentered = False
    assert not result.meets(lifetime.IADC_YEARS) and result.reentry_utc is None


def _template_18(altitude_km, duration_days=1.0):
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(_TEMPLATES / "18_leo_station_keeping.json")
    scenario.spacecraft[0].orbit.semi_major_axis_km = lifetime.REQ_EARTH_M / 1e3 + altitude_km  # [km]
    scenario.spacecraft[0].station_keeping = None
    scenario.spacecraft[0].drag_coeff = 2.2  # [-] the figures quoted below (the template flies at 3.0)
    scenario.sim_settings.duration_days = duration_days  # [day]
    scenario.sim_settings.record_interval_s = 300.0  # [s]
    return scenario


@pytest.mark.requires_basilisk
@pytest.mark.requirement("E-ST-10-04C 7.2.1.1a")
def test_density_matches_the_simulations_own_atmosphere():
    """The standalone NRLMSISE-00 evaluator against the density a
    simulation of the same orbit feeds its drag model (within 1.4% in a
    real run; the rest is Earth's precession, ignored here)."""
    from Basilisk.utilities import macros

    from spacemissionstudio.engine import spaceweather
    from spacemissionstudio.engine.service import SimulationService

    scenario = _template_18(300.0)
    service = SimulationService(scenario)
    service.build()
    atmosphere = next(model for task in service.scSim.TaskList for model in task.TaskModels
                      if getattr(model, "ModelTag", "") == "msisAtmosphere")
    state = service.spacecraft_handles["leo-sat-1"].sc_object.scStateOutMsg.recorder()
    density = atmosphere.envOutMsgs[0].recorder()
    task = service.scSim.TaskList[0].Name
    service.scSim.AddModelToTask(task, state)
    service.scSim.AddModelToTask(task, density)
    service.scSim.InitializeSimulation()
    service.scSim.ConfigureStopTime(macros.sec2nano(6000.0))  # [s] about one orbit
    service.scSim.ExecuteSimulation()

    start = datetime(2030, 1, 1)
    weather = spaceweather.resolve("bundled", start, datetime(2031, 1, 1))
    evaluator = lifetime.MsisDensity(weather.path, start, points=1)
    times = state.times() * 1e-9  # [s]
    for k in range(0, len(times), 40):
        mine = evaluator(float(times[k]), state.r_BN_N[k:k + 1])[0]
        assert mine == pytest.approx(density.neutralDensity[k], rel=0.02)


@pytest.mark.requires_basilisk
def test_reentry_date_matches_a_basilisk_decay_run():
    """Template 18's spacecraft from 300 km with no station keeping: the
    estimate's re-entry (perigee at 120 km) within 3% of a full Basilisk
    run's (34.35 vs 34.04 days on MSFC's 2030 prediction: +0.9%; 25.7 days
    before the density used geodetic altitude, Phase 3 F-07). The run
    stops at re-entry with a warning."""
    from spacemissionstudio.engine.service import SimulationService

    scenario = _template_18(300.0, duration_days=40.0)  # [day]
    estimate = lifetime.spacecraft_lifetime(scenario, "leo-sat-1")
    result = SimulationService(scenario).run()

    sma = result.series["leo-sat-1.orbit_elements_mean.semi_major_axis"]
    ecc = result.series["leo-sat-1.orbit_elements_mean.eccentricity"].data[:, 0]
    perigee_km = (sma.data[:, 0] * (1.0 - ecc) - lifetime.REQ_EARTH_M) / 1e3
    with np.errstate(invalid="ignore"):
        basilisk_days = sma.time_s[np.argmax(perigee_km <= lifetime.REENTRY_ALTITUDE_KM)] / 86400.0
    assert estimate.reentered
    assert estimate.lifetime_s / 86400.0 == pytest.approx(basilisk_days, rel=0.03)
    assert any(w.startswith("leo-sat-1 re-entered: below 100 km") for w in result.warnings)


@pytest.mark.requires_basilisk
def test_end_of_run_lifetime_uses_the_final_state_and_the_propellant_left():
    """After a day of template 18 started 1.5 km low (station keeping
    burns), the lifetime starts a day later with less propellant aboard;
    a deorbit burn bigger than the tank lowers the perigee only as far as
    the propellant goes."""
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(_TEMPLATES / "18_leo_station_keeping.json")
    scenario.spacecraft[0].orbit.semi_major_axis_km -= 1.5  # [km]
    scenario.spacecraft[0].station_keeping.propellant_kg = 0.2  # [kg]
    scenario.sim_settings.duration_days = 1.0  # [day]
    run = SimulationService(scenario).run()
    left_kg = run.series["leo-sat-1.station_keeping.propellant_remaining"].data[-1, 0]  # [kg]
    assert left_kg < 0.2

    after = lifetime.end_of_life(scenario, "leo-sat-1", run, max_years=5.0)
    assert after.from_end_of_run and after.mass_kg == pytest.approx(120.0 + left_kg)  # [kg]
    assert after.lifetime.start_utc == datetime(2030, 1, 2)

    deorbit = lifetime.end_of_life(scenario, "leo-sat-1", run, deorbit_perigee_km=130.0, max_years=5.0).deorbit
    assert not deorbit.sufficient
    assert deorbit.propellant_kg == pytest.approx(left_kg)  # [kg] all of it
    assert 130.0 < deorbit.perigee_km < 400.0  # [km]


def test_the_exponential_atmosphere_is_flagged_as_too_thin():
    """Basilisk's exponential model is fitted at sea level: at 400 km it is
    ~1e9 times too thin for a lifetime."""
    from spacemissionstudio.schema.scenario import Scenario, SpaceWeatherConfig

    scenario = Scenario(name="e", epoch_utc="2030-01-01T00:00:00",
                        space_weather=SpaceWeatherConfig(atmosphere_model="exponential"),
                        spacecraft=[SpacecraftConfig(name="s", orbit=OrbitIC(
                            type="cartesian", position_km=[6778.0, 0.0, 0.0], velocity_km_s=[0.0, 7.67, 0.0]))])
    density, _years, warnings = lifetime.density_for_scenario(scenario, datetime(2030, 1, 1), 1.0)
    assert density is lifetime.exponential_density
    assert "far too thin" in warnings[0]
    assert density(0.0, np.array([[lifetime.REQ_EARTH_M + 400e3, 0.0, 0.0]]))[0] < 1e-20  # [kg/m^3]


@pytest.mark.requires_basilisk
def test_a_run_stops_cleanly_when_its_spacecraft_reenters(monkeypatch):
    """Template 18's spacecraft from 300 km asked to fly 60 days, split
    into 20-day segments: the run stops at re-entry (~34 days) with its
    results so far and a warning, rather than integrate on through the
    Earth until the state diverges and the whole run is lost."""
    from spacemissionstudio.engine import long_run
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.schema.scenario import SimSettings

    monkeypatch.setattr(long_run, "SEGMENT_DAYS", 20.0)  # [day]
    monkeypatch.setattr(SimSettings, "_MAX_SINGLE_RUN_DAYS", 20.0)  # [day]
    result = SimulationService(_template_18(300.0, duration_days=60.0)).run()  # [km], [day]

    end_days = result.series["leo-sat-1.position_N"].time_s[-1] / 86400.0
    assert 30.0 < end_days < 40.0
    reentries = [w for w in result.warnings if w.startswith("leo-sat-1 re-entered")]
    assert len(reentries) == 1 and reentries[0].endswith("the run stopped there")
    altitude_km = (np.linalg.norm(result.series["leo-sat-1.position_N"].data[-1]) - lifetime.REQ_EARTH_M) / 1e3
    assert 0.0 < altitude_km < 200.0  # [km] stopped near the ground, not inside it


@pytest.mark.requires_basilisk
def test_the_held_orbit_sits_at_the_station_keeping_target():
    """Station keeping holds the mean radius at Req + target (400.3 km in
    the five-year runs): the J2 short-period terms put the mean
    semi-major axis ~4.6 km lower."""
    from spacemissionstudio.schema import load_scenario

    spacecraft = load_scenario(_TEMPLATES / "18_leo_station_keeping.json").spacecraft[0]
    orbit = lifetime.held_orbit(spacecraft)
    r, _v = lifetime.ring_states(orbit)
    assert (np.linalg.norm(r, axis=1).mean() - lifetime.REQ_EARTH_M) / 1e3 == pytest.approx(400.0, abs=0.01)
    assert 394.0 < (orbit.semi_major_axis_m - lifetime.REQ_EARTH_M) / 1e3 < 397.0  # [km]


@pytest.mark.requires_basilisk
def test_drag_makeup_is_the_delta_v_the_decay_takes_away():
    """Over 5 days from 400 km, the make-up delta-V matches what the same
    drag takes out of the free-decaying orbit (dV = n * da / 2 on a
    circle) to 2.5% (measured 1.9%: 1.3% already over one day, from the
    decay's Gauss equation taking the mean semi-major axis with the
    osculating velocities; the rest as the decaying orbit sinks into
    denser air); Cd 3.0 is 3.0/2.2 times Cd 2.2."""
    scenario = _template_18(400.0)
    spacecraft = scenario.spacecraft[0]
    start = datetime(2030, 1, 1)
    window_years = 5.0 / 365.25  # [year]
    makeup = lifetime.drag_makeup(scenario, spacecraft, start, window_years, drag_coeff=2.2)
    assert makeup.cumulative_m_s[-1] == pytest.approx(makeup.delta_v_m_s)
    assert np.all(np.diff(makeup.cumulative_m_s) > 0.0)

    orbit = lifetime.held_orbit(spacecraft)
    density, _years, _warnings = lifetime.density_for_scenario(scenario, start, 1.0)
    decay = lifetime.propagate_decay(orbit, start, 2.2 * spacecraft.drag_area_m2 / spacecraft.dry_mass_kg,
                                     density, window_years)
    end_sma_m = lifetime.REQ_EARTH_M + 0.5e3 * (decay.perigee_altitude_km[-1] + decay.apogee_altitude_km[-1])
    n = math.sqrt(lifetime.MU_EARTH_M3_S2 / orbit.semi_major_axis_m ** 3)  # [rad/s]
    assert makeup.delta_v_m_s == pytest.approx(0.5 * n * (orbit.semi_major_axis_m - end_sma_m), rel=0.025)
    harder = lifetime.drag_makeup(scenario, spacecraft, start, window_years, drag_coeff=3.0)
    assert harder.delta_v_m_s == pytest.approx(makeup.delta_v_m_s * 3.0 / 2.2, rel=1e-9)
