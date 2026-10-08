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
"""Phase 3 validation cases (remediation R13), shared by the GMAT reference
generator (``compliance/validation/make_gmat_references.py``) and the
tests in this directory, so both sides propagate exactly the same initial
state with the same force model.

Constants are the tool's, so a difference between the tool and GMAT is an
implementation difference, not a constant choice: Earth GM 398600.436
km^3/s^2, Sun 132712440023.310 and Moon 4902.799 km^3/s^2 (BODY10_GM,
BODY301_GM of de-403-masses.tpc), the GGM03S field, DE430 ephemerides,
solar flux 1361 W/m^2 at 1 AU.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

DATA = Path(__file__).resolve().parent.parent / "data" / "validation"
GMAT_DATA = DATA / "gmat"

EARTH_GM_KM3_S2 = 398600.436  # [km^3/s^2]
SUN_GM_KM3_S2 = 132712440023.310  # [km^3/s^2]
MOON_GM_KM3_S2 = 4902.799  # [km^3/s^2]
WGS84_A_KM = 6378.137  # [km]
WGS84_INV_F = 298.257223563  # [-]
SOLAR_FLUX_W_M2 = 1361.0  # [W/m^2] at 1 AU
OUTPUT_STEP_S = 600.0  # [s] GMAT report interval


@dataclass(frozen=True)
class PropagationCase:
    """One orbit propagated by the tool and by GMAT."""

    name: str
    epoch_utc: str
    r_km: List[float]
    v_km_s: List[float]
    days: float
    degree: int = 0
    third_bodies: List[str] = field(default_factory=list)  # "sun", "moon"
    srp: bool = False
    drag: bool = False
    mass_kg: float = 500.0  # [kg]
    area_m2: float = 10.0  # [m^2] SRP and drag area
    cr: float = 1.3  # [-]
    cd: float = 2.2  # [-]
    tolerance_m: float = 1.0  # [m] largest allowed position difference
    note: str = ""


_LEO_R = [6778.137, 0.0, 0.0]  # [km] 400 km altitude
_LEO_V = [0.0, 4.668322, 6.083876]  # [km/s] circular, 52.5 deg inclination
_GEO_R = [42164.17, 0.0, 0.0]  # [km]
_GEO_V = [0.0, 3.07466, 0.0537]  # [km/s] about 1 deg inclination
_SSO_R = [7078.137, 0.0, 0.0]  # [km] 700 km altitude
_SSO_V = [0.0, -1.0384, 7.4314]  # [km/s] about 98.2 deg inclination

PROPAGATION_CASES = [
    PropagationCase("twobody_leo", "2024-06-01T00:00:00", _LEO_R, _LEO_V, 1.0, tolerance_m=0.05,
                    note="point-mass Earth"),
    PropagationCase("ggm03s_20_leo", "2024-06-01T00:00:00", _LEO_R, _LEO_V, 1.0, degree=20, tolerance_m=1.0,
                    note="GGM03S degree and order 20"),
    PropagationCase("third_body_geo", "2024-03-15T00:00:00", _GEO_R, _GEO_V, 7.0, third_bodies=["sun", "moon"],
                    tolerance_m=1.0, note="Sun and Moon point masses, DE430"),
    PropagationCase("srp_geo", "2024-03-15T00:00:00", _GEO_R, _GEO_V, 7.0, third_bodies=["sun", "moon"],
                    srp=True, tolerance_m=10.0, note="cannonball SRP with eclipses (equinox season)"),
    PropagationCase("drag_leo", "2024-06-01T00:00:00", _LEO_R, _LEO_V, 1.0, drag=True, mass_kg=100.0,
                    area_m2=1.0, tolerance_m=1600.0, note="NRLMSISE-00 with observed 2024 indices"),
    # drag_leo tolerance: 5 % of GMAT's drag-induced displacement after one day (32 km). Revised after the
    # first comparison from an absolute 500 m chosen without analysis (compliance/phase3_log.md, V-04).
]


#: V-01 epochs (UTC): either side of the 1999-01-01 and 2017-01-01 leap seconds, J2000.0, the annual TDB
#: extremes, today and the template epochs.
TIME_EPOCHS = ["1980-01-06T00:00:00", "1998-12-31T23:59:59", "1999-01-01T00:00:00", "2000-01-01T11:58:55.816",
               "2004-04-06T07:51:28.386", "2016-12-31T23:59:59", "2017-01-01T00:00:00", "2024-01-03T12:00:00",
               "2024-07-04T12:00:00", "2026-10-08T00:00:00", "2030-01-01T00:00:00"]
# [s] GMAT reports MJD to ~1 us. TDB-TT: GMAT uses the two-term series 0.001657 sin M + 0.00001385 sin 2M
# (checked to 1 us), whose omitted terms reach ~35 us; the first tolerance, 20 us, assumed a full series and was
# revised after the comparison (compliance/phase3_log.md, V-01). The full series is checked against SOFA's own
# test value instead.
TIME_TOLERANCE_S = {"tai_minus_utc": 2e-6, "tt_minus_tai": 2e-6, "tdb_minus_tt": 5e-5}


#: V-05: Berlin (WGS-84 geodetic), 10 deg mask, seen from the twobody_leo orbit for one day.
STATION = {"name": "berlin", "latitude_deg": 52.52, "longitude_deg": 13.405, "altitude_m": 34.0,
           "min_elevation_deg": 10.0}
CONTACT_CASE = "twobody_leo"
CONTACT_TOLERANCE_S = 1.0  # [s] on each pass start and end


def case(name: str) -> PropagationCase:
    return next(c for c in PROPAGATION_CASES if c.name == name)


def tool_scenario(case: PropagationCase, station: bool = False):
    """The tool scenario for ``case``, run as a user would (10 s dynamics
    step, RKF78); with ``station``, ``STATION`` is added as a ground station."""
    from spacemissionstudio.schema import load_scenario
    from spacemissionstudio.schema.scenario import GroundStationConfig

    scenario = load_scenario(DATA.parents[2] / "spacemissionstudio" / "scenarios" / "two_body_validation.json")
    scenario.name = f"validation {case.name}"
    scenario.epoch_utc = case.epoch_utc
    scenario.gravity.central_body_degree = case.degree
    scenario.gravity.third_body_perturbers = list(case.third_bodies)
    scenario.sim_settings.duration_days = case.days  # [day]
    scenario.sim_settings.dynamics_task_rate_s = 10.0  # [s] the default
    sc = scenario.spacecraft[0]
    sc.orbit.type, sc.orbit.position_km, sc.orbit.velocity_km_s = "cartesian", list(case.r_km), list(case.v_km_s)
    sc.dry_mass_kg = case.mass_kg
    sc.enable_srp, sc.srp_area_m2, sc.srp_coeff = case.srp, case.area_m2, case.cr
    sc.enable_drag, sc.drag_area_m2, sc.drag_coeff = case.drag, case.area_m2, case.cd
    if station:
        scenario.ground_stations = [GroundStationConfig(**STATION)]
    return scenario


def gmat_reference(name: str) -> Optional[Path]:
    path = GMAT_DATA / f"{name}.txt"
    return path if path.exists() else None
