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

"""Facet models (schema.scenario.FacetConfig, engine.facets) and their
attitude-dependent drag/SRP. The last tests need Basilisk."""

import numpy as np
import pytest

from spacemissionstudio.engine.facets import box_facets
from spacemissionstudio.engine.scenario_checks import scenario_warnings
from spacemissionstudio.schema.scenario import (
    FacetConfig,
    OrbitIC,
    Scenario,
    ScenarioValidationError,
    SpacecraftConfig,
)


def _spacecraft(**overrides):
    defaults = dict(name="sat-1", orbit=OrbitIC(type="cartesian", position_km=[7000.0, 0.0, 0.0],
                                                 velocity_km_s=[0.0, 7.5, 0.0]))
    defaults.update(overrides)
    return SpacecraftConfig(**defaults)


def test_box_facets_cover_each_face_once_plus_a_two_sided_array():
    facets = box_facets((1.2, 1.0, 1.5), 2.5, (0.0, 0.0, 1.0), (0.0, 1.5, 0.75))  # [m], [m^2]
    assert [f.name for f in facets] == ["bus +x", "bus -x", "bus +y", "bus -y", "bus +z", "bus -z",
                                        "array front", "array back"]
    by_name = {f.name: f for f in facets}
    assert by_name["bus +x"].area_m2 == pytest.approx(1.0 * 1.5)  # [m^2] y * z
    assert by_name["bus -z"].location_b == [0.0, 0.0, -0.75]  # [m]
    front, back = by_name["array front"], by_name["array back"]
    assert front.normal_b == [0.0, 0.0, 1.0] and back.normal_b == [-0.0, -0.0, -1.0]
    assert front.location_b == back.location_b == [0.0, 1.5, 0.75]
    assert front.specular_coeff + front.diffuse_coeff < back.specular_coeff + back.diffuse_coeff + 0.3
    # Opposite faces cancel: a box seen from any side presents its face once.
    normals = np.array([f.normal_b for f in facets[:6]])
    areas = np.array([f.area_m2 for f in facets[:6]])
    assert np.allclose(areas @ normals, 0.0)
    for facet in facets:
        facet.validate("sat-1")


def test_no_array_means_just_the_box():
    assert len(box_facets((1.0, 1.0, 1.0))) == 6


@pytest.mark.parametrize("change, message", [
    ({"area_m2": 0.0}, "area_m2 must be in"),
    ({"normal_b": [0.0, 0.0, 0.0]}, "normal_b must be a non-zero"),
    ({"location_b": [0.0, float("nan"), 0.0]}, "location_b must be a finite"),
    ({"specular_coeff": 0.7, "diffuse_coeff": 0.5}, "sum to at most 1"),
    ({"drag_coeff": -1.0}, "drag_coeff must be in"),
])
def test_a_bad_facet_is_rejected(change, message):
    facet = FacetConfig(name="f", area_m2=1.0, normal_b=[1.0, 0.0, 0.0])
    for key, value in change.items():
        setattr(facet, key, value)
    with pytest.raises(ScenarioValidationError, match=message):
        _spacecraft(facets=[facet]).validate()


def test_facet_names_must_be_unique():
    facet = FacetConfig(name="f", area_m2=1.0, normal_b=[1.0, 0.0, 0.0])
    with pytest.raises(ScenarioValidationError, match="facet names must be unique"):
        _spacecraft(facets=[facet, facet]).validate()


def test_facets_need_full_attitude_and_round_trip():
    scenario = Scenario(name="f", epoch_utc="2030-01-01T00:00:00", simulation_mode="orbit_only",
                        spacecraft=[_spacecraft(facets=box_facets((1.0, 1.0, 1.0)), enable_drag=True)])
    with pytest.raises(ScenarioValidationError, match="facets are set but scenario.simulation_mode is 'orbit_only'"):
        scenario.validate()
    scenario.simulation_mode = "full_attitude"
    scenario.validate()
    assert Scenario.from_dict(scenario.to_dict()).spacecraft[0].facets == scenario.spacecraft[0].facets


def test_facets_with_drag_and_srp_off_are_flagged():
    scenario = Scenario(name="f", epoch_utc="2030-01-01T00:00:00",
                        spacecraft=[_spacecraft(facets=box_facets((1.0, 1.0, 1.0)))])
    assert scenario_warnings(scenario) == ["sat-1: its facets are unused -- they only shape drag and SRP, "
                                           "and both are off"]
    scenario.spacecraft[0].enable_srp = True
    assert scenario_warnings(scenario) == []


def _sun_pointing_run(facets, enable_srp=True, srp_coeff=1.0, srp_area_m2=4.0, hours=1.6):
    from spacemissionstudio.engine.orbit_design import raan_for_ltan_deg
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.schema.scenario import GravityConfig, SimSettings

    spacecraft = _spacecraft(
        dry_mass_kg=300.0, inertia_kg_m2=[92.3, 0.0, 0.0, 0.0, 92.3, 0.0, 0.0, 0.0, 72.0],
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0, inclination_deg=97.6,
                      raan_deg=raan_for_ltan_deg("2030-01-01T00:00:00"), arg_periapsis_deg=0.0,
                      true_anomaly_deg=0.0),
        fsw_mode="sunSafePoint", fsw_params={"sHatBdyCmd": [0.0, 0.0, 1.0]},
        enable_srp=enable_srp, srp_coeff=srp_coeff, srp_area_m2=srp_area_m2, facets=facets)
    scenario = Scenario(name="f", epoch_utc="2030-01-01T00:00:00", simulation_mode="full_attitude",
                        gravity=GravityConfig(central_body="earth", central_body_degree=0,
                                              third_body_perturbers=["sun"]),
                        sim_settings=SimSettings(duration_days=hours / 24.0, dynamics_task_rate_s=1.0),  # [day], [s]
                        spacecraft=[spacecraft])
    return SimulationService(scenario).run()


@pytest.mark.requires_basilisk
def test_an_absorbing_sun_facing_plate_pushes_like_the_sphere_model():
    """A black plate (no reflection) held facing the Sun feels P*A, the
    same as the sphere model's Cr = 1 with the same area."""
    plate = [FacetConfig(name="plate", area_m2=4.0, normal_b=[0.0, 0.0, 1.0], specular_coeff=0.0,
                         diffuse_coeff=0.0)]
    none = _sun_pointing_run([], enable_srp=False).series["sat-1.position_N"].data[-1]
    sphere = _sun_pointing_run([]).series["sat-1.position_N"].data[-1]
    faceted = _sun_pointing_run(plate).series["sat-1.position_N"].data[-1]
    srp_shift = np.linalg.norm(sphere - none)  # [m]
    assert srp_shift > 0.05  # [m] SRP moved the spacecraft measurably
    assert np.linalg.norm(faceted - sphere) < 0.05 * srp_shift  # [m]


@pytest.mark.requires_basilisk
def test_an_off_centre_array_torques_the_spacecraft():
    """A sun-facing array 1.5 m off to one side: its SRP pushes off-centre,
    a steady torque about body x that the attitude control must cancel.
    Expected while sunlit: (1 + s + 2d/3) P A arm, with the array's s = d =
    0.16 and P = 4.58e-6 N/m^2 at 1 AU, scaled to Earth's 0.983 AU on
    1 January: 1.267 * 4.73e-6 * 2.5 * 1.5 = 2.25e-5 N*m (2.24e-5 in a
    real run)."""
    def sunlit_control_torque(array_location):
        facets = box_facets((1.2, 1.2, 1.5), 2.5, (0.0, 0.0, 1.0), array_location)  # [m], [m^2]
        torque = _sun_pointing_run(facets, hours=1.0).series["sat-1.control_torque"]
        settled = (torque.time_s > 900.0) & (torque.time_s < 1500.0)  # [s] after the slew, before eclipse
        return np.abs(torque.data[settled]).max(axis=0)  # [N*m]

    assert sunlit_control_torque((0.0, 1.5, 0.75))[0] == pytest.approx(2.25e-5, rel=0.05)  # [N*m]
    assert sunlit_control_torque((0.0, 0.0, 0.75))[0] < 1e-6  # [N*m] centred: no torque (1e-7 in a real run)


def test_explain_tab_names_the_facet_model():
    from spacemissionstudio.engine.scenario_explainer import explain

    scenario = Scenario(name="f", epoch_utc="2030-01-01T00:00:00",
                        spacecraft=[_spacecraft(facets=box_facets((1.0, 1.0, 1.0)), enable_srp=True)])
    badges = [b.label for section in explain(scenario).sections for b in section.badges]
    assert "Facet model (drag/SRP torques)" in badges
