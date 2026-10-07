"""Tests for spacemissionstudio.engine.spacecraft_templates. All but the
last run without Basilisk.
"""

import pytest

from spacemissionstudio.engine.spacecraft_templates import SPACECRAFT_TEMPLATES


def test_every_template_builds_a_valid_spacecraft_config():
    for template in SPACECRAFT_TEMPLATES:
        config = template.build()
        config.validate()  # raises ScenarioValidationError with a specific message on anything bad


def test_every_template_has_a_name_and_description():
    for template in SPACECRAFT_TEMPLATES:
        assert template.name.strip()
        assert template.description.strip()


def test_template_names_are_unique():
    names = [t.name for t in SPACECRAFT_TEMPLATES]
    assert len(names) == len(set(names))


def test_build_returns_a_fresh_instance_each_call():
    """Regression-guard: two calls to the same template's build() must not
    share mutable state (e.g. the same sensors/actuators list object) --
    mutating one build()'s result must not affect the next one's.
    """
    for template in SPACECRAFT_TEMPLATES:
        first = template.build()
        second = template.build()
        assert first is not second
        first.name = "mutated"
        assert second.name != "mutated"
        if first.sensors:
            first.sensors.append("not a real sensor")
            assert len(second.sensors) != len(first.sensors)


def test_presets_cover_the_100_to_500_kg_class_with_fitting_inertias():
    """The class this app is for: no CubeSats."""
    masses = sorted(t.build().dry_mass_kg for t in SPACECRAFT_TEMPLATES)
    assert masses == [100.0, 150.0, 300.0, 500.0]  # [kg]
    for template in SPACECRAFT_TEMPLATES:
        config = template.build()
        mean_inertia = sum(config.inertia_kg_m2[i] for i in (0, 4, 8)) / 3.0  # [kg*m^2]
        assert config.dry_mass_kg * 0.5 ** 2 / 6.0 <= mean_inertia <= config.dry_mass_kg * 2.5 ** 2 / 6.0


def test_sun_safe_presets_put_array_sensor_and_sun_axis_on_the_same_face():
    for template in SPACECRAFT_TEMPLATES:
        config = template.build()
        if config.fsw_mode != "sunSafePoint":
            continue
        sun_axis = config.fsw_params["sHatBdyCmd"]
        assert config.power.panel_normal_b == sun_axis
        assert any(s.kind == "coarse_sun_sensor" and s.params["nHat_B"] == sun_axis for s in config.sensors)
        assert [a.kind for a in config.actuators] == ["reaction_wheel"] * 3
        assert config.enable_drag and config.enable_srp


@pytest.mark.requires_basilisk
@pytest.mark.parametrize("template", [t for t in SPACECRAFT_TEMPLATES if t.build().fsw_mode == "sunSafePoint"],
                         ids=lambda t: t.name)
def test_sun_safe_preset_points_at_the_sun_at_the_default_step(template):
    """Flown as built, at SimSettings' default 10 s step: +Z settles on the
    Sun (70 s in a real run) and stays there."""
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.schema.scenario import GravityConfig, Scenario, SimSettings

    spacecraft = template.build()
    spacecraft.name = "sat-1"
    scenario = Scenario(name=template.name, epoch_utc="2030-01-01T00:00:00", simulation_mode="full_attitude",
                        gravity=GravityConfig(central_body="earth", central_body_degree=2,
                                              third_body_perturbers=["sun"]),
                        sim_settings=SimSettings(duration_days=20.0 / 1440.0), spacecraft=[spacecraft])  # [day]
    sun = SimulationService(scenario).run().series["sat-1.sun_heading_body"]
    assert sun.data[sun.time_s >= 300.0, 2].min() > 0.99  # [-] +Z on the Sun from 5 minutes on
