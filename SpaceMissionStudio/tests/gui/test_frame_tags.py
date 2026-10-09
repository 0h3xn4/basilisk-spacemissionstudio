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
"""Position and vector inputs show their frame in the visible label, not
only in a tooltip (UX/UI guidelines, "frame, epoch and time scale beside
every input"; ECSS-E-ST-10-09C 5.3.2a: a coordinate system is identified
by a unique descriptive name)."""

import pytest
from PySide6.QtWidgets import QFormLayout, QLabel


def _form_labels(widget) -> list:
    labels = []
    for form in widget.findChildren(QFormLayout):
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if item is not None and isinstance(item.widget(), QLabel):
                labels.append(item.widget().text())
    return labels


@pytest.mark.requirement("E-ST-10-09C 5.3.2a")
def test_spacecraft_editor_vector_inputs_name_their_frame(qtbot):
    """Attitude, rate, antenna, Sun-axis, tank and panel vectors say which frame they are in."""
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    labels = _form_labels(dialog)
    for start, frame in (("sigma_BN", "EME2000"), ("omega_BN_B", "body frame"),
                         ("Antenna boresight", "body frame"), ("Axis to point at the Sun", "body frame"),
                         ("Tank position", "body frame"), ("Panel normal", "body frame")):
        matching = [label for label in labels if label.startswith(start)]
        assert matching and all(frame in label for label in matching), (start, matching)
    assert any("EME2000" in label for label in labels)  # the orbit page's frame row


@pytest.mark.requirement("E-ST-10-09C 5.3.2a")
def test_ground_station_coordinates_name_their_ellipsoid(qtbot):
    """Latitude, longitude and height say they are WGS-84 geodetic."""
    from spacemissionstudio.gui.ground_station_editor import GroundStationEditorDialog

    dialog = GroundStationEditorDialog()
    qtbot.addWidget(dialog)
    labels = _form_labels(dialog)
    for start in ("Geodetic latitude", "Longitude", "Height"):
        matching = [label for label in labels if label.startswith(start)]
        assert matching and all("WGS-84" in label for label in matching), (start, matching)
