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

"""The Basilisk C flight-software modules the export can package.

Each entry names a module as ``engine.fsw`` builds it (the Python module
under ``Basilisk.fswAlgorithms``), where its sources sit in the Basilisk
tree, its configuration struct and the suffix of its ``SelfInit_``,
``Reset_`` and ``Update_`` functions (``tamComm``'s are
``tamProcessTelem``). These are read from the sources of
:data:`BASILISK_REVISION`, the revision the pinned Basilisk 2.12.0 wheel
records in ``Basilisk/_buildInfoData.py``.

Pure data: no Basilisk import, so the vendoring script, the generator and
the tests can all use it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

BASILISK_VERSION = "2.12.0"
BASILISK_REVISION = "611665f742999951453d4e128c8540c761de8a4f"  # the v2.12.0 tag


@dataclass(frozen=True)
class CModule:
    """One exportable Basilisk C module."""

    python_name: str  # Basilisk.fswAlgorithms.<python_name>
    source_dir: str  # relative to the Basilisk tree's src/
    file_stem: str  # <file_stem>.c / <file_stem>.h in source_dir
    config_struct: str
    function_suffix: str

    @property
    def header(self) -> str:
        return f"{self.source_dir}/{self.file_stem}.h"

    @property
    def source(self) -> str:
        return f"{self.source_dir}/{self.file_stem}.c"


_MODULES = (
    CModule("inertial3D", "fswAlgorithms/attGuidance/inertial3D", "inertial3D", "inertial3DConfig", "inertial3D"),
    CModule("hillPoint", "fswAlgorithms/attGuidance/hillPoint", "hillPoint", "hillPointConfig", "hillPoint"),
    CModule("velocityPoint", "fswAlgorithms/attGuidance/velocityPoint", "velocityPoint", "velocityPointConfig",
            "velocityPoint"),
    CModule("sunSafePoint", "fswAlgorithms/attGuidance/sunSafePoint", "sunSafePoint", "sunSafePointConfig",
            "sunSafePoint"),
    CModule("locationPointing", "fswAlgorithms/attGuidance/locationPointing", "locationPointing",
            "locationPointingConfig", "locationPointing"),
    CModule("attTrackingError", "fswAlgorithms/attGuidance/attTrackingError", "attTrackingError",
            "attTrackingErrorConfig", "attTrackingError"),
    CModule("mrpFeedback", "fswAlgorithms/attControl/mrpFeedback", "mrpFeedback", "mrpFeedbackConfig", "mrpFeedback"),
    CModule("rwMotorTorque", "fswAlgorithms/effectorInterfaces/rwMotorTorque", "rwMotorTorque", "rwMotorTorqueConfig",
            "rwMotorTorque"),
    CModule("cssWlsEst", "fswAlgorithms/attDetermination/CSSEst", "cssWlsEst", "CSSWLSConfig", "cssWlsEst"),
    CModule("tamComm", "fswAlgorithms/sensorInterfaces/TAMSensorData", "tamComm", "tamConfigData", "tamProcessTelem"),
    CModule("mtbMomentumManagement", "fswAlgorithms/attControl/mtbMomentumManagement", "mtbMomentumManagement",
            "mtbMomentumManagementConfig", "mtbMomentumManagement"),
    CModule("thrForceMapping", "fswAlgorithms/effectorInterfaces/thrForceMapping", "thrForceMapping",
            "thrForceMappingConfig", "thrForceMapping"),
    CModule("thrFiringSchmitt", "fswAlgorithms/effectorInterfaces/thrFiringSchmitt", "thrFiringSchmitt",
            "thrFiringSchmittConfig", "thrFiringSchmitt"),
    CModule("thrMomentumManagement", "fswAlgorithms/attControl/thrMomentumManagement", "thrMomentumManagement",
            "thrMomentumManagementConfig", "thrMomentumManagement"),
    CModule("thrMomentumDumping", "fswAlgorithms/effectorInterfaces/thrMomentumDumping", "thrMomentumDumping",
            "thrMomentumDumpingConfig", "thrMomentumDumping"),
)

MODULES: Dict[str, CModule] = {m.python_name: m for m in _MODULES}

# Files the generator needs besides the modules' include closures: the
# templates Basilisk's CMake fills in for the C message interface
# (architecture/messaging/cMsgCInterface/CMakeLists.txt), the message
# header they include, and Basilisk's licence.
EXTRA_FILES = (
    "architecture/messaging/cMsgCInterface/msg_C.h.in",
    "architecture/messaging/cMsgCInterface/msg_C.cpp.in",
    "architecture/messaging/msgHeader.h",
    "architecture/utilities/bskLogging.h",
    "architecture/utilities/bsk_Print.h",
)
LICENSE_FILE = "LICENSE"  # at the top of the Basilisk tree

# Flight software the tool runs that is not one of the C modules above,
# and so is not exported (listed in the ICD). Keyed by the Python class or
# module that implements it.
NOT_EXPORTED = {
    "_CommsPointingArbitrator": "comms-pointing mode switch (Python, engine.fsw)",
    "StationKeepingController": "station keeping (Python, engine.orbit_maintenance)",
    "PhasingKeepingController": "phasing keeping (Python, engine.orbit_maintenance)",
    "ConstantFrameThrustController": "constant thrust (Python, engine.orbit_maintenance)",
    "GeoStationKeepingController": "GEO station keeping (Python, engine.geo_station_keeping)",
    "FormationControlBridge": "formation control bridge (Python, engine.formation_control)",
    "_DownlinkGate": "downlink link gate (Python, engine.data_handling)",
    "_DataLedger": "data ledger (Python, engine.data_handling)",
}
