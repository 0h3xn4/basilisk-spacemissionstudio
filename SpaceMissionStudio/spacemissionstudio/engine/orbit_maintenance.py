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
Automated orbit maintenance: independent altitude/semi-major-axis
station-keeping (``schema.scenario.StationKeepingConfig``) and
constellation-wide phasing maintenance
(``schema.scenario.PhasingKeepingConfig``), both with delta-V and
propellant bookkeeping.

:class:`StationKeepingController` is ported from
``../missionAnalysis/constellation_controllers.py``'s
``AltitudeKeepingController`` -- the burn logic (orbit-period-smoothed
altitude, deadband/hysteresis, eclipse gating) and the propellant/delta-V
bookkeeping math (explicit-Euler rocket equation, thrust-to-mass fed back
into ``scObject.hub.mHub`` every tick so achieved acceleration stays
physically consistent as propellant depletes) are unchanged. Two things
differ from the original:

* No separate fast-dynamics/coarse-control task split. ``missionAnalysis``
  needed that to keep a 5-year multi-satellite run tractable; SpaceMissionStudio
  scenarios are much shorter and single-spacecraft-scale, so this runs on
  the same dynamics task as everything else, at
  ``schema.scenario.SimSettings.dynamics_task_rate_s`` -- see
  :func:`build_station_keeping`.
* ``orbit_period_s`` is not a caller-supplied argument -- computed here
  from ``mu``/``nominal_alt_m``/``r_planet_m`` via Kepler's third law
  instead (one fewer thing ``engine.service`` needs to compute).
* No ``log_decimation`` -- SpaceMissionStudio scenarios are short enough that
  logging every tick (matching how every other recorder in
  ``engine.service`` already behaves) doesn't need thinning.
* Publishes ``fuelTankOutMsg`` (a real ``FuelTankMsgPayload``, not part of
  the original ``AltitudeKeepingController``) purely so ``engine.vizard``
  can drive a live "propellant remaining" bar in Vizard off of it (see
  that module) -- this controller still does NOT use a Basilisk
  ``fuelTank`` state effector for the actual physics, only for this one
  output message.
* Publishes ``deltaVOutMsg`` (a ``DataStorageStatusMsgPayload``, chosen
  over reusing ``FuelTankMsgPayload`` a second time so a spacecraft's
  "propellant remaining" and "delta-V used" Vizard panels are backed by
  two genuinely distinct message instances, never two panels racing to
  overwrite the same one) -- same "purely for a live Vizard gauge" reason
  as ``fuelTankOutMsg``, this time driving a delta-V-used bar scaled
  against :func:`~spacemissionstudio.engine.propellant_bookkeeping.total_delta_v_budget`'s
  closed-form total for this controller's own tank. :class:`PhasingKeepingController`
  publishes the same kind of message (its own delta-V, plus a live
  along-track separation-from-chief reading) for the same reason -- see
  that class's own docstring.

Uses a dedicated ``extForceTorque`` effector for the reboost force
(``extForce_N``, inertial-frame), independent of whatever effector
``engine.fsw.build_idealized_actuation`` may also be using for attitude
-control torque on the same spacecraft (``extTorquePntB_B``) -- multiple
dynamic effectors on one hub sum additively, the same pattern
``../missionAnalysis`` itself uses for drag/SRP/thrust as three separate
effectors.

Shared mass bookkeeping (audit fix)
------------------------------------
:class:`StationKeepingController`, :class:`PhasingKeepingController`, and
:class:`ConstantFrameThrustController` each track propellant use and feed
it back into ``scObject.hub.mHub`` so thrust-to-mass stays physically
consistent as propellant depletes. An earlier version of all three
UpdateState methods did this by unconditionally OVERWRITING
``hub.mHub = self.dryMass + self.propellant`` (an absolute value, each
controller's own construction-time-captured belief) every tick -- a real
bug, found by audit and fixed here: with more than one such controller on
the same spacecraft (``station_keeping`` + ``constant_thrust`` is an
explicitly supported combination -- see ``ConstantThrustConfig``'s
docstring), whichever one's ``UpdateState`` happened to run last each
tick silently discarded the other's propellant contribution to the
simulated mass; the same overwrite also silently undid any
``engine.monte_carlo`` ``dry_mass_kg`` dispersion (applied to ``hub.mHub``
once, before ``InitializeSimulation()`` -- see that module's docstring)
the moment the first tick ran.

Fixed by having each controller read the spacecraft's CURRENT
``hub.mHub`` at the top of its own ``UpdateState`` (rather than
recomputing an absolute value from its own captured ``dryMass``) and then
subtract only the propellant mass it ITSELF burns that tick. This
composes correctly no matter how many other controllers or an external
dispersion are also adjusting the same ``hub.mHub`` -- each one's edit is
a self-contained delta, order-independent by construction, rather than a
snapshot that can stomp on someone else's.

A second, related audit finding fixed alongside the above: the
acceleration/delta-V math (``thrustMag / currentMass``) used to read that
same ``hub.mHub`` value too -- which is NOT the spacecraft's true total
mass whenever a ``schema.scenario.FuelTankConfig`` "fuel_tank" state
effector is also configured on the same spacecraft. Basilisk's
``fuelTank`` effector tracks its own mass via ``effProps.mEff``, which
contributes to the vehicle's real dynamics but is NEVER added into
``hub.mHub`` (confirmed directly in ``fuelTank.cpp``) -- so a
station-keeping/phasing/constant-thrust burn running alongside a
fuel-tank-equipped thruster would silently undercount the true mass,
inflating the estimated acceleration and ending the burn early (an
achieved-delta-V undershoot), while the actual simulated dynamics (driven
by Basilisk's own integrator, which DOES sum every state effector's mass
correctly) stayed physically correct throughout. Each controller's
acceleration/delta-V estimate now reads ``scObject.scMassOutMsg.read()
.massSC`` instead -- Basilisk's own hub+state-effector mass aggregate,
confirmed by direct experimentation to be fresh every tick regardless of
this controller's ``AddModelToTask`` priority relative to the
spacecraft's. The propellant-burn WRITE-BACK above still reads/writes
``hub.mHub`` specifically, never ``scMassOutMsg`` -- using the aggregate
there would double-count a coexisting fuel tank's mass (once in the
tank's own state, once baked into ``hub.mHub``).

Verification status: the burn/bookkeeping logic is copied from
``../missionAnalysis``'s already-reviewed controller, not written from
memory (the shared-mass-bookkeeping fix above is this project's own,
found and fixed after a full codebase audit). This whole module's
``requires_basilisk``-marked tests (``tests/test_orbit_maintenance.py``)
-- including the ``deltaVOutMsg``/``separationRadialOutMsg``/
``separationTransverseOutMsg``/``separationNormalOutMsg`` telemetry this
docstring describes above -- have been run for real against a genuine
``pip install "bsk[all]"`` Basilisk build (this project's own "vendoring"
discovery -- see ``SpaceMissionStudio/README.md``'s "Getting started"), not
left unexercised; this superseded an earlier, stale version of this note
that (incorrectly, by the time it was written) still claimed no Basilisk
build was ever available to run these against in this project's own
development sandbox.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from Basilisk.architecture import messaging, sysModel
from Basilisk.simulation import extForceTorque
from Basilisk.utilities import macros, orbitalMotion

from ..schema.scenario import ConstantThrustConfig, PhasingKeepingConfig, StationKeepingConfig
from .constellation import SeparationSchedule
from .propellant_bookkeeping import apply_propellant_burn, total_delta_v_budget

_LOGGER = logging.getLogger(__name__)

# PhasingKeepingController's own divergence guard (see its UpdateState's
# own comment): how many consecutive full correction cycles may fail to
# reduce the tracking error before automatic corrections are suspended.
# 2 (not 1): a single non-improving cycle alone is not yet a strong
# signal of genuine non-convergence (could be ordinary smoothing-window
# noise right at a cycle boundary); two in a row is.
_MAX_NON_CONVERGENT_CYCLES = 2

# Relative semi-major-axis mismatch [m] (follower minus chief, one-orbit
# average) that PhasingKeepingController treats as a disturbance worth
# trimming out on its own, independent of the phase error -- e.g. a reboost
# that only one spacecraft made. Measured to ~0.1 m under real J2 (the
# one-orbit boxcar of the osculating difference), so this is far above
# measurement noise, yet a fraction of the ~5 km mismatch a lone reboost
# causes. Smaller mismatches are left to the ordinary phase-error cycles.
# (Burns hit their delta-V exactly -- partial-tick thrust, see UpdateState
# -- so a trim cannot overshoot back out of this tolerance.)
_RELATIVE_SMA_TRIM_TOLERANCE_M = 25.0


def _log_sunlit_transition(tag: str, t_s: float, illumination: float, in_sun: bool,
                           previous_in_sun: Optional[bool]) -> bool:
    """DEBUG-logs an eclipse reading only when the sunlit/eclipsed verdict
    CHANGES (and on the first tick), returning ``in_sun`` for the caller to
    store. Real bug: these controllers logged every single tick, three
    controllers x every 30 s, which made a real user's 90-day
    formation-template run write a 116 MB log of nothing but that line.
    """
    if in_sun != previous_in_sun:
        _LOGGER.debug("%s: t=%.3f s now %s (eclipse illumination %r)", tag, t_s,
                      "sunlit" if in_sun else "eclipsed", illumination)
    return in_sun


class ThrusterOnTimeModel:
    """On-time command model for the one physical thruster a spacecraft's
    station-keeping and phasing controllers share (see ``StationKeepingConfig``).

    Two hardware/astrodynamics realities the ideal per-tick force used to
    ignore:

    * **Minimum on-time** (``min_on_time_s``, 0 = an ideal, arbitrarily
      short firing). A real thruster can't fire for less than its minimum
      on-time, so it has a minimum impulse bit of ``thrust * min_on_time``.
      A firing, once started, runs for at least that long, even across
      several control ticks. A burn needing LESS than one minimum firing
      is rounded up to it if it needs at least half of one, and otherwise
      skipped.
    * **Eccentricity-neutral burns** (``eccentricity_neutral``). Tangential
      thrust changes the eccentricity vector by ~(2 dv / v) (cos u, sin u)
      at argument of latitude u. A burn spread evenly over whole orbits
      cancels out, but eclipse gating cuts the same arc out of every orbit,
      so a multi-orbit reboost accumulated an eccentricity change
      comparable to the formation template's own e = 0.001. With this on, a
      new firing only STARTS if it keeps the burn's accumulated
      eccentricity change within one orbit's natural excursion of
      continuous thrust.
      The thruster then skips just enough sunlit arc to stay balanced
      (each firing lasts at most ``max(min_on_time_s, dt)`` so the gate
      is re-checked often).

    Basilisk's own ``thrusterDynamicEffector`` was deliberately NOT used:
    its thrusters are fixed in the BODY frame, so burning along-track
    would need the spacecraft to slew to point along its velocity, and an
    orbit-only scenario has no attitude control at all. This model keeps
    the ideal inertial force but gives it the firing constraints of real
    hardware. A firing is applied as its average force over each 30 s
    tick (same impulse as full thrust for part of the tick).
    """

    def __init__(self, min_on_time_s: float = 0.0, eccentricity_neutral: bool = False):
        self.minOnTimeS = float(min_on_time_s)  # [s]
        self.eccentricityNeutral = bool(eccentricity_neutral)
        self.pulseLeftS = 0.0  # [s] committed on-time still to fire
        self.pulseOwner = None  # the controller whose command started the firing in progress
        self.eccVector = np.zeros(2)  # [-] eccentricity-vector change of the current maneuver (node frame)
        self._eccOwner = None  # the controller whose maneuver eccVector belongs to

    def reset(self) -> None:
        """Start of a new maneuver: no firing in progress, no accumulated
        eccentricity change."""
        self.pulseLeftS = 0.0
        self.pulseOwner = None
        self.eccVector = np.zeros(2)
        self._eccOwner = None

    def firing_owned_by(self, owner) -> bool:
        """True while a firing that ``owner`` started is still committed."""
        return self.pulseLeftS > 0.0 and self.pulseOwner is owner

    def minimum_impulse_dv(self, thrust_n: float, mass_kg: float) -> float:
        """Delta-V [m/s] of one minimum firing (0 for an ideal thruster)."""
        return thrust_n * self.minOnTimeS / mass_kg

    def _ecc_step(self, sign: float, dv: float, u_rad: float, v_mps: float) -> np.ndarray:
        return sign * 2.0 * dv / v_mps * np.array([np.cos(u_rad), np.sin(u_rad)])

    def _start_allowed(self, sign, on_time_s, thrust_n, mass_kg, u_rad, v_mps, mean_motion) -> bool:
        if not self.eccentricityNeutral:
            return True
        accel = thrust_n / mass_kg  # [m/s^2]
        # One orbit of continuous tangential thrust traces a circle through
        # the origin of the eccentricity plane, of diameter
        # 4 * accel / (v * n): an unavoidable transient that an evenly
        # spread burn returns to zero from. Allowing exactly that much means
        # an uninterrupted burn is never held back; only the drift that
        # eclipse gating adds orbit after orbit is.
        tolerance = max(4.0 * accel / (v_mps * mean_motion),
                        2.5 * 2.0 * accel * on_time_s / v_mps)
        after = self.eccVector + self._ecc_step(sign, accel * on_time_s, u_rad, v_mps)
        return float(np.linalg.norm(after)) <= max(float(np.linalg.norm(self.eccVector)), tolerance)

    def command(self, *, owner, want_firing: bool, remaining_dv: Optional[float], sign: float, thrust_n: float,
                mass_kg: float, dt_s: float, in_sun: bool, u_rad: float, v_mps: float, mean_motion: float):
        """This tick's average thrust [N], plus the committed delta-V [m/s]
        a newly started firing adds beyond ``remaining_dv`` (non-zero only
        when a small burn was rounded UP to one minimum firing -- the
        caller extends its own burn target by it), and whether a
        ``remaining_dv`` burn turned out too small to fire at all.

        ``remaining_dv`` None = open-ended (station-keeping: fire for as
        long as ``want_firing``). Eclipse (``not in_sun``) always cuts a
        firing short -- the bus has no power for it.

        ``owner`` is the calling controller. The station-keeping and phasing
        controllers share one thruster, so a firing belongs to whoever
        started it: another caller gets no thrust until it ends (real bug
        caught in verification: station-keeping used to continue, and log,
        half of every phasing firing as its own).
        """
        if self.pulseLeftS > 0.0 and self.pulseOwner is not owner:
            return 0.0, 0.0, False  # the thruster is busy with another controller's firing
        if not in_sun or dt_s <= 0.0:
            self.pulseLeftS = 0.0
            return 0.0, 0.0, False
        if self._eccOwner is not owner:
            self.eccVector = np.zeros(2)  # a different controller's maneuver
            self._eccOwner = owner
        extra_dv = 0.0
        if self.pulseLeftS <= 0.0:
            if not want_firing:
                return 0.0, 0.0, False
            chunk_s = max(self.minOnTimeS, dt_s)
            if remaining_dv is None:
                on_time = chunk_s
            else:
                on_time = remaining_dv * mass_kg / thrust_n  # [s]
                if on_time <= 0.0:
                    return 0.0, 0.0, True
                if self.minOnTimeS > 0.0 and on_time < self.minOnTimeS:
                    if on_time < 0.5 * self.minOnTimeS:
                        return 0.0, 0.0, True  # below half an impulse bit: not worth a firing
                    extra_dv = (self.minOnTimeS - on_time) * thrust_n / mass_kg
                    on_time = self.minOnTimeS
                if self.eccentricityNeutral and on_time >= chunk_s + self.minOnTimeS:
                    # Split into gate-checked pieces, but never leave a
                    # last piece shorter than one minimum firing (it would
                    # be rounded up or skipped): fly a shorter remainder,
                    # up to chunk + minimum on-time, as one firing.
                    on_time = chunk_s
            if not self._start_allowed(sign, on_time, thrust_n, mass_kg, u_rad, v_mps, mean_motion):
                return 0.0, 0.0, False
            self.pulseLeftS = on_time
            self.pulseOwner = owner
        on = min(dt_s, self.pulseLeftS)
        self.pulseLeftS -= on
        thrust = thrust_n * on / dt_s
        self.eccVector = self.eccVector + self._ecc_step(sign, thrust_n * on / mass_kg, u_rad, v_mps)
        return thrust, extra_dv, False


def _crossed_zero(error_rad: float, drift_sign: float) -> bool:
    """True once a phase error that started with sign ``drift_sign`` has
    crossed ZERO -- not merely changed sign by wrapping through +/-180 deg
    (an error near +/-pi means "half an orbit away", the opposite of
    "target reached")."""
    return bool(error_rad != 0.0 and np.sign(error_rad) != drift_sign and abs(error_rad) < 0.5 * np.pi)


def _wrap_pm_pi(angle_rad: float) -> float:
    """Wrap an angle [rad] to (-pi, pi]."""
    return (angle_rad + np.pi) % (2.0 * np.pi) - np.pi


def _clamp_magnitude(value: float, limit: float) -> float:
    """Return ``abs(value)`` clamped to ``[0, limit]`` -- used for a live
    Vizard GenericStorage panel's ``storageLevel`` (see
    ``PhasingKeepingController.UpdateState``'s own comment).

    GenericStorage's own field comments -- both
    ``vizStructures.h``'s (``"current/maximum absolute value of the
    storage device"``) and the wire-format ``vizMessage.proto``'s
    (identical wording) -- document ``currentValue``/``maxValue`` as a
    non-negative gauge, e.g. a battery charge or a propellant tank level.
    An earlier revision of this function (``_clamp_symmetric``) clamped
    to ``[-limit, limit]`` instead, to preserve "ahead of"/"behind the
    chief" sign -- a real user screenshot then showed exactly the panels
    that were negative at that moment (Radial, Normal) rendering
    "Unavailable" in Vizard, while the one that happened to be positive
    (Transverse) rendered normally.

    CONFIRMED, not just inferred from the field comments: the ``0h3xn4/
    vizard`` Unity project's own source --
    ``VizardUnityProject/Assets/Scripts/MainScene/MainSceneGUI/
    GenericStoragePanel/GenericStorageUnitMethods.cs``,
    ``UpdateCurrentValue()`` -- branches on ``value >= 0`` with no
    tolerance whatsoever: ``value < 0`` unconditionally sets
    ``hoverText``/``verboseText`` to ``"Unavailable"`` (``"Stale"`` in
    VR), grays the bar, and zeroes its width, regardless of
    ``maxValue``/color thresholds/anything else. See this class's own
    docstring for the full reasoning.
    """
    return min(abs(value), limit)


def _eclipse_illumination_fraction(eclipse_payload) -> float:
    """[-] 0 = fully eclipsed, 1 = fully sunlit, from a real
    ``EclipseMsgPayload``.

    Real crash report: ``illuminationFactor`` (this project's own source
    tree copy of Basilisk documents it as the current field name --
    ``src/architecture/msgPayloadDefC/EclipseMsgPayload.h``) does not
    exist at all on a real user's installed Basilisk build --
    ``AttributeError: 'EclipseMsgPayload' object has no attribute
    'illuminationFactor'`` -- meaning that build predates the field being
    added; only the older ``shadowFactor`` name exists there. This
    project does not pin an exact Basilisk version (see
    ``pyproject.toml``'s own comment on why), so both must work: try the
    current name first, fall back to the older one only if it is genuinely
    absent on the installed build.
    """
    try:
        return eclipse_payload.illuminationFactor
    except AttributeError:
        return eclipse_payload.shadowFactor


class StationKeepingController(sysModel.SysModel):
    """Independent altitude/SMA station-keeping for one spacecraft -- see
    this module's docstring and ``schema.scenario.StationKeepingConfig``'s
    docstring for the control law and bookkeeping. Construct via
    :func:`build_station_keeping` rather than directly; that function
    wires ``scStateInMsg``/``eclipseInMsg``/``extForceEffector``/
    ``scObject``, which this class needs set before ``UpdateState`` runs.

    Formation-follower mode
    -----------------------
    :func:`build_phasing_keeping` switches a phasing follower's own
    controller into this mode (``formationFollower = True``, plus
    ``formationReference`` = the chief's own controller, or ``None`` if
    the chief has no station-keeping). The follower then never reboosts
    toward its OWN absolute ``target_altitude_km``. Instead it mirrors
    the chief's reboosts tick for tick, and keeps only a safety floor of
    ``deadband_km`` below the chief's smoothed altitude.

    Real bug behind this, reproduced from a real user's 90-day run of the
    formation template: an absolute target makes the two spacecraft
    reboost independently. That run's follower (with a 2 km deadband)
    reboosted to its 550 km target at t = 0.07 d while the chief, whose
    natural mean altitude was ~545 km, never did. The result was a ~5 km
    semi-major-axis mismatch, i.e. ~6 deg/day of relative drift, which
    the phasing controller could never undo (its corrections are capped
    at a few km and sized in metres). The follower lapped the chief
    repeatedly for the whole run. Mirroring the chief keeps both orbits
    raised together, and the phasing controller's own closed-loop
    relative-SMA trim removes whatever small mismatch remains.
    """

    def __init__(
        self,
        name: str,
        mu: float,
        nominal_alt_m: float,
        deadband_m: float,
        r_planet_m: float,
        thrust_n: float,
        isp_s: float,
        dry_mass_kg: float,
        propellant_kg: float,
        eclipse_sunlit_threshold: float = 0.99,
        g0_mps2: float = 9.80665,
        min_on_time_s: float = 0.0,
        eccentricity_neutral: bool = False,
    ):
        super().__init__()
        self.ModelTag = name

        self.scStateInMsg = messaging.SCStatesMsgReader()
        self.eclipseInMsg = messaging.EclipseMsgReader()
        # Live propellant telemetry, for Vizard's GenericStorage "fuel tank"
        # panel (see engine.vizard) -- this controller tracks propellant as
        # a plain Python scalar (see module docstring for why: no
        # fuelTank state effector), so there is no Basilisk message
        # carrying it unless this module publishes one itself.
        self.fuelTankOutMsg = messaging.FuelTankMsg()
        # Live delta-V-used telemetry, for Vizard's GenericStorage
        # "delta-V" panel (see engine.vizard and this module's own
        # docstring) -- a DataStorageStatusMsgPayload (not a second
        # FuelTankMsgPayload) so the propellant and delta-V panels are
        # backed by two distinct messages.
        self.deltaVOutMsg = messaging.DataStorageStatusMsg()

        # Wired up externally (see build_station_keeping): the
        # extForceTorque effector this controller commands, and the
        # spacecraft hub whose mass it updates as propellant depletes.
        self.extForceEffector = None
        self.scObject = None

        self.mu = mu  # [m^3/s^2]
        self.nominalAlt = nominal_alt_m  # [m]
        self.deadband = deadband_m  # [m]
        self.rPlanet = r_planet_m  # [m]
        self.thrustN = thrust_n  # [N]
        self.ispS = isp_s  # [s]
        self.g0 = g0_mps2  # [m/s^2]
        self.dryMass = dry_mass_kg  # [kg]
        self.propellant = propellant_kg  # [kg]
        self._initialPropellantKg = propellant_kg  # [kg] fixed tank capacity, for fuelTankOutMsg.maxFuelMass
        # [m/s] closed-form Tsiolkovsky total for a FULL tank -- the fixed
        # "gauge max" deltaVOutMsg.storageCapacity below reports every
        # tick; NOT recomputed from the depleting propellant_kg (that
        # would shrink the gauge's own max as propellant burns, which is
        # not what "how much of this tank's total budget have I used so
        # far" should show).
        self.dvBudgetMps = total_delta_v_budget(dry_mass_kg, propellant_kg, isp_s, g0_mps2)
        semi_major_axis_m = r_planet_m + nominal_alt_m  # [m]
        self.smoothingWindowS = float(2.0 * np.pi * np.sqrt(semi_major_axis_m ** 3 / mu))  # [s] orbit period
        self.sunlitThreshold = eclipse_sunlit_threshold  # [-]
        # The physical thruster's firing model -- shared with a co-located
        # PhasingKeepingController (build_phasing_keeping), see
        # ThrusterOnTimeModel.
        self.thruster = ThrusterOnTimeModel(min_on_time_s, eccentricity_neutral)
        self._burnWasOn = False

        self.burnOn = False
        # Formation-follower mode -- see this class's own docstring. Set by
        # build_phasing_keeping, never by build_station_keeping itself.
        self.formationFollower = False
        self.formationReference: Optional["StationKeepingController"] = None
        self._floorBurn = False  # formation follower: the current burn is a safety-floor burn, not a mirror
        # Latest smoothed altitude (None before the first tick) -- read by
        # a formation follower's controller to compare against this one.
        self.lastSmoothAlt: Optional[float] = None  # [m]
        self._lastInSun: Optional[bool] = None  # for _log_sunlit_transition
        self._lastT: Optional[float] = None  # [s]
        self._altHistory: list = []  # list of (t [s], alt [m]) for the smoothing window
        # [s] When the FIRST sample since Reset() was recorded -- tracked
        # separately from _altHistory[0][0] because the pruning loop
        # below keeps that oldest-kept-sample's age at or under
        # smoothingWindowS by construction, so it can never itself reach
        # or exceed smoothingWindowS; this is the real "has a full
        # orbital period of history actually accumulated yet" clock (see
        # UpdateState's own cold-start-guard comment).
        self._historyStartT: Optional[float] = None  # [s]

        # Python-side telemetry (cheap; avoids extra BSK messages/recorders
        # for what is ultimately just a handful of scalars per tick).
        self.tLog: list = []
        self.altLog: list = []
        self.smoothAltLog: list = []
        self.burnLog: list = []
        self.propellantLog: list = []
        self.deltaVLog: list = []
        self._cumulativeDv = 0.0  # [m/s]

    def Reset(self, CurrentSimNanos):
        self.burnOn = False
        self._floorBurn = False
        self.lastSmoothAlt = None
        self._lastT = CurrentSimNanos * macros.NANO2SEC
        self._altHistory = []
        self._historyStartT = None
        if self.extForceEffector is not None:
            self.extForceEffector.extForce_N = [0.0, 0.0, 0.0]

    def _formation_follower_burn_on(self, smoothAlt: float, windowFull: bool) -> bool:
        """Burn decision in formation-follower mode (see this class's own
        docstring): mirror the chief's reboost while it burns, and
        otherwise only fire (until level with the chief again) if this
        spacecraft has fallen more than ``deadband`` below the chief's
        smoothed altitude. With no chief controller to follow, never fire
        on its own -- the co-located phasing controller's relative-SMA
        trim then keeps the follower matched to the decaying chief.
        """
        reference = self.formationReference
        if reference is None or reference.lastSmoothAlt is None:
            self._floorBurn = False
            return False
        if reference.burnOn:
            self._floorBurn = False
            return True
        if self.burnOn and self._floorBurn:  # a safety-floor burn already in progress
            self._floorBurn = smoothAlt < reference.lastSmoothAlt
            return self._floorBurn
        # A MIRRORED burn ends with the reference's. Real bug: it used to be
        # carried on as if it were a safety-floor burn, until this smoothed
        # altitude caught up with the reference's -- but a one-orbit boxcar
        # lags a burn by up to an orbit, so a follower that ended its mirror
        # a few metres short kept firing and overshot by ~700 m of semi-major
        # axis (with eclipse gating and a 300 s minimum on-time). The
        # co-located phasing controller trims the small residual instead.
        self._floorBurn = windowFull and smoothAlt < (reference.lastSmoothAlt - self.deadband)
        return self._floorBurn

    def UpdateState(self, CurrentSimNanos):
        t = CurrentSimNanos * macros.NANO2SEC  # [s]
        dt = t - self._lastT if self._lastT is not None else 0.0  # [s]
        self._lastT = t

        scState = self.scStateInMsg()
        rVec = np.array(scState.r_BN_N)  # [m]
        vVec = np.array(scState.v_BN_N)  # [m/s]

        # Same reasoning as PhasingKeepingController.UpdateState()'s own
        # matching guard: a non-finite (or, for vVec, exactly zero --
        # np.linalg.norm(vVec) below would divide by it) state must never
        # be allowed to propagate into a commanded force -- command no
        # thrust and hold state this tick instead.
        if not (np.all(np.isfinite(rVec)) and np.all(np.isfinite(vVec)) and np.linalg.norm(vVec) > 0.0):
            if self.extForceEffector is not None:
                self.extForceEffector.extForce_N = [0.0, 0.0, 0.0]
            self.tLog.append(t)
            self.altLog.append(float("nan"))
            self.smoothAltLog.append(float("nan"))
            self.burnLog.append(0)
            self.propellantLog.append(self.propellant)
            self.deltaVLog.append(self._cumulativeDv)
            return

        alt = float(np.linalg.norm(rVec) - self.rPlanet)  # [m]

        # Orbit-period boxcar smoothing to reject short-period altitude
        # oscillation and only respond to secular (e.g. drag-driven) decay.
        if self._historyStartT is None:
            self._historyStartT = t
        self._altHistory.append((t, alt))
        while self._altHistory and (t - self._altHistory[0][0]) > self.smoothingWindowS:
            self._altHistory.pop(0)
        smoothAlt = float(np.mean([a for _, a in self._altHistory]))

        # Real bug, found by reproducing a real Vizard screenshot showing
        # a co-located PhasingKeepingController's along-track separation
        # diverging without bound instead of converging toward its own
        # target (see that class's own docstring) -- traced to THIS
        # controller, not phasing-keeping's own control law. _altHistory
        # starts EMPTY every Reset(), so smoothAlt at/near t=0 is averaged
        # over however few samples have accumulated so far -- at the very
        # first tick, exactly ONE: the raw OSCULATING altitude at
        # whatever point in the orbit the spacecraft happens to start.
        # For a spacecraft placed near perigee (a common, deliberate
        # choice -- e.g. true_anomaly_deg=0, as this module's own
        # formation-flying template uses), that one sample reads well
        # BELOW the orbit's true mean altitude from completely normal
        # Keplerian motion, with nothing secular (drag decay, etc.)
        # involved at all. Confirmed directly: a bare two-body repro
        # (point-mass gravity, no drag/J2) with the spacecraft started at
        # perigee showed burnOn flip True at t=0 and stay True for
        # roughly half an orbital period, injecting a real, unintended
        # ~540 m semi-major-axis change before the window held enough
        # samples to reflect the orbit's genuine, already-on-target
        # average altitude -- a co-located PhasingKeepingController
        # sharing this same thruster has no way to distinguish that
        # perturbation from a real orbital anomaly, and its own single,
        # correctly-sized correction burn is then overwhelmed by it.
        # Fixed by gating a NEW burn's START on the window actually
        # holding a full orbital period of real history -- the exact
        # same "don't trust a partial window" discipline this smoothing
        # filter already claims for itself in the comment above, just
        # not previously applied at cold start. Never gates the
        # symmetric EXIT condition below, which only matters once a burn
        # has legitimately begun (by then the window is always full).
        # Delays reacting to a genuinely real altitude deficiency at
        # simulation start by at most one orbital period -- consistent
        # with, not a new tradeoff against, this controller's own stated
        # purpose of responding only to SECULAR decay, which by
        # definition unfolds over many orbits anyway.
        #
        # Deliberately measured against self._historyStartT (set once,
        # the first tick after Reset()), NOT self._altHistory[0][0]: the
        # pruning loop just above keeps the OLDEST entry still in the
        # window at or under smoothingWindowS old by construction, so
        # that age can never itself reach smoothingWindowS -- comparing
        # against it here would make this guard permanently, silently
        # unsatisfiable (a real bug caught in this fix's own first-draft
        # test run: the window never read as "full" even after a
        # genuinely full orbital period of real ticks had elapsed).
        windowFull = (t - self._historyStartT) >= self.smoothingWindowS
        self.lastSmoothAlt = smoothAlt
        if self.formationFollower:
            self.burnOn = self._formation_follower_burn_on(smoothAlt, windowFull)
        elif not self.burnOn and windowFull and smoothAlt < (self.nominalAlt - self.deadband):
            self.burnOn = True
        elif self.burnOn and smoothAlt >= self.nominalAlt:
            self.burnOn = False

        inSun = True
        if self.eclipseInMsg.isLinked():
            illum = _eclipse_illumination_fraction(self.eclipseInMsg())
            inSun = illum > self.sunlitThreshold
            self._lastInSun = _log_sunlit_transition(self.ModelTag, t, illum, inSun, self._lastInSun)

        if self.burnOn and not self._burnWasOn:
            self.thruster.reset()  # a new reboost maneuver
        self._burnWasOn = self.burnOn
        thrustMag = 0.0  # [N]
        if self.burnOn and self.propellant <= 1e-9:
            self.bskLogger.warning(f"{self.ModelTag}: propellant depleted, reboost inhibited")
        elif self.burnOn or self.thruster.firing_owned_by(self):
            massEstimate = (self.scObject.scMassOutMsg.read().massSC if self.scObject is not None
                            else (self.dryMass + self.propellant))  # [kg]
            meanMotion = np.sqrt(self.mu / (self.rPlanet + self.nominalAlt) ** 3)  # [rad/s]
            # A firing already started keeps going for at least its minimum
            # on-time, even if burnOn just dropped (see ThrusterOnTimeModel).
            thrustMag, _extraDv, _tooSmall = self.thruster.command(
                owner=self, want_firing=self.burnOn, remaining_dv=None, sign=1.0, thrust_n=self.thrustN,
                mass_kg=massEstimate, dt_s=dt, in_sun=inSun,
                u_rad=PhasingKeepingController._argument_of_latitude(rVec, vVec),
                v_mps=float(np.linalg.norm(vVec)), mean_motion=meanMotion)

        # Achieved acceleration/delta-v depends on the spacecraft's TRUE
        # total mass -- hub.mHub ALONE undercounts it whenever a
        # schema.scenario.FuelTankConfig "fuel_tank" state effector is
        # also configured (Basilisk's fuelTank tracks its own mass via
        # effProps.mEff, never touching hub.mHub -- confirmed directly in
        # fuelTank.cpp), which silently shrinks this controller's
        # estimated/accumulated delta-V and can end a burn early. See
        # this module's "Shared mass bookkeeping" docstring note:
        # scMassOutMsg.massSC is Basilisk's own aggregate (hub + every
        # state effector's mass contribution), fresh every tick regardless
        # of this controller's own AddModelToTask priority relative to the
        # spacecraft's (confirmed by direct experimentation).
        trueTotalMass = (
            self.scObject.scMassOutMsg.read().massSC if self.scObject is not None
            else (self.dryMass + self.propellant)
        )
        if thrustMag > 0.0:
            self._cumulativeDv += (thrustMag / trueTotalMass) * dt  # [m/s]

        # The burn bookkeeping write-back, in contrast, must stay a
        # self-contained delta against hub.mHub specifically (NOT
        # trueTotalMass) -- apply_propellant_burn's returned
        # new_total_mass_kg is written straight back to hub.mHub below, so
        # feeding it trueTotalMass would double-count a coexisting
        # fuel_tank's own mass (once in the tank's own state, once baked
        # into hub.mHub). See this module's "Shared mass bookkeeping"
        # docstring note for why hub.mHub (not an absolute recomputed
        # value) is the correct base for this part.
        hubMass = self.scObject.hub.mHub if self.scObject is not None else (self.dryMass + self.propellant)
        newMass, self.propellant, _burnedKg, mDot = apply_propellant_burn(
            hubMass, self.propellant, thrustMag, self.ispS, dt, self.g0)
        if self.scObject is not None:
            self.scObject.hub.mHub = newMass

        forceVec = np.zeros(3)
        if thrustMag > 0.0:
            vHat = vVec / np.linalg.norm(vVec)
            forceVec = thrustMag * vHat
        if self.extForceEffector is not None:
            self.extForceEffector.extForce_N = forceVec.tolist()

        fuelTankMsg = messaging.FuelTankMsgPayload()
        fuelTankMsg.fuelMass = self.propellant  # [kg]
        fuelTankMsg.fuelMassDot = -mDot  # [kg/s] negative: mass decreasing
        fuelTankMsg.maxFuelMass = self._initialPropellantKg  # [kg]
        self.fuelTankOutMsg.write(fuelTankMsg, CurrentSimNanos, self.moduleID)

        deltaVMsg = messaging.DataStorageStatusMsgPayload()
        deltaVMsg.storageLevel = self._cumulativeDv  # [m/s]
        deltaVMsg.storageCapacity = self.dvBudgetMps  # [m/s]
        self.deltaVOutMsg.write(deltaVMsg, CurrentSimNanos, self.moduleID)

        self.tLog.append(t)
        self.altLog.append(alt)
        self.smoothAltLog.append(smoothAlt)
        self.burnLog.append(1 if thrustMag > 0.0 else 0)
        self.propellantLog.append(self.propellant)
        self.deltaVLog.append(self._cumulativeDv)


def build_station_keeping(scSim, task_name: str, tag: str, sc_object, mu: float, r_planet_m: float,
                           dry_mass_kg: float, config: StationKeepingConfig,
                           eclipse_out_msg=None) -> StationKeepingController:
    """Builds and wires one spacecraft's :class:`StationKeepingController`:
    a dedicated ``extForceTorque`` effector for the reboost force, the
    controller itself subscribed to the spacecraft's own state (and, if
    given, an eclipse output message for sunlit gating -- see
    ``engine.service``'s shared eclipse-model wiring, the same one
    ``PowerConfig`` uses). Adds both to ``task_name``.

    ``dry_mass_kg`` is the spacecraft's mass WITHOUT station-keeping
    propellant (``SpacecraftConfig.dry_mass_kg`` -- the caller is
    responsible for having already set ``sc_object.hub.mHub`` to
    ``dry_mass_kg + config.propellant_kg`` before calling this, so the
    initial simulated mass matches what this controller believes it is
    depleting from).
    """
    controller = StationKeepingController(
        name=f"{tag}StationKeeping",
        mu=mu,
        nominal_alt_m=config.target_altitude_km * 1000.0,
        deadband_m=config.deadband_km * 1000.0,
        r_planet_m=r_planet_m,
        thrust_n=config.thrust_n,
        isp_s=config.isp_s,
        dry_mass_kg=dry_mass_kg,
        propellant_kg=config.propellant_kg,
        eclipse_sunlit_threshold=config.eclipse_sunlit_threshold,
        min_on_time_s=config.min_on_time_s,
        eccentricity_neutral=config.eccentricity_neutral_burns,
    )

    thruster = extForceTorque.ExtForceTorque()
    thruster.ModelTag = f"{tag}StationKeepingThruster"
    sc_object.addDynamicEffector(thruster)
    scSim.AddModelToTask(task_name, thruster)

    controller.extForceEffector = thruster
    controller.scObject = sc_object
    controller.scStateInMsg.subscribeTo(sc_object.scStateOutMsg)
    if eclipse_out_msg is not None:
        controller.eclipseInMsg.subscribeTo(eclipse_out_msg)
    scSim.AddModelToTask(task_name, controller)
    return controller


class PhasingKeepingController(sysModel.SysModel):
    """In-plane phasing / constellation-keeping between two co-planar
    spacecraft -- see this module's docstring and
    ``schema.scenario.PhasingKeepingConfig``'s docstring for the control
    law and why this always shares a thruster/tank with a co-located
    :class:`StationKeepingController`. Construct via
    :func:`build_phasing_keeping` rather than directly.

    Ported from ``../missionAnalysis/constellation_controllers.py``'s
    controller of the same name -- the drift-orbit state machine
    (IDLE/BURN_OUT/DRIFT/BURN_RESTORE) and the thruster-arbitration/
    shared-propellant logic are unchanged. The phase-error computation
    itself is NOT unchanged -- see "Numerical conditioning of the phase
    error" below, a real bug found by this project's own audit, after a
    real user's screenshot kept showing the along-track separation
    diverging even after an earlier, unrelated cold-start fix (see
    :class:`StationKeepingController`'s own docstring) had already
    landed. Still smoothed over one orbital period to reject J2
    short-period noise, same as the ported original. Differs the same two
    ways :class:`StationKeepingController` differs from its own original
    (no fast-dyn/coarse-ctrl task split, no ``log_decimation``), plus:
    ``thrust_n``/``isp_s``/``dry_mass_kg`` are not schema fields here --
    :func:`build_phasing_keeping` always reads them off the co-located
    ``StationKeepingController`` (see ``PhasingKeepingConfig``'s
    docstring for why: one physical thruster/tank, so there is no
    schema-level way for the two to disagree about it). ``dv_budget_mps``
    is read the same way (the co-located controller's own
    ``dvBudgetMps`` -- see that class's docstring) rather than
    recomputed here, for the same one-tank-no-disagreement reason.

    Numerical conditioning of the phase error
    ------------------------------------------
    The ported original measured along-track phase error from the
    difference of each spacecraft's osculating MEAN ANOMALY
    (``orbitalMotion.rv2elem`` -> ``f2E`` -> ``E2M``, i.e. via each
    spacecraft's own, individually-decomposed eccentricity/argument-of
    -periapsis/true-anomaly). Real bug, found by audit after a real
    user's Vizard screenshot kept showing the along-track separation
    diverging without bound even after the cold-start fix above had
    landed: reproduced directly against a genuine Basilisk build with
    real (degree >= 2) spherical-harmonics Earth gravity active on the
    exact chief/follower elements this module's own formation-flying
    template uses (``a`` = 6928 km, ``e`` = 0.001) -- the classical
    orbital-element decomposition is numerically SINGULAR as
    eccentricity -> 0 (argument of periapsis, hence true/mean anomaly
    measured from it, becomes meaningless once the osculating
    eccentricity vector's direction is undefined), a well-known
    limitation of classical (as opposed to non-singular/equinoctial)
    element sets. J2's own short-period oscillation of the osculating
    eccentricity vector is, by itself, enough to carry a near-circular
    orbit's ``e`` through numerically-zero every orbit -- confirmed
    directly: with the above elements, ``e`` dipped to ~7.5e-5 and the
    recovered argument of periapsis swung by ~180 deg within three 30 s
    ticks, while the REAL geometric along-track separation
    (``orbitalMotion.rv2hill``, i.e. exactly ``lastTransverseKm`` below)
    barely moved at all over that same interval. The resulting
    mean-anomaly-difference "error" read as large as several THOUSAND
    km of spurious phase error within a handful of ticks, which this
    controller's own control law (faithfully) acted on as if it were
    real -- computing a wildly wrong ``deltaA``/burn direction from it,
    actually perturbing the real orbit, and in the reproduction that
    exposed this, tripping the divergence guard (below) after just one
    such bogus cycle, suspending all further automatic correction for
    the rest of the run while the real separation then free-drifted,
    uncorrected, off whatever the bogus burn had left it at -- matching
    a real user's "pinned at the Vizard gauge ceiling" screenshot
    exactly.

    Fixed by :func:`_argument_of_latitude`: the angle ``u = omega + f``,
    computed DIRECTLY from each spacecraft's instantaneous position/
    velocity via the ascending-node/orbit-normal geometry, never
    decomposing ``e``/``omega``/``f`` individually. ``u`` stays
    numerically well-behaved all the way through ``e -> 0`` -- it is
    exactly the quantity non-singular/equinoctial element sets are built
    around retaining, for exactly this reason -- at the (textbook,
    standard) cost of a tiny, un-corrected equation-of-center bias
    (true, not mean, argument of latitude) of order ``2*e`` radians,
    utterly negligible for the near-circular (``e`` well under ~0.05)
    LEO constellations this controller targets (``engine.constellation``'s
    own Walker-pattern generator defaults ``eccentricity`` to 0.0 "for
    the usual circular case"). A rigorous equinoctial-element
    reformulation (correct at any eccentricity, including the
    classical-element-friendly high-``e`` regime this approximation does
    NOT cover) is a real, documented follow-on, not implemented here.

    Publishes two more live-Vizard-only messages (see this module's
    docstring and ``engine.vizard``), same "never fed back into simulated
    physics" caveat as ``StationKeepingController.deltaVOutMsg``:

    * ``deltaVOutMsg`` -- this controller's OWN cumulative delta-V (i.e.
      phasing burns only, NOT the co-located ``StationKeepingController``'s
      reboost delta-V -- the two are reported as separate Vizard panels
      deliberately, so a user can see the propellant cost of altitude
      -keeping and phasing-keeping separately, even though both draw from
      the one shared tank).
    * ``separationRadialOutMsg``/``separationTransverseOutMsg``/
      ``separationNormalOutMsg`` -- the actual, LIVE chief/follower offset
      in the chief's own Hill (RTN) frame (``storageLevel``, km each),
      via ``orbitalMotion.rv2hill`` -- the exact same function
      ``engine.formation``'s wizard itself uses to place a follower, so
      these numbers are directly comparable to what a user typed into
      that wizard's Radial/Along-track/Cross-track fields. Real user
      feedback: a single scalar "separation" number wasn't interpretable
      ("vague") -- three real distances in a named, familiar frame is
      the fix. All three share ONE ``storageCapacity`` (2x the
      currently-scheduled along-track target, km -- NOT the raw target
      itself; see UpdateState's own comment: a target-sized max leaves a
      normal, on-target transverse reading pegged at ~100% fill with no
      room for an ordinary correction transient, which is what a real
      Vizard screenshot caught overflowing the panel). ``storageLevel``
      is ``abs(...)`` CLAMPED to ``[0, storageCapacity]`` (see
      :func:`_clamp_magnitude`'s own docstring for why NOT signed --
      GenericStorage is a non-negative gauge widget, and a real user
      screenshot showed a signed, negative ``storageLevel`` rendering as
      "Unavailable" rather than a bar). Live Vizard panels therefore show
      MAGNITUDE only, not "ahead of"/"behind the chief" direction; the
      true, signed numbers are ``self.lastRadialKm``/
      ``self.lastTransverseKm``/``self.lastNormalKm``/
      ``self.lastTargetSeparationKm`` (plain Python attributes, for
      anything that needs the exact signed geometry -- nothing in this
      codebase currently reads them, same as before this round's fix;
      not fed into the exported CSV/results plots either, see this
      module's own "None of this feeds back into simulated physics..."
      note in ``engine.vizard``).
    * ``chiefName`` -- the chief spacecraft's own ``ModelTag`` (a plain
      ``str`` attribute, not a message), wired by :func:`build_phasing_keeping`
      so ``engine.vizard`` can label each panel with WHICH chief the
      number is measured against (e.g. ``"R vs chief-1"``) -- real user
      feedback that "Radial (R)"/etc. alone didn't say whose offset it
      was. Defaults to ``""`` (falls back to a generic "vs chief" label)
      when constructed directly, e.g. in a unit test, rather than via
      :func:`build_phasing_keeping`.
    """

    IDLE, BURN_OUT, DRIFT, BURN_RESTORE = range(4)

    def __init__(
        self,
        name: str,
        mu: float,
        nominal_a_m: float,
        separation_schedule: SeparationSchedule,
        tolerance_fraction: float,
        restore_tolerance_fraction: float,
        correction_window_days: float,
        max_drift_days: float,
        max_delta_a_m: float,
        thrust_n: float,
        isp_s: float,
        dry_mass_kg: float,
        dv_budget_mps: float = 0.0,
        eclipse_sunlit_threshold: float = 0.99,
        g0_mps2: float = 9.80665,
    ):
        super().__init__()
        self.ModelTag = name

        self.scStateInMsgA = messaging.SCStatesMsgReader()  # chief
        self.scStateInMsgB = messaging.SCStatesMsgReader()  # follower (maneuvered)
        self.eclipseInMsgB = messaging.EclipseMsgReader()
        self.deltaVOutMsg = messaging.DataStorageStatusMsg()
        self.separationRadialOutMsg = messaging.DataStorageStatusMsg()
        self.separationTransverseOutMsg = messaging.DataStorageStatusMsg()
        self.separationNormalOutMsg = messaging.DataStorageStatusMsg()

        # Wired up externally (see build_phasing_keeping): the follower's
        # extForceTorque effector and hub, and the co-located
        # StationKeepingController this shares a thruster/tank with (also
        # used for thruster-arbitration -- see UpdateState).
        self.extForceEffectorB = None
        self.scObjectB = None
        self.altitudeControllerB = None
        # The chief spacecraft's own ModelTag -- plain str, not a message
        # -- so engine.vizard can label the RTN panels with WHOSE offset
        # they show (see this class's own docstring). "" (the default
        # for a controller built directly, e.g. in a unit test, rather
        # than via build_phasing_keeping) falls back to a generic label.
        self.chiefName = ""

        self.mu = mu  # [m^3/s^2]
        self.aNom = nominal_a_m  # [m]
        self.separationSchedule = separation_schedule
        self.toleranceFraction = tolerance_fraction  # [-] of the current target separation
        self.restoreToleranceFraction = restore_tolerance_fraction  # [-] of the active maneuver's target
        # Snapshot of the target this controller is actively maneuvering
        # toward, taken once at IDLE -> BURN_OUT and held fixed through
        # BURN_OUT/DRIFT/BURN_RESTORE even if the schedule ticks over to a
        # new target mid-maneuver.
        self._activeTargetRad = 0.0
        self.correctionWindowS = correction_window_days * 86400.0  # [s]
        self.maxDriftS = max_drift_days * 86400.0  # [s]
        self.maxDeltaA = max_delta_a_m  # [m]
        self.thrustN = thrust_n  # [N]
        self.ispS = isp_s  # [s]
        self.g0 = g0_mps2  # [m/s^2]
        self.dryMass = dry_mass_kg  # [kg]
        self.dvBudgetMps = dv_budget_mps  # [m/s] see this class's docstring
        # Fallback propellant tracker, used only if altitudeControllerB is
        # never set -- see _propellant_tracker(). SpaceMissionStudio always
        # sets it (PhasingKeepingConfig requires station_keeping), so this
        # is defensive, not the normal path.
        self.propellant = 0.0  # [kg]
        self.sunlitThreshold = eclipse_sunlit_threshold  # [-]
        # Unclamped RTN separation telemetry -- see UpdateState's own
        # comment on why these (not the separation*OutMsg messages' own,
        # possibly-clamped storageLevel) are the true numbers. Zero here
        # only as a before-the-first-tick default.
        self.lastRadialKm = 0.0  # [km]
        self.lastTransverseKm = 0.0  # [km]
        self.lastNormalKm = 0.0  # [km]
        self.lastTargetSeparationKm = 0.0  # [km]

        semi_major_axis_m = nominal_a_m  # already the chief/follower shared SMA
        self.smoothingWindowS = float(2.0 * np.pi * np.sqrt(semi_major_axis_m ** 3 / mu))  # [s] orbit period
        self._errorHistory: list = []  # list of (t [s], rawError [rad])

        self.state = self.IDLE
        self._lastT: Optional[float] = None  # [s]
        self._targetDv = 0.0  # [m/s]
        self._accumDv = 0.0  # [m/s]
        self._burnSign = 1.0  # [-] direction of the CURRENT burn: +1 prograde (raise a), -1 retrograde
        self._pendingLegDv = 0.0  # [m/s] signed second leg of a two-firing trim (0 = none), see _start_burn
        self._driftSign = 1.0  # [-] sign of the planned drift offset (= sign of the error being corrected)
        self._driftStartT = 0.0  # [s]
        # Closed-loop relative semi-major axis (see UpdateState): one-orbit
        # boxcar of (a_follower - a_chief), the planned offset the current
        # cycle wants, and when the last thrust (ours or station-keeping's)
        # ended, so a measurement is only trusted once a full window of
        # unthrusted samples has accumulated.
        self._relAHistory: list = []  # list of (t [s], aB - aA [m])
        self._relAStartT: Optional[float] = None  # [s]
        self._quietSinceT: Optional[float] = None  # [s]
        self._plannedDeltaA = 0.0  # [m]
        self._trimOnly = False  # current BURN_RESTORE is a disturbance trim, not a phasing cycle's restore
        # Firing model of the shared physical thruster -- replaced by the
        # co-located StationKeepingController's own instance in
        # build_phasing_keeping (one thruster, one firing state).
        self.thruster = ThrusterOnTimeModel()
        self.lastRelativeSmaM = 0.0  # [m] latest one-orbit-mean relative SMA (telemetry)
        self._lastInSun: Optional[bool] = None  # for _log_sunlit_transition
        # Divergence guard -- see UpdateState's own comment at the
        # BURN_RESTORE -> IDLE transition.
        self._errorAtCycleStartRad = 0.0  # [rad] error when the ACTIVE cycle started
        self._consecutiveNonConvergentCycles = 0  # [-]
        self._lastScheduledTargetRad = 0.0  # [rad] detects the schedule ticking over to a new target
        # Public (not underscore-prefixed): real, user-visible telemetry --
        # True once automatic corrections have been suspended because they
        # were not converging (see UpdateState's own comment). Not fed
        # into any live Vizard panel yet (a reasonable follow-on, not done
        # here -- this attribute exists so it's at least inspectable/
        # testable and logged, matching this project's own "surface it,
        # don't silently drop it" discipline elsewhere).
        self.suspendedDueToNonConvergence = False

        self.tLog: list = []
        self.errorDegLog: list = []
        self.stateLog: list = []
        self.propellantLog: list = []
        self.deltaVLog: list = []
        self.relativeSmaLog: list = []  # [m] one-orbit-mean a_follower - a_chief
        self._cumulativeDv = 0.0  # [m/s]

    def Reset(self, CurrentSimNanos):
        self.state = self.IDLE
        self._lastT = CurrentSimNanos * macros.NANO2SEC
        self._accumDv = 0.0
        # Mirrors StationKeepingController.Reset()'s own self._altHistory
        # clear -- this smoothing window is per-tick algorithmic state, not
        # cumulative telemetry (unlike tLog/errorDegLog/... below, which
        # intentionally keep accumulating across a Reset() the same way
        # every other controller's logs do), so a second Reset() on this
        # same instance (Basilisk permits calling it more than once, even
        # though every current caller in this codebase only ever does so
        # once) must not let stale pre-reset error samples leak into the
        # smoothed error average computed just after it.
        self._errorHistory = []
        # Same reasoning as _errorHistory just above: algorithmic state for
        # the divergence guard, not cumulative telemetry, so a second
        # Reset() must not carry over a suspension (or its non-convergence
        # count) decided before this reset.
        self._errorAtCycleStartRad = 0.0
        self._consecutiveNonConvergentCycles = 0
        self._lastScheduledTargetRad = 0.0
        self.suspendedDueToNonConvergence = False
        self._relAHistory = []
        self._relAStartT = None
        self._quietSinceT = None
        self._plannedDeltaA = 0.0
        self._trimOnly = False
        self._pendingLegDv = 0.0
        if self.extForceEffectorB is not None:
            self.extForceEffectorB.extForce_N = [0.0, 0.0, 0.0]

    def _burn_complete(self) -> bool:
        # Relative slack: partial-tick thrust (see UpdateState) lands the
        # accumulated delta-V on the target itself, give or take rounding.
        if self._accumDv < self._targetDv * (1.0 - 1e-9):
            return False
        if self._pendingLegDv != 0.0:
            # First leg of a two-firing trim done: fly the second.
            self._targetDv = abs(self._pendingLegDv)
            self._burnSign = float(np.sign(self._pendingLegDv))
            self._pendingLegDv = 0.0
            self._accumDv = 0.0
            return False
        return True

    def _start_burn(self, deltaA_needed_m: float) -> None:
        """Arms a tangential burn that changes this follower's semi-major
        axis by ``deltaA_needed_m`` (linearized: deltaA/a = 2*dv/v)."""
        vCirc = np.sqrt(self.mu / self.aNom)  # [m/s]
        dv = deltaA_needed_m / self.aNom * vCirc / 2.0  # [m/s]
        self._pendingLegDv = 0.0
        bitDv = self._impulse_bit_delta_a_m() / self.aNom * vCirc / 2.0  # [m/s]
        if 0.0 < abs(dv) < bitDv * (1.0 - 1e-6):
            # Finer than one minimum firing: fly (one bit + dv) then one bit
            # back, which nets exactly dv. Rounding to whole bits instead
            # left up to half a bit (~130 m of semi-major axis for a 300 s
            # firing of 0.05 N), which drifts the formation ~18 km/day, so a
            # coarse thruster cycled a full correction every day.
            self._pendingLegDv = -float(np.copysign(bitDv, dv))
            dv = float(np.copysign(bitDv + abs(dv), dv))
        self._targetDv = abs(dv)
        self._burnSign = 1.0 if dv >= 0.0 else -1.0
        self._accumDv = 0.0
        self.thruster.reset()

    def _impulse_bit_delta_a_m(self) -> float:
        """Semi-major-axis change [m] of one minimum thruster firing (0 for
        an ideal thruster) -- the finest correction the hardware can make."""
        mass = self.dryMass + self._propellant_tracker().propellant  # [kg]
        vCirc = np.sqrt(self.mu / self.aNom)  # [m/s]
        return 2.0 * self.aNom * self.thruster.minimum_impulse_dv(self.thrustN, mass) / vCirc

    @staticmethod
    def _argument_of_latitude(rVec, vVec):
        """True argument of latitude ``u = omega + f`` [rad], in
        (-pi, pi] -- the in-plane angle from the ascending node to the
        spacecraft's actual current position. See this class's own
        docstring ("Numerical conditioning of the phase error") for why
        this replaces an earlier osculating-mean-anomaly-based error
        metric: ``u`` is computed DIRECTLY from the instantaneous
        position/velocity via the orbit-normal/ascending-node geometry
        (same inertial +Z-pole convention ``orbitalMotion.rv2elem``
        itself uses internally) -- never decomposing eccentricity,
        argument of periapsis, or true anomaly individually, which keeps
        it numerically well-behaved all the way through ``e -> 0``
        (classical elements are not: "where periapsis is" becomes
        meaningless once the osculating eccentricity vector's direction
        is undefined).

        Undefined, in the same well-known way classical RAAN is, only
        for an exactly equatorial orbit (``i == 0``, orbit normal along
        +/-Z, so the ascending node itself is undefined) -- falls back
        to the inertial +X axis as an arbitrary but FIXED reference in
        that case. This loses no accuracy for THIS controller's own use
        (only the difference ``uB - uA`` is ever used below, and both
        spacecraft share the same orbit-normal sign whenever they share
        the same orbital plane, as every caller of this class assumes --
        see ``PhasingKeepingConfig``'s own docstring), it just picks a
        consistent zero-point instead of an undefined one.
        """
        rHat = rVec / np.linalg.norm(rVec)
        hVec = np.cross(rVec, vVec)
        hHat = hVec / np.linalg.norm(hVec)
        nVec = np.cross(np.array([0.0, 0.0, 1.0]), hHat)
        nNorm = np.linalg.norm(nVec)
        nHat = nVec / nNorm if nNorm > 1e-9 else np.array([1.0, 0.0, 0.0])
        cosU = np.dot(rHat, nHat)
        sinU = np.dot(rHat, np.cross(hHat, nHat))
        return float(np.arctan2(sinU, cosU))

    @staticmethod
    def _circular_mean(angles_rad):
        # Mean of a circular (wrapped) quantity via the resultant vector,
        # correct near the +/-pi wrap boundary -- a plain arithmetic mean
        # is not (e.g. averaging +179 deg and -179 deg should give +/-180
        # deg, not 0).
        return float(np.arctan2(np.mean(np.sin(angles_rad)), np.mean(np.cos(angles_rad))))

    def UpdateState(self, CurrentSimNanos):
        t = CurrentSimNanos * macros.NANO2SEC  # [s]
        dt = t - self._lastT if self._lastT is not None else 0.0  # [s]
        self._lastT = t

        stateA = self.scStateInMsgA()
        stateB = self.scStateInMsgB()
        rA, vA = np.array(stateA.r_BN_N), np.array(stateA.v_BN_N)
        rB, vB = np.array(stateB.r_BN_N), np.array(stateB.v_BN_N)

        # Same reasoning as StationKeepingController.UpdateState()'s own
        # matching guard: a non-finite state (from either spacecraft) must
        # never propagate into a commanded force -- command no thrust and
        # hold state this tick instead. Also guards vA/vB against being
        # exactly zero -- a real gap found by audit: this method reads
        # vB's norm to compute a burn direction further down
        # (`vHatB = vB / np.linalg.norm(vB)`), and _argument_of_latitude()
        # below divides by norm(cross(r, v)) (the orbit-normal magnitude --
        # zero whenever r/v happen to be parallel, e.g. a purely radial
        # trajectory, not just when either is individually zero; same
        # degenerate case ConstantFrameThrustController's own matching
        # guard already checks for) -- either was previously only checked
        # for NaN/inf, not for exactly zero, unlike this class's own
        # StationKeepingController sibling.
        if not (np.all(np.isfinite(rA)) and np.all(np.isfinite(vA)) and np.linalg.norm(vA) > 0.0
                and np.all(np.isfinite(rB)) and np.all(np.isfinite(vB)) and np.linalg.norm(vB) > 0.0
                and np.linalg.norm(np.cross(rA, vA)) > 0.0 and np.linalg.norm(np.cross(rB, vB)) > 0.0):
            if self.extForceEffectorB is not None:
                self.extForceEffectorB.extForce_N = [0.0, 0.0, 0.0]
            self.tLog.append(t)
            self.errorDegLog.append(float("nan"))
            self.stateLog.append(self.state)
            self.propellantLog.append(self._propellant_tracker().propellant)
            self.deltaVLog.append(self._cumulativeDv)
            self.relativeSmaLog.append(float("nan"))
            return

        mA = self._argument_of_latitude(rA, vA)
        mB = self._argument_of_latitude(rB, vB)

        # Relative semi-major axis, closed loop. Real bug behind this (see
        # StationKeepingController's "Formation-follower mode" docstring):
        # this controller used to size every burn open-loop and "restore"
        # by replaying its own delta-V backwards, so it could never notice,
        # let alone remove, a semi-major-axis mismatch something ELSE made
        # (a lone station-keeping reboost left a real user's follower 5 km
        # high, drifting ~6 deg/day for 90 days). The instantaneous
        # osculating difference swings +/-135 m under J2, but its one-orbit
        # mean is steady to ~0.1 m (measured on the formation template), so
        # every burn is now sized from that measured value.
        aA = 1.0 / (2.0 / np.linalg.norm(rA) - np.dot(vA, vA) / self.mu)  # [m]
        aB = 1.0 / (2.0 / np.linalg.norm(rB) - np.dot(vB, vB) / self.mu)  # [m]
        if self._relAStartT is None:
            self._relAStartT = t
        if self._quietSinceT is None:
            self._quietSinceT = t
        self._relAHistory.append((t, aB - aA))
        while self._relAHistory and (t - self._relAHistory[0][0]) > self.smoothingWindowS:
            self._relAHistory.pop(0)
        relA = float(np.mean([d for _, d in self._relAHistory]))  # [m]
        self.lastRelativeSmaM = relA
        # Trusted only once a full orbit of samples taken WITHOUT any thrust
        # on this follower has accumulated (a burn shifts the true value
        # mid-window, and the boxcar would otherwise lag it by half an orbit).
        relASettled = (t - max(self._relAStartT, self._quietSinceT)) >= self.smoothingWindowS

        scheduledTargetRad = self.separationSchedule.value_at(t)
        referenceTargetRad = scheduledTargetRad if self.state == self.IDLE else self._activeTargetRad

        # error > 0 means B's phase leads the target separation (B is "too
        # far ahead" of A); error < 0 means B trails. Smoothed over one
        # orbital period to reject J2 short-period noise (real, physical
        # short-period oscillation of the argument of latitude itself --
        # NOT the numerical-conditioning artifact _argument_of_latitude
        # was specifically chosen to avoid; see this class's own
        # docstring).
        rawError = _wrap_pm_pi((mB - mA) - referenceTargetRad)  # [rad]
        self._errorHistory.append((t, rawError))
        while self._errorHistory and (t - self._errorHistory[0][0]) > self.smoothingWindowS:
            self._errorHistory.pop(0)
        error = self._circular_mean(np.array([e for _, e in self._errorHistory]))  # [rad]

        # Live RTN separation-from-chief telemetry, for Vizard's
        # GenericStorage "Radial"/"Transverse"/"Normal" panels -- see this
        # class's own docstring. The REAL geometric offset in the chief's
        # own Hill (RTN) frame, via ``orbitalMotion.rv2hill`` -- the exact
        # same function (and axis convention) ``engine.formation``'s
        # wizard itself uses to PLACE a follower, so these numbers are
        # directly comparable to what a user typed into that wizard's R/T/N
        # fields. Deliberately NOT derived from mB - mA (the control law's
        # own argument-of-latitude-difference approximation, still what
        # actually drives burns below, unchanged) -- real user feedback: a
        # single, abstract "separation" scalar wasn't interpretable ("vague");
        # three real distances in a named, familiar frame are.
        rhoH, _rhoPrimeH = orbitalMotion.rv2hill(rA, vA, rB, vB)
        radialKm = float(rhoH[0]) / 1000.0  # [km]
        transverseKm = float(rhoH[1]) / 1000.0  # [km]
        normalKm = float(rhoH[2]) / 1000.0  # [km]
        targetKm = abs(scheduledTargetRad) * self.aNom / 1000.0  # [km]
        self.lastRadialKm = radialKm
        self.lastTransverseKm = transverseKm
        self.lastNormalKm = normalKm
        self.lastTargetSeparationKm = targetKm

        # Real bug found against a real running Vizard instance (screenshot
        # from an actual user): a GenericStorage bar with storageLevel
        # outside [-storageCapacity, storageCapacity] renders broken
        # (overflowing its own panel, full window width) rather than
        # clamping itself -- and storageCapacity == targetKm means NORMAL,
        # on-target transverse holding already sits at ~100% fill (the
        # opposite of the usual "full bar == bad" gauge convention),
        # leaving no headroom before an ordinary correction transient (a
        # fresh phasing error, right after a reconfiguration) pushes
        # storageLevel past it. All three R/T/N panels share ONE capacity
        # (2x the along-track target -- generous headroom for the
        # actively-held T axis, and a common scale so the three bars'
        # relative fill is directly comparable).
        capacityKm = 2.0 * targetKm  # [km]

        # A SECOND real bug found against a real running Vizard instance,
        # a later screenshot: storageLevel was clamped SYMMETRICALLY at
        # this point (preserving sign, so "ahead of"/"behind the chief"
        # would still read correctly) -- but the Radial/Normal panels,
        # negative at that moment, rendered "Unavailable" instead of a
        # bar, while Transverse (positive at that moment) rendered fine.
        # GenericStorage's own field comments document currentValue/
        # maxValue as a non-negative gauge ("absolute value of the
        # storage device") -- see _clamp_magnitude's own docstring for
        # the full reasoning. Fixed by publishing magnitude, not signed
        # value; the true signed numbers stay available as this
        # instance's own lastRadialKm/lastTransverseKm/lastNormalKm.
        radialMsg = messaging.DataStorageStatusMsgPayload()
        radialMsg.storageCapacity = capacityKm
        radialMsg.storageLevel = _clamp_magnitude(radialKm, capacityKm)
        self.separationRadialOutMsg.write(radialMsg, CurrentSimNanos, self.moduleID)

        transverseMsg = messaging.DataStorageStatusMsgPayload()
        transverseMsg.storageCapacity = capacityKm
        transverseMsg.storageLevel = _clamp_magnitude(transverseKm, capacityKm)
        self.separationTransverseOutMsg.write(transverseMsg, CurrentSimNanos, self.moduleID)

        normalMsg = messaging.DataStorageStatusMsgPayload()
        normalMsg.storageCapacity = capacityKm
        normalMsg.storageLevel = _clamp_magnitude(normalKm, capacityKm)
        self.separationNormalOutMsg.write(normalMsg, CurrentSimNanos, self.moduleID)

        # Also written here (not only in the final block below, which the
        # thrusterHeldByAltCtrl arbitration branch just below returns
        # before reaching): dvBudgetMps (the gauge's fixed "max") should
        # read correctly from the very first tick, even on a spacecraft
        # whose co-located StationKeepingController happens to hold the
        # shared thruster for a long stretch -- the final block's write
        # still runs (with a fresher storageLevel) on every tick that
        # reaches it, so this one is only ever stale, never wrong.
        deltaVMsg = messaging.DataStorageStatusMsgPayload()
        deltaVMsg.storageLevel = self._cumulativeDv  # [m/s]
        deltaVMsg.storageCapacity = self.dvBudgetMps  # [m/s]
        self.deltaVOutMsg.write(deltaVMsg, CurrentSimNanos, self.moduleID)

        inSun = True
        if self.eclipseInMsgB.isLinked():
            # See _eclipse_illumination_fraction's own docstring: an
            # earlier crash investigation initially pinned a real crash on
            # EclipseMsgPayload.shadowFactor being deprecated in favor of
            # illuminationFactor -- wrong, since a real user's installed
            # Basilisk build turned out not to have illuminationFactor AT
            # ALL. That crash's actual root cause was later found
            # (engine.vizard.enable_vizard()'s GenericStorage/GenericSensor
            # dangling-pointer bug -- see that module's docstring); eclipse
            # was never involved. This call site remains tolerant of both
            # Basilisk API generations regardless.
            illumB = _eclipse_illumination_fraction(self.eclipseInMsgB())
            inSun = illumB > self.sunlitThreshold
            self._lastInSun = _log_sunlit_transition(self.ModelTag, t, illumB, inSun, self._lastInSun)

        # Thruster arbitration: altitude keeping owns the effector whenever
        # it is actively burning. Log telemetry and return without
        # touching the effector or advancing the state machine's clocks.
        thrusterHeldByAltCtrl = self.altitudeControllerB is not None and (
            self.altitudeControllerB.burnOn or self.thruster.firing_owned_by(self.altitudeControllerB))
        if thrusterHeldByAltCtrl:
            self._quietSinceT = t  # station-keeping is changing this orbit -- re-measure afterwards
            self.tLog.append(t)
            self.errorDegLog.append(np.degrees(error))
            self.stateLog.append(self.state)
            self.propellantLog.append(self._propellant_tracker().propellant)
            self.deltaVLog.append(self._cumulativeDv)
            self.relativeSmaLog.append(relA)
            return

        thrustMag = 0.0  # [N]

        # Divergence guard: a fresh schedule target (the schedule ticking
        # over to a new entry) is a genuinely new situation worth trying
        # again, even after a previous target was given up on below. Gated
        # to self.state == self.IDLE (real audit finding): this used to run
        # unconditionally every tick, so a schedule entry ticking over
        # mid-maneuver (BURN_OUT/DRIFT/BURN_RESTORE) wiped
        # suspendedDueToNonConvergence/_consecutiveNonConvergentCycles
        # before the in-progress cycle was ever judged against the OLD
        # target below (the BURN_RESTORE -> IDLE transition), handing a
        # genuinely diverging correction a free reset of its non-
        # convergence count for a coincidence of timing rather than an
        # actual improvement. IDLE is the only state that reads
        # suspendedDueToNonConvergence (just below) to decide whether to
        # start a new correction, so deferring the reset until the
        # controller is actually back in IDLE -- at which point it compares
        # against whatever the schedule's CURRENT value is, not a stale
        # mid-cycle snapshot -- loses no information, just the premature
        # reset.
        if self.state == self.IDLE and scheduledTargetRad != self._lastScheduledTargetRad:
            self.suspendedDueToNonConvergence = False
            self._consecutiveNonConvergentCycles = 0
            self._lastScheduledTargetRad = scheduledTargetRad

        if self.state == self.IDLE:
            # Tolerance scales with the CURRENT target, not a fixed angle.
            tolRad = self.toleranceFraction * abs(scheduledTargetRad)
            if abs(error) > tolRad and not self.suspendedDueToNonConvergence:
                self._activeTargetRad = scheduledTargetRad
                self._errorAtCycleStartRad = error
                n = np.sqrt(self.mu / self.aNom ** 3)  # [rad/s] mean motion
                # error is an argument-of-latitude difference (see this
                # class's own docstring), whose drift rate equals the
                # two-body mean motion n to within O(e) for the
                # near-circular orbits this controller targets -- so the
                # same two-body mean-motion-offset-from-an-SMA-offset
                # relation below still applies directly:
                #   dn = -1.5 * n * (deltaA / a)
                # Solve deltaA so the accumulated drift over the correction
                # window exactly cancels the current error:
                #   error + dn * T = 0  =>  deltaA = error * a / (1.5 * n * T)
                deltaA = error * self.aNom / (1.5 * n * self.correctionWindowS)  # [m]
                # A correction finer than the thruster's minimum impulse bit
                # can't be flown: plan at least one bit (a slightly faster
                # correction) rather than a burn that would be skipped.
                bitA = self._impulse_bit_delta_a_m()
                if 0.0 < abs(deltaA) < bitA:
                    deltaA = float(np.copysign(bitA, deltaA))
                deltaA = float(np.clip(deltaA, -self.maxDeltaA, self.maxDeltaA))
                self._plannedDeltaA = deltaA
                self._driftSign = 1.0 if deltaA >= 0.0 else -1.0
                # The max-drift clock starts once per correction (not again
                # after a mid-drift re-steer -- see DRIFT below).
                self._driftStartT = t
                # Burn from where the relative SMA actually IS (when that's
                # known), not from an assumed zero.
                self._start_burn(deltaA - (relA if relASettled else 0.0))
                self._trimOnly = False
                self.state = self.BURN_OUT
            elif relASettled and abs(relA) > _RELATIVE_SMA_TRIM_TOLERANCE_M:
                # Not a phasing correction: something else (e.g. a reboost
                # only one spacecraft made) left the two orbits at different
                # semi-major axes, which would otherwise drift the formation
                # apart unchecked. Trim it out -- allowed even while
                # suspended, since this can only REDUCE the drift.
                self._plannedDeltaA = 0.0
                self._start_burn(-relA)
                self._trimOnly = True
                self.state = self.BURN_RESTORE

        elif self.state == self.BURN_OUT:
            thrustMag = self.thrustN if inSun else 0.0
            if self._burn_complete():
                self._accumDv = 0.0
                self.state = self.DRIFT
                thrustMag = 0.0

        elif self.state == self.DRIFT:
            restoreTolRad = self.restoreToleranceFraction * abs(self._activeTargetRad)
            # "Overshot" = the error crossed ZERO. Real bug: this used to be
            # a bare sign comparison, so an error wrapping through +/-180 deg
            # (the follower having drifted half an orbit away) also counted
            # as "target reached", triggering a restore burn at the worst
            # possible moment (seen at day 28 of a real user's run).
            overshot = _crossed_zero(error, self._driftSign)
            if abs(error) < restoreTolRad or overshot or (t - self._driftStartT) > self.maxDriftS:
                # Null the MEASURED relative SMA, not just this cycle's own
                # delta-V, so the drift really stops.
                self._start_burn(-(relA if relASettled else self._plannedDeltaA))
                self._plannedDeltaA = 0.0
                self._trimOnly = False
                self.state = self.BURN_RESTORE
            elif relASettled and abs(relA - self._plannedDeltaA) > max(
                    _RELATIVE_SMA_TRIM_TOLERANCE_M, 0.5 * abs(self._plannedDeltaA)):
                # Disturbed mid-drift (e.g. a station-keeping burn): steer back
                # to the planned offset, keeping this cycle's target/clock.
                self._start_burn(self._plannedDeltaA - relA)
                self.state = self.BURN_OUT

        elif self.state == self.BURN_RESTORE:
            thrustMag = self.thrustN if inSun else 0.0
            if self._burn_complete() and self._trimOnly:
                # A disturbance trim, not the end of a phasing cycle -- the
                # divergence guard below judges phasing cycles only.
                self.state = self.IDLE
                self._trimOnly = False
                thrustMag = 0.0
            elif self._burn_complete():
                self.state = self.IDLE
                thrustMag = 0.0
                # Real numerical confirmation (not just reasoned about, see
                # this class's own docstring): a severely mis-conditioned
                # starting geometry -- notably ANY nonzero radial placement
                # offset, see engine.formation's own docstring -- can push
                # the follower's real orbit far enough from the
                # near-circular assumption this controller's linearized
                # deltaA model relies on that a "correction" leaves the
                # REAL separation no better than before, and the error
                # metric itself oscillates between two phase-locked values
                # on alternating cycles (observed numerically: -36 deg ->
                # +162 deg -> -36 deg -> ...) rather than monotonically
                # growing -- so comparing a cycle's ending error against its
                # OWN starting error is fooled by that oscillation (it looks
                # "better" every other cycle and never accumulates). Instead
                # each full correction cycle is judged against the SAME
                # tolerance band IDLE itself uses to decide a correction is
                # even needed: if the error is still outside that band after
                # a full correction, the cycle didn't actually fix anything.
                # Exhausting a small budget of such cycles suspends further
                # automatic corrections entirely, rather than burning
                # propellant into an unbounded, non-converging spiral with
                # no other natural stopping point. A fresh schedule target
                # (see above) gives this a clean new attempt.
                activeTolRad = self.toleranceFraction * abs(self._activeTargetRad)
                if abs(error) > activeTolRad:
                    self._consecutiveNonConvergentCycles += 1
                else:
                    self._consecutiveNonConvergentCycles = 0
                if (self._consecutiveNonConvergentCycles >= _MAX_NON_CONVERGENT_CYCLES
                        and not self.suspendedDueToNonConvergence):
                    self.suspendedDueToNonConvergence = True
                    _LOGGER.warning(
                        "%s: phasing correction did not reduce its own tracking error over %d "
                        "consecutive cycles (%.3f deg -> %.3f deg) -- suspending further automatic "
                        "corrections rather than keep burning propellant into a non-converging "
                        "spiral. This usually means the follower's real orbit has drifted too far "
                        "from the near-circular assumption this controller's own model relies on "
                        "(e.g. from a large initial radial/cross-track placement offset) -- see "
                        "PhasingKeepingController's own docstring.",
                        self.ModelTag, self._consecutiveNonConvergentCycles,
                        np.degrees(self._errorAtCycleStartRad), np.degrees(error),
                    )

        tracker = self._propellant_tracker()
        # Achieved acceleration/delta-v needs the spacecraft's TRUE total
        # mass (scMassOutMsg.massSC, Basilisk's own hub+state-effector
        # aggregate), not just hub.mHub -- see
        # StationKeepingController.UpdateState's identical comment for why
        # (a coexisting fuel_tank state effector's mass would otherwise be
        # silently missed, ending a burn early).
        trueTotalMass = (
            self.scObjectB.scMassOutMsg.read().massSC if self.scObjectB is not None
            else (self.dryMass + tracker.propellant)
        )

        if self.state in (self.BURN_OUT, self.BURN_RESTORE):
            # Partial-tick thrust via the shared thruster's on-time model:
            # never more than the delta-V this burn still needs, rounded to
            # the thruster's minimum impulse bit, optionally gated for
            # eccentricity neutrality. Real limitation the partial-tick part
            # removed: whole 30 s ticks of the formation template's 0.05 N
            # thruster moved the semi-major axis ~26 m each, while a typical
            # correction needs ~2 m, so every correction overshot ~10x.
            remainingDv = max(self._targetDv - self._accumDv, 0.0)  # [m/s]
            thrustMag, extraDv, tooSmall = self.thruster.command(
                owner=self, want_firing=thrustMag > 0.0 or self.thruster.firing_owned_by(self),
                remaining_dv=remainingDv,
                sign=self._burnSign, thrust_n=self.thrustN, mass_kg=trueTotalMass, dt_s=dt, in_sun=inSun,
                u_rad=mB, v_mps=float(np.linalg.norm(vB)), mean_motion=np.sqrt(self.mu / self.aNom ** 3))
            if extraDv > 0.0:
                self._targetDv += extraDv  # rounded up to one minimum firing: fly all of it
            if tooSmall:
                self._targetDv = self._accumDv  # below half an impulse bit: nothing to fire, burn done

        if thrustMag > 0.0:
            accel = thrustMag / trueTotalMass  # [m/s^2]
            self._accumDv += accel * dt
            self._cumulativeDv += accel * dt

        # The burn bookkeeping write-back stays against hub.mHub
        # specifically, NOT trueTotalMass -- see
        # StationKeepingController.UpdateState's identical comment (would
        # otherwise double-count a coexisting fuel_tank's own mass).
        hubMass = self.scObjectB.hub.mHub if self.scObjectB is not None else (self.dryMass + tracker.propellant)
        newMass, tracker.propellant, _burnedKg, _mDot = apply_propellant_burn(
            hubMass, tracker.propellant, thrustMag, self.ispS, dt, self.g0)
        if self.scObjectB is not None:
            self.scObjectB.hub.mHub = newMass

        forceVec = np.zeros(3)
        if thrustMag > 0.0:
            self._quietSinceT = t
            vHatB = vB / np.linalg.norm(vB)
            forceVec = thrustMag * self._burnSign * vHatB
        if self.extForceEffectorB is not None:
            self.extForceEffectorB.extForce_N = forceVec.tolist()

        deltaVMsg = messaging.DataStorageStatusMsgPayload()
        deltaVMsg.storageLevel = self._cumulativeDv  # [m/s] this controller's OWN phasing delta-V only
        deltaVMsg.storageCapacity = self.dvBudgetMps  # [m/s] shared-tank total (see this class's docstring)
        self.deltaVOutMsg.write(deltaVMsg, CurrentSimNanos, self.moduleID)

        self.tLog.append(t)
        self.errorDegLog.append(np.degrees(error))
        self.stateLog.append(self.state)
        self.propellantLog.append(tracker.propellant)
        self.deltaVLog.append(self._cumulativeDv)
        self.relativeSmaLog.append(relA)

    def _propellant_tracker(self):
        # Satellite B's thruster (and hence its one physical propellant
        # tank) is shared with its own StationKeepingController (see the
        # thruster-arbitration check above); track mass through that same
        # object rather than keeping an independent second belief about
        # how much propellant is left. Falls back to this controller's own
        # (never independently depleted) tracker only if none was wired up.
        return self.altitudeControllerB if self.altitudeControllerB is not None else self


def build_phasing_keeping(scSim, task_name: str, tag: str, mu: float, chief_sc_object, follower_sc_object,
                           follower_station_keeping_controller: StationKeepingController,
                           follower_eclipse_out_msg, chief_semi_major_axis_km: float,
                           config: PhasingKeepingConfig,
                           chief_station_keeping_controller: Optional[StationKeepingController] = None,
                           ) -> PhasingKeepingController:
    """Builds and wires one follower spacecraft's :class:`PhasingKeepingController`.

    Also switches ``follower_station_keeping_controller`` into formation
    -follower mode, following ``chief_station_keeping_controller`` (``None``
    if the chief has no station-keeping) -- see
    :class:`StationKeepingController`'s "Formation-follower mode" docstring.

    Shares ``follower_station_keeping_controller``'s ``extForceEffector``
    (no second effector is created -- see ``PhasingKeepingConfig``'s
    docstring on why phasing and altitude-keeping share one physical
    thruster) and reads ``thrust_n``/``isp_s``/``dry_mass_kg``/
    ``eclipse_sunlit_threshold`` off it rather than off ``config``, which
    has no such fields of its own.
    """
    nominal_a_m = chief_semi_major_axis_km * 1000.0
    schedule = SeparationSchedule(
        distances_km=config.target_separation_km,
        interval_days=config.reconfiguration_interval_days,
        semi_major_axis_m=nominal_a_m,
    )
    controller = PhasingKeepingController(
        name=f"{tag}PhasingKeeping",
        mu=mu,
        nominal_a_m=nominal_a_m,
        separation_schedule=schedule,
        tolerance_fraction=config.tolerance_fraction,
        restore_tolerance_fraction=config.restore_tolerance_fraction,
        correction_window_days=config.correction_window_days,
        max_drift_days=config.max_drift_days,
        max_delta_a_m=config.max_delta_semi_major_axis_km * 1000.0,
        thrust_n=follower_station_keeping_controller.thrustN,
        isp_s=follower_station_keeping_controller.ispS,
        dry_mass_kg=follower_station_keeping_controller.dryMass,
        dv_budget_mps=follower_station_keeping_controller.dvBudgetMps,
        eclipse_sunlit_threshold=follower_station_keeping_controller.sunlitThreshold,
    )

    controller.scStateInMsgA.subscribeTo(chief_sc_object.scStateOutMsg)
    controller.scStateInMsgB.subscribeTo(follower_sc_object.scStateOutMsg)
    if follower_eclipse_out_msg is not None:
        controller.eclipseInMsgB.subscribeTo(follower_eclipse_out_msg)
    controller.extForceEffectorB = follower_station_keeping_controller.extForceEffector
    controller.scObjectB = follower_sc_object
    controller.chiefName = chief_sc_object.ModelTag
    # Thruster-arbitration link: phasing pauses while the follower's own
    # altitude controller is actively reboosting (see UpdateState).
    controller.altitudeControllerB = follower_station_keeping_controller
    controller.thruster = follower_station_keeping_controller.thruster  # one physical thruster
    follower_station_keeping_controller.formationFollower = True
    follower_station_keeping_controller.formationReference = chief_station_keeping_controller
    scSim.AddModelToTask(task_name, controller)
    return controller


def _vnb_basis(r_vec: np.ndarray, v_vec: np.ndarray):
    """(V, N, B) unit vectors of the velocity-normal-binormal frame at this
    instant: V = velocity direction, N = orbit-normal (angular-momentum
    direction, r x v), B = V x N (completes the right-handed triad).
    Re-evaluated fresh from the spacecraft's CURRENT r/v every call -- this
    is an osculating, instantaneously-rotating frame, not a fixed one.
    """
    v_hat = v_vec / np.linalg.norm(v_vec)
    h_vec = np.cross(r_vec, v_vec)
    n_hat = h_vec / np.linalg.norm(h_vec)
    b_hat = np.cross(v_hat, n_hat)
    return v_hat, n_hat, b_hat


def _rtn_basis(r_vec: np.ndarray, v_vec: np.ndarray):
    """(R, T, N) unit vectors of the radial-transverse-normal frame at this
    instant: R = radial (outward from the central body), N = orbit-normal
    (angular-momentum direction, r x v), T = N x R (completes the
    right-handed triad; in-plane, perpendicular to R -- coincides with the
    velocity direction only at periapsis/apoapsis or for a circular orbit,
    NOT in general, unlike VNB's V). Re-evaluated fresh every call, like
    :func:`_vnb_basis`.
    """
    r_hat = r_vec / np.linalg.norm(r_vec)
    h_vec = np.cross(r_vec, v_vec)
    n_hat = h_vec / np.linalg.norm(h_vec)
    t_hat = np.cross(n_hat, r_hat)
    return r_hat, t_hat, n_hat


class ConstantFrameThrustController(sysModel.SysModel):
    """Continuous (always-on), constant-magnitude thrust with a fixed
    DIRECTION IN A ROTATING FRAME (VNB or RTN -- see
    :class:`schema.scenario.ConstantThrustConfig`'s docstring for why: an
    orbit-only "cannonball" scenario needs a delta-V/propellant budgeting
    tool that doesn't require any attitude modeling, and a thrust
    direction fixed in the INERTIAL frame would drift relative to the
    orbit as the spacecraft moves -- VNB/RTN are the standard
    astrodynamics frames for exactly this, re-evaluated every tick from
    the spacecraft's current state, see :func:`_vnb_basis`/:func:`_rtn_basis`).

    Propellant/delta-V bookkeeping (explicit-Euler rocket equation, mass
    fed back into ``scObject.hub.mHub``) is the same approach
    :class:`StationKeepingController` uses, just with no
    altitude-deadband/eclipse trigger -- this fires every tick until
    propellant is exhausted (then silently stays at zero thrust, same as
    station-keeping's own depletion behavior, just without the repeated
    per-tick warning log -- running out is the expected steady state for
    a continuous-thrust budget scenario, not a surprise).

    Construct via :func:`build_constant_thrust` rather than directly.
    """

    def __init__(self, name: str, frame: str, direction, thrust_n: float, isp_s: float,
                 dry_mass_kg: float, propellant_kg: float, g0_mps2: float = 9.80665):
        super().__init__()
        self.ModelTag = name

        self.scStateInMsg = messaging.SCStatesMsgReader()
        # Live propellant telemetry for Vizard's GenericStorage "fuel tank"
        # panel -- same rationale as StationKeepingController's own
        # fuelTankOutMsg (see that class's docstring).
        self.fuelTankOutMsg = messaging.FuelTankMsg()

        # Wired up externally (see build_constant_thrust): the
        # extForceTorque effector this controller commands, and the
        # spacecraft hub whose mass it updates as propellant depletes.
        self.extForceEffector = None
        self.scObject = None

        self.frame = frame  # "VNB" or "RTN" -- trusted pre-validated (ConstantThrustConfig.validate())
        direction_arr = np.array(direction, dtype=float)
        norm = np.linalg.norm(direction_arr)
        self.direction = direction_arr / norm if norm > 0.0 else direction_arr  # unit vector in `frame`
        self.thrustN = thrust_n  # [N]
        self.ispS = isp_s  # [s]
        self.g0 = g0_mps2  # [m/s^2]
        self.dryMass = dry_mass_kg  # [kg]
        self.propellant = propellant_kg  # [kg]
        self._initialPropellantKg = propellant_kg  # [kg] fixed tank capacity, for fuelTankOutMsg.maxFuelMass

        self._lastT: Optional[float] = None  # [s]
        self.tLog: list = []
        self.propellantLog: list = []
        self.deltaVLog: list = []
        self._cumulativeDv = 0.0  # [m/s]

    def Reset(self, CurrentSimNanos):
        self._lastT = CurrentSimNanos * macros.NANO2SEC
        if self.extForceEffector is not None:
            self.extForceEffector.extForce_N = [0.0, 0.0, 0.0]

    def UpdateState(self, CurrentSimNanos):
        t = CurrentSimNanos * macros.NANO2SEC  # [s]
        dt = t - self._lastT if self._lastT is not None else 0.0  # [s]
        self._lastT = t

        scState = self.scStateInMsg()
        rVec = np.array(scState.r_BN_N)  # [m]
        vVec = np.array(scState.v_BN_N)  # [m/s]

        # Same "never feed a degenerate state into a commanded force"
        # reasoning as StationKeepingController's/PhasingKeepingController's
        # own matching guards -- a real gap found by audit: this class had
        # NO guard at all. _vnb_basis()/_rtn_basis() (called just below)
        # divide by norm(vVec) (both frames), norm(rVec) (RTN only), and
        # norm(cross(rVec, vVec)) (both frames, the orbit-normal magnitude
        # -- zero whenever rVec/vVec happen to be parallel, e.g. a purely
        # radial trajectory, not just when either one is individually
        # zero). Command no thrust and hold state this tick instead.
        if not (np.all(np.isfinite(rVec)) and np.all(np.isfinite(vVec))
                and np.linalg.norm(rVec) > 0.0 and np.linalg.norm(vVec) > 0.0
                and np.linalg.norm(np.cross(rVec, vVec)) > 0.0):
            if self.extForceEffector is not None:
                self.extForceEffector.extForce_N = [0.0, 0.0, 0.0]
            self.tLog.append(t)
            self.propellantLog.append(self.propellant)
            self.deltaVLog.append(self._cumulativeDv)
            return

        axis1, axis2, axis3 = _vnb_basis(rVec, vVec) if self.frame == "VNB" else _rtn_basis(rVec, vVec)
        dirHat_N = self.direction[0] * axis1 + self.direction[1] * axis2 + self.direction[2] * axis3

        thrustMag = self.thrustN if self.propellant > 1e-9 else 0.0  # [N]
        # Achieved acceleration/delta-v needs the spacecraft's TRUE total
        # mass (scMassOutMsg.massSC, Basilisk's own hub+state-effector
        # aggregate), not just hub.mHub -- see
        # StationKeepingController.UpdateState's identical comment for why
        # (a coexisting fuel_tank state effector's mass would otherwise be
        # silently missed, ending a burn early).
        trueTotalMass = (
            self.scObject.scMassOutMsg.read().massSC if self.scObject is not None
            else (self.dryMass + self.propellant)
        )

        if thrustMag > 0.0:
            self._cumulativeDv += (thrustMag / trueTotalMass) * dt  # [m/s]

        # The burn bookkeeping write-back stays against hub.mHub
        # specifically, NOT trueTotalMass -- see
        # StationKeepingController.UpdateState's identical comment (would
        # otherwise double-count a coexisting fuel_tank's own mass).
        hubMass = self.scObject.hub.mHub if self.scObject is not None else (self.dryMass + self.propellant)
        newMass, self.propellant, _burnedKg, mDot = apply_propellant_burn(
            hubMass, self.propellant, thrustMag, self.ispS, dt, self.g0)
        if self.scObject is not None:
            self.scObject.hub.mHub = newMass

        forceVec = thrustMag * dirHat_N
        if self.extForceEffector is not None:
            self.extForceEffector.extForce_N = forceVec.tolist()

        fuelTankMsg = messaging.FuelTankMsgPayload()
        fuelTankMsg.fuelMass = self.propellant  # [kg]
        fuelTankMsg.fuelMassDot = -mDot  # [kg/s] negative: mass decreasing
        fuelTankMsg.maxFuelMass = self._initialPropellantKg  # [kg]
        self.fuelTankOutMsg.write(fuelTankMsg, CurrentSimNanos, self.moduleID)

        self.tLog.append(t)
        self.propellantLog.append(self.propellant)
        self.deltaVLog.append(self._cumulativeDv)


def build_constant_thrust(scSim, task_name: str, tag: str, sc_object, dry_mass_kg: float,
                           config: ConstantThrustConfig) -> ConstantFrameThrustController:
    """Builds and wires one spacecraft's :class:`ConstantFrameThrustController`:
    a DEDICATED ``extForceTorque`` effector -- independent of
    station-keeping's own effector, if also configured on this spacecraft
    (multiple dynamic effectors on one hub sum additively, same pattern
    this module's docstring already notes for attitude-control/
    station-keeping). Adds both to ``task_name``.

    ``dry_mass_kg`` is the spacecraft's mass WITHOUT this controller's own
    propellant, same convention as :func:`build_station_keeping`'s
    ``dry_mass_kg`` argument -- see that function's docstring. If BOTH
    station_keeping and constant_thrust are configured on the same
    spacecraft, the caller is responsible for including both propellant
    masses in the spacecraft's initial simulated mass (they are
    independent propellant budgets/tanks, unlike station_keeping +
    phasing_keeping which deliberately share one) -- see this module's
    "Shared mass bookkeeping" docstring note for how each controller's
    ``UpdateState`` now preserves that initial total correctly tick over
    tick, instead of each one recomputing (and clobbering) its own.
    """
    controller = ConstantFrameThrustController(
        name=f"{tag}ConstantThrust",
        frame=config.frame,
        direction=config.direction,
        thrust_n=config.thrust_n,
        isp_s=config.isp_s,
        dry_mass_kg=dry_mass_kg,
        propellant_kg=config.propellant_kg,
    )

    thruster = extForceTorque.ExtForceTorque()
    thruster.ModelTag = f"{tag}ConstantThrustThruster"
    sc_object.addDynamicEffector(thruster)
    scSim.AddModelToTask(task_name, thruster)

    controller.extForceEffector = thruster
    controller.scObject = sc_object
    controller.scStateInMsg.subscribeTo(sc_object.scStateOutMsg)
    scSim.AddModelToTask(task_name, controller)
    return controller
