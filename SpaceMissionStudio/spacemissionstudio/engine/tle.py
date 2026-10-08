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

"""Two-line element sets to the simulation's inertial frame
(ECSS-E-ST-10-09C 5.3.1b/c; CCSDS 502.0-B-3 4.2.4.9).

Basilisk-free. A TLE is a non-compliant external convention: SGP4 mean
elements in the TEME frame, with its own epoch. The conversion into the
tool's convention (EME2000, i.e. SPICE ``J2000``, at the scenario epoch) is:

1. **Check** both lines: length, line numbers, matching catalogue number
   and the modulo-10 checksum of each line.
2. **Propagate** with SGP4 (the ``sgp4`` package, the Vallado et al. 2006
   reference implementation, WGS-72 constants as SGP4 requires) from the
   TLE epoch to the scenario epoch (both UTC).
3. **Rotate** from TEME of date (the CCSDS-preferred interpretation) to
   EME2000::

       r_EME2000 = P^T N^T R3(-Eq) r_TEME

   with ``P`` the IAU 1976 precession matrix, ``N`` the IAU 1980 nutation
   matrix and ``Eq = dpsi cos(eps_mean)`` the equation of the equinoxes
   without the 1994 kinematic terms (Vallado et al. 2006, AIAA 2006-6753),
   all evaluated in TT at the scenario epoch with ERFA (the SOFA library).
   No ICRS frame bias is applied: the simulation frame is EME2000, not
   GCRF. Velocity is rotated by the same matrix (the frame's rotation rate,
   ~1e-11 rad/s, is neglected).

Basilisk 2.12's ``tleHandling.satTle2elem`` evaluates SGP4 only at the TLE
epoch and applies the ICRS frame bias, so the tool no longer uses it.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Tuple

import erfa
import numpy as np
from sgp4.api import SGP4_ERRORS, Satrec, jday

TLE_AGE_WARNING_DAYS = 3.0  # [day] warn when the TLE epoch is further from the scenario epoch


class TLEError(ValueError):
    """A TLE that cannot be used, with the reason."""


@dataclass(frozen=True)
class TLEState:
    """A TLE converted to the scenario epoch."""

    r_m: np.ndarray  # [m] EME2000 position
    v_m_s: np.ndarray  # [m/s] EME2000 velocity
    tle_epoch_utc: datetime
    age_days: float  # [day] scenario epoch minus TLE epoch
    catalog_number: str


def _checksum(line: str) -> int:
    return sum(int(c) if c.isdigit() else 1 if c == "-" else 0 for c in line[:68]) % 10


def check_lines(line1: str, line2: str) -> None:
    """Raise :class:`TLEError` naming the first format problem found."""
    for number, line in (("1", line1), ("2", line2)):
        if len(line) != 69:
            raise TLEError(f"TLE line {number} has {len(line)} characters, expected 69")
        if line[0] != number or line[1] != " ":
            raise TLEError(f"TLE line {number} must start with '{number} '")
        if not line[68].isdigit():
            raise TLEError(f"TLE line {number} has no checksum digit in column 69")
        if _checksum(line) != int(line[68]):
            raise TLEError(f"TLE line {number} checksum is {line[68]}, computed {_checksum(line)}")
    if line1[2:7] != line2[2:7]:
        raise TLEError(f"TLE catalogue numbers differ: {line1[2:7]!r} and {line2[2:7]!r}")


def parse(line1: str, line2: str) -> Satrec:
    """Checked SGP4 record of a TLE."""
    line1, line2 = line1.rstrip("\r\n "), line2.rstrip("\r\n ")
    check_lines(line1, line2)
    try:
        return Satrec.twoline2rv(line1, line2)
    except Exception as exc:  # sgp4 raises ValueError on malformed fields
        raise TLEError(f"TLE could not be parsed: {exc}") from exc


def tle_epoch_utc(satrec: Satrec) -> datetime:
    """The TLE epoch as a naive UTC datetime."""
    return datetime(2000, 1, 1, 12) + timedelta(days=(satrec.jdsatepoch - 2451545.0) + satrec.jdsatepochF)


def _utc_to_tt_jd(epoch: datetime) -> Tuple[float, float]:
    """Two-part TT Julian date of a naive UTC datetime (ERFA's leap seconds)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", erfa.ErfaWarning)  # "dubious year" for future epochs
        u1, u2 = erfa.dtf2d("UTC", epoch.year, epoch.month, epoch.day, epoch.hour, epoch.minute,
                            epoch.second + epoch.microsecond / 1e6)
        a1, a2 = erfa.utctai(u1, u2)
        return erfa.taitt(a1, a2)


def teme_to_eme2000_matrix(epoch_utc: datetime) -> np.ndarray:
    """Rotation matrix taking TEME-of-date vectors to EME2000 at ``epoch_utc``."""
    t1, t2 = _utc_to_tt_jd(epoch_utc)
    precession = erfa.pmat76(t1, t2)  # EME2000 -> mean of date
    dpsi, deps = erfa.nut80(t1, t2)
    eps_mean = erfa.obl80(t1, t2)
    nutation = erfa.numat(eps_mean, dpsi, deps)  # mean of date -> true of date
    equinox = erfa.rz(dpsi * math.cos(eps_mean), np.eye(3))  # true of date -> TEME
    return (equinox @ nutation @ precession).T


def _naive_utc(epoch_utc: str) -> datetime:
    epoch = datetime.fromisoformat(epoch_utc)
    if epoch.tzinfo is not None:
        epoch = epoch.astimezone(timezone.utc).replace(tzinfo=None)
    return epoch


def state_at(line1: str, line2: str, epoch_utc: str) -> TLEState:
    """EME2000 state of a TLE propagated by SGP4 to ``epoch_utc`` (ISO 8601)."""
    satrec = parse(line1, line2)
    epoch = _naive_utc(epoch_utc)
    jd, fraction = jday(epoch.year, epoch.month, epoch.day, epoch.hour, epoch.minute,
                        epoch.second + epoch.microsecond / 1e6)  # [day] UTC
    error, r_km, v_km_s = satrec.sgp4(jd, fraction)
    if error != 0:
        raise TLEError(f"SGP4 failed at the scenario epoch: {SGP4_ERRORS.get(error, f'error {error}')}")
    rotation = teme_to_eme2000_matrix(epoch)
    tle_epoch = tle_epoch_utc(satrec)
    return TLEState(r_m=rotation @ np.array(r_km) * 1e3, v_m_s=rotation @ np.array(v_km_s) * 1e3,
                    tle_epoch_utc=tle_epoch, age_days=(epoch - tle_epoch).total_seconds() / 86400.0,
                    catalog_number=line1.strip()[2:7])
