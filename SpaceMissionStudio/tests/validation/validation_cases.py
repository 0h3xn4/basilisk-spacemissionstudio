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
_LEO_V = [0.0, 4.6, 6.0]  # [km/s] 52.5 deg inclination
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
                    area_m2=1.0, tolerance_m=500.0, note="NRLMSISE-00 with observed 2024 indices"),
]


def case(name: str) -> PropagationCase:
    return next(c for c in PROPAGATION_CASES if c.name == name)


def gmat_reference(name: str) -> Optional[Path]:
    path = GMAT_DATA / f"{name}.txt"
    return path if path.exists() else None
