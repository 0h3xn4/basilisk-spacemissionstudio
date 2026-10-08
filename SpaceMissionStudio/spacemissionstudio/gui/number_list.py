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

"""An ordered list of numbers edited as one labelled spin box per entry.

Replaces comma-separated text fields, where the meaning of each position
was invisible (real user feedback on the spacecraft editor). Two modes:

- **fixed rows** (:meth:`NumberListEditor.set_rows`): one row per named item,
  e.g. a speed bias per reaction wheel, labelled with the wheel's name;
- **growable** (``growable=True``): numbered rows ("Stage 1", "Stage 2", ...)
  with Add and Remove buttons, always at least one row.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import PALETTE
from .widgets import PreciseDoubleSpinBox


class NumberListEditor(QWidget):
    changed = Signal()

    def __init__(self, unit: str = "", minimum: float = -1.0e9, maximum: float = 1.0e9, decimals: int = 3,
                 growable: bool = False, row_label: str = "Stage", default_value: float = 0.0,
                 empty_text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._unit = unit
        self._minimum = minimum
        self._maximum = maximum
        self._decimals = decimals
        self._growable = growable
        self._row_label = row_label
        self._default_value = default_value
        self._boxes: list[PreciseDoubleSpinBox] = []
        self._remove_buttons: list[QPushButton] = []
        self._labels: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._form = QFormLayout()
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        layout.addLayout(self._form)
        self.empty_label = QLabel(empty_text)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)
        self.add_button = QPushButton(f"Add {row_label.lower()}")
        self.add_button.setAutoDefault(False)
        self.add_button.clicked.connect(self._on_add)
        self.add_button.setVisible(growable)
        add_row = QHBoxLayout()
        add_row.addWidget(self.add_button)
        add_row.addStretch(1)
        layout.addLayout(add_row)

    # -- public API ----------------------------------------------------
    def set_values(self, values) -> None:
        """Growable mode: one numbered row per value (at least one row)."""
        values = [float(v) for v in values] or [self._default_value]
        self._rebuild([f"{self._row_label} {i + 1}" for i in range(len(values))], values)

    def set_rows(self, labels, values) -> None:
        """Fixed-row mode: one row per label. Values are matched by
        position; missing ones get the default, extra ones are dropped."""
        labels = list(labels)
        values = [float(v) for v in values][:len(labels)]
        values += [self._default_value] * (len(labels) - len(values))
        self._rebuild(labels, values)

    def values(self) -> list[float]:
        return [box.value() for box in self._boxes]

    def boxes(self) -> list[PreciseDoubleSpinBox]:
        return list(self._boxes)

    def labels(self) -> list[str]:
        return list(self._labels)

    # -- internals -----------------------------------------------------
    def _rebuild(self, labels: list[str], values: list[float]) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        self._boxes.clear()
        self._remove_buttons.clear()
        self._labels = list(labels)
        for label, value in zip(labels, values):
            box = PreciseDoubleSpinBox()
            box.setRange(self._minimum, self._maximum)
            box.setDecimals(self._decimals)
            if self._unit:
                box.setSuffix(f" {self._unit}")
            box.setFixedWidth(240)  # [px] room for a full-precision value plus its unit
            box.setValue(value)
            box.valueChanged.connect(self.changed)
            self._boxes.append(box)
            if self._growable:
                holder = QWidget()
                row = QHBoxLayout(holder)
                row.setContentsMargins(0, 0, 0, 0)
                row.addWidget(box)
                remove = QPushButton("Remove")
                remove.setAutoDefault(False)
                remove.clicked.connect(lambda _checked, b=box: self._on_remove(b))
                self._remove_buttons.append(remove)
                row.addWidget(remove)
                row.addStretch(1)
                self._form.addRow(label, holder)
            else:
                self._form.addRow(label, box)
        for button in self._remove_buttons:
            button.setEnabled(len(self._boxes) > 1)
        self.empty_label.setVisible(not self._boxes and bool(self.empty_label.text()))

    def _on_add(self) -> None:
        values = self.values()
        self.set_values(values + [values[-1] if values else self._default_value])
        self.changed.emit()

    def _on_remove(self, box) -> None:
        values = [b.value() for b in self._boxes if b is not box]
        self.set_values(values)
        self.changed.emit()
