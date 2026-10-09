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

"""The vendored Basilisk sources (``basilisk_fsw_sources.zip``), checked.

``scripts/vendor_basilisk_fsw.py`` writes the zip and its manifest from
the Basilisk revision in :mod:`.catalog`. Every read here recomputes the
entry's git blob hash (``sha1(b"blob <size>\\0" + content)``, the id git
itself gives a file) and refuses a file whose hash differs from the
manifest's, so an export can only ever contain Basilisk's own bytes.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

_HERE = Path(__file__).resolve().parent
ARCHIVE = _HERE / "basilisk_fsw_sources.zip"
MANIFEST = _HERE / "basilisk_fsw_sources.json"


class VendoredSourceError(RuntimeError):
    """A vendored file is missing or not Basilisk's."""


def git_blob_hash(content: bytes) -> str:
    """The id git gives a file with this content."""
    return hashlib.sha1(b"blob %d\0" % len(content) + content, usedforsecurity=False).hexdigest()


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads(MANIFEST.read_text())


@lru_cache(maxsize=None)
def read(path: str) -> bytes:
    """The vendored file at ``path`` (relative to Basilisk's ``src/``, or
    ``LICENSE``), after checking it against the manifest."""
    expected = manifest()["files"].get(path)
    if expected is None:
        raise VendoredSourceError(f"{path} is not among the vendored Basilisk sources")
    with zipfile.ZipFile(ARCHIVE) as archive:
        try:
            content = archive.read(path)
        except KeyError:
            raise VendoredSourceError(f"{path} is listed in {MANIFEST.name} but missing from {ARCHIVE.name}") from None
    actual = git_blob_hash(content)
    if actual != expected:
        raise VendoredSourceError(f"{path} differs from Basilisk {manifest()['basilisk_revision'][:9]}: "
                                  f"git blob {actual}, expected {expected}")
    return content


def read_text(path: str) -> str:
    return read(path).decode("utf-8")


def paths() -> List[str]:
    return sorted(manifest()["files"])


def verify_all() -> Dict[str, str]:
    """Reads (and so checks) every file; returns ``{path: blob hash}``.
    Also refuses entries the manifest does not list."""
    with zipfile.ZipFile(ARCHIVE) as archive:
        extra = sorted(set(archive.namelist()) - set(manifest()["files"]))
    if extra:
        raise VendoredSourceError(f"{ARCHIVE.name} holds files the manifest does not list: {extra}")
    return {path: git_blob_hash(read(path)) for path in paths()}
