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

"""The reused software this tool depends on, and the Basilisk version it is
qualified with (ECSS-Q-ST-80C 6.2.4, 6.2.7; decision D5, 2026-10-08).

Basilisk is existing (reused) software in the sense of ECSS-Q-ST-80C: the
tool is verified against one Basilisk release, :data:`QUALIFIED_BASILISK_
VERSION`, and the installers pin it. Another version still runs, but
:func:`basilisk_check` reports it at start-up and every run's provenance
records it. Importing this module does not import Basilisk.
"""

from __future__ import annotations

import hashlib
import platform
import sys
from importlib import metadata
from pathlib import Path
from typing import Dict, Optional

QUALIFIED_BASILISK_VERSION = "2.12.0"

# Distribution names of the runtime dependencies, as pip knows them.
_DEPENDENCIES = ("bsk", "numpy", "sgp4", "pyerfa", "PySide6", "plotly")

# Files above this size are recorded by size only (hashing de430.bsp,
# ~114 MB, at every run would cost more than it adds).
_HASH_LIMIT_BYTES = 32 * 1024 * 1024  # [byte]


def basilisk_version() -> Optional[str]:
    """Installed Basilisk version, or ``None`` when Basilisk is missing."""
    try:
        import Basilisk
    except ImportError:
        return None
    return str(getattr(Basilisk, "__version__", "unknown"))


def basilisk_check(version: Optional[str] = None) -> Optional[str]:
    """``None`` when the installed Basilisk is the qualified version,
    otherwise one line saying what differs."""
    version = basilisk_version() if version is None else version
    if version is None:
        return "Basilisk is not installed: simulations cannot run"
    if version != QUALIFIED_BASILISK_VERSION:
        return (f"Basilisk {version} is installed; SpaceMissionStudio is qualified with "
                f"{QUALIFIED_BASILISK_VERSION} -- results are not covered by its verification")
    return None


def dependency_versions() -> Dict[str, str]:
    """``{distribution: version}`` of the runtime dependencies that are
    installed, plus the Python version and platform."""
    versions = {"python": platform.python_version(), "platform": f"{sys.platform} {platform.machine()}"}
    for name in _DEPENDENCIES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return versions


def file_record(path) -> Dict[str, object]:
    """Path, size and (below 32 MB) SHA-256 of a reference data file."""
    path = Path(path)
    record: Dict[str, object] = {"path": str(path)}
    try:
        size = path.stat().st_size
    except OSError:
        record["missing"] = True
        return record
    record["size_bytes"] = size
    if size <= _HASH_LIMIT_BYTES:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        record["sha256"] = digest.hexdigest()
    return record
