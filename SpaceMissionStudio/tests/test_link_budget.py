"""Tests for spacemissionstudio.engine.link_budget -- no Basilisk import, runs
anywhere; verifies against a hand-computed link budget and against the
free-space-path-loss identity (range up by 10x -> FSPL up by 20 dB ->
margin down by 20 dB) rather than a second copy of the same formula.
"""

import numpy as np
import pytest

from spacemissionstudio.engine.link_budget import link_budget_breakdown, link_margin_db, link_margin_series
from spacemissionstudio.engine.results import ResultSet, ResultsError, TimeSeries
from spacemissionstudio.schema.scenario import GroundStationConfig, RFLinkConfig


def _rf_link(**overrides):
    defaults = dict(tx_power_w=15.0, frequency_hz=8.2e9, data_rate_bps=1.0e6,
                     tx_antenna_gain_dbi=6.0, implementation_loss_db=2.0, required_ebno_db=6.0)
    defaults.update(overrides)
    return RFLinkConfig(**defaults)


def _ground_station(**overrides):
    defaults = dict(name="gs1", latitude_deg=0.0, longitude_deg=0.0,
                     rx_antenna_gain_dbi=45.0, system_noise_temp_k=500.0)
    defaults.update(overrides)
    return GroundStationConfig(**defaults)


def test_link_margin_db_matches_hand_computed_value():
    # Independently computed (not copy-pasted from link_budget.py's own
    # expression): EIRP = 10*log10(15) + 6 - 2 = 15.761 dBW
    # FSPL @ 1000 km, 8.2 GHz = 20*log10(4*pi*1e6*8.2e9/299792458) = 170.724 dB
    # received = 15.761 - 170.724 + 45 = -109.963 dBW
    # N0 = -228.6 + 10*log10(500) = -201.610 dBW/Hz
    # C/N0 = -109.963 - (-201.610) = 91.647 dB-Hz
    # Eb/N0 = 91.647 - 10*log10(1e6) = 31.647 dB
    # margin = 31.647 - 6 = 25.647 dB
    margin = link_margin_db(1_000_000.0, _rf_link(), _ground_station())
    assert margin == pytest.approx(25.647, abs=0.01)


def test_link_margin_decreases_20db_per_decade_of_range():
    rf_link, gs = _rf_link(), _ground_station()
    margin_near = link_margin_db(1.0e6, rf_link, gs)
    margin_far = link_margin_db(1.0e7, rf_link, gs)
    assert margin_near - margin_far == pytest.approx(20.0, abs=1e-6)


def test_higher_tx_power_increases_margin_by_matching_db():
    rf_link_lo, gs = _rf_link(tx_power_w=10.0), _ground_station()
    rf_link_hi = _rf_link(tx_power_w=20.0)  # +3.01 dB
    delta = link_margin_db(1.0e6, rf_link_hi, gs) - link_margin_db(1.0e6, rf_link_lo, gs)
    assert delta == pytest.approx(10.0 * np.log10(2.0), abs=1e-9)


def _access_result(range_m, has_access, n=5):
    t = np.linspace(0.0, 100.0, n)
    result = ResultSet(scenario_name="test")
    result.add(TimeSeries("gs1.access_to_sat1.slant_range", t, ("slant_range",),
                           np.full((n, 1), range_m), units="m"))
    result.add(TimeSeries("gs1.access_to_sat1.has_access", t, ("has_access",),
                           np.array(has_access, dtype=float).reshape(-1, 1), units="-"))
    return result


def test_link_margin_series_only_defined_during_access():
    has_access = [0, 1, 1, 0, 0]
    result = _access_result(1.0e6, has_access)
    series = link_margin_series(result, "gs1", "sat1", _rf_link(), _ground_station())

    assert series.name == "gs1.access_to_sat1.link_margin_db"
    assert series.units == "dB"
    expected_margin = link_margin_db(1.0e6, _rf_link(), _ground_station())
    for i, accessible in enumerate(has_access):
        if accessible:
            assert series.data[i, 0] == pytest.approx(expected_margin)
        else:
            assert np.isnan(series.data[i, 0])


def test_link_margin_series_missing_pair_raises_clear_error():
    result = ResultSet(scenario_name="test")
    with pytest.raises(ResultsError, match="no access-analysis series found"):
        link_margin_series(result, "gs1", "sat1", _rf_link(), _ground_station())


def test_link_budget_breakdown_zero_pointing_error_matches_no_beamwidth_case():
    """No antenna_beamwidth_deg (the pre-existing default) and a
    perfectly-pointed antenna (pointing_error_deg=0.0) must produce the
    exact same margin -- confirms the new pointing-loss term is additive,
    never changing existing behavior when it doesn't apply.
    """
    rf_link_no_beamwidth = _rf_link()
    rf_link_with_beamwidth = _rf_link(antenna_beamwidth_deg=10.0)
    gs = _ground_station()

    no_beamwidth = link_budget_breakdown(1.0e6, rf_link_no_beamwidth, gs, pointing_error_deg=5.0)
    with_beamwidth_zero_error = link_budget_breakdown(1.0e6, rf_link_with_beamwidth, gs, pointing_error_deg=0.0)

    assert no_beamwidth.pointing_loss_db == 0.0
    assert with_beamwidth_zero_error.pointing_loss_db == 0.0
    assert no_beamwidth.margin_db == pytest.approx(with_beamwidth_zero_error.margin_db)


def test_link_budget_breakdown_pointing_loss_matches_parabolic_formula():
    # 12 * (pointing_error_deg / antenna_beamwidth_deg)^2, per this
    # module's own docstring -- independently computed here, not
    # copy-pasted from link_budget.py's own expression.
    rf_link = _rf_link(antenna_beamwidth_deg=20.0)
    gs = _ground_station()
    breakdown = link_budget_breakdown(1.0e6, rf_link, gs, pointing_error_deg=10.0)
    expected_loss_db = 12.0 * (10.0 / 20.0) ** 2  # = 3.0 dB
    assert breakdown.pointing_loss_db == pytest.approx(expected_loss_db)

    baseline = link_budget_breakdown(1.0e6, rf_link, gs, pointing_error_deg=0.0)
    assert baseline.margin_db - breakdown.margin_db == pytest.approx(expected_loss_db)


def test_link_budget_breakdown_pointing_loss_clamped_at_max():
    rf_link = _rf_link(antenna_beamwidth_deg=1.0)  # tiny beamwidth -> huge unclamped loss
    gs = _ground_station()
    breakdown = link_budget_breakdown(1.0e6, rf_link, gs, pointing_error_deg=90.0)
    assert breakdown.pointing_loss_db == 30.0  # _MAX_POINTING_LOSS_DB


def test_link_margin_db_pointing_error_kwarg_matches_breakdown():
    rf_link = _rf_link(antenna_beamwidth_deg=15.0)
    gs = _ground_station()
    assert link_margin_db(1.0e6, rf_link, gs, pointing_error_deg=7.0) == pytest.approx(
        link_budget_breakdown(1.0e6, rf_link, gs, pointing_error_deg=7.0).margin_db
    )


def _access_result_with_comms_pointing(range_m, has_access, active_mode, pointing_error_deg, n=5):
    t = np.linspace(0.0, 100.0, n)
    result = ResultSet(scenario_name="test")
    result.add(TimeSeries("gs1.access_to_sat1.slant_range", t, ("slant_range",),
                           np.full((n, 1), range_m), units="m"))
    result.add(TimeSeries("gs1.access_to_sat1.has_access", t, ("has_access",),
                           np.array(has_access, dtype=float).reshape(-1, 1), units="-"))
    result.add(TimeSeries("sat1.comms_pointing.active_mode", t, ("active_mode",),
                           np.array(active_mode, dtype=float).reshape(-1, 1), units="-"))
    result.add(TimeSeries("sat1.comms_pointing.pointing_error_deg", t, ("pointing_error_deg",),
                           np.array(pointing_error_deg, dtype=float).reshape(-1, 1), units="deg"))
    return result


def test_link_margin_series_gates_on_active_mode_in_addition_to_has_access():
    """Real geometric access alone isn't enough once a spacecraft also has
    comms_pointing configured -- the spacecraft must have actually
    switched into ground-station-pointing mode too (see
    link_margin_series's own docstring: "geometric visibility vs actual
    RF link availability"). Index 1 below has real access but the
    spacecraft hasn't switched modes yet (e.g. right at access start,
    before the arbitrator's own next tick) -- margin must be NaN there.
    """
    has_access = [0, 1, 1, 1, 0]
    active_mode = [0, 0, 1, 1, 0]
    pointing_error_deg = [0.0, 20.0, 5.0, 1.0, 0.0]
    result = _access_result_with_comms_pointing(1.0e6, has_access, active_mode, pointing_error_deg)
    rf_link = _rf_link(antenna_beamwidth_deg=15.0)
    gs = _ground_station()

    series = link_margin_series(result, "gs1", "sat1", rf_link, gs)

    assert np.isnan(series.data[0, 0])  # no access at all
    assert np.isnan(series.data[1, 0])  # access, but mode not yet switched
    assert not np.isnan(series.data[2, 0])
    assert not np.isnan(series.data[3, 0])
    assert np.isnan(series.data[4, 0])  # access ended


def test_link_margin_series_applies_the_pointing_error_series_per_sample():
    has_access = [1, 1]
    active_mode = [1, 1]
    pointing_error_deg = [20.0, 1.0]  # degraded right at the transition, converged afterward
    result = _access_result_with_comms_pointing(1.0e6, has_access, active_mode, pointing_error_deg, n=2)
    rf_link = _rf_link(antenna_beamwidth_deg=15.0)
    gs = _ground_station()

    series = link_margin_series(result, "gs1", "sat1", rf_link, gs)

    expected_0 = link_margin_db(1.0e6, rf_link, gs, pointing_error_deg=20.0)
    expected_1 = link_margin_db(1.0e6, rf_link, gs, pointing_error_deg=1.0)
    assert series.data[0, 0] == pytest.approx(expected_0)
    assert series.data[1, 0] == pytest.approx(expected_1)
    assert expected_1 > expected_0  # better-pointed sample has less pointing loss, so more margin


def test_link_margin_series_is_nan_for_a_ground_station_other_than_the_comms_pointing_target():
    """Regression test for a real bug: a comms_pointing spacecraft has
    exactly ONE antenna, committed to comms_pointing.target_ground_station
    -- geometric visibility of a DIFFERENT, non-targeted ground station is
    never a real link attempt, even if that other station's own
    has_access happens to be true at the same moment the spacecraft is
    actively comms-pointing (at its real target). Before this fix,
    link_margin_series had no way to know which ground station was
    actually targeted, so it would compute a plausible-looking,
    nonsensical margin for ANY station with has_access=1, using pointing
    error that was really measured against the ACTUAL target.
    """
    has_access = [1, 1]
    active_mode = [1, 1]  # actively comms-pointing -- but at gs-OTHER, not gs1
    pointing_error_deg = [2.0, 2.0]
    result = _access_result_with_comms_pointing(1.0e6, has_access, active_mode, pointing_error_deg, n=2)
    rf_link = _rf_link(antenna_beamwidth_deg=15.0)
    gs = _ground_station()

    series = link_margin_series(result, "gs1", "sat1", rf_link, gs,
                                 comms_pointing_target_ground_station="gs-OTHER")

    assert np.all(np.isnan(series.data[:, 0]))


def test_link_margin_series_still_applies_normal_gating_for_the_actual_comms_pointing_target():
    has_access = [1, 1]
    active_mode = [1, 1]
    pointing_error_deg = [2.0, 2.0]
    result = _access_result_with_comms_pointing(1.0e6, has_access, active_mode, pointing_error_deg, n=2)
    rf_link = _rf_link(antenna_beamwidth_deg=15.0)
    gs = _ground_station()

    series = link_margin_series(result, "gs1", "sat1", rf_link, gs,
                                 comms_pointing_target_ground_station="gs1")

    expected = link_margin_db(1.0e6, rf_link, gs, pointing_error_deg=2.0)
    assert series.data[0, 0] == pytest.approx(expected)
    assert series.data[1, 0] == pytest.approx(expected)


def test_link_margin_series_without_comms_pointing_series_is_unaffected():
    """A spacecraft with rf_link but no comms_pointing configured (the
    pre-existing case) has neither active_mode nor pointing_error_deg
    recorded -- link_margin_series must behave exactly as it did before
    this feature existed (gate on has_access alone, assume perfect
    pointing).
    """
    has_access = [0, 1, 1, 0]
    result = _access_result(1.0e6, has_access, n=4)
    series = link_margin_series(result, "gs1", "sat1", _rf_link(), _ground_station())
    expected_margin = link_margin_db(1.0e6, _rf_link(), _ground_station())
    for i, accessible in enumerate(has_access):
        if accessible:
            assert series.data[i, 0] == pytest.approx(expected_margin)
        else:
            assert np.isnan(series.data[i, 0])
