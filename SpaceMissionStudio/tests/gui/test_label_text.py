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

"""Help text in every dialog stays short and readable.

Real user feedback: long help paragraphs squeezed beside or under fields
were "cramped", and several named code fields (``phasing_keeping``,
``hs_max``, docstrings). This renders every dialog (each tab, every
optional group on) and checks each visible plain-text label: at most 160
characters and no code names. Rich-text cards (device card, template
description) are structured, scrollable content and are not checked here.
"""

import re

import pytest

from test_input_borders import _CASES, _expand_everything

pytestmark = pytest.mark.requires_gui

_MAX_LABEL_CHARS = 160
_CODE_NAME = re.compile(r"\b[a-z]+_[a-z_]+\b|docstring|\w+\(\)|\bengine\.|\bschema\.")
# Where code syntax IS the content: the if/while condition is typed as a
# Python expression, so its hint has to show the names it can use.
_SYNTAX_HINTS = ("A condition, e.g.", "Available: t_s")


@pytest.fixture
def themed(qapp):
    from spacemissionstudio.gui.theme import apply_theme

    previous = qapp.styleSheet()
    apply_theme(qapp)
    yield
    qapp.setStyleSheet(previous)


def _problems(root):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    found = []
    for label in root.findChildren(QLabel):
        text = label.text().strip()
        if not label.isVisible() or not text or label.textFormat() == Qt.TextFormat.RichText or "<" in text:
            continue
        if len(text) > _MAX_LABEL_CHARS:
            found.append(f"{len(text)} chars: {text[:80]!r}")
        match = _CODE_NAME.search(text)
        if match and not text.startswith(_SYNTAX_HINTS):
            found.append(f"code name {match.group(0)!r}: {text[:80]!r}")
    return found


@pytest.mark.parametrize("factory", [factory for _, factory in _CASES], ids=[name for name, _ in _CASES])
def test_help_text_is_short_and_plain(qtbot, qapp, themed, factory):
    dialog = factory()
    qtbot.addWidget(dialog)
    dialog.resize(max(dialog.width(), 1000), max(dialog.height(), 800))  # [px]
    dialog.show()
    qtbot.waitExposed(dialog)
    problems = _problems(dialog)
    for tabs in _expand_everything(dialog, qapp):
        for index in range(tabs.count()):
            tabs.setCurrentIndex(index)
            qapp.processEvents()
            problems += [f"[{tabs.tabText(index)}] {p}" for p in _problems(dialog)]
    assert not sorted(set(problems)), "\n".join(sorted(set(problems)))
