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

"""The byte stream under the SIL contract (``SIL_CONTRACT.md`` section 2).

:class:`Transport` is all :mod:`.session` uses: send bytes, receive an
exact number of bytes within a time limit, close. :class:`Listener` makes
the socket kind the contract names: a Unix-domain socket in a private
folder on Linux and macOS, TCP on 127.0.0.1 on Windows (or when asked).
A serial or UDP link would be another :class:`Transport`.
"""

from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional

from .contract import SilError

# sockaddr_un.sun_path holds 108 bytes on Linux, 104 on macOS.
_MAX_UNIX_PATH = 100


class SilTimeout(SilError):
    """Nothing (or not enough) arrived in time."""


class SilLinkClosed(SilError):
    """The other side closed the link or it failed."""


class Transport(ABC):
    """A reliable, ordered byte stream."""

    @abstractmethod
    def send(self, data: bytes) -> None:
        """Sends every byte, or raises :class:`SilLinkClosed`."""

    @abstractmethod
    def receive(self, size: int, timeout_s: Optional[float]) -> bytes:
        """Exactly ``size`` bytes. Raises :class:`SilTimeout` when they have
        not all arrived within ``timeout_s`` (``None``: wait for ever); the
        bytes that did arrive are kept for the next call. Raises
        :class:`SilLinkClosed` when the link closes."""

    @abstractmethod
    def close(self) -> None:
        """Closes the link (twice is harmless)."""


class SocketTransport(Transport):
    """A connected stream socket."""

    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._pending = bytearray()
        if sock.family == socket.AF_INET:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def send(self, data: bytes) -> None:
        try:
            self._sock.settimeout(None)
            self._sock.sendall(data)
        except OSError as exc:
            raise SilLinkClosed(f"the link to the flight software failed while sending ({exc})") from None

    def receive(self, size: int, timeout_s: Optional[float]) -> bytes:
        end = None if timeout_s is None else time.monotonic() + max(0.0, timeout_s)
        while len(self._pending) < size:
            remaining = None if end is None else end - time.monotonic()
            if remaining is not None and remaining <= 0.0:
                raise SilTimeout(f"waited {timeout_s:.3g} s")
            try:
                self._sock.settimeout(remaining)
                chunk = self._sock.recv(max(65536, size - len(self._pending)))
            except socket.timeout:
                raise SilTimeout(f"waited {timeout_s:.3g} s") from None
            except OSError as exc:
                raise SilLinkClosed(f"the link to the flight software failed ({exc})") from None
            if not chunk:
                raise SilLinkClosed("the flight software closed the link")
            self._pending += chunk
        data = bytes(self._pending[:size])
        del self._pending[:size]
        return data

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


class Listener:
    """Where the flight software connects. ``kind`` is ``"unix"``,
    ``"tcp"`` or ``"auto"`` (Unix-domain where there is one, else TCP)."""

    def __init__(self, kind: str = "auto"):
        if kind == "auto":
            kind = "tcp" if sys.platform == "win32" or not hasattr(socket, "AF_UNIX") else "unix"
        self.kind = kind
        self._folder: Optional[Path] = None
        if kind == "unix":
            self._folder = Path(tempfile.mkdtemp(prefix="sms-sil-"))  # mode 0700
            path = self._folder / "fsw.sock"
            if len(str(path)) > _MAX_UNIX_PATH:
                shutil.rmtree(self._folder, ignore_errors=True)
                self._folder = Path(tempfile.mkdtemp(prefix="sms-sil-", dir="/tmp"))
                path = self._folder / "fsw.sock"
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.bind(str(path))
            os.chmod(path, 0o600)
            self.address = f"unix:{path}"
        elif kind == "tcp":
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.bind(("127.0.0.1", 0))
            self.address = f"tcp:127.0.0.1:{self._sock.getsockname()[1]}"
        else:
            raise ValueError(f"unknown transport kind {kind!r}")
        self._sock.listen(1)

    def accept(self, timeout_s: float, gone: Callable[[], Optional[str]] = lambda: None) -> SocketTransport:
        """The first connection within ``timeout_s``. ``gone()`` is asked
        between waits; a reason from it (the program exited) ends the wait."""
        end = time.monotonic() + timeout_s
        while True:
            reason = gone()
            if reason:
                raise SilLinkClosed(reason)
            remaining = end - time.monotonic()
            if remaining <= 0.0:
                raise SilTimeout(f"the flight software did not connect within {timeout_s:.3g} s")
            self._sock.settimeout(min(0.1, remaining))
            try:
                connection, _ = self._sock.accept()
            except socket.timeout:
                continue
            return SocketTransport(connection)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass
        if self._folder is not None:
            shutil.rmtree(self._folder, ignore_errors=True)
            self._folder = None
