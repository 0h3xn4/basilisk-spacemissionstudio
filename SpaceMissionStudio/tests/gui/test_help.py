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
"""The user manual and keyboard shortcuts in the Help menu, offline
(UX/UI guidelines, "help and examples built in")."""

import re
from pathlib import Path

from PySide6.QtCore import QUrl

_TOOL = Path(__file__).resolve().parents[2]


def test_the_bundled_manual_is_the_current_manual():
    """The package copy matches USER_MANUAL.md and its images (run scripts/sync_help.py after edits)."""
    from spacemissionstudio.gui.help_dialog import HELP_DIR

    text = (_TOOL / "USER_MANUAL.md").read_bytes()
    assert (HELP_DIR / "USER_MANUAL.md").read_bytes() == text
    for image in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text.decode("utf-8")):
        assert (HELP_DIR / image).read_bytes() == (_TOOL / image).read_bytes(), image


def test_every_contents_link_of_the_manual_finds_its_section(qtbot):
    """Each in-manual link (the table of contents) jumps to a heading."""
    from spacemissionstudio.gui.help_dialog import ManualDialog

    dialog = ManualDialog()
    qtbot.addWidget(dialog)
    text = (_TOOL / "USER_MANUAL.md").read_text(encoding="utf-8")
    anchors = re.findall(r"\]\(#([^)]+)\)", text)
    assert anchors
    for anchor in anchors:
        assert dialog.show_section(anchor), anchor


def test_links_to_other_sites_are_not_opened(qtbot, monkeypatch):
    """The dialog shows the address instead of opening a browser."""
    from PySide6.QtGui import QDesktopServices

    from spacemissionstudio.gui.help_dialog import ManualDialog

    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    dialog = ManualDialog()
    qtbot.addWidget(dialog)
    dialog.browser.anchorClicked.emit(QUrl("https://example.org/page"))
    assert opened == []
    assert "not opened" in dialog.link_note.text() and "example.org" in dialog.link_note.text()


def test_help_menu_offers_the_manual_on_f1_and_the_shortcuts(qtbot):
    """F1 opens the manual; the shortcut list includes Run (Ctrl+R)."""
    from spacemissionstudio.gui.help_dialog import ShortcutsDialog
    from spacemissionstudio.gui.main_window import MainWindow

    window = MainWindow(prompt_startup_fetch=False, check_autosave_recovery=False)
    qtbot.addWidget(window)
    assert window.manual_action.shortcut().toString() == "F1"
    actions = [a for m in window.menuBar().actions() if m.menu() for a in m.menu().actions()]
    dialog = ShortcutsDialog(actions, window)
    qtbot.addWidget(dialog)
    shortcuts = {dialog.table.item(r, 1).text() for r in range(dialog.table.rowCount())}
    assert "Ctrl+R" in shortcuts and "F1" in shortcuts
