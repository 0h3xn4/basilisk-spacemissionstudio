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

"""FormationDiagramWidget: draws the real along-track phasing-keeping
control mechanism -- a target separation held inside a two-tier
hysteresis band -- for ``engine.scenario_explainer.FormationDiagram``.
Drawn procedurally with :class:`QPainter` (same precedent as
``icons.py``'s own app-icon glyph: no bitmap/SVG asset to keep in sync
with the theme, no new dependency), not a bullet point or a badge --
this is the "depict the mechanism, not its name" visual a real user
asked for directly, after two earlier, more verbose Explain-tab designs
(prose, then plain bullet points) were explicitly rejected.

Deliberately static/schematic, not to real physical scale and not fed
by live telemetry (``mission_dashboard_widget.py`` already owns that):
this widget visualizes what the SCENARIO CONFIGURES -- the target
along-track separation and the trigger/restore tolerance fractions
around it -- the same information ``ScenarioExplainerWidget`` would
otherwise only show as plain numbers in the spacecraft table.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..engine.scenario_explainer import FormationDiagram
from .theme import PALETTE

_MARGIN_X = 48
_TRACK_Y_FRACTION = 0.42
_MARKER_RADIUS = 7


class FormationDiagramWidget(QWidget):
    """``set_diagram(Optional[FormationDiagram])`` -- ``None`` makes the
    widget collapse to zero height (nothing to show), mirroring
    ``ScenarioExplainerWidget``'s own "clear, don't just hide" idiom for
    optional content.
    """

    def __init__(self, diagram: FormationDiagram | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._diagram = diagram
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._apply_fixed_height()

    def set_diagram(self, diagram: FormationDiagram | None) -> None:
        self._diagram = diagram
        self._apply_fixed_height()
        self.update()

    def _apply_fixed_height(self) -> None:
        self.setFixedHeight(110 if self._diagram is not None else 0)

    def sizeHint(self) -> QSize:
        return QSize(420, 110 if self._diagram is not None else 0)

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override
        diagram = self._diagram
        if diagram is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = self.width()
        track_y = self.height() * _TRACK_Y_FRACTION
        chief_x = float(_MARGIN_X)
        # The trigger band extends tolerance_fraction * span PAST the
        # follower, so shrink the span until that band (plus a small gap)
        # still fits inside the widget instead of being cut off at its edge.
        track_span_px = min(width - 2 * _MARGIN_X,
                            (width - _MARGIN_X - 16) / (1.0 + max(diagram.tolerance_fraction, 0.0)))
        follower_x = chief_x + track_span_px
        if track_span_px <= 0:
            painter.end()
            return

        # The hysteresis band: the controller only acts once the real
        # separation drifts outside the (wider) trigger tolerance, and
        # only stops correcting once back inside the (tighter) restore
        # tolerance -- drawn as two concentric, translucent bands
        # centered on the follower's nominal target position, not just
        # mentioned as two separate numbers.
        trigger_half_km = diagram.target_separation_km * diagram.tolerance_fraction
        restore_half_km = diagram.target_separation_km * diagram.restore_tolerance_fraction
        px_per_km = track_span_px / diagram.target_separation_km if diagram.target_separation_km else 0.0
        trigger_half_px = trigger_half_km * px_per_km
        restore_half_px = restore_half_km * px_per_km

        band_height = 28.0
        band_top = track_y - band_height / 2.0

        trigger_color = QColor(PALETTE["warning"])
        trigger_color.setAlpha(45)
        painter.fillRect(
            QRectF(follower_x - trigger_half_px, band_top, 2 * trigger_half_px, band_height), trigger_color,
        )
        restore_color = QColor(PALETTE["success"])
        restore_color.setAlpha(70)
        painter.fillRect(
            QRectF(follower_x - restore_half_px, band_top, 2 * restore_half_px, band_height), restore_color,
        )

        # The along-track baseline itself, with an arrowhead showing the
        # direction of orbital motion (the follower leads the chief --
        # target_separation_km is always a positive, "follower leads
        # chief" distance, per PhasingKeepingController's own docstring).
        track_pen = QPen(QColor(PALETTE["border_strong"]))
        track_pen.setWidthF(2.0)
        painter.setPen(track_pen)
        painter.drawLine(int(chief_x), int(track_y), int(follower_x + 14), int(track_y))
        painter.drawLine(int(follower_x + 14), int(track_y), int(follower_x + 6), int(track_y - 5))
        painter.drawLine(int(follower_x + 14), int(track_y), int(follower_x + 6), int(track_y + 5))

        # Chief and follower markers.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE["text_muted"]))
        painter.drawEllipse(QRectF(chief_x - _MARKER_RADIUS, track_y - _MARKER_RADIUS,
                                    2 * _MARKER_RADIUS, 2 * _MARKER_RADIUS))
        painter.setBrush(QColor(PALETTE["accent"]))
        painter.drawEllipse(QRectF(follower_x - _MARKER_RADIUS, track_y - _MARKER_RADIUS,
                                    2 * _MARKER_RADIUS, 2 * _MARKER_RADIUS))

        # Labels: names below their markers, the measured distance above
        # the baseline between them, band legend below the track.
        painter.setPen(QColor(PALETTE["text"]))
        name_font = QFont(painter.font())
        name_font.setPointSize(max(8, name_font.pointSize() - 1))
        painter.setFont(name_font)
        painter.drawText(QRectF(chief_x - 60, track_y + 10, 120, 16), Qt.AlignmentFlag.AlignHCenter,
                          diagram.chief_name)
        painter.drawText(QRectF(follower_x - 60, track_y + 10, 120, 16), Qt.AlignmentFlag.AlignHCenter,
                          diagram.follower_name)

        distance_font = QFont(painter.font())
        distance_font.setBold(True)
        painter.setFont(distance_font)
        painter.drawText(
            QRectF(chief_x, track_y - 32, track_span_px, 16), Qt.AlignmentFlag.AlignHCenter,
            f"{diagram.target_separation_km:g} km target separation",
        )

        legend_font = QFont(painter.font())
        legend_font.setBold(False)
        legend_font.setPointSize(max(7, legend_font.pointSize() - 2))
        painter.setFont(legend_font)
        painter.setPen(QColor(PALETTE["text_muted"]))
        painter.drawText(
            QRectF(chief_x, track_y + 30, track_span_px, 16), Qt.AlignmentFlag.AlignHCenter,
            f"correction triggers past ±{diagram.tolerance_fraction * 100:g}% "
            f"({trigger_half_km:.2g} km) -- settles within ±{diagram.restore_tolerance_fraction * 100:g}% "
            f"({restore_half_km:.2g} km)",
        )

        painter.end()
