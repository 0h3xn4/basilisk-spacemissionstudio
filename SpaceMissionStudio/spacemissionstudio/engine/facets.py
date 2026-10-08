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

"""Facet models for attitude-dependent drag and SRP
(:class:`schema.scenario.FacetConfig`), without Basilisk.

:func:`box_facets` builds the usual first model of a spacecraft: the six
faces of its box-shaped bus, centred on the body origin B (the hub's
centre of mass), plus an optional flat solar array as two facets, front
and back. The optical coefficients are those of Basilisk's own
``examples/scenarioSepMomentumManagement.py``: blanketed bus faces, and an
array whose cell side reflects less than its back.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from ..schema.scenario import FacetConfig

# [-] (specular, diffuse) reflection fractions, as in Basilisk's
# examples/scenarioSepMomentumManagement.py
BUS_OPTICS = (0.336, 0.139)
ARRAY_FRONT_OPTICS = (0.16, 0.16)
ARRAY_BACK_OPTICS = (0.0, 0.56)
DRAG_COEFF = 2.2  # [-] free-molecular flat plate, the usual LEO value


def box_facets(size_m: Sequence[float], array_area_m2: float = 0.0,
               array_normal_b: Sequence[float] = (0.0, 0.0, 1.0),
               array_location_b: Optional[Sequence[float]] = None,
               drag_coeff: float = DRAG_COEFF) -> List[FacetConfig]:
    """The six faces of a ``size_m`` = (x, y, z) [m] box centred on B,
    plus, if ``array_area_m2`` > 0, a solar array at ``array_location_b``
    [m] facing ``array_normal_b`` (default: centred on the +Z face, so it
    adds no torque). An array off to one side is what makes solar pressure
    torque a Sun-pointing spacecraft. Every facet gets ``drag_coeff`` [-]."""
    x, y, z = (float(v) for v in size_m)
    faces = [
        ("+x", y * z, [1.0, 0.0, 0.0], [x / 2, 0.0, 0.0]),
        ("-x", y * z, [-1.0, 0.0, 0.0], [-x / 2, 0.0, 0.0]),
        ("+y", x * z, [0.0, 1.0, 0.0], [0.0, y / 2, 0.0]),
        ("-y", x * z, [0.0, -1.0, 0.0], [0.0, -y / 2, 0.0]),
        ("+z", x * y, [0.0, 0.0, 1.0], [0.0, 0.0, z / 2]),
        ("-z", x * y, [0.0, 0.0, -1.0], [0.0, 0.0, -z / 2]),
    ]
    facets = [FacetConfig(name=f"bus {name}", area_m2=round(area, 4), normal_b=normal, location_b=location,
                          drag_coeff=drag_coeff, specular_coeff=BUS_OPTICS[0], diffuse_coeff=BUS_OPTICS[1])
              for name, area, normal, location in faces]
    if array_area_m2 > 0.0:
        normal = [float(v) for v in array_normal_b]
        location = [float(v) for v in array_location_b] if array_location_b is not None else [0.0, 0.0, z / 2]
        for name, sign, optics in (("array front", 1.0, ARRAY_FRONT_OPTICS), ("array back", -1.0, ARRAY_BACK_OPTICS)):
            facets.append(FacetConfig(name=name, area_m2=float(array_area_m2), normal_b=[sign * v for v in normal],
                                      location_b=list(location), drag_coeff=drag_coeff,
                                      specular_coeff=optics[0], diffuse_coeff=optics[1]))
    return facets
