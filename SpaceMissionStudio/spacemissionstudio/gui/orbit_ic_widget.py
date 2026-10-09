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

"""OrbitIcWidget: one orbit initial-condition editor covering all three
forms :class:`schema.scenario.OrbitIC` supports (classical elements,
Cartesian, TLE), switched via a combo box + stacked widget. Every field
maps 1:1 onto an ``OrbitIC`` field -- no separate GUI-only representation.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..engine import tle
from ..engine.orbit_design import DEFAULT_LTAN_HOUR, raan_for_ltan_deg, sun_synchronous_inclination_deg
from ..schema.scenario import ANOMALY_TYPES, ORBIT_IC_TYPES, OrbitIC
from .widgets import ComboBox, PreciseDoubleSpinBox

_ANOMALY_TYPE_LABELS = {
    "true": "True anomaly [deg]",
    "mean": "Mean anomaly [deg]",
}

_TYPE_LABELS = {
    "classical_elements": "Classical elements",
    "cartesian": "Cartesian state",
    "tle": "Two-Line Element (TLE)",
}


def _spin(minimum: float, maximum: float, decimals: int = 6, step: float = 1.0, value: float = 0.0) -> QDoubleSpinBox:
    box = PreciseDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(decimals)
    box.setSingleStep(step)
    box.setValue(value)
    return box


def _frame_label(kind: str) -> QLabel:
    """Frame and time scale of an orbit input (ECSS-E-ST-10-09C 5.4.1)."""
    label = QLabel("EME2000 (SPICE J2000), central body, at the scenario epoch (UTC)")
    label.setToolTip(f"The {kind} are given in the inertial frame N: Earth mean equator and equinox of "
                     "J2000 (SPICE J2000), centred on the scenario's central body, at the scenario epoch.")
    return label


class OrbitIcWidget(QWidget):
    """Emits :attr:`changed` on any edit (type switch or field value), so
    a containing form can re-validate live.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # Set by the owning dialog (see set_epoch_provider) so the
        # "Compute RAAN for LTAN..." button below always uses this
        # scenario's CURRENT epoch -- same provider pattern as
        # gui.spacecraft_editor.SpacecraftListWidget's own
        # set_central_body_provider/set_ground_station_names_provider.
        # Falls back to a fixed placeholder epoch when unset (e.g. this
        # widget used standalone in a test).
        self._epoch_provider = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.type_combo = ComboBox()
        for orbit_type in ORBIT_IC_TYPES:
            self.type_combo.addItem(_TYPE_LABELS[orbit_type], userData=orbit_type)
        self.type_combo.setToolTip(
            "How to describe where the spacecraft starts.\n\n"
            "Classical elements: size/shape/orientation of the orbit (easiest to reason "
            "about -- e.g. 'a circular orbit at 500 km, tilted 97 deg').\n"
            "Cartesian state: a raw position + velocity vector at the epoch -- use this if "
            "you already have an exact state from another tool.\n"
            "Two-Line Element (TLE): paste a real satellite's TLE (e.g. from CelesTrak) to "
            "start from its actual, currently-published orbit."
        )
        layout.addWidget(self.type_combo)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        self._build_classical_elements_page()
        self._build_cartesian_page()
        self._build_tle_page()

        self.type_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.type_combo.currentIndexChanged.connect(self.changed)

    def set_epoch_provider(self, provider) -> None:
        """``provider`` is a zero-argument callable returning this
        scenario's current ``epoch_utc`` string, e.g.
        ``lambda: self.epoch_edit.text().strip()`` from
        ``ScenarioEditorWidget`` (plumbed down through
        ``SpacecraftEditorDialog``/``SpacecraftListWidget``).
        """
        self._epoch_provider = provider

    def _build_classical_elements_page(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.sma_km = _spin(1.0, 1.0e7, decimals=3, step=10.0, value=7000.0)
        self.ecc = _spin(0.0, 0.999999, decimals=6, step=0.001)
        self.inc_deg = _spin(0.0, 180.0, decimals=4, step=1.0)
        self.raan_deg = _spin(0.0, 360.0, decimals=4, step=1.0)
        self.aop_deg = _spin(0.0, 360.0, decimals=4, step=1.0)
        self.sma_km.setToolTip(
            "Half the distance across the orbit's long axis, measured from Earth's center -- "
            "sets the orbit's SIZE and, by Kepler's third law, its PERIOD. Bigger = slower, "
            "longer orbit (e.g. ~6778 km is a ~500 km-altitude LEO with a ~95 min period; "
            "~42164 km is geostationary, one orbit per sidereal day)."
        )
        self.ecc.setToolTip(
            "How far from circular the orbit is. 0 = perfectly circular (constant altitude). "
            "Closer to 1 = a more stretched ellipse (low, fast periapsis; high, slow apoapsis). "
            "Values at or above 1 describe an escape/hyperbolic trajectory, not a closed orbit, "
            "so this field is capped below 1."
        )
        self.inc_deg.setToolTip(
            "Tilt of the orbit plane relative to Earth's equator. 0 deg = equatorial (orbits "
            "directly above the equator); 90 deg = polar (passes over both poles); around "
            "97-98 deg at low altitude gives a Sun-synchronous orbit (see the RAAN field below) "
            "that revisits the same local solar time on every pass."
        )
        self.raan_deg.setToolTip(
            "Right ascension of the ascending node -- rotates the WHOLE orbit plane around "
            "Earth's spin axis, fixing where (in inertial space) the spacecraft crosses the "
            "equator heading north. Combined with inclination, this sets which longitudes the "
            "ground track passes over and, for a Sun-synchronous orbit, the local time of day "
            "those passes happen at."
        )
        self.aop_deg.setToolTip(
            "Argument of periapsis -- rotates the ellipse's long axis WITHIN its own orbit "
            "plane, fixing where in the orbit the closest approach to Earth (periapsis) falls "
            "relative to the ascending node. Has no effect for a circular orbit (eccentricity "
            "0), since a circle has no distinct closest point."
        )
        form.addRow("Frame", _frame_label("osculating Keplerian elements"))
        form.addRow("Semi-major axis [km]", self.sma_km)
        form.addRow("Eccentricity [-]", self.ecc)
        form.addRow("Inclination [deg]", self.inc_deg)

        # Sun-synchronous helper (Phase 6 audit fix): previously, the only
        # way to reproduce 12 of the 20 bundled templates' own
        # Sun-synchronous orbit by hand was to read this project's own
        # generator-script source -- sun_synchronous_inclination_deg()/
        # raan_for_ltan_deg() (engine.orbit_design, Basilisk-free) were
        # never exposed anywhere in the GUI. These buttons compute a
        # value and WRITE it into the existing spin box above/below --
        # still editable afterward, same "compute a sane starting point,
        # let the user keep tweaking" spirit as this app's other
        # generator dialogs (e.g. "Generate Walker constellation...").
        sso_incl_button = QPushButton("Compute Sun-sync inclination for this altitude")
        sso_incl_button.setToolTip(
            "Overwrites Inclination above with the exact value whose J2 secular nodal "
            "regression rate matches the Sun's own apparent motion, computed from the "
            "Semi-major axis and Eccentricity above (engine.orbit_design"
            ".sun_synchronous_inclination_deg())."
        )
        sso_incl_button.clicked.connect(self._on_compute_sso_inclination)
        form.addRow(sso_incl_button)

        raan_ltan_row = QHBoxLayout()
        sso_raan_button = QPushButton("Compute RAAN for LTAN...")
        sso_raan_button.setToolTip(
            "Overwrites RAAN below with the value that puts this orbit's ascending node at "
            "the local time of ascending node (LTAN) entered here, at this scenario's own "
            "epoch (engine.orbit_design.raan_for_ltan_deg())."
        )
        sso_raan_button.clicked.connect(self._on_compute_sso_raan)
        self.sso_ltan_hour = _spin(0.0, 24.0, decimals=2, step=0.5, value=DEFAULT_LTAN_HOUR)
        self.sso_ltan_hour.setSuffix(" h LTAN")
        self.sso_ltan_hour.setToolTip(
            "Local time of ascending node (24h clock) -- 10.5 (10:30 AM) is the most common "
            "real choice for an Earth-observation/commercial smallsat."
        )
        raan_ltan_row.addWidget(sso_raan_button)
        raan_ltan_row.addWidget(self.sso_ltan_hour)
        form.addRow(raan_ltan_row)

        form.addRow("RAAN [deg]", self.raan_deg)
        form.addRow("Argument of periapsis [deg]", self.aop_deg)

        # One shared angle field for whichever anomaly the user wants to
        # specify -- switching the combo box just relabels what the number
        # means (see schema.scenario.OrbitIC.anomaly_type); it does NOT
        # convert the displayed value, since true and mean anomaly aren't
        # numerically close in general and silently reinterpreting a typed
        # number would be more confusing than resetting it to 0.
        self.anomaly_type_combo = ComboBox()
        for anomaly_type in ANOMALY_TYPES:
            self.anomaly_type_combo.addItem(_ANOMALY_TYPE_LABELS[anomaly_type], userData=anomaly_type)
        self.anomaly_type_combo.setToolTip(
            "How the spacecraft's starting position ALONG the orbit (below) is specified. "
            "True anomaly is the real geometric angle from periapsis -- easiest to visualize. "
            "Mean anomaly is a fictitious angle that increases at a constant rate over one "
            "orbit -- easier for picking an exact starting TIME offset, but not the same "
            "number as true anomaly except in a circular orbit. Switching this does NOT "
            "convert the typed value below (the two scales aren't numerically close in "
            "general); it resets it to 0 to avoid a silently wrong carry-over."
        )
        self.anomaly_deg = _spin(0.0, 360.0, decimals=4, step=1.0)
        self.anomaly_deg.setToolTip(
            "Where the spacecraft starts along the orbit at the epoch, as the angle type "
            "selected on the left. 0 deg = starting exactly at periapsis (closest approach)."
        )
        form.addRow(self.anomaly_type_combo, self.anomaly_deg)

        for box in (self.sma_km, self.ecc, self.inc_deg, self.raan_deg, self.aop_deg, self.anomaly_deg):
            box.valueChanged.connect(self.changed)
        self.anomaly_type_combo.currentIndexChanged.connect(self.changed)
        self.stack.addWidget(page)

    def _build_cartesian_page(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.pos_x_km = _spin(-1.0e9, 1.0e9, decimals=3, step=100.0, value=7000.0)
        self.pos_y_km = _spin(-1.0e9, 1.0e9, decimals=3, step=100.0)
        self.pos_z_km = _spin(-1.0e9, 1.0e9, decimals=3, step=100.0)
        self.vel_x_km_s = _spin(-100.0, 100.0, decimals=6, step=0.1)
        self.vel_y_km_s = _spin(-100.0, 100.0, decimals=6, step=0.1, value=7.5)
        self.vel_z_km_s = _spin(-100.0, 100.0, decimals=6, step=0.1)
        for box in (self.pos_x_km, self.pos_y_km, self.pos_z_km):
            box.setToolTip(
                "Spacecraft position at the epoch, in the inertial frame EME2000 (SPICE J2000), centred on the central body "
                "frame -- not a frame that rotates with Earth, so these numbers don't 'point' "
                "at a fixed place on the ground the way latitude/longitude would. Distance "
                "from Earth's center, not altitude above the surface."
            )
        for box in (self.vel_x_km_s, self.vel_y_km_s, self.vel_z_km_s):
            box.setToolTip(
                "Spacecraft velocity at the epoch, in the same Earth-centered inertial frame as "
                "the position above. Position and velocity together fully determine the orbit "
                "-- get either one wrong and the resulting orbit can look nothing like what "
                "you intended (e.g. a mismatched speed turns a circular orbit into a highly "
                "elliptical, or escaping, one)."
            )
        form.addRow("Frame", _frame_label("position and velocity"))
        form.addRow("Position X [km]", self.pos_x_km)
        form.addRow("Position Y [km]", self.pos_y_km)
        form.addRow("Position Z [km]", self.pos_z_km)
        form.addRow("Velocity X [km/s]", self.vel_x_km_s)
        form.addRow("Velocity Y [km/s]", self.vel_y_km_s)
        form.addRow("Velocity Z [km/s]", self.vel_z_km_s)
        for box in (self.pos_x_km, self.pos_y_km, self.pos_z_km, self.vel_x_km_s, self.vel_y_km_s, self.vel_z_km_s):
            box.valueChanged.connect(self.changed)
        self.stack.addWidget(page)

    def _build_tle_page(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.tle_line1 = QLineEdit()
        self.tle_line1.setPlaceholderText("1 25544U 98067A   24001.00000000  .00000000  00000-0  00000-0 0  9990")
        self.tle_line1.setToolTip(
            "The FIRST of a real satellite's two-line element (TLE) lines -- starts with '1', "
            "encodes its catalog number, epoch, and drag term. Copy both lines exactly as "
            "published (e.g. from CelesTrak) -- a single changed character produces a garbage "
            "or rejected orbit."
        )
        self.tle_line2 = QLineEdit()
        self.tle_line2.setPlaceholderText("2 25544  51.6400   0.0000 0000000   0.0000   0.0000 15.50000000000000")
        self.tle_line2.setToolTip(
            "The SECOND of the same satellite's two TLE lines -- starts with '2', encodes the "
            "classical orbital elements (inclination, RAAN, eccentricity, etc.) at that epoch. "
            "Must be the matching second line for the SAME satellite as line 1 above."
        )
        form.addRow("TLE line 1", self.tle_line1)
        form.addRow("TLE line 2", self.tle_line2)
        frame_note = QLabel("TEME (SGP4) -> EME2000, propagated to the scenario epoch")
        frame_note.setToolTip("SGP4 propagates the TLE from its own epoch to the scenario epoch; the state "
                              "is then rotated from TEME of date to EME2000 (IAU 1976/1980).")
        form.addRow("Frame", frame_note)
        self.tle_status = QLabel("")
        self.tle_status.setWordWrap(True)
        form.addRow("TLE epoch", self.tle_status)
        for line in (self.tle_line1, self.tle_line2):
            line.textChanged.connect(self.changed)
            line.textChanged.connect(self._refresh_tle_status)
        self.stack.addWidget(page)

    def _refresh_tle_status(self) -> None:
        """TLE epoch and its distance from the scenario epoch, or the format
        problem (checksum, length, line numbers)."""
        line1, line2 = self.tle_line1.text().strip(), self.tle_line2.text().strip()
        if not line1 or not line2:
            self.tle_status.setText("")
            return
        try:
            epoch = tle.tle_epoch_utc(tle.parse(line1, line2))
        except tle.TLEError as exc:
            self.tle_status.setText(str(exc))
            return
        text = f"{epoch:%Y-%m-%d %H:%M:%S} UTC"
        epoch_utc = (self._epoch_provider() if self._epoch_provider else "").strip()
        if epoch_utc:
            try:
                age_days = tle.state_at(line1, line2, epoch_utc).age_days
                text += f" ({abs(age_days):.1f} d {'before' if age_days >= 0 else 'after'} the scenario epoch)"
            except (tle.TLEError, ValueError) as exc:
                text += f" -- {exc}"
        self.tle_status.setText(text)

    def _on_compute_sso_inclination(self) -> None:
        value = sun_synchronous_inclination_deg(self.sma_km.value(), self.ecc.value())
        self.inc_deg.setValue(value)

    def _on_compute_sso_raan(self) -> None:
        epoch_utc = (self._epoch_provider() if self._epoch_provider else "").strip()
        if not epoch_utc:
            QMessageBox.warning(self, "No epoch set",
                                 "This scenario's Epoch (UTC) field is empty -- set a valid "
                                 "ISO 8601 epoch before computing a RAAN for LTAN.")
            return
        try:
            value = raan_for_ltan_deg(epoch_utc, self.sso_ltan_hour.value())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid epoch",
                                 f"Could not parse this scenario's Epoch (UTC) {epoch_utc!r} as a "
                                 f"valid ISO 8601 date/time: {exc}")
            return
        self.raan_deg.setValue(value)

    def to_dataclass(self) -> OrbitIC:
        orbit_type = self.type_combo.currentData()
        if orbit_type == "classical_elements":
            anomaly_type = self.anomaly_type_combo.currentData()
            return OrbitIC(
                type=orbit_type,
                semi_major_axis_km=self.sma_km.value(),
                eccentricity=self.ecc.value(),
                inclination_deg=self.inc_deg.value(),
                raan_deg=self.raan_deg.value(),
                arg_periapsis_deg=self.aop_deg.value(),
                anomaly_type=anomaly_type,
                true_anomaly_deg=self.anomaly_deg.value() if anomaly_type == "true" else None,
                mean_anomaly_deg=self.anomaly_deg.value() if anomaly_type == "mean" else None,
            )
        if orbit_type == "cartesian":
            return OrbitIC(
                type=orbit_type,
                position_km=[self.pos_x_km.value(), self.pos_y_km.value(), self.pos_z_km.value()],
                velocity_km_s=[self.vel_x_km_s.value(), self.vel_y_km_s.value(), self.vel_z_km_s.value()],
            )
        return OrbitIC(type=orbit_type, tle_line1=self.tle_line1.text(), tle_line2=self.tle_line2.text())

    def from_dataclass(self, orbit: OrbitIC) -> None:
        index = self.type_combo.findData(orbit.type)
        if index < 0:
            raise ValueError(f"OrbitIcWidget doesn't know orbit type {orbit.type!r}")
        self.type_combo.setCurrentIndex(index)
        self.stack.setCurrentIndex(index)

        if orbit.type == "classical_elements":
            self.sma_km.setValue(orbit.semi_major_axis_km or 0.0)
            self.ecc.setValue(orbit.eccentricity or 0.0)
            self.inc_deg.setValue(orbit.inclination_deg or 0.0)
            self.raan_deg.setValue(orbit.raan_deg or 0.0)
            self.aop_deg.setValue(orbit.arg_periapsis_deg or 0.0)
            anomaly_type = orbit.anomaly_type or "true"
            anomaly_index = self.anomaly_type_combo.findData(anomaly_type)
            self.anomaly_type_combo.setCurrentIndex(anomaly_index if anomaly_index >= 0 else 0)
            anomaly_value = orbit.mean_anomaly_deg if anomaly_type == "mean" else orbit.true_anomaly_deg
            self.anomaly_deg.setValue(anomaly_value or 0.0)
        elif orbit.type == "cartesian":
            pos = orbit.position_km or [0.0, 0.0, 0.0]
            vel = orbit.velocity_km_s or [0.0, 0.0, 0.0]
            self.pos_x_km.setValue(pos[0])
            self.pos_y_km.setValue(pos[1])
            self.pos_z_km.setValue(pos[2])
            self.vel_x_km_s.setValue(vel[0])
            self.vel_y_km_s.setValue(vel[1])
            self.vel_z_km_s.setValue(vel[2])
        elif orbit.type == "tle":
            self.tle_line1.setText(orbit.tle_line1 or "")
            self.tle_line2.setText(orbit.tle_line2 or "")
