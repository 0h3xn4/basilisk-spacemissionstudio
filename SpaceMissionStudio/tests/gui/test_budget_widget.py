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

"""Tests for gui.budget_widget (the AD10 budget inputs and table)."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_gui

_TEMPLATE_18 = (Path(__file__).resolve().parents[2] / "spacemissionstudio" / "scenarios" / "templates"
                / "18_leo_station_keeping.json")


def test_budget_inputs_round_trip(qtbot):
    """Every input survives the form, including "from last run" (None)."""
    from spacemissionstudio.gui.budget_widget import BudgetInputsGroup
    from spacemissionstudio.schema.scenario import PropellantBudgetConfig

    config = PropellantBudgetConfig(mission_years=7.0, tank_capacity_kg=12.5, isp_s=220.0, thrust_angle_deg=5.0,
                                    injection_sma_error_km=3.0, collision_avoidance_count=6.0,
                                    in_plane_control_delta_v_m_s=None, out_of_plane_control_delta_v_m_s=4.0,
                                    disposal="graveyard", clearance_sma_drop_km=5.0)
    group = BudgetInputsGroup(config)
    qtbot.addWidget(group)
    assert group.to_config() == config
    group.setChecked(False)
    assert group.to_config() is None
    assert BudgetInputsGroup(None).to_config() is None


def test_the_spacecraft_editor_keeps_the_budget(qtbot):
    """Opening a spacecraft with budget inputs and pressing OK keeps them."""
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema import load_scenario
    from spacemissionstudio.schema.scenario import PropellantBudgetConfig

    spacecraft = load_scenario(_TEMPLATE_18).spacecraft[0]
    spacecraft.propellant_budget = PropellantBudgetConfig(collision_avoidance_count=3.0)
    dialog = SpacecraftEditorDialog(spacecraft)
    qtbot.addWidget(dialog)
    assert dialog.to_dataclass().propellant_budget == spacecraft.propellant_budget


@pytest.mark.requires_basilisk
def test_the_budget_tab_shows_the_table(qtbot):
    """Template 18 at 400 km (no disposal burn needed): rows per phase and
    a total, with the collision-avoidance count noted as missing."""
    from spacemissionstudio.gui.budget_widget import BudgetWidget
    from spacemissionstudio.schema import load_scenario
    from spacemissionstudio.schema.scenario import PropellantBudgetConfig

    scenario = load_scenario(_TEMPLATE_18)
    scenario.spacecraft[0].propellant_budget = PropellantBudgetConfig(in_plane_control_delta_v_m_s=100.0)
    widget = BudgetWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(scenario)
    widget.compute()
    qtbot.waitUntil(lambda: widget.table.rowCount() > 0, timeout=120000)
    contributors = [widget.table.item(r, 1).text() for r in range(widget.table.rowCount())]
    assert "In-plane orbit control" in contributors and "Residual" in contributors
    assert widget.totals_label.text().startswith("Total: ")
    assert "DRAMA" in widget.notes_label.text()
