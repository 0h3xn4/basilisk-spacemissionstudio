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
Phase 3: Monte Carlo batch execution, wrapping the real, already-native
``Basilisk.utilities.MonteCarlo`` framework (``Controller``,
``Dispersions``, ``RetentionPolicy``) -- this module does not reimplement
any dispersion math or batch-execution logic; it only translates
:class:`schema.scenario.MonteCarloConfig`/``DispersionConfig`` into calls
against that framework, matching the pattern already `.md` documented in
``src/utilities/MonteCarlo/README.md`` and exercised end-to-end in
``examples/scenarioMonteCarloAttRW.py``.

Why ``SimulationService.build(initialize=False)``
---------------------------------------------------
``Controller`` calls, per run: creation function (no args, returns a
``SimBaseClass``) -> apply dispersions (mutating attributes directly on
that returned sim object, via dotted/indexed/zero-arg-method path strings
-- see ``Controller.SimulationExecutor.getNestedAttr``/``setNestedAttr``)
-> configure function (optional) -> execution function. Basilisk's
``InitializeSimulation()`` calls ``Reset()`` on every module using
whatever attribute values are set AT THAT MOMENT -- if it already ran
(which ``SimulationService.build()`` always used to do, Phase 0 through
Phase 2), a dispersion applied afterward would silently have no effect,
since Reset() already latched in the un-dispersed nominal values. So the
creation function here calls ``service.build(initialize=False)`` and the
execution function finishes the job (``InitializeSimulation()``,
``ConfigureStopTime()``, ``ExecuteSimulation()``) AFTER the Controller has
applied every dispersion.

A ``dry_mass_kg`` dispersion writes directly to ``hub.mHub`` (see
``_QUANTITY_PATHS`` below), which survives ``Reset()`` fine (no module's
``Reset()`` touches ``hub.mHub``) -- but a real bug, found by audit and
fixed in ``engine.orbit_maintenance``, used to silently UNDO it on the
first tick for any spacecraft with ``station_keeping``/``constant_thrust``
configured: those controllers used to recompute ``hub.mHub`` from their
own construction-time-captured, undispersed ``dry_mass_kg`` every tick,
discarding whatever this dispersion had just set. See
``engine.orbit_maintenance``'s "Shared mass bookkeeping" docstring note --
those controllers now read ``hub.mHub`` back and only subtract what they
themselves burn, so a dispersion applied here is preserved correctly.

A second, DIFFERENT ``dry_mass_kg`` bug (also found by audit, also fixed):
Basilisk's dispersion classes write their generated value ABSOLUTELY to
the target path, with no way to add anything on top -- but
``schema.scenario.SpacecraftConfig.dry_mass_kg`` is documented as the
mass WITHOUT station-keeping/constant-thrust propellant, while
``hub.mHub`` (this dispersion's actual target) is ``dry_mass_kg +
propellant`` (see ``service.py``'s own ``initial_mass_kg`` computation).
Applying a plain ``UniformDispersion``/``NormalDispersion`` straight to
``hub.mHub`` under the name "dry_mass_kg" would therefore silently
disperse the TOTAL mass under that name for any spacecraft with
``station_keeping``/``constant_thrust`` configured -- bounds the user
picked to disperse just the dry mass would actually disperse dry mass +
propellant, quietly shrinking the effective dry-mass spread by exactly
the propellant amount. Fixed with
:class:`_DryMassPlusPropellantUniformDispersion`/
:class:`_DryMassPlusPropellantNormalDispersion`, which add that
spacecraft's configured propellant back on top of the generated
dry-mass value before it's written to ``hub.mHub``.

Dispersed quantities
--------------------
Each ``schema.scenario.DISPERSION_QUANTITIES`` entry uses one of
Basilisk's own ``Dispersions`` classes, unmodified:

* ``dry_mass_kg``: ``UniformDispersion``/``NormalDispersion`` on
  ``hub.mHub``, plus the propellant (below).
* ``attitude_sigma_bn``: ``UniformEulerAngleMRPDispersion``.
* ``orbit_elements``: ``OrbitalElementDispersion`` on ``hub.r_CN_NInit``
  and ``hub.v_CN_NInit``. It draws every element absolutely and sets one
  with no entry to zero, so each element gets an entry: the nominal value
  (:func:`nominal_elements`, from the same state the service starts the
  run in) with the configured spread, or none.
* ``inertia_kg_m2``: ``InertiaTensorDispersion``, which adds a normal
  offset to each diagonal element and rotates the tensor by small random
  angles. Without bounds it clips each offset to [-1, 1] kg*m^2, so this
  module passes infinite bounds unless the scenario sets its own.
* ``angular_rate_bn_b``: ``NormalVectorCartDispersion``/
  ``UniformVectorCartDispersion``, which draw an absolute vector; the
  subclasses here add the nominal rate back, so the spread is a
  perturbation (deg/s in the scenario, rad/s in Basilisk).
* ``drag_coeff``/``srp_coeff``: ``UniformDispersion``/``NormalDispersion``
  on the sphere ``dragDynamicEffector``'s ``coreParams.dragCoeff`` or the
  ``radiationPressure`` effector's ``coefficientReflection``, reached
  through ``sim.get_drag_<name>()``/``sim.get_srp_<name>()`` (below).

Dispersion path resolution
---------------------------
Basilisk's dispersion path strings resolve via attribute access, integer
indexing, and zero-argument method calls ONLY -- no string-keyed lookups
(confirmed by reading ``Controller._parseAttributePath``/``_resolvePathPart``
directly: a path segment is either ``.name``, ``[int]``, or ``name()``).
Since a scenario can have several spacecraft, and there is no
string-keyed way to reach "the sc_object for spacecraft named X" from the
sim object, the creation function attaches one dynamically-named,
zero-argument accessor method per spacecraft directly onto the returned
sim object (``sim.get_spacecraft_<sanitized name>()`` -> that spacecraft's
``spacecraft.Spacecraft`` instance) -- a dispersion path like
``"get_spacecraft_sat_1().hub.mHub"`` then resolves exactly per the rules
above. This is not a Basilisk API; it is this module's own bridge, built
entirely from the documented, verified path-resolution rules.

Retained data
-------------
V1 scope: every run retains each spacecraft's position/velocity
(``r_BN_N``/``v_BN_N`` off its ``scStateOutMsg`` recorder, via
``sim.msgRecList`` + one ``RetentionPolicy.addMessageLog`` call per
spacecraft -- both documented, verified mechanisms, see
``MonteCarlo/README.md``'s "Retain simulation data" section). There is no
per-run custom retention selection in the schema yet (e.g. "also retain
attitude" or "also retain a specific sensor") -- a reasonable v1 scope
given position/velocity dispersion spread is the headline Monte Carlo
question for a mission-analysis tool, extendable later without a schema
break (``MonteCarloConfig`` is a dataclass like everything else here).

Thread count
------------
``Controller.setThreadCount(n)`` for ``n > 1`` uses ``multiprocessing.Pool``
(confirmed by reading ``Controller.py`` directly). Python's
``multiprocessing`` needs the worker's target callables to be importable
(pickle-based "spawn"/"forkserver" start methods) or merely needs the
parent process state duplicated (fork). This module's creation/execution
functions are plain module-level functions (not closures) specifically so
they pickle cleanly either way, but the SCENARIO itself is threaded through
via ``functools.partial`` (also picklable, since :class:`Scenario` is a
plain dataclass tree of built-in types). This has NOT been exercised
against a real multi-process run in this project's development sandbox
(no Basilisk build here -- see this module's own verification-status note
below), so :data:`schema.scenario.MonteCarloConfig.thread_count` defaults
to the definitely-safe ``1``.

Verification status
--------------------
Requires a Basilisk build -- cannot be executed in this development
sandbox (no Basilisk build here; see ``SpaceMissionStudio/README.md``). Written
directly against ``src/utilities/MonteCarlo/Controller.py``,
``Dispersions.py``, and ``RetentionPolicy.py`` (read directly in this
checkout, including ``Controller``'s path-parsing internals) and against
that package's own ``README.md`` usage guide -- not from memory, and not
guessed.
"""

from __future__ import annotations

import functools
import gzip
import json
import logging
import pickle  # noqa: S403 -- reads back only the archive this same call wrote (security analysis S-04)
import re
from pathlib import Path
from typing import Dict, List

import math

import numpy as np

from Basilisk.utilities import macros, orbitalMotion, simIncludeGravBody
from Basilisk.utilities.MonteCarlo.Controller import Controller
from Basilisk.utilities.MonteCarlo.Dispersions import (
    InertiaTensorDispersion,
    NormalDispersion,
    NormalVectorCartDispersion,
    OrbitalElementDispersion,
    UniformDispersion,
    UniformEulerAngleMRPDispersion,
    UniformVectorCartDispersion,
)
from Basilisk.utilities.MonteCarlo.RetentionPolicy import RetentionPolicy

from ..schema.scenario import DispersionConfig, MonteCarloConfig, Scenario, SimSettings
from . import monte_carlo_results
from .service import SimulationService, _orbit_ic_to_rv

_logger = logging.getLogger(__name__)

# spacecraft.name -> attribute path suffix on that spacecraft's sc_object,
# rooted after the "get_spacecraft_<name>()." accessor -- see module
# docstring. Kept in lock-step with schema.scenario.DISPERSION_QUANTITIES.
_QUANTITY_PATHS = {
    "dry_mass_kg": "hub.mHub",
    "attitude_sigma_bn": "hub.sigma_BNInit",
    "inertia_kg_m2": "hub.IHubPntBc_B",
    "angular_rate_bn_b": "hub.omega_BN_BInit",
    # rooted after the drag/SRP effector accessor instead (_EFFECTOR_ACCESSORS)
    "drag_coeff": "coreParams.dragCoeff",
    "srp_coeff": "coefficientReflection",
}
# Effector accessor prefix for the coefficient quantities (see _create_sim).
_EFFECTOR_ACCESSORS = {"drag_coeff": "get_drag_", "srp_coeff": "get_srp_"}
# OrbitalElementDispersion's element names for each element_spread key,
# and the factor from the key's unit (km, [-], deg) to Basilisk's (m, rad).
_ELEMENT_KEYS = {
    "semi_major_axis_km": ("a", 1000.0),
    "eccentricity": ("e", 1.0),
    "inclination_deg": ("i", math.pi / 180.0),
    "raan_deg": ("Omega", math.pi / 180.0),
    "arg_periapsis_deg": ("omega", math.pi / 180.0),
    "true_anomaly_deg": ("f", math.pi / 180.0),
}


class MonteCarloError(Exception):
    """Raised for anything that prevents building or running the Monte
    Carlo batch -- always a specific, actionable message.
    """


def _accessor_name(spacecraft_name: str) -> str:
    """A valid, unique-enough Python identifier for
    ``sim.get_spacecraft_<...>()`` -- see module docstring. Uniqueness
    relies on ``schema.scenario.Scenario.validate()`` already requiring
    spacecraft names to be unique; two names that only differ by
    non-identifier characters (e.g. ``"sat 1"`` and ``"sat-1"``) would
    collide here, which is a real but narrow edge case worth knowing about
    rather than silently mishandling -- callers with such names should
    rename them.
    """
    safe = re.sub(r"\W+", "_", spacecraft_name)
    if not safe or safe[0].isdigit():
        safe = f"sc_{safe}"
    return f"get_spacecraft_{safe}"


def _propellant_offset_kg(sc_config) -> float:
    """How much MORE than ``dry_mass_kg`` ``engine.service.build()`` itself
    puts in ``hub.mHub`` for this spacecraft at t=0 -- see
    ``schema.scenario.SpacecraftConfig.dry_mass_kg``'s docstring
    (station-keeping/constant-thrust propellant is additional mass on top
    of the dry mass, both added if both are configured, mirroring
    ``service.py``'s own ``initial_mass_kg`` computation exactly).
    """
    offset = 0.0
    if sc_config.station_keeping is not None:
        offset += sc_config.station_keeping.propellant_kg
    if sc_config.constant_thrust is not None:
        offset += sc_config.constant_thrust.propellant_kg
    return offset


class _DryMassPlusPropellantUniformDispersion(UniformDispersion):
    """A ``dry_mass_kg`` dispersion writes its generated value ABSOLUTELY
    to ``hub.mHub`` (Basilisk's dispersion framework has no notion of
    "add this on top of whatever's already there" -- see
    ``Controller.applyModification``/``setNestedAttr``). But
    ``hub.mHub`` is not the dry mass for a spacecraft with
    ``station_keeping``/``constant_thrust`` configured -- it's
    ``dry_mass_kg + propellant`` (``service.py``'s own
    ``initial_mass_kg``). Without this adjustment, a
    ``dry_mass_kg`` dispersion on such a spacecraft would silently
    disperse the TOTAL mass under that name instead: bounds the user
    picked to disperse just the dry mass would actually disperse dry
    mass + propellant, quietly shrinking the effective dry-mass spread
    by exactly the propellant amount on every run. ``generate()``'s
    ``self.magnitude``/percent-of-bounds bookkeeping (from the base
    class) still reflects the DRY-mass draw, since only the final
    returned value gets the offset added.
    """

    def __init__(self, varName, bounds, propellant_offset_kg: float):
        super().__init__(varName, bounds=bounds)
        self._propellant_offset_kg = propellant_offset_kg

    def generate(self, sim):
        return super().generate(sim) + self._propellant_offset_kg


class _DryMassPlusPropellantNormalDispersion(NormalDispersion):
    """Same adjustment as :class:`_DryMassPlusPropellantUniformDispersion`,
    for ``kind="normal"`` dispersions."""

    def __init__(self, varName, mean, stdDeviation, bounds, propellant_offset_kg: float):
        super().__init__(varName, mean=mean, stdDeviation=stdDeviation, bounds=bounds)
        self._propellant_offset_kg = propellant_offset_kg

    def generate(self, sim):
        return super().generate(sim) + self._propellant_offset_kg


class _AddedToNominalNormalRate(NormalVectorCartDispersion):
    """``NormalVectorCartDispersion`` draws an absolute vector; the initial
    body rate is dispersed around its nominal value instead."""

    def __init__(self, varName, stdDeviation, nominal):
        super().__init__(varName, mean=0.0, stdDeviation=stdDeviation)
        self._nominal = np.asarray(nominal, dtype=float)

    def generate(self, sim=None):
        return list(self._nominal + np.asarray(super().generate(sim), dtype=float))


class _AddedToNominalUniformRate(UniformVectorCartDispersion):
    """Same as :class:`_AddedToNominalNormalRate`, uniform per axis."""

    def __init__(self, varName, bounds, nominal):
        super().__init__(varName, bounds=bounds)
        self._nominal = np.asarray(nominal, dtype=float)

    def generate(self, sim=None):
        return list(self._nominal + np.asarray(super().generate(sim), dtype=float))


def _central_body_mu(scenario: Scenario) -> float:
    """[m^3/s^2] the central body's mu, from the same gravity factory the
    service builds the run with."""
    body = scenario.gravity.central_body
    return simIncludeGravBody.gravBodyFactory().createBodies([body])[body].mu


def nominal_elements(scenario: Scenario, sc_config):
    """The spacecraft's initial orbit as Basilisk ``ClassicElements`` in the
    simulation frame, from the same position and velocity the service
    gives the run (so any orbit type, frame or anomaly works)."""
    mu = _central_body_mu(scenario)
    r_n, v_n = _orbit_ic_to_rv(mu, sc_config.orbit, scenario.epoch_utc)
    return orbitalMotion.rv2elem(mu, np.asarray(r_n, dtype=float), np.asarray(v_n, dtype=float))


def _orbit_dispersion(dispersion: DispersionConfig, scenario: Scenario, sc_config, accessor: str):
    """``OrbitalElementDispersion`` around the nominal elements: each one is
    drawn from N(nominal, spread) or U(nominal - spread, nominal + spread);
    elements with no spread keep their nominal value (the Basilisk class
    would otherwise set them to zero)."""
    oe = nominal_elements(scenario, sc_config)
    spread = dispersion.element_spread or {}
    table = {"mu": _central_body_mu(scenario)}
    for key, (element, factor) in _ELEMENT_KEYS.items():
        nominal = float(getattr(oe, element))
        width = float(spread.get(key, 0.0)) * factor
        if dispersion.kind == "normal":
            table[element] = ["normal", nominal, width]
        else:
            table[element] = ["uniform", nominal - width, nominal + width]
    return OrbitalElementDispersion(f"{accessor}().hub.r_CN_NInit", f"{accessor}().hub.v_CN_NInit", table)


def _build_dispersion(dispersion: DispersionConfig, scenario: Scenario):
    accessor = _accessor_name(dispersion.spacecraft)
    sc_config = next((sc for sc in scenario.spacecraft if sc.name == dispersion.spacecraft), None)
    if dispersion.quantity in _EFFECTOR_ACCESSORS:
        effector_accessor = accessor.replace("get_spacecraft_", _EFFECTOR_ACCESSORS[dispersion.quantity], 1)
        path = f"{effector_accessor}().{_QUANTITY_PATHS[dispersion.quantity]}"
        if dispersion.kind == "uniform":
            return UniformDispersion(path, bounds=dispersion.bounds)
        return NormalDispersion(path, mean=dispersion.mean, stdDeviation=dispersion.std_deviation,
                                bounds=dispersion.bounds)
    if dispersion.quantity in ("orbit_elements", "angular_rate_bn_b") and sc_config is None:
        raise MonteCarloError(
            f"dispersion.spacecraft {dispersion.spacecraft!r} is not one of this scenario's spacecraft")
    if dispersion.quantity == "orbit_elements":
        return _orbit_dispersion(dispersion, scenario, sc_config, accessor)
    path = f"{accessor}().{_QUANTITY_PATHS[dispersion.quantity]}"
    if dispersion.quantity == "inertia_kg_m2":
        bounds = dispersion.bounds if dispersion.bounds is not None else [-math.inf, math.inf]
        return InertiaTensorDispersion(path, stdDiag=dispersion.std_deviation, boundsDiag=bounds,
                                       stdAngle=math.radians(dispersion.angle_std_deg or 0.0))
    if dispersion.quantity == "angular_rate_bn_b":
        nominal = sc_config.omega_bn_b_init_rad_s  # [rad/s]
        if dispersion.kind == "normal":
            return _AddedToNominalNormalRate(path, math.radians(dispersion.std_deviation), nominal)
        return _AddedToNominalUniformRate(path, [math.radians(b) for b in dispersion.bounds], nominal)

    if dispersion.quantity == "dry_mass_kg":
        # scenario.validate() (the caller's responsibility -- see
        # run_monte_carlo()'s docstring) already requires
        # dispersion.spacecraft to name a real spacecraft in this
        # scenario, so this lookup cannot fail in practice; the
        # MonteCarloError below is defensive, matching this module's own
        # "always a specific, actionable message" discipline rather than
        # a bare StopIteration/IndexError if that contract is ever violated.
        if sc_config is None:
            raise MonteCarloError(
                f"dispersion.spacecraft {dispersion.spacecraft!r} is not one of this scenario's spacecraft"
            )
        propellant_offset_kg = _propellant_offset_kg(sc_config)
        if dispersion.kind == "uniform":
            return _DryMassPlusPropellantUniformDispersion(
                path, bounds=dispersion.bounds, propellant_offset_kg=propellant_offset_kg)
        if dispersion.kind == "normal":
            return _DryMassPlusPropellantNormalDispersion(
                path, mean=dispersion.mean, stdDeviation=dispersion.std_deviation, bounds=dispersion.bounds,
                propellant_offset_kg=propellant_offset_kg)
    if dispersion.quantity == "attitude_sigma_bn" and dispersion.kind == "uniform_euler_mrp":
        return UniformEulerAngleMRPDispersion(path, bounds=dispersion.bounds)

    # unreachable if DispersionConfig.validate() passed (schema.scenario.DISPERSION_KINDS_BY_QUANTITY
    # is the single source of truth for which (quantity, kind) pairings exist)
    raise MonteCarloError(
        f"no engine.monte_carlo builder for dispersion kind {dispersion.kind!r} on quantity "
        f"{dispersion.quantity!r} (spacecraft {dispersion.spacecraft!r})"
    )


def _create_sim(scenario: Scenario):
    """Monte Carlo creation function (see module docstring for why
    ``initialize=False``). Module-level + ``functools.partial``-bound
    (never a closure) so it stays picklable for ``thread_count > 1``.
    """
    service = SimulationService(scenario)
    service.build(initialize=False)
    sim = service.scSim

    for name, handle in service.spacecraft_handles.items():
        sc_object = handle.sc_object
        accessor = _accessor_name(name)
        setattr(sim, accessor, (lambda sc_object=sc_object: sc_object))
        # The coefficient dispersions write to the drag/SRP effector itself.
        for quantity, prefix in _EFFECTOR_ACCESSORS.items():
            effector = handle.drag_effector if quantity == "drag_coeff" else handle.srp_effector
            if effector is not None:
                setattr(sim, accessor.replace("get_spacecraft_", prefix, 1), (lambda effector=effector: effector))

    sim.msgRecList = {f"{name}.scState": handle.recorder for name, handle in service.spacecraft_handles.items()}
    sim._spacemissionstudio_service = service  # stashed for _execute_sim to finish init/configure/execute
    return sim


def _execute_sim(sim) -> None:
    """Monte Carlo execution function: finishes what ``_create_sim`` left
    undone, AFTER the Controller has applied every dispersion to ``sim``
    (see module docstring).
    """
    service = sim._spacemissionstudio_service
    sim.InitializeSimulation()
    stop_time_s = service.scenario.sim_settings.duration_days * 86400.0
    sim.ConfigureStopTime(macros.sec2nano(stop_time_s))
    sim.ExecuteSimulation()


def _default_retention_policy(scenario: Scenario) -> RetentionPolicy:
    policy = RetentionPolicy()
    for sc in scenario.spacecraft:
        policy.addMessageLog(f"{sc.name}.scState", ["r_BN_N", "v_BN_N"])
    return policy


def run_monte_carlo(scenario: Scenario, mc_config: MonteCarloConfig, archive_dir: "str | Path") -> List[int]:
    """Runs ``mc_config.num_runs`` dispersed executions of ``scenario`` via
    ``Basilisk.utilities.MonteCarlo.Controller``, archiving retained
    position/velocity data (JSON per-run parameter files plus the
    Controller's own pickled archive) to ``archive_dir``. Returns the list
    of FAILED run indices, exactly as ``Controller.executeSimulations()``
    does (empty list == every run succeeded).

    Afterwards it reads those run files back (:func:`collect_batch`) and
    writes the pickle-free summary of ``engine.monte_carlo_results``
    (``batch_results.npz``/``.json``) next to them, which the GUI's Monte
    Carlo tab and ``spacemissionstudio monte-carlo`` show. A failure there
    is logged and does not fail the batch.

    ``scenario`` must already be valid (``scenario.validate()`` -- this
    function does not re-validate it, since :func:`SimulationService.build`
    inside each run's creation function does, and a validation failure
    there surfaces as a per-run failure rather than an upfront one).
    """
    if not mc_config.enabled:
        raise MonteCarloError("monte_carlo.enabled is False -- set it True before calling run_monte_carlo()")
    if scenario.sim_settings.duration_days > SimSettings._MAX_SINGLE_RUN_DAYS:
        raise MonteCarloError(f"Monte Carlo runs at most {SimSettings._MAX_SINGLE_RUN_DAYS:g} days per run "
                              "(sim_settings.duration_days) -- shorten the run")

    archive_dir = Path(archive_dir)
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # e.g. archive_dir already exists as a plain file, or is
        # unwritable -- without this, the raw OSError would escape
        # run_monte_carlo() as something other than MonteCarloError, so
        # cli.py's cmd_monte_carlo() (which only catches MonteCarloError)
        # would let it surface as an uncaught traceback instead of this
        # module's usual "ERROR: ..." + specific exit code convention.
        raise MonteCarloError(f"could not create Monte Carlo archive directory {archive_dir}: {exc}") from exc

    controller = Controller()
    controller.setSimulationFunction(functools.partial(_create_sim, scenario))
    controller.setExecutionFunction(_execute_sim)
    controller.setExecutionCount(mc_config.num_runs)
    controller.setShouldDisperseSeeds(True)
    controller.setThreadCount(mc_config.thread_count)
    controller.setVerbose(mc_config.verbose)
    controller.setArchiveDir(str(archive_dir))

    for dispersion in mc_config.dispersions:
        controller.addDispersion(_build_dispersion(dispersion, scenario))

    controller.addRetentionPolicy(_default_retention_policy(scenario))

    try:
        failures = controller.executeSimulations()
    except Exception as exc:  # noqa: BLE001 -- report ANY batch-level failure with a specific message
        raise MonteCarloError(f"Monte Carlo batch execution failed: {exc}") from exc
    try:
        batch = collect_batch(scenario, archive_dir, mc_config.num_runs, failures)
        if batch.runs:
            monte_carlo_results.save(batch, archive_dir)
    except Exception:  # noqa: BLE001 -- the batch itself ran; a summary problem must not lose that
        _logger.exception("Monte Carlo batch finished, but its summary could not be written")
    return failures


# Readable labels for the drawn values of each dispersed quantity, by the
# last part of the Controller's parameter name (see _QUANTITY_PATHS).
_ELEMENT_LABELS = {
    "semi_major_axis_km": "semi-major axis [km]",
    "eccentricity": "eccentricity [-]",
    "inclination_deg": "inclination [deg]",
    "raan_deg": "RAAN [deg]",
    "arg_periapsis_deg": "argument of periapsis [deg]",
    "true_anomaly_deg": "true anomaly [deg]",
}


def _elements_deg(oe) -> Dict[str, float]:
    """Basilisk ``ClassicElements`` in the element_spread keys' units."""
    return {"semi_major_axis_km": oe.a / 1e3, "eccentricity": oe.e,
            "inclination_deg": math.degrees(oe.i), "raan_deg": math.degrees(oe.Omega),
            "arg_periapsis_deg": math.degrees(oe.omega), "true_anomaly_deg": math.degrees(oe.f)}


def _drawn_values(params: Dict[str, str], scenario: Scenario, mu: float) -> Dict[str, float]:
    """One run's drawn values (``runN.json``: Controller parameter name ->
    value as text), keyed by readable labels."""
    by_accessor = {_accessor_name(sc.name): sc for sc in scenario.spacecraft}
    spread_keys = {d.spacecraft: list(d.element_spread or {}) for d in scenario.monte_carlo.dispersions
                   if d.quantity == "orbit_elements"}
    drawn: Dict[str, float] = {}
    for key, text in params.items():
        accessor, _, path = key.partition("().")
        for prefix in _EFFECTOR_ACCESSORS.values():
            if accessor.startswith(prefix):
                accessor = accessor.replace(prefix, "get_spacecraft_", 1)
        sc = by_accessor.get(accessor)
        if sc is None:
            continue  # e.g. the RNG seeds
        value = np.asarray(json.loads(text), dtype=float)
        if path == "hub.mHub":
            drawn[f"{sc.name} dry mass [kg]"] = float(value) - _propellant_offset_kg(sc)
        elif path == "coreParams.dragCoeff":
            drawn[f"{sc.name} drag coefficient [-]"] = float(value)
        elif path == "coefficientReflection":
            drawn[f"{sc.name} SRP coefficient [-]"] = float(value)
        elif path == "hub.IHubPntBc_B":
            for axis, inertia in zip(("xx", "yy", "zz"), np.diag(value.reshape(3, 3))):
                drawn[f"{sc.name} I{axis} [kg m^2]"] = float(inertia)
        elif path == "hub.omega_BN_BInit":
            for axis, rate in zip("xyz", value.ravel()):
                drawn[f"{sc.name} rate {axis} [deg/s]"] = math.degrees(float(rate))
        elif path == "hub.sigma_BNInit":
            for index, component in enumerate(value.ravel(), start=1):
                drawn[f"{sc.name} attitude MRP {index} [-]"] = float(component)
        elif path == "hub.r_CN_NInit":
            velocity = params.get(key.replace("r_CN_NInit", "v_CN_NInit"))
            if velocity is None:
                continue
            elements = _elements_deg(orbitalMotion.rv2elem(
                mu, value.ravel(), np.asarray(json.loads(velocity), dtype=float).ravel()))
            nominal = _elements_deg(nominal_elements(scenario, sc))
            for element in spread_keys.get(sc.name) or list(elements):
                drawn_value = elements[element]
                if element.endswith("_deg"):  # within 180 deg of the nominal, so 0 +/- 0.1 is not 359.9
                    drawn_value = nominal[element] + (drawn_value - nominal[element] + 180.0) % 360.0 - 180.0
                drawn[f"{sc.name} {_ELEMENT_LABELS[element]}"] = float(drawn_value)
    return drawn


def collect_batch(scenario: Scenario, archive_dir: "str | Path", num_runs: int,
                  failures: List[int]) -> monte_carlo_results.MonteCarloBatch:
    """Every successful run's retained position and velocity, on a shared,
    strided time grid, and the values it drew -- read back from the files
    :func:`run_monte_carlo` has just had the Controller write into
    ``archive_dir``. Only ever called on that call's own output: the run
    files are pickles (security analysis S-04)."""
    archive_dir = Path(archive_dir)
    mu = _central_body_mu(scenario)
    names = [sc.name for sc in scenario.spacecraft]
    runs, raw, drawn = [], [], []
    for run in range(num_runs):
        data_path = archive_dir / f"run{run}.data"
        if run in failures or not data_path.is_file():
            continue
        with gzip.open(data_path) as handle:
            messages = pickle.load(handle)["messages"]  # noqa: S301 -- written by this call (see docstring)
        raw.append({name: (np.asarray(messages[f"{name}.scState.r_BN_N"], dtype=float),
                           np.asarray(messages[f"{name}.scState.v_BN_N"], dtype=float)) for name in names})
        params_path = archive_dir / f"run{run}.json"
        params = json.loads(params_path.read_text()) if params_path.is_file() else {}
        drawn.append(_drawn_values(params, scenario, mu))
        runs.append(run)
    failed = sorted(set(failures) | {run for run in range(num_runs) if run not in runs})
    if not runs:
        return monte_carlo_results.MonteCarloBatch(scenario.name, scenario.gravity.central_body, np.zeros(0),
                                                   [], failed, {}, {}, [])
    samples = min(rv[0].shape[0] for run_data in raw for rv in run_data.values())
    stride = monte_carlo_results.stride_for(samples)
    rows = slice(0, samples, stride)
    time_s = raw[0][names[0]][0][rows, 0] / 1e9  # [s] Basilisk records nanoseconds
    positions = {name: np.stack([run_data[name][0][rows, 1:4] for run_data in raw]) for name in names}
    velocities = {name: np.stack([run_data[name][1][rows, 1:4] for run_data in raw]) for name in names}
    return monte_carlo_results.MonteCarloBatch(scenario.name, scenario.gravity.central_body, time_s, runs,
                                               failed, positions, velocities, drawn, scenario.epoch_utc)
