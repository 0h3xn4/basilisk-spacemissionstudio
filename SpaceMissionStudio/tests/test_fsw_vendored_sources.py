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

"""The vendored Basilisk flight-software sources (SRS-F-18): Basilisk's
own bytes, from the revision the pinned wheel was built from, and enough
of them to build every exportable module."""

import re
import subprocess
import zipfile
from pathlib import Path

import pytest

from spacemissionstudio.fsw_export import catalog, sources

_REPO = Path(__file__).resolve().parents[2]


def test_every_vendored_file_has_its_basilisk_git_blob_hash():
    """Each file's recomputed git blob hash matches the manifest, and the
    zip holds nothing the manifest does not list."""
    verified = sources.verify_all()
    assert verified == sources.manifest()["files"]
    assert sources.manifest()["basilisk_revision"] == catalog.BASILISK_REVISION
    assert sources.manifest()["basilisk_version"] == catalog.BASILISK_VERSION


def test_a_changed_file_is_refused(tmp_path, monkeypatch):
    """One changed byte in the zip and the reader refuses that file."""
    original = sources.ARCHIVE.read_bytes()
    target = "fswAlgorithms/attControl/mrpFeedback/mrpFeedback.c"
    changed = tmp_path / "changed.zip"
    with zipfile.ZipFile(sources.ARCHIVE) as source, zipfile.ZipFile(changed, "w") as out:
        for info in source.infolist():
            data = source.read(info)
            out.writestr(info, data.replace(b"K", b"k", 1) if info.filename == target else data)
    assert changed.read_bytes() != original
    monkeypatch.setattr(sources, "ARCHIVE", changed)
    sources.read.cache_clear()
    try:
        with pytest.raises(sources.VendoredSourceError, match="differs from Basilisk 611665f74"):
            sources.read(target)
        assert sources.read("fswAlgorithms/attGuidance/inertial3D/inertial3D.c")  # the others still read
    finally:
        sources.read.cache_clear()


def test_every_module_and_include_is_present():
    """Every catalogued module's header and source are vendored, and every
    quoted include in the vendored C resolves inside them (or is a
    standard header, or the generated message interface)."""
    vendored = set(sources.paths())
    for module in catalog.MODULES.values():
        assert {module.header, module.source} <= vendored, module.python_name
    for path in vendored:
        if not path.endswith((".c", ".h")):
            continue
        for include in re.findall(r'^\s*#\s*include\s+"([^"]+)"', sources.read_text(path), re.M):
            if include.startswith("cMsgCInterface/"):
                payload = include.split("/")[1].replace("Msg_C.h", "MsgPayload.h")
                assert f"architecture/msgPayloadDefC/{payload}" in vendored, (path, include)
            elif include not in {"math.h", "string.h", "stdio.h", "stdlib.h"}:
                local = f"{path.rsplit('/', 1)[0]}/{include}"
                assert include in vendored or local in vendored, (path, include)
    assert "LICENSE" in vendored and "ISC" in sources.read_text("LICENSE")


def test_the_manifest_matches_the_basilisk_tag_when_its_objects_are_here():
    """In a Basilisk clone that has the v2.12.0 objects, the manifest's
    hashes are the tree's own. CI's shallow checkouts do not have them;
    the hash test above still holds there."""
    try:
        listing = subprocess.run(["git", "-C", str(_REPO), "ls-tree", "-r", catalog.BASILISK_REVISION, "src"],  # noqa: S603,S607
                                 check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip(f"this checkout does not have Basilisk {catalog.BASILISK_REVISION[:9]}'s objects")
    tree = {line.split("\t")[1][len("src/"):]: line.split()[2] for line in listing.splitlines()}
    for path, blob in sources.manifest()["files"].items():
        if path != "LICENSE":
            assert tree[path] == blob, path
