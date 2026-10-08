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

"""FlowLayout: lays widgets out left to right and wraps onto new lines,
like text -- for rows of chips that must fit a narrow pane (Qt has no
built-in one; this follows Qt's own "Flow Layout" example)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QWidgetItem


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self._items: list = []
        self._spacing = spacing  # [px]
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802 -- Qt API name
        self._items.append(item)

    def addWidget(self, widget) -> None:  # noqa: N802 -- Qt API name
        self.addChildWidget(widget)
        self.addItem(QWidgetItem(widget))

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802 -- Qt API name
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802 -- Qt API name
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802 -- Qt API name
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 -- Qt API name
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 -- Qt API name
        return self._do_layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect) -> None:  # noqa: N802 -- Qt API name
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802 -- Qt API name
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 -- Qt API name
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _do_layout(self, rect, apply: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, line_height = area.x(), area.y(), 0
        for item in self._items:
            if item.widget() is not None and not item.widget().isVisible() and item.widget().isHidden():
                continue
            hint = item.sizeHint()
            if x > area.x() and x + hint.width() > area.right() + 1:
                x, y = area.x(), y + line_height + self._spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()
