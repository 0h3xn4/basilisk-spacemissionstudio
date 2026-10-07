"""Confirms every template in spacemissionstudio/scenarios/templates/ actually
round-trips through the GUI's own ScenarioEditorWidget -- the primary way
a user is expected to open one (File > Open) -- not just through
schema.scenario.load_scenario()/validate() directly (see
tests/test_scenario_templates.py for that Basilisk-free layer).
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_gui

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "spacemissionstudio" / "scenarios" / "templates"
_TEMPLATE_PATHS = sorted(_TEMPLATES_DIR.glob("*.json"))


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_template_round_trips_through_scenario_editor_widget(qtbot, path):
    from spacemissionstudio.gui.scenario_editor import ScenarioEditorWidget
    from spacemissionstudio.schema import load_scenario

    widget = ScenarioEditorWidget()
    qtbot.addWidget(widget)

    scenario = load_scenario(path)
    widget.from_scenario(scenario)
    assert "✓" in widget.validation_label.text(), widget.validation_label.text()

    got = widget.to_scenario()
    assert got.to_dict() == scenario.to_dict()


def _assert_same_values(original, got, where=""):
    """Recursive dataclass/list/dict comparison with a tight float tolerance
    (the editors store values to 10 decimals -- see gui.widgets).
    """
    import dataclasses
    import math

    if dataclasses.is_dataclass(original):
        for field in dataclasses.fields(original):
            _assert_same_values(getattr(original, field.name), getattr(got, field.name), f"{where}.{field.name}")
    elif isinstance(original, (list, tuple)):
        assert len(original) == len(got), where
        for index, (a, b) in enumerate(zip(original, got)):
            _assert_same_values(a, b, f"{where}[{index}]")
    elif isinstance(original, dict):
        for key, value in original.items():
            assert key in got, f"{where}[{key!r}] was dropped"
            _assert_same_values(value, got[key], f"{where}[{key!r}]")
    elif isinstance(original, float) and not isinstance(original, bool):
        assert math.isclose(original, got, rel_tol=1e-8, abs_tol=1e-10), f"{where}: {original!r} -> {got!r}"
    else:
        assert original == got, f"{where}: {original!r} -> {got!r}"


@pytest.mark.parametrize("path", _TEMPLATE_PATHS, ids=lambda p: p.name)
def test_opening_then_okaying_every_editor_leaves_template_values_unchanged(qtbot, path):
    """Regression test for a real data-change bug found by audit: a plain
    QDoubleSpinBox rounds every value to its DISPLAY precision when set, so
    just opening an editor on an existing spacecraft and clicking OK, with
    no edits at all, rewrote e.g. template 13's 0.00667 kg*m^2 inertia as
    0.007 and its 2-hour (0.08333 day) duration as 0.0833. Exercises every
    spacecraft/sensor/actuator/propagation/ground-station/dispersion dialog
    on every bundled template. (Keys an editor ADDS with Basilisk's own
    default value, e.g. a zero IMU bias, are deliberately allowed -- only
    values already in the file must survive unchanged.)
    """
    from spacemissionstudio.gui.ground_station_editor import GroundStationEditorDialog
    from spacemissionstudio.gui.monte_carlo_editor import _DispersionEditorDialog
    from spacemissionstudio.gui.propagation_setup_dialog import PropagationSetupDialog
    from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema import load_scenario
    from spacemissionstudio.schema.scenario import (
        SUPPORTED_ACTUATOR_KINDS,
        SUPPORTED_SENSOR_KINDS,
        ActuatorConfig,
        SensorConfig,
    )

    scenario = load_scenario(path)
    names = [sc.name for sc in scenario.spacecraft]
    station_names = [gs.name for gs in scenario.ground_stations]

    for craft in scenario.spacecraft:
        dialog = SpacecraftEditorDialog(config=craft, other_spacecraft_names=[n for n in names if n != craft.name],
                                        ground_station_names=station_names)
        qtbot.addWidget(dialog)
        _assert_same_values(craft, dialog.to_dataclass(), craft.name)
        for item, cls, kinds in ([(s, SensorConfig, SUPPORTED_SENSOR_KINDS) for s in craft.sensors]
                                 + [(a, ActuatorConfig, SUPPORTED_ACTUATOR_KINDS) for a in craft.actuators]):
            item_dialog = _ItemEditorDialog(cls, kinds, item=item)
            qtbot.addWidget(item_dialog)
            _assert_same_values(item, item_dialog.to_dataclass(), f"{craft.name}.{item.name}")

    propagation = PropagationSetupDialog(scenario.gravity, scenario.sim_settings, scenario.space_weather)
    qtbot.addWidget(propagation)
    _assert_same_values(scenario.gravity, propagation.to_gravity(), "gravity")
    _assert_same_values(scenario.sim_settings, propagation.to_sim_settings(), "sim_settings")
    _assert_same_values(scenario.space_weather, propagation.to_space_weather(), "space_weather")

    for station in scenario.ground_stations:
        station_dialog = GroundStationEditorDialog(station)
        qtbot.addWidget(station_dialog)
        _assert_same_values(station, station_dialog.to_dataclass(), station.name)

    for dispersion in scenario.monte_carlo.dispersions:
        dispersion_dialog = _DispersionEditorDialog(names, item=dispersion)
        qtbot.addWidget(dispersion_dialog)
        _assert_same_values(dispersion, dispersion_dialog.to_dataclass(), "dispersion")
