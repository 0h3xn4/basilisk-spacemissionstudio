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

"""GEO station-keeping (:class:`schema.scenario.GeoStationKeepingConfig`):
hold a geostationary spacecraft inside a longitude box (east-west control)
and below an inclination limit (north-south control), the two things real
GEO station-keeping does. Needs Basilisk.

Longitude and inclination are measured in Earth's own rotating frame, read
every tick from the central body's SPICE state (``J20002Pfix``), the same
frame Basilisk's gravity model rotates with. Using the J2000 equator
instead would be off by Earth's ~0.17 deg pole precession since 2000,
larger than a typical inclination box.

East-west. A day of longitude samples is fitted with a straight line plus a
once-per-day sine and cosine: the line's value now and its slope (the drift
rate), with the daily libration an eccentric orbit causes fitted out. (A
plain straight line over exactly one day does not cancel that libration: it
biases the slope by up to ~1.9 x its amplitude per day, which at
e = 2e-4 is twice a typical drift. Found in the first real run.) When the
spacecraft leaves the box heading outward, an along-track burn sets a new
drift rate. If Earth's triaxiality (the J22 term) is accelerating it outward,
the new drift sends it back across the box on a parabola that just reaches
the far edge: drift speed ``2 sqrt(|lambda_ddot| * deadband)``. If that
acceleration already points back inward, nothing is done unless it would
carry the spacecraft more than a quarter box further out; then the burn
only stops the drift. A
tangential delta-V changes the drift rate by ``-3 dv / a``, so the burn is
``dv = -a * d(lambda_dot) / 3``. After each burn, the day of samples restarts.

North-south. When the inclination passes ``inclination_max_deg``, the
controller waits for the next node of the orbit on Earth's equator, the only
place an out-of-plane burn changes inclination efficiently, and fires one
burn centred on it, sized to bring the inclination down to a quarter of the
limit. The thrust is held along Earth's pole axis (as with thrusters fixed on
an Earth-pointing bus), so the symmetric burn turns the orbit's angular
momentum straight toward the pole and leaves the node where it was. (Gating a
burn on "near a node" alone does not work at these tiny inclinations: each
off-node bit of thrust moves the node, and a first version chased it
forever, firing one step in five.)

Propellant comes from one tank, tracked with the rocket equation and fed
back into the simulated mass every tick, exactly as
:class:`engine.orbit_maintenance.StationKeepingController` does. Burns are
not eclipse-gated (GEO station-keeping thrusters are usually chemical).
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from Basilisk.architecture import messaging, sysModel
from Basilisk.simulation import extForceTorque
from Basilisk.utilities import macros

from ..schema.scenario import GeoStationKeepingConfig
from .propellant_bookkeeping import apply_propellant_burn

_OMEGA_EARTH = 7.2921159e-5  # [rad/s] Earth's sidereal rotation rate
_SIDEREAL_DAY_S = 2.0 * math.pi / _OMEGA_EARTH  # [s]
_J22 = 1.81554e-6  # [-] Earth's sectoral (triaxiality) harmonic
_LAMBDA_22 = math.radians(-14.928)  # [rad] longitude of the J22 bulge axis
_MAX_HALF_ARC = math.radians(60.0)  # [rad] longest N-S burn arc per node; more needs more passes
_INCLINATION_RESET_FRACTION = 0.25  # [-] N-S burns stop below this fraction of the limit
_FIT_INTERVAL_S = 600.0  # [s] how often the east-west drift fit is redone


def longitude_acceleration(longitude_rad: float, semi_major_axis_m: float, r_equator_m: float) -> float:
    """Drift acceleration [rad/s^2] from Earth's triaxiality at a GEO
    longitude: ``18 w^2 J22 (Re/a)^2 sin(2 (lambda - lambda22))``.
    Unstable equilibria at lambda22 (~345 E) and lambda22 + 180 (~165 E),
    stable at ~75 E and ~255 E."""
    return (18.0 * _OMEGA_EARTH ** 2 * _J22 * (r_equator_m / semi_major_axis_m) ** 2
            * math.sin(2.0 * (longitude_rad - _LAMBDA_22)))


def _wrap_pm_pi(angle_rad: float) -> float:
    return (angle_rad + math.pi) % (2.0 * math.pi) - math.pi


class GeoStationKeepingController(sysModel.SysModel):
    """See this module's docstring. Construct via
    :func:`build_geo_station_keeping`."""

    def __init__(self, name: str, mu: float, r_equator_m: float, config: GeoStationKeepingConfig,
                 dry_mass_kg: float, g0_mps2: float = 9.80665):
        super().__init__()
        self.ModelTag = name
        self.scStateInMsg = messaging.SCStatesMsgReader()
        self.planetStateInMsg = messaging.SpicePlanetStateMsgReader()
        self.extForceEffector = None
        self.scObject = None

        self.mu = mu  # [m^3/s^2]
        self.rEquator = r_equator_m  # [m]
        self.targetLon = math.radians(config.target_longitude_deg)  # [rad]
        self.deadband = math.radians(config.longitude_deadband_deg)  # [rad]
        self.inclinationMax = math.radians(config.inclination_max_deg)  # [rad]
        self.thrustN = config.thrust_n  # [N]
        self.ispS = config.isp_s  # [s]
        self.g0 = g0_mps2  # [m/s^2]
        self.dryMass = dry_mass_kg  # [kg]
        self.propellant = config.propellant_kg  # [kg]

        self._lastT: Optional[float] = None  # [s]
        self._history: list = []  # (t [s], unwrapped longitude error [rad]) over the last sidereal day
        self._historyStartT: Optional[float] = None  # [s]
        self._ewRemainingDv = 0.0  # [m/s] signed: + prograde
        self._nsActive = False
        # [frozen node direction, half arc [rad], thrust direction, needed dv
        # [m/s], delivered dv [m/s]] during a burn
        self._nsBurn = None
        self._stepS = 0.0  # [s]
        self._lastFit = None  # (t [s], (error [rad], drift [rad/s]))
        self._cumulativeDv = 0.0  # [m/s]
        self.ewManeuvers = 0
        self.nsManeuvers = 0

        self.tLog: list = []
        self.lonLog: list = []
        self.smoothLonLog: list = []
        self.inclinationLog: list = []
        self.ewBurnLog: list = []
        self.nsBurnLog: list = []
        self.propellantLog: list = []
        self.deltaVLog: list = []

    def Reset(self, CurrentSimNanos):
        self._lastT = CurrentSimNanos * macros.NANO2SEC
        self._history = []
        self._historyStartT = None
        self._ewRemainingDv = 0.0
        self._nsActive = False
        self._nsBurn = None
        self._lastFit = None
        if self.extForceEffector is not None:
            self.extForceEffector.extForce_N = [0.0, 0.0, 0.0]

    def _drift_fit(self, t: float):
        """(longitude error now [rad], drift rate [rad/s]) from a line plus
        a daily sine/cosine through the last sidereal day, or None until a
        full day of samples has built up since the last east-west burn."""
        if self._historyStartT is None or t - self._historyStartT < _SIDEREAL_DAY_S:
            return None
        times = np.array([s for s, _ in self._history]) - t  # [s]
        errors = np.array([e for _, e in self._history])
        phase = _OMEGA_EARTH * times
        basis = np.column_stack([np.ones_like(times), times, np.sin(phase), np.cos(phase)])
        (intercept, slope, _, _), *_ = np.linalg.lstsq(basis, errors, rcond=None)
        return float(intercept), float(slope)

    def _plan_east_west(self, error: float, drift: float, a_m: float, lon_rad: float) -> float:
        """Signed delta-V [m/s] (+ prograde) for an out-of-box state."""
        accel = longitude_acceleration(lon_rad, a_m, self.rEquator)  # [rad/s^2]
        outward = math.copysign(1.0, error)
        if accel * outward > 0.0:  # pushed further out: reverse onto a parabola spanning the box
            target_drift = -outward * 2.0 * math.sqrt(abs(accel) * self.deadband)  # [rad/s]
        elif drift ** 2 / (2.0 * max(abs(accel), 1e-30)) > 0.25 * self.deadband:
            target_drift = 0.0  # pulled back in, but not before overshooting further: stop the drift
        else:
            return 0.0  # the pull back inward turns it around soon enough
        return -a_m * (target_drift - drift) / 3.0

    def UpdateState(self, CurrentSimNanos):
        t = CurrentSimNanos * macros.NANO2SEC  # [s]
        dt = t - self._lastT if self._lastT is not None else 0.0  # [s]
        self._lastT = t
        self._stepS = dt
        state = self.scStateInMsg()
        r_n = np.array(state.r_BN_N)  # [m] Earth-centred (the SPICE zero base is the central body)
        v_n = np.array(state.v_BN_N)  # [m/s]
        dcm_pn = np.array(self.planetStateInMsg().J20002Pfix)  # [-] inertial -> Earth-fixed
        force = np.zeros(3)
        if not (np.all(np.isfinite(r_n)) and np.all(np.isfinite(v_n)) and np.linalg.norm(v_n) > 0.0):
            self._log(t, float("nan"), float("nan"), float("nan"), 0.0, 0.0)
            if self.extForceEffector is not None:
                self.extForceEffector.extForce_N = [0.0, 0.0, 0.0]
            return

        r_p = dcm_pn @ r_n
        lon = math.atan2(r_p[1], r_p[0])  # [rad] east longitude
        error = _wrap_pm_pi(lon - self.targetLon)  # [rad]
        if self._history:  # keep the day of samples continuous across +/-180 deg
            error = self._history[-1][1] + _wrap_pm_pi(error - self._history[-1][1])
        if self._historyStartT is None:
            self._historyStartT = t
        self._history.append((t, error))
        while self._history and t - self._history[0][0] > _SIDEREAL_DAY_S:
            self._history.pop(0)

        pole_n = dcm_pn[2, :]  # Earth's spin axis, inertial components
        h_hat = np.cross(r_n, v_n)
        h_hat /= np.linalg.norm(h_hat)
        inclination = math.acos(max(-1.0, min(1.0, float(h_hat @ pole_n))))  # [rad]

        a_m = 1.0 / (2.0 / np.linalg.norm(r_n) - float(v_n @ v_n) / self.mu)  # [m]
        mass = (self.scObject.scMassOutMsg.read().massSC if self.scObject is not None
                else self.dryMass + self.propellant)  # [kg]
        fit = None
        if self._lastFit is None or t - self._lastFit[0] >= _FIT_INTERVAL_S:
            fit = self._drift_fit(t)
            self._lastFit = (t, fit) if fit is not None else None
        smoothed = (self._lastFit[1][0] + self._lastFit[1][1] * (t - self._lastFit[0])
                    if self._lastFit is not None else float("nan"))
        if fit is not None and self._ewRemainingDv == 0.0:
            fit_error, drift = fit
            if abs(fit_error) > self.deadband and fit_error * drift > 0.0:
                self._ewRemainingDv = self._plan_east_west(fit_error, drift, a_m, lon)
                if self._ewRemainingDv != 0.0:
                    self.ewManeuvers += 1

        if not self._nsActive and inclination > self.inclinationMax:
            self._nsActive = True
            self.nsManeuvers += 1
        elif self._nsActive and inclination < _INCLINATION_RESET_FRACTION * self.inclinationMax:
            self._nsActive = False

        ew_thrust = ns_thrust = 0.0  # [N]
        if self.propellant > 1e-9 and dt > 0.0:
            if self._ewRemainingDv != 0.0:
                ew_thrust = min(self.thrustN, abs(self._ewRemainingDv) * mass / dt)
                force += math.copysign(ew_thrust, self._ewRemainingDv) * v_n / np.linalg.norm(v_n)
                step_dv = ew_thrust / mass * dt  # [m/s]
                if step_dv >= abs(self._ewRemainingDv) - 1e-12:
                    self._ewRemainingDv = 0.0
                    self._history, self._historyStartT = [], None  # a new drift: refit from scratch
                    self._lastFit = None
                else:
                    self._ewRemainingDv -= math.copysign(step_dv, self._ewRemainingDv)
            if self._nsActive or self._nsBurn is not None:
                ns_force = self._north_south_force(r_n, v_n, h_hat, pole_n, inclination, mass)
                ns_thrust = float(np.linalg.norm(ns_force))
                force += ns_force

        total_thrust = float(np.linalg.norm(force))  # [N]
        if total_thrust > 0.0:
            self._cumulativeDv += (ew_thrust + ns_thrust) / mass * dt
        hub_mass = self.scObject.hub.mHub if self.scObject is not None else self.dryMass + self.propellant
        new_mass, self.propellant, _burned, _m_dot = apply_propellant_burn(
            hub_mass, self.propellant, ew_thrust + ns_thrust, self.ispS, dt, self.g0)
        if self.scObject is not None:
            self.scObject.hub.mHub = new_mass
        if self.extForceEffector is not None:
            self.extForceEffector.extForce_N = force.tolist()
        self._log(t, lon, self.targetLon + smoothed, inclination, ew_thrust, ns_thrust)

    def _north_south_force(self, r_n, v_n, h_hat, pole_n, inclination, mass) -> np.ndarray:
        """Thrust [N] for this step of a node-centred north-south burn."""
        r_hat = r_n / np.linalg.norm(r_n)
        if self._nsBurn is None:
            node = np.cross(pole_n, h_hat)  # ascending node direction on the equator
            if np.linalg.norm(node) < 1e-12 or not self._nsActive:
                return np.zeros(3)
            node /= np.linalg.norm(node)
            node *= math.copysign(1.0, float(r_hat @ node))  # the nearer node
            needed_dv = float(np.linalg.norm(v_n)) * (inclination - _INCLINATION_RESET_FRACTION
                                                      * self.inclinationMax)  # [m/s]
            mean_motion = math.sqrt(self.mu / np.linalg.norm(r_n) ** 3)  # [rad/s]
            half_arc = min(0.5 * needed_dv * mass / self.thrustN * mean_motion, _MAX_HALF_ARC)  # [rad]
            if float(r_hat @ node) < math.cos(half_arc):
                return np.zeros(3)  # not at the node yet
            # Thrust along the pole, signed so r x F points against the
            # equatorial part of the angular momentum (the tilt).
            h_eq = h_hat - (h_hat @ pole_n) * pole_n
            sign = -math.copysign(1.0, float(np.cross(node, pole_n) @ h_eq))
            self._nsBurn = [node, half_arc, sign * pole_n, needed_dv, 0.0]
        node, half_arc, direction, needed_dv, delivered_dv = self._nsBurn
        if float(r_hat @ node) < math.cos(half_arc) or not self._nsActive:
            # Past the arc: a full burn ends the maneuver (short-period
            # wobble would otherwise trigger touch-ups at every node); one
            # cut short by starting mid-arc is finished at the next node.
            if delivered_dv >= 0.9 * needed_dv:
                self._nsActive = False
            self._nsBurn = None
            return np.zeros(3)
        self._nsBurn[4] += self.thrustN / mass * self._stepS  # [m/s]
        return self.thrustN * direction

    def _log(self, t, lon, smoothed_lon, inclination, ew_thrust, ns_thrust) -> None:
        self.tLog.append(t)
        self.lonLog.append(lon)
        self.smoothLonLog.append(smoothed_lon)
        self.inclinationLog.append(inclination)
        self.ewBurnLog.append(1.0 if ew_thrust > 0.0 else 0.0)
        self.nsBurnLog.append(1.0 if ns_thrust > 0.0 else 0.0)
        self.propellantLog.append(self.propellant)
        self.deltaVLog.append(self._cumulativeDv)


def build_geo_station_keeping(scSim, task_name: str, tag: str, sc_object, mu: float, r_equator_m: float,
                              dry_mass_kg: float, config: GeoStationKeepingConfig,
                              planet_state_out_msg) -> GeoStationKeepingController:
    """One spacecraft's controller, its own ``extForceTorque`` effector, and
    their wiring. The caller has already added ``config.propellant_kg`` to
    the hub mass."""
    controller = GeoStationKeepingController(f"{tag}GeoStationKeeping", mu, r_equator_m, config, dry_mass_kg)
    effector = extForceTorque.ExtForceTorque()
    effector.ModelTag = f"{tag}GeoStationKeepingThrust"
    sc_object.addDynamicEffector(effector)
    controller.scStateInMsg.subscribeTo(sc_object.scStateOutMsg)
    controller.planetStateInMsg.subscribeTo(planet_state_out_msg)
    controller.extForceEffector = effector
    controller.scObject = sc_object
    scSim.AddModelToTask(task_name, effector)
    scSim.AddModelToTask(task_name, controller)
    return controller
