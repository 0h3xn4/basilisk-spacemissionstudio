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
"""Constant-frame thrust (``SpacecraftConfig.constant_thrust``) in a real
run. The unexecuted-code analysis (Q-ST-80C 6.2.3.6a,
``compliance/unreached_code.md``) found that no test ran it: no template
uses it and the unit tests stop at the schema.

The checks are physical: on a two-body circular orbit, prograde thrust
spends propellant at F / (Isp g0), gives the rocket equation's delta-V,
and raises the semi-major axis by 2 a^1.5 / sqrt(mu) per m/s (Gauss's
equation for tangential thrust on a near-circular orbit).
"""

import math
from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_basilisk

_TEMPLATES = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
G0_M_S2 = 9.80665  # [m/s^2] standard gravity
MU_M3_S2 = 3.986004415e14  # [m^3/s^2] Earth (Basilisk's, deviation D-07)
THRUST_N = 0.05  # [N]
ISP_S = 1500.0  # [s]
PROPELLANT_KG = 2.0  # [kg]
DURATION_DAYS = 0.5  # [day]


def _scenario(frame="VNB", direction=(1.0, 0.0, 0.0)):
    from spacemissionstudio.schema import load_scenario
    from spacemissionstudio.schema.scenario import ConstantThrustConfig

    scenario = load_scenario(next(_TEMPLATES.glob("01_*.json")))  # two-body, circular, 400 km
    scenario.sim_settings.duration_days = DURATION_DAYS
    scenario.sim_settings.record_interval_s = 60.0  # [s]
    scenario.spacecraft[0].constant_thrust = ConstantThrustConfig(
        frame=frame, direction=list(direction), thrust_n=THRUST_N, isp_s=ISP_S, propellant_kg=PROPELLANT_KG)
    return scenario


@pytest.mark.requirement("E-ST-40C 5.8.3.5a")
def test_prograde_constant_thrust_follows_the_rocket_and_gauss_equations():
    """0.05 N prograde for half a day on a 500 kg spacecraft: propellant
    F t / (Isp g0), delta-V Isp g0 ln(m0 / m1) to 0.1 %, and the
    semi-major axis up by 2 a^1.5 / sqrt(mu) times that delta-V to 2 %."""
    from spacemissionstudio.engine.service import SimulationService

    scenario = _scenario()
    result = SimulationService(scenario).run()
    name = scenario.spacecraft[0].name
    elapsed_s = float(result.series[f"{name}.constant_thrust.delta_v"].time_s[-1])  # [s]

    used_kg = PROPELLANT_KG - float(result.series[f"{name}.constant_thrust.propellant_remaining"].data[-1, 0])
    assert used_kg == pytest.approx(THRUST_N * elapsed_s / (ISP_S * G0_M_S2), rel=1e-2)

    start_kg = scenario.spacecraft[0].dry_mass_kg + PROPELLANT_KG  # [kg]
    rocket_m_s = ISP_S * G0_M_S2 * math.log(start_kg / (start_kg - used_kg))  # [m/s]
    delta_v_m_s = float(result.series[f"{name}.constant_thrust.delta_v"].data[-1, 0])
    assert delta_v_m_s == pytest.approx(rocket_m_s, rel=1e-3)
    assert delta_v_m_s == pytest.approx(THRUST_N / start_kg * elapsed_s, rel=1e-2)

    sma = result.series[f"{name}.orbit_elements.semi_major_axis"].data[:, 0]  # [m]
    a_m = float(sma[0])
    expected_m = 2.0 * a_m ** 1.5 / math.sqrt(MU_M3_S2) * delta_v_m_s  # [m]
    assert float(sma[-1] - sma[0]) == pytest.approx(expected_m, rel=2e-2)


@pytest.mark.requirement("E-ST-40C 5.8.3.5a")
def test_orbit_normal_constant_thrust_leaves_the_semi_major_axis_alone():
    """The same thrust along the orbit normal (VNB "N") spends the same
    delta-V but changes the semi-major axis by under 1 % of what
    prograde thrust does: it turns the plane instead."""
    from spacemissionstudio.engine.service import SimulationService

    scenario = _scenario(direction=(0.0, 1.0, 0.0))
    result = SimulationService(scenario).run()
    name = scenario.spacecraft[0].name
    delta_v_m_s = float(result.series[f"{name}.constant_thrust.delta_v"].data[-1, 0])
    sma = result.series[f"{name}.orbit_elements.semi_major_axis"].data[:, 0]  # [m]
    inclination = result.series[f"{name}.orbit_elements.inclination"].data[:, 0]  # [rad]
    prograde_m = 2.0 * float(sma[0]) ** 1.5 / math.sqrt(MU_M3_S2) * delta_v_m_s  # [m]
    assert delta_v_m_s > 1.0  # [m/s] it did fire
    assert abs(float(sma[-1] - sma[0])) < 0.01 * prograde_m
    assert abs(float(inclination[-1] - inclination[0])) > 1e-5  # [rad] the plane turned
