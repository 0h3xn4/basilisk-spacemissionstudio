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
"""Tests for gui.widgets."""

import pytest

pytestmark = pytest.mark.requires_gui


def test_precise_spin_box_keeps_full_precision_beyond_its_display_decimals(qtbot):
    from spacemissionstudio.gui.widgets import PreciseDoubleSpinBox

    box = PreciseDoubleSpinBox()
    qtbot.addWidget(box)
    box.setRange(0.0, 1.0e6)  # [kg*m^2]
    box.setDecimals(3)
    box.setValue(0.0066666667)  # [kg*m^2]
    assert box.value() == pytest.approx(0.0066666667, rel=1e-12)
    assert box.cleanText() == "0.0066666667"  # shows every stored digit, never a rounded 0.007


@pytest.mark.parametrize("value", [1.18e-9, 8.0e-7, 1.0e-12, 0.1, 6.366e-4, 123456.789, -2.5e-10])
def test_precise_spin_box_stores_and_shows_values_exactly(qtbot, value):
    """Real bug: values were kept to 10 decimal places, so applying the
    MM200 magnetometer preset turned its 1.18e-9 T noise into 1.2e-9 T."""
    from spacemissionstudio.gui.widgets import PreciseDoubleSpinBox

    box = PreciseDoubleSpinBox()
    qtbot.addWidget(box)
    box.setRange(-1.0e6, 1.0e6)
    box.setDecimals(2)
    box.setValue(value)
    assert box.value() == value
    assert float(box.cleanText()) == value  # what is shown is exactly what is saved
    assert "e" not in box.cleanText().lower()


def test_precise_spin_box_pads_to_its_minimum_display_decimals(qtbot):
    from spacemissionstudio.gui.widgets import PreciseDoubleSpinBox

    box = PreciseDoubleSpinBox()
    qtbot.addWidget(box)
    box.setRange(0.0, 1.0e6)  # [km]
    box.setDecimals(3)
    box.setSuffix(" km")
    box.setValue(500.0)  # [km]
    assert box.text() == "500.000 km"
    assert box.decimals() == 3


def test_precise_spin_box_parses_typed_text_with_either_decimal_separator(qtbot):
    from spacemissionstudio.gui.widgets import PreciseDoubleSpinBox

    box = PreciseDoubleSpinBox()
    qtbot.addWidget(box)
    box.setRange(-100.0, 100.0)  # [deg]
    box.setSuffix(" deg")
    box.lineEdit().setText("12,5 deg")
    box.interpretText()
    assert box.value() == 12.5  # [deg]
    box.lineEdit().setText("-7.25")
    box.interpretText()
    assert box.value() == -7.25  # [deg]


def test_precise_spin_box_rejects_garbage_and_out_of_range_input(qtbot):
    from PySide6.QtGui import QValidator

    from spacemissionstudio.gui.widgets import PreciseDoubleSpinBox

    box = PreciseDoubleSpinBox()
    qtbot.addWidget(box)
    box.setRange(0.0, 10.0)  # [s]
    assert box.validate("abc", 3)[0] == QValidator.State.Invalid
    assert box.validate("nan", 3)[0] == QValidator.State.Invalid
    assert box.validate("-", 1)[0] == QValidator.State.Intermediate
    assert box.validate("50", 2)[0] == QValidator.State.Intermediate
    assert box.validate("5.5", 3)[0] == QValidator.State.Acceptable


@pytest.mark.parametrize("value, text", [(50.0, "50"), (83.7758040957278, "83.7758040957278"), (-0.5, "-0.5")])
def test_exact_number_text_round_trips_exactly(value, text):
    from spacemissionstudio.gui.widgets import exact_number_text

    assert exact_number_text(value) == text
    assert float(exact_number_text(value)) == value


def test_mouse_wheel_never_changes_a_value_and_scrolls_the_page(qtbot, qapp):
    """Real user feedback: "Don't allow scrolling to change the values in
    any boxes". The app's spin boxes, drop-downs and tab bars ignore the
    wheel, so it goes on to the page, which scrolls instead."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

    from spacemissionstudio.gui.widgets import ComboBox, DoubleSpinBox, PreciseDoubleSpinBox, SpinBox, TabWidget

    area = QScrollArea()
    content = QWidget()
    layout = QVBoxLayout(content)
    boxes = [PreciseDoubleSpinBox(), DoubleSpinBox(), SpinBox(), ComboBox()]
    boxes[0].setValue(5.0)
    boxes[1].setValue(5.0)
    boxes[2].setValue(5)
    boxes[3].addItems(["a", "b", "c"])
    tabs = TabWidget()
    for name in ("one", "two", "three"):
        tabs.addTab(QWidget(), name)
    for widget in boxes + [tabs]:
        layout.addWidget(widget)
    layout.addSpacing(3000)  # [px] tall enough to scroll
    area.setWidget(content)
    area.resize(300, 200)
    qtbot.addWidget(area)
    area.show()
    qtbot.waitExposed(area)

    def wheel(target):
        event = QWheelEvent(QPointF(5, 5), QPointF(target.mapToGlobal(QPoint(5, 5))), QPoint(0, 0),
                            QPoint(0, -120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        qapp.sendEvent(target, event)
        return event

    for widget in boxes + [tabs.tabBar()]:
        # Ignored, so for real (spontaneous) input Qt passes it on to the
        # parent and the page scrolls; a synthetic event is not passed on.
        assert not wheel(widget).isAccepted(), type(widget).__name__
        if not isinstance(widget, ComboBox) and hasattr(widget, "lineEdit"):
            wheel(widget.lineEdit())  # the text field inside a spin box
    assert [boxes[0].value(), boxes[1].value(), boxes[2].value()] == [5.0, 5.0, 5]
    assert boxes[3].currentIndex() == 0
    assert tabs.currentIndex() == 0
    before = area.verticalScrollBar().value()
    wheel(area.viewport())  # where an ignored event ends up
    assert area.verticalScrollBar().value() > before
    boxes[0].stepUp()  # arrows and keyboard still work
    assert boxes[0].value() == 6.0
