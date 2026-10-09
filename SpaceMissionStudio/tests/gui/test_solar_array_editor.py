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
"""The spacecraft editor's flexible solar arrays (SRS-F-09): what is opened
comes back unchanged, a bad cell is named, and the group is hidden where
the attitude is not simulated."""

import pytest

pytestmark = pytest.mark.requires_gui


def _spacecraft():
    from spacemissionstudio.schema.scenario import OrbitIC, SolarArrayConfig, SpacecraftConfig

    return SpacecraftConfig(
        name="flex-sat",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        dry_mass_kg=300.0,  # [kg]
        solar_arrays=[
            SolarArrayConfig("wing+y", 8.0, 2.4, 1.0, [0.0, 0.6, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
                             0.2, 0.005, initial_deflection_deg=1.5, initial_rate_deg_s=-0.25),
            SolarArrayConfig("wing-y", 8.0, 2.4, 1.0, [0.0, -0.6, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0],
                             0.2, 0.005, generates_power=False),
        ],
    )


def test_an_opened_spacecraft_comes_back_with_its_arrays_unchanged(qtbot):
    """Every array field survives opening and OK, with no edits."""
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    original = _spacecraft()
    dialog = SpacecraftEditorDialog(original)
    qtbot.addWidget(dialog)
    assert dialog.to_dataclass().solar_arrays == original.solar_arrays


def test_a_bad_array_cell_is_named_and_add_gives_a_valid_row(qtbot):
    """A vector that is not three numbers, or a yes/no that is neither,
    is refused with its row and column; a new row validates."""
    from PySide6.QtWidgets import QTableWidgetItem

    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(_spacecraft())
    qtbot.addWidget(dialog)
    table = dialog.solar_array_table.table
    table.setItem(1, 5, QTableWidgetItem("0, -1"))
    with pytest.raises(ValueError, match="Solar array row 2: Extends toward \\(x, y, z\\) '0, -1' must be three"):
        dialog.to_dataclass()
    table.setItem(1, 5, QTableWidgetItem("0, -1, 0"))
    table.setItem(0, 11, QTableWidgetItem("maybe"))
    with pytest.raises(ValueError, match="Solar array row 1: Generates power 'maybe' must be yes or no"):
        dialog.to_dataclass()
    table.setItem(0, 11, QTableWidgetItem("Yes"))
    dialog.solar_array_table.add_button.click()
    arrays = dialog.to_dataclass().solar_arrays
    assert [a.name for a in arrays] == ["wing+y", "wing-y", "wing-3"] and arrays[0].generates_power


def test_orbit_only_hides_the_arrays_and_drops_them(qtbot):
    """Without attitude there is nothing for the arrays to act on."""
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(_spacecraft(), simulation_mode="orbit_only")
    qtbot.addWidget(dialog)
    assert dialog.solar_array_group.isHidden()
    assert dialog.to_dataclass().solar_arrays == []
