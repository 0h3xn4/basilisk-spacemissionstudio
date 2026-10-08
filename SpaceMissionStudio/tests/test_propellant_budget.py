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
from pathlib import Path

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
        name="sat-1", dry_mass_kg=120.0,
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
