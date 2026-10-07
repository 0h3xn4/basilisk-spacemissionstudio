"""Tests for gui.formation_diagram_widget.FormationDiagramWidget."""

import pytest

pytestmark = pytest.mark.requires_gui


def _diagram(**overrides):
    from spacemissionstudio.engine.scenario_explainer import FormationDiagram

    defaults = dict(chief_name="chief-1", follower_name="follower-1", target_separation_km=50.0,
                     tolerance_fraction=0.10, restore_tolerance_fraction=0.02)
    defaults.update(overrides)
    return FormationDiagram(**defaults)


def test_no_diagram_collapses_to_zero_height(qtbot):
    from spacemissionstudio.gui.formation_diagram_widget import FormationDiagramWidget

    widget = FormationDiagramWidget()
    qtbot.addWidget(widget)
    assert widget.height() == 0
    assert widget.sizeHint().height() == 0


def test_setting_a_diagram_gives_the_widget_real_height(qtbot):
    from spacemissionstudio.gui.formation_diagram_widget import FormationDiagramWidget

    widget = FormationDiagramWidget()
    qtbot.addWidget(widget)
    widget.set_diagram(_diagram())
    assert widget.height() > 0
    assert widget.sizeHint().height() > 0


def test_clearing_a_diagram_collapses_back_to_zero_height(qtbot):
    from spacemissionstudio.gui.formation_diagram_widget import FormationDiagramWidget

    widget = FormationDiagramWidget()
    qtbot.addWidget(widget)
    widget.set_diagram(_diagram())
    widget.set_diagram(None)
    assert widget.height() == 0


def test_paints_without_raising_for_a_range_of_tolerance_fractions(qtbot):
    """The real regression risk here: dividing by target_separation_km or
    drawing a band wider than the track for an unusual (but legal)
    combination of fields could raise or draw garbage. Exercises paintEvent
    directly (via grab()) across small/large separations and tolerances.
    """
    from spacemissionstudio.gui.formation_diagram_widget import FormationDiagramWidget

    widget = FormationDiagramWidget()
    qtbot.addWidget(widget)
    widget.resize(480, 110)

    for target_separation_km, tolerance_fraction, restore_tolerance_fraction in [
        (50.0, 0.10, 0.02),
        (1.0, 0.5, 0.1),
        (10000.0, 0.01, 0.001),
        (100.0, 0.99, 0.01),
    ]:
        widget.set_diagram(_diagram(target_separation_km=target_separation_km,
                                     tolerance_fraction=tolerance_fraction,
                                     restore_tolerance_fraction=restore_tolerance_fraction))
        pixmap = widget.grab()
        assert not pixmap.isNull()


def test_constructor_accepts_an_initial_diagram(qtbot):
    from spacemissionstudio.gui.formation_diagram_widget import FormationDiagramWidget

    widget = FormationDiagramWidget(_diagram())
    qtbot.addWidget(widget)
    assert widget.height() > 0
