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

"""A labelled form for an open ``params`` dict, driven by parameter specs.

Used by the sensor/actuator dialog and the spacecraft dialog's Attitude
control tab. Both used to show a bullet list of every key above a raw
JSON box; real user feedback called that cramped and unreadable. Here
each known parameter gets its own row:

- the label is a short name, with the unit shown in the field;
- the full description is in the tooltip;
- an optional parameter's label is a checkbox (unticked = the default is
  used and the key is left out of ``params``);
- a 3-component vector gets x/y/z boxes, plus Normalize for directions;
- keys the specs don't know stay editable in a collapsed "Advanced" JSON box.

A spec is any object with ``key``, ``required``, ``example`` and
``help_text`` attributes. It may also have ``normalizable`` (bool) and
``label`` (str) attributes.
"""

from __future__ import annotations

import json
import math
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .theme import PALETTE
from .widgets import ComboBox, PreciseDoubleSpinBox


def is_vector(spec) -> bool:
    return isinstance(spec.example, list) and len(spec.example) == 3


def short_label(spec) -> tuple[str, str]:
    """(label, unit) for a spec. The text before " -- " in the help is used.
    For example, "1-sigma gyro noise [rad/s] -- ..." gives
    ("1-sigma gyro noise", "rad/s"). A non-empty ``spec.label`` overrides
    the label text."""
    first = spec.help_text.split(" -- ")[0]
    unit = ""
    if "[" in first and "]" in first:
        unit = first[first.rfind("[") + 1:first.rfind("]")]
        first = first[:first.rfind("[")]
    text = getattr(spec, "label", "") or first.split(",")[0].strip().rstrip(":") or spec.key
    return text[:1].upper() + text[1:], ("" if unit in ("-", "") else unit)


def choices(spec) -> list[str]:
    """Quoted option names listed in a string spec's help text, e.g.
    'none' / 'stuck_current'. Empty when fewer than two are listed."""
    found = re.findall(r"'([A-Za-z0-9_]+)'", spec.help_text)
    return list(dict.fromkeys(found)) if len(found) >= 2 else []


def _component_box() -> QDoubleSpinBox:
    box = PreciseDoubleSpinBox()
    box.setRange(-1.0e6, 1.0e6)
    box.setDecimals(6)
    box.setSingleStep(0.1)
    box.setFixedWidth(130)
    return box


class ParamForm(QWidget):
    """Form rows for a list of specs, plus a collapsed JSON box for extras.

    Call :meth:`set_specs` to (re)build it. :meth:`params` returns the
    merged dict (form values win over extras with the same key).
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None, show_advanced: bool = True):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.form.setVerticalSpacing(6)
        self.form.setHorizontalSpacing(16)
        layout.addLayout(self.form)

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("Advanced: other parameters (JSON)")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.setStyleSheet("QToolButton { border: none; }")
        self.advanced_toggle.toggled.connect(self._on_advanced_toggled)
        self.advanced_toggle.setVisible(show_advanced)
        layout.addWidget(self.advanced_toggle)
        self.params_edit = QPlainTextEdit("{}")
        self.params_edit.setTabChangesFocus(True)
        self.params_edit.setPlaceholderText('Extra parameters the form above does not cover, e.g. {"key": 1.0}')
        self.params_edit.setFixedHeight(90)
        self.params_edit.setVisible(False)
        self.params_edit.textChanged.connect(self.changed)
        layout.addWidget(self.params_edit)

        self.fields: dict = {}  # key -> (spec, include checkbox or None, widget)
        self.vector_boxes: dict[str, tuple[QDoubleSpinBox, QDoubleSpinBox, QDoubleSpinBox]] = {}

    # -- building ------------------------------------------------------
    def set_specs(self, specs, params: dict, options: dict | None = None,
                  empty_text: str = "No parameters.", group_headings: bool = True) -> None:
        """Rebuild the rows.

        ``options`` maps a string key to ``(choices, editable)``. It
        overrides the choices taken from the help text, e.g. for a list of
        the scenario's ground stations.
        """
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields.clear()
        self.vector_boxes.clear()
        options = options or {}
        specs = list(specs)
        required = [spec for spec in specs if spec.required]
        optional = [spec for spec in specs if not spec.required]
        for title, group in (("Required", required), ("Optional", optional)):
            if not group:
                continue
            if group_headings and required:
                heading = QLabel(title)
                heading.setStyleSheet(f"font-weight: 600; color: {PALETTE['text_muted']}; margin-top: 4px;")
                self.form.addRow(heading)
            for spec in group:
                self._add_row(spec, params, options.get(spec.key))
        if not specs:
            empty = QLabel(empty_text)
            empty.setStyleSheet(f"color: {PALETTE['text_muted']};")
            self.form.addRow(empty)
        known = {spec.key for spec in specs}
        extras = {k: v for k, v in params.items() if k not in known}
        self.params_edit.blockSignals(True)
        self.params_edit.setPlainText(json.dumps(extras, indent=2) if extras else "{}")
        self.params_edit.blockSignals(False)
        self.advanced_toggle.setChecked(bool(extras))

    def _add_row(self, spec, params: dict, option) -> None:
        text, unit = short_label(spec)
        tooltip = f"{spec.key}: {spec.help_text}"
        widget = self._make_widget(spec, unit, option)
        self._set_value(spec, widget, params.get(spec.key, spec.example))
        widget.setToolTip(tooltip)
        if spec.required:
            label = QLabel(text)
            label.setToolTip(tooltip)
            include = None
        else:
            label = include = QCheckBox(text)
            include.setToolTip(f"{tooltip}\n\nUnticked: the default is used.")
            include.setChecked(spec.key in params)
            widget.setEnabled(spec.key in params)
            include.toggled.connect(widget.setEnabled)
            include.toggled.connect(self.changed)
        if is_vector(spec):
            # x/y/z boxes on their own indented line under the label, so a
            # vector never widens the whole form's field column.
            self.form.addRow(label)
            widget.setContentsMargins(26, 0, 0, 0)  # [px] line up under the label text
            self.form.addRow(widget)
        else:
            self.form.addRow(label, widget)
        self.fields[spec.key] = (spec, include, widget)

    def _make_widget(self, spec, unit: str, option):
        example = spec.example
        if isinstance(example, bool):
            box = QCheckBox("Yes")
            box.toggled.connect(self.changed)
            return box
        if isinstance(example, str):
            names, editable = option if option is not None else (choices(spec), not choices(spec))
            combo = ComboBox()
            combo.setEditable(editable)
            combo.addItems(list(names))
            combo.setMinimumWidth(220)
            combo.currentTextChanged.connect(self.changed)
            return combo
        if is_vector(spec):
            boxes = tuple(_component_box() for _ in range(3))
            holder = QWidget()
            holder.setObjectName("vectorRow")
            holder.setStyleSheet("QWidget#vectorRow { background: transparent; }")
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            for axis, box in zip("xyz", boxes):
                box.setPrefix(f"{axis}  ")
                box.valueChanged.connect(self.changed)
                row.addWidget(box)
            if unit:
                row.addWidget(QLabel(unit))
            if getattr(spec, "normalizable", True):
                normalize = QPushButton("Normalize")
                normalize.setAutoDefault(False)
                normalize.setToolTip("Rescale to a unit vector (keeps the direction).")
                normalize.clicked.connect(lambda _checked, k=spec.key: self.normalize(k))
                row.addWidget(normalize)
            row.addStretch(1)
            self.vector_boxes[spec.key] = boxes
            return holder
        box = PreciseDoubleSpinBox()
        box.setRange(-1.0e12, 1.0e12)
        box.setDecimals(0 if isinstance(example, int) else 3)
        if unit:
            box.setSuffix(f" {unit}")
        box.setFixedWidth(200)
        box.valueChanged.connect(self.changed)
        return box

    def _set_value(self, spec, widget, value) -> None:
        if isinstance(spec.example, bool):
            widget.setChecked(bool(value))
        elif isinstance(spec.example, str):
            text = str(value)
            if text and widget.findText(text) < 0:
                widget.addItem(text)
            if text:
                widget.setCurrentText(text)
        elif is_vector(spec):
            for box, component in zip(self.vector_boxes[spec.key], value):
                box.setValue(float(component))
        else:
            widget.setValue(value)

    @staticmethod
    def _value(spec, widget, vector_boxes):
        if isinstance(spec.example, bool):
            return widget.isChecked()
        if isinstance(spec.example, str):
            return widget.currentText().strip()
        if is_vector(spec):
            return [box.value() for box in vector_boxes[spec.key]]
        if isinstance(spec.example, int):
            return int(round(widget.value()))
        return widget.value()

    # -- access --------------------------------------------------------
    def include_box(self, key: str) -> QCheckBox | None:
        entry = self.fields.get(key)
        return entry[1] if entry else None

    def widget(self, key: str):
        entry = self.fields.get(key)
        return entry[2] if entry else None

    def set_value(self, key: str, value, include: bool = True) -> None:
        spec, box, widget = self.fields[key]
        self._set_value(spec, widget, value)
        if box is not None:
            box.setChecked(include)

    def form_params(self) -> dict:
        params = {}
        for key, (spec, include, widget) in self.fields.items():
            if include is None or include.isChecked():
                params[key] = self._value(spec, widget, self.vector_boxes)
        return params

    def extra_params(self) -> dict:
        text = self.params_edit.toPlainText().strip() or "{}"
        try:
            params = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"the advanced params are not valid JSON: {exc}") from exc
        if not isinstance(params, dict):
            raise ValueError("the advanced params must be a JSON object (e.g. {\"noise_std\": 0.01})")
        return params

    def params(self) -> dict:
        """Extras first, then the form's values (the form wins on a clash)."""
        params = {k: v for k, v in self.extra_params().items() if k not in self.fields}
        params.update(self.form_params())
        return params

    def normalize(self, key: str) -> None:
        x, y, z = self.vector_boxes[key]
        magnitude = math.sqrt(x.value() ** 2 + y.value() ** 2 + z.value() ** 2)
        if magnitude > 0.0:
            x.setValue(x.value() / magnitude)
            y.setValue(y.value() / magnitude)
            z.setValue(z.value() / magnitude)

    def _on_advanced_toggled(self, checked: bool) -> None:
        self.params_edit.setVisible(checked)
        self.advanced_toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
