"""Tests for gui.scenario_explainer_widget.ScenarioExplainerWidget."""

import pytest

pytestmark = pytest.mark.requires_gui


def _rich_scenario():
    from spacemissionstudio.schema.scenario import (
        OrbitIC,
        PhasingKeepingConfig,
        Scenario,
        SpacecraftConfig,
        StationKeepingConfig,
    )

    chief = SpacecraftConfig(
        name="chief-1",
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                       inclination_deg=97.59, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
        station_keeping=StationKeepingConfig(target_altitude_km=550.0, deadband_km=15.0, thrust_n=0.05,
                                              isp_s=1500.0, propellant_kg=5.0),
        enable_drag=True,
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
    return Scenario(name="formation test", epoch_utc="2030-01-01T00:00:00", spacecraft=[chief, follower])


def _trivial_scenario():
    from spacemissionstudio.schema.scenario import OrbitIC, Scenario, SpacecraftConfig

    return Scenario(
        name="trivial", epoch_utc="2030-01-01T00:00:00",
        spacecraft=[SpacecraftConfig(name="sat-1", orbit=OrbitIC(
            type="classical_elements", semi_major_axis_km=7000.0, eccentricity=0.001,
            inclination_deg=51.6, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0))],
    )


def test_none_scenario_shows_placeholder_without_raising(qtbot):
    from spacemissionstudio.gui.scenario_explainer_widget import ScenarioExplainerWidget

    widget = ScenarioExplainerWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(None)
    assert not widget._placeholder_label.isHidden()
    assert widget._headline_label.isHidden()
    assert widget._tiles_row.count() == 0
    assert widget._table.isHidden()


def test_rich_scenario_renders_tiles_badges_and_table(qtbot):
    from spacemissionstudio.gui.scenario_explainer_widget import ScenarioExplainerWidget

    widget = ScenarioExplainerWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(_rich_scenario())

    assert widget._placeholder_label.isHidden()
    assert not widget._headline_label.isHidden()
    assert widget._headline_label.text() == "formation test"
    # tiles_row ends with a stretch item, so count > 0 is the real signal
    assert widget._tiles_row.count() > 0
    assert widget._sections_layout.count() > 0
    assert not widget._table.isHidden()
    assert widget._table.rowCount() == 2


def test_rich_scenario_renders_a_formation_diagram(qtbot):
    from spacemissionstudio.gui.formation_diagram_widget import FormationDiagramWidget
    from spacemissionstudio.gui.scenario_explainer_widget import ScenarioExplainerWidget

    widget = ScenarioExplainerWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(_rich_scenario())

    diagrams = widget.findChildren(FormationDiagramWidget)
    assert len(diagrams) == 1
    assert diagrams[0].height() > 0  # it was actually given a diagram, not left empty


def test_trivial_scenario_has_no_formation_diagram(qtbot):
    from spacemissionstudio.gui.formation_diagram_widget import FormationDiagramWidget
    from spacemissionstudio.gui.scenario_explainer_widget import ScenarioExplainerWidget

    widget = ScenarioExplainerWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(_trivial_scenario())

    assert widget.findChildren(FormationDiagramWidget) == []


def test_switching_from_rich_to_trivial_removes_the_formation_diagram(qtbot):
    from spacemissionstudio.gui.formation_diagram_widget import FormationDiagramWidget
    from spacemissionstudio.gui.scenario_explainer_widget import ScenarioExplainerWidget

    widget = ScenarioExplainerWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(_rich_scenario())
    assert len(widget.findChildren(FormationDiagramWidget)) == 1

    widget.set_scenario(_trivial_scenario())
    qtbot.wait(10)  # deleteLater() is deferred to the next event loop pass, not immediate
    assert widget.findChildren(FormationDiagramWidget) == []


def test_trivial_scenario_renders_no_table_and_fewer_badges_than_rich(qtbot):
    from spacemissionstudio.gui.scenario_explainer_widget import ScenarioExplainerWidget

    widget = ScenarioExplainerWidget()
    qtbot.addWidget(widget)

    widget.set_scenario(_trivial_scenario())
    assert widget._table.isHidden()
    trivial_sections = widget._sections_layout.count()

    widget.set_scenario(_rich_scenario())
    rich_sections = widget._sections_layout.count()
    assert not widget._table.isHidden()

    assert rich_sections >= trivial_sections


def test_switching_between_scenarios_clears_previous_table(qtbot):
    from spacemissionstudio.gui.scenario_explainer_widget import ScenarioExplainerWidget

    widget = ScenarioExplainerWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(_rich_scenario())
    assert widget._table.rowCount() == 2

    widget.set_scenario(_trivial_scenario())
    assert widget._table.rowCount() == 0
    assert widget._table.isHidden()


def test_set_scenario_none_after_rich_hides_everything(qtbot):
    from spacemissionstudio.gui.scenario_explainer_widget import ScenarioExplainerWidget

    widget = ScenarioExplainerWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(_rich_scenario())
    widget.set_scenario(None)
    assert not widget._placeholder_label.isHidden()
    assert widget._tiles_row.count() == 0
    assert widget._sections_layout.count() == 0
    assert widget._table.isHidden()


def test_table_is_not_cut_off_in_a_narrow_pane(qtbot):
    """In a narrow pane the table scrolls sideways; its height must then
    include the scroll bar, or the last row is hidden behind it."""
    from pathlib import Path

    from spacemissionstudio.gui.scenario_explainer_widget import ScenarioExplainerWidget
    from spacemissionstudio.schema import load_scenario

    templates = Path(__file__).resolve().parents[2] / "spacemissionstudio" / "scenarios" / "templates"
    widget = ScenarioExplainerWidget()
    qtbot.addWidget(widget)
    widget.setFixedSize(420, 760)  # [px] narrow pane, set before the scenario arrives (as in the app)
    widget.show()
    qtbot.waitExposed(widget)
    widget.set_scenario(load_scenario(next(templates.glob("05_*.json"))))
    qtbot.wait(50)  # [ms] let the layout settle
    table = widget._table
    assert table.horizontalScrollBar().isVisible(), "precondition: the pane should be narrower than the table"
    rows_height = sum(table.rowHeight(r) for r in range(table.rowCount()))
    visible = table.viewport().height()
    assert visible >= rows_height, (visible, rows_height)
    assert not table.verticalScrollBar().isVisible()
