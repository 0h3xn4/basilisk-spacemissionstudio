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

"""Small reusable input widgets shared by the GUI's editor dialogs.

:class:`PreciseDoubleSpinBox` exists because a plain ``QDoubleSpinBox``
silently ROUNDS every value to its display ``decimals()`` the moment the
value is set -- so merely opening an editor on an existing scenario and
clicking OK, with zero edits, rewrote its data. Found by round-tripping
every bundled template through every editor dialog: e.g. template 13's
0.00667 kg*m^2 CubeSat inertia came back as 0.007 (a 5% change), and a
2-hour duration of 0.08333 days came back as 0.0833.
"""

from __future__ import annotations

import math

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox, QWidget

# Internal storage precision -- far finer than any field here needs, but
# still well inside a double's ~15-16 significant digits for the value
# ranges these editors use.
_STORAGE_DECIMALS = 10

# Text that is a valid PREFIX of a number while the user is still typing.
_PARTIAL_NUMBERS = {"", "-", "+", ".", "-.", "+."}


class PreciseDoubleSpinBox(QDoubleSpinBox):
    """A ``QDoubleSpinBox`` that stores values at full precision.

    :meth:`setDecimals` sets the MINIMUM number of decimals shown (e.g.
    ``3`` shows ``500.000``) rather than the precision values are rounded
    to; a value with more significant decimals than that shows them, so
    what is displayed is always what will be saved. Always uses ``.`` as
    the decimal point (a typed ``,`` is accepted too), matching every
    other number this app prints, rather than following the system locale.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._display_decimals = 2
        super().setDecimals(_STORAGE_DECIMALS)

    def setDecimals(self, prec: int) -> None:  # noqa: N802 -- Qt API name
        self._display_decimals = max(0, int(prec))
        self.update()  # re-render the current value with the new minimum

    def decimals(self) -> int:
        return self._display_decimals

    def textFromValue(self, value: float) -> str:  # noqa: N802 -- Qt override
        text = f"{value:.{_STORAGE_DECIMALS}f}"
        whole, _, fraction = text.partition(".")
        fraction = fraction.rstrip("0").ljust(self._display_decimals, "0")
        return f"{whole}.{fraction}" if fraction else whole

    def _number_part(self, text: str) -> str:
        text = text.strip()
        if self.prefix() and text.startswith(self.prefix()):
            text = text[len(self.prefix()):]
        if self.suffix() and text.endswith(self.suffix()):
            text = text[:-len(self.suffix())]
        return text.strip().replace(",", ".")

    def valueFromText(self, text: str) -> float:  # noqa: N802 -- Qt override
        try:
            return float(self._number_part(text))
        except ValueError:
            return self.value()

    def validate(self, text: str, pos: int):
        number = self._number_part(text)
        if number in _PARTIAL_NUMBERS:
            return QValidator.State.Intermediate, text, pos
        try:
            value = float(number)
        except ValueError:
            return QValidator.State.Invalid, text, pos
        if not math.isfinite(value):
            return QValidator.State.Invalid, text, pos
        if self.minimum() <= value <= self.maximum():
            return QValidator.State.Acceptable, text, pos
        return QValidator.State.Intermediate, text, pos


def exact_number_text(value: float) -> str:
    """Shortest text that parses back to exactly ``value`` (``repr``-based),
    minus a redundant trailing ``.0`` -- for numbers edited as free text
    (e.g. a comma-separated list), where ``f"{value:g}"`` keeps only 6
    significant digits and so silently changed the data on a round trip.
    """
    text = repr(float(value))
    return text[:-2] if text.endswith(".0") else text
