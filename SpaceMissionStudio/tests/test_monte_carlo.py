"""Tests for spacemissionstudio.engine.monte_carlo.run_monte_carlo(). Needs a
Basilisk build to import (Basilisk.utilities.MonteCarlo.* at module level);
see tests/conftest.py for the auto-skip behavior in this development
sandbox, which does not have one.
"""

import pytest

from spacemissionstudio.schema import GravityConfig, MonteCarloConfig, OrbitIC, Scenario, SpacecraftConfig
from spacemissionstudio.schema.scenario import ConstantThrustConfig, DispersionConfig, StationKeepingConfig

pytestmark = pytest.mark.requires_basilisk


def _scenario(**spacecraft_overrides):
    return Scenario(
        name="mc test scenario",
        epoch_utc="2030-01-01T00:00:00",
        gravity=GravityConfig(central_body="earth", central_body_degree=0),
        spacecraft=[SpacecraftConfig(
            name="sat-1", dry_mass_kg=100.0,
            orbit=OrbitIC(type="cartesian", position_km=[7000.0, 0.0, 0.0], velocity_km_s=[0.0, 7.5, 0.0]),
            **spacecraft_overrides,
        )],
        monte_carlo=MonteCarloConfig(enabled=True, num_runs=1),
    )


def test_run_monte_carlo_reports_a_clean_error_when_archive_dir_is_a_file(tmp_path):
    """Regression test for an audit finding: archive_dir.mkdir(...) used to
    sit outside run_monte_carlo()'s own try/except (which only wrapped
    controller.executeSimulations()), so pointing --archive-dir at a path
    that already exists as a plain file raised a bare FileExistsError
    instead of this module's usual MonteCarloError.
    """
    from spacemissionstudio.engine.monte_carlo import MonteCarloError, run_monte_carlo

    archive_dir = tmp_path / "already_a_file"
    archive_dir.write_text("not a directory")

    with pytest.raises(MonteCarloError, match="could not create Monte Carlo archive directory"):
        run_monte_carlo(_scenario(), MonteCarloConfig(enabled=True, num_runs=1), archive_dir)


def test_propellant_offset_kg_sums_station_keeping_and_constant_thrust():
    from spacemissionstudio.engine.monte_carlo import _propellant_offset_kg

    sc = SpacecraftConfig(
        name="s", orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        station_keeping=StationKeepingConfig(
            target_altitude_km=500, deadband_km=1, thrust_n=0.1, isp_s=200, propellant_kg=10.0),
        constant_thrust=ConstantThrustConfig(propellant_kg=2.0),
    )
    assert _propellant_offset_kg(sc) == 12.0


def test_propellant_offset_kg_is_zero_with_neither_configured():
    from spacemissionstudio.engine.monte_carlo import _propellant_offset_kg

    sc = SpacecraftConfig(name="s", orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0],
                                                    velocity_km_s=[0, 7.5, 0]))
    assert _propellant_offset_kg(sc) == 0.0


def test_dry_mass_dispersion_adds_propellant_offset_on_top():
    """Regression test for an audit finding: Basilisk's dispersion classes
    write their generated value ABSOLUTELY to hub.mHub, with no way to add
    anything on top -- but hub.mHub is dry_mass_kg + propellant for a
    spacecraft with station_keeping/constant_thrust configured (see
    service.py's own initial_mass_kg computation), not just dry_mass_kg.
    A plain dispersion on "dry_mass_kg" would therefore silently disperse
    the TOTAL mass under that name instead of just the dry mass.
    """
    from spacemissionstudio.engine.monte_carlo import _build_dispersion

    scenario = _scenario(station_keeping=StationKeepingConfig(
        target_altitude_km=500, deadband_km=1, thrust_n=0.1, isp_s=200, propellant_kg=10.0))
    dispersion = DispersionConfig(spacecraft="sat-1", quantity="dry_mass_kg", kind="uniform", bounds=[90.0, 110.0])

    disp = _build_dispersion(dispersion, scenario)
    for _ in range(50):
        value = disp.generate(sim=None)
        assert 100.0 <= value <= 120.0  # [90, 110] dry-mass bounds + 10 kg propellant offset


def test_dry_mass_dispersion_with_no_propellant_is_unshifted():
    from spacemissionstudio.engine.monte_carlo import _build_dispersion

    scenario = _scenario()  # no station_keeping/constant_thrust
    dispersion = DispersionConfig(spacecraft="sat-1", quantity="dry_mass_kg", kind="uniform", bounds=[90.0, 110.0])

    disp = _build_dispersion(dispersion, scenario)
    for _ in range(50):
        value = disp.generate(sim=None)
        assert 90.0 <= value <= 110.0


def test_dry_mass_normal_dispersion_adds_propellant_offset_on_top():
    from spacemissionstudio.engine.monte_carlo import _build_dispersion

    scenario = _scenario(constant_thrust=ConstantThrustConfig(propellant_kg=5.0))
    dispersion = DispersionConfig(spacecraft="sat-1", quantity="dry_mass_kg", kind="normal",
                                   mean=100.0, std_deviation=0.001)

    disp = _build_dispersion(dispersion, scenario)
    value = disp.generate(sim=None)
    assert value == pytest.approx(105.0, abs=0.1)  # mean 100 + 5 kg propellant offset


def test_build_dispersion_unknown_spacecraft_raises_clear_error():
    from spacemissionstudio.engine.monte_carlo import MonteCarloError, _build_dispersion

    scenario = _scenario()
    dispersion = DispersionConfig(spacecraft="does-not-exist", quantity="dry_mass_kg", kind="uniform",
                                   bounds=[90.0, 110.0])

    with pytest.raises(MonteCarloError, match="does-not-exist"):
        _build_dispersion(dispersion, scenario)


# -- The orbit, inertia, body-rate and coefficient dispersions -----------------

_TEMPLATE_07 = "07_attitude_pointing_with_adcs_hardware.json"


def _template_07_with(dispersions, num_runs=3, duration_s=120.0):
    """Template 07 (full attitude, sphere drag and SRP), shortened."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "spacemissionstudio" / "scenarios" / "templates" / _TEMPLATE_07
    data = json.loads(path.read_text(encoding="utf-8"))
    name = data["spacecraft"][0]["name"]
    data["sim_settings"]["duration_days"] = duration_s / 86400.0
    data["monte_carlo"].update(enabled=True, num_runs=num_runs,
                               dispersions=[dict(d, spacecraft=name) for d in dispersions])
    scenario = Scenario.from_dict(data)
    scenario.validate()
    return scenario


def _draw(dispersion, scenario):
    """One draw of ``dispersion``, as the Controller makes it: {path: value}."""
    import ast

    from spacemissionstudio.engine.monte_carlo import _build_dispersion, _create_sim

    sim = _create_sim(scenario)
    disp = _build_dispersion(dispersion, scenario)
    try:
        return {disp.getName(): ast.literal_eval(disp.generateString(sim))}
    except TypeError:  # OrbitalElementDispersion: two co-dependent paths
        disp.generate()
        return {disp.getName(i): ast.literal_eval(disp.generateString(i, sim)) for i in (1, 2)}


def test_an_orbit_dispersion_moves_only_the_elements_it_spreads():
    """OrbitalElementDispersion around the nominal orbit: a 1 km spread on the
    semi-major axis changes a, while inclination and RAAN stay nominal (the
    Basilisk class would set an element with no entry to zero)."""
    import numpy as np
    from Basilisk.utilities import orbitalMotion

    from spacemissionstudio.engine.monte_carlo import _central_body_mu, nominal_elements

    scenario = _template_07_with([{"quantity": "orbit_elements", "kind": "uniform",
                                   "element_spread": {"semi_major_axis_km": 1.0}}])
    nominal = nominal_elements(scenario, scenario.spacecraft[0])
    values = list(_draw(scenario.monte_carlo.dispersions[0], scenario).values())
    oe = orbitalMotion.rv2elem(_central_body_mu(scenario), np.array(values[0]), np.array(values[1]))
    assert 0.0 < abs(oe.a - nominal.a) <= 1000.0 + 1e-6  # [m]
    assert oe.i == pytest.approx(nominal.i, abs=1e-12)
    assert oe.Omega == pytest.approx(nominal.Omega, abs=1e-12)


def test_the_body_rate_spread_is_added_to_the_nominal_rate():
    """The vector Cartesian classes draw an absolute vector; the rate is
    dispersed around template 07's own nominal rate instead (deg/s spread)."""
    import math

    import numpy as np

    scenario = _template_07_with([{"quantity": "angular_rate_bn_b", "kind": "uniform", "bounds": [-0.1, 0.1]}])
    nominal = np.array(scenario.spacecraft[0].omega_bn_b_init_rad_s)  # [rad/s]
    for _ in range(5):
        (rate,) = _draw(scenario.monte_carlo.dispersions[0], scenario).values()
        assert np.all(np.abs(np.array(rate) - nominal) <= math.radians(0.1) + 1e-12)


def test_an_inertia_dispersion_is_not_clipped_to_one_kg_m2_by_default():
    """InertiaTensorDispersion clips each diagonal offset to [-1, 1] kg*m^2
    unless given bounds; with no bounds set here, a 5 kg*m^2 spread is kept."""
    import numpy as np

    scenario = _template_07_with([{"quantity": "inertia_kg_m2", "kind": "normal", "std_deviation": 5.0}])
    nominal = np.array(scenario.spacecraft[0].inertia_kg_m2).reshape(3, 3)
    offsets = []
    for _ in range(10):
        (inertia,) = _draw(scenario.monte_carlo.dispersions[0], scenario).values()
        offsets += list(np.diag(np.array(inertia) - nominal))
    assert max(abs(o) for o in offsets) > 1.0  # [kg*m^2]


def test_a_batch_disperses_every_new_quantity_in_every_run(tmp_path):
    """Three runs through Basilisk's Controller: each run's archived
    parameters hold its own orbit, inertia, rate, Cd and Cr, within bounds."""
    import json

    scenario = _template_07_with([
        {"quantity": "orbit_elements", "kind": "normal", "element_spread": {"semi_major_axis_km": 0.5}},
        {"quantity": "inertia_kg_m2", "kind": "normal", "std_deviation": 0.5, "angle_std_deg": 1.0},
        {"quantity": "angular_rate_bn_b", "kind": "normal", "std_deviation": 0.05},
        {"quantity": "drag_coeff", "kind": "uniform", "bounds": [2.0, 3.0]},
        {"quantity": "srp_coeff", "kind": "uniform", "bounds": [1.2, 1.5]},
    ])
    from spacemissionstudio.engine.monte_carlo import run_monte_carlo

    assert run_monte_carlo(scenario, scenario.monte_carlo, tmp_path) == []
    runs = [json.loads((tmp_path / f"run{i}.json").read_text()) for i in range(3)]
    drag = [float(next(v for k, v in run.items() if k.endswith("dragCoeff"))) for run in runs]
    srp = [float(next(v for k, v in run.items() if k.endswith("coefficientReflection"))) for run in runs]
    assert len(set(drag)) == 3 and all(2.0 <= cd <= 3.0 for cd in drag)
    assert all(1.2 <= cr <= 1.5 for cr in srp)
    for suffix in ("r_CN_NInit", "v_CN_NInit", "IHubPntBc_B", "omega_BN_BInit"):
        assert len({next(v for k, v in run.items() if k.endswith(suffix)) for run in runs}) == 3, suffix


def test_a_batch_leaves_a_pickle_free_summary_of_every_run(tmp_path):
    """After the batch, run_monte_carlo reads back the run files it just
    wrote and saves batch_results.npz/.json (security analysis S-04): every
    run's trajectory and its drawn values under readable labels, matching
    what the Controller recorded in runN.json."""
    import json

    from spacemissionstudio.engine import monte_carlo_results as mcr
    from spacemissionstudio.engine.monte_carlo import run_monte_carlo

    scenario = _template_07_with([
        {"quantity": "orbit_elements", "kind": "normal",
         "element_spread": {"semi_major_axis_km": 0.5, "true_anomaly_deg": 0.1}},
        {"quantity": "drag_coeff", "kind": "uniform", "bounds": [2.0, 3.0]},
        {"quantity": "inertia_kg_m2", "kind": "normal", "std_deviation": 0.5},
    ])
    assert run_monte_carlo(scenario, scenario.monte_carlo, tmp_path) == []
    batch = mcr.load(tmp_path)
    name = scenario.spacecraft[0].name
    assert batch.runs == [0, 1, 2] and batch.failed == []
    assert batch.positions[name].shape == (3, batch.time_s.size, 3)
    assert batch.time_s[-1] == pytest.approx(120.0)  # [s] the shortened run
    for k, drawn in enumerate(batch.drawn):
        params = json.loads((tmp_path / f"run{k}.json").read_text())
        cd = float(next(v for key, v in params.items() if key.endswith("dragCoeff")))
        assert drawn[f"{name} drag coefficient [-]"] == pytest.approx(cd)
        assert set(drawn) >= {f"{name} semi-major axis [km]", f"{name} true anomaly [deg]", f"{name} Ixx [kg m^2]"}
        assert drawn[f"{name} semi-major axis [km]"] == pytest.approx(6928.0, abs=5.0)  # [km] nominal +/- 10 sigma
        assert abs(drawn[f"{name} true anomaly [deg]"]) < 1.0  # [deg] near the nominal 0, not 359.9
    assert len({drawn[f"{name} drag coefficient [-]"] for drawn in batch.drawn}) == 3
    # the starting positions differ along track, as the true-anomaly spread says
    assert mcr.offsets(batch.positions[name], batch.velocities[name])[:, 0, 1].std() > 100.0  # [m]
