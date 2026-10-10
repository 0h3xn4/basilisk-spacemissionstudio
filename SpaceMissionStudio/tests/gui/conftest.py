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

# Which phase of a test is running: "setup", "call", "teardown" or None.
_PHASE = {"name": None}


class UnexpectedDialog(AssertionError):
    """A modal dialog opened that the test did not replace: under the
    offscreen platform nobody could ever answer it."""


def _phase_wrapper(name):
    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def wrapper(item):
        _PHASE["name"] = name
        try:
            return (yield)
        finally:
            _PHASE["name"] = None

    return wrapper


pytest_runtest_setup = _phase_wrapper("setup")
pytest_runtest_call = _phase_wrapper("call")
pytest_runtest_teardown = _phase_wrapper("teardown")


def _dialog_text(args, kwargs):
    words = [a for a in args if isinstance(a, str)] + [v for v in kwargs.values() if isinstance(v, str)]
    return " / ".join(repr(w[:80]) for w in words[:2]) or "(no title)"


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch):
    """Under the offscreen platform a modal dialog nobody answers blocks for
    ever: a GUI test that opened one hung the whole suite instead of
    failing (a failing test that left the main window with unsaved
    changes hung at its "Unsaved changes" prompt when the window closed).

    Every modal entry point the GUI uses (QMessageBox's static functions,
    QFileDialog's getters, ``QDialog.exec`` and ``QMenu.exec``) is replaced
    for the test. During setup and the test itself, one the test did not
    replace raises :class:`UnexpectedDialog` naming the dialog, so the test
    fails (pytest-qt reports an exception raised inside a Qt slot too).
    While the test's widgets are closed afterwards it answers at once
    instead: the message box's default button, a rejected dialog, no file.
    A test that drives a dialog replaces it with its own monkeypatch, which
    takes precedence for that test.
    """
    try:
        from PySide6.QtWidgets import QDialog, QFileDialog, QMenu, QMessageBox
    except ImportError:  # no PySide6: these tests are skipped via requires_gui anyway
        yield
        return

    def guard(kind, quiet_answer):
        def blocked(*args, **kwargs):
            if _PHASE["name"] != "teardown":
                raise UnexpectedDialog(f"unexpected modal dialog {kind}: {_dialog_text(args, kwargs)}; replace it in "
                                       "the test (monkeypatch) -- offscreen, nobody can answer it")
            return quiet_answer(args, kwargs)

        return blocked

    def default_button(args, kwargs):
        if "defaultButton" in kwargs:
            return kwargs["defaultButton"]
        return args[4] if len(args) > 4 else QMessageBox.StandardButton.NoButton

    for name in ("question", "information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(guard(f"QMessageBox.{name}", default_button)))
    monkeypatch.setattr(QMessageBox, "about", staticmethod(guard("QMessageBox.about", lambda a, k: None)))
    for name, answer in (("getOpenFileName", ("", "")), ("getSaveFileName", ("", "")),
                         ("getOpenFileNames", ([], "")), ("getExistingDirectory", "")):
        monkeypatch.setattr(QFileDialog, name, staticmethod(guard(f"QFileDialog.{name}", lambda a, k, r=answer: r)))
    monkeypatch.setattr(QDialog, "exec", guard("exec() of a dialog", lambda a, k: QDialog.DialogCode.Rejected))
    monkeypatch.setattr(QMenu, "exec", guard("QMenu.exec()", lambda a, k: None))
    yield


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
