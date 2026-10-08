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
"""GUI-test-only fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _join_qthreads_started_by_the_test(monkeypatch):
    """Joins every ``QThread`` a test started before that test's objects are
    torn down.

    Background workers emit their terminal signal from inside ``run()``, so
    a test that waits only for that signal can end while the thread is
    still returning -- and garbage-collecting a still-running ``QThread``
    makes Qt abort the WHOLE test process ("QThread: Destroyed while thread
    is still running"). Looping the GUI suite hit exactly that in about one
    run in three before this fixture existed.
    """
    try:
        from PySide6.QtCore import QThread
    except ImportError:  # no PySide6: these tests are skipped via requires_gui anyway
        yield
        return

    started = []
    original_start = QThread.start

    def recording_start(self, *args, **kwargs):
        started.append(self)
        return original_start(self, *args, **kwargs)

    monkeypatch.setattr(QThread, "start", recording_start)
    yield
    for thread in started:
        try:
            thread.wait(10_000)
        except RuntimeError:  # the C++ object was already deleted, so the thread is long gone
            pass
