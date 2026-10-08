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


def _stub_sweep(sweep=None, **kwargs):
    """A launch-delay sweep of template 18 with stubbed drag (2031 the worst)
    and no disposal burn: no Basilisk needed."""
    from types import SimpleNamespace

    from spacemissionstudio.engine import propellant_budget as pb
    from spacemissionstudio.schema import load_scenario

    drag = {2030: 100.0, 2031: 300.0, 2032: 200.0, 2033: 150.0, 2034: 120.0, 2035: 110.0}  # [m/s]
    return (sweep or pb.launch_delay_sweep)(
        load_scenario(_TEMPLATE_18), "leo-sat-1", reentry_solver=lambda *_a: (0.0, 400.0, 0.5, []),
        makeup=lambda _s, _sc, start, *_a, **_k: SimpleNamespace(delta_v_m_s=drag[start.year], altitude_km=400.0,
                                                                 warnings=[]), **kwargs)


def test_the_sweep_table_marks_the_worst_launch_and_shows_its_budget(qtbot):
    """One row per launch date; the worst (2031 here) is bold and its budget
    fills the main table; picking another row shows that one."""
    from spacemissionstudio.gui.budget_widget import BudgetWidget

    widget = BudgetWidget()
    qtbot.addWidget(widget)
    assert not widget.sweep_group.isVisibleTo(widget)
    widget._show_sweep(_stub_sweep())
    assert widget.sweep_group.isVisibleTo(widget)
    assert widget.sweep_table.rowCount() == 6
    assert widget.sweep_table.item(1, 0).text() == "2031-01-01 (worst)" and widget.sweep_table.item(1, 0).font().bold()
    assert not widget.sweep_table.item(0, 0).font().bold()
    in_plane = next(r for r in range(widget.table.rowCount())
                    if widget.table.item(r, 1).text() == "In-plane orbit control")
    assert widget.table.item(in_plane, 2).text() == "300.00"
    assert widget.status_label.text().startswith("Launch 2031-01-01 (1 year late)")
    widget.sweep_table.selectRow(0)
    assert widget.table.item(in_plane, 2).text() == "100.00"
    assert "worst case: launch 2031-01-01" in widget.sweep_notes_label.text()


def test_the_sweep_button_runs_in_the_background_and_reports_progress(qtbot, monkeypatch):
    """"Launch delays" runs the sweep on a worker thread with progress, and
    reads "Cancel" while it runs."""
    from spacemissionstudio.engine import propellant_budget as pb
    from spacemissionstudio.gui.budget_widget import BudgetWidget
    from spacemissionstudio.schema import load_scenario

    seen = []
    original = pb.launch_delay_sweep
    monkeypatch.setattr(pb, "launch_delay_sweep", lambda *_a, progress=None, should_cancel=None: _stub_sweep(
        original, progress=lambda f, label: (seen.append(label), progress(f, label))))
    widget = BudgetWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(load_scenario(_TEMPLATE_18))
    widget.sweep_button.click()
    assert widget.sweep_button.text() == "Cancel"
    qtbot.waitUntil(lambda: widget.sweep_table.rowCount() == 6, timeout=30000)
    qtbot.waitUntil(lambda: widget._worker is None, timeout=30000)
    assert widget.sweep_button.text() == "Launch delays"
    assert "drag for the planned launch" in seen and seen[-1] == "done"
