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

r"""Basilisk's own formation-flying flight software as an alternative to
the drift-orbit phasing controller (``schema.scenario.PhasingKeepingConfig``
``control_law``).

Two of Basilisk's ``fswAlgorithms/formationFlying`` modules are run
unmodified, as shipped in the pinned Basilisk release:

* ``"mean_oe"`` -- ``meanOEFeedback``: Lyapunov feedback on the difference
  of mean (Brouwer, J2) equinoctial elements, ``u = -B(oe)^T K delta_oe``
  (Schaub and Junkins, Analytical Mechanics of Space Systems, ch. 14). The
  target difference is zero in every element except the mean longitude,
  which is the scheduled along-track separation divided by the chief's
  semi-major axis. Equinoctial elements (``oeType = 1``) are used because
  the classical set is singular at the near-zero eccentricities of a LEO
  formation (see ``PhasingKeepingController``'s "Numerical conditioning"
  docstring). Needs J2: Earth, with spherical-harmonics gravity of degree
  2 or more (``Scenario.validate``).
* ``"hill_pd"`` -- ``hillFrameRelativeControl``: a PD law on the
  follower's position and velocity in the chief's Hill frame, with
  feedforward of the linearised relative dynamics. The reference position
  is the point on the chief's own circular orbit the scheduled arc length
  ahead (``x = -a (1 - cos theta)``, ``y = a sin theta``) rather than
  ``y = s`` on the Hill frame's straight along-track axis: a straight-line
  offset of 50 km puts the follower 180 m above the chief's orbit, which
  takes a continuous 0.13 N on a 200 kg spacecraft to hold.

Both modules output an inertial force request (``CmdForceInertialMsg``).
:class:`FormationControlBridge` turns that request into thrust from the
follower's ``station_keeping`` thruster, the same one the drift-orbit
controller uses, with the same hardware limits:

* the request's magnitude is limited to ``station_keeping.thrust_n``
  (direction kept): a throttleable (or pulse-width-modulated) thruster
  delivering the requested impulse within each control tick;
* the shared :class:`~.orbit_maintenance.ThrusterOnTimeModel` applies the
  minimum on-time (requests under half an impulse bit are dropped) and
  gives the firing to one controller at a time;
* no thrust in eclipse (``station_keeping.eclipse_sunlit_threshold``);
* propellant from the one shared tank, fed back into the hub mass, as the
  other orbit-maintenance controllers do.

The thruster is an ideal inertial force, as for the other
orbit-maintenance controllers (see ``ThrusterOnTimeModel``'s docstring on
why Basilisk's body-fixed ``thrusterDynamicEffector`` is not used); the
eccentricity-neutral gate does not apply, because both laws control the
relative eccentricity themselves.

The follower's ``station_keeping`` controller is put in formation-follower
mode with no reference, so it never fires on its own: a law that controls
the whole relative state also follows the chief's reboosts, and a second
controller mirroring them would correct the same error twice.

Neither law is designed for a thrust limit. The PD law in particular
needs its commanded acceleration to stay below the thruster's: with a
low-thrust electric thruster and a kilometre-scale error it saturates
continuously, and a saturated PD law in orbit diverges (along-track thrust
moves the follower the opposite way within an orbit). See the
``tests/test_formation_control.py`` runs and ``HISTORY.md``.

The telemetry matches :class:`~.orbit_maintenance.PhasingKeepingController`
(same log lists, Vizard messages and attributes), so results, events and
Vizard treat both alike; ``stateLog`` is :data:`FIRING` while the thruster
fires, :data:`COASTING` otherwise.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from Basilisk.architecture import messaging, sysModel
from Basilisk.fswAlgorithms import hillFrameRelativeControl, meanOEFeedback
from Basilisk.simulation import simpleNav
from Basilisk.utilities import macros, orbitalMotion

from ..schema.scenario import PhasingKeepingConfig
from .constellation import SeparationSchedule
from .orbit_maintenance import (
    LogThinner,
    PhasingKeepingController,
    StationKeepingController,
    _clamp_magnitude,
    _eclipse_illumination_fraction,
    _log_sunlit_transition,
    _wrap_pm_pi,
)
from .propellant_bookkeeping import apply_propellant_burn

COASTING = 0  # stateLog: thruster off
FIRING = 4  # stateLog: thruster firing (after the drift-orbit states 0-3)


def hill_reference_position_m(semi_major_axis_m: float, separation_rad: float) -> list:
    """Hill-frame position [m] of the point ``separation_rad`` of arc ahead
    on a circular orbit of radius ``semi_major_axis_m`` (see the module
    docstring)."""
    return [-semi_major_axis_m * (1.0 - math.cos(separation_rad)),
            semi_major_axis_m * math.sin(separation_rad), 0.0]


class FormationControlBridge(sysModel.SysModel):
    """Applies a Basilisk formation-flying law's force request through the
    follower's shared thruster and tank. Build with
    :func:`build_formation_control`."""

    def __init__(self, name: str, control_law: str, mu: float, nominal_a_m: float,
                 separation_schedule: SeparationSchedule, thrust_n: float, isp_s: float,
                 dry_mass_kg: float, dv_budget_mps: float, eclipse_sunlit_threshold: float,
                 g0_mps2: float = 9.80665):
        super().__init__()
        self.ModelTag = name
        self.controlLaw = control_law

        self.scStateInMsgA = messaging.SCStatesMsgReader()  # chief
        self.scStateInMsgB = messaging.SCStatesMsgReader()  # follower
        self.eclipseInMsgB = messaging.EclipseMsgReader()
        self.forceInMsg = messaging.CmdForceInertialMsgReader()  # the Basilisk law's request
        self.deltaVOutMsg = messaging.DataStorageStatusMsg()
        self.separationRadialOutMsg = messaging.DataStorageStatusMsg()
        self.separationTransverseOutMsg = messaging.DataStorageStatusMsg()
        self.separationNormalOutMsg = messaging.DataStorageStatusMsg()

        # Wired by build_formation_control.
        self.extForceEffectorB = None
        self.scObjectB = None
        self.altitudeControllerB: Optional[StationKeepingController] = None
        self.thruster = None  # the follower's shared ThrusterOnTimeModel
        self.lawModule = None  # meanOEFeedback config or HillFrameRelativeControl
        self.vehicleConfigMsg = None  # "hill_pd": the follower's current mass, for the law
        self.chiefName = ""

        self.mu = mu  # [m^3/s^2]
        self.aNom = nominal_a_m  # [m]
        self.separationSchedule = separation_schedule
        self.thrustN = thrust_n  # [N]
        self.ispS = isp_s  # [s]
        self.g0 = g0_mps2  # [m/s^2]
        self.dryMass = dry_mass_kg  # [kg]
        self.dvBudgetMps = dv_budget_mps  # [m/s] shared-tank total, for the Vizard gauge
        self.sunlitThreshold = eclipse_sunlit_threshold  # [-]
        self.smoothingWindowS = float(2.0 * np.pi * np.sqrt(nominal_a_m ** 3 / mu))  # [s] orbit period
        self.suspendedDueToNonConvergence = False  # never set: no suspension logic in this controller

        self.state = COASTING
        self._lastT: Optional[float] = None  # [s]
        self._targetRad: Optional[float] = None  # [rad] the target last given to the law
        self._direction = np.zeros(3)  # [-] direction of the firing in progress
        self._errorHistory: list = []  # (t [s], error [rad])
        self._relAHistory: list = []  # (t [s], aB - aA [m])
        self._lastInSun: Optional[bool] = None
        self._cumulativeDv = 0.0  # [m/s]
        self._firedSinceLog = False
        self._peakCommandSinceLog = 0.0  # [N]
        self._peakAppliedSinceLog = 0.0  # [N]

        self.lastRadialKm = 0.0  # [km]
        self.lastTransverseKm = 0.0  # [km]
        self.lastNormalKm = 0.0  # [km]
        self.lastTargetSeparationKm = 0.0  # [km]
        self.lastRelativeSmaM = 0.0  # [m]

        self.logThinner = LogThinner()
        self.tLog: list = []
        self.errorDegLog: list = []
        self.stateLog: list = []
        self.propellantLog: list = []
        self.deltaVLog: list = []
        self.relativeSmaLog: list = []
        self.commandedForceLog: list = []  # [N] largest request since the last sample
        self.appliedForceLog: list = []  # [N] largest applied thrust since the last sample

    def Reset(self, CurrentSimNanos):
        self.state = COASTING
        self._lastT = CurrentSimNanos * macros.NANO2SEC
        self._targetRad = None
        self._errorHistory = []
        self._relAHistory = []
        self._apply_target(self.separationSchedule.value_at(self._lastT))
        if self.extForceEffectorB is not None:
            self.extForceEffectorB.extForce_N = [0.0, 0.0, 0.0]

    def _apply_target(self, target_rad: float) -> None:
        """Give the law the scheduled separation (a new target when the
        schedule steps)."""
        if target_rad == self._targetRad:
            return
        self._targetRad = target_rad
        if self.lawModule is None:
            return
        if self.controlLaw == "mean_oe":
            self.lawModule.targetDiffOeMean = [0.0, 0.0, 0.0, 0.0, 0.0, target_rad]
        else:
            self.lawModule.setReferencePosition(hill_reference_position_m(self.aNom, target_rad))
            self.lawModule.setReferenceVelocity([0.0, 0.0, 0.0])

    def _log(self, t: float, error_deg: float, propellant_kg: float, rel_a_m: float) -> None:
        if not self.logThinner.due(t):
            return
        self.tLog.append(t)
        self.errorDegLog.append(error_deg)
        self.stateLog.append(FIRING if self._firedSinceLog else COASTING)
        self.propellantLog.append(propellant_kg)
        self.deltaVLog.append(self._cumulativeDv)
        self.relativeSmaLog.append(rel_a_m)
        self.commandedForceLog.append(self._peakCommandSinceLog)
        self.appliedForceLog.append(self._peakAppliedSinceLog)
        self._firedSinceLog = False
        self._peakCommandSinceLog = 0.0
        self._peakAppliedSinceLog = 0.0

    def _propellant_tracker(self):
        return self.altitudeControllerB

    def UpdateState(self, CurrentSimNanos):
        t = CurrentSimNanos * macros.NANO2SEC  # [s]
        dt = t - self._lastT if self._lastT is not None else 0.0  # [s]
        self._lastT = t
        tracker = self._propellant_tracker()

        stateA, stateB = self.scStateInMsgA(), self.scStateInMsgB()
        rA, vA = np.array(stateA.r_BN_N), np.array(stateA.v_BN_N)
        rB, vB = np.array(stateB.r_BN_N), np.array(stateB.v_BN_N)
        if not (np.all(np.isfinite(rA)) and np.all(np.isfinite(vA)) and np.all(np.isfinite(rB))
                and np.all(np.isfinite(vB)) and np.linalg.norm(np.cross(rA, vA)) > 0.0
                and np.linalg.norm(np.cross(rB, vB)) > 0.0):
            if self.extForceEffectorB is not None:
                self.extForceEffectorB.extForce_N = [0.0, 0.0, 0.0]
            self._log(t, float("nan"), tracker.propellant, float("nan"))
            return

        targetRad = self.separationSchedule.value_at(t)
        self._apply_target(targetRad)  # takes effect at the law's next update

        # Telemetry, as PhasingKeepingController computes it: the one-orbit
        # circular mean of the argument-of-latitude error, the one-orbit
        # mean relative semi-major axis, and the Hill-frame offset.
        uA = PhasingKeepingController._argument_of_latitude(rA, vA)
        uB = PhasingKeepingController._argument_of_latitude(rB, vB)
        self._errorHistory.append((t, _wrap_pm_pi((uB - uA) - targetRad)))
        while self._errorHistory and (t - self._errorHistory[0][0]) > self.smoothingWindowS:
            self._errorHistory.pop(0)
        error = PhasingKeepingController._circular_mean(np.array([e for _, e in self._errorHistory]))
        aA = 1.0 / (2.0 / np.linalg.norm(rA) - np.dot(vA, vA) / self.mu)  # [m]
        aB = 1.0 / (2.0 / np.linalg.norm(rB) - np.dot(vB, vB) / self.mu)  # [m]
        self._relAHistory.append((t, aB - aA))
        while self._relAHistory and (t - self._relAHistory[0][0]) > self.smoothingWindowS:
            self._relAHistory.pop(0)
        relA = float(np.mean([d for _, d in self._relAHistory]))  # [m]
        self.lastRelativeSmaM = relA

        rhoH, _ = orbitalMotion.rv2hill(rA, vA, rB, vB)
        self.lastRadialKm, self.lastTransverseKm, self.lastNormalKm = (float(x) / 1000.0 for x in rhoH)
        self.lastTargetSeparationKm = abs(targetRad) * self.aNom / 1000.0  # [km]
        capacityKm = 2.0 * self.lastTargetSeparationKm  # [km] same gauge scale as the drift-orbit controller
        for msg, value in ((self.separationRadialOutMsg, self.lastRadialKm),
                           (self.separationTransverseOutMsg, self.lastTransverseKm),
                           (self.separationNormalOutMsg, self.lastNormalKm)):
            payload = messaging.DataStorageStatusMsgPayload()
            payload.storageCapacity = capacityKm
            payload.storageLevel = _clamp_magnitude(value, capacityKm)
            msg.write(payload, CurrentSimNanos, self.moduleID)

        inSun = True
        if self.eclipseInMsgB.isLinked():
            illum = _eclipse_illumination_fraction(self.eclipseInMsgB())
            inSun = illum > self.sunlitThreshold
            self._lastInSun = _log_sunlit_transition(self.ModelTag, t, illum, inSun, self._lastInSun)

        massTotal = (self.scObjectB.scMassOutMsg.read().massSC if self.scObjectB is not None
                     else self.dryMass + tracker.propellant)  # [kg]
        if self.vehicleConfigMsg is not None:
            vehicle = messaging.VehicleConfigMsgPayload()
            vehicle.massSC = massTotal
            self.vehicleConfigMsg.write(vehicle, CurrentSimNanos, self.moduleID)

        request = np.array(self.forceInMsg().forceRequestInertial) if self.forceInMsg.isLinked() else np.zeros(3)
        requestN = float(np.linalg.norm(request)) if np.all(np.isfinite(request)) else 0.0  # [N]
        self._peakCommandSinceLog = max(self._peakCommandSinceLog, requestN)
        if requestN > 0.0:
            self._direction = request / requestN

        heldByStationKeeping = tracker.burnOn or self.thruster.firing_owned_by(tracker)
        thrustMag = 0.0  # [N]
        if not heldByStationKeeping and tracker.propellant > 1e-9:
            wantN = min(requestN, self.thrustN)  # [N]
            thrustMag, _extraDv, _tooSmall = self.thruster.command(
                owner=self, want_firing=wantN > 0.0, remaining_dv=wantN * dt / massTotal, sign=0.0,
                thrust_n=self.thrustN, mass_kg=massTotal, dt_s=dt, in_sun=inSun, u_rad=uB,
                v_mps=float(np.linalg.norm(vB)), mean_motion=np.sqrt(self.mu / self.aNom ** 3))

        if thrustMag > 0.0:
            self._cumulativeDv += thrustMag / massTotal * dt  # [m/s]
            self._firedSinceLog = True
            self._peakAppliedSinceLog = max(self._peakAppliedSinceLog, thrustMag)
        self.state = FIRING if thrustMag > 0.0 else COASTING

        hubMass = self.scObjectB.hub.mHub if self.scObjectB is not None else self.dryMass + tracker.propellant
        newMass, tracker.propellant, _burnedKg, _mDot = apply_propellant_burn(
            hubMass, tracker.propellant, thrustMag, self.ispS, dt, self.g0)
        if self.scObjectB is not None:
            self.scObjectB.hub.mHub = newMass
        if self.extForceEffectorB is not None and not heldByStationKeeping:
            self.extForceEffectorB.extForce_N = (thrustMag * self._direction).tolist()

        deltaVMsg = messaging.DataStorageStatusMsgPayload()
        deltaVMsg.storageLevel = self._cumulativeDv  # [m/s] this controller's own delta-V
        deltaVMsg.storageCapacity = self.dvBudgetMps  # [m/s]
        self.deltaVOutMsg.write(deltaVMsg, CurrentSimNanos, self.moduleID)

        self._log(t, float(np.degrees(error)), tracker.propellant, relA)


def build_formation_control(scSim, task_name: str, tag: str, mu: float, chief_sc_object, follower_sc_object,
                            follower_station_keeping_controller: StationKeepingController,
                            follower_eclipse_out_msg, chief_semi_major_axis_km: float,
                            config: PhasingKeepingConfig, central_radius_m: float,
                            j2: Optional[float] = None) -> FormationControlBridge:
    """Builds one follower's Basilisk formation law (``config.control_law``
    ``"mean_oe"`` or ``"hill_pd"``), truth navigation for both spacecraft
    (``simpleNav``, no noise) and the :class:`FormationControlBridge`, in
    that order on ``task_name`` so the law reads this tick's states and
    the bridge this tick's request.

    ``j2`` (needed by ``"mean_oe"``) is the central body's J2;
    ``central_radius_m`` its equatorial radius.
    """
    nominal_a_m = chief_semi_major_axis_km * 1000.0
    schedule = SeparationSchedule(distances_km=config.target_separation_km,
                                  interval_days=config.reconfiguration_interval_days,
                                  semi_major_axis_m=nominal_a_m)
    station_keeping = follower_station_keeping_controller
    bridge = FormationControlBridge(
        name=f"{tag}FormationControl", control_law=config.control_law, mu=mu, nominal_a_m=nominal_a_m,
        separation_schedule=schedule, thrust_n=station_keeping.thrustN, isp_s=station_keeping.ispS,
        dry_mass_kg=station_keeping.dryMass, dv_budget_mps=station_keeping.dvBudgetMps,
        eclipse_sunlit_threshold=station_keeping.sunlitThreshold)

    navs = []
    for role, sc_object in (("Chief", chief_sc_object), ("Follower", follower_sc_object)):
        nav = simpleNav.SimpleNav()
        nav.ModelTag = f"{tag}FormationNav{role}"
        nav.scStateInMsg.subscribeTo(sc_object.scStateOutMsg)
        scSim.AddModelToTask(task_name, nav)
        navs.append(nav)

    if config.control_law == "mean_oe":
        if j2 is None:
            raise ValueError(f"{tag}: phasing_keeping control_law 'mean_oe' needs the central body's J2")
        law = meanOEFeedback.meanOEFeedback()
        law.ModelTag = f"{tag}MeanOEFeedback"
        law.chiefTransInMsg.subscribeTo(navs[0].transOutMsg)
        law.deputyTransInMsg.subscribeTo(navs[1].transOutMsg)
        mass_kg = station_keeping.dryMass + station_keeping.propellant  # [kg] at the start
        law.K = (np.eye(6) * config.mean_oe_gain * mass_kg).flatten().tolist()  # [N*m/s]
        law.oeType = 1  # equinoctial: non-singular at e = 0
        law.mu = mu  # [m^3/s^2]
        law.req = central_radius_m  # [m]
        law.J2 = j2  # [-]
    elif config.control_law == "hill_pd":
        law = hillFrameRelativeControl.HillFrameRelativeControl()
        law.ModelTag = f"{tag}HillFrameRelativeControl"
        law.chiefTransInMsg.subscribeTo(navs[0].transOutMsg)
        law.deputyTransInMsg.subscribeTo(navs[1].transOutMsg)
        vehicle = messaging.VehicleConfigMsgPayload()
        vehicle.massSC = station_keeping.dryMass + station_keeping.propellant  # [kg]
        bridge.vehicleConfigMsg = messaging.VehicleConfigMsg().write(vehicle)
        law.deputyVehicleConfigInMsg.subscribeTo(bridge.vehicleConfigMsg)
        law.setMu(mu)
        law.setK((np.eye(3) * config.hill_position_gain).flatten().tolist())  # [1/s^2]
        law.setP((np.eye(3) * config.hill_velocity_gain).flatten().tolist())  # [1/s]
    else:
        raise ValueError(f"{tag}: phasing_keeping control_law {config.control_law!r} is not a Basilisk law")
    scSim.AddModelToTask(task_name, law)
    bridge.lawModule = law
    bridge._apply_target(schedule.value_at(0.0))
    bridge._navs = navs  # keep the SWIG objects alive with the bridge

    bridge.forceInMsg.subscribeTo(law.forceOutMsg)
    bridge.scStateInMsgA.subscribeTo(chief_sc_object.scStateOutMsg)
    bridge.scStateInMsgB.subscribeTo(follower_sc_object.scStateOutMsg)
    if follower_eclipse_out_msg is not None:
        bridge.eclipseInMsgB.subscribeTo(follower_eclipse_out_msg)
    bridge.extForceEffectorB = station_keeping.extForceEffector
    bridge.scObjectB = follower_sc_object
    bridge.altitudeControllerB = station_keeping
    bridge.thruster = station_keeping.thruster
    bridge.chiefName = chief_sc_object.ModelTag
    # The law controls the whole relative state, chief reboosts included:
    # the follower's station keeping never fires on its own (formation
    # follower with nothing to follow).
    station_keeping.formationFollower = True
    station_keeping.formationReference = None
    scSim.AddModelToTask(task_name, bridge)
    return bridge
