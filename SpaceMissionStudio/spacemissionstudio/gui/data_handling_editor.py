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

"""Tables for the spacecraft editor's data handling and antenna pattern:
the instruments that fill the onboard memory, and an antenna's gain
against the angle off its boresight, as read off its datasheet."""

from __future__ import annotations

from typing import List

from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ..schema.scenario import InstrumentConfig

# (header, attribute, display factor: shown = stored * factor)
_INSTRUMENT_COLUMNS = (
    ("Name", "name", None),
    ("Data rate [kbit/s]", "data_rate_bps", 1e-3),
    ("Power [W]", "power_w", 1.0),
    ("On board at start [Gbit]", "initial_data_gbit", 1.0),
)


class _TableEditor(QWidget):
    """A table of text cells with Add and Remove buttons."""

    def __init__(self, headers: List[str], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(120)  # [px]
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add")
        self.remove_button = QPushButton("Remove")
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.add_button.clicked.connect(self._on_add)
        self.remove_button.clicked.connect(self._on_remove)

    def _append_row(self, texts: List[str]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, text in enumerate(texts):
            self.table.setItem(row, column, QTableWidgetItem(text))

    def _cell(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item is not None else ""

    def _number(self, row: int, column: int, what: str) -> float:
        text = self._cell(row, column)
        try:
            return float(text)
        except ValueError:
            header = self.table.horizontalHeaderItem(column).text()
            raise ValueError(f"{what} row {row + 1}: {header} {text!r} is not a number") from None

    def _on_add(self) -> None:
        raise NotImplementedError

    def _on_remove(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows or [self.table.rowCount() - 1]:
            if row >= 0:
                self.table.removeRow(row)


class InstrumentTableWidget(_TableEditor):
    """The instruments of a ``DataHandlingConfig``, one per row."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__([header for header, _, _ in _INSTRUMENT_COLUMNS], parent)
        self.table.setToolTip("Each instrument writes at its data rate into its own memory partition. Give an "
                              "orbit-average rate for an instrument that does not run all the time.")

    def from_list(self, instruments: List[InstrumentConfig]) -> None:
        self.table.setRowCount(0)
        for instrument in instruments:
            self._append_row([instrument.name if factor is None else f"{getattr(instrument, attribute) * factor:g}"
                              for _, attribute, factor in _INSTRUMENT_COLUMNS])

    def to_list(self) -> List[InstrumentConfig]:
        """Raises ValueError naming the cell when a number doesn't parse."""
        instruments = []
        for row in range(self.table.rowCount()):
            values = {}
            for column, (_header, attribute, factor) in enumerate(_INSTRUMENT_COLUMNS):
                if factor is None:
                    values[attribute] = self._cell(row, column)
                else:
                    values[attribute] = self._number(row, column, "Instrument") / factor
            instruments.append(InstrumentConfig(**values))
        return instruments

    def _on_add(self) -> None:
        names = {self._cell(row, 0) for row in range(self.table.rowCount())}
        name = "housekeeping" if "housekeeping" not in names else f"instrument-{self.table.rowCount() + 1}"
        self._append_row([name, "4", "0", "0"])


class GainTableWidget(_TableEditor):
    """``RFLinkConfig.antenna_gain_table``: gain against the angle off boresight."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(["Off boresight [deg]", "Gain [dBi]"], parent)
        self.table.setToolTip("Read these off the antenna's datasheet pattern, from 0 deg (boresight) up. "
                              "Gains between the rows are interpolated in dB; beyond the last row the last gain "
                              "holds.")

    def from_list(self, rows: list) -> None:
        self.table.setRowCount(0)
        for angle, gain in rows:
            self._append_row([f"{angle:g}", f"{gain:g}"])

    def to_list(self) -> list:
        """Raises ValueError naming the cell when a number doesn't parse."""
        return [[self._number(row, 0, "Antenna gain"), self._number(row, 1, "Antenna gain")]
                for row in range(self.table.rowCount())]

    def _on_add(self) -> None:
        last = self._number(self.table.rowCount() - 1, 0, "Antenna gain") if self.table.rowCount() else -30.0
        self._append_row([f"{min(last + 30.0, 180.0):g}", "0"])
