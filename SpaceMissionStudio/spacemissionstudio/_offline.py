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
"""Keep Basilisk's import-time GitHub request on this computer (finding F-16).

Basilisk 2.12.0's ``Basilisk.utilities.supportDataTools.dataFetcher``
sends ``requests.head("https://github.com/AVSLab/basilisk/releases/tag/<version>",
timeout=1)`` when it is imported, to choose the URL its downloads use.
Every simulation imports it (through ``simIncludeGravBody``), so every
run would contact github.com, before and without any consent. The tool
must use no network unless the user starts a download (UX/UI guidelines,
"offline and closed operation"; decision of 2026-10-09).

Basilisk is not changed or patched. :func:`install` adds an import hook
that, only while that one module is first executed, points the HTTPS and
HTTP proxy settings at a closed port on this computer and clears
``NO_PROXY``. The request then fails at once, locally: no name lookup,
nothing leaves the machine. Basilisk takes the failure as "tag not
found", as it does on any offline machine, and uses its ``develop``
download URL; the tool downloads nothing from that URL without the
user's consent. The previous proxy settings are restored afterwards.
"""

from __future__ import annotations

import contextlib
import importlib.abc
import os
import socket
import sys

DATA_FETCHER = "Basilisk.utilities.supportDataTools.dataFetcher"
_PROXY_VARIABLES = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy",
                    "NO_PROXY", "no_proxy")


def _closed_local_port() -> int:
    """A port on 127.0.0.1 that nothing listens on (bound, then released)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@contextlib.contextmanager
def requests_stay_local():
    """While active, ``requests`` and ``urllib`` send every HTTP(S) request
    to a closed local port instead of the network."""
    saved = {name: os.environ.get(name) for name in _PROXY_VARIABLES}
    proxy = f"http://127.0.0.1:{_closed_local_port()}"
    try:
        for name in _PROXY_VARIABLES:
            os.environ.pop(name, None)
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["HTTP_PROXY"] = proxy
        yield proxy
    finally:
        for name in _PROXY_VARIABLES:
            os.environ.pop(name, None)
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value


class _ContainedLoader(importlib.abc.Loader):
    """Runs the wrapped loader inside :func:`requests_stay_local`."""

    def __init__(self, loader):
        self._loader = loader

    def create_module(self, spec):
        return self._loader.create_module(spec)

    def exec_module(self, module):
        with requests_stay_local():
            self._loader.exec_module(module)


class _ContainingFinder(importlib.abc.MetaPathFinder):
    """Finds :data:`DATA_FETCHER` with the other finders and wraps its loader."""

    def find_spec(self, fullname, path, target=None):
        if fullname != DATA_FETCHER:
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(fullname, path, target)
            if spec is not None and spec.loader is not None:
                spec.loader = _ContainedLoader(spec.loader)
                return spec
        return None


def install() -> bool:
    """Install the hook once. False when the module was already imported
    (then its request has already been made and cannot be contained)."""
    if DATA_FETCHER in sys.modules:
        return False
    if not any(isinstance(finder, _ContainingFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _ContainingFinder())
    return True
