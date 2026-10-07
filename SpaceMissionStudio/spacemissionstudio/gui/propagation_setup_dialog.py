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

"""PropagationSetupDialog: one dedicated window for everything that governs
HOW a scenario's orbits propagate -- central body, gravity model (point
-mass vs. spherical harmonics, third-body point-mass perturbers), the
integrator/step/duration, and the space-weather source that drives
atmospheric drag. Previously these lived as three separate, always-visible
group boxes inline in the main scenario form; user feedback specifically
asked for "a full and comprehensive propagate setup window" plus the
ability to switch each perturbation on/off individually.

Every perturbation this app actually wires up in ``engine.service`` gets
its own explicit enable control here:

* spherical-harmonics gravity -- ``enable_harmonics_check`` (new; see its
  own comment below for why it's a GUI-only concept, not a new schema
  field)
* third-body point-mass gravity -- one checkbox per body in
  ``third_body_list`` (existing, moved here unchanged)
* atmospheric drag / solar radiation pressure -- these are PER
  -SPACECRAFT, not scenario-wide (a spacecraft's own cross-section/
  coefficient are needed either way), so they stay on
  ``gui.spacecraft_editor.SpacecraftEditorDialog``'s "Orbit / mass" tab
  (``enable_drag``/``enable_srp``) -- already present, and already
  reachable in "orbit_only" (cannonball) mode since that tab is never
  hidden for that mode. Real user report: this wasn't discoverable --
  looking for SRP specifically in THIS dialog and not finding it read as
  "SRP isn't supported", not "it's one dialog over". Fixed with an
  explicit ``QLabel`` pointer in the space-weather group below (never
  found by reading this module's own docstring, which the user never
  sees) rather than moving the per-spacecraft fields here, which would
  need a spacecraft-picker of its own and duplicate
  ``SpacecraftEditorDialog``'s existing one.
* atmosphere-model CHOICE (``atmosphere_model_combo``) and a
  CONSERVATIVE, historical-percentile drag margin
  (``activity_level_combo``/``activity_percentile_spin``) -- see
  ``schema.scenario.SpaceWeatherConfig``'s own docstring for exactly
  what each selects and why (Basilisk has no Jacchia-Roberts model to
  offer, checked directly against its source; the percentile margin is
  computed from real historical F10.7/Ap data the user supplies via a
  local file). This dialog itself makes no network calls -- there is no
  "celestrak" source option here, only "local_file"/"synthetic" -- but
  its Local file field pre-fills with the path of the most recent
  startup-time fetch (``gui.startup_fetch_dialog``, a real CelesTrak CSV,
  only ever downloaded after the user explicitly agreed to it) when one
  exists and the scenario doesn't already have its own path set; see
  ``engine.spaceweather``'s own "Closed-off/offline policy" docstring.

Construct with the scenario's current ``GravityConfig``/``SimSettings``/
``SpaceWeatherConfig``, then read back the (possibly unchanged) values via
:meth:`to_gravity`/:meth:`to_sim_settings`/:meth:`to_space_weather` after
``exec()`` returns ``Accepted``. Never mutates the dataclasses it was
constructed with -- ``gui.scenario_editor.ScenarioEditorWidget`` only
replaces its own stored copies once the user actually clicks OK.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..schema.scenario import (
    SUPPORTED_CENTRAL_BODIES,
    SUPPORTED_INTEGRATORS,
    GravityConfig,
    ScenarioValidationError,
    SimSettings,
    SpaceWeatherConfig,
)
from .widgets import PreciseDoubleSpinBox

# The minimum spherical-harmonics degree/order that's actually meaningful
# ("spherical harmonics" starting below this is just point-mass again) --
# used only as a friendly default when the user checks the enable box
# while the degree spinner is still at 0, never enforced as a hard floor
# (GravityConfig.validate() only requires >= 0).
_DEFAULT_HARMONICS_DEGREE = 2

# Wrap width for this dialog's explanatory labels -- keeps the dialog a
# comfortable reading width instead of one label's single-line length.
_CONTENT_WIDTH = 600


class PropagationSetupDialog(QDialog):
    def __init__(self, gravity: GravityConfig, sim_settings: SimSettings, space_weather: SpaceWeatherConfig,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Propagation setup")

        layout = QVBoxLayout(self)

        # Everything but the OK/Cancel row lives in a QScrollArea: the
        # three groups together need ~800 px of height, more than a
        # common 768/800 px-tall laptop screen offers -- found by
        # rendering this dialog on an 800 px screen, where the window
        # manager clamped the window and Qt squashed the last group's
        # rows until their text was cut off. Scrolling degrades cleanly
        # instead; on a taller screen the dialog simply opens at full size.
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        intro_label = QLabel(
            "Everything that governs how this scenario's orbits propagate: the gravity model, "
            "which perturbations are active, the numerical integrator, and the space-weather data "
            "atmospheric drag uses."
        )
        intro_label.setWordWrap(True)
        # A word-wrapped QLabel's sizeHint() reports the width needed to
        # lay the text out on ONE line unless something else constrains
        # it -- without this cap, this label alone stretched the whole
        # dialog to ~1360px wide.
        intro_label.setMaximumWidth(_CONTENT_WIDTH)
        content_layout.addWidget(intro_label)

        content_layout.addWidget(self._build_gravity_group(gravity))
        content_layout.addWidget(self._build_sim_settings_group(sim_settings))
        content_layout.addWidget(self._build_space_weather_group(space_weather))
        content_layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # A QScrollArea's own sizeHint() is a small arbitrary default, not
        # its content's real size, so size the window from the CONTENT
        # (computed after every group exists), capped to the screen.
        content_hint = content.sizeHint()
        margins = layout.contentsMargins()
        width = content_hint.width() + margins.left() + margins.right() + scroll.verticalScrollBar().sizeHint().width()
        height = (content_hint.height() + buttons.sizeHint().height() + layout.spacing()
                  + margins.top() + margins.bottom())
        screen = self.screen() if self.screen() is not None else QApplication.primaryScreen()
        if screen is not None:
            height = min(height, int(screen.availableGeometry().height() * 0.9))
        self.resize(width, height)

    # -- construction ---------------------------------------------------------
    def _build_gravity_group(self, gravity: GravityConfig) -> QGroupBox:
        group = QGroupBox("Gravity")
        form = QFormLayout(group)

        self.central_body_combo = QComboBox()
        self.central_body_combo.addItems(SUPPORTED_CENTRAL_BODIES)
        self.central_body_combo.setCurrentText(gravity.central_body)
        self.central_body_combo.setToolTip(
            "Which body's gravity dominates this scenario's orbit -- every spacecraft's "
            "position/velocity is relative to this body, and it's what 'altitude' means "
            "throughout this app. Changing it also changes which bodies are even available as "
            "third-body perturbers below (a body can't perturb itself)."
        )
        self.central_body_combo.currentTextChanged.connect(self._on_central_body_changed)
        form.addRow("Central body", self.central_body_combo)

        # Spherical-harmonics gravity: an explicit enable checkbox, SEPARATE
        # from the degree/order value itself -- schema.scenario.GravityConfig
        # still only has ONE field for this (central_body_degree == 0 means
        # point-mass, exactly as before; no schema/migration change), but a
        # bare spin box with no enable control meant unchecking it required
        # zeroing out (and losing) whatever degree/order the user had typed.
        # to_gravity() below folds this checkbox back into that one field.
        self.enable_harmonics_check = QCheckBox("Enable spherical-harmonics gravity (Earth only)")
        self.enable_harmonics_check.setChecked(gravity.central_body_degree > 0)
        self.enable_harmonics_check.toggled.connect(self._on_harmonics_toggled)
        form.addRow(self.enable_harmonics_check)

        self.central_body_degree_spin = QSpinBox()
        self.central_body_degree_spin.setRange(0, 360)
        self.central_body_degree_spin.setValue(
            gravity.central_body_degree if gravity.central_body_degree > 0 else _DEFAULT_HARMONICS_DEGREE
        )
        self.central_body_degree_spin.setToolTip(
            "How many terms of the real gravity field to include -- higher captures finer "
            "mass-distribution detail at the cost of more compute per step. Degree 2 alone "
            "already captures J2 (by far the dominant term); low double digits (e.g. 8-10) is "
            "a common practical choice for most mission-design work."
        )
        form.addRow("Degree/order", self.central_body_degree_spin)

        self.third_body_list = QListWidget()
        self.third_body_list.setFixedHeight(130)
        self.third_body_list.setToolTip(
            "Other bodies whose OWN gravity also pulls on the spacecraft (in addition to the "
            "central body above) -- e.g. checking 'sun'/'moon' for an Earth-orbiting "
            "spacecraft adds real lunisolar perturbation, which matters more the higher the "
            "orbit (negligible in low LEO, significant at GEO and beyond)."
        )
        form.addRow("Third-body perturbers", self.third_body_list)
        self._refresh_third_body_choices(gravity.third_body_perturbers)

        self._on_central_body_changed(gravity.central_body)  # applies the Earth-only harmonics gate immediately
        return group

    def _on_central_body_changed(self, text: str) -> None:
        self._refresh_third_body_choices()
        is_earth = text == "earth"
        # Spherical harmonics here is Earth-only (engine.service.build()
        # only has a gravity-field data file for Earth -- GGM03S -- and
        # raises a clear SimulationServiceError for any other central body
        # with central_body_degree > 0). Disabling it here means the GUI
        # can never construct that invalid combination in the first place,
        # rather than letting the user discover it only when a run fails.
        self.enable_harmonics_check.setEnabled(is_earth)
        if not is_earth:
            self.enable_harmonics_check.setChecked(False)
        self.central_body_degree_spin.setEnabled(is_earth and self.enable_harmonics_check.isChecked())
        base_tooltip = (
            "Checking this ON replaces the idealized point-mass gravity model with Earth's "
            "real, lumpy mass distribution (the GGM03S gravity field) -- this is what makes "
            "effects like J2 nodal/apsidal precession real rather than absent, and is REQUIRED "
            "for a genuine Sun-synchronous orbit to actually stay Sun-synchronous over time. "
            "Point-mass gravity alone (this unchecked) has no such precession at all."
        )
        tooltip = base_tooltip if is_earth else "Spherical-harmonics gravity is only wired up for Earth (GGM03S data)."
        self.enable_harmonics_check.setToolTip(tooltip)

    def _on_harmonics_toggled(self, checked: bool) -> None:
        self.central_body_degree_spin.setEnabled(checked)
        if checked and self.central_body_degree_spin.value() == 0:
            self.central_body_degree_spin.setValue(_DEFAULT_HARMONICS_DEGREE)

    def _refresh_third_body_choices(self, checked: list | None = None) -> None:
        checked = set(checked) if checked is not None else self._checked_third_bodies()
        central = self.central_body_combo.currentText()
        self.third_body_list.blockSignals(True)
        self.third_body_list.clear()
        for body in SUPPORTED_CENTRAL_BODIES:
            if body == central:
                continue
            item = QListWidgetItem(body)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if body in checked else Qt.CheckState.Unchecked)
            self.third_body_list.addItem(item)
        self.third_body_list.blockSignals(False)

    def _checked_third_bodies(self) -> list:
        result = []
        for i in range(self.third_body_list.count()):
            item = self.third_body_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.text())
        return result

    def _build_sim_settings_group(self, sim_settings: SimSettings) -> QGroupBox:
        group = QGroupBox("Simulation settings")
        form = QFormLayout(group)

        self.duration_days_spin = PreciseDoubleSpinBox()
        self.duration_days_spin.setRange(0.0001, 100000.0)
        self.duration_days_spin.setDecimals(4)
        self.duration_days_spin.setValue(sim_settings.duration_days)
        self.duration_days_spin.setToolTip(
            "Total simulated time, starting from the epoch. Longer means more wall-clock run "
            "time (roughly proportional to duration / task rate below) and a bigger recorded "
            "dataset -- pick just enough to see what you're looking for (e.g. a few orbits for "
            "a quick geometry check, weeks/months for a real decay/station-keeping study)."
        )
        form.addRow("Duration [days]", self.duration_days_spin)

        self.task_rate_spin = PreciseDoubleSpinBox()
        self.task_rate_spin.setRange(0.001, 1.0e6)
        self.task_rate_spin.setDecimals(3)
        self.task_rate_spin.setValue(sim_settings.dynamics_task_rate_s)
        self.task_rate_spin.setToolTip(
            "How often the dynamics are integrated and recorded -- the real numerical time "
            "step. Smaller = finer resolution and better numerical accuracy, but more compute "
            "(more steps for the same duration). A fast-moving/rotating spacecraft (active "
            "attitude control, a fast orbit) typically needs a smaller rate than a slow, "
            "coasting one to stay both accurate and stable."
        )
        form.addRow("Dynamics task rate [s]", self.task_rate_spin)

        self.integrator_combo = QComboBox()
        self.integrator_combo.addItems(SUPPORTED_INTEGRATORS)
        self.integrator_combo.setCurrentText(sim_settings.integrator)
        self.integrator_combo.setToolTip(
            "The numerical method used to step the dynamics forward in time. 'euler'/'rk2' are "
            "simple, lower-order fixed-step methods -- fast per step, but need a smaller task "
            "rate above to stay accurate. 'rkf45'/'rkf78' are higher-order Runge-Kutta-Fehlberg "
            "methods -- more accurate per step, the better default choice for most scenarios "
            "(rkf78 is this app's own default)."
        )
        form.addRow("Integrator", self.integrator_combo)

        return group

    def _build_space_weather_group(self, space_weather: SpaceWeatherConfig) -> QGroupBox:
        # "&&", not "&": Qt treats a single "&" in a QGroupBox title as a
        # mnemonic marker (it consumes the "&" and underlines the next
        # character instead of showing it) -- confirmed by actually
        # rendering this dialog and looking at the PNG, where the plain
        # "&" version rendered as a visibly broken "Atmosphere _drag".
        # "&&" is Qt's own documented escape for a literal "&" character.
        group = QGroupBox("Atmosphere && drag")
        group_layout = QVBoxLayout(group)

        # Real user report: looked for solar radiation pressure in THIS
        # dialog, didn't find it, read that as "not supported" -- it's a
        # per-spacecraft field (needs that spacecraft's own cross-section/
        # coefficient either way), on SpacecraftEditorDialog's "Orbit /
        # mass" tab instead. See this module's own docstring for the full
        # reasoning on why it stays there rather than moving here.
        #
        # Added via group_layout.addWidget(), NOT form.addRow(): a real
        # rendering bug, found by actually looking at this dialog (not
        # just reading the code) -- QFormLayout.addRow() given a single
        # spanning widget did not reserve this label its full wrapped
        # height (confirmed directly: geometry().height() was 27px while
        # the label's own heightForWidth(520) said it needed 68px), so
        # two of its three lines were silently clipped off. A plain
        # QVBoxLayout.addWidget(), the same mechanism this dialog's own
        # top-level intro_label already uses successfully, doesn't have
        # that negotiation problem.
        srp_pointer = QLabel(
            "Atmospheric drag and solar radiation pressure are set PER SPACECRAFT (each needs that "
            "spacecraft's own cross-section/coefficient) -- open a spacecraft in the scenario's "
            "spacecraft list and look at its \"Orbit / mass\" tab, not here."
        )
        srp_pointer.setWordWrap(True)
        srp_pointer.setMaximumWidth(_CONTENT_WIDTH)
        group_layout.addWidget(srp_pointer)

        form = QFormLayout()
        group_layout.addLayout(form)

        self.atmosphere_model_combo = QComboBox()
        # (display text, schema value) -- SpaceWeatherConfig.atmosphere_model's
        # own docstring explains why these two and not, say, Jacchia-Roberts
        # (Basilisk has no such model at all).
        self._atmosphere_model_items = [("NRLMSISE-00 (real space weather)", "nrlmsise00"),
                                         ("Exponential (simple, no space weather)", "exponential")]
        for label, _value in self._atmosphere_model_items:
            self.atmosphere_model_combo.addItem(label)
        self.atmosphere_model_combo.setCurrentIndex(
            0 if space_weather.atmosphere_model == "nrlmsise00" else 1
        )
        self.atmosphere_model_combo.setToolTip(
            "What atmospheric density model drag (see each spacecraft's own 'Enable "
            "atmospheric drag' checkbox) is actually computed from. NRLMSISE-00 is a real, "
            "physically-detailed density model that responds to solar/geomagnetic activity "
            "(set via Source/Drag margin below); Exponential is a much simpler fallback with "
            "no space-weather dependence at all -- only use it when you specifically want to "
            "isolate drag's effect from solar-cycle variability."
        )
        self.atmosphere_model_combo.currentIndexChanged.connect(self._on_atmosphere_model_changed)
        form.addRow("Atmosphere model", self.atmosphere_model_combo)

        self.space_weather_source_combo = QComboBox()
        self.space_weather_source_combo.addItems(["synthetic", "local_file"])
        self.space_weather_source_combo.setCurrentText(space_weather.source)
        self.space_weather_source_combo.setToolTip(
            "Where NRLMSISE-00's solar/geomagnetic activity inputs (F10.7, Ap) come from. "
            "'synthetic' generates a nominal, solar-cycle-SHAPED profile locally -- plausible "
            "but not a real historical record, and the only option that needs no extra setup. "
            "'local_file' reads real historical data from a CSV you supply yourself (this app "
            "makes no network calls at runtime -- see the field below)."
        )
        self.space_weather_source_combo.currentTextChanged.connect(self._on_space_weather_source_changed)
        form.addRow("Source", self.space_weather_source_combo)

        local_file_row = QHBoxLayout()
        # Pre-fills with the most recently startup-fetched CelesTrak CSV
        # (see gui.startup_fetch_dialog) when the scenario doesn't already
        # have its own local_file_path set -- a real user-visible fetch
        # that produces a local file nobody can actually USE unless they
        # know its path isn't much of a convenience. Still just a
        # suggestion: the field stays plain text, editable/clearable like
        # any other, and nothing here touches the network -- it only
        # checks whether a previous fetch already left a file on disk.
        initial_local_file_path = space_weather.local_file_path
        if not initial_local_file_path:
            from ..engine import spaceweather as sw
            cached = sw.cached_fetch_path()
            if cached is not None:
                initial_local_file_path = str(cached)
        self.local_file_edit = QLineEdit(initial_local_file_path or "")
        self.local_file_edit.setToolTip(
            "Path to a real historical space-weather CSV (e.g. a CelesTrak F10.7/Ap extract "
            "you downloaded ahead of time) -- only read when Source above is 'local_file'; "
            "ignored otherwise. This app never fetches this itself at run time."
        )
        self.local_file_edit.setPlaceholderText("only used when Source is local_file")
        self.local_file_browse_button = QPushButton("Browse...")
        self.local_file_browse_button.clicked.connect(self._on_browse_local_file)
        local_file_row.addWidget(self.local_file_edit)
        local_file_row.addWidget(self.local_file_browse_button)
        form.addRow("Local CSV file", local_file_row)

        self.activity_level_combo = QComboBox()
        # (display text, schema value)
        self._activity_level_items = [("Nominal (ordinary resolved space weather)", "nominal"),
                                       ("Conservative (historical-percentile worst-case margin)", "conservative")]
        for label, _value in self._activity_level_items:
            self.activity_level_combo.addItem(label)
        self.activity_level_combo.setCurrentIndex(0 if space_weather.activity_level == "nominal" else 1)
        self.activity_level_combo.setToolTip(
            "'Nominal' uses the resolved space-weather profile (from Source above) as-is -- "
            "day-to-day variation included. 'Conservative' instead holds activity at a fixed, "
            "sustained high percentile (set below) for the WHOLE scenario -- a worst-case "
            "margin for drag-sensitive design questions (e.g. minimum propellant for station "
            "-keeping), at the cost of being less representative of an ordinary day."
        )
        self.activity_level_combo.currentIndexChanged.connect(self._on_activity_level_changed)
        form.addRow("Drag margin", self.activity_level_combo)

        self.activity_percentile_spin = PreciseDoubleSpinBox()
        self.activity_percentile_spin.setRange(50.0, 99.9)
        self.activity_percentile_spin.setDecimals(1)
        self.activity_percentile_spin.setValue(space_weather.activity_percentile)
        self.activity_percentile_spin.setToolTip(
            "Percentile of REAL historical F10.7/Ap data to hold constant across the whole scenario as "
            "a sustained worst-case drag assumption -- 95.0 is a common 'P95' choice; ~97.7 approximates "
            "a mean+2-sigma figure. This app makes no network calls at runtime, so 'Conservative' needs "
            "Source above set to 'local_file', pointing at a real historical space-weather CSV you "
            "supply yourself (e.g. a CelesTrak extract downloaded ahead of time, outside this app)."
        )
        form.addRow("Worst-case percentile", self.activity_percentile_spin)

        # cache_dir: internal-infra override, not a mission-design knob --
        # see SpaceWeatherConfig.cache_dir's own comment. Blank (the
        # common case) keeps the None default, which lets
        # engine.spaceweather pick its own cache directory. Rarely
        # needed; included here only so a value already set on a
        # hand-edited scenario round-trips instead of being silently
        # dropped on save (same reasoning as every other optional field
        # in this dialog).
        self.cache_dir_edit = QLineEdit(space_weather.cache_dir or "")
        self.cache_dir_edit.setPlaceholderText("(default cache directory)")
        self.cache_dir_edit.setToolTip(
            "Overrides where engine.spaceweather caches fetched space-weather data on disk. "
            "Rarely needed -- leave blank unless you specifically need a non-default cache "
            "location (e.g. a read-only home directory)."
        )
        form.addRow("Cache directory (advanced)", self.cache_dir_edit)

        self._on_atmosphere_model_changed(self.atmosphere_model_combo.currentIndex())
        self._on_space_weather_source_changed(self.space_weather_source_combo.currentText())
        self._on_activity_level_changed(self.activity_level_combo.currentIndex())
        return group

    def _on_atmosphere_model_changed(self, _index: int) -> None:
        is_msis = self._selected_atmosphere_model() == "nrlmsise00"
        # Exponential ignores source/local_file_path/activity_level entirely
        # (schema.scenario.SpaceWeatherConfig's own docstring) -- greyed
        # out rather than hidden, so switching back doesn't lose whatever
        # the user had set.
        self.space_weather_source_combo.setEnabled(is_msis)
        self.local_file_edit.setEnabled(is_msis and self.space_weather_source_combo.currentText() == "local_file")
        self.local_file_browse_button.setEnabled(
            is_msis and self.space_weather_source_combo.currentText() == "local_file"
        )
        self.activity_level_combo.setEnabled(is_msis)
        self.activity_percentile_spin.setEnabled(is_msis and self._selected_activity_level() == "conservative")

    def _on_activity_level_changed(self, _index: int) -> None:
        is_msis = self._selected_atmosphere_model() == "nrlmsise00"
        self.activity_percentile_spin.setEnabled(is_msis and self._selected_activity_level() == "conservative")

    def _selected_atmosphere_model(self) -> str:
        return self._atmosphere_model_items[self.atmosphere_model_combo.currentIndex()][1]

    def _selected_activity_level(self) -> str:
        return self._activity_level_items[self.activity_level_combo.currentIndex()][1]

    def _on_space_weather_source_changed(self, source: str) -> None:
        is_msis = self._selected_atmosphere_model() == "nrlmsise00"
        self.local_file_edit.setEnabled(is_msis and source == "local_file")
        self.local_file_browse_button.setEnabled(is_msis and source == "local_file")

    def _on_browse_local_file(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Select space-weather CSV", "", "CSV files (*.csv)")
        if path:
            self.local_file_edit.setText(path)

    # -- (dis)assembly -------------------------------------------------------
    def to_gravity(self) -> GravityConfig:
        return GravityConfig(
            central_body=self.central_body_combo.currentText(),
            central_body_degree=(
                self.central_body_degree_spin.value() if self.enable_harmonics_check.isChecked() else 0
            ),
            third_body_perturbers=self._checked_third_bodies(),
        )

    def to_sim_settings(self) -> SimSettings:
        return SimSettings(
            duration_days=self.duration_days_spin.value(),
            dynamics_task_rate_s=self.task_rate_spin.value(),
            integrator=self.integrator_combo.currentText(),
        )

    def to_space_weather(self) -> SpaceWeatherConfig:
        return SpaceWeatherConfig(
            source=self.space_weather_source_combo.currentText(),
            local_file_path=self.local_file_edit.text().strip() or None,
            cache_dir=self.cache_dir_edit.text().strip() or None,
            atmosphere_model=self._selected_atmosphere_model(),
            activity_level=self._selected_activity_level(),
            activity_percentile=self.activity_percentile_spin.value(),
        )

    def _on_accept(self) -> None:
        try:
            self.to_gravity().validate()
            self.to_sim_settings().validate()
            self.to_space_weather().validate()
        except ScenarioValidationError as exc:
            QMessageBox.critical(self, "Invalid propagation setup", str(exc))
            return
        self.accept()
