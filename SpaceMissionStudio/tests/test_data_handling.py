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

"""Onboard data handling and the patch-antenna downlink (SRS-F-13):
antenna patterns, the schema's checks, and -- with Basilisk -- the
instruments, memory and transmitter chain, its bookkeeping and its link
gate."""

import dataclasses
import json
import math

import numpy as np
import pytest

from spacemissionstudio.engine import data_budget, events, link_budget
from spacemissionstudio.engine.results import ResultSet, TimeSeries
from spacemissionstudio.engine.scenario_explainer import explain
from spacemissionstudio.engine.series_names import expected_series_names
from spacemissionstudio.schema.scenario import (DataHandlingConfig, GravityConfig, GroundStationConfig,
                                                InstrumentConfig, OrbitIC, PowerConfig, RFLinkConfig, Scenario,
                                                ScenarioValidationError, SimSettings, SpacecraftConfig)


def _patch(gain_dbi=6.0, **overrides):
    return RFLinkConfig(tx_power_w=2.0, frequency_hz=2.2e9, data_rate_bps=5.0e6,  # [W], [Hz], [bit/s]
                        tx_antenna_gain_dbi=gain_dbi, required_ebno_db=10.0, antenna_pattern="cosine",  # [dBi], [dB]
                        antenna_boresight_b=[-1.0, 0.0, 0.0], **overrides)


_BERLIN = GroundStationConfig("berlin-gs", 52.52, 13.405, altitude_m=34.0, rx_antenna_gain_dbi=35.0,
                              system_noise_temp_k=150.0)  # [deg], [m], [dBi], [K]


# -- antenna patterns ------------------------------------------------------------

def test_the_cosine_exponent_gives_the_peak_gain_as_the_patterns_directivity():
    """cos^n over the forward hemisphere: integrating the pattern numerically
    gives back the peak gain the exponent was derived from."""
    for gain_dbi in (4.0, 6.0, 9.0):  # [dBi]
        n = link_budget.cosine_exponent(gain_dbi)
        theta = np.linspace(0.0, math.pi / 2.0, 200001)  # [rad]
        radiated = 2.0 * math.pi * np.trapezoid(np.cos(theta) ** n * np.sin(theta), theta)
        assert 10.0 * math.log10(4.0 * math.pi / radiated) == pytest.approx(gain_dbi, abs=1e-6)


def test_a_patch_loses_gain_off_boresight_and_floors_behind_its_ground_plane():
    rf = _patch(10.0 * math.log10(4.0), antenna_front_to_back_db=18.0)  # [dBi] n = 1
    peak = rf.tx_antenna_gain_dbi
    assert link_budget.cosine_exponent(peak) == pytest.approx(1.0)
    assert link_budget.antenna_gain_dbi(rf, 0.0) == pytest.approx(peak)
    assert link_budget.antenna_gain_dbi(rf, 60.0) == pytest.approx(peak - 10.0 * math.log10(2.0))  # [dB] cos 60 = 1/2
    assert link_budget.antenna_gain_dbi(rf, 90.0) == pytest.approx(peak - 18.0)
    assert link_budget.antenna_gain_dbi(rf, 150.0) == pytest.approx(peak - 18.0)
    gains = link_budget.antenna_gain_dbi(rf, np.linspace(0.0, 180.0, 181))
    assert np.all(np.diff(gains) <= 1e-12)
    assert link_budget.half_power_beamwidth_deg(rf) == pytest.approx(120.0)  # [deg] cos theta = 1/2 at 60 deg


def test_a_datasheet_table_interpolates_in_db_and_holds_its_last_gain():
    rf = dataclasses.replace(_patch(), antenna_pattern="table",
                             antenna_gain_table=[[0.0, 7.0], [40.0, 4.0], [90.0, -6.0]])  # [deg, dBi]
    assert link_budget.peak_gain_dbi(rf) == 7.0
    assert link_budget.antenna_gain_dbi(rf, 20.0) == pytest.approx(5.5)
    assert link_budget.antenna_gain_dbi(rf, 170.0) == pytest.approx(-6.0)
    assert link_budget.half_power_beamwidth_deg(rf) == pytest.approx(80.0, abs=0.2)  # [deg] 4.0 dBi at 40 deg


def test_the_per_step_margin_equals_the_full_link_budget():
    """engine.data_handling evaluates margin_at_one_metre - 20 log10 r -
    pointing loss every step; it must agree with link_margin_db."""
    for rf in (_patch(), RFLinkConfig(1.0, 2.2e9, 1e6, antenna_beamwidth_deg=40.0), RFLinkConfig(1.0, 8.2e9, 2e7)):
        for range_m, angle in ((6.0e5, 0.0), (1.5e6, 35.0), (2.4e6, 70.0)):  # [m], [deg]
            fast = (link_budget.margin_at_one_metre_db(rf, _BERLIN) - 20.0 * math.log10(range_m)
                    - link_budget.pointing_loss_db(rf, angle))
            assert fast == pytest.approx(link_budget.link_margin_db(range_m, rf, _BERLIN, angle), abs=1e-9)


def test_a_fixed_pattern_keeps_the_earlier_link_budget():
    """No pattern: the same numbers as before patterns existed."""
    rf = RFLinkConfig(15.0, 8.2e9, 1.0e6, antenna_beamwidth_deg=10.0)
    breakdown = link_budget.link_budget_breakdown(1.0e6, rf, _BERLIN, 4.0)
    assert breakdown.pointing_loss_db == pytest.approx(12.0 * (4.0 / 10.0) ** 2)
    assert breakdown.eirp_dbw == pytest.approx(10.0 * math.log10(15.0) - 2.0)


# -- schema ------------------------------------------------------------------------

def _ORBIT(raan_deg):
    """550 km, Sun-synchronous, circular."""
    return OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.0,  # [km]
                   inclination_deg=97.6, raan_deg=raan_deg, arg_periapsis_deg=0.0, true_anomaly_deg=0.0)  # [deg]


def _scenario(**sc_overrides):
    spacecraft = SpacecraftConfig(
        name="sat", orbit=_ORBIT(48.0),
        rf_link=_patch(), data_handling=DataHandlingConfig(4.0, [InstrumentConfig("camera", 2.0e5),
                                                                 InstrumentConfig("housekeeping", 4.0e3)]))
    for key, value in sc_overrides.items():
        setattr(spacecraft, key, value)
    return Scenario(name="dh", epoch_utc="2030-01-01T08:30:00", ground_stations=[_BERLIN], spacecraft=[spacecraft],
                    gravity=GravityConfig(central_body="earth"), sim_settings=SimSettings(duration_days=0.1))


def test_a_data_handling_scenario_round_trips_through_json():
    scenario = _scenario()
    scenario.validate()
    back = Scenario.from_dict(json.loads(json.dumps(dataclasses.asdict(scenario))))
    assert back.spacecraft[0].data_handling == scenario.spacecraft[0].data_handling
    assert back.spacecraft[0].rf_link == scenario.spacecraft[0].rf_link


@pytest.mark.parametrize("change, message", [
    (lambda sc: setattr(sc.rf_link, "tx_antenna_gain_dbi", 2.0), "3.01 dBi"),
    (lambda sc: setattr(sc.rf_link, "antenna_boresight_b", None), "needs rf_link.antenna_boresight_b"),
    (lambda sc: setattr(sc.rf_link, "antenna_pattern", "dipole"), "antenna_pattern must be one of"),
    (lambda sc: (setattr(sc.rf_link, "antenna_pattern", "table"),
                 setattr(sc.rf_link, "antenna_gain_table", [[10.0, 6.0], [50.0, 2.0]])), "start at 0 deg"),
    (lambda sc: (setattr(sc.rf_link, "antenna_pattern", "table"),
                 setattr(sc.rf_link, "antenna_gain_table", [[0.0, 6.0], [0.0, 2.0]])), "start at 0 deg"),
    (lambda sc: setattr(sc.data_handling, "instruments", []), "at least one instrument"),
    (lambda sc: sc.data_handling.instruments.append(InstrumentConfig("camera", 1.0)), "must be unique"),
    (lambda sc: setattr(sc.data_handling.instruments[0], "name", "x" * 128), "1 to 127 characters"),
    (lambda sc: setattr(sc.data_handling.instruments[0], "initial_data_gbit", 5.0), "more than the"),
    (lambda sc: setattr(sc.data_handling.instruments[0], "power_w", 10.0), "no power budget"),
    (lambda sc: setattr(sc.data_handling, "transmitter_power_w", 5.0), "no power budget"),
])
def test_bad_data_handling_and_antenna_settings_are_refused_plainly(change, message):
    scenario = _scenario()
    change(scenario.spacecraft[0])
    with pytest.raises(ScenarioValidationError, match=message):
        scenario.validate()


def test_an_attitude_dependent_pattern_is_refused_in_orbit_only_mode():
    scenario = _scenario()
    scenario.simulation_mode = "orbit_only"
    with pytest.raises(ScenarioValidationError, match="'orbit_only' mode"):
        scenario.validate()
    scenario.spacecraft[0].rf_link.antenna_pattern = "fixed"
    scenario.validate()  # data handling itself needs no attitude


# -- what the GUI, CLI and Events tab make of it ------------------------------------

def test_the_explain_tab_gives_the_data_budget_before_any_run():
    section = next(s for s in explain(_scenario()).sections if s.title == "Data handling")
    assert [b.label for b in section.badges] == ["Data handling", "Patch antenna"]
    assert section.notes == ["sat: 17.6 Gbit/day; memory full in 5.45 h",  # 204 kbit/s into 4 Gbit
                             "sat: 5 Mbit/s, 3 Gbit per 10-min pass"]
    no_radio = _scenario(rf_link=None)
    section = next(s for s in explain(no_radio).sections if s.title == "Data handling")
    assert any(b.kind == "warning" and "no downlink" in b.label for b in section.badges)


def test_predicted_series_include_the_data_chain_and_the_link_gate():
    names = expected_series_names(_scenario())
    for part in ("stored", "downlink_rate", "data_generated", "data_downlinked", "data_lost"):
        assert f"sat.data_handling.{part}" in names
    for part in ("link_margin_db", "antenna_off_boresight", "link_closed"):
        assert f"berlin-gs.access_to_sat.{part}" in names


def _synthetic_result():
    t = np.arange(0.0, 100.0, 10.0)  # [s]
    closed = np.array([0, 1, 1, 1, 0, 0, 1, 1, 0, 0], dtype=float)
    rate = closed * 1.0e6  # [bit/s]
    rate[7] = 0.0  # the memory ran empty within the second window
    downlinked = np.concatenate([[0.0], np.cumsum(rate[1:] * 10.0)])  # [bit]
    result = ResultSet(scenario_name="s")
    result.add(TimeSeries("gs.access_to_sat.link_closed", t, ("link_closed",), closed))
    result.add(TimeSeries("sat.data_handling.downlink_rate", t, ("downlink_rate",), rate, units="bit/s"))
    result.add(TimeSeries("sat.data_handling.data_downlinked", t, ("data_downlinked",), downlinked, units="bit"))
    result.add(TimeSeries("sat.data_handling.data_generated", t, ("data_generated",), t * 1.0e6, units="bit"))
    result.add(TimeSeries("sat.data_handling.data_lost", t, ("data_lost",), np.zeros_like(t), units="bit"))
    stored = np.column_stack([t * 1.0e6 - downlinked, t * 1.0e6 - downlinked])
    result.add(TimeSeries("sat.data_handling.stored", t, ("total", "camera"), stored, units="bit"))
    return result


def test_each_link_window_that_sent_data_is_one_downlink_event():
    found = [e for e in events.extract_events(_synthetic_result()) if e.kind == events.DOWNLINK]
    assert [(e.start_s, e.end_s, e.detail, e.other) for e in found] == [
        (10.0, 30.0, "0.03 Gbit", "gs"), (60.0, 70.0, "0.01 Gbit", "gs")]
    assert events.DOWNLINK not in events.missing_kinds(_synthetic_result())


def test_the_run_summary_reads_the_totals_back():
    (budget,) = data_budget.budgets(_synthetic_result())
    assert (budget.generated, budget.downlinked, budget.lost) == (9.0e7, 4.0e7, 0.0)
    assert data_budget.summary_lines(_synthetic_result()) == [
        "sat: generated 0.09 Gbit, downlinked 0.04, lost to a full memory 0, on board at the end 0.05"]


# -- the chain in Basilisk ------------------------------------------------------------

def _orbit_only_downlink(days=1.0, capacity_gbit=0.5, initial_gbit=0.0):
    """A fast run: no attitude (a fixed-gain antenna), 10 s steps, a camera
    that outruns Berlin's passes so the memory fills."""
    scenario = _scenario()
    scenario.simulation_mode = "orbit_only"
    scenario.sim_settings = SimSettings(duration_days=days, dynamics_task_rate_s=10.0, integrator="rkf45")  # [day], [s]
    sc = scenario.spacecraft[0]
    sc.rf_link = RFLinkConfig(tx_power_w=2.0, frequency_hz=2.2e9, data_rate_bps=2.0e6,  # [W], [Hz], [bit/s]
                              tx_antenna_gain_dbi=3.0, required_ebno_db=10.0)  # [dBi], [dB]
    sc.data_handling = DataHandlingConfig(capacity_gbit, [
        InstrumentConfig("camera", 3.0e4, initial_data_gbit=initial_gbit),  # [bit/s], [Gbit]
        InstrumentConfig("housekeeping", 2.0e3)])  # [bit/s]
    scenario.validate()
    return scenario


@pytest.mark.requires_basilisk
def test_the_memory_fills_refuses_data_and_every_bit_is_accounted_for():
    """Generated = downlinked + lost + on board; the memory never exceeds
    its capacity; data only leaves while the link closes."""
    from spacemissionstudio.engine.service import SimulationService

    result = SimulationService(_orbit_only_downlink()).run()
    dh = "sat.data_handling"
    stored = result.series[f"{dh}.stored"]
    assert stored.columns == ("total", "camera", "housekeeping")
    assert np.all(stored.data[:, 0] <= 0.5e9)  # [bit]
    assert np.allclose(stored.data[:, 0], stored.data[:, 1] + stored.data[:, 2])
    generated, downlinked, lost = (result.series[f"{dh}.{part}"].data[-1, 0]
                                   for part in ("data_generated", "data_downlinked", "data_lost"))
    assert generated == pytest.approx(32.0e3 * 86400.0)  # [bit]
    assert lost > 0.0 and downlinked > 0.0
    assert generated == pytest.approx(downlinked + lost + stored.data[-1, 0], abs=1.0)  # [bit]
    rate = result.series[f"{dh}.downlink_rate"].data[:, 0]
    closed = result.series["berlin-gs.access_to_sat.link_closed"].data[:, 0]
    assert np.all(rate[closed == 0.0] == 0.0) and np.all(rate <= 2.0e6 + 1e-6)  # [bit/s]
    assert np.all(closed <= result.series["berlin-gs.access_to_sat.has_access"].data[:, 0])
    margin = result.series["berlin-gs.access_to_sat.link_margin_db"].data[:, 0]
    assert np.array_equal(np.isfinite(margin), result.series["berlin-gs.access_to_sat.has_access"].data[:, 0] > 0)


@pytest.mark.requires_basilisk
def test_what_the_ledger_counts_as_downlinked_is_what_the_transmitter_sent():
    """An independent check: a memory that never runs empty, so every bit
    the transmitter asks for leaves it -- the ledger's count must equal the
    transmitter's own output summed over the steps."""
    from spacemissionstudio.engine.service import SimulationService

    service = SimulationService(_orbit_only_downlink(days=0.5, capacity_gbit=60.0, initial_gbit=50.0))
    service.build(initialize=False)
    handle = service.spacecraft_handles["sat"].data_handling
    transmitter = next(m for m in handle.keep_alive if m.ModelTag.endswith("Transmitter"))
    recorder = transmitter.nodeDataOutMsg.recorder()
    service.scSim.AddModelToTask(service.dyn_task_name, recorder)
    service.scSim.InitializeSimulation()
    result = service.run()
    sent = -float(np.sum(np.asarray(recorder.baudRate)[1:])) * 10.0  # [bit] each step's request, 10 s steps
    downlinked = result.series["sat.data_handling.data_downlinked"].data[-1, 0]
    assert sent > 1.0e9 and downlinked == pytest.approx(sent, abs=1.0)  # [bit]


@pytest.mark.requires_basilisk
def test_the_gate_measures_the_angle_between_boresight_and_station():
    """off_boresight_deg against a hand-made geometry: the station straight
    'below' along -x of a body turned 90 deg about z."""
    from Basilisk.architecture import messaging

    from spacemissionstudio.engine.data_handling import _DownlinkGate

    gate = _DownlinkGate(_patch(), [_BERLIN], np.array([-1.0, 0.0, 0.0]), 0.0)
    sc_state = messaging.SCStatesMsgPayload()
    sc_state.r_BN_N = [7.0e6, 0.0, 0.0]  # [m]
    sc_state.sigma_BN = [0.0, 0.0, 0.0]
    ground = messaging.GroundStateMsgPayload()
    ground.r_LN_N = [6.4e6, 0.0, 0.0]  # [m] directly below
    assert gate.off_boresight_deg(sc_state, ground) == pytest.approx(0.0, abs=1e-9)
    sc_state.sigma_BN = [0.0, 0.0, math.tan(math.radians(90.0) / 4.0)]  # 90 deg about z
    assert gate.off_boresight_deg(sc_state, ground) == pytest.approx(90.0)
    ground.r_LN_N = [6.4e6, 0.6e6, 0.0]  # [m] 45 deg off nadir, toward +y
    sc_state.sigma_BN = [0.0, 0.0, 0.0]
    assert gate.off_boresight_deg(sc_state, ground) == pytest.approx(45.0)


@pytest.mark.requires_basilisk
def test_the_memory_and_the_totals_carry_across_long_run_segments(monkeypatch):
    """One day in one run, then as four segments: the memory's contents
    carry over and the generated, downlinked and lost totals match."""
    from spacemissionstudio.engine import long_run
    from spacemissionstudio.engine.service import SimulationService

    single = SimulationService(_orbit_only_downlink()).run()
    monkeypatch.setattr(long_run, "SEGMENT_DAYS", 0.25)  # [day]
    monkeypatch.setattr(SimSettings, "_MAX_SINGLE_RUN_DAYS", 0.25)  # [day]
    split = SimulationService(_orbit_only_downlink()).run()
    for part in ("data_generated", "data_downlinked", "data_lost"):
        name = f"sat.data_handling.{part}"
        assert split.series[name].data[-1, 0] == pytest.approx(single.series[name].data[-1, 0], rel=1e-3), part
    assert np.all(np.diff(split.series["sat.data_handling.data_generated"].data[:, 0]) >= 0.0)


@pytest.mark.requires_basilisk
def test_instruments_and_the_transmitter_draw_from_the_battery():
    """With the power budget on, the instruments' draw is constant and the
    transmitter's only while it sends: the battery ends lower than without
    them, by about what they drew."""
    from spacemissionstudio.engine.service import SimulationService

    def run(instrument_w, transmitter_w):
        scenario = _orbit_only_downlink(days=0.25)
        scenario.simulation_mode = "full_attitude"
        sc = scenario.spacecraft[0]
        sc.power = PowerConfig(panel_area_m2=0.1, panel_efficiency=0.0001, bus_idle_power_w=0.0,  # [m^2], [-], [W]
                               battery_capacity_wh=500.0, battery_initial_soc=1.0)  # [W*hr], [-]
        sc.data_handling.instruments[0].power_w = instrument_w
        sc.data_handling.transmitter_power_w = transmitter_w
        scenario.gravity.third_body_perturbers = ["sun"]
        result = SimulationService(scenario).run()
        return result

    quiet = run(0.0, 0.0)
    busy = run(10.0, 20.0)  # [W]
    sent_s = float(np.sum(busy.series["sat.data_handling.downlink_rate"].data[:, 0] > 0.0)) * 10.0  # [s]
    drawn_wh = (10.0 * 0.25 * 86400.0 + 20.0 * sent_s) / 3600.0  # [W*hr]
    difference = quiet.series["sat.battery_charge"].data[-1, 0] - busy.series["sat.battery_charge"].data[-1, 0]
    assert sent_s > 0.0
    assert difference == pytest.approx(drawn_wh, rel=0.02)
