"""Tests for gui.theme."""

import pytest

pytestmark = pytest.mark.requires_gui


def test_apply_theme_runs_without_error(qapp):
    from PySide6.QtGui import QPalette

    from spacemissionstudio.gui.theme import _C, apply_theme

    apply_theme(qapp)
    assert qapp.styleSheet().strip() != ""
    # The palette's actual colors are the meaningful, stable thing to
    # check here -- app.style()'s runtime class hierarchy changes once a
    # stylesheet is active (Qt wraps the base style in a QStyleSheetStyle
    # proxy) and isn't a reliable signal to assert on.
    assert qapp.palette().color(QPalette.ColorRole.Window).name() == _C["bg"].lower()
    assert qapp.palette().color(QPalette.ColorRole.Highlight).name() == _C["accent"].lower()


def test_mid_palette_role_is_readable_not_left_at_qt_default(qapp):
    """Regression test for a real user report, with a screenshot: several
    widgets' own inline stylesheets use "color: palette(mid);" for muted
    hint/description text (see e.g. LoadScenarioWidget's template
    description) -- QPalette.Mid was never explicitly set, so it stayed
    at Qt's own computed default (a subtle 3D-bevel shading tone, not
    meant for body text), making that text unreadably low-contrast
    against this theme's light background. Must be mapped to the same
    text_muted this theme already uses for PlaceholderText, not left
    unset.
    """
    from PySide6.QtGui import QPalette

    from spacemissionstudio.gui.theme import _C, apply_theme

    apply_theme(qapp)
    assert qapp.palette().color(QPalette.ColorRole.Mid).name() == _C["text_muted"].lower()


def test_apply_theme_is_idempotent(qapp):
    """Applying the theme twice (e.g. two MainWindow instances created in
    the same process, as tests here sometimes do) must not raise or leave
    the application in a broken state.
    """
    from spacemissionstudio.gui.theme import apply_theme

    apply_theme(qapp)
    apply_theme(qapp)
    assert qapp.styleSheet().strip() != ""


def test_every_asset_the_stylesheet_references_exists():
    """The combo/spin arrows and check marks are SVG files (see theme.py's
    _ASSETS_DIR comment) -- a renamed or unpackaged one would silently
    bring back arrow-less combo boxes rather than raise anything.
    """
    import re
    from pathlib import Path

    from spacemissionstudio.gui.theme import _qss

    referenced = re.findall(r"url\(([^)]+)\)", _qss())
    assert referenced, "expected the stylesheet to reference its SVG assets"
    for path in referenced:
        assert Path(path).is_file(), path


def test_svg_asset_colors_match_the_palette():
    """The glyph SVGs hard-code their colors (QSS can't recolor an image),
    so they must be kept in step with PALETTE by hand -- this catches drift.
    """
    from pathlib import Path

    from spacemissionstudio.gui.theme import PALETTE, _ASSETS_DIR

    expected = {
        "chevron-down.svg": PALETTE["text_muted"],
        "chevron-up.svg": PALETTE["text_muted"],
        "chevron-down-disabled.svg": PALETTE["text_disabled"],
        "chevron-up-disabled.svg": PALETTE["text_disabled"],
        "check.svg": PALETTE["on_accent"],
        "radio-dot.svg": PALETTE["on_accent"],
        "tb-run.svg": PALETTE["on_accent"],
        "tb-abort.svg": PALETTE["danger"],
    }
    for name, color in expected.items():
        assert color.upper() in Path(_ASSETS_DIR / name).read_text().upper(), name


def test_every_toolbar_action_has_an_icon(qtbot):
    from spacemissionstudio.gui.main_window import MainWindow

    window = MainWindow(prompt_startup_fetch=False, check_autosave_recovery=False)
    qtbot.addWidget(window)
    from PySide6.QtWidgets import QToolBar

    for toolbar in window.findChildren(QToolBar):
        for action in toolbar.actions():
            if action.isSeparator():
                continue
            assert not action.icon().isNull(), action.text()
