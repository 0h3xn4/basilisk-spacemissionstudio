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
