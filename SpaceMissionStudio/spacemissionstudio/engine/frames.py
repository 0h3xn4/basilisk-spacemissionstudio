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

"""The coordinate systems of a run and the frame of every result series
(ECSS-E-ST-10-09C 5.2.3, 5.3.2, 5.4.1; remediation R02). Basilisk-free.

**Naming convention** (5.3.2a, c-g): each coordinate system has a
descriptive name and a one-letter mnemonic, Basilisk's. A vector carries
its frame as a suffix (``r_BN_N``: position of B relative to N, in N
components); a direction cosine matrix ``dcm_XY`` takes Y components to X
components (``v_X = dcm_XY v_Y``), and a transformation is named
"Y -> X" in the same direction. Attitudes are Basilisk MRPs ``sigma_XY``
(rotation from Y to X, shadow set used for |sigma| > 1). Angles are
radians unless a series' units say otherwise; rotations are right-handed.

The definitions below are what the CSD (``compliance/docs``) restates;
:func:`definitions` and :func:`series_frames` put them into every run's
provenance so results carry their frames (5.4.1a, 5.4.1h).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Frame:
    """A coordinate system: name, mnemonic, origin, axes, epoch, time scale."""

    mnemonic: str
    name: str
    origin: str
    axes: str
    epoch: str = "-"
    time_scale: str = "-"
    realisation: str = "-"


def definitions(central_body: str = "earth", earth_frame: str = "IAU_EARTH") -> Dict[str, Dict[str, str]]:
    """The frames of a run, ``{mnemonic: fields}``."""
    body = central_body.capitalize()
    planet_axes = (f"{earth_frame}: Earth-fixed, z = rotation pole, x = prime meridian"
                   if central_body == "earth" else f"IAU_{central_body.upper()}: IAU body-fixed rotation model")
    frames: List[Frame] = [
        Frame("N", "Inertial (EME2000 / SPICE J2000)", f"{body} centre of mass",
              "Earth mean equator and equinox of J2000 (SPICE J2000, treated as ICRF-aligned by SPICE)",
              epoch="J2000.0 = 2000-01-01T12:00:00 TT", time_scale="TDB (ephemerides, propagation)",
              realisation="SPICE with DE430"),
        Frame("P", f"{body}-fixed", f"{body} centre of mass", planet_axes, time_scale="TDB",
              realisation="SPICE PCK (engine.earth_orientation for Earth)"),
        Frame("B", "Spacecraft body", "spacecraft body point B (Basilisk hub frame origin)",
              "fixed to the spacecraft structure, as given by inertia_kg_m2 and device axes"),
        Frame("H", "Hill (orbit)", "spacecraft", "x radial out, z orbit normal, y completes (along-track)"),
        Frame("L", "Topocentric (ground station)", "ground station site (WGS-84 geodetic, engine.geodesy)",
              "South-East-Zenith; elevation/azimuth from the geodetic horizon, azimuth from North to East"),
        Frame("TEME", "True equator, mean equinox of date (TLE input only)", "Earth centre of mass",
              "SGP4 output frame, converted to N at the scenario epoch (engine.tle)", time_scale="UTC"),
    ]
    return {frame.mnemonic: asdict(frame) for frame in frames}


TRANSFORMATIONS = {
    "N -> P": "dcm_PN = J20002Pfix from SPICE pxform(J2000, P frame, ET) each step; time dependent; SPICE "
              "evaluates the PCK Chebyshev/rotation model at ET (no further interpolation)",
    "N -> B": "dcm_BN from the spacecraft MRP sigma_BN (integrated by Basilisk)",
    "N -> H": "dcm_HN from r_BN_N, v_BN_N (Basilisk hillFrame convention)",
    "P -> L": "dcm_LP from the site's geodetic latitude and longitude (engine.geodesy)",
    "TEME -> N": "P^T N^T R3(-Eq) at the scenario epoch, IAU 1976/1980 (engine.tle)",
}


def series_frames(series_names) -> Dict[str, str]:
    """Frame mnemonic of each result series that has one, from its name."""
    frames = {}
    for name in series_names:
        leaf = name.rsplit(".", 1)[-1]
        if leaf.endswith("_BN"):
            frames[name] = "B relative to N"
        elif leaf.endswith("_N"):
            frames[name] = "N"
        elif leaf.endswith("_B") or leaf.endswith("_body") or "body" in leaf.split("_"):
            frames[name] = "B"
        elif ".orbit_elements" in name:
            frames[name] = "N"
        elif ".access_to_" in name and leaf in ("elevation", "azimuth"):
            frames[name] = "L"
    return frames
