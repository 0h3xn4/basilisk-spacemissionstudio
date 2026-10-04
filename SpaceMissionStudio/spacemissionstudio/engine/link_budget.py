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

r"""
Downlink RF link-margin ESTIMATE: a simplified free-space-path-loss Eb/N0
budget, ported directly from ``../missionAnalysis``'s
``run_constellation_mission.py::_rf_link_margin_db()`` -- EIRP - FSPL
(- an optional antenna-pointing-loss term, see
:func:`link_budget_breakdown`) + G/T against the required Eb/N0 for the
assumed data rate (still no atmosphere/rain/coding-gain terms). See
``schema.scenario.RFLinkConfig``'s docstring for what this does and does
NOT feed into.

This module has NO Basilisk import and is fully unit-testable here with
synthetic data -- it only consumes the already-recorded ``slant_range``/
``has_access``/``pointing_error_deg`` :class:`~engine.results.TimeSeries`
that ``engine.service.SimulationService.run()`` produces from Basilisk's
real, simulated orbit geometry (``groundLocation.GroundLocation``) and
attitude (``engine.fsw.build_comms_pointing``'s arbitrator, when a
spacecraft has ``schema.scenario.CommsPointingConfig`` configured); this
module never computes geometry or attitude itself.

A real, more physically-complete alternative exists in Basilisk itself
(``src/simulation/communication/{simpleAntenna,linkBudget}/`` -- a real
2D-Gaussian-beam antenna pattern + a compiled ``LinkBudget`` module
computing FSPL, atmospheric attenuation, and pointing loss from true
antenna geometry) but is deliberately NOT used here: no example scenario
anywhere in this checkout exercises it yet, so there is no reference
usage to confirm the wiring against the way every other module this
project uses was confirmed first -- see ``SpaceMissionStudio/HISTORY.md``'s
comms_pointing entry for the full reasoning. This module's own simplified,
already-proven approach is used instead, extended (not replaced) below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..schema.scenario import GroundStationConfig, RFLinkConfig
from .results import ResultSet, ResultsError, TimeSeries

_C_LIGHT_M_S = 299792458.0  # [m/s]
_K_BOLTZMANN_DBW_HZ = -228.6  # [dBW/K/Hz] 10*log10(1.380649e-23)
_MAX_POINTING_LOSS_DB = 30.0  # [dB] clamp -- the parabolic approximation below is only valid near boresight


@dataclass
class LinkBudgetBreakdown:
    """Every intermediate quantity :func:`link_budget_breakdown` computes
    on the way to the final margin -- for telemetry/display (e.g.
    ``gui.mission_dashboard_widget``), not just the one final number
    :func:`link_margin_db` returns.
    """

    eirp_dbw: float
    fspl_db: float
    pointing_loss_db: float
    received_dbw: float
    n0_dbw_hz: float
    cn0_db_hz: float
    ebno_db: float
    margin_db: float


def link_budget_breakdown(range_m: float, rf_link: RFLinkConfig, ground_station: GroundStationConfig,
                           pointing_error_deg: float = 0.0) -> LinkBudgetBreakdown:
    """The full link budget, every stage broken out -- see
    :class:`LinkBudgetBreakdown`. :func:`link_margin_db` is a thin
    wrapper returning just ``.margin_db``.

    ``pointing_error_deg`` (the ACTUAL achieved angle between the
    spacecraft's antenna boresight and the ground station, e.g. from
    ``{sc}.comms_pointing.pointing_error_deg`` -- see
    ``engine.fsw.build_comms_pointing``) only matters when
    ``rf_link.antenna_beamwidth_deg`` is also set; otherwise
    ``pointing_loss_db`` is always ``0.0``, matching this function's
    exact pre-pointing-loss behavior for every scenario that doesn't set
    that field. When both are given, applies the standard parabolic
    -reflector/Gaussian-main-lobe pointing-loss approximation
    ``12*(pointing_error_deg / antenna_beamwidth_deg)^2`` dB (clamped to
    :data:`_MAX_POINTING_LOSS_DB` -- the approximation itself is only
    meaningful within a few beamwidths of boresight, not an indication
    the link still "almost" closes far off-axis).
    """
    eirp_dbw = 10.0 * np.log10(rf_link.tx_power_w) + rf_link.tx_antenna_gain_dbi - rf_link.implementation_loss_db
    fspl_db = 20.0 * np.log10(4.0 * np.pi * range_m * rf_link.frequency_hz / _C_LIGHT_M_S)
    pointing_loss_db = 0.0
    if rf_link.antenna_beamwidth_deg is not None and pointing_error_deg != 0.0:
        pointing_loss_db = min(
            _MAX_POINTING_LOSS_DB, 12.0 * (pointing_error_deg / rf_link.antenna_beamwidth_deg) ** 2
        )
    received_dbw = eirp_dbw - fspl_db - pointing_loss_db + ground_station.rx_antenna_gain_dbi
    n0_dbw_hz = _K_BOLTZMANN_DBW_HZ + 10.0 * np.log10(ground_station.system_noise_temp_k)
    cn0_db_hz = received_dbw - n0_dbw_hz
    ebno_db = cn0_db_hz - 10.0 * np.log10(rf_link.data_rate_bps)
    margin_db = ebno_db - rf_link.required_ebno_db
    return LinkBudgetBreakdown(
        eirp_dbw=float(eirp_dbw), fspl_db=float(fspl_db), pointing_loss_db=float(pointing_loss_db),
        received_dbw=float(received_dbw), n0_dbw_hz=float(n0_dbw_hz), cn0_db_hz=float(cn0_db_hz),
        ebno_db=float(ebno_db), margin_db=float(margin_db),
    )


def link_margin_db(range_m: float, rf_link: RFLinkConfig, ground_station: GroundStationConfig,
                    pointing_error_deg: float = 0.0) -> float:
    """Downlink Eb/N0 margin [dB] at the given slant range: positive means
    the link closes with that much margin to spare; negative means it
    doesn't close at that range with these parameters. See
    :func:`link_budget_breakdown` for every intermediate quantity and
    for what ``pointing_error_deg`` does.
    """
    return link_budget_breakdown(range_m, rf_link, ground_station, pointing_error_deg).margin_db


def link_margin_series(result: ResultSet, ground_station_name: str, spacecraft_name: str,
                        rf_link: RFLinkConfig, ground_station: GroundStationConfig) -> TimeSeries:
    """Builds a ``"<gs>.access_to_<sc>.link_margin_db"`` :class:`TimeSeries`
    from that pair's already-recorded ``slant_range``/``has_access`` series
    (see ``engine.service.SimulationService.run()``'s access-analysis
    wiring). The margin is only defined while ``has_access`` is true --
    there is no link (and so no meaningful margin) outside an access
    window, so those samples are ``NaN`` rather than a misleadingly large
    negative number.

    When the spacecraft also has ``schema.scenario.CommsPointingConfig``
    configured, this additionally gates on its own
    ``{spacecraft_name}.comms_pointing.active_mode`` series (when present in
    ``result.series``) -- real geometric ``has_access`` only means the
    ground station is visible, not that the spacecraft has actually
    (mode-)switched its antenna to point at it yet, so a sample only gets a
    defined margin once BOTH are true. When that series is present, this
    also feeds the spacecraft's own, real, simulated
    ``{spacecraft_name}.comms_pointing.pointing_error_deg`` into
    :func:`link_margin_db` for that sample, so the margin reflects the
    actually-achieved antenna pointing rather than assuming perfect
    boresight. Spacecraft with no ``comms_pointing`` configured (the
    pre-existing behavior) have neither series recorded, so this is exactly
    equivalent to the old, always-perfect-pointing margin for them.
    """
    prefix = f"{ground_station_name}.access_to_{spacecraft_name}"
    range_series = result.series.get(f"{prefix}.slant_range")
    access_series = result.series.get(f"{prefix}.has_access")
    if range_series is None or access_series is None:
        raise ResultsError(
            f"no access-analysis series found for ground station {ground_station_name!r} / spacecraft "
            f"{spacecraft_name!r} -- was this pair actually simulated? (expected "
            f"{prefix}.slant_range/{prefix}.has_access in result.series)"
        )

    active_mode_series = result.series.get(f"{spacecraft_name}.comms_pointing.active_mode")
    pointing_error_series = result.series.get(f"{spacecraft_name}.comms_pointing.pointing_error_deg")

    margin_db = np.full(len(range_series.time_s), np.nan)
    has_access = access_series.data[:, 0] > 0.5
    if active_mode_series is not None:
        has_access = has_access & (active_mode_series.data[:, 0] > 0.5)
    for i in np.nonzero(has_access)[0]:
        pointing_error_deg = float(pointing_error_series.data[i, 0]) if pointing_error_series is not None else 0.0
        margin_db[i] = link_margin_db(float(range_series.data[i, 0]), rf_link, ground_station, pointing_error_deg)

    return TimeSeries(f"{prefix}.link_margin_db", range_series.time_s, ("link_margin_db",),
                       margin_db.reshape(-1, 1), units="dB")
