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
"""Application-wide visual theme, after IBM's Carbon design system (UX/UI
guidelines, decision 1: full restyle): Carbon's g10 colour tokens, its type
(IBM Plex, bundled) and its component looks, rebuilt in Qt as one QSS
stylesheet plus a QPalette, applied once at start-up (:func:`apply_theme`,
called from ``gui/app.py``).

What is Carbon here:

* **Colour:** the g10 theme tokens (``background`` #f4f4f4, ``layer-01``
  #ffffff, ``field-02`` #f4f4f4, ``border-subtle`` #e0e0e0,
  ``border-strong`` #8d8d8d, ``text-primary`` #161616, ``text-secondary``
  #525252, ``interactive``/``button-primary`` #0f62fe, the support colours).
  :data:`PALETTE` keeps this module's earlier key names, so every widget
  that reads it follows; the Carbon token each key stands for is noted.
* **Type:** IBM Plex Sans at 14 px (Carbon ``body-compact-01``, 10.5 pt at
  96 dpi) with 0.16 px tracking; semibold for headings and selected tabs;
  IBM Plex Mono for code. The WOFF files ship unmodified under the SIL Open
  Font License (``assets/fonts/``). Where Qt cannot load them (PySide6
  older than 6.7) the platform font is used.
* **Components:** square corners; fields filled with a bottom rule and a
  2 px focus outline (plus a light edge on the other sides, the one
  deviation: users must see a box around editable values); line tabs with a 2 px indicator; primary buttons
  filled blue, other buttons Carbon's tertiary outline; selected rows in
  ``layer-selected`` grey rather than blue; dark tooltips; Carbon tags for
  badges (``gui/badges.py``).

Qt Style Sheets are a limited CSS dialect (Qt docs, "Qt Style Sheets
Reference"): no shadows, no letter-spacing (set on the application font
instead), per-widget property support varies. Everything here is written
against that reference.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

# Carbon g10 tokens (Carbon v11), under this module's key names.
_C = {
    "bg": "#F4F4F4",            # background
    "surface": "#FFFFFF",       # layer-01: tiles, group boxes, tab panes, popups
    "surface_alt": "#F4F4F4",   # layer-02 (on layer-01): status bar, recessed panels, disabled fields
    "field": "#F4F4F4",         # field-02: inputs on layer-01
    "hover": "#E8E8E8",         # layer-hover-01
    "selected": "#E0E0E0",      # layer-selected-01 (selected rows and list items)
    "border": "#E0E0E0",        # border-subtle-01
    "border_strong": "#8D8D8D",  # border-strong-01 (field bottom rules, checkbox outlines)
    "field_edge": "#C6C6C6",    # gray 30: a field's other three edges (not Carbon; see the fields rule)
    "text": "#161616",          # text-primary (also icon-primary)
    "text_muted": "#525252",    # text-secondary
    "text_disabled": "#C6C6C6",  # text-disabled
    "accent": "#0F62FE",        # interactive, button-primary, focus, border-interactive
    "accent_hover": "#0050E6",  # button-primary-hover
    "accent_pressed": "#002D9C",  # button-primary-active
    "accent_soft": "#D0E2FF",   # highlight (text selection, soft accent)
    "on_accent": "#FFFFFF",     # text-on-color
    "inverse": "#393939",       # background-inverse (tooltips)
    "danger": "#DA1E28",        # support-error
    "success": "#24A148",       # support-success
    "warning": "#8E6A00",       # yellow 60: warning TEXT (support-warning #F1C21B is too light for text)
    "warning_fill": "#F1C21B",  # support-warning (fills, never text)
    "danger_soft": "#FFF1F1",   # notification-background-error
    "success_soft": "#DEFBE6",  # notification-background-success
    "warning_soft": "#FCF4D6",  # notification-background-warning
    "info_soft": "#EDF5FF",     # notification-background-info
}

# Public alias: widgets (feedback.py's toasts, badges, charts) reuse these
# colours rather than picking their own.
PALETTE = _C

# Carbon's categorical data-visualisation hues (cyan 50, orange 50, purple 60,
# yellow 50, teal 50, orange 60, blue 50, magenta 60), stepped and ordered
# so the set passes the dataviz validator on the white chart surface: all 8
# in the lightness band, chroma above the floor, worst adjacent CVD
# Delta E 14.6 (protan), worst normal-vision Delta E 19.4, all >= 3:1
# contrast. Carbon's own first eight fail the band and chroma checks (red 90,
# blue 80, teal 70). Red and green stay out: they mean error and success.
SERIES_COLORS = ["#1192E8", "#EB6200", "#8A3FFC", "#B28600", "#009D9A", "#BA4E00", "#4589FF", "#D02670"]

# Small SVG glyphs (combo/spin arrows, check mark, radio dot) the stylesheet
# points at: styling a subcontrol makes Qt stop drawing its native arrow.
# Their colours are hard-coded to text_muted/text_disabled/on_accent/text
# (tests/gui/test_theme.py checks they stay in step).
_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONTS_DIR = _ASSETS_DIR / "fonts"
UI_FONT_FAMILY = "IBM Plex Sans"
MONO_FONT_FAMILY = "IBM Plex Mono"
_UI_FONT_SIZE_PT = 10.5  # [pt] 14 px at 96 dpi (Carbon body-compact-01)
_UI_LETTER_SPACING_PX = 0.16  # [px] Carbon body-compact-01 tracking
_loaded_families: List[str] = []


def _asset(name: str) -> str:
    # Qt's url() wants forward slashes on every platform, Windows included.
    return (_ASSETS_DIR / name).as_posix()


def load_fonts() -> List[str]:
    """Register the bundled IBM Plex faces with Qt (once); the families
    that loaded. A face Qt cannot read is skipped, not fatal."""
    if not _loaded_families:
        for path in sorted(FONTS_DIR.glob("*.woff")):
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id >= 0:
                _loaded_families.extend(f for f in QFontDatabase.applicationFontFamilies(font_id)
                                        if f not in _loaded_families)
    return list(_loaded_families)


def _qss() -> str:
    c = _C
    return f"""
    /* ---- base ---------------------------------------------------- */
    QWidget {{
        background-color: {c['bg']};
        color: {c['text']};
        selection-background-color: {c['accent_soft']};
        selection-color: {c['text']};
    }}
    QMainWindow, QDialog {{
        background-color: {c['bg']};
    }}
    QToolTip {{
        background-color: {c['inverse']};
        color: {c['on_accent']};
        border: none;
        padding: 4px 8px;
        border-radius: 2px;
    }}
    QLabel {{
        background: transparent;
    }}

    /* ---- group boxes: Carbon tiles on layer-01 ---------------------- */
    QGroupBox {{
        background-color: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 0px;
        margin-top: 22px;
        padding-top: 8px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 0px;
        top: 2px;
        padding: 0 0 4px 0;
        background-color: transparent;
        color: {c['text']};
    }}
    QGroupBox::indicator {{
        width: 16px;
        height: 16px;
    }}

    /* ---- buttons: primary filled, others Carbon tertiary ------------- */
    QPushButton {{
        background-color: transparent;
        border: 1px solid {c['accent']};
        border-radius: 0px;
        padding: 6px 16px;
        color: {c['accent']};
    }}
    QPushButton:hover {{
        background-color: {c['accent_hover']};
        border-color: {c['accent_hover']};
        color: {c['on_accent']};
    }}
    QPushButton:pressed {{
        background-color: {c['accent_pressed']};
        border-color: {c['accent_pressed']};
        color: {c['on_accent']};
    }}
    QPushButton:focus {{
        border: 2px solid {c['accent']};
        padding: 5px 15px;
    }}
    QPushButton:disabled {{
        color: {c['text_disabled']};
        border-color: {c['text_disabled']};
        background-color: transparent;
    }}
    QPushButton:default, QPushButton[primary="true"] {{
        background-color: {c['accent']};
        border: 1px solid {c['accent']};
        color: {c['on_accent']};
    }}
    /* Semibold only for the static primary property, NOT :default -- a
       button can BECOME the default after Qt has sized it (QWizard's Finish
       button on the last page), and the wider text was then clipped. */
    QPushButton[primary="true"] {{
        font-weight: 600;
    }}
    QPushButton:default:hover, QPushButton[primary="true"]:hover {{
        background-color: {c['accent_hover']};
        border-color: {c['accent_hover']};
    }}
    QPushButton:default:pressed, QPushButton[primary="true"]:pressed {{
        background-color: {c['accent_pressed']};
        border-color: {c['accent_pressed']};
    }}
    /* A disabled primary button must not keep the bright fill (Carbon:
       button-disabled #C6C6C6 with text-on-color-disabled #8D8D8D). */
    QPushButton:default:disabled, QPushButton[primary="true"]:disabled {{
        background-color: {c['text_disabled']};
        border: 1px solid {c['text_disabled']};
        color: {c['border_strong']};
    }}
    /* Compact in-row action (a template row's "Customize..."): Carbon ghost. */
    QPushButton#rowCustomizeButton {{
        padding: 1px 8px;
        border: 1px solid transparent;
        color: {c['accent']};
        font-weight: 600;
    }}
    QPushButton#rowCustomizeButton:hover {{
        background-color: {c['hover']};
        color: {c['accent_hover']};
    }}

    /* ---- fields: filled, bottom rule, 2 px focus outline -------------- */
    /* One deviation from Carbon, which draws only the bottom rule: a light
       edge on the other three sides too. Users could not tell editable
       values from labels without a box around them, and a field-02 fill
       vanishes where a field sits straight on the window background
       (tests/gui/test_input_borders.py). */
    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateTimeEdit {{
        background-color: {c['field']};
        border: 1px solid {c['field_edge']};
        border-bottom: 1px solid {c['border_strong']};
        border-radius: 0px;
        padding: 5px 8px;
        selection-background-color: {c['accent_soft']};
        selection-color: {c['text']};
    }}
    QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover,
    QComboBox:hover, QDateTimeEdit:hover {{
        background-color: {c['hover']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
    QComboBox:focus, QDateTimeEdit:focus {{
        border: 2px solid {c['accent']};
        padding: 4px 7px;
    }}
    QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled, QSpinBox:disabled,
    QDoubleSpinBox:disabled, QComboBox:disabled, QDateTimeEdit:disabled {{
        color: {c['text_disabled']};
        background-color: {c['field']};
        border-bottom: 1px solid {c['field_edge']};
    }}
    QLineEdit:read-only {{
        background-color: transparent;
        border-bottom: 1px solid {c['border']};
    }}
    /* Inline field-validation state (gui/feedback.py's mark_invalid): a
       dynamic property, the documented way to add a custom QSS selector.
       Carbon's invalid field: a 2 px support-error outline. */
    QLineEdit[state="error"], QDoubleSpinBox[state="error"], QSpinBox[state="error"], QComboBox[state="error"] {{
        border: 2px solid {c['danger']};
        padding: 4px 7px;
    }}
    QLineEdit[state="error"]:focus, QDoubleSpinBox[state="error"]:focus,
    QSpinBox[state="error"]:focus, QComboBox[state="error"]:focus {{
        border: 2px solid {c['danger']};
    }}
    QLineEdit::placeholder {{
        color: {c['text_muted']};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 28px;
    }}
    QComboBox::down-arrow {{
        image: url({_asset('chevron-down.svg')});
        width: 10px;
        height: 10px;
    }}
    QComboBox::down-arrow:disabled {{
        image: url({_asset('chevron-down-disabled.svg')});
    }}
    QComboBox QAbstractItemView {{
        background-color: {c['surface']};
        border: none;
        selection-background-color: {c['selected']};
        selection-color: {c['text']};
        outline: none;
        padding: 0px;
    }}
    QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        width: 18px;
        border: none;
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url({_asset('chevron-up.svg')});
        width: 8px;
        height: 8px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url({_asset('chevron-down.svg')});
        width: 8px;
        height: 8px;
    }}
    QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled,
    QSpinBox::up-arrow:off, QDoubleSpinBox::up-arrow:off {{
        image: url({_asset('chevron-up-disabled.svg')});
    }}
    QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled,
    QSpinBox::down-arrow:off, QDoubleSpinBox::down-arrow:off {{
        image: url({_asset('chevron-down-disabled.svg')});
    }}

    /* ---- lists and trees: Carbon structured list ----------------------- */
    QListWidget, QTreeWidget, QListView, QTreeView {{
        background-color: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 0px;
        outline: none;
    }}
    /* Padding as before the restyle: list rows that hold their own widgets
       (the template list's Customize... buttons) are sized to it. */
    QListWidget::item, QTreeWidget::item {{
        padding: 4px 6px;
    }}
    QListWidget::item:selected, QTreeWidget::item:selected {{
        background-color: {c['selected']};
        color: {c['text']};
    }}
    QListWidget::item:hover:!selected, QTreeWidget::item:hover:!selected {{
        background-color: {c['hover']};
    }}

    /* ---- tables: Carbon data table ------------------------------------- */
    QTableWidget, QTableView {{
        background-color: {c['surface']};
        alternate-background-color: {c['surface']};
        border: 1px solid {c['border']};
        gridline-color: {c['border']};
        selection-background-color: {c['selected']};
        selection-color: {c['text']};
    }}
    QHeaderView::section {{
        background-color: {c['selected']};
        color: {c['text']};
        font-weight: 600;
        border: none;
        border-right: 1px solid {c['surface']};
        padding: 6px 12px;
    }}
    QTableCornerButton::section {{
        background-color: {c['selected']};
        border: none;
    }}

    /* ---- tabs: Carbon line tabs ------------------------------------------ */
    QTabWidget::pane {{
        background-color: {c['surface']};
        border: none;
        border-top: 1px solid {c['border']};
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {c['text_muted']};
        padding: 8px 16px;
        margin-right: 0px;
        border: none;
        border-bottom: 2px solid {c['border']};
    }}
    QTabBar::tab:selected {{
        color: {c['text']};
        font-weight: 600;
        border-bottom: 2px solid {c['accent']};
    }}
    QTabBar::tab:hover:!selected {{
        color: {c['text']};
        border-bottom: 2px solid {c['border_strong']};
    }}
    QTabBar::tab:disabled {{
        color: {c['text_disabled']};
    }}

    /* ---- scroll areas / scrollbars ------------------------------------ */
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}
    QScrollArea > QWidget > QWidget {{
        background-color: transparent;
    }}
    /* Bordered, recessed reference panel (the sensor/actuator editor's
       per-kind parameter reference). */
    QScrollArea#paramReference {{
        border: 1px solid {c['border']};
        border-radius: 0px;
        background-color: {c['surface_alt']};
    }}
    QScrollArea#paramReference > QWidget > QWidget {{
        background-color: {c['surface_alt']};
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['text_disabled']};
        border-radius: 0px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c['border_strong']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c['text_disabled']};
        border-radius: 0px;
        min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {c['border_strong']};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* ---- menus / toolbar / status bar --------------------------------- */
    QMenuBar {{
        background-color: {c['surface']};
        border-bottom: 1px solid {c['border']};
        padding: 0px;
    }}
    QMenuBar::item {{
        padding: 8px 12px;
        background: transparent;
    }}
    QMenuBar::item:selected {{
        background-color: {c['hover']};
        color: {c['text']};
    }}
    QMenu {{
        background-color: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 0px;
        padding: 0px;
    }}
    QMenu::item {{
        padding: 8px 32px 8px 16px;
    }}
    QMenu::item:selected {{
        background-color: {c['hover']};
        color: {c['text']};
    }}
    QMenu::item:disabled {{
        color: {c['text_disabled']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {c['border']};
        margin: 0px;
    }}
    QToolBar {{
        background-color: {c['surface']};
        border-bottom: 1px solid {c['border']};
        padding: 0px 4px;
        spacing: 0px;
    }}
    QToolButton {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 0px;
        padding: 6px 10px;
    }}
    QToolButton:hover {{
        background-color: {c['hover']};
    }}
    QToolButton:pressed {{
        background-color: {c['selected']};
    }}
    QToolButton:disabled {{
        color: {c['text_disabled']};
    }}
    /* A checkable action's ON state (e.g. "Live Plot"): selected layer and
       Carbon's 2 px interactive indicator. */
    QToolButton:checked {{
        background-color: {c['selected']};
        border-bottom: 2px solid {c['accent']};
        color: {c['text']};
    }}
    /* A menu button laid out among push buttons (the Data tab's Download,
       Import, Roll back): Carbon tertiary, like QPushButton above. */
    QToolButton[tertiary="true"] {{
        border: 1px solid {c['accent']};
        color: {c['accent']};
        padding: 6px 24px 6px 16px;
    }}
    QToolButton[tertiary="true"]:hover {{
        background-color: {c['accent_hover']};
        border-color: {c['accent_hover']};
        color: {c['on_accent']};
    }}
    QToolButton[tertiary="true"]:disabled {{
        border-color: {c['text_disabled']};
        color: {c['text_disabled']};
    }}
    QToolButton[tertiary="true"]::menu-indicator {{
        image: url({_asset('chevron-down.svg')});
        subcontrol-position: right center;
        subcontrol-origin: padding;
        right: 6px;
        width: 10px;
        height: 10px;
    }}
    QToolButton#primaryToolButton {{
        background-color: {c['accent']};
        color: {c['on_accent']};
        font-weight: 600;
    }}
    QToolButton#primaryToolButton:hover {{
        background-color: {c['accent_hover']};
    }}
    QToolButton#primaryToolButton:pressed {{
        background-color: {c['accent_pressed']};
    }}
    QToolButton#primaryToolButton:disabled {{
        background-color: {c['text_disabled']};
        color: {c['border_strong']};
    }}
    QStatusBar {{
        background-color: {c['surface']};
        border-top: 1px solid {c['border']};
        color: {c['text_muted']};
    }}
    QSplitter::handle {{
        background-color: {c['border']};
    }}
    QSplitter::handle:horizontal {{
        width: 1px;
    }}
    QSplitter::handle:vertical {{
        height: 1px;
    }}

    /* ---- progress bar: Carbon progress bar ------------------------------- */
    QProgressBar {{
        background-color: {c['border']};
        border: none;
        border-radius: 0px;
        text-align: center;
        color: {c['text_muted']};
        max-height: 8px;
    }}
    QProgressBar::chunk {{
        background-color: {c['accent']};
        border-radius: 0px;
    }}

    /* ---- checkboxes / radio buttons / checkable group boxes --------- */
    /* Transparent, not the base rule's window background: inside a white
       group box that painted a grey band behind every checkbox row. */
    QCheckBox, QRadioButton, QStackedWidget {{
        background-color: transparent;
    }}
    /* ... and a stacked widget's pages (the orbit initial-condition forms):
       painted with the window colour they hid the grey fields on them. */
    QStackedWidget > QWidget {{
        background-color: transparent;
    }}
    QCheckBox, QRadioButton {{
        spacing: 8px;
    }}
    /* Carbon checkbox: 16 px, 1 px icon-primary outline, 2 px corners,
       checked filled icon-primary with a white tick. Radio: a ring and a
       centre dot in icon-primary. */
    QCheckBox::indicator, QGroupBox::indicator, QRadioButton::indicator,
    QListWidget::indicator, QTreeWidget::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {c['text']};
        border-radius: 2px;
        background-color: {c['surface']};
    }}
    QRadioButton::indicator {{
        border-radius: 8px;
    }}
    QCheckBox::indicator:hover, QGroupBox::indicator:hover, QRadioButton::indicator:hover,
    QListWidget::indicator:hover, QTreeWidget::indicator:hover {{
        border: 2px solid {c['accent']};
        width: 12px;
        height: 12px;
    }}
    QCheckBox::indicator:checked, QGroupBox::indicator:checked,
    QListWidget::indicator:checked, QTreeWidget::indicator:checked {{
        background-color: {c['text']};
        border-color: {c['text']};
        image: url({_asset('check.svg')});
    }}
    QRadioButton::indicator:checked {{
        background-color: {c['surface']};
        border-color: {c['text']};
        image: url({_asset('radio-dot.svg')});
    }}
    QCheckBox::indicator:disabled, QGroupBox::indicator:disabled, QRadioButton::indicator:disabled,
    QListWidget::indicator:disabled, QTreeWidget::indicator:disabled {{
        background-color: {c['surface']};
        border-color: {c['text_disabled']};
    }}
    QCheckBox::indicator:checked:disabled, QGroupBox::indicator:checked:disabled,
    QListWidget::indicator:checked:disabled, QTreeWidget::indicator:checked:disabled {{
        background-color: {c['text_disabled']};
        border-color: {c['text_disabled']};
    }}
    QRadioButton::indicator:checked:disabled {{
        border-color: {c['text_disabled']};
    }}
    """


def apply_theme(app: QApplication) -> None:
    """Call once, right after constructing the ``QApplication`` (see
    ``gui/app.py``). "Fusion" is the base QStyle: the one built-in Qt style
    that renders the same, and is predictably styleable by QSS, on Linux,
    macOS and Windows."""
    app.setStyle("Fusion")
    if UI_FONT_FAMILY in load_fonts():
        font = QFont(UI_FONT_FAMILY)
        font.setPointSizeF(_UI_FONT_SIZE_PT)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, _UI_LETTER_SPACING_PX)
        app.setFont(font)
    else:  # the platform font, at Carbon's body size
        font = app.font()
        font.setPointSizeF(_UI_FONT_SIZE_PT)
        app.setFont(font)

    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(_C["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(_C["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(_C["surface"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(_C["surface_alt"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(_C["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(_C["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(_C["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(_C["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(_C["on_accent"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(_C["inverse"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(_C["on_accent"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(_C["text_muted"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(_C["accent"]))
    # Several widgets' own stylesheets use "color: palette(mid);" for muted
    # hint text; Qt's computed Mid (a bevel shade) was unreadable on this
    # light background (a user report). Mapped to text-secondary.
    palette.setColor(QPalette.ColorRole.Mid, QColor(_C["text_muted"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(_C["text_disabled"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(_C["text_disabled"]))
    app.setPalette(palette)

    app.setStyleSheet(_qss())
