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

"""Editor for a spacecraft's facet model
(:class:`schema.scenario.FacetConfig`): one table row per flat plate, and
a "Box + solar array..." generator (:func:`engine.facets.box_facets`) for
the usual starting point."""

from __future__ import annotations

from typing import List

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..engine.facets import box_facets
from ..schema.scenario import FacetConfig
from .widgets import PreciseDoubleSpinBox

# (header, FacetConfig attribute, vector index or None)
_COLUMNS = [
    ("Name", "name", None),
    ("Area [m^2]", "area_m2", None),
    ("Normal x", "normal_b", 0), ("Normal y", "normal_b", 1), ("Normal z", "normal_b", 2),
    ("CoP x [m]", "location_b", 0), ("CoP y [m]", "location_b", 1), ("CoP z [m]", "location_b", 2),
    ("Cd [-]", "drag_coeff", None),
    ("Specular [-]", "specular_coeff", None),
    ("Diffuse [-]", "diffuse_coeff", None),
]


def _spin(low: float, high: float, value: float, decimals: int = 3) -> PreciseDoubleSpinBox:
    box = PreciseDoubleSpinBox()
    box.setRange(low, high)
    box.setDecimals(decimals)
    box.setValue(value)
    return box


class BoxFacetDialog(QDialog):
    """Asks for a box-shaped bus and an optional flat solar array."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Box + solar array")
        layout = QVBoxLayout(self)
        hint = QLabel("Six bus faces centred on the body origin, plus a two-sided array. "
                      "Offset the array to one side to see its torque.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.size_x, self.size_y, self.size_z = (_spin(0.01, 50.0, v) for v in (1.2, 1.2, 1.5))
        form.addRow("Bus size x, y, z [m]", _row(self.size_x, self.size_y, self.size_z))
        self.array_area = _spin(0.0, 1000.0, 2.5)
        self.array_area.setToolTip("0 for no solar array")
        form.addRow("Array area [m^2]", self.array_area)
        self.normal_x, self.normal_y, self.normal_z = (_spin(-1.0, 1.0, v) for v in (0.0, 0.0, 1.0))
        form.addRow("Array normal x, y, z", _row(self.normal_x, self.normal_y, self.normal_z))
        self.loc_x, self.loc_y, self.loc_z = (_spin(-50.0, 50.0, v) for v in (0.0, 0.0, 0.75))
        form.addRow("Array centre x, y, z [m]", _row(self.loc_x, self.loc_y, self.loc_z))
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def facets(self) -> List[FacetConfig]:
        normal = [self.normal_x.value(), self.normal_y.value(), self.normal_z.value()]
        if self.array_area.value() > 0.0 and not any(normal):
            raise ValueError("The array normal must not be zero")
        return box_facets((self.size_x.value(), self.size_y.value(), self.size_z.value()),
                          self.array_area.value(), normal,
                          (self.loc_x.value(), self.loc_y.value(), self.loc_z.value()))


def _row(*widgets) -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        row.addWidget(widget)
    return holder


class FacetTableWidget(QWidget):
    """Table of facets with Add / Remove / Box + solar array... buttons."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels([header for header, _, _ in _COLUMNS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add")
        self.remove_button = QPushButton("Remove")
        self.box_button = QPushButton("Box + solar array...")
        self.box_button.setToolTip("Replace the table with a box-shaped bus and a flat solar array")
        for button in (self.add_button, self.remove_button, self.box_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.add_button.clicked.connect(self._on_add)
        self.remove_button.clicked.connect(self._on_remove)
        self.box_button.clicked.connect(self._on_box)

    def from_list(self, facets: List[FacetConfig]) -> None:
        self.table.setRowCount(0)
        for facet in facets:
            self._append(facet)

    def to_list(self) -> List[FacetConfig]:
        """Raises ValueError naming the cell when a number doesn't parse."""
        facets = []
        for row in range(self.table.rowCount()):
            values = {"normal_b": [0.0, 0.0, 0.0], "location_b": [0.0, 0.0, 0.0]}
            for column, (header, attribute, index) in enumerate(_COLUMNS):
                item = self.table.item(row, column)
                text = item.text().strip() if item is not None else ""
                if attribute == "name":
                    values["name"] = text
                    continue
                try:
                    number = float(text)
                except ValueError:
                    raise ValueError(f"Facet row {row + 1}: {header} {text!r} is not a number") from None
                if index is None:
                    values[attribute] = number
                else:
                    values[attribute][index] = number
            facets.append(FacetConfig(**values))
        return facets

    def _append(self, facet: FacetConfig) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, (_header, attribute, index) in enumerate(_COLUMNS):
            value = getattr(facet, attribute)
            if index is not None:
                value = value[index]
            text = value if isinstance(value, str) else f"{value:g}"
            self.table.setItem(row, column, QTableWidgetItem(text))

    def _on_add(self) -> None:
        existing = {self.table.item(r, 0).text() for r in range(self.table.rowCount()) if self.table.item(r, 0)}
        number = self.table.rowCount() + 1
        while f"facet-{number}" in existing:
            number += 1
        self._append(FacetConfig(name=f"facet-{number}", area_m2=1.0, normal_b=[1.0, 0.0, 0.0]))

    def _on_remove(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not rows and self.table.rowCount():
            rows = [self.table.rowCount() - 1]
        for row in rows:
            self.table.removeRow(row)

    def _on_box(self) -> None:
        dialog = BoxFacetDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.from_list(dialog.facets())
