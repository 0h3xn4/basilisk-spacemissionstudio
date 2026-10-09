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
SPICE kernel / support-data management: a thin, GUI-facing wrapper over
Basilisk's own versioned fetch/cache
(``Basilisk.utilities.supportDataTools.dataFetcher``, which fetches via
``pooch`` and caches locally -- this is real, native Basilisk
infrastructure, not something this module reimplements), adding a status
report so the app is never silently trusting a file the user can't see
or verify.

**Closed-off/offline policy**: SpaceMissionStudio itself must never touch
the network except during installation (real user requirement -- "the
app must be completely closed off and offline, only exception is the
installation process"). Every ``packaging/`` installer
(``install.sh``/``install.ps1``/``deb/DEBIAN/postinst``/
``windows/bootstrap_env.ps1``) now calls :func:`require_kernels` with NO
arguments right after installing Basilisk -- its default,
:data:`ALL_SUPPORT_DATA_FILES`, covers every ``dataFetcher``-backed file
ANY of this app's own code paths read (confirmed by grepping every
``get_path()``/``DataFile.`` call site in ``engine/``/``gui/``: the four
SPICE ephemeris kernels :func:`build_spice_interface` needs, plus
``LocalGravData.GGM03S`` -- spherical-harmonics gravity, ``engine.service``
-- and ``MagneticFieldData.WMM`` -- magnetometer sensors,
``engine.fsw.build_magnetic_field_wmm``), so that first (and only) fetch
warms Basilisk's own local ``pooch`` cache for good: every later
``get_path()`` call, for the rest of this install's lifetime, resolves
from that cache with no network touched at all (``pooch``'s own fetch
-from-cache behavior, not something this module reimplements). This
module's own :func:`build_spice_interface`/:func:`require_kernels` calls
therefore run ONLY against an already-warm cache in normal operation --
if one of them still needs the network (a missing/corrupted cache entry),
that is treated as a configuration problem to fix by re-running the
installer, not a background feature this app silently falls back on; see
:class:`KernelError`'s own message for exactly that. Runs use
:func:`cached_path`/:func:`require_cached`, which never download
(review_log F-17); Basilisk's ``get_path`` would.

Requires a Basilisk build (imports ``Basilisk.utilities...``). Written
directly against the verified ``dataFetcher``/``spiceKernels``/
``simIncludeGravBody`` source in this checkout (not from memory).

Verification status: this module's CODE PATHS (the ``ensure_kernels``/
``require_kernels``/``build_spice_interface`` call sequence, and the clear
``KernelError`` it raises on failure) were exercised for real against a
genuine Basilisk build (``pip install "bsk[all]"`` -- see
``SpaceMissionStudio/README.md``'s "Getting started" section), and behaved
exactly as designed. The actual KERNEL DOWNLOAD could not be completed in
that same environment: its network egress to ``naif.jpl.nasa.gov`` (and
the ``hanspeterschaub.info`` backup mirror ``dataFetcher`` itself falls
back to) was blocked, so every kernel fetch failed there -- correctly
surfaced as a specific ``KernelError`` naming each kernel and the
underlying network error, never a silent hang or a bare traceback. On a
machine with ordinary internet access this same code should fetch and
cache the kernels normally; that path specifically (the download
succeeding) remains unverified.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from Basilisk.utilities.supportDataTools import dataFetcher
from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

# Matches Basilisk's own default kernel set exactly -- see
# utilities/supportDataTools/spiceKernels.py's DEFAULT_KERNELS and
# simIncludeGravBody.gravBodyFactory.createSpiceInterface()'s own default
# spiceKernelFileNames. Kept as a separate constant here (rather than
# importing spiceKernels.DEFAULT_KERNELS) only so this module's own default
# is explicit and independently readable; the values are identical.
DEFAULT_KERNELS: tuple = (
    DataFile.EphemerisData.naif0012,       # leap-second kernel (LSK)
    DataFile.EphemerisData.de430,          # planetary ephemeris (SPK)
    DataFile.EphemerisData.de_403_masses,  # body GM/masses (PCK)
    DataFile.EphemerisData.pck00010,       # planet shape/orientation (PCK)
)

# Every ``dataFetcher``-backed support-data file ANY of this app's own
# code reads (confirmed by grepping every get_path()/DataFile. call site
# under engine/ and gui/) -- DEFAULT_KERNELS (above) is the narrower,
# SPICE-only subset :func:`build_spice_interface` actually passes to
# ``createSpiceInterface()`` (which only accepts real SPICE kernel
# filenames, not GGM03S.txt/WMM2025.COF). This broader set is what
# :func:`ensure_kernels`/:func:`require_kernels` default to instead --
# see this module's own docstring, "Closed-off/offline policy", for why
# a single pre-fetch of exactly this set (done once, by every
# packaging/ installer) is what lets the rest of this app run with zero
# network access afterward.
ALL_SUPPORT_DATA_FILES: tuple = DEFAULT_KERNELS + (
    DataFile.LocalGravData.GGM03S,     # spherical-harmonics gravity (engine.service)
    DataFile.MagneticFieldData.WMM,    # magnetometer sensors (engine.fsw.build_magnetic_field_wmm)
)


class KernelError(Exception):
    """Raised when a required kernel could not be fetched -- carries the
    specific kernel name(s) and underlying error, never a bare Basilisk
    traceback from deep inside SPICE.
    """


@dataclass
class KernelStatus:
    name: str  # enum member name, e.g. "naif0012"
    filename: str  # e.g. "naif0012.tls"
    path: Optional[Path]
    available: bool
    error: Optional[str]
    modified_utc: Optional[str]  # local cached file's mtime, ISO 8601 -- a
    # proxy for "how current is this cached copy". Surfaced explicitly
    # rather than trusted forever: a leap-second kernel in particular needs
    # periodic refresh as new leap seconds are announced (roughly every
    # few years), and this app must not hide that from the user.


def ensure_kernels(kernels: Iterable = ALL_SUPPORT_DATA_FILES) -> List[KernelStatus]:
    """Ensure every kernel in ``kernels`` is fetched/cached (triggering a
    download through Basilisk's own ``pooch``-backed fetch if not already
    cached) and return a status report for each. The GUI/CLI call this to
    show kernel state (and surface any fetch failure) BEFORE a run, rather
    than the run failing deep inside SPICE with a less actionable error.

    Defaults to :data:`ALL_SUPPORT_DATA_FILES` (every support-data file
    this app's own code might need), not just the narrower SPICE-only
    :data:`DEFAULT_KERNELS` -- every ``packaging/`` installer calls this
    (via :func:`require_kernels`) with no arguments as its ONE allowed
    network touch, so the default here is what actually gets pre-fetched;
    see this module's own docstring.
    """
    statuses = []
    for kernel in kernels:
        try:
            path = get_path(kernel)
            modified_utc = (
                datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
                if path.exists() else None
            )
            statuses.append(KernelStatus(kernel.name, kernel.value, path, True, None, modified_utc))
        except Exception as exc:  # deliberately broad: report ANY fetch failure, not just FileNotFoundError
            statuses.append(KernelStatus(kernel.name, kernel.value, None, False, str(exc), None))
    return statuses


def cached_path(kernel) -> Path:
    """Local path of a support-data file, without ever downloading it.

    Basilisk's ``get_path`` downloads a file that is not in its cache;
    every run of the tool uses this instead, so a run never touches the
    network (SRS-S-01, review_log F-16). Downloads happen only where the
    user starts them (:func:`ensure_kernels`: the startup prompt, Kernel
    Status, ``spacemissionstudio kernels-status``, the installers). A file
    Basilisk's registry gives a checksum for is checked against it.

    Raises:
        KernelError: the file is not installed, or its checksum is wrong.
    """
    import pooch

    rel = dataFetcher.relpath(kernel)
    local = dataFetcher.local_support_path(rel)
    if local is not None and local.exists():
        return local
    path = Path(dataFetcher.POOCH.abspath) / rel
    if not path.is_file():
        raise KernelError(
            f"support-data file {kernel.value} is not installed ({path}). SpaceMissionStudio does not download "
            "during a run: download it from the Data tab (Download > Support data) or with `spacemissionstudio kernels-status`.")
    expected = dataFetcher.POOCH.registry.get(rel)
    if expected:
        algorithm, _, digest = expected.rpartition(":")
        if pooch.file_hash(str(path), alg=algorithm or "sha256") != digest:
            raise KernelError(f"support-data file {path} does not match its checksum ({expected}); "
                              "download it again from the Data tab")
    return path


def cached_statuses(kernels: Iterable = ALL_SUPPORT_DATA_FILES) -> List[KernelStatus]:
    """Like :func:`ensure_kernels`, but only looks at the local cache: no download."""
    statuses = []
    for kernel in kernels:
        try:
            path = cached_path(kernel)
            modified_utc = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
            statuses.append(KernelStatus(kernel.name, kernel.value, path, True, None, modified_utc))
        except KernelError as exc:
            statuses.append(KernelStatus(kernel.name, kernel.value, None, False, str(exc), None))
    return statuses


def require_cached(kernels: Iterable = ALL_SUPPORT_DATA_FILES) -> List[KernelStatus]:
    """:func:`cached_statuses`, raising :class:`KernelError` naming every missing file."""
    statuses = cached_statuses(kernels)
    failed = [s for s in statuses if not s.available]
    if failed:
        raise KernelError("; ".join(s.error for s in failed))
    return statuses


def require_kernels(kernels: Iterable = ALL_SUPPORT_DATA_FILES) -> List[KernelStatus]:
    """Like :func:`ensure_kernels`, but raises :class:`KernelError` naming
    every kernel that failed, instead of returning a status list with
    ``available=False`` entries for the caller to notice on its own.
    """
    statuses = ensure_kernels(kernels)
    failed = [s for s in statuses if not s.available]
    if failed:
        names = "; ".join(f"{s.name} ({s.error})" for s in failed)
        raise KernelError(
            f"could not fetch required support-data file(s): {names} -- SpaceMissionStudio does not access "
            "the network at runtime by design, only during installation (see packaging/README.md): these "
            "files should already have been cached then. If you're seeing this outside that installer "
            "(e.g. a dev checkout), run `spacemissionstudio kernels-status` once WITH network access to "
            "fetch them now, or restore/re-run the installer if the local cache was deleted or corrupted."
        )
    return statuses


def build_spice_interface(grav_factory, spice_time_string: str, kernels: Iterable = DEFAULT_KERNELS,
                           epoch_in_msg: bool = True):
    """Thin wrapper over ``gravBodyFactory.createSpiceInterface()``: ensures
    every requested kernel is cached first (see :func:`require_kernels`)
    and passes the resolved local cache directory straight through. Must
    be called AFTER the gravity bodies are added to ``grav_factory``
    (same ordering requirement as the method it wraps).

    Args:
        grav_factory: a ``Basilisk.utilities.simIncludeGravBody.gravBodyFactory``
            instance with its gravity bodies already created.
        spice_time_string: a SPICE-recognizable epoch string -- use
            ``engine.time_system.utc_iso_to_spice_string()`` to build one
            from the scenario's ``epoch_utc``, rather than formatting it
            ad hoc (single source of truth for time, see that module).
        kernels: which kernels to load; defaults to :data:`DEFAULT_KERNELS`.
        epoch_in_msg: forwarded to ``createSpiceInterface`` -- also
            publishes an ``EpochMsg`` other modules (e.g.
            ``spaceWeatherData``) can subscribe to.
    """
    statuses = require_cached(kernels)  # never downloads during a run (F-16)
    kernel_dir = statuses[0].path.parent
    return grav_factory.createSpiceInterface(
        path=str(kernel_dir),
        time=spice_time_string,
        spiceKernelFileNames=tuple(kernels),
        epochInMsg=epoch_in_msg,
    )
