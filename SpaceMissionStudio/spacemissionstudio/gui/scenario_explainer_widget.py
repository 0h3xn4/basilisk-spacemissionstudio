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

"""ScenarioExplainerWidget: renders ``engine.scenario_explainer.explain()``'s
structured output as a KPI-style stat-tile row, per-section colored
badges, and (for 2+ spacecraft) a comparison table -- never prose, never
a raw bullet-point list (both were tried first and explicitly rejected
by a real user). See that module's own docstring for the full design
rationale and the "don't regress this" discipline.

Wired into ``main_window.py`` as a new "Explain" tab, driven by
``ScenarioEditorWidget.changed`` (already fires on every edit to drive
``revalidate()`` -- zero new plumbing needed). Does NOT touch or replace
``scenario_editor.py``'s own free-text ``description`` box -- that one is
hand-written, narrative/pedagogical prose for the 20 bundled templates
specifically; this is a terse, ALWAYS-CURRENT fact summary for any
scenario, built fresh from the scenario's actual current fields.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..engine.scenario_explainer import ScenarioExplanation, explain
from ..schema.scenario import Scenario
from .badges import ACCENT, DANGER, MUTED, SUCCESS, WARNING, badge_style
from .formation_diagram_widget import FormationDiagramWidget
from .theme import PALETTE

_FORMATION_SECTION_TITLE = "Formation / orbit maintenance"

_BADGE_KIND_COLORS = {
    "neutral": MUTED,
    "accent": ACCENT,
    "success": SUCCESS,
    "warning": WARNING,
    "danger": DANGER,
}


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


def _stat_tile(label: str, value: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName("statTile")
    frame.setFrameShape(QFrame.Shape.NoFrame)
    # "#statTile", not a bare "QFrame" selector: QLabel inherits QFrame,
    # so an unscoped rule also drew a second bordered box around each
    # tile's own value and caption labels.
    frame.setStyleSheet(
        f"QFrame#statTile {{ background-color: {PALETTE['surface']}; border: 1px solid {PALETTE['border']}; "
        "border-radius: 6px; }"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 6, 10, 6)
    layout.setSpacing(2)
    value_label = QLabel(value)
    value_label.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {PALETTE['text']};")
    value_label.setWordWrap(True)
    label_label = QLabel(label)
    label_label.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 11px;")
    layout.addWidget(value_label)
    layout.addWidget(label_label)
    return frame


def _badge_label(text: str, kind: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(badge_style(_BADGE_KIND_COLORS.get(kind, MUTED)))
    return label


class ScenarioExplainerWidget(QWidget):
    """``set_scenario(Optional[Scenario])`` rebuilds the whole display
    from scratch (clear + repopulate -- mirrors
    ``scenario_editor.py``'s own ``_refresh_propagation_summary()``
    pattern), inside a ``QScrollArea`` so it never forces the window
    taller. ``None`` (e.g. the scenario currently fails validation) shows
    a short placeholder instead of crashing.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer_layout.addWidget(scroll)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        scroll.setWidget(content)

        self._placeholder_label = QLabel(
            "Fix validation errors above to see this scenario's recipe here."
        )
        self._placeholder_label.setWordWrap(True)
        self._placeholder_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        self._content_layout.addWidget(self._placeholder_label)

        self._headline_label = QLabel()
        self._headline_label.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {PALETTE['text']};")
        self._headline_label.setWordWrap(True)
        self._content_layout.addWidget(self._headline_label)

        self._tiles_row = QHBoxLayout()
        self._tiles_row.setSpacing(8)
        self._content_layout.addLayout(self._tiles_row)

        self._sections_layout = QVBoxLayout()
        self._sections_layout.setSpacing(10)
        self._content_layout.addLayout(self._sections_layout)

        self._table = QTableWidget()
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._table.verticalHeader().setVisible(False)  # the Spacecraft column already names each row
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._table.installEventFilter(self)  # refit the height when the width changes
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Fitted to its rows (below), so it never scrolls vertically.
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_layout.addWidget(self._table)

        self._content_layout.addStretch(1)

        self.set_scenario(None)

    def _fit_table_height(self) -> None:
        """Fit the table to its rows instead of leaving a tall, mostly
        empty grid -- and, when it is wider than the pane, add room for its
        horizontal scroll bar so the last row isn't cut off."""
        table = self._table
        height = table.horizontalHeader().height() + 2 * table.frameWidth() + 2
        height += sum(table.rowHeight(r) for r in range(table.rowCount()))
        if table.horizontalHeader().length() > table.width() - 2 * table.frameWidth():
            height += table.horizontalScrollBar().sizeHint().height()
        if table.height() != height:
            table.setFixedHeight(height)

    def eventFilter(self, watched, event):  # noqa: N802 -- Qt API name
        if watched is self._table and event.type() == QEvent.Type.Resize and self._table.rowCount():
            self._fit_table_height()
        return super().eventFilter(watched, event)

    def set_scenario(self, scenario: Optional[Scenario]) -> None:
        if scenario is None:
            self._placeholder_label.setVisible(True)
            self._headline_label.setVisible(False)
            _clear_layout(self._tiles_row)
            _clear_layout(self._sections_layout)
            self._table.setVisible(False)
            self._table.setRowCount(0)
            self._table.setColumnCount(0)
            return

        self._placeholder_label.setVisible(False)
        self._headline_label.setVisible(True)

        explanation = explain(scenario)
        self._render(explanation)

    def _render(self, explanation: ScenarioExplanation) -> None:
        self._headline_label.setText(explanation.headline)

        _clear_layout(self._tiles_row)
        for tile in explanation.stat_tiles:
            self._tiles_row.addWidget(_stat_tile(tile.label, tile.value))
        self._tiles_row.addStretch(1)

        _clear_layout(self._sections_layout)
        for section in explanation.sections:
            section_widget = QWidget()
            # Transparent: the theme's base "QWidget" rule otherwise painted
            # each section as a grey band across this tab's white pane.
            section_widget.setObjectName("explainSection")
            section_widget.setStyleSheet("QWidget#explainSection { background: transparent; }")
            section_layout = QVBoxLayout(section_widget)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.setSpacing(4)

            title_label = QLabel(section.title)
            title_label.setStyleSheet(f"font-weight: 600; color: {PALETTE['text']};")
            section_layout.addWidget(title_label)

            if section.badges:
                badges_row = QHBoxLayout()
                badges_row.setSpacing(6)
                for badge in section.badges:
                    badges_row.addWidget(_badge_label(badge.label, badge.kind))
                badges_row.addStretch(1)
                section_layout.addLayout(badges_row)

            for note in section.notes:
                note_label = QLabel(note)
                note_label.setWordWrap(True)
                note_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
                section_layout.addWidget(note_label)

            # The formation-geometry diagram(s) belong right alongside the
            # section whose badges they illustrate -- "Station-keeping"/
            # "Phasing-keeping" badges name the mechanism, the diagram
            # depicts it (per the dataviz skill's own "depict the
            # mechanism, not its name" guidance, and direct user feedback
            # that an earlier badges-only design still lacked "depth of
            # information").
            if section.title == _FORMATION_SECTION_TITLE:
                for diagram in explanation.formation_diagrams:
                    section_layout.addWidget(FormationDiagramWidget(diagram))

            self._sections_layout.addWidget(section_widget)

        if explanation.spacecraft_table:
            columns = []
            for row in explanation.spacecraft_table:
                for key in row.facts:
                    if key not in columns:
                        columns.append(key)
            self._table.setVisible(True)
            self._table.setColumnCount(1 + len(columns))
            self._table.setHorizontalHeaderLabels(["Spacecraft"] + columns)
            self._table.setRowCount(len(explanation.spacecraft_table))
            for row_index, row in enumerate(explanation.spacecraft_table):
                self._table.setItem(row_index, 0, QTableWidgetItem(row.name))
                for col_index, column in enumerate(columns, start=1):
                    self._table.setItem(row_index, col_index, QTableWidgetItem(row.facts.get(column, "")))
            self._table.resizeColumnsToContents()
            self._fit_table_height()
        else:
            self._table.setVisible(False)
            self._table.setRowCount(0)
            self._table.setColumnCount(0)
