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

"""Delta-V and propellant budgets after ESA's AD10 guideline
(engine.propellant_budget). The last tests need Basilisk."""

import math
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from spacemissionstudio.engine import propellant_budget as pb
from spacemissionstudio.engine.results import ResultSet, TimeSeries
from spacemissionstudio.schema.scenario import (
    GravityConfig,
    OrbitIC,
    PropellantBudgetConfig,
    Scenario,
    ScenarioValidationError,
    SpacecraftConfig,
    StationKeepingConfig,
)

_TEMPLATES = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
_A_400_M = pb.REQ_EARTH_M + 400e3  # [m]


def _scenario(budget, altitude_km=400.0):
    spacecraft = SpacecraftConfig(
        name="sat-1", dry_mass_kg=120.0, enable_drag=True,
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=pb.REQ_EARTH_M / 1e3 + altitude_km,
                      eccentricity=0.0, inclination_deg=97.0, raan_deg=0.0, arg_periapsis_deg=0.0,
                      true_anomaly_deg=0.0),
        station_keeping=StationKeepingConfig(target_altitude_km=altitude_km, deadband_km=1.0, thrust_n=0.05,
                                             isp_s=1500.0, propellant_kg=5.0),
        propellant_budget=budget)
    return Scenario(name="b", epoch_utc="2030-01-01T00:00:00", spacecraft=[spacecraft],
                    gravity=GravityConfig(central_body="earth", third_body_perturbers=["sun"]))


def _no_reentry(*_args):
    return 0.0, 400.0, 0.5, []


_DRAG_BY_YEAR = {2030: 100.0, 2031: 150.0, 2032: 250.0, 2033: 300.0, 2034: 200.0, 2035: 120.0}  # [m/s]


class _StubMakeup:
    """A drag make-up of ``_DRAG_BY_YEAR[launch year]``, recording its calls."""

    def __init__(self):
        self.calls = []

    def __call__(self, scenario, spacecraft, start_utc, years, percentile, drag_coeff=None, should_cancel=None):
        self.calls.append((start_utc, years, percentile, drag_coeff))
        return SimpleNamespace(delta_v_m_s=_DRAG_BY_YEAR[start_utc.year], altitude_km=400.0, warnings=[])


def test_propellant_follows_ad10s_formula():
    """m * (exp(dV / Ve) - 1), Ve = eta * Isp * g0."""
    assert pb.propellant_for(140.0, 100.0, 1500.0 * 9.80665) == pytest.approx(140.0 * (math.exp(100.0 / 14709.975) - 1))
    config = PropellantBudgetConfig(thrust_angle_deg=10.0, misalignment_deg=1.0, plume_efficiency=0.98,
                                    modulation_efficiency=0.95)
    expected = math.cos(math.radians(10.0)) * math.cos(math.radians(1.0)) * 0.98 * 0.95
    assert pb.thruster_efficiency(config) == pytest.approx(expected)


def test_collision_avoidance_clearance_and_injection_delta_v():
    """At 400 km (v = 7.67 km/s): a CAM (+100 m then back) is 0.113 m/s;
    a 5 km clearance drop 2.83 m/s; a 5 km injection error 2.83 m/s and
    0.05 deg of inclination 6.69 m/s."""
    v = math.sqrt(pb.MU_EARTH_M3_S2 / _A_400_M)  # [m/s]
    assert pb.collision_avoidance_delta_v(_A_400_M) == pytest.approx(v * 100.0 / _A_400_M)
    assert pb.collision_avoidance_delta_v(_A_400_M) == pytest.approx(0.113, abs=0.001)
    assert pb.clearance_delta_v(_A_400_M, 5.0) == pytest.approx(2.83, abs=0.01)
    in_plane, out_of_plane = pb.injection_delta_v(
        PropellantBudgetConfig(injection_sma_error_km=5.0, injection_eccentricity_error=0.0001,
                               injection_inclination_error_deg=0.05), _A_400_M)
    assert in_plane == pytest.approx(2.83, abs=0.01)  # the larger of a (2.83) and e (0.38)
    assert out_of_plane == pytest.approx(2.0 * v * math.sin(math.radians(0.025)))


def test_geo_graveyard_rises_235_km_plus_the_srp_term():
    """Cr 1.3, 10 m^2, 500 kg: 235 + 1000 * 1.3 * 10 / 500 = 261 km up,
    a ~9.5 m/s Hohmann transfer."""
    dv, raise_m = pb.graveyard_delta_v(42164.0e3, 1.3, 10.0, 500.0)
    assert raise_m == pytest.approx(261.0e3)
    assert dv == pytest.approx(9.5, abs=0.1)


def test_the_budget_applies_ad10s_margins_and_converges():
    """CAM count x4, attitude propellant x2, a controlled re-entry's last
    burn +15%, 15% dry-mass margin, residual 1% and uncertainty 2% of the
    tank; iterated until the total moves by under 0.1 kg."""
    budget = pb.compute_budget(_scenario(PropellantBudgetConfig(
        in_plane_control_delta_v_m_s=200.0, collision_avoidance_count=5.0, attitude_thruster_propellant_kg=0.3,
        disposal="controlled_reentry", controlled_reentry_delta_v_m_s=80.0, controlled_reentry_last_burn_m_s=40.0,
        tank_capacity_kg=10.0)), "sat-1")
    rows = {r.contributor.split(" (")[0]: r for r in budget.rows}
    assert budget.dry_mass_kg == pytest.approx(138.0)  # [kg] 120 + 15%
    assert rows["Collision avoidance"].delta_v_m_s == pytest.approx(20 * pb.collision_avoidance_delta_v(_A_400_M))
    assert rows["Attitude control by thrusters"].propellant_kg == pytest.approx(0.6)  # [kg]
    assert rows["Controlled re-entry"].delta_v_m_s == pytest.approx(80.0 + 40.0 * 1.15)  # [m/s]
    assert rows["Residual"].propellant_kg == pytest.approx(0.1)  # [kg] 1% of 10
    assert rows["Loading uncertainty and gauging"].propellant_kg == pytest.approx(0.2)  # [kg]
    # Converged: one more pass from the final total changes it by under 0.1 kg
    in_plane = rows["In-plane orbit control"]
    mass_ops = budget.dry_mass_kg + budget.total_propellant_kg  # [kg] beginning of life, no BOL burns here
    assert in_plane.propellant_kg == pytest.approx(pb.propellant_for(mass_ops, 200.0, 1500.0 * 9.80665), abs=0.01)
    assert any("summary table prints 10% and 20%" in n for n in budget.notes)


def test_the_last_run_supplies_orbit_control_scaled_to_the_mission():
    """A 10-day run's station keeping (with a phasing share of the same
    tank) scaled to a 1-year mission, flagged as such."""
    result = ResultSet(scenario_name="r")
    t = np.array([0.0, 10.0 * 86400.0])  # [s]
    result.add(TimeSeries("sat-1.position_N", t, ("x", "y", "z"), np.zeros((2, 3))))
    result.add(TimeSeries("sat-1.station_keeping.delta_v", t, ("dv",), [0.0, 3.0]))
    result.add(TimeSeries("sat-1.phasing_keeping.delta_v", t, ("dv",), [0.0, 1.0]))
    result.add(TimeSeries("sat-1.station_keeping.propellant_remaining", t, ("kg",), [5.0, 4.96]))
    flown = pb.run_contributors(result, "sat-1", 1.0)
    scale = 365.25 / 10.0
    assert flown.scale == pytest.approx(scale)
    assert flown.in_plane == pytest.approx((3.0 * scale, 0.03 * scale))
    assert flown.formation == pytest.approx((1.0 * scale, 0.01 * scale))

    scenario = _scenario(PropellantBudgetConfig(mission_years=1.0))
    budget = pb.compute_budget(scenario, "sat-1", result, reentry_solver=_no_reentry)
    row = next(r for r in budget.rows if r.contributor == "In-plane orbit control")
    assert (row.delta_v_m_s, row.propellant_kg) == pytest.approx((3.0 * scale, 0.03 * scale))
    assert row.source == "last run, scaled"
    assert any("scaled x36.5" in n for n in budget.notes)
    assert any("50th percentile" in n for n in budget.notes)  # AD10 wants the 95th for operations


def test_budget_inputs_validate_and_round_trip():
    config = PropellantBudgetConfig(disposal="graveyard", collision_avoidance_count=2.0)
    scenario = _scenario(config)
    scenario.validate()
    assert Scenario.from_dict(scenario.to_dict()).spacecraft[0].propellant_budget == config
    with pytest.raises(ScenarioValidationError, match="disposal 'sideways'"):
        _scenario(PropellantBudgetConfig(disposal="sideways")).validate()
    with pytest.raises(ScenarioValidationError, match="collision_avoidance_count must be >= 0"):
        _scenario(PropellantBudgetConfig(collision_avoidance_count=-1.0)).validate()


def test_a_spacecraft_without_a_thruster_needs_an_isp():
    scenario = _scenario(PropellantBudgetConfig())
    scenario.spacecraft[0].station_keeping = None
    with pytest.raises(pb.BudgetError, match="set propellant_budget.isp_s"):
        pb.compute_budget(scenario, "sat-1", reentry_solver=_no_reentry)


@pytest.mark.requires_basilisk
def test_the_disposal_burn_brings_the_lifetime_to_five_years():
    """From 550 km in 2035 (after a 5-year mission from 2030): the
    perigee drop the solver picks re-enters in about 5 years at MSFC's
    50th percentile and Cd 2.2; from 400 km no burn is needed."""
    from datetime import datetime

    low = _scenario(None, altitude_km=400.0)
    dv, _perigee, years, _notes = pb.uncontrolled_reentry_delta_v(low, low.spacecraft[0], datetime(2035, 1, 1),
                                                                  125.0, 5.0)
    assert dv == 0.0 and years < 5.0
    high = _scenario(None, altitude_km=550.0)
    dv, perigee_km, years, _notes = pb.uncontrolled_reentry_delta_v(high, high.spacecraft[0],
                                                                    datetime(2035, 1, 1), 125.0, 5.0)
    assert 0.0 < dv < 60.0  # [m/s]
    assert perigee_km < 550.0
    assert 4.5 < years <= 5.05  # [year]


def test_without_a_run_in_plane_control_is_the_drag_estimate():
    """No entry, no run: a LEO station keeper's in-plane control is the
    drag make-up at MSFC's 95th percentile, flagged as estimated."""
    makeup = _StubMakeup()
    budget = pb.compute_budget(_scenario(PropellantBudgetConfig(mission_years=5.0)), "sat-1",
                               reentry_solver=_no_reentry, makeup=makeup)
    row = next(r for r in budget.rows if r.contributor == "In-plane orbit control")
    assert (row.delta_v_m_s, row.source) == (100.0, "estimated")
    assert makeup.calls == [(datetime(2030, 1, 1), 5.0, 95.0, None)]
    assert any("estimated from the drag at 400 km" in n for n in budget.notes)
    assert any("uses Cd 2.2" in n for n in budget.notes)  # the fixture's own Cd, not AD10's 3.0


def test_the_sweep_follows_each_launch_windows_drag():
    """Launches 0-5 years late: in-plane control is each window's drag
    estimate, propellant from each budget's own mass; the worst case is
    the window with the most drag (2033 here)."""
    makeup = _StubMakeup()
    sweep = pb.launch_delay_sweep(_scenario(PropellantBudgetConfig(mission_years=5.0)), "sat-1",
                                  reentry_solver=_no_reentry, makeup=makeup)
    assert [c.launch_utc.year for c in sweep.cases] == [2030, 2031, 2032, 2033, 2034, 2035]
    assert [c.delta_v_of("Operations", "In-plane") for c in sweep.cases] == pytest.approx(
        [100.0, 150.0, 250.0, 300.0, 200.0, 120.0])
    assert [c.drag_ratio for c in sweep.cases] == pytest.approx([1.0, 1.5, 2.5, 3.0, 2.0, 1.2])
    assert sweep.worst.delay_years == 3.0
    assert sweep.worst.budget.total_propellant_kg == max(c.budget.total_propellant_kg for c in sweep.cases)
    assert all(call[2] == 95.0 for call in makeup.calls)  # AD10 Sec. 5.9 for operations
    assert any("worst case: launch 2033-01-01 (3 years late)" in n for n in sweep.notes)


def test_the_sweep_scales_the_entered_or_flown_figure_by_the_drag_ratio():
    """An entered in-plane figure, or the last run's, is kept for the
    planned launch and scaled by the drag ratio for the late ones, at the
    run's own percentile and drag coefficient."""
    entered = pb.launch_delay_sweep(_scenario(PropellantBudgetConfig(in_plane_control_delta_v_m_s=40.0)),
                                    "sat-1", delays_years=(0.0, 2.0), reentry_solver=_no_reentry,
                                    makeup=_StubMakeup())
    rows = [next(r for r in c.budget.rows if r.contributor == "In-plane orbit control") for c in entered.cases]
    assert [(r.delta_v_m_s, r.source) for r in rows] == [(40.0, "input"), (100.0, "input x2.50 (drag)")]

    result = ResultSet(scenario_name="r")
    t = np.array([0.0, 365.25 * 86400.0])  # [s] the whole 1-year mission
    result.add(TimeSeries("sat-1.position_N", t, ("x", "y", "z"), np.zeros((2, 3))))
    result.add(TimeSeries("sat-1.station_keeping.delta_v", t, ("dv",), [0.0, 30.0]))
    result.add(TimeSeries("sat-1.station_keeping.propellant_remaining", t, ("kg",), [5.0, 4.7]))
    run_scenario = _scenario(None)
    run_scenario.space_weather.forecast_percentile = 50.0
    run_scenario.spacecraft[0].drag_coeff = 3.0
    makeup = _StubMakeup()
    flown = pb.launch_delay_sweep(_scenario(PropellantBudgetConfig(mission_years=1.0)), "sat-1", result,
                                  run_scenario, delays_years=(1.0,), reentry_solver=_no_reentry, makeup=makeup)
    rows = [next(r for r in c.budget.rows if r.contributor == "In-plane orbit control") for c in flown.cases]
    assert [(r.delta_v_m_s, r.source) for r in rows] == [(30.0, "last run"), (45.0, "last run x1.50 (drag)")]
    assert rows[0].propellant_kg == pytest.approx(0.3)  # [kg] as flown
    assert {call[2:] for call in makeup.calls} == {(50.0, 3.0)}


def test_without_drag_driven_station_keeping_every_launch_date_is_the_same():
    scenario = _scenario(PropellantBudgetConfig(in_plane_control_delta_v_m_s=10.0))
    scenario.spacecraft[0].enable_drag = False
    sweep = pb.launch_delay_sweep(scenario, "sat-1", delays_years=(0.0, 4.0), reentry_solver=_no_reentry,
                                  makeup=_StubMakeup())
    assert sweep.cases[0].budget.total_delta_v_m_s == sweep.cases[1].budget.total_delta_v_m_s
    assert any("same for every launch date" in n for n in sweep.notes)


def test_launch_dates_move_by_calendar_years():
    """Same date and time of day (an SSO keeps its local time); 29 February
    becomes 28 February."""
    assert pb._years_later(datetime(2030, 1, 1, 8, 30), 3.0) == datetime(2033, 1, 1, 8, 30)
    assert pb._years_later(datetime(2032, 2, 29), 1.0) == datetime(2033, 2, 28)
    assert pb._years_later(datetime(2030, 1, 1), 0.5) == datetime(2030, 7, 2, 15)
    assert [pb.years_late(d) for d in (0.0, 1.0, 2.0)] == ["planned launch", "1 year late", "2 years late"]


class _AltitudeMakeup(_StubMakeup):
    """Drag make-up falling 10x per 100 km above 400 km, times the launch year's factor."""

    def __call__(self, scenario, spacecraft, start_utc, years, percentile, drag_coeff=None, should_cancel=None):
        self.calls.append((start_utc, years, percentile, drag_coeff, spacecraft.station_keeping.target_altitude_km,
                           spacecraft.orbit.inclination_deg))
        altitude_km = spacecraft.orbit.semi_major_axis_km - pb.REQ_EARTH_M / 1e3
        scale = 10.0 ** (-(altitude_km - 400.0) / 100.0)
        return SimpleNamespace(delta_v_m_s=_DRAG_BY_YEAR[start_utc.year] * scale, altitude_km=altitude_km, warnings=[])


def _sso_scenario(budget, altitude_km=400.0):
    from spacemissionstudio.engine.orbit_design import sun_synchronous_inclination_deg

    scenario = _scenario(budget, altitude_km)
    orbit = scenario.spacecraft[0].orbit
    orbit.inclination_deg = sun_synchronous_inclination_deg(orbit.semi_major_axis_km)
    return scenario


def test_the_altitude_trade_finds_the_lowest_altitude_that_fits_the_tank():
    """At each altitude the launch-delay sweep, its worst case held
    against the 2 kg tank; the orbit stays Sun-synchronous and station
    keeping follows the altitude."""
    makeup = _AltitudeMakeup()
    scenario = _sso_scenario(PropellantBudgetConfig(mission_years=5.0))
    scenario.spacecraft[0].station_keeping.propellant_kg = 2.0  # [kg]
    trade = pb.altitude_trade(scenario, "sat-1", [450.0, 400.0, 500.0], reentry_solver=_no_reentry, makeup=makeup)
    assert [c.altitude_km for c in trade.altitudes] == [400.0, 450.0, 500.0]
    worst = [c.worst.delta_v_of("Operations", "In-plane") for c in trade.altitudes]
    assert worst == pytest.approx([300.0, 300.0 / math.sqrt(10.0), 30.0])  # 2033, the stub's worst year
    assert all(c.worst.launch_utc.year == 2033 for c in trade.altitudes)
    from spacemissionstudio.engine.orbit_design import sun_synchronous_inclination_deg
    for case in trade.altitudes:
        assert case.inclination_deg == sun_synchronous_inclination_deg(pb.REQ_EARTH_M / 1e3 + case.altitude_km)
    assert {(call[4], call[5]) for call in makeup.calls} == {(c.altitude_km, c.inclination_deg) for c in trade.altitudes}
    assert trade.tank_kg == 2.0  # the station-keeping propellant, no tank capacity entered
    assert [trade.fits(c) for c in trade.altitudes] == [False, True, True]
    assert trade.lowest_fitting.altitude_km == 450.0
    assert any("lowest altitude whose worst launch fits the 2 kg tank: 450 km" in n for n in trade.notes)


def test_the_altitude_trade_scales_the_scenarios_own_figure():
    """An entered in-plane figure belongs to the scenario's own altitude
    and launch: elsewhere it is scaled by the drag against that one."""
    trade = pb.altitude_trade(_scenario(PropellantBudgetConfig(in_plane_control_delta_v_m_s=50.0, mission_years=5.0)),
                              "sat-1", [400.0, 500.0], delays_years=(0.0,), reentry_solver=_no_reentry,
                              makeup=_AltitudeMakeup())
    in_plane = [next(r for r in c.worst.budget.rows if r.contributor == "In-plane orbit control")
                for c in trade.altitudes]
    assert [(r.delta_v_m_s, r.source) for r in in_plane] == [(50.0, "input x1.00 (drag)"), (5.0, "input x0.10 (drag)")]


def test_the_altitude_trade_needs_classical_elements():
    scenario = _scenario(PropellantBudgetConfig())
    scenario.spacecraft[0].orbit = OrbitIC(type="cartesian", position_km=[6778.0, 0.0, 0.0],
                                           velocity_km_s=[0.0, 7.67, 0.0])
    with pytest.raises(pb.BudgetError, match="classical elements"):
        pb.altitude_trade(scenario, "sat-1", [400.0], reentry_solver=_no_reentry, makeup=_AltitudeMakeup())


def test_default_altitudes_are_five_around_the_spacecrafts_own():
    assert pb.default_altitudes_km(402.0) == [300.0, 350.0, 400.0, 450.0, 500.0]
    assert pb.default_altitudes_km(260.0) == [250.0, 300.0, 350.0, 400.0, 450.0]


@pytest.mark.requires_basilisk
def test_the_altitude_trade_runs_its_altitudes_in_parallel_processes():
    """The real drag estimate and disposal solver in two worker processes:
    the same figures as one launch-delay case run here."""
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(_TEMPLATES / "18_leo_station_keeping.json")
    trade = pb.altitude_trade(scenario, "leo-sat-1", [400.0, 450.0], delays_years=(0.0,), workers=2)
    assert [c.altitude_km for c in trade.altitudes] == [400.0, 450.0]
    here = pb.launch_delay_sweep(pb._at_altitude(scenario, "leo-sat-1", 450.0)[0], "leo-sat-1", delays_years=(0.0,))
    assert trade.altitudes[1].worst.budget.total_propellant_kg == pytest.approx(
        here.worst.budget.total_propellant_kg, rel=1e-9)
    assert trade.altitudes[0].worst.budget.total_propellant_kg > trade.altitudes[1].worst.budget.total_propellant_kg
