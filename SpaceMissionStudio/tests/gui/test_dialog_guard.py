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

"""A GUI test that opens a modal dialog fails, naming it, instead of
hanging the suite (``tests/gui/conftest.py``, ``_no_blocking_dialogs``).

Found the hard way: a failing label test left the main window with unsaved
changes, and the whole suite hung at its "Unsaved changes" prompt when the
window closed. These tests run small test files in a separate pytest, under
a time limit, with this folder's conftest, and check that each one ends.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_gui

_HERE = Path(__file__).resolve().parent
_PROJECT = _HERE.parents[1]

_INNER = '''
import pytest


def test_a_failing_test_leaves_unsaved_changes(qtbot):
    from spacemissionstudio.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window._dirty = True  # the "Unsaved changes" prompt on close
    assert False, "deliberate failure with unsaved changes"


def test_a_slot_opens_an_unexpected_message_box(qtbot):
    from PySide6.QtWidgets import QMessageBox, QPushButton

    button = QPushButton("Run")
    qtbot.addWidget(button)
    button.clicked.connect(lambda: QMessageBox.warning(button, "Cannot run", "Fix the scenario first."))
    button.click()


def test_a_dialog_the_test_replaced_still_works(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    assert QMessageBox.question(None, "Replace?", "Replace it?") == QMessageBox.StandardButton.Yes
    assert QDialog().exec() == QDialog.DialogCode.Accepted
'''


def test_dialogs_fail_the_test_instead_of_hanging_the_suite(tmp_path):
    """Three tests in their own pytest, within 120 s: the one that fails
    with unsaved changes fails for its own reason and its window closes;
    the one whose slot opens a message box fails naming it; a test that
    replaced the dialogs drives them as before."""
    folder = tmp_path / "inner"
    folder.mkdir()
    (folder / "conftest.py").write_text((_HERE / "conftest.py").read_text())
    (folder / "test_inner.py").write_text(_INNER)
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "HOME": str(tmp_path / "home"),
           "PYTHONPATH": os.pathsep.join(filter(None, [str(_PROJECT), os.environ.get("PYTHONPATH")]))}
    done = subprocess.run([sys.executable, "-m", "pytest", str(folder), "-q", "-p", "no:cacheprovider", "-p",  # noqa: S603
                           "no:xdist", "-rf"], capture_output=True, text=True, env=env, cwd=str(tmp_path),
                          timeout=120)
    out = done.stdout + done.stderr
    assert "2 failed, 1 passed" in out, out
    assert "deliberate failure with unsaved changes" in out
    assert "unexpected modal dialog QMessageBox.warning: 'Cannot run'" in out
