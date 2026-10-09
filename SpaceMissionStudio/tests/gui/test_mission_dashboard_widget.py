"""Tests for gui.mission_dashboard_widget.MissionDashboardWidget -- uses
synthetic ResultSet/Scenario data, no Basilisk needed. Checks the widget's
own QLabel/QProgressBar/badge state directly, the same convention
tests/gui/test_results_widget.py already uses for its own widget.
"""

import numpy as np
import pytest

pytestmark = pytest.mark.requires_gui


def _scenario():
    from spacemissionstudio.schema.scenario import (
        CommsPointingConfig, GravityConfig, GroundStationConfig, OrbitIC, PowerConfig, RFLinkConfig,
        Scenario, SimSettings, SpacecraftConfig,
    )

    return Scenario(
        name="dashboard test", epoch_utc="2030-01-01T00:00:00", simulation_mode="full_attitude",
        gravity=GravityConfig(central_body="earth", third_body_perturbers=["sun"]),
        sim_settings=SimSettings(duration_days=0.1, dynamics_task_rate_s=1.0),
        ground_stations=[GroundStationConfig(
            name="gs-1", latitude_deg=40.0, longitude_deg=-105.0,
            rx_antenna_gain_dbi=35.0, system_noise_temp_k=150.0,
        )],
        spacecraft=[SpacecraftConfig(
            name="sat-1",
            orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,
                          inclination_deg=97.8, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
            power=PowerConfig(panel_area_m2=0.4, panel_efficiency=0.28, battery_capacity_wh=40.0),
            rf_link=RFLinkConfig(tx_power_w=5.0, frequency_hz=2.2e9, data_rate_bps=5.0e6,
                                  tx_antenna_gain_dbi=6.0, required_ebno_db=10.0, antenna_beamwidth_deg=30.0),
            comms_pointing=CommsPointingConfig(target_ground_station="gs-1", comms_power_w=15.0),
        )],
    )


def _result_set(active_mode, pointing_error_deg, has_access, slant_range_m, battery_charge_wh, net_power_w):
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    n = len(active_mode)
    t = np.linspace(0.0, float(n - 1), n)
    rs = ResultSet(scenario_name="dashboard test")
    rs.add(TimeSeries("sat-1.comms_pointing.active_mode", t, ("active_mode",),
                       np.asarray(active_mode, dtype=float), units="-"))
    rs.add(TimeSeries("sat-1.comms_pointing.pointing_error_deg", t, ("pointing_error_deg",),
                       np.asarray(pointing_error_deg, dtype=float), units="deg"))
    rs.add(TimeSeries("gs-1.access_to_sat-1.has_access", t, ("has_access",),
                       np.asarray(has_access, dtype=float), units="-"))
    rs.add(TimeSeries("gs-1.access_to_sat-1.slant_range", t, ("slant_range",),
                       np.asarray(slant_range_m, dtype=float), units="m"))
    rs.add(TimeSeries("sat-1.battery_charge", t, ("charge",),
                       np.asarray(battery_charge_wh, dtype=float), units="W*hr"))
    rs.add(TimeSeries("sat-1.battery_net_power", t, ("net_power",),
                       np.asarray(net_power_w, dtype=float), units="W"))
    return rs


@pytest.fixture
def widget(qtbot):
    from spacemissionstudio.gui.mission_dashboard_widget import MissionDashboardWidget

    w = MissionDashboardWidget()
    qtbot.addWidget(w)
    return w


def test_empty_state_shows_placeholder_and_hides_panels(widget):
    assert not widget._placeholder.isHidden()
    assert widget._state_box.isHidden()
    assert widget._attitude_box.isHidden()
    assert widget._power_box.isHidden()
    assert widget._rf_box.isHidden()


def test_set_result_none_restores_empty_state(widget):
    widget.set_result(_result_set([1], [2.0], [1], [1.0e6], [30.0], [5.0]), _scenario())
    assert widget._state_box.isHidden() is False

    widget.set_result(None)
    assert not widget._placeholder.isHidden()
    assert widget._state_box.isHidden()


def test_sun_pointing_mode_shows_success_badge_and_no_access(widget):
    result = _result_set(
        active_mode=[0, 0], pointing_error_deg=[1.0, 0.5], has_access=[0, 0],
        slant_range_m=[2.0e7, 2.0e7], battery_charge_wh=[35.0, 35.2], net_power_w=[8.0, 8.0],
    )
    widget.set_result(result, _scenario())

    assert widget.mode_badge.text() == "Sun-pointing"
    assert widget.visibility_badge.text() == "No ground station in view"
    assert widget.link_status_badge.text() == "No access"
    assert widget.tracking_badge.text() == "Converged"


def test_comms_pointing_mode_shows_accent_badge_and_visibility(widget):
    result = _result_set(
        active_mode=[0, 1], pointing_error_deg=[1.0, 3.0], has_access=[0, 1],
        slant_range_m=[2.0e7, 9.0e5], battery_charge_wh=[35.0, 33.0], net_power_w=[8.0, -10.0],
    )
    widget.set_result(result, _scenario())

    assert widget.mode_badge.text() == "Ground-station-pointing"
    assert widget.visibility_badge.text() == "In view of gs-1"
    assert "900.0 km" in widget.slant_range_label.text()


def test_real_access_without_mode_switch_shows_no_link_breakdown(widget):
    """Regression test for a real bug: has_access alone used to be enough
    to compute and show a full RF breakdown, even while the spacecraft was
    still Sun-pointing (active_mode == 0) -- i.e. its antenna was never
    actually pointed at the ground station at all. This contradicts
    engine.link_budget.link_margin_series()'s own gating (has_access AND
    active_mode), and showed a fabricated link margin right next to a
    "Sun-pointing" mode badge. The ground station being geometrically
    visible must not, by itself, produce a link breakdown.
    """
    result = _result_set(
        active_mode=[0], pointing_error_deg=[1.0], has_access=[1],
        slant_range_m=[1.0e6], battery_charge_wh=[35.0], net_power_w=[8.0],
    )
    widget.set_result(result, _scenario())

    assert widget.mode_badge.text() == "Sun-pointing"
    assert widget.link_status_badge.text() == "Not yet comms-pointing"
    assert widget.margin_label.text() == "--"
    assert widget.eirp_label.text() == "--"


def test_large_pointing_error_shows_slewing_badge_and_degraded_link(widget):
    """Right at a Sun-pointing -> ground-station-pointing transition, the
    arbitrator has already switched the attitude reference and has_access
    is already true, but the spacecraft hasn't physically slewed onto the
    new target yet -- a large pointing_error_deg should read as
    "Slewing" (not "Converged") and, with this template's 30 deg
    beamwidth, enough antenna-pointing loss to plausibly degrade the
    link -- confirms the dashboard surfaces exactly the "geometrically
    visible but not yet actually linked" distinction this feature's own
    link_margin_series gating was built for.
    """
    result = _result_set(
        active_mode=[1], pointing_error_deg=[60.0], has_access=[1],
        slant_range_m=[2.5e6], battery_charge_wh=[33.0], net_power_w=[-10.0],
    )
    widget.set_result(result, _scenario())

    assert widget.tracking_badge.text() == "Slewing"
    assert widget.link_status_badge.text() == "Link degraded"
    assert widget.margin_label.text() != "--"


def test_battery_soc_bar_reflects_capacity_when_scenario_given(widget):
    result = _result_set(
        active_mode=[0], pointing_error_deg=[0.0], has_access=[0],
        slant_range_m=[2.0e7], battery_charge_wh=[20.0], net_power_w=[5.0],
    )
    widget.set_result(result, _scenario())  # battery_capacity_wh=40.0 -> 50% SOC

    assert widget.battery_soc_bar.isEnabled()
    assert widget.battery_soc_bar.value() == 50
    assert widget.net_power_label.text() == "+5.00 W"
    assert widget.battery_soc_label.text() == "50%"  # beside the bar, not drawn across it


def test_battery_soc_bar_disabled_without_scenario(widget):
    result = _result_set(
        active_mode=[0], pointing_error_deg=[0.0], has_access=[0],
        slant_range_m=[2.0e7], battery_charge_wh=[20.0], net_power_w=[5.0],
    )
    widget.set_result(result, scenario=None)

    assert not widget.battery_soc_bar.isEnabled()
    assert widget.battery_charge_label.text() == "20.00 W*hr"


def test_negative_net_power_shown_without_plus_sign(widget):
    result = _result_set(
        active_mode=[1], pointing_error_deg=[2.0], has_access=[1],
        slant_range_m=[1.0e6], battery_charge_wh=[20.0], net_power_w=[-12.5],
    )
    widget.set_result(result, _scenario())

    assert widget.net_power_label.text() == "-12.50 W"


def test_set_live_result_is_an_alias_for_set_result(widget):
    result = _result_set(
        active_mode=[1], pointing_error_deg=[2.0], has_access=[1],
        slant_range_m=[1.0e6], battery_charge_wh=[20.0], net_power_w=[-12.5],
    )
    widget.set_live_result(result, _scenario())

    assert widget.mode_badge.text() == "Ground-station-pointing"
    assert not widget._state_box.isHidden()


def test_no_comms_pointing_series_leaves_the_empty_state(widget):
    """A ResultSet from a scenario with no comms_pointing spacecraft at
    all (e.g. every other bundled template) must leave this dashboard in
    its placeholder state, not crash or show stale/default values.
    """
    from spacemissionstudio.engine.results import ResultSet, TimeSeries

    rs = ResultSet(scenario_name="plain orbit")
    rs.add(TimeSeries("sat-1.position_N", np.array([0.0, 1.0]), ("x", "y", "z"),
                       np.zeros((2, 3)), units="m"))

    widget.set_result(rs, None)

    assert not widget._placeholder.isHidden()
    assert widget._state_box.isHidden()


def test_cards_fit_their_content_and_stack_when_narrow(qtbot):
    """Real user feedback on clutter: every card stretched to the full tab
    height (~85% empty) and badges stretched into full-width bars. Cards
    now keep their own content height, badges their natural width, and
    the cards stack in one column in a narrow pane."""
    from PySide6.QtCore import QPoint

    from spacemissionstudio.gui.mission_dashboard_widget import MissionDashboardWidget

    result = _result_set(
        active_mode=[0, 1], pointing_error_deg=[30.0, 0.4], has_access=[0, 1],
        slant_range_m=[2.0e6, 1.2e6], battery_charge_wh=[30.0, 27.0], net_power_w=[-8.0, -14.0],
    )
    w = MissionDashboardWidget()
    qtbot.addWidget(w)
    w.set_result(result, _scenario())
    w.setFixedSize(1000, 700)  # [px] a typical right-hand pane
    w.show()
    qtbot.waitExposed(w)

    cards = [w._state_box, w._attitude_box, w._power_box, w._rf_box]
    assert all(card.height() < 420 for card in cards)  # none stretched to the 700 px pane
    assert w._attitude_box.height() < w._rf_box.height()  # own height, not its row neighbour's
    def left(card):
        return card.mapTo(w, QPoint(0, 0)).x()

    assert left(w._state_box) == left(w._attitude_box) != left(w._power_box)  # two columns
    assert w.mode_badge.width() < w._state_box.width() * 0.6  # a pill, not a full-width bar

    w.setFixedSize(620, 900)  # [px] a narrow pane
    qtbot.wait(20)
    assert len({left(card) for card in cards}) == 1  # one column
    assert w.visibility_badge.text() == "In view of gs-1"


def test_the_dashboard_shows_the_moment_under_the_shared_time_cursor(widget):
    """UX/UI guidelines, "one shared time cursor across views": with a
    cursor the panels show that moment; cleared, the end of the run."""
    from spacemissionstudio.gui.time_cursor import TimeCursor

    result = _result_set(
        active_mode=[0, 1, 1], pointing_error_deg=[1.0, 12.0, 3.0], has_access=[0, 1, 1],
        slant_range_m=[2.0e7, 1.2e6, 9.0e5], battery_charge_wh=[35.0, 34.0, 33.0], net_power_w=[8.0, -9.0, -10.0],
    )
    widget.set_result(result, _scenario())
    cursor = TimeCursor()
    widget.set_time_cursor(cursor)
    assert widget.mode_badge.text() == "Ground-station-pointing"
    cursor.set_time(0.4)  # [s] between the first two samples: the first one is shown
    assert widget.mode_badge.text() == "Sun-pointing"
    assert widget.sim_time_label.text() == "0.0 s (time cursor)"
    cursor.set_time(1.0)  # [s]
    assert widget.tracking_badge.text() == "Slewing" and "1,200.0 km" in widget.slant_range_label.text()
    cursor.clear()
    assert widget.sim_time_label.text() == "2.0 s" and widget.tracking_badge.text() == "Converged"
