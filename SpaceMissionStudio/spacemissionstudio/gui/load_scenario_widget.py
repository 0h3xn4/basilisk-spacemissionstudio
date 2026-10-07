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
        color = PALETTE["on_accent"] if selected else PALETTE["text"]
        self.title_label.setStyleSheet(f"color: {color};")


class LoadScenarioWidget(QWidget):
    path_chosen = Signal(object)  # pathlib.Path
    scenario_customized = Signal(object)  # schema.scenario.Scenario, built by TemplateCustomizeWizard

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._template_paths: Dict[str, Path] = {}

        # This tab's own natural content height (20 template rows plus
        # a long, multi-paragraph description label) can exceed what fits
        # in a real, non-maximized window on a modest display. Without this
        # QScrollArea, squeezing this widget's content into less height
        # than it needs doesn't just clip cleanly: QLabel does not clip
        # wrapped text to its own allocated rect, so description_label
        # (and the intro label above the list) paint their overflow text
        # past their own boundary and visibly overlap the sibling widget
        # above/below them -- confirmed from a real user screenshot taken
        # while resizing/maximizing the main window, where this showed up
        # as garbled, overlapping text right at the template list /
        # description label boundary. A QScrollArea never squeezes its
        # inner widget below its own size hint -- it scrolls instead --
        # which is exactly what ScenarioEditorWidget's own top-level
        # QScrollArea (scenario_editor.py) and spacecraft_editor.py's
        # per-tab _scrollable() already do for this same reason; this
        # widget is the one tab-page-sized widget in the app that was
        # still missing it.
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        intro = QLabel(
            "Start from one of SpaceMissionStudio's built-in template missions -- each demonstrates one "
            "concept in isolation and is a good starting point for your own scenario (see the "
            "description below once one is selected) -- or browse for any other scenario file."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Action row ABOVE the list, not below it: with 20 bundled
        # templates the list alone fills most of a 1400x850 window's
        # left pane, so buttons placed after it (or after a selected
        # template's multi-paragraph description) ended up below the fold.
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

        # No stretch factor: with one, this list claims and keeps every
        # pixel of extra vertical space the pane has, whether or not it
        # has enough rows to use it -- 9 short rows in a tall pane left a
        # few hundred pixels of visibly empty white box. Sized to its own
        # content instead (see _size_list_to_contents(), called once
        # populated below), with the leftover space collected in one
        # addStretch(1) at the very bottom -- ordinary, expected blank
        # space below a compact form, not an oversized near-empty widget.
        self.list_widget = QListWidget()
        self.list_widget.setItemDelegate(_BackgroundOnlyDelegate(self.list_widget))
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._rows: Dict[str, _TemplateRow] = {}
        layout.addWidget(self.list_widget)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.description_label)

        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._on_open_template_clicked())

        self._populate_templates()
        self._size_list_to_contents()

        hint = QLabel("Double-click a template to open it, or use a row's Customize... button for a guided "
                      "wizard over just that template's key parameters.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {PALETTE['text_muted']};")
        layout.insertWidget(layout.indexOf(self.list_widget) + 1, hint)
        layout.addStretch(1)

    def _size_list_to_contents(self) -> None:
        count = self.list_widget.count()
        if count == 0:
            return
        row_height = max(self.list_widget.sizeHintForRow(i) for i in range(count))
        frame = 2 * self.list_widget.frameWidth()
        # setFixedHeight(), not setMaximumHeight(): QListWidget's own
        # sizeHint() is a generic Qt default, NOT based on its actual
        # item count, and the layout's trailing addStretch(1) greedily
        # claims every pixel beyond whatever sizeHint() this widget
        # reports (stretch=0 items are pinned at their sizeHint, not
        # grown toward their maximumHeight, when a sibling stretch item
        # is competing for the same leftover space) -- so a maximum
        # alone was silently never reached. Exactly as many rows as there
        # are templates -- earlier "+2 rows of slack" just showed up as an
        # empty white band at the bottom of the list.
        self.list_widget.setFixedHeight(row_height * count + frame + 4)

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
        self.description_label.setText(current.data(Qt.ItemDataRole.UserRole) if current is not None else "")
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
