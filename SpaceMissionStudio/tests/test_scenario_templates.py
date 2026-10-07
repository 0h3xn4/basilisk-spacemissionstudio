"""Tests for spacemissionstudio/scenarios/templates/*.json -- the education/
starter-template scenarios (see that directory's own README). Basilisk
-free: these only exercise schema.scenario.load_scenario()/validate(),
the same path the GUI's File > Open and the CLI's `validate`/`run`
subcommands go through, never an actual Basilisk propagation.
"""

from pathlib import Path

import pytest

from spacemissionstudio.schema import load_scenario

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
_TEMPLATE_PATHS = sorted(_TEMPLATES_DIR.glob("*.json"))


def test_at_least_one_template_exists():
    # A guard against the glob above silently matching nothing (e.g. the
    # directory got renamed/moved) and every parametrized test below
    # collecting zero cases, which would pass "successfully" while
    # testing nothing at all.
    assert len(_TEMPLATE_PATHS) >= 18


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_template_loads_and_validates(path):
    scenario = load_scenario(path)
    scenario.validate()  # must not raise


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_template_has_at_least_one_spacecraft(path):
    scenario = load_scenario(path)
    assert len(scenario.spacecraft) >= 1


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_template_has_a_substantial_description(path):
    """Every template's whole point is to explain a concept -- a blank or
    one-line description would defeat that, so this is checked directly
    rather than just trusting the generator script forever gets it right.
    """
    scenario = load_scenario(path)
    assert len(scenario.description) > 200


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_template_round_trips_through_save_load(path, tmp_path):
    scenario = load_scenario(path)
    out_path = tmp_path / path.name
    scenario.save(out_path)
    round_tripped = load_scenario(out_path)
    round_tripped.validate()
    assert round_tripped.to_dict() == scenario.to_dict()


def test_walker_constellation_template_has_six_uniquely_named_satellites():
    scenario = load_scenario(_TEMPLATES_DIR / "04_walker_constellation.json")
    names = [sc.name for sc in scenario.spacecraft]
    assert len(names) == 6
    assert len(set(names)) == 6


def test_mission_sequence_template_has_a_maneuver_command():
    scenario = load_scenario(_TEMPLATES_DIR / "08_mission_sequence_orbit_raise.json")
    kinds = [c.kind for c in scenario.mission_sequence]
    assert "maneuver" in kinds


def test_monte_carlo_template_has_monte_carlo_enabled():
    scenario = load_scenario(_TEMPLATES_DIR / "09_monte_carlo_dispersion_analysis.json")
    assert scenario.monte_carlo.enabled
    assert len(scenario.monte_carlo.dispersions) >= 1


def test_gravity_gradient_template_has_no_attitude_control_and_an_elongated_inertia():
    """Regression guard for '10's own stated lesson: gravity-gradient
    torque is identically zero for a spherically-symmetric inertia, and
    invisible behind an active controller that just rejects it as one
    more disturbance -- both conditions must hold for the template to
    actually demonstrate the effect it claims to.
    """
    scenario = load_scenario(_TEMPLATES_DIR / "10_gravity_gradient_torque.json")
    sat = scenario.spacecraft[0]
    assert sat.fsw_mode is None
    assert sat.enable_gravity_gradient is True
    ixx, iyy, izz = sat.inertia_kg_m2[0], sat.inertia_kg_m2[4], sat.inertia_kg_m2[8]
    assert not (ixx == iyy == izz)


def test_thruster_attitude_control_template_has_only_thruster_actuators():
    scenario = load_scenario(_TEMPLATES_DIR / "11_thruster_attitude_control.json")
    sat = scenario.spacecraft[0]
    kinds = {a.kind for a in sat.actuators}
    assert kinds == {"thruster"}
    assert len(sat.actuators) >= 6  # fewer cannot produce a pure 3-axis torque solution
    assert sat.fsw_mode is not None


def test_momentum_dumping_template_mixes_reaction_wheel_and_thruster_actuators():
    scenario = load_scenario(_TEMPLATES_DIR / "12_reaction_wheel_momentum_dumping.json")
    sat = scenario.spacecraft[0]
    kinds = {a.kind for a in sat.actuators}
    assert kinds == {"reaction_wheel", "thruster"}
    assert sat.momentum_dumping is not None
    assert sat.momentum_dumping.hs_max > 0


def test_magnetic_momentum_management_template_mixes_reaction_wheel_and_mtb_actuators():
    scenario = load_scenario(_TEMPLATES_DIR / "13_magnetic_torque_rod_momentum_management.json")
    sat = scenario.spacecraft[0]
    kinds = {a.kind for a in sat.actuators}
    assert kinds == {"reaction_wheel", "magnetic_torque_rod"}
    assert sat.magnetic_momentum_management is not None
    num_rw = sum(1 for a in sat.actuators if a.kind == "reaction_wheel")
    assert len(sat.magnetic_momentum_management.wheel_speed_biases_rad_s) == num_rw


def test_css_sun_heading_estimation_template_wires_use_css_estimation():
    scenario = load_scenario(_TEMPLATES_DIR / "14_css_sun_heading_estimation.json")
    sat = scenario.spacecraft[0]
    assert sat.fsw_mode == "sunSafePoint"
    assert sat.fsw_params.get("use_css_estimation") is True
    assert sum(1 for s in sat.sensors if s.kind == "coarse_sun_sensor") == 8
    assert "sun" in scenario.gravity.third_body_perturbers
    # DEFAULT_MRP_GAINS (K=3.5/P=30) scaled down for this template's 5 kg*m^2
    # hub -- see scripts/_generate_templates.py's own comment and
    # HISTORY.md for why an unscaled default never converges here.
    assert sat.control_params.get("K", 3.5) < 1.0
    assert sat.control_params.get("P", 30.0) < 1.0


def test_celestial_body_pointing_template_uses_target_body_not_ground_station():
    scenario = load_scenario(_TEMPLATES_DIR / "15_celestial_body_pointing.json")
    sat = scenario.spacecraft[0]
    assert sat.fsw_mode == "locationPointing"
    assert sat.fsw_params.get("target_body") == "moon"
    assert "target_ground_station" not in sat.fsw_params
    assert sat.fsw_params.get("target_body") in (
        {scenario.gravity.central_body} | set(scenario.gravity.third_body_perturbers)
    )


def test_lambert_transfer_template_targets_the_documented_position():
    scenario = load_scenario(_TEMPLATES_DIR / "16_lambert_transfer.json")
    kinds = [c.kind for c in scenario.mission_sequence]
    assert "lambert_transfer" in kinds
    lambert_cmd = scenario.mission_sequence[kinds.index("lambert_transfer")]
    assert lambert_cmd.params["spacecraft"] == "sat-1"
    assert lambert_cmd.params["target_position_m"] == [-6578000.0, 0.0, 0.0]
    assert lambert_cmd.params["time_of_flight_s"] == 2490.0


def test_fuel_tank_template_has_a_tank_tied_to_its_thrusters():
    scenario = load_scenario(_TEMPLATES_DIR / "17_fuel_tank_depletion.json")
    sat = scenario.spacecraft[0]
    assert sat.fuel_tank is not None
    assert sat.fuel_tank.propellant_mass_kg == 0.5
    assert sat.fuel_tank.max_propellant_mass_kg == 1.0
    assert any(a.kind == "thruster" for a in sat.actuators)


def test_phasing_template_pairs_phasing_keeping_with_station_keeping():
    """Regression guard for PhasingKeepingConfig's own documented
    requirement (also enforced by Scenario.validate() itself) -- if a
    future edit to this template ever drops the paired station_keeping,
    this fails clearly instead of only failing deep inside validate()'s
    generic error message.
    """
    scenario = load_scenario(_TEMPLATES_DIR / "05_formation_flying_phasing.json")
    follower = next(sc for sc in scenario.spacecraft if sc.phasing_keeping is not None)
    assert follower.station_keeping is not None


def test_leo_station_keeping_template_is_drag_driven_not_srp_driven():
    """The direct LEO counterpart to '03' (GEO, SRP/third-body-driven,
    drag off): this one isolates drag as the one dominant perturbation
    instead, with a materially tighter deadband than '03's GEO case --
    see the file's own description for why (continuous drag needs more
    frequent, smaller corrections than GEO's occasional ones).
    """
    leo = load_scenario(_TEMPLATES_DIR / "18_leo_station_keeping.json").spacecraft[0]
    geo = load_scenario(_TEMPLATES_DIR / "03_geo_station_keeping.json").spacecraft[0]
    assert leo.station_keeping is not None
    assert leo.enable_drag is True
    assert leo.enable_srp is False
    assert leo.station_keeping.target_altitude_km < 1000.0  # genuinely LEO, not GEO-scale
    assert leo.station_keeping.deadband_km < geo.station_keeping.deadband_km


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_template_descriptions_are_short_and_structured(path):
    """Real user feedback on the Load tab ("just awful UI/UX"): the
    descriptions were up to 7,000 characters of prose, including
    development audit history. They are now a short summary plus "What to
    look at" / "Try changing" bullets, written for the user."""
    description = load_scenario(path).description
    assert len(description) < 1400, len(description)
    assert "What to look at" in description and "Try changing:" in description
    for banned in ("Audit history", "docstring", "HISTORY.md", "confirmed directly", "real user"):
        assert banned not in description, banned
    summary = description.split("\n\n")[0]
    assert len(summary) < 300, summary
    for line in description.splitlines():
        if line.startswith("- "):
            assert len(line) < 200, line  # short bullets, not paragraphs


def test_lambert_template_burns_a_quarter_orbit_in_like_basilisks_example():
    """examples/scenarioLambertSolver.py burns at tau/4 and arrives at tau/2.
    Burning at t = 0 puts the arc below Earth's surface (~6366 km), which
    the template's own min_orbit_radius_m rejects; the coast also gives the
    first report something recorded to show."""
    import math

    scenario = load_scenario(_TEMPLATES_DIR / "16_lambert_transfer.json")
    kinds = [c.kind for c in scenario.mission_sequence]
    assert kinds == ["propagate", "report", "lambert_transfer", "propagate", "report"]
    a_m = scenario.spacecraft[0].orbit.semi_major_axis_km * 1e3
    period_s = 2 * math.pi * math.sqrt(a_m ** 3 / 3.986004415e14)  # [s] Basilisk's Earth mu
    coast_s = scenario.mission_sequence[0].params["duration_days"] * 86400.0
    assert coast_s == pytest.approx(round(period_s / 4 / 10) * 10)  # [s] the example's tm, on its 10 s step
    lambert = scenario.mission_sequence[2]
    arrival_coast_s = scenario.mission_sequence[3].params["duration_days"] * 86400.0
    assert arrival_coast_s == pytest.approx(lambert.params["time_of_flight_s"])


@pytest.mark.parametrize("path", sorted(_TEMPLATES_DIR.glob("*.json")), ids=lambda p: p.name)
def test_sun_pointing_templates_put_their_sun_sensors_on_the_sun_face(path):
    """sunSafePoint turns sHatBdyCmd (default +Z) to the Sun. Template 20's
    thermal sensor (and 07/20's single sun sensor) faced +X, i.e. edge-on to
    the Sun: zero projected area, so no solar heating and no CSS signal,
    contradicting the template's own "heats in sunlight" lesson."""
    import numpy as np

    for sc in load_scenario(path).spacecraft:
        if sc.fsw_mode != "sunSafePoint":
            continue
        sun_axis = np.array(sc.fsw_params.get("sHatBdyCmd", [0.0, 0.0, 1.0]))
        facing = {s.name: float(np.dot(s.params["nHat_B"], sun_axis)) for s in sc.sensors
                  if s.kind in ("thermal", "coarse_sun_sensor")}
        thermal = [s.name for s in sc.sensors if s.kind == "thermal"]
        assert all(facing[name] > 0.5 for name in thermal), facing
        css = [s.name for s in sc.sensors if s.kind == "coarse_sun_sensor"]
        assert not css or any(facing[name] > 0.5 for name in css), facing


def test_template_descriptions_match_the_run_length():
    """Template 15 promised Moon pointing "for the whole orbit" over a run
    shorter than one orbit."""
    import math

    scenario = load_scenario(_TEMPLATES_DIR / "15_celestial_body_pointing.json")
    a_m = scenario.spacecraft[0].orbit.semi_major_axis_km * 1e3
    period_days = 2 * math.pi * math.sqrt(a_m ** 3 / 3.986004415e14) / 86400.0  # [day]
    if scenario.sim_settings.duration_days < period_days:
        assert "whole orbit" not in scenario.description
