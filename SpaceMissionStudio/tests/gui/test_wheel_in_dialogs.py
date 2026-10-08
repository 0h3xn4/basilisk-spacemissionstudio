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

"""The mouse wheel changes nothing in any dialog (real user feedback:
"Don't allow scrolling to change the values in any boxes").

This opens every dialog, visits every tab with every optional group on,
and wheels over every visible spin box, drop-down and tab bar: no value,
selection or tab may change. A widget created as a plain QComboBox/
QSpinBox instead of the no-wheel classes in gui.widgets fails here.
"""

import pytest
import shiboken6

from test_input_borders import _CASES, _expand_everything

pytestmark = pytest.mark.requires_gui


def _wheel(qapp, target, up):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    delta = QPoint(0, 120 if up else -120)
    event = QWheelEvent(QPointF(4, 4), QPointF(target.mapToGlobal(QPoint(4, 4))), QPoint(0, 0), delta,
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    qapp.sendEvent(target, event)


def _state(widget):
    from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QTabBar

    if isinstance(widget, QComboBox):
        return (widget.currentIndex(), widget.currentText())
    if isinstance(widget, QTabBar):
        return widget.currentIndex()
    if isinstance(widget, QAbstractSpinBox):
        return widget.text()
    return None


def _changed_by_wheel(root, qapp):
    from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QTabBar

    changed, count = [], 0
    targets = [w for cls in (QAbstractSpinBox, QComboBox, QTabBar) for w in root.findChildren(cls)]
    for widget in targets:
        # A widget can be deleted by Qt mid-loop (e.g. a pane rebuilt
        # after a tab switch); its Python wrapper then points at freed
        # memory.
        if not shiboken6.isValid(widget) or not widget.isVisible() or not widget.isEnabled():
            continue
        count += 1
        before = _state(widget)
        # Checked after EVERY step: up-then-down could otherwise land back
        # where it started (e.g. a drop-down already on its last item).
        for up in (True, False, False, True):
            targets_now = [widget]
            if isinstance(widget, QAbstractSpinBox) and widget.lineEdit() is not None:
                targets_now.append(widget.lineEdit())
            for target in targets_now:
                _wheel(qapp, target, up)
                qapp.processEvents()
                if shiboken6.isValid(widget) and _state(widget) != before:
                    changed.append(f"{type(widget).__name__} {widget.toolTip()[:40]!r}: "
                                   f"{before!r} -> {_state(widget)!r}")
                    break
            else:
                continue
            break
    return changed, count


# The Vizard dialog has only text fields: nothing the wheel could change.
_WHEEL_CASES = [(name, factory) for name, factory in _CASES if name != "vizard"]


@pytest.mark.parametrize("factory", [f for _, f in _WHEEL_CASES], ids=[name for name, _ in _WHEEL_CASES])
def test_mouse_wheel_changes_nothing(qtbot, qapp, factory):
    dialog = factory()
    qtbot.addWidget(dialog)
    dialog.resize(max(dialog.width(), 1000), max(dialog.height(), 800))  # [px]
    dialog.show()
    qtbot.waitExposed(dialog)
    changed, count = _changed_by_wheel(dialog, qapp)
    for tabs in _expand_everything(dialog, qapp):
        for index in range(tabs.count()):
            tabs.setCurrentIndex(index)
            qapp.processEvents()
            more, more_count = _changed_by_wheel(dialog, qapp)
            changed += [f"[{tabs.tabText(index)}] {item}" for item in more]
            count += more_count
    assert count > 0, "nothing to wheel over -- the check would pass vacuously"
    assert not changed, "the wheel changed:\n" + "\n".join(changed)
