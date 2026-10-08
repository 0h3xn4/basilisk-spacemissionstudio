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

"""Tests for gui.lifetime_widget (the End of Life tab)."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_gui

_TEMPLATE_18 = (Path(__file__).resolve().parents[2] / "spacemissionstudio" / "scenarios" / "templates"
                / "18_leo_station_keeping.json")


def _scenario(altitude_km=550.0):
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(_TEMPLATE_18)
    scenario.spacecraft[0].orbit.semi_major_axis_km = 6378.1366 + altitude_km  # [km]
    return scenario


def test_the_last_run_choice_waits_for_a_finished_run(qtbot):
    """'End of last run' is offered only once a run has finished."""
    from spacemissionstudio.engine.results import ResultSet
    from spacemissionstudio.gui.lifetime_widget import _FROM_LAST_RUN, LifetimeWidget

    widget = LifetimeWidget()
    qtbot.addWidget(widget)
    assert not widget.compute_button.isEnabled()
    widget.set_scenario(_scenario())
    assert [widget.spacecraft_combo.itemText(i) for i in range(widget.spacecraft_combo.count())] == ["leo-sat-1"]
    last_run = widget.from_combo.model().item(widget.from_combo.findText(_FROM_LAST_RUN))
    assert not last_run.isEnabled()
    widget.set_last_run(_scenario(), ResultSet(scenario_name="s"))
    assert last_run.isEnabled() and widget.compute_button.isEnabled()
    widget.set_scenario(None)
    assert widget.spacecraft_combo.count() == 0 and not widget.compute_button.isEnabled()


def test_the_chart_draws_years_and_months(qtbot):
    """The altitude chart paints a decades-long and a months-long decay."""
    from spacemissionstudio.gui.lifetime_widget import AltitudeChart

    chart = AltitudeChart()
    qtbot.addWidget(chart)
    chart.resize(500, 260)
    for years in ([0.0, 6.0, 12.0], [0.0, 0.1, 0.25]):  # [year]
        chart.set_data(years, [550.0, 400.0, 120.0], [560.0, 410.0, 125.0], 120.0, 30.0)  # [km]
        assert not chart.grab().isNull()
    chart.clear()
    assert not chart.grab().isNull()


@pytest.mark.requires_basilisk
def test_an_estimate_shows_the_reentry_and_the_rule_badges(qtbot):
    """550 km with a burn down to a 250 km perigee: re-entry within months,
    both disposal rules met, the burn's delta-V on a tile."""
    from PySide6.QtWidgets import QLabel

    from spacemissionstudio.gui.lifetime_widget import LifetimeWidget

    widget = LifetimeWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(_scenario())
    widget.deorbit_check.setChecked(True)
    widget.compute()
    qtbot.waitUntil(lambda: widget.tiles_row.count() > 0, timeout=60000)
    texts = [w.text() for w in widget.findChildren(QLabel)]
    assert "5-year rule: met" in texts and "25-year guideline: met" in texts
    assert any(text.endswith("m/s, 0.67 kg") for text in texts)
    assert any(text.endswith("days") for text in texts)


def test_the_drag_coefficient_defaults_to_ad10s_end_of_life_value(qtbot, monkeypatch):
    """Cd 2.2 (AD10 Sec. 5.2, end of life) unless "the spacecraft's own" is
    picked (templates fly at 3.0, the operations value)."""
    from spacemissionstudio.engine import lifetime
    from spacemissionstudio.gui.lifetime_widget import LifetimeWidget

    asked = []

    def fake_end_of_life(*_args, drag_coeff=None, **_kwargs):
        asked.append(drag_coeff)
        raise lifetime.LifetimeError("stub")

    monkeypatch.setattr(lifetime, "end_of_life", fake_end_of_life)
    widget = LifetimeWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(_scenario())
    for index, expected in ((0, 2.2), (1, None)):
        widget.drag_combo.setCurrentIndex(index)
        widget.compute()
        qtbot.waitUntil(lambda: widget._worker is None, timeout=10000)
        assert asked[-1] == expected
