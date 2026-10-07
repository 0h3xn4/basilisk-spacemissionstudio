"""Tests for spacemissionstudio.engine.scenario_explainer -- no Basilisk
import, runs anywhere.
"""

from pathlib import Path

import pytest

from spacemissionstudio.engine.scenario_explainer import Badge, explain
from spacemissionstudio.schema import load_scenario
from spacemissionstudio.schema.scenario import (
    GravityConfig,
    OrbitIC,
    PhasingKeepingConfig,
    Scenario,
    SpacecraftConfig,
    StationKeepingConfig,
)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
_TEMPLATE_PATHS = sorted(_TEMPLATES_DIR.glob("*.json"))

# Generous ceiling -- a cheap, permanent regression guard against this
# quietly regrowing into prose or a bullet wall later (see this module's
# own docstring: every string here must be ONE short, scannable fragment).
_MAX_STRING_LEN = 90


def _single_spacecraft_scenario(**orbit_overrides) -> Scenario:
    orbit_defaults = dict(
        type="classical_elements", semi_major_axis_km=7000.0, eccentricity=0.001,
        inclination_deg=51.6, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0,
    )
    orbit_defaults.update(orbit_overrides)
    return Scenario(
        name="point-mass test",
        epoch_utc="2030-01-01T00:00:00",
        spacecraft=[SpacecraftConfig(name="sat-1", orbit=OrbitIC(**orbit_defaults))],
    )


def test_zero_spacecraft_scenario_does_not_raise():
    scenario = Scenario(name="empty", epoch_utc="2030-01-01T00:00:00", spacecraft=[])
    explanation = explain(scenario)
    assert explanation.headline == "empty"
    assert explanation.spacecraft_table == []


def test_trivial_scenario_produces_short_tiles_and_no_table():
    explanation = explain(_single_spacecraft_scenario())
    assert len(explanation.stat_tiles) >= 3
    assert explanation.spacecraft_table == []
    labels = {tile.label for tile in explanation.stat_tiles}
    assert "Spacecraft" in labels
    assert "Duration" in labels
    assert "Gravity" in labels


def test_degree_10_sun_moon_gravity_shows_up_as_a_tile():
    scenario = _single_spacecraft_scenario()
    scenario.gravity = GravityConfig(central_body="earth", central_body_degree=10,
                                      third_body_perturbers=["sun", "moon"])
    explanation = explain(scenario)
    gravity_tile = next(t for t in explanation.stat_tiles if t.label == "Gravity")
    assert "10" in gravity_tile.value
    assert gravity_tile.value == "Degree-10 Earth + Sun/Moon"  # body names capitalised


def test_sso_detection_fires_at_the_real_reference_point():
    # 97.40 deg at 6878.1366 km altitude -- the same reference value
    # engine.orbit_design.sun_synchronous_inclination_deg's own docstring
    # verifies against.
    from spacemissionstudio.schema.scenario import GravityConfig

    scenario = _single_spacecraft_scenario(semi_major_axis_km=6878.1366, inclination_deg=97.40)
    scenario.gravity = GravityConfig(central_body="earth", central_body_degree=2)
    explanation = explain(scenario)
    orbit_tile = next(t for t in explanation.stat_tiles if t.label == "Orbit")
    assert "SSO" in orbit_tile.value
    env_section = next((s for s in explanation.sections if s.title == "Environment"), None)
    assert env_section is not None
    assert any(b.label == "Sun-synchronous" for b in env_section.badges)


def test_sso_detection_does_not_fire_for_an_unrelated_inclination():
    explanation = explain(_single_spacecraft_scenario(semi_major_axis_km=6878.1366, inclination_deg=51.6))
    orbit_tile = next(t for t in explanation.stat_tiles if t.label == "Orbit")
    assert "SSO" not in orbit_tile.value
    env_section = next((s for s in explanation.sections if s.title == "Environment"), None)
    assert env_section is None or not any(b.label == "Sun-synchronous" for b in env_section.badges)


def test_template_05_shaped_chief_follower_pair_produces_spacecraft_table():
    chief = SpacecraftConfig(
        name="chief-1",
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                       inclination_deg=97.59, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
        station_keeping=StationKeepingConfig(target_altitude_km=550.0, deadband_km=15.0, thrust_n=0.05,
                                              isp_s=1500.0, propellant_kg=5.0),
    )
    follower = SpacecraftConfig(
        name="follower-1",
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                       inclination_deg=97.59, raan_deg=0.0, arg_periapsis_deg=0.0,
                       anomaly_type="mean", mean_anomaly_deg=0.413509),
        station_keeping=StationKeepingConfig(target_altitude_km=550.0, deadband_km=15.0, thrust_n=0.05,
                                              isp_s=1500.0, propellant_kg=5.0),
        phasing_keeping=PhasingKeepingConfig(chief_spacecraft="chief-1", target_separation_km=[50.0]),
    )
    scenario = Scenario(name="formation", epoch_utc="2030-01-01T00:00:00", spacecraft=[chief, follower])

    explanation = explain(scenario)
    assert len(explanation.spacecraft_table) == 2
    names = {row.name for row in explanation.spacecraft_table}
    assert names == {"chief-1", "follower-1"}

    formation_section = next(s for s in explanation.sections if s.title == "Formation / orbit maintenance")
    badge_labels = {b.label for b in formation_section.badges}
    assert "Station-keeping" in badge_labels
    assert "Phasing-keeping" in badge_labels
    assert formation_section.notes == []  # both spacecraft DO have station_keeping -- no warning note

    assert len(explanation.formation_diagrams) == 1
    diagram = explanation.formation_diagrams[0]
    assert diagram.chief_name == "chief-1"
    assert diagram.follower_name == "follower-1"
    assert diagram.target_separation_km == 50.0
    assert diagram.tolerance_fraction == 0.10
    assert diagram.restore_tolerance_fraction == 0.02


def test_formation_diagram_uses_the_first_entry_of_a_multi_step_schedule():
    chief = SpacecraftConfig(name="chief-1", orbit=OrbitIC(
        type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
        inclination_deg=97.59, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0))
    follower = SpacecraftConfig(
        name="follower-1",
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                       inclination_deg=97.59, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
        phasing_keeping=PhasingKeepingConfig(chief_spacecraft="chief-1", target_separation_km=[1000.0, 500.0, 100.0]),
    )
    scenario = Scenario(name="constellation", epoch_utc="2030-01-01T00:00:00", spacecraft=[chief, follower])

    explanation = explain(scenario)
    assert len(explanation.formation_diagrams) == 1
    assert explanation.formation_diagrams[0].target_separation_km == 1000.0  # the FIRST (current) step


def test_no_formation_diagram_without_phasing_keeping():
    scenario = _single_spacecraft_scenario()
    explanation = explain(scenario)
    assert explanation.formation_diagrams == []


def test_phasing_keeping_without_station_keeping_surfaces_a_note():
    chief = SpacecraftConfig(name="chief-1", orbit=OrbitIC(
        type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
        inclination_deg=97.59, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0))
    follower = SpacecraftConfig(
        name="follower-1",
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                       inclination_deg=97.59, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
        phasing_keeping=PhasingKeepingConfig(chief_spacecraft="chief-1", target_separation_km=[50.0]),
    )
    scenario = Scenario(name="formation", epoch_utc="2030-01-01T00:00:00", spacecraft=[chief, follower])

    explanation = explain(scenario)
    formation_section = next(s for s in explanation.sections if s.title == "Formation / orbit maintenance")
    assert formation_section.notes  # follower-1 has phasing_keeping but no station_keeping
    assert "follower-1" in formation_section.notes[0]


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_explain_does_not_raise_on_any_bundled_template(path):
    scenario = load_scenario(path)
    explanation = explain(scenario)
    assert explanation.headline  # every bundled template has a real name


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_every_string_in_the_explanation_stays_short(path):
    """Permanent regression guard: this module's whole design point is
    terse, scannable fragments, not prose -- a real user explicitly
    rejected two earlier, more verbose designs before this one. Checked
    against every real bundled template, not just synthetic cases.
    """
    scenario = load_scenario(path)
    explanation = explain(scenario)
    for tile in explanation.stat_tiles:
        assert len(tile.value) <= _MAX_STRING_LEN, f"{tile.label}: {tile.value!r}"
    for section in explanation.sections:
        for badge in section.badges:
            assert len(badge.label) <= _MAX_STRING_LEN, f"{section.title}: {badge.label!r}"
        for note in section.notes:
            assert len(note) <= 220, f"{section.title} note too long: {note!r}"  # notes allow a bit more
    for row in explanation.spacecraft_table:
        for column, value in row.facts.items():
            assert len(value) <= _MAX_STRING_LEN, f"{row.name}.{column}: {value!r}"


def test_explain_never_raises_even_on_a_scenario_missing_its_own_schema_defaults():
    # A somewhat pathological but legal input -- an empty-string name and
    # no spacecraft -- exercising the try/except wrapper directly rather
    # than only via well-formed inputs.
    scenario = Scenario(name="", epoch_utc="", spacecraft=[])
    explanation = explain(scenario)
    assert isinstance(explanation.headline, str)


def test_badge_default_kind_is_neutral():
    assert Badge("x").kind == "neutral"


def _template_scenario(prefix):
    return load_scenario(next((Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios"
                               / "templates").glob(f"{prefix}_*.json")))


def test_identical_spacecraft_share_one_table_row():
    """A 6-satellite constellation used to repeat the same row six times."""
    rows = explain(_template_scenario("04")).spacecraft_table
    assert len(rows) == 1
    assert rows[0].name == "leo-01-01 ... leo-02-03 (6)"


def test_badges_use_plain_names_and_reserve_status_colours():
    """Real user feedback on clutter: Drag/SRP badges were in the warning
    colour and power/RF in the success colour, though neither is a state;
    attitude modes showed code names; stations were a count plus a list."""
    every_badge = []
    for path in sorted((Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios"
                        / "templates").glob("*.json")):
        for section in explain(load_scenario(path)).sections:
            if section.title == "Check before running":  # a real state: the one place warning colour belongs
                assert {badge.kind for badge in section.badges} == {"warning"}
            else:
                every_badge += section.badges
            for note in section.notes:
                assert "_" not in note, note  # no code names in notes either
    assert {badge.kind for badge in every_badge} <= {"accent", "neutral"}
    labels = {badge.label for badge in every_badge}
    assert not labels & {"inertial3D", "hillPoint", "velocityPoint", "sunSafePoint", "locationPointing"}
    assert "Sun pointing" in labels
    stations = next(s for s in explain(_template_scenario("19")).sections if s.title == "Ground stations")
    assert [b.label for b in stations.badges] == ["berlin-gs"]
    assert stations.notes == ["berlin-gs: 2 passes, first at 10 min (peak 61 deg)"]


def test_sso_inclination_without_oblateness_is_not_called_sun_synchronous():
    """The precession that makes an orbit Sun-synchronous comes from J2;
    templates 01/09/10/12 use a Sun-synchronous inclination with point-mass
    gravity, where the plane never turns -- the badge would be a false claim."""
    explanation = explain(_single_spacecraft_scenario(semi_major_axis_km=6878.1366, inclination_deg=97.40))
    orbit_tile = next(t for t in explanation.stat_tiles if t.label == "Orbit")
    assert orbit_tile.value.startswith("Classical")
    env_section = next((s for s in explanation.sections if s.title == "Environment"), None)
    assert env_section is None or not any(b.label == "Sun-synchronous" for b in env_section.badges)


def test_checks_section_comes_first_and_flags_a_late_first_pass():
    """Template 19 used to start at midnight UTC: its first Berlin pass came
    8.2 h into a 12 h run, so users saw "never" any contact. The Explain tab
    now says so before the run."""
    scenario = _template_scenario("19")
    scenario.epoch_utc = "2030-01-01T00:00:00"
    scenario.sim_settings.duration_days = 0.5
    sections = explain(scenario).sections
    assert sections[0].title == "Check before running"
    assert sections[0].notes == ["berlin-gs: the first pass only comes at 8.2 h of a 12.0 h run"]
    assert all(s.title != "Check before running" for s in explain(_template_scenario("19")).sections)


def test_duration_tile_uses_a_readable_unit():
    """Template 19's 2 h 15 min run showed as "0.09375 d"."""
    from spacemissionstudio.engine.scenario_explainer import _duration_label

    assert [_duration_label(d) for d in (0.01, 0.09375, 0.5, 14.0)] == ["14.4 min", "2.25 h", "12 h", "14 d"]
    tile = next(t for t in explain(_template_scenario("19")).stat_tiles if t.label == "Duration")
    assert tile.value == "2.25 h"
