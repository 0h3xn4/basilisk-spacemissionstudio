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
"""The user manual and the keyboard shortcuts, shown from the Help menu
without a network (UX/UI guidelines, "help and examples built in").

The manual is the copy shipped as package data (``spacemissionstudio/help/``,
kept current by ``scripts/sync_help.py``), rendered by Qt's own Markdown
support. Links inside the manual jump to their section; links to other
sites are not opened (the tool works offline) -- the address is shown
instead, for the user to open elsewhere if they wish.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QImage, QTextCursor
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem, QTextBrowser,
                               QVBoxLayout, QWidget)

HELP_DIR = Path(__file__).resolve().parent.parent / "help"
MANUAL = HELP_DIR / "USER_MANUAL.md"


def heading_slug(text: str) -> str:
    """The anchor GitHub gives a heading: lower case, punctuation dropped,
    spaces to hyphens (the manual's table of contents uses these)."""
    slug = re.sub(r"[^\w\- ]", "", text.strip().lower())
    return slug.replace(" ", "-")


class ManualDialog(QDialog):
    """The bundled user manual."""

    def __init__(self, parent: Optional[QWidget] = None, manual: Path = MANUAL):
        super().__init__(parent)
        self.setWindowTitle("SpaceMissionStudio User Manual")
        self.resize(900, 760)  # [px]
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setSearchPaths([str(manual.parent)])
        self.browser.anchorClicked.connect(self._on_link)
        self.link_note = QLabel("")
        self.link_note.setWordWrap(True)
        self.link_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.browser)
        layout.addWidget(self.link_note)
        layout.addWidget(buttons)
        try:
            self.browser.setMarkdown(manual.read_text(encoding="utf-8"))
        except OSError as exc:
            self.browser.setPlainText(f"The user manual could not be read ({exc}). It is USER_MANUAL.md in the "
                                      "SpaceMissionStudio folder of the source.")
        self._fit_images(manual.parent)
        self._anchors = self._heading_positions()

    def _fit_images(self, base: Path, max_width_px: int = 820) -> None:
        """Scale screenshots wider than ``max_width_px`` down, keeping their
        aspect, so the manual never scrolls sideways."""
        document = self.browser.document()
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isImageFormat():
                    image_format = fragment.charFormat().toImageFormat()
                    image = QImage(str(base / image_format.name()))
                    if not image.isNull() and image.width() > max_width_px:
                        image_format.setWidth(max_width_px)
                        image_format.setHeight(image.height() * max_width_px / image.width())
                        cursor = QTextCursor(document)
                        cursor.setPosition(fragment.position())
                        cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.MoveMode.KeepAnchor)
                        cursor.setCharFormat(image_format)
                iterator += 1
            block = block.next()

    def _heading_positions(self) -> Dict[str, int]:
        positions = {}
        block = self.browser.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel() > 0:
                positions.setdefault(heading_slug(block.text()), block.position())
            block = block.next()
        return positions

    def show_section(self, slug: str) -> bool:
        """Scroll to the heading with this anchor; False when there is none."""
        position = self._anchors.get(slug)
        if position is None:
            return False
        cursor = QTextCursor(self.browser.document())
        cursor.setPosition(position)
        self.browser.setTextCursor(cursor)
        bar = self.browser.verticalScrollBar()
        bar.setValue(bar.value() + self.browser.cursorRect(cursor).top())  # heading at the top
        return True

    def _on_link(self, url: QUrl) -> None:
        if url.scheme() in ("http", "https", "mailto", "ftp"):
            self.link_note.setText(f"Links to other sites are not opened (SpaceMissionStudio works offline): "
                                   f"{url.toString()}")
            return
        if url.hasFragment() and self.show_section(url.fragment()):
            self.link_note.setText("")
            return
        self.link_note.setText(f"Not found in the manual: {url.toString()}")


def shortcut_rows(actions: List[QAction]) -> List[tuple]:
    """(action, shortcut) for every action that has a keyboard shortcut."""
    rows = []
    for action in actions:
        keys = action.shortcut().toString()
        if keys:
            rows.append((action.text().replace("&", ""), keys))
    return sorted(rows)


class ShortcutsDialog(QDialog):
    """The keyboard shortcuts of the main window's actions."""

    def __init__(self, actions: List[QAction], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        rows = shortcut_rows(actions)
        self.table = QTableWidget(len(rows), 2)
        self.table.setHorizontalHeaderLabels(["Action", "Shortcut"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, (name, keys) in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(keys))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(buttons)
