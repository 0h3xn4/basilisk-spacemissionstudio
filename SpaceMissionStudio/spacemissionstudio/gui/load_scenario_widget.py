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

"""LoadScenarioWidget: the "Load Scenario" tab -- lets a user pick one of
SpaceMissionStudio's built-in template missions (``spacemissionstudio/scenarios/
templates/``, see that directory's own README and
``scripts/_generate_templates.py``) without needing to already know
where they're installed, or browse for any other scenario file. Built in
response to a direct request that the bundled templates be reachable
from inside the GUI itself, not just as files a user has to go find on
disk.

Deliberately thin: this widget only picks a *path* and emits it via
:attr:`path_chosen` -- ``MainWindow.open_path()`` does the actual
loading (``schema.scenario.load_scenario()`` plus its existing
unsaved-changes/error-message handling), so there is exactly one place
that knows how to open a scenario file, matching how every other
GUI-vs-``schema``/``engine`` split in this app works (see this module's
own class docstring).

Also offers a "Customize..." button on the list row of every template
with a registered ``gui.template_wizard.TemplateWizardSpec`` -- runs a
guided, multi-step wizard over just that template's own curated "Try
changing:" parameters (see ``gui.template_wizard``'s own docstring) and
emits the resulting in-memory ``Scenario`` via :attr:`scenario_customized`,
instead of a path (there is no file yet -- see
``MainWindow._on_load_scenario_customized`` for how that's opened
without ever touching the original template file on disk).

Each row's button is always visible and acts on THAT row's template,
never on the list's current selection -- built in response to direct
feedback that an earlier version (one generic "Customize..." button,
enabled only once a template was already selected) was too easy to miss
entirely. An intermediate version then added a second, full-width
"Customize: <whole template title>..." button per template below the
list; that duplicated every title and, at up to ~670 px wide, forced the
whole left pane into a horizontal scrollbar at the default window size
(clipping the intro text and this tab's own action buttons). One
compact button per row keeps the discoverability without the clutter.
"""

from __future__ import annotations

import html

import functools
import logging
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

import spacemissionstudio

from ..schema import load_scenario
from .template_wizard import TemplateCustomizeWizard, get_wizard_spec
from .theme import PALETTE

_logger = logging.getLogger(__name__)

# Where scripts/_generate_templates.py writes the built-in templates, and
# where setuptools package-data (see pyproject.toml's own comment on
# this) copies them to in an installed wheel -- spacemissionstudio.__file__ is
# <install>/spacemissionstudio/__init__.py either way (a checkout or a real
# install), so this resolves correctly in both.
TEMPLATES_DIR = Path(spacemissionstudio.__file__).resolve().parent / "scenarios" / "templates"

_FILE_FILTER = "SpaceMissionStudio scenario (*.json)"



def description_html(text: str) -> str:
    """A template description as rich text: paragraphs separated by a
    blank line, a paragraph whose first line ends with ":" as a heading,
    and "- " lines as a bullet list (see scripts/_template_descriptions.py).
    A real user called the old plain-text block "just awful UI/UX"."""
    parts = []
    for paragraph in text.strip().split("\n\n"):
        lines = paragraph.splitlines()
        heading = lines[0] if lines and lines[0].endswith(":") and not lines[0].startswith("- ") else None
        body = lines[1:] if heading else lines
        if heading:
            parts.append(f"<p style='margin: 10px 0 2px 0;'><b>{html.escape(heading[:-1])}</b></p>")
        bullets = [line[2:] for line in body if line.startswith("- ")]
        prose = [line for line in body if not line.startswith("- ")]
        if prose:
            parts.append(f"<p style='margin: 0 0 4px 0;'>{html.escape(' '.join(prose))}</p>")
        if bullets:
            parts.append("<ul style='margin: 0; -qt-list-indent: 1;'>"
                         + "".join(f"<li>{html.escape(item)}</li>" for item in bullets) + "</ul>")
    return "".join(parts)

class _BackgroundOnlyDelegate(QStyledItemDelegate):
    """Paints each row's background/selection/hover exactly as the theme
    styles them, but not its text -- the row's own ``_TemplateRow`` widget
    (``setItemWidget``) draws the visible, elided title instead. Keeps
    ``item.text()`` as the template's real name for every lookup.
    """

    def paint(self, painter, option, index):
        opt = option.__class__(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)


class _ElidedLabel(QLabel):
    """A single-line label that elides with "..." instead of demanding
    its full text width as a minimum -- lets a long template title shrink
    gracefully with the pane rather than forcing a horizontal scrollbar.
    """

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setToolTip(text)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        elided = self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), elided)


class _TemplateRow(QWidget):
    """One template list row: its title, plus (if it has a wizard spec) a
    compact "Customize..." button acting on THIS template only."""

    def __init__(self, name: str, on_customize=None, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 1, 4, 1)
        layout.setSpacing(8)
        self.title_label = _ElidedLabel(name)
        layout.addWidget(self.title_label, 1)
        self.customize_button: Optional[QPushButton] = None
        if on_customize is not None:
            button = QPushButton("Customize...")
            button.setObjectName("rowCustomizeButton")
            button.setAccessibleName(f"Customize: {name}")
            button.setToolTip(
                f"Customize '{name}': a short, guided wizard over just this template's own key tunable "
                "parameters, then opens the result in the Scenario Editor -- the original template file "
                "is never modified."
            )
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(on_customize)
            layout.addWidget(button)
            self.customize_button = button
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        # Selected rows are Carbon's light layer-selected grey, not blue, so
        # the title keeps the primary text colour (white on it was unreadable)
        # and turns semibold.
        weight = 600 if selected else 400
        self.title_label.setStyleSheet(f"color: {PALETTE['text']}; font-weight: {weight};")


class LoadScenarioWidget(QWidget):
    path_chosen = Signal(object)  # pathlib.Path
    scenario_customized = Signal(object)  # schema.scenario.Scenario, built by TemplateCustomizeWizard

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._template_paths: Dict[str, Path] = {}

        # Layout: intro and buttons on top, then the template list and the
        # selected template's description card, split by a draggable
        # divider, each scrolling on its own. Real user feedback ("just
        # awful UI/UX"): the description used to sit below the 20-row list,
        # off-screen until the whole tab was scrolled, as one grey block of
        # prose. Its own scroll area also keeps the wrapped text from ever
        # being squeezed and painting over its neighbours (an earlier,
        # real overlapping-text bug).
        layout = QVBoxLayout(self)
        intro = QLabel("Pick a built-in template mission, or open your own scenario file.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        button_row = QHBoxLayout()
        self.open_template_button = QPushButton("Open Template")
        self.open_template_button.setEnabled(False)
        self.open_template_button.setProperty("primary", True)
        self.open_template_button.clicked.connect(self._on_open_template_clicked)
        button_row.addWidget(self.open_template_button)
        self.browse_button = QPushButton("Browse for a file...")
        self.browse_button.clicked.connect(self._on_browse_clicked)
        button_row.addWidget(self.browse_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        hint = QLabel("Double-click to open. Customize... changes settings first.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {PALETTE['text_muted']};")
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.setItemDelegate(_BackgroundOnlyDelegate(self.list_widget))
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._rows: Dict[str, _TemplateRow] = {}

        self.description_title = QLabel()
        self.description_title.setStyleSheet("font-weight: 600; font-size: 115%;")
        self.description_title.setWordWrap(True)
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setTextFormat(Qt.TextFormat.RichText)
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        card = QWidget()
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(self.description_title)
        card_layout.addWidget(self.description_label)
        card_layout.addStretch(1)
        self.description_scroll = QScrollArea()
        self.description_scroll.setWidgetResizable(True)
        self.description_scroll.setWidget(card)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.list_widget)
        splitter.addWidget(self.description_scroll)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 360])  # roughly half each; the divider stays draggable
        layout.addWidget(splitter, 1)

        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._on_open_template_clicked())

        self._populate_templates()

    def _populate_templates(self) -> None:
        if not TEMPLATES_DIR.is_dir():
            return
        for path in sorted(TEMPLATES_DIR.glob("*.json")):
            try:
                scenario = load_scenario(path)
            except Exception:  # noqa: BLE001 -- a malformed bundled template must never crash the GUI on open
                _logger.exception("Skipping malformed bundled template %s", path)
                continue
            self._template_paths[scenario.name] = path
            item = QListWidgetItem(scenario.name)
            item.setData(Qt.ItemDataRole.UserRole, scenario.description)
            self.list_widget.addItem(item)

            spec = get_wizard_spec(path.name)
            on_customize = (functools.partial(self._on_customize_template_clicked, path, spec)
                            if spec is not None else None)
            row = _TemplateRow(scenario.name, on_customize)
            item.setSizeHint(QSize(0, max(row.sizeHint().height(), 28)))
            self.list_widget.setItemWidget(item, row)
            self._rows[scenario.name] = row

    def _on_selection_changed(self, current: Optional[QListWidgetItem], previous) -> None:
        self.open_template_button.setEnabled(current is not None)
        self.description_title.setText(current.text() if current is not None else "")
        self.description_label.setText(
            description_html(current.data(Qt.ItemDataRole.UserRole) or "") if current is not None else "")
        for item, selected in ((previous, False), (current, True)):
            row = self._rows.get(item.text()) if item is not None else None
            if row is not None:
                row.set_selected(selected)

    def _on_open_template_clicked(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        path = self._template_paths.get(item.text())
        if path is not None:
            self.path_chosen.emit(path)

    def _on_customize_template_clicked(self, path: Path, spec) -> None:
        """A row's own "Customize..." button -- unlike
        _on_open_template_clicked, this never reads
        self.list_widget.currentItem(): each button already knows exactly
        which template/spec it's for, regardless of whatever (if anything)
        is currently selected in the list.
        """
        try:
            scenario = load_scenario(path)
        except Exception as exc:  # noqa: BLE001 -- surface ANY failure in a dialog, never crash the GUI
            _logger.exception("Could not load template %s for the customize wizard", path)
            QMessageBox.critical(self, "Could not open template", str(exc))
            return
        wizard = TemplateCustomizeWizard(scenario, spec, self)
        if wizard.exec() == TemplateCustomizeWizard.DialogCode.Accepted:
            self.scenario_customized.emit(wizard.result_scenario())

    def _on_browse_clicked(self) -> None:
        path_str, _selected_filter = QFileDialog.getOpenFileName(self, "Open scenario", "", _FILE_FILTER)
        if path_str:
            self.path_chosen.emit(Path(path_str))
