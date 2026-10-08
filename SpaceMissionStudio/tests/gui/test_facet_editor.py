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

"""Tests for gui.facet_editor and its place in the spacecraft editor."""

import pytest

pytestmark = pytest.mark.requires_gui


def test_table_round_trips_facets(qtbot):
    from spacemissionstudio.engine.facets import box_facets
    from spacemissionstudio.gui.facet_editor import FacetTableWidget

    table = FacetTableWidget()
    qtbot.addWidget(table)
    facets = box_facets((1.2, 1.2, 1.5), 2.5, (0.0, 0.0, 1.0), (0.0, 1.5, 0.75))  # [m], [m^2]
    table.from_list(facets)
    assert table.table.rowCount() == 8
    assert table.to_list() == facets


def test_add_remove_and_a_bad_number_is_named(qtbot):
    from spacemissionstudio.gui.facet_editor import FacetTableWidget

    table = FacetTableWidget()
    qtbot.addWidget(table)
    table.add_button.click()
    table.add_button.click()
    assert [f.name for f in table.to_list()] == ["facet-1", "facet-2"]
    table.table.item(1, 1).setText("lots")
    with pytest.raises(ValueError, match="Facet row 2: Area \\[m\\^2\\] 'lots' is not a number"):
        table.to_list()
    table.remove_button.click()  # no selection: removes the last row
    assert [f.name for f in table.to_list()] == ["facet-1"]


def test_box_dialog_builds_the_box_and_array(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui import facet_editor

    table = facet_editor.FacetTableWidget()
    qtbot.addWidget(table)

    def accept_with_offset(dialog):
        dialog.loc_y.setValue(1.5)  # [m]
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(facet_editor.BoxFacetDialog, "exec", accept_with_offset)
    table.box_button.click()
    facets = table.to_list()
    assert len(facets) == 8
    assert facets[-1].name == "array back" and facets[-1].location_b == [0.0, 1.5, 0.75]


def test_spacecraft_dialog_keeps_its_facets_on_ok(qtbot):
    """The facet list must survive opening and accepting the spacecraft
    editor unchanged, like every other optional block."""
    from spacemissionstudio.engine.spacecraft_templates import SPACECRAFT_TEMPLATES
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    config = next(t for t in SPACECRAFT_TEMPLATES if "300 kg" in t.name).build()
    dialog = SpacecraftEditorDialog(config)
    qtbot.addWidget(dialog)
    assert dialog.to_dataclass().facets == config.facets
