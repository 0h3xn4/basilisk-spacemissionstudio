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

"""MissionDashboardWidget: a live, at-a-glance telemetry readout for a
``schema.scenario.CommsPointingConfig`` spacecraft -- the GUI counterpart
to template '19' (``19_sun_pointing_comms_link.json``). Takes a plain
``engine.results.ResultSet`` (no Basilisk import in this module, same
"testable with synthetic data" convention as ``results_widget.py``) plus
an optional ``schema.scenario.Scenario`` (for the RF/power config needed
to recompute a live link-budget breakdown and a battery SOC percentage --
see :meth:`set_result`'s docstring for exactly what each unlocks).

Follows ``ResultsWidget``'s own ``set_result()``/``set_live_result()``
calling convention exactly, so ``gui/main_window.py`` can feed it from
the same ``RunWorker.progress``/``finished_ok``/``cancelled`` signals
with one more call alongside each existing ``results_widget`` one --
``engine.service.SimulationService.run_live()`` already re-derives the
FULL ``ResultSet`` (including this feature's own
``{sc}.comms_pointing.*`` series) on every progress chunk, so this widget
is "live" for free, the same way ``ResultsWidget`` already is.

Single-spacecraft assumption: this dashboard shows ONE spacecraft -- the
first one found carrying a ``{sc}.comms_pointing.active_mode`` series in
the given ``ResultSet`` (see :func:`_find_comms_pointing_spacecraft`).
Matches ``gui/template_wizard.py``'s own ``_sc()`` helper's documented
"every current wizard spec is single-spacecraft" precedent -- a future
multi-spacecraft version would need one panel per spacecraft, not a
change to this module's own per-spacecraft logic.
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ..engine import link_budget
from ..engine.results import ResultSet
from ..schema.scenario import Scenario
from .badges import ACCENT as _ACCENT_BADGE, badge_style as _badge_style
from .badges import DANGER as _DANGER_BADGE, MUTED as _MUTED_BADGE, SUCCESS as _SUCCESS_BADGE
from .theme import PALETTE


def _find_comms_pointing_spacecraft(result: Optional[ResultSet]) -> Optional[str]:
    """The first spacecraft name with a recorded
    ``{name}.comms_pointing.active_mode`` series, or ``None`` if the
    given result has none (e.g. no run yet, or a scenario with no
    ``comms_pointing`` spacecraft at all).
    """
    if result is None:
        return None
    suffix = ".comms_pointing.active_mode"
    for series_name in result.series:
        if series_name.endswith(suffix):
            return series_name[: -len(suffix)]
    return None


def _find_ground_station(result: ResultSet, spacecraft_name: str,
                          comms_pointing_target_ground_station: Optional[str] = None) -> Optional[str]:
    """The ground station this panel should show for ``spacecraft_name``.

    When ``comms_pointing_target_ground_station`` is given (the
    spacecraft's own ``schema.scenario.CommsPointingConfig.
    target_ground_station``, when a ``Scenario`` is available -- see
    :meth:`MissionDashboardWidget._refresh`) and that pair was actually
    recorded, it's used directly: a ``comms_pointing`` spacecraft has
    exactly one antenna under that mode arbitrator's control, so it is
    the ONLY ground station whose access/link-margin series mean
    anything for this panel, even if another station happens to be
    simultaneously, geometrically visible too (see
    ``engine.link_budget.link_margin_series``'s own docstring for the
    same reasoning on the engine side). Otherwise falls back to the
    FIRST ``{gs}.access_to_{sc}.has_access`` pairing found in
    ``result.series`` (e.g. no ``Scenario`` was given alongside this
    ``ResultSet``) -- matching this module's own single-spacecraft-panel
    scope (a spacecraft tracked by more than one ground station would
    need more than one RF panel, not handled here).
    """
    if comms_pointing_target_ground_station is not None:
        if f"{comms_pointing_target_ground_station}.access_to_{spacecraft_name}.has_access" in result.series:
            return comms_pointing_target_ground_station
        return None
    suffix = f".access_to_{spacecraft_name}.has_access"
    for series_name in result.series:
        if series_name.endswith(suffix):
            return series_name[: -len(suffix)]
    return None


def _latest(result: ResultSet, series_name: str) -> Optional[float]:
    series = result.series.get(series_name)
    if series is None or series.data.shape[0] == 0:
        return None
    return float(series.data[-1, 0])


class MissionDashboardWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._result: Optional[ResultSet] = None
        self._scenario: Optional[Scenario] = None

        layout = QVBoxLayout(self)

        self._placeholder = QLabel(
            "No live telemetry yet -- run a scenario with comms_pointing configured (e.g. template "
            "'19 - Sun-pointing spacecraft with automatic ground-station comms link') to populate this tab."
        )
        self._placeholder.setWordWrap(True)
        self._placeholder.setStyleSheet(f"color: {PALETTE['text_muted']};")
        layout.addWidget(self._placeholder)

        panels_row = QHBoxLayout()
        layout.addLayout(panels_row)

        # -- Operating state --------------------------------------------
        self._state_box = QGroupBox("Operating state")
        state_form = QFormLayout(self._state_box)
        self.sim_time_label = QLabel("--")
        self.mode_badge = QLabel("--")
        self.visibility_badge = QLabel("--")
        state_form.addRow("Sim time:", self.sim_time_label)
        state_form.addRow("Mode:", self.mode_badge)
        state_form.addRow("Ground-station visibility:", self.visibility_badge)
        panels_row.addWidget(self._state_box)

        # -- Attitude -----------------------------------------------------
        self._attitude_box = QGroupBox("Attitude")
        attitude_form = QFormLayout(self._attitude_box)
        self.pointing_error_label = QLabel("--")
        self.tracking_badge = QLabel("--")
        attitude_form.addRow("Pointing error:", self.pointing_error_label)
        attitude_form.addRow("Tracking:", self.tracking_badge)
        panels_row.addWidget(self._attitude_box)

        # -- Power ----------------------------------------------------------
        self._power_box = QGroupBox("Power")
        power_form = QFormLayout(self._power_box)
        self.battery_charge_label = QLabel("--")
        self.battery_soc_bar = QProgressBar()
        self.battery_soc_bar.setRange(0, 100)
        self.battery_soc_bar.setFormat("%p% SOC")
        self.net_power_label = QLabel("--")
        power_form.addRow("Battery charge:", self.battery_charge_label)
        power_form.addRow("Battery SOC:", self.battery_soc_bar)
        power_form.addRow("Net power:", self.net_power_label)
        panels_row.addWidget(self._power_box)

        # -- RF link --------------------------------------------------------
        self._rf_box = QGroupBox("RF link")
        rf_form = QFormLayout(self._rf_box)
        self.link_status_badge = QLabel("--")
        self.slant_range_label = QLabel("--")
        self.eirp_label = QLabel("--")
        self.fspl_label = QLabel("--")
        self.pointing_loss_label = QLabel("--")
        self.received_power_label = QLabel("--")
        self.noise_label = QLabel("--")
        self.cn0_label = QLabel("--")
        self.ebno_label = QLabel("--")
        self.margin_label = QLabel("--")
        rf_form.addRow("Link status:", self.link_status_badge)
        rf_form.addRow("Slant range:", self.slant_range_label)
        rf_form.addRow("EIRP:", self.eirp_label)
        rf_form.addRow("Free-space path loss:", self.fspl_label)
        rf_form.addRow("Antenna pointing loss:", self.pointing_loss_label)
        rf_form.addRow("Received power:", self.received_power_label)
        rf_form.addRow("Noise (N0):", self.noise_label)
        rf_form.addRow("C/N0:", self.cn0_label)
        rf_form.addRow("Eb/N0:", self.ebno_label)
        rf_form.addRow("Link margin:", self.margin_label)
        panels_row.addWidget(self._rf_box)

        self._set_panels_visible(False)

    def _set_panels_visible(self, visible: bool) -> None:
        self._state_box.setVisible(visible)
        self._attitude_box.setVisible(visible)
        self._power_box.setVisible(visible)
        self._rf_box.setVisible(visible)
        self._placeholder.setVisible(not visible)

    def set_result(self, result: Optional[ResultSet], scenario: Optional[Scenario] = None) -> None:
        self._result = result
        self._scenario = scenario
        self._refresh()

    def set_live_result(self, result: ResultSet, scenario: Optional[Scenario] = None) -> None:
        """Updates the dashboard with one chunk's worth of a still
        -running simulation -- see ``ResultsWidget.set_live_result()``'s
        own docstring for the live-update story this mirrors. Unlike that
        method, this widget holds no per-series UI state to avoid
        rebuilding (there is no series picker here), so this is simply an
        alias for :meth:`set_result`.
        """
        self.set_result(result, scenario)

    def _refresh(self) -> None:
        sc_name = _find_comms_pointing_spacecraft(self._result)
        if sc_name is None:
            self._set_panels_visible(False)
            return
        self._set_panels_visible(True)
        result = self._result
        assert result is not None

        sc_config = None
        if self._scenario is not None:
            sc_config = next((sc for sc in self._scenario.spacecraft if sc.name == sc_name), None)

        # -- Operating state --------------------------------------------
        active_mode_series = result.series.get(f"{sc_name}.comms_pointing.active_mode")
        sim_time_s = float(active_mode_series.time_s[-1]) if active_mode_series is not None and \
            active_mode_series.time_s.shape[0] > 0 else None
        self.sim_time_label.setText(f"{sim_time_s:,.1f} s" if sim_time_s is not None else "--")

        active_mode = _latest(result, f"{sc_name}.comms_pointing.active_mode")
        is_comms_mode = bool(active_mode is not None and active_mode > 0.5)
        if active_mode is None:
            self.mode_badge.setText("Unknown")
            self.mode_badge.setStyleSheet(_badge_style(_MUTED_BADGE))
        elif is_comms_mode:
            self.mode_badge.setText("Ground-station-pointing")
            self.mode_badge.setStyleSheet(_badge_style(_ACCENT_BADGE))
        else:
            self.mode_badge.setText("Sun-pointing")
            self.mode_badge.setStyleSheet(_badge_style(_SUCCESS_BADGE))

        comms_target = sc_config.comms_pointing.target_ground_station \
            if sc_config is not None and sc_config.comms_pointing is not None else None
        gs_name = _find_ground_station(result, sc_name, comms_target)
        has_access = None
        slant_range_m = None
        if gs_name is not None:
            has_access_val = _latest(result, f"{gs_name}.access_to_{sc_name}.has_access")
            has_access = bool(has_access_val is not None and has_access_val > 0.5)
            slant_range_m = _latest(result, f"{gs_name}.access_to_{sc_name}.slant_range")
        if has_access is None:
            self.visibility_badge.setText("Unknown")
            self.visibility_badge.setStyleSheet(_badge_style(_MUTED_BADGE))
        elif has_access:
            self.visibility_badge.setText(f"In view of {gs_name}")
            self.visibility_badge.setStyleSheet(_badge_style(_ACCENT_BADGE))
        else:
            self.visibility_badge.setText("No ground station in view")
            self.visibility_badge.setStyleSheet(_badge_style(_MUTED_BADGE))

        # -- Attitude -----------------------------------------------------
        pointing_error_deg = _latest(result, f"{sc_name}.comms_pointing.pointing_error_deg")
        self.pointing_error_label.setText(
            f"{pointing_error_deg:.2f} deg" if pointing_error_deg is not None else "--"
        )
        if pointing_error_deg is None:
            self.tracking_badge.setText("Unknown")
            self.tracking_badge.setStyleSheet(_badge_style(_MUTED_BADGE))
        elif pointing_error_deg < 5.0:
            self.tracking_badge.setText("Converged")
            self.tracking_badge.setStyleSheet(_badge_style(_SUCCESS_BADGE))
        else:
            self.tracking_badge.setText("Slewing")
            self.tracking_badge.setStyleSheet(_badge_style(_ACCENT_BADGE))

        # -- Power ----------------------------------------------------------
        battery_charge_wh = _latest(result, f"{sc_name}.battery_charge")
        net_power_w = _latest(result, f"{sc_name}.battery_net_power")
        self.battery_charge_label.setText(f"{battery_charge_wh:.2f} W*hr" if battery_charge_wh is not None else "--")
        battery_capacity_wh = sc_config.power.battery_capacity_wh if sc_config is not None and \
            sc_config.power is not None else None
        if battery_charge_wh is not None and battery_capacity_wh is not None and battery_capacity_wh > 0:
            soc_pct = max(0.0, min(100.0, 100.0 * battery_charge_wh / battery_capacity_wh))
            self.battery_soc_bar.setValue(int(round(soc_pct)))
            self.battery_soc_bar.setEnabled(True)
        else:
            self.battery_soc_bar.setValue(0)
            self.battery_soc_bar.setEnabled(False)
        if net_power_w is not None:
            sign = "+" if net_power_w >= 0 else ""
            self.net_power_label.setText(f"{sign}{net_power_w:.2f} W")
            self.net_power_label.setStyleSheet(
                f"color: {PALETTE['success'] if net_power_w >= 0 else PALETTE['danger']};"
            )
        else:
            self.net_power_label.setText("--")
            self.net_power_label.setStyleSheet("")

        # -- RF link --------------------------------------------------------
        self._refresh_rf_link(sc_config, gs_name, has_access, is_comms_mode, slant_range_m, pointing_error_deg)

    def _refresh_rf_link(self, sc_config, gs_name: Optional[str], has_access: Optional[bool],
                          is_comms_mode: bool, slant_range_m: Optional[float],
                          pointing_error_deg: Optional[float]) -> None:
        self.slant_range_label.setText(f"{slant_range_m / 1000.0:,.1f} km" if slant_range_m is not None else "--")

        rf_link = sc_config.rf_link if sc_config is not None else None
        gs_config = None
        if self._scenario is not None and gs_name is not None:
            gs_config = next((gs for gs in self._scenario.ground_stations if gs.name == gs_name), None)

        # Gated on has_access AND is_comms_mode -- matching
        # engine.link_budget.link_margin_series()'s own gating exactly
        # (see that function's docstring): real geometric access alone
        # does not mean the spacecraft has actually switched into
        # ground-station-pointing mode yet, so no link attempt -- and so
        # no breakdown -- should be shown while it's still Sun-pointing,
        # even if the ground station happens to already be visible.
        breakdown = None
        if rf_link is not None and gs_config is not None and slant_range_m is not None \
                and has_access and is_comms_mode:
            breakdown = link_budget.link_budget_breakdown(
                slant_range_m, rf_link, gs_config, pointing_error_deg or 0.0
            )

        if breakdown is None:
            for label in (self.eirp_label, self.fspl_label, self.pointing_loss_label,
                          self.received_power_label, self.noise_label, self.cn0_label,
                          self.ebno_label, self.margin_label):
                label.setText("--")
            if has_access is None:
                self.link_status_badge.setText("Unknown")
                self.link_status_badge.setStyleSheet(_badge_style(_MUTED_BADGE))
            elif not has_access:
                self.link_status_badge.setText("No access")
                self.link_status_badge.setStyleSheet(_badge_style(_MUTED_BADGE))
            elif not is_comms_mode:
                # Real access exists, but the spacecraft hasn't
                # (mode-)switched its antenna to point at it yet -- the
                # "geometric visibility vs. actual RF link availability"
                # distinction this feature is built around.
                self.link_status_badge.setText("Not yet comms-pointing")
                self.link_status_badge.setStyleSheet(_badge_style(_MUTED_BADGE))
            else:
                self.link_status_badge.setText("Link status unknown (no rf_link configured)")
                self.link_status_badge.setStyleSheet(_badge_style(_MUTED_BADGE))
            return

        self.eirp_label.setText(f"{breakdown.eirp_dbw:.2f} dBW")
        self.fspl_label.setText(f"{breakdown.fspl_db:.2f} dB")
        self.pointing_loss_label.setText(f"{breakdown.pointing_loss_db:.2f} dB")
        self.received_power_label.setText(f"{breakdown.received_dbw:.2f} dBW")
        self.noise_label.setText(f"{breakdown.n0_dbw_hz:.2f} dBW/Hz")
        self.cn0_label.setText(f"{breakdown.cn0_db_hz:.2f} dB-Hz")
        self.ebno_label.setText(f"{breakdown.ebno_db:.2f} dB")
        self.margin_label.setText(f"{breakdown.margin_db:.2f} dB")
        if math.isnan(breakdown.margin_db) or breakdown.margin_db < 0:
            self.link_status_badge.setText("Link degraded")
            self.link_status_badge.setStyleSheet(_badge_style(_DANGER_BADGE))
        else:
            self.link_status_badge.setText("Link OK")
            self.link_status_badge.setStyleSheet(_badge_style(_SUCCESS_BADGE))
