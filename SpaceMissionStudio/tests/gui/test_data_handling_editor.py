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


"""The spacecraft editor's antenna pattern and data handling (SRS-F-15):
what is opened comes back unchanged, and the pattern shows only its own
controls."""

import pytest

pytestmark = pytest.mark.requires_gui


def _spacecraft():
    from spacemissionstudio.schema.scenario import (DataHandlingConfig, InstrumentConfig, OrbitIC, PowerConfig,
                                                    RFLinkConfig, SpacecraftConfig)

    return SpacecraftConfig(
        name="eo-sat",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        power=PowerConfig(panel_area_m2=1.0, panel_efficiency=0.29),
        rf_link=RFLinkConfig(tx_power_w=2.0, frequency_hz=2.2e9, data_rate_bps=5.0e6, antenna_pattern="table",
                             antenna_gain_table=[[0.0, 6.5], [40.0, 4.0], [90.0, -6.0]],
                             antenna_boresight_b=[-1.0, 0.0, 0.0]),
        data_handling=DataHandlingConfig(3.0, [InstrumentConfig("camera", 8.0e4, 15.0, 0.5),
                                               InstrumentConfig("housekeeping", 4.0e3)], 12.0),
    )


def test_an_opened_spacecraft_comes_back_with_its_data_handling_and_antenna_unchanged(qtbot):
    """Nothing the editor has no widget for may be dropped on OK."""
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    original = _spacecraft()
    dialog = SpacecraftEditorDialog(original)
    qtbot.addWidget(dialog)
    back = dialog.to_dataclass()
    assert back.data_handling == original.data_handling
    assert back.rf_link == original.rf_link


def test_each_pattern_shows_only_its_own_controls(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(_spacecraft())
    qtbot.addWidget(dialog)
    assert not dialog.rf_gain_table.isHidden() and dialog.rf_front_to_back_db.isHidden()
    assert not dialog.tx_antenna_gain_dbi.isEnabled()  # the table's 0 deg row is the peak
    dialog.rf_pattern_combo.setCurrentIndex(dialog.rf_pattern_combo.findData("cosine"))
    dialog.tx_antenna_gain_dbi.setValue(6.02)
    assert not dialog.rf_front_to_back_db.isHidden() and dialog.rf_gain_table.isHidden()
    assert "half-power beamwidth 120 deg" in dialog.rf_pattern_hint.text()
    sc = dialog.to_dataclass()
    assert sc.rf_link.antenna_pattern == "cosine" and sc.rf_link.antenna_gain_table == []
    dialog.rf_pattern_combo.setCurrentIndex(dialog.rf_pattern_combo.findData("fixed"))
    assert dialog.rf_pattern_hint.isHidden()


def test_a_bad_instrument_cell_is_named_and_unticking_drops_the_chain(qtbot):
    from PySide6.QtWidgets import QTableWidgetItem

    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(_spacecraft())
    qtbot.addWidget(dialog)
    dialog.dh_instruments.table.setItem(1, 1, QTableWidgetItem("fast"))
    with pytest.raises(ValueError, match="Instrument row 2: Data rate \\[kbit/s\\] 'fast' is not a number"):
        dialog.to_dataclass()
    dialog.dh_instruments.table.setItem(1, 1, QTableWidgetItem("4"))
    dialog.dh_instruments.add_button.click()
    assert [i.name for i in dialog.to_dataclass().data_handling.instruments] == ["camera", "housekeeping",
                                                                                 "instrument-3"]
    dialog.data_handling_group.setChecked(False)
    assert dialog.to_dataclass().data_handling is None
