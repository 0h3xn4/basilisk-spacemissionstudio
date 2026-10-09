"""SpaceMissionStudio: a standalone, GUI-based mission-analysis application built
on the Basilisk astrodynamics framework (AVS Lab, University of Colorado
Boulder) as its sole simulation/dynamics engine.

This package is the ``spacemissionstudio`` backend: the GUI-agnostic service
layer, scenario schema, and supporting engine modules (time system, SPICE
kernel management, space weather, results). See ``SpaceMissionStudio/README.md``
for the phased roadmap and what is/isn't implemented yet.
"""

__version__ = "2.0.0"

# Before anything imports Basilisk: keep its import-time GitHub request local (F-16).
from . import _offline  # noqa: E402

_offline.install()
