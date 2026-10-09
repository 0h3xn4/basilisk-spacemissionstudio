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

"""Orbital lifetime: how long until drag brings an Earth orbit down.

Simulating decades of decay step by step would take hours, so this
follows the orbit's mean elements instead, one orbit-averaged drag step
at a time:

* the drag on a ring of points spread evenly around the orbit (in mean
  anomaly, so the average is a time average) changes the semi-major axis
  and eccentricity vector (Gauss's equations in vector form);
* J2 turns the node and perigee at their secular rates;
* steps are at most a day, shorter as the orbit nears re-entry.

Density comes from the scenario's own model: Basilisk's ``msisAtmosphere``
(NRLMSISE-00) driven by ``spaceWeatherData`` from the same space-weather
file a simulation would use, or Basilisk's exponential model. Drag acts on
the velocity relative to an atmosphere turning with the Earth, as in the
simulations (``zeroWindModel``).

Re-entry is taken as the perigee reaching :data:`REENTRY_ALTITUDE_KM`;
below that an orbit lasts days at most.

:func:`drag_makeup` uses the same drag model the other way round: the
delta-V a station keeper spends holding an orbit against drag over a
window, for propellant budgets at other launch dates.

Limits: Earth only; sphere (cannonball) drag, or the tumbling-average area
of the facets (sum of facet areas / 4, exact for a convex body); no solar
radiation pressure, third bodies or higher harmonics, which matter little
for orbits that decay within decades. Compared with full Basilisk decay
runs in ``tests/test_lifetime.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

import numpy as np

from . import geodesy

# Basilisk's own Earth constants (architecture/utilities/astroConstants.h)
MU_EARTH_M3_S2 = 398600.436e9  # [m^3/s^2]
REQ_EARTH_M = 6378136.6  # [m]
J2_EARTH = 1082.616e-6  # [-]
OMEGA_EARTH_RAD_S = 2.0 * math.pi / 23.9345 / 3600.0  # [rad/s]

REENTRY_ALTITUDE_KM = 120.0  # [km] perigee altitude counted as re-entry
RING_POINTS = 16  # points around the orbit per drag average
MAX_STEP_S = 86400.0  # [s]
_MAX_PERIGEE_DROP = 0.01  # [-] largest fraction of the remaining perigee height lost in one step

# Disposal rules a lifetime is checked against [year]
ZERO_DEBRIS_YEARS = 5.0  # [year] ESA Zero Debris approach (and the FCC's 5-year rule)
IADC_YEARS = 25.0  # [year] IADC / ISO 24113 guideline


class LifetimeError(Exception):
    """A lifetime this module cannot estimate (e.g. no drag model)."""


@dataclass
class MeanOrbit:
    """Mean classical elements; angles in radians."""

    semi_major_axis_m: float
    eccentricity: float
    inclination_rad: float
    raan_rad: float
    arg_periapsis_rad: float

    @property
    def perigee_altitude_km(self) -> float:
        return (self.semi_major_axis_m * (1.0 - self.eccentricity) - REQ_EARTH_M) / 1e3

    @property
    def apogee_altitude_km(self) -> float:
        return (self.semi_major_axis_m * (1.0 + self.eccentricity) - REQ_EARTH_M) / 1e3

    @property
    def period_s(self) -> float:
        return 2.0 * math.pi * math.sqrt(self.semi_major_axis_m ** 3 / MU_EARTH_M3_S2)


@dataclass
class LifetimeResult:
    reentered: bool
    lifetime_s: float  # [s] to re-entry, or the horizon when not re-entered
    time_s: np.ndarray  # [s] since the start
    perigee_altitude_km: np.ndarray  # [km]
    apogee_altitude_km: np.ndarray  # [km]
    start_utc: datetime
    warnings: List[str] = field(default_factory=list)
    horizon_years: Optional[float] = None  # [year] how far it looked (less than asked where the data ends)

    @property
    def lifetime_years(self) -> float:
        return self.lifetime_s / (365.25 * 86400.0)

    @property
    def reentry_utc(self) -> Optional[datetime]:
        return self.start_utc + timedelta(seconds=self.lifetime_s) if self.reentered else None

    def meets(self, years: float) -> bool:
        """Re-enters within ``years`` of the start."""
        return self.reentered and self.lifetime_years <= years

    def known(self, years: float) -> bool:
        """Whether :meth:`meets` is decided for ``years``: re-entered, or
        looked at least that far ahead."""
        return self.reentered or (self.horizon_years is not None and self.horizon_years >= years)


def _perifocal_axes(orbit: MeanOrbit):
    """Unit vectors to perigee (p) and 90 deg ahead in the orbit plane (q)."""
    cO, sO = math.cos(orbit.raan_rad), math.sin(orbit.raan_rad)
    cw, sw = math.cos(orbit.arg_periapsis_rad), math.sin(orbit.arg_periapsis_rad)
    ci, si = math.cos(orbit.inclination_rad), math.sin(orbit.inclination_rad)
    p = np.array([cO * cw - sO * sw * ci, sO * cw + cO * sw * ci, sw * si])
    q = np.array([-cO * sw - sO * cw * ci, -sO * sw + cO * cw * ci, cw * si])
    return p, q


def ring_states(orbit: MeanOrbit, points: int = RING_POINTS):
    """Positions and velocities [m, m/s] at ``points`` evenly spaced mean
    anomalies, shape (points, 3) each, with J2's short-period terms added
    back (Basilisk's ``clMeanOscMap``, mean -> osculating). Without them
    the ring sits several km below the real path (4.6 km at 300 km), and
    the density there is ~12% too high."""
    from Basilisk.utilities import orbitalMotion

    eccentricity = max(orbit.eccentricity, 1e-7)  # clMeanOscMap divides by e
    r = np.empty((points, 3))
    v = np.empty((points, 3))
    for k in range(points):
        mean = orbitalMotion.ClassicElements()
        mean.a, mean.e, mean.i = orbit.semi_major_axis_m, eccentricity, orbit.inclination_rad
        mean.Omega, mean.omega = orbit.raan_rad, orbit.arg_periapsis_rad
        mean.f = orbitalMotion.E2f(orbitalMotion.M2E(2.0 * math.pi * k / points, eccentricity), eccentricity)
        osculating = orbitalMotion.ClassicElements()
        orbitalMotion.clMeanOscMap(REQ_EARTH_M, J2_EARTH, mean, osculating, 1)
        r[k], v[k] = orbitalMotion.elem2rv(MU_EARTH_M3_S2, osculating)
    return r, v


def mean_orbit_from_state(r_m, v_m_s) -> MeanOrbit:
    """Mean elements (Basilisk's ``clMeanOscMap``, J2 short-period terms
    removed) from an inertial position and velocity [m, m/s]."""
    from Basilisk.utilities import orbitalMotion

    osculating = orbitalMotion.rv2elem(MU_EARTH_M3_S2, np.asarray(r_m, dtype=float), np.asarray(v_m_s, dtype=float))
    osculating.i = min(max(osculating.i, 1e-9), math.pi - 1e-9)  # clMeanOscMap divides by tan(i)
    mean = orbitalMotion.ClassicElements()
    orbitalMotion.clMeanOscMap(REQ_EARTH_M, J2_EARTH, osculating, mean, -1)
    return MeanOrbit(mean.a, max(mean.e, 0.0), mean.i, mean.Omega, mean.omega)


def _gmst_rad(when_utc: datetime) -> float:
    """Greenwich mean sidereal angle [rad] (UT1 taken as UTC)."""
    days = (when_utc - datetime(2000, 1, 1, 12)).total_seconds() / 86400.0
    return math.radians((280.46061837 + 360.98564736629 * days) % 360.0)


DensityModel = Callable[[float, np.ndarray], np.ndarray]  # (seconds since start, r_N (n, 3) [m]) -> [kg/m^3]


class MsisDensity:
    """NRLMSISE-00 density from Basilisk's ``msisAtmosphere``, driven by
    ``spaceWeatherData`` reading ``space_weather_path``. Times are seconds
    after ``start_utc``; both modules take elapsed nanoseconds directly,
    so decades are fine (no ``nanoToSec()`` involved)."""

    def __init__(self, space_weather_path, start_utc: datetime, points: int = RING_POINTS):
        from Basilisk.architecture import messaging
        from Basilisk.simulation import msisAtmosphere, spaceWeatherData

        self.start_utc = start_utc
        self.points = points
        self._messaging = messaging
        self._epoch_msg = messaging.EpochMsg()
        epoch = messaging.EpochMsgPayload()
        epoch.year, epoch.month, epoch.day = start_utc.year, start_utc.month, start_utc.day
        epoch.hours, epoch.minutes = start_utc.hour, start_utc.minute
        epoch.seconds = float(start_utc.second)  # [s] whole seconds: MSIS reads an integer
        self._epoch_msg.write(epoch)
        self._weather = spaceWeatherData.SpaceWeatherData()
        self._weather.loadSpaceWeatherFile(str(space_weather_path))
        self._weather.epochInMsg.subscribeTo(self._epoch_msg)
        self._atmosphere = msisAtmosphere.MsisAtmosphere()
        self._atmosphere.epochInMsg.subscribeTo(self._epoch_msg)
        self._planet_msg = messaging.SpicePlanetStateMsg()
        self._atmosphere.planetPosInMsg.subscribeTo(self._planet_msg)
        self._state_msgs = [messaging.SCStatesMsg() for _ in range(points)]
        for msg in self._state_msgs:
            self._atmosphere.addSpacecraftToModel(msg)
        for index in range(23):  # fixed count of space-weather messages msisAtmosphere reads
            self._atmosphere.swDataInMsgs[index].subscribeTo(self._weather.swDataOutMsgs[index])
        self._write_inputs(0.0, np.zeros((points, 3)) + [REQ_EARTH_M + 4e5, 0.0, 0.0])
        self._weather.Reset(0)
        self._atmosphere.Reset(0)

    def _write_inputs(self, t_s: float, r_m: np.ndarray) -> None:
        planet = self._messaging.SpicePlanetStateMsgPayload()
        angle = _gmst_rad(self.start_utc + timedelta(seconds=t_s))
        c, s = math.cos(angle), math.sin(angle)
        planet.J20002Pfix = [[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]]
        self._planet_msg.write(planet)
        for msg, position in zip(self._state_msgs, r_m):
            state = self._messaging.SCStatesMsgPayload()
            # geodetic altitude and latitude, as the simulation's atmosphere sees them (engine.geodetic_atmosphere)
            proxy = geodesy.atmosphere_proxy_position(position, planet.J20002Pfix, self._atmosphere.planetRadius)
            state.r_BN_N = [float(v) for v in proxy]
            msg.write(state)

    def __call__(self, t_s: float, r_m: np.ndarray) -> np.ndarray:
        self._write_inputs(t_s, r_m)
        nanos = int(round(t_s * 1e9))
        self._weather.UpdateState(nanos)
        self._atmosphere.UpdateState(nanos)
        return np.array([self._atmosphere.envOutMsgs[k].read().neutralDensity for k in range(len(r_m))])


def exponential_density(t_s: float, r_m: np.ndarray) -> np.ndarray:
    """Basilisk's exponential Earth atmosphere, as
    ``simSetPlanetEnvironment.exponentialAtmosphere(module, "earth")`` sets
    it up (1.217 kg/m^3 at the surface, 8.5 km scale height)."""
    altitude_m = np.array([geodesy.pcpf_to_geodetic(r)[2] for r in np.atleast_2d(r_m)])  # [m] geodetic
    return 1.217 * np.exp(-altitude_m / 8500.0)  # [kg/m^3]


def _drag_rates(orbit: MeanOrbit, t_s: float, ballistic_m2_kg: float, density: DensityModel):
    """Orbit-averaged da/dt [m/s] and d(eccentricity vector)/dt [1/s] from
    drag, ``ballistic_m2_kg`` = Cd * A / m."""
    r, v = ring_states(orbit, getattr(density, "points", RING_POINTS))
    omega = np.array([0.0, 0.0, OMEGA_EARTH_RAD_S])
    v_rel = v - np.cross(omega, r)
    rho = density(t_s, r)
    accel = -0.5 * ballistic_m2_kg * (rho * np.linalg.norm(v_rel, axis=1))[:, None] * v_rel  # [m/s^2]
    a = orbit.semi_major_axis_m
    da_dt = np.mean(2.0 * a * a / MU_EARTH_M3_S2 * np.sum(v * accel, axis=1))
    de_vec_dt = np.mean((2.0 * np.sum(v * accel, axis=1)[:, None] * r - np.sum(r * v, axis=1)[:, None] * accel
                         - np.sum(r * accel, axis=1)[:, None] * v), axis=0) / MU_EARTH_M3_S2
    return da_dt, de_vec_dt


def _j2_rates(orbit: MeanOrbit):
    """Secular node and perigee rates [rad/s] from J2."""
    a, e, i = orbit.semi_major_axis_m, orbit.eccentricity, orbit.inclination_rad
    n = math.sqrt(MU_EARTH_M3_S2 / a ** 3)
    factor = 1.5 * J2_EARTH * (REQ_EARTH_M / (a * (1.0 - e * e))) ** 2 * n
    return -factor * math.cos(i), factor * (2.0 - 2.5 * math.sin(i) ** 2)


def _advanced(orbit: MeanOrbit, step_s: float, da_dt: float, de_vec_dt: np.ndarray) -> MeanOrbit:
    """``orbit`` after ``step_s`` [s] of the given drag rates plus J2."""
    p, q = _perifocal_axes(orbit)
    normal = np.cross(p, q)
    e_vec = orbit.eccentricity * p + step_s * de_vec_dt
    e_vec -= (e_vec @ normal) * normal  # stay in the orbit plane
    node_rate, perigee_rate = _j2_rates(orbit)
    eccentricity = float(np.linalg.norm(e_vec))
    turn = math.atan2(float(e_vec @ q), float(e_vec @ p)) if eccentricity > 1e-12 else 0.0
    return MeanOrbit(orbit.semi_major_axis_m + da_dt * step_s, eccentricity, orbit.inclination_rad,
                     orbit.raan_rad + node_rate * step_s, orbit.arg_periapsis_rad + turn + perigee_rate * step_s)


def _perigee_drop_rate(orbit: MeanOrbit, da_dt: float, de_vec_dt: np.ndarray) -> float:
    """How fast the perigee height falls [m/s]."""
    de_dt = float(de_vec_dt @ _perifocal_axes(orbit)[0])  # [1/s] along the current perigee
    return -(da_dt * (1.0 - orbit.eccentricity) - orbit.semi_major_axis_m * de_dt)


def propagate_decay(orbit: MeanOrbit, start_utc: datetime, ballistic_m2_kg: float, density: DensityModel,
                    max_years: float = 30.0,
                    should_cancel: Optional[Callable[[], bool]] = None) -> LifetimeResult:
    """Follows ``orbit`` down until re-entry or ``max_years``, one midpoint
    step at a time (rates taken half-way through each step: a plain step
    from the start lags the rising density and decays ~2% slow)."""
    horizon_s = max_years * 365.25 * 86400.0  # [s]
    t_s = 0.0  # [s]
    times, perigees, apogees = [0.0], [orbit.perigee_altitude_km], [orbit.apogee_altitude_km]
    while t_s < horizon_s and orbit.perigee_altitude_km > REENTRY_ALTITUDE_KM:
        if should_cancel is not None and should_cancel():
            break
        da_dt, de_vec_dt = _drag_rates(orbit, t_s, ballistic_m2_kg, density)
        drop_m_s = _perigee_drop_rate(orbit, da_dt, de_vec_dt)
        remaining_m = (orbit.perigee_altitude_km - REENTRY_ALTITUDE_KM) * 1e3  # [m]
        step_s = MAX_STEP_S if drop_m_s <= 0.0 else min(MAX_STEP_S, _MAX_PERIGEE_DROP * remaining_m / drop_m_s)
        step_s = min(max(step_s, orbit.period_s), horizon_s - t_s)  # [s]
        middle = _advanced(orbit, 0.5 * step_s, da_dt, de_vec_dt)
        da_dt, de_vec_dt = _drag_rates(middle, t_s + 0.5 * step_s, ballistic_m2_kg, density)
        orbit = _advanced(orbit, step_s, da_dt, de_vec_dt)
        t_s += step_s
        times.append(t_s)
        perigees.append(orbit.perigee_altitude_km)
        apogees.append(orbit.apogee_altitude_km)
        if orbit.semi_major_axis_m * (1.0 - orbit.eccentricity) < REQ_EARTH_M:
            break
    reentered = orbit.perigee_altitude_km <= REENTRY_ALTITUDE_KM
    return LifetimeResult(reentered=reentered, lifetime_s=t_s, time_s=np.array(times),
                          perigee_altitude_km=np.array(perigees), apogee_altitude_km=np.array(apogees),
                          start_utc=start_utc)


def deorbit_burn(orbit: MeanOrbit, target_perigee_km: float, mass_kg: float, isp_s: float):
    """One retrograde burn at apogee lowering the perigee to
    ``target_perigee_km``: returns (delta-V [m/s], propellant [kg], the
    lowered orbit)."""
    r_apo = orbit.semi_major_axis_m * (1.0 + orbit.eccentricity)  # [m]
    r_peri_new = REQ_EARTH_M + target_perigee_km * 1e3  # [m]
    if r_peri_new >= orbit.semi_major_axis_m * (1.0 - orbit.eccentricity):
        return 0.0, 0.0, MeanOrbit(**vars(orbit))
    a_new = 0.5 * (r_apo + r_peri_new)  # [m]
    v_old = math.sqrt(MU_EARTH_M3_S2 * (2.0 / r_apo - 1.0 / orbit.semi_major_axis_m))  # [m/s]
    v_new = math.sqrt(MU_EARTH_M3_S2 * (2.0 / r_apo - 1.0 / a_new))  # [m/s]
    delta_v = v_old - v_new  # [m/s]
    propellant = mass_kg * (1.0 - math.exp(-delta_v / (isp_s * 9.80665)))  # [kg]
    lowered = _orbit_after_retro_burn(orbit, delta_v)
    return delta_v, propellant, lowered


def _parse_utc(epoch_utc: str) -> datetime:
    when = datetime.fromisoformat(epoch_utc)
    return when.astimezone(timezone.utc).replace(tzinfo=None) if when.tzinfo is not None else when


def drag_properties(spacecraft) -> tuple:
    """(area [m^2], drag coefficient [-]) for a lifetime: the facets'
    tumbling average (sum of areas / 4) when set, else the sphere model."""
    if spacecraft.facets:
        total = sum(f.area_m2 for f in spacecraft.facets)  # [m^2]
        return total / 4.0, sum(f.area_m2 * f.drag_coeff for f in spacecraft.facets) / total
    return spacecraft.drag_area_m2, spacecraft.drag_coeff


def density_for_scenario(scenario, start_utc: datetime, max_years: float, points: int = RING_POINTS,
                         forecast_percentile: float = 50.0):
    """The scenario's atmosphere model as a :data:`DensityModel` from
    ``start_utc``, the years it can look ahead (``max_years``, or less
    where the real space-weather data ends), and any warnings. Solar
    activity at MSFC's ``forecast_percentile`` (ESA AD10 Sec. 5.9: 50
    for end of life)."""
    sw_config = scenario.space_weather
    if sw_config.atmosphere_model == "exponential":
        return exponential_density, max_years, [
            "the exponential atmosphere (8.5 km scale height from sea level) is far too thin above ~150 km: "
            "the lifetime is overstated -- use NRLMSISE-00"]
    from . import spaceweather

    try:
        first, last = spaceweather.data_coverage(sw_config.source, sw_config.local_file_path, sw_config.cache_dir,
                                                 sw_config.msfc_file_path)
    except spaceweather.SpaceWeatherError as exc:
        raise LifetimeError(str(exc)) from None
    pad = timedelta(days=11.0)  # [day] the resolver's own padding, plus a day
    if start_utc - pad < datetime.combine(first, datetime.min.time()):
        raise LifetimeError(f"the real space-weather data starts {first}, after {start_utc:%Y-%m-%d}")
    warnings = []
    if last is not None:
        data_years = ((datetime.combine(last, datetime.min.time()) - pad) - start_utc).total_seconds() \
            / (365.25 * 86400.0)
        if data_years <= 0.0:
            raise LifetimeError(f"the real space-weather data ends {last}, before {start_utc:%Y-%m-%d}")
        if data_years < max_years:
            warnings.append(f"the real space-weather data ends {last}: looked {data_years:.1f} years ahead, "
                            f"not {max_years:g}")
            max_years = data_years
    end_utc = start_utc + timedelta(days=max_years * 365.25)
    try:
        resolved = spaceweather.resolve_for(sw_config, start_utc, end_utc, forecast_percentile=forecast_percentile)
    except spaceweather.SpaceWeatherError as exc:
        raise LifetimeError(str(exc)) from None
    return MsisDensity(resolved.path, start_utc, points), max_years, warnings + list(resolved.warnings)


MAKEUP_STEP_S = 21600.0  # [s] drag make-up sampling step


@dataclass
class DragMakeup:
    """Delta-V to hold an orbit against drag (:func:`drag_makeup`)."""

    delta_v_m_s: float  # [m/s] over the whole window
    time_s: np.ndarray  # [s] since the start
    cumulative_m_s: np.ndarray  # [m/s] delta-V up to each time
    altitude_km: float  # [km] mean orbit radius held, above the equatorial radius
    years: float  # [year] window covered (less than asked where the data ends)
    warnings: List[str] = field(default_factory=list)


def held_orbit(spacecraft) -> MeanOrbit:
    """The mean orbit a spacecraft keeps: its initial orbit, with the
    semi-major axis set so the orbit's mean radius is the station-keeping
    target (Req + ``target_altitude_km``, as the controller holds it)."""
    from .service import _orbit_ic_to_rv  # the same orbit set-up a run uses

    orbit = mean_orbit_from_state(*_orbit_ic_to_rv(MU_EARTH_M3_S2, spacecraft.orbit))
    if spacecraft.station_keeping is not None:
        target_m = REQ_EARTH_M + spacecraft.station_keeping.target_altitude_km * 1e3  # [m]
        for _ in range(3):  # the J2 short-period terms move the mean radius by a few km: converges in 2
            r, _v = ring_states(orbit)
            orbit.semi_major_axis_m += target_m - float(np.linalg.norm(r, axis=1).mean())
    return orbit


def drag_makeup(scenario, spacecraft, start_utc: datetime, years: float, forecast_percentile: float = 50.0,
                drag_coeff: Optional[float] = None, step_s: float = MAKEUP_STEP_S,
                should_cancel: Optional[Callable[[], bool]] = None) -> DragMakeup:
    """Delta-V [m/s] that holds the spacecraft's orbit (:func:`held_orbit`)
    against drag for ``years`` from ``start_utc``: the orbit-averaged
    along-track drag, integrated over the window, with J2 turning the node
    and perigee. Mass: dry plus the propellant aboard at the start, held
    fixed. Drag coefficient: ``drag_coeff``, else the spacecraft's (the
    facets' tumbling average when set).

    Against full five-year Basilisk station-keeping runs (template 18)
    this comes out ~5% low: -5.4% over five years from 2030 at MSFC's 50th
    percentile and Cd 2.2, -4.9% from 2033 at the 95th and Cd 3.0 (-2 to
    -6% per year from the second year; -19% and -3% over the first;
    compliance/drag_remeasure.md, re-measured after F-07 and F-09). The
    simulated controller spends more than the drag it replaces; why
    exactly is not pinned down. Ratios of it (one launch date against
    another) carry over better than its absolute value."""
    if scenario.gravity.central_body != "earth":
        raise LifetimeError("drag make-up is only estimated around Earth")
    orbit = held_orbit(spacecraft)
    area_m2, own_cd = drag_properties(spacecraft)
    _isp, propellant_kg = _propulsion(spacecraft)
    mass_kg = spacecraft.dry_mass_kg + propellant_kg  # [kg]
    if spacecraft.fuel_tank is not None:
        mass_kg += spacecraft.fuel_tank.propellant_mass_kg
    ballistic = (own_cd if drag_coeff is None else drag_coeff) * area_m2 / mass_kg  # [m^2/kg]
    density, years, warnings = density_for_scenario(scenario, start_utc, years,
                                                    forecast_percentile=forecast_percentile)
    node_rate, perigee_rate = _j2_rates(orbit)
    omega = np.array([0.0, 0.0, OMEGA_EARTH_RAD_S])
    steps = max(1, int(round(years * 365.25 * 86400.0 / step_s)))
    step_s = years * 365.25 * 86400.0 / steps  # [s]
    times, cumulative = np.empty(steps), np.empty(steps)
    total = 0.0  # [m/s]
    for k in range(steps):
        if should_cancel is not None and should_cancel():
            raise LifetimeError("cancelled")
        t_s = (k + 0.5) * step_s  # [s] mid-step
        turned = MeanOrbit(orbit.semi_major_axis_m, orbit.eccentricity, orbit.inclination_rad,
                           orbit.raan_rad + node_rate * t_s, orbit.arg_periapsis_rad + perigee_rate * t_s)
        r, v = ring_states(turned, getattr(density, "points", RING_POINTS))
        v_rel = v - np.cross(omega, r)
        rho = density(t_s, r)
        accel = -0.5 * ballistic * (rho * np.linalg.norm(v_rel, axis=1))[:, None] * v_rel  # [m/s^2]
        total -= float(np.mean(np.sum(v * accel, axis=1) / np.linalg.norm(v, axis=1))) * step_s
        times[k], cumulative[k] = (k + 1) * step_s, total
    radius_r, _v = ring_states(orbit)
    altitude_km = (float(np.linalg.norm(radius_r, axis=1).mean()) - REQ_EARTH_M) / 1e3
    return DragMakeup(total, times, cumulative, altitude_km, years, warnings)


def spacecraft_lifetime(scenario, spacecraft_name: str, max_years: float = 30.0,
                        should_cancel: Optional[Callable[[], bool]] = None,
                        forecast_percentile: float = 50.0, drag_coeff: Optional[float] = None) -> LifetimeResult:
    """Natural lifetime of one spacecraft from the scenario's start (see
    :func:`end_of_life` for after a run, or with a deorbit burn)."""
    return end_of_life(scenario, spacecraft_name, max_years=max_years, should_cancel=should_cancel,
                       forecast_percentile=forecast_percentile, drag_coeff=drag_coeff).lifetime


@dataclass
class DeorbitPlan:
    """A retrograde apogee burn lowering the perigee."""

    target_perigee_km: float  # [km] asked for
    perigee_km: float  # [km] reached (lower propellant can mean higher than asked)
    delta_v_m_s: float  # [m/s]
    propellant_kg: float  # [kg] burned
    propellant_available_kg: float  # [kg]

    @property
    def sufficient(self) -> bool:
        return self.perigee_km <= self.target_perigee_km + 1e-6


@dataclass
class EndOfLife:
    lifetime: LifetimeResult
    from_end_of_run: bool
    mass_kg: float  # [kg] at the start of the decay
    deorbit: Optional[DeorbitPlan] = None


def _propulsion(spacecraft):
    """(Isp [s], propellant [kg]) of the spacecraft's orbit thruster, if any."""
    for block in (spacecraft.station_keeping, spacecraft.geo_station_keeping, spacecraft.constant_thrust):
        if block is not None:
            return block.isp_s, block.propellant_kg
    return None, 0.0


def _remaining_propellant(result, name: str, initial_kg: float) -> float:
    for key in ("station_keeping", "geo_station_keeping", "constant_thrust"):
        series = result.series.get(f"{name}.{key}.propellant_remaining")
        if series is not None and len(series.data):
            return float(series.data[-1, 0])
    return initial_kg


def end_of_life(scenario, spacecraft_name: str, result=None, deorbit_perigee_km: Optional[float] = None,
                max_years: float = 30.0, should_cancel: Optional[Callable[[], bool]] = None,
                forecast_percentile: float = 50.0, drag_coeff: Optional[float] = None) -> EndOfLife:
    """Lifetime of one spacecraft after the run in ``result`` (from its
    last state, with the propellant left), or from the scenario's start
    when ``result`` is None. With ``deorbit_perigee_km``, an apogee burn
    first lowers the perigee there, or as far as the propellant allows.
    Solar activity at MSFC's ``forecast_percentile`` (ESA AD10 Sec. 5.9:
    50 for end of life, whatever the scenario's operations setting);
    ``drag_coeff`` replaces the spacecraft's own (AD10 Sec. 5.2: 2.2 at
    end of life, against 3.0 in operations)."""
    spacecraft = next((sc for sc in scenario.spacecraft if sc.name == spacecraft_name), None)
    if spacecraft is None:
        raise LifetimeError(f"no spacecraft named {spacecraft_name!r}")
    isp_s, propellant_kg = _propulsion(spacecraft)
    r_m = v_m_s = None
    elapsed_s = 0.0  # [s]
    if result is not None:
        position = result.series.get(f"{spacecraft_name}.position_N")
        velocity = result.series.get(f"{spacecraft_name}.velocity_N")
        if position is None or not len(position.data):
            raise LifetimeError(f"the last run has no position for {spacecraft_name!r}")
        r_m, v_m_s, elapsed_s = position.data[-1], velocity.data[-1], float(position.time_s[-1])
        propellant_kg = _remaining_propellant(result, spacecraft_name, propellant_kg)
    mass_kg = spacecraft.dry_mass_kg + propellant_kg  # [kg]
    if spacecraft.fuel_tank is not None:
        mass_kg += spacecraft.fuel_tank.propellant_mass_kg

    if scenario.gravity.central_body != "earth":
        raise LifetimeError("orbit lifetime is only estimated around Earth")
    if r_m is None:
        from .service import _orbit_ic_to_rv  # the same orbit set-up a run uses

        r_m, v_m_s = _orbit_ic_to_rv(MU_EARTH_M3_S2, spacecraft.orbit, scenario.epoch_utc)
    orbit = mean_orbit_from_state(r_m, v_m_s)
    plan = None
    if deorbit_perigee_km is not None:
        if isp_s is None:
            raise LifetimeError(f"{spacecraft_name} has no orbit thruster (station keeping or constant thrust) "
                                "for a deorbit burn")
        delta_v, needed_kg, lowered = deorbit_burn(orbit, deorbit_perigee_km, mass_kg, isp_s)
        if needed_kg > propellant_kg:  # burn what there is: lower the perigee as far as it goes
            delta_v = isp_s * 9.80665 * math.log(mass_kg / (mass_kg - propellant_kg))  # [m/s]
            lowered = _orbit_after_retro_burn(orbit, delta_v)
            needed_kg = propellant_kg
        plan = DeorbitPlan(deorbit_perigee_km, lowered.perigee_altitude_km, delta_v, needed_kg, propellant_kg)
        orbit, mass_kg = lowered, mass_kg - needed_kg
    area_m2, own_cd = drag_properties(spacecraft)
    drag_coeff = own_cd if drag_coeff is None else drag_coeff
    start_utc = _parse_utc(scenario.epoch_utc) + timedelta(seconds=elapsed_s)
    density, horizon_years, warnings = density_for_scenario(scenario, start_utc, max_years,
                                                            forecast_percentile=forecast_percentile)
    lifetime = propagate_decay(orbit, start_utc, drag_coeff * area_m2 / mass_kg, density, horizon_years,
                               should_cancel)
    lifetime.horizon_years = horizon_years
    lifetime.warnings.extend(warnings)
    return EndOfLife(lifetime, result is not None, mass_kg, plan)


def _orbit_after_retro_burn(orbit: MeanOrbit, delta_v_m_s: float) -> MeanOrbit:
    """``orbit`` after slowing by ``delta_v_m_s`` at apogee."""
    r_apo = orbit.semi_major_axis_m * (1.0 + orbit.eccentricity)  # [m]
    v_apo = math.sqrt(MU_EARTH_M3_S2 * (2.0 / r_apo - 1.0 / orbit.semi_major_axis_m)) - delta_v_m_s  # [m/s]
    a_new = 1.0 / (2.0 / r_apo - v_apo * v_apo / MU_EARTH_M3_S2)  # [m]
    r_peri = 2.0 * a_new - r_apo  # [m]
    return MeanOrbit(a_new, (r_apo - r_peri) / (r_apo + r_peri), orbit.inclination_rad, orbit.raan_rad,
                     orbit.arg_periapsis_rad + (math.pi if orbit.eccentricity > 0.0 else 0.0))
