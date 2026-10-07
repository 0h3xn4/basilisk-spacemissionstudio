"""Tests for gui.spacecraft_editor."""

import pytest

pytestmark = pytest.mark.requires_gui


def test_dialog_default_spacecraft(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    sc = dialog.to_dataclass()
    assert sc.name == "sat-1"
    assert sc.orbit.type == "classical_elements"
    assert sc.inertia_kg_m2 == [10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0]


def test_dialog_every_tab_is_independently_scrollable(qtbot):
    """Regression test: QTabWidget sizes EVERY tab page to fit whichever
    page is tallest (its internal QStackedWidget's size hint is the max
    across ALL pages, not just the current one) -- without each tab
    wrapped in its own QScrollArea, the "Power / propulsion / link
    budget" tab (five stacked group boxes) forced every other tab,
    including "Orbit / mass", to render with a huge dead-space gap and
    made the whole dialog's natural size well over 1000px tall. Caught by
    actually rendering the dialog and looking at it, not from reading the
    layout code.
    """
    from PySide6.QtWidgets import QScrollArea

    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    for i in range(dialog.tabs.count()):
        assert isinstance(dialog.tabs.widget(i), QScrollArea), f"tab {i} ({dialog.tabs.tabText(i)!r}) isn't scrollable"


def test_long_description_labels_wrap_instead_of_blowing_up_dialog_width(qtbot):
    """Regression guard for a real bug, found via an actual user
    screenshot of gui.phasing_formation_dialog.PhasingFormationDialog
    (same copy-pasted top-description-QLabel shape, same missing
    word-wrap): the Vizard-model tab's own description QLabel had the
    identical problem. See that dialog's own test docstring for the
    full explanation of what goes wrong without setWordWrap(True).
    """
    from PySide6.QtWidgets import QLabel

    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)

    description_labels = [w for w in dialog.findChildren(QLabel) if len(w.text()) > 100]
    assert description_labels, "expected to find at least one long description QLabel"
    assert all(w.wordWrap() for w in description_labels)


def test_dialog_natural_size_stays_reasonable(qtbot):
    """A loose upper bound, not a pixel-exact check: guards against the
    whole-dialog-height blowing up again (it briefly reached ~1450px
    tall before the per-tab QScrollArea fix -- see the test above) without
    being so tight that an unrelated, legitimate content change trips it.
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)
    assert dialog.sizeHint().height() < 800


def test_dialog_opens_at_a_usable_size_not_just_a_reasonable_upper_bound(qtbot):
    """Regression test for a real bug, found from a user screenshot: with
    no explicit resize() anywhere in this class, the dialog opened so
    small that even its own first tab's Name/Dry mass rows were clipped
    behind scrollbars -- QDialog.sizeHint() is dominated by each tab's
    QScrollArea (see test_dialog_every_tab_is_independently_scrollable's
    own docstring for why every tab has one), whose OWN sizeHint() is a
    small, mostly-arbitrary default, not the wrapped content's real size
    (confirmed directly: this dialog's sizeHint() measured 530x416 while
    its "Orbit / mass" tab content alone needed 572x789). The test above
    only guards the UPPER bound (it must not blow back up past ~800px
    tall) -- this one guards the other direction, that it doesn't collapse
    back down to that tiny broken size either.
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)
    # Not pixel-exact (the real fix computes width from each tab's own
    # content, which could legitimately shift with future tab content
    # changes) -- wide/tall enough that "Orbit / mass"'s Name/Dry mass
    # rows and every tab label are visibly usable without scrolling.
    assert dialog.size().width() >= 600
    assert dialog.size().height() >= 600


def test_dialog_edits_existing_config(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-existing",
        orbit=OrbitIC(type="cartesian", position_km=[1.0, 2.0, 3.0], velocity_km_s=[4.0, 5.0, 6.0]),
        dry_mass_kg=250.0,
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    got = dialog.to_dataclass()
    assert got.name == "sat-existing"
    assert got.dry_mass_kg == 250.0
    assert got.orbit.position_km == [1.0, 2.0, 3.0]


def test_dialog_round_trips_sensors_actuators_and_fsw_mode(qtbot):
    """Regression test: editing an existing spacecraft used to silently
    DROP sensors/actuators/fsw_mode/fsw_params/control_params (the dialog
    built a brand new SpacecraftConfig without passing them through). This
    is exactly the round trip that bug broke.
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import ActuatorConfig, OrbitIC, SensorConfig, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-with-fsw",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        sensors=[SensorConfig(kind="star_tracker", name="st-1", params={"noise_arcsec": 5.0})],
        actuators=[ActuatorConfig(kind="reaction_wheel", name="rw-1", params={"gsHat_B": [1, 0, 0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0})],
        fsw_mode="hillPoint",
        fsw_params={"foo": "bar"},
        control_params={"K": 4.0, "P": 25.0},
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    got = dialog.to_dataclass()

    assert len(got.sensors) == 1
    assert got.sensors[0].kind == "star_tracker"
    assert got.sensors[0].params == {"noise_arcsec": 5.0}
    assert len(got.actuators) == 1
    assert got.actuators[0].params == {"gsHat_B": [1, 0, 0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0}
    assert got.fsw_mode == "hillPoint"
    assert got.fsw_params == {"foo": "bar"}
    assert got.control_params == {"K": 4.0, "P": 25.0}


def test_dialog_defaults_fsw_mode_to_none(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    sc = dialog.to_dataclass()
    assert sc.fsw_mode is None
    assert sc.sensors == []
    assert sc.actuators == []


def test_dialog_catches_missing_locationpointing_target_immediately(qtbot):
    """Regression test: locationPointing's required
    fsw_params['target_ground_station'] used to only be caught deep inside
    engine.fsw at Run Simulation time (an FswError with no connection back
    to this dialog), or not at all if the scenario was never actually run.
    This dialog should catch it itself, right where the params box is.
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    index = dialog.fsw_mode_combo.findData("locationPointing")
    dialog.fsw_mode_combo.setCurrentIndex(index)
    dialog.fsw_param_form.include_box("target_ground_station").setChecked(False)  # no target at all

    with pytest.raises(ValueError, match="target_ground_station"):
        dialog.to_dataclass()


def test_dialog_fsw_reset_template_fills_working_example(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    index = dialog.fsw_mode_combo.findData("locationPointing")
    dialog.fsw_mode_combo.setCurrentIndex(index)
    dialog._on_fsw_reset_template()

    sc = dialog.to_dataclass()
    assert "target_ground_station" in sc.fsw_params


def test_dialog_fsw_hint_updates_with_mode(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert "no attitude control" in dialog.fsw_hint_label.text().lower()

    assert dialog.fsw_params_group.isHidden()

    index = dialog.fsw_mode_combo.findData("locationPointing")
    dialog.fsw_mode_combo.setCurrentIndex(index)
    assert "ground station" in dialog.fsw_hint_label.text()
    assert not dialog.fsw_params_group.isHidden()
    assert set(dialog.fsw_param_form.fields) == {"target_ground_station", "target_body", "pHat_B"}


def test_attitude_tab_is_a_form_not_bullets_over_json(qtbot):
    """Real user feedback on the Attitude control tab ("another bad UI/UX
    example"): a bullet list of keys above two raw JSON boxes. Each
    parameter and gain is now a labelled row; the JSON boxes are only a
    collapsed "Advanced" area for keys the form doesn't cover."""
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(ground_station_names=["berlin", "kiruna"])
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("sat-1")
    dialog.fsw_mode_combo.setCurrentIndex(dialog.fsw_mode_combo.findData("locationPointing"))
    assert "•" not in dialog.fsw_hint_label.text()
    assert dialog.fsw_params_edit.isHidden() and dialog.control_params_edit.isHidden()

    # The ground-station row lists the scenario's stations.
    station = dialog.fsw_param_form.widget("target_ground_station")
    assert [station.itemText(i) for i in range(station.count())] == ["berlin", "kiruna"]
    station.setCurrentText("kiruna")
    # Exactly one target: ticking the body unticks the station.
    dialog.fsw_param_form.include_box("target_body").setChecked(True)
    assert not dialog.fsw_param_form.include_box("target_ground_station").isChecked()
    dialog.fsw_param_form.include_box("target_ground_station").setChecked(True)
    assert not dialog.fsw_param_form.include_box("target_body").isChecked()

    dialog.control_param_form.set_value("K", 0.5)
    sc = dialog.to_dataclass()
    assert sc.fsw_params == {"target_ground_station": "kiruna", "pHat_B": [0.0, 0.0, 1.0]}
    assert sc.control_params == {"K": 0.5}


def test_attitude_tab_round_trips_existing_params_and_extras(qtbot):
    """Opening and OK'ing a spacecraft keeps its fsw/control params,
    including keys the form doesn't know (kept in the Advanced box)."""
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    orbit = OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                    inclination_deg=97.6, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0)
    config = SpacecraftConfig(name="sat-1", orbit=orbit, fsw_mode="sunSafePoint",
                              fsw_params={"sHatBdyCmd": [1.0, 0.0, 0.0], "custom_key": 2},
                              control_params={"P": 12.0, "extra_gain": 1.5})
    dialog = SpacecraftEditorDialog(config)
    qtbot.addWidget(dialog)
    assert not dialog.fsw_params_edit.isHidden()  # extras present -> Advanced expanded
    sc = dialog.to_dataclass()
    assert sc.fsw_params == config.fsw_params
    assert sc.control_params == config.control_params


def test_switching_fsw_mode_away_and_back_keeps_edits(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("sat-1")
    dialog.fsw_mode_combo.setCurrentIndex(dialog.fsw_mode_combo.findData("sunSafePoint"))
    dialog.fsw_param_form.set_value("min_unit_mag", 0.25)
    dialog.fsw_mode_combo.setCurrentIndex(dialog.fsw_mode_combo.findData("hillPoint"))
    dialog.fsw_mode_combo.setCurrentIndex(dialog.fsw_mode_combo.findData("sunSafePoint"))
    assert dialog.to_dataclass().fsw_params["min_unit_mag"] == pytest.approx(0.25)


def test_dialog_power_and_rf_link_default_to_none(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.power_group.isChecked()
    assert not dialog.rf_link_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.power is None
    assert sc.rf_link is None


def test_dialog_builds_power_config_when_group_checked(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.power_group.setChecked(True)
    dialog.panel_area_m2.setValue(2.5)
    dialog.panel_efficiency.setValue(0.3)
    dialog.bus_idle_power_w.setValue(30.0)
    dialog.battery_capacity_wh.setValue(200.0)
    dialog.battery_initial_soc.setValue(0.8)

    sc = dialog.to_dataclass()
    assert sc.power is not None
    assert sc.power.panel_area_m2 == 2.5
    assert sc.power.panel_efficiency == 0.3
    assert sc.power.bus_idle_power_w == 30.0
    assert sc.power.battery_capacity_wh == 200.0
    assert sc.power.battery_initial_soc == 0.8
    assert sc.rf_link is None  # unrelated group, still unchecked


def test_dialog_builds_rf_link_config_when_group_checked(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.rf_link_group.setChecked(True)
    dialog.tx_power_w.setValue(20.0)
    dialog.frequency_ghz.setValue(2.2)
    dialog.data_rate_mbps.setValue(0.5)
    dialog.tx_antenna_gain_dbi.setValue(8.0)
    dialog.rf_implementation_loss_db.setValue(3.0)
    dialog.required_ebno_db.setValue(5.0)

    sc = dialog.to_dataclass()
    assert sc.rf_link is not None
    assert sc.rf_link.tx_power_w == 20.0
    assert sc.rf_link.frequency_hz == pytest.approx(2.2e9)
    assert sc.rf_link.data_rate_bps == pytest.approx(0.5e6)
    assert sc.rf_link.tx_antenna_gain_dbi == 8.0
    assert sc.rf_link.implementation_loss_db == 3.0
    assert sc.rf_link.required_ebno_db == 5.0
    assert sc.power is None  # unrelated group, still unchecked


def test_dialog_round_trips_power_and_rf_link(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import OrbitIC, PowerConfig, RFLinkConfig, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-power",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        power=PowerConfig(panel_area_m2=1.5, panel_efficiency=0.28, panel_normal_b=[1.0, 0.0, 0.0],
                           bus_idle_power_w=20.0, battery_capacity_wh=150.0, battery_initial_soc=0.95),
        rf_link=RFLinkConfig(tx_power_w=12.0, frequency_hz=8.4e9, data_rate_bps=2.0e6),
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)

    assert dialog.power_group.isChecked()
    assert dialog.rf_link_group.isChecked()

    got = dialog.to_dataclass()
    assert got.power == existing.power
    assert got.rf_link == existing.rf_link


def test_dialog_round_trips_rf_link_antenna_beamwidth_deg(qtbot):
    """Regression test for a real data-loss bug found by audit:
    antenna_beamwidth_deg had no editor at all, so opening then OK'ing a
    spacecraft that already had it set (e.g. template 19's "leo-comms-1")
    silently deleted it.
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import OrbitIC, RFLinkConfig, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-beamwidth",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        rf_link=RFLinkConfig(tx_power_w=12.0, frequency_hz=8.4e9, data_rate_bps=2.0e6, antenna_beamwidth_deg=12.5),
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)

    assert dialog.rf_link_group.isChecked()
    assert dialog.rf_beamwidth_check.isChecked()
    assert dialog.rf_beamwidth_deg.value() == pytest.approx(12.5)

    got = dialog.to_dataclass()
    assert got.rf_link == existing.rf_link  # unedited round-trip, including antenna_beamwidth_deg


def test_dialog_rf_link_antenna_beamwidth_deg_defaults_to_none_unchecked(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.rf_link_group.setChecked(True)
    assert not dialog.rf_beamwidth_check.isChecked()

    sc = dialog.to_dataclass()
    assert sc.rf_link.antenna_beamwidth_deg is None


def test_dialog_comms_pointing_defaults_to_none(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.comms_pointing_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.comms_pointing is None


def test_dialog_comms_pointing_ground_station_combo_lists_provided_names(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(ground_station_names=["berlin", "svalbard"])
    qtbot.addWidget(dialog)
    dialog.comms_pointing_group.setChecked(True)
    assert dialog.cp_ground_station_combo.isEnabled()
    names = {dialog.cp_ground_station_combo.itemData(i) for i in range(dialog.cp_ground_station_combo.count())}
    assert names == {"berlin", "svalbard"}


def test_dialog_comms_pointing_disabled_combo_with_no_ground_stations(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.comms_pointing_group.setChecked(True)
    assert not dialog.cp_ground_station_combo.isEnabled()


def test_dialog_comms_pointing_requires_a_selectable_ground_station(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import ScenarioValidationError

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.comms_pointing_group.setChecked(True)
    with pytest.raises(ScenarioValidationError, match="no ground station is selectable"):
        dialog.to_dataclass()


def test_dialog_builds_comms_pointing_config_when_group_checked(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(ground_station_names=["berlin"])
    qtbot.addWidget(dialog)
    dialog.comms_pointing_group.setChecked(True)
    dialog.power_group.setChecked(True)  # comms_power_w > 0 requires power also configured
    dialog.cp_boresight_x.setValue(1.0)
    dialog.cp_boresight_y.setValue(0.0)
    dialog.cp_boresight_z.setValue(0.0)
    dialog.cp_comms_power_w.setValue(5.0)

    sc = dialog.to_dataclass()
    assert sc.comms_pointing is not None
    assert sc.comms_pointing.target_ground_station == "berlin"
    assert sc.comms_pointing.antenna_boresight_b == [1.0, 0.0, 0.0]
    assert sc.comms_pointing.sun_pointing_axis_b is None  # default checkbox left checked
    assert sc.comms_pointing.comms_power_w == 5.0


def test_dialog_comms_pointing_sun_axis_override(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(ground_station_names=["berlin"])
    qtbot.addWidget(dialog)
    dialog.comms_pointing_group.setChecked(True)
    dialog.cp_sun_axis_default_check.setChecked(False)
    assert dialog.cp_sun_axis_x.isEnabled()
    dialog.cp_sun_axis_x.setValue(0.0)
    dialog.cp_sun_axis_y.setValue(1.0)
    dialog.cp_sun_axis_z.setValue(0.0)

    sc = dialog.to_dataclass()
    assert sc.comms_pointing.sun_pointing_axis_b == [0.0, 1.0, 0.0]


def test_dialog_round_trips_comms_pointing(qtbot):
    """Regression test for a real data-loss bug found by audit:
    comms_pointing had NO editor at all anywhere in this dialog, so
    opening then OK'ing a spacecraft that already had it set (e.g.
    template 19's "leo-comms-1") silently DELETED it -- to_dataclass()
    always rebuilt a fresh SpacecraftConfig from widget state alone.
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import CommsPointingConfig, OrbitIC, PowerConfig, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-comms",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        power=PowerConfig(panel_area_m2=1.5, panel_efficiency=0.28, panel_normal_b=[0.0, 0.0, 1.0],
                           bus_idle_power_w=10.0, battery_capacity_wh=100.0, battery_initial_soc=1.0),
        comms_pointing=CommsPointingConfig(
            target_ground_station="berlin", antenna_boresight_b=[0.0, 1.0, 0.0],
            sun_pointing_axis_b=[1.0, 0.0, 0.0], comms_power_w=8.0,
        ),
    )
    dialog = SpacecraftEditorDialog(config=existing, ground_station_names=["berlin"])
    qtbot.addWidget(dialog)

    assert dialog.comms_pointing_group.isChecked()
    assert not dialog.cp_sun_axis_default_check.isChecked()  # explicit override must survive, not get reset to default

    got = dialog.to_dataclass()
    assert got.comms_pointing == existing.comms_pointing


def test_dialog_stale_comms_pointing_ground_station_is_preserved_not_silently_swapped(qtbot):
    """Same stale-reference preservation as pk_chief_combo's own test
    (test_dialog_stale_chief_spacecraft_is_preserved_not_silently_swapped)
    -- a comms_pointing.target_ground_station that no longer matches any
    current ground station (renamed/removed since save) must round-trip
    unchanged, not silently swap to whichever station happens to be first.
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import CommsPointingConfig, OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-comms",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        comms_pointing=CommsPointingConfig(target_ground_station="old-station"),
    )
    dialog = SpacecraftEditorDialog(config=existing, ground_station_names=["berlin", "svalbard"])
    qtbot.addWidget(dialog)

    assert dialog.cp_ground_station_combo.currentData() == "old-station"

    got = dialog.to_dataclass()
    assert got.comms_pointing.target_ground_station == "old-station"


def test_dialog_template_19_leo_comms_1_survives_open_then_ok(qtbot):
    """The exact real-world bug scenario this fix closes, checked
    end-to-end against the real bundled template rather than only via the
    dataclass-level round-trip tests above: load template 19, open its
    "leo-comms-1" spacecraft (which has both comms_pointing and
    rf_link.antenna_beamwidth_deg already set) in this dialog, accept with
    NO edits, and confirm both fields are still populated afterward.
    """
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / "19_sun_pointing_comms_link.json")
    original = next(sc for sc in scenario.spacecraft if sc.name == "leo-comms-1")
    assert original.comms_pointing is not None  # sanity check this template still exercises the bug
    assert original.rf_link.antenna_beamwidth_deg is not None

    dialog = SpacecraftEditorDialog(
        config=original,
        other_spacecraft_names=[sc.name for sc in scenario.spacecraft if sc.name != "leo-comms-1"],
        ground_station_names=[gs.name for gs in scenario.ground_stations],
    )
    qtbot.addWidget(dialog)

    got = dialog.to_dataclass()  # same call OK triggers, with zero edits made
    assert got.comms_pointing == original.comms_pointing
    assert got.rf_link == original.rf_link


def test_dialog_orbit_only_mode_force_clears_comms_pointing(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import CommsPointingConfig, OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-comms",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        comms_pointing=CommsPointingConfig(target_ground_station="berlin"),
    )
    dialog = SpacecraftEditorDialog(config=existing, ground_station_names=["berlin"], simulation_mode="orbit_only")
    qtbot.addWidget(dialog)

    sc = dialog.to_dataclass()
    assert sc.comms_pointing is None


def test_dialog_station_keeping_defaults_to_none(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.station_keeping_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.station_keeping is None


def test_dialog_builds_station_keeping_config_when_group_checked(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.station_keeping_group.setChecked(True)
    dialog.sk_target_altitude_km.setValue(600.0)
    dialog.sk_deadband_km.setValue(2.0)
    dialog.sk_thrust_n.setValue(0.02)
    dialog.sk_isp_s.setValue(1600.0)
    dialog.sk_propellant_kg.setValue(3.5)
    dialog.sk_eclipse_sunlit_threshold.setValue(0.95)

    sc = dialog.to_dataclass()
    assert sc.station_keeping is not None
    assert sc.station_keeping.target_altitude_km == 600.0
    assert sc.station_keeping.deadband_km == 2.0
    assert sc.station_keeping.thrust_n == 0.02
    assert sc.station_keeping.isp_s == 1600.0
    assert sc.station_keeping.propellant_kg == 3.5
    assert sc.station_keeping.eclipse_sunlit_threshold == 0.95


def test_dialog_round_trips_station_keeping(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig, StationKeepingConfig

    existing = SpacecraftConfig(
        name="sat-sk",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        station_keeping=StationKeepingConfig(target_altitude_km=550.0, deadband_km=1.5, thrust_n=0.015,
                                              isp_s=1550.0, propellant_kg=2.5),
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)

    assert dialog.station_keeping_group.isChecked()

    got = dialog.to_dataclass()
    assert got.station_keeping == existing.station_keeping


def test_dialog_phasing_keeping_defaults_to_none(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.phasing_keeping_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.phasing_keeping is None


def test_dialog_phasing_keeping_chief_combo_lists_other_spacecraft(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(other_spacecraft_names=["chief", "follower-2"])
    qtbot.addWidget(dialog)
    dialog.phasing_keeping_group.setChecked(True)  # a checkable QGroupBox disables its children while unchecked
    assert dialog.pk_chief_combo.isEnabled()
    names = {dialog.pk_chief_combo.itemData(i) for i in range(dialog.pk_chief_combo.count())}
    assert names == {"chief", "follower-2"}


def test_dialog_phasing_keeping_disabled_combo_with_no_other_spacecraft(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.phasing_keeping_group.setChecked(True)  # isolate this widget's OWN disabled state from the group's
    assert not dialog.pk_chief_combo.isEnabled()
    assert dialog.pk_chief_combo.currentData() is None


def test_dialog_phasing_keeping_requires_a_selectable_chief(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import ScenarioValidationError

    dialog = SpacecraftEditorDialog()  # no other_spacecraft_names -- combo disabled
    qtbot.addWidget(dialog)
    dialog.station_keeping_group.setChecked(True)
    dialog.phasing_keeping_group.setChecked(True)
    with pytest.raises(ScenarioValidationError, match="no chief spacecraft is selectable"):
        dialog.to_dataclass()


def test_dialog_builds_phasing_keeping_config_when_group_checked(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(other_spacecraft_names=["chief"])
    qtbot.addWidget(dialog)
    dialog.station_keeping_group.setChecked(True)  # phasing_keeping requires this
    dialog.phasing_keeping_group.setChecked(True)
    dialog.pk_target_separations.set_values([1000.0, 500.0, 100.0])
    dialog.pk_reconfiguration_interval_days.setValue(60.0)
    dialog.pk_tolerance_fraction.setValue(0.2)
    dialog.pk_restore_tolerance_fraction.setValue(0.05)
    dialog.pk_correction_window_days.setValue(14.0)
    dialog.pk_max_drift_days.setValue(45.0)
    dialog.pk_max_delta_sma_km.setValue(2.0)

    sc = dialog.to_dataclass()
    assert sc.phasing_keeping is not None
    assert sc.phasing_keeping.chief_spacecraft == "chief"
    assert sc.phasing_keeping.target_separation_km == [1000.0, 500.0, 100.0]
    assert sc.phasing_keeping.reconfiguration_interval_days == 60.0
    assert sc.phasing_keeping.tolerance_fraction == 0.2
    assert sc.phasing_keeping.restore_tolerance_fraction == 0.05
    assert sc.phasing_keeping.correction_window_days == 14.0
    assert sc.phasing_keeping.max_drift_days == 45.0
    assert sc.phasing_keeping.max_delta_semi_major_axis_km == 2.0


def test_target_separation_stages_are_added_and_removed_as_rows(qtbot):
    """Real user feedback: the comma-separated separation list is now one
    km box per stage, with Add/Remove, never fewer than one stage."""
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(other_spacecraft_names=["chief"])
    qtbot.addWidget(dialog)
    dialog.station_keeping_group.setChecked(True)
    dialog.phasing_keeping_group.setChecked(True)
    editor = dialog.pk_target_separations
    assert editor.values() == [100.0] and editor.labels() == ["Stage 1"]
    assert "km" in editor.boxes()[0].suffix()
    editor.boxes()[0].setValue(1000.0)
    editor.add_button.click()
    editor.boxes()[1].setValue(500.0)
    editor.add_button.click()
    editor.boxes()[2].setValue(100.0)
    assert editor.labels() == ["Stage 1", "Stage 2", "Stage 3"]
    assert dialog.to_dataclass().phasing_keeping.target_separation_km == [1000.0, 500.0, 100.0]

    editor._on_remove(editor.boxes()[1])
    assert editor.values() == [1000.0, 100.0]
    editor._on_remove(editor.boxes()[0])
    assert editor.values() == [100.0]
    assert not editor._remove_buttons[0].isEnabled()  # the last stage can't be removed


def test_dialog_stale_chief_spacecraft_is_preserved_not_silently_swapped(qtbot):
    """Regression test: pk0.chief_spacecraft naming a spacecraft that no
    longer exists in other_spacecraft_names (e.g. renamed/removed since
    this config was saved) used to be silently dropped -- findData()
    returned -1, nothing set the combo's index, and it stayed on
    whatever was first, re-targeting phasing_keeping at the WRONG chief
    with no indication anything had changed. It must instead be
    round-tripped as-is (surfaced as its own combo entry) so
    to_dataclass() either preserves it or a later validate() call catches
    it as a real, visible error -- never a silent swap.
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import OrbitIC, PhasingKeepingConfig, SpacecraftConfig, StationKeepingConfig

    existing = SpacecraftConfig(
        name="sat-follower",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        station_keeping=StationKeepingConfig(target_altitude_km=550.0, deadband_km=1.5, thrust_n=0.015,
                                              isp_s=1550.0, propellant_kg=2.5),
        phasing_keeping=PhasingKeepingConfig(chief_spacecraft="renamed-chief", target_separation_km=[250.0]),
    )
    # "renamed-chief" is NOT in other_spacecraft_names -- simulates the
    # chief having been renamed/removed after this config was saved.
    dialog = SpacecraftEditorDialog(config=existing, other_spacecraft_names=["some-other-sat"])
    qtbot.addWidget(dialog)

    assert dialog.pk_chief_combo.currentData() == "renamed-chief"
    got = dialog.to_dataclass()
    assert got.phasing_keeping.chief_spacecraft == "renamed-chief"


def test_dialog_round_trips_drag_and_srp_fields(qtbot):
    """Regression test: to_dataclass() used to build a brand new
    SpacecraftConfig without passing enable_drag/drag_coeff/drag_area_m2/
    enable_srp/srp_coeff/srp_area_m2 at all (there was no editor for them
    at the time), silently resetting them to SpacecraftConfig's defaults
    every time an existing spacecraft with these set was edited and
    re-saved. There is now a real editor (drag_srp_group) -- this checks
    both that it round-trips an existing config's values AND (below) that
    editing it actually changes what to_dataclass() returns.
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-drag",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        enable_drag=True,
        drag_coeff=2.5,
        drag_area_m2=3.3,
        enable_srp=True,
        srp_coeff=1.5,
        srp_area_m2=4.4,
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)

    assert dialog.enable_drag_check.isChecked()
    assert dialog.drag_coeff.value() == 2.5
    assert dialog.drag_area_m2.value() == 3.3
    assert dialog.enable_srp_check.isChecked()
    assert dialog.srp_coeff.value() == 1.5
    assert dialog.srp_area_m2.value() == 4.4

    got = dialog.to_dataclass()
    assert got.enable_drag is True
    assert got.drag_coeff == 2.5
    assert got.drag_area_m2 == 3.3
    assert got.enable_srp is True
    assert got.srp_coeff == 1.5
    assert got.srp_area_m2 == 4.4


def test_dialog_drag_srp_editor_actually_edits(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.enable_drag_check.isChecked()  # default off

    dialog.enable_drag_check.setChecked(True)
    dialog.drag_coeff.setValue(2.7)
    dialog.drag_area_m2.setValue(0.05)
    dialog.enable_srp_check.setChecked(True)
    dialog.srp_coeff.setValue(1.4)
    dialog.srp_area_m2.setValue(0.05)

    sc = dialog.to_dataclass()
    assert sc.enable_drag is True
    assert sc.drag_coeff == 2.7
    assert sc.drag_area_m2 == 0.05
    assert sc.enable_srp is True
    assert sc.srp_coeff == 1.4
    assert sc.srp_area_m2 == 0.05


def test_dialog_defaults_to_no_constant_thrust(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.constant_thrust_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.constant_thrust is None


def test_dialog_builds_constant_thrust_when_group_checked(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.constant_thrust_group.setChecked(True)
    dialog.ct_frame_combo.setCurrentText("RTN")
    dialog.ct_dir_x.setValue(0.0)
    dialog.ct_dir_y.setValue(1.0)
    dialog.ct_dir_z.setValue(0.0)
    dialog.ct_thrust_n.setValue(0.05)
    dialog.ct_isp_s.setValue(2000.0)
    dialog.ct_propellant_kg.setValue(1.5)

    sc = dialog.to_dataclass()
    assert sc.constant_thrust is not None
    assert sc.constant_thrust.frame == "RTN"
    assert sc.constant_thrust.direction == [0.0, 1.0, 0.0]
    assert sc.constant_thrust.thrust_n == 0.05
    assert sc.constant_thrust.isp_s == 2000.0
    assert sc.constant_thrust.propellant_kg == 1.5


def test_dialog_round_trips_constant_thrust(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import ConstantThrustConfig, OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-thrust",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        constant_thrust=ConstantThrustConfig(frame="VNB", direction=[1.0, 0.0, 0.0], thrust_n=0.02,
                                              isp_s=1800.0, propellant_kg=3.0),
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    assert dialog.constant_thrust_group.isChecked()
    assert dialog.ct_frame_combo.currentText() == "VNB"

    got = dialog.to_dataclass()
    assert got.constant_thrust == existing.constant_thrust


def test_dialog_orbit_only_mode_hides_attitude_tabs_and_power(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(simulation_mode="orbit_only")
    qtbot.addWidget(dialog)
    assert not dialog.tabs.isTabVisible(dialog._sensors_tab_index)
    assert not dialog.tabs.isTabVisible(dialog._fsw_tab_index)
    # isHidden() (not isVisible()): tracks whether THIS widget was
    # explicitly hidden, independent of whether the dialog itself was ever
    # shown (it isn't, in this test) -- isVisible() would be False either
    # way since the dialog is never .show()n.
    assert dialog.power_group.isHidden()


def test_dialog_orbit_only_mode_force_clears_attitude_fields(qtbot):
    """Even if a spacecraft being edited already has sensors/actuators/
    fsw_mode/power set (e.g. the scenario's mode was just switched to
    orbit_only without yet touching this spacecraft), the dialog must not
    let those hidden, stale values silently pass through to_dataclass().
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import OrbitIC, PowerConfig, SensorConfig, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-orbit-only",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        sensors=[SensorConfig(kind="imu", name="imu-1")],
        fsw_mode="hillPoint",
        power=PowerConfig(panel_area_m2=1.0, panel_efficiency=0.29),
    )
    dialog = SpacecraftEditorDialog(config=existing, simulation_mode="orbit_only")
    qtbot.addWidget(dialog)

    sc = dialog.to_dataclass()
    assert sc.sensors == []
    assert sc.actuators == []
    assert sc.fsw_mode is None
    assert sc.power is None
    sc.validate()  # must not raise


def test_dialog_full_attitude_mode_keeps_tabs_visible(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(simulation_mode="full_attitude")
    qtbot.addWidget(dialog)
    assert dialog.tabs.isTabVisible(dialog._sensors_tab_index)
    assert dialog.tabs.isTabVisible(dialog._fsw_tab_index)
    assert not dialog.power_group.isHidden()


def test_dialog_defaults_to_no_vizard_model(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.viz_model_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.vizard_model_path is None
    assert sc.vizard_model_offset_m == [0.0, 0.0, 0.0]
    assert sc.vizard_model_rotation_deg == [0.0, 0.0, 0.0]
    assert sc.vizard_model_scale == [1.0, 1.0, 1.0]


def test_dialog_builds_vizard_model_when_group_checked(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.viz_model_group.setChecked(True)
    dialog.viz_model_path_edit.setText("/tmp/my_bus.obj")
    dialog.viz_offset_x.setValue(0.1)
    dialog.viz_offset_y.setValue(-0.2)
    dialog.viz_offset_z.setValue(0.3)
    dialog.viz_rotation_z.setValue(90.0)
    dialog.viz_scale_x.setValue(2.0)
    dialog.viz_scale_y.setValue(2.0)
    dialog.viz_scale_z.setValue(2.0)

    sc = dialog.to_dataclass()
    assert sc.vizard_model_path == "/tmp/my_bus.obj"
    assert sc.vizard_model_offset_m == [0.1, -0.2, 0.3]
    assert sc.vizard_model_rotation_deg == [90.0, 0.0, 0.0]
    assert sc.vizard_model_scale == [2.0, 2.0, 2.0]


def test_dialog_vizard_model_checked_but_blank_path_is_none(qtbot):
    """Checking the group box without filling in a path shouldn't produce
    an unvalidatable half-configured model -- it's simply treated as "no
    custom model", same as leaving the group box unchecked.
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.viz_model_group.setChecked(True)

    sc = dialog.to_dataclass()
    assert sc.vizard_model_path is None


def test_dialog_round_trips_vizard_model(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-with-model",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        vizard_model_path="CYLINDER",
        vizard_model_offset_m=[0.0, 0.0, -0.5],
        vizard_model_rotation_deg=[0.0, 45.0, 0.0],
        vizard_model_scale=[1.5, 1.5, 3.0],
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    assert dialog.viz_model_group.isChecked()
    assert dialog.viz_model_path_edit.text() == "CYLINDER"

    got = dialog.to_dataclass()
    assert got.vizard_model_path == "CYLINDER"
    assert got.vizard_model_offset_m == [0.0, 0.0, -0.5]
    assert got.vizard_model_rotation_deg == [0.0, 45.0, 0.0]
    assert got.vizard_model_scale == [1.5, 1.5, 3.0]


def test_dialog_round_trips_phasing_keeping(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import (
        OrbitIC,
        PhasingKeepingConfig,
        SpacecraftConfig,
        StationKeepingConfig,
    )

    existing = SpacecraftConfig(
        name="sat-follower",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        station_keeping=StationKeepingConfig(target_altitude_km=550.0, deadband_km=1.5, thrust_n=0.015,
                                              isp_s=1550.0, propellant_kg=2.5),
        phasing_keeping=PhasingKeepingConfig(chief_spacecraft="chief", target_separation_km=[250.0, 100.0],
                                              reconfiguration_interval_days=45.0),
    )
    dialog = SpacecraftEditorDialog(config=existing, other_spacecraft_names=["chief"])
    qtbot.addWidget(dialog)

    assert dialog.phasing_keeping_group.isChecked()
    assert dialog.pk_chief_combo.currentData() == "chief"
    assert dialog.pk_target_separations.values() == [250.0, 100.0]

    got = dialog.to_dataclass()
    assert got.phasing_keeping == existing.phasing_keeping


def test_dialog_rejects_invalid_fsw_params_json(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.fsw_params_edit.setPlainText("{not valid json")
    with pytest.raises(ValueError, match="not valid JSON"):
        dialog.to_dataclass()


def test_dialog_rejects_empty_name(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import ScenarioValidationError

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("")
    with pytest.raises(ScenarioValidationError, match="name must not be empty"):
        dialog.to_dataclass()


def test_dialog_name_field_shows_inline_error_while_empty(qtbot):
    """gui.feedback's inline-validation primitive, live as the user
    types -- not just the to_dataclass()-time exception the test above
    already covers.
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)

    dialog.name_edit.setText("")
    assert dialog.name_edit.property("state") == "error"

    dialog.name_edit.setText("sat-42")
    assert dialog.name_edit.property("state") != "error"


def test_dialog_name_field_shows_inline_error_on_duplicate(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(other_spacecraft_names=["sat-1", "sat-2"])
    qtbot.addWidget(dialog)

    dialog.name_edit.setText("sat-2")
    assert dialog.name_edit.property("state") == "error"
    assert "sat-2" in dialog.name_edit.toolTip()

    dialog.name_edit.setText("sat-3")
    assert dialog.name_edit.property("state") != "error"


def test_dialog_accept_blocks_and_keeps_dialog_open_on_empty_name(qtbot):
    """Regression guard for a real data-loss UX bug: _on_accept() used to
    call self.accept() unconditionally, so a duplicate/empty name wasn't
    caught until the (already-closed) dialog's caller checked afterward
    -- silently discarding every edit the user just made. _on_accept()
    must now refuse to close the dialog itself.
    """
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("")

    dialog._on_accept()

    assert dialog.result() == 0  # neither Accepted nor Rejected -- still open
    assert dialog.name_edit.property("state") == "error"


def test_dialog_accept_blocks_on_duplicate_name(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog(other_spacecraft_names=["sat-1"])
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("sat-1")

    dialog._on_accept()

    assert dialog.result() == 0
    assert dialog.name_edit.property("state") == "error"


def test_list_widget_from_list_to_list_round_trip(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    configs = [
        SpacecraftConfig(name="a", orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0])),
        SpacecraftConfig(name="b", orbit=OrbitIC(type="cartesian", position_km=[8000, 0, 0], velocity_km_s=[0, 7.0, 0])),
    ]
    lw.from_list(configs)
    assert lw.list_widget.count() == 2
    assert [c.name for c in lw.to_list()] == ["a", "b"]


def test_list_widget_add_via_dialog(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog, SpacecraftListWidget

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)

    def fake_exec(self):
        self.name_edit.setText("added-sat")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SpacecraftEditorDialog, "exec", fake_exec)
    changed_count = []
    lw.changed.connect(lambda: changed_count.append(1))

    qtbot.mouseClick(lw.add_button, Qt.MouseButton.LeftButton)

    assert lw.list_widget.count() == 1
    assert lw.to_list()[0].name == "added-sat"
    assert changed_count == [1]
    assert lw.list_widget.currentRow() == 0  # the new spacecraft is selected, not left unselected


def test_list_widget_add_and_remove_show_a_toast(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog, SpacecraftListWidget

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)

    def fake_exec(self):
        self.name_edit.setText("toasted-sat")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SpacecraftEditorDialog, "exec", fake_exec)
    lw._on_add()

    toasts = getattr(lw.window(), "_spacemissionstudio_active_toasts", [])
    assert any("toasted-sat" in t.text() for t in toasts)

    lw.list_widget.setCurrentRow(0)
    lw._on_remove()

    toasts = getattr(lw.window(), "_spacemissionstudio_active_toasts", [])
    assert any("toasted-sat" in t.text() and "Removed" in t.text() for t in toasts)


def test_list_widget_new_from_template(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.engine.spacecraft_templates import SPACECRAFT_TEMPLATES
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog, SpacecraftListWidget
    from spacemissionstudio.gui.spacecraft_template_dialog import SpacecraftTemplateDialog

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)

    stabilized = next(t for t in SPACECRAFT_TEMPLATES if "150 kg" in t.name)

    def fake_picker_exec(self):
        return QDialog.DialogCode.Accepted

    def fake_picker_selected_template(self):
        return stabilized

    def fake_editor_exec(self):
        return QDialog.DialogCode.Accepted  # accept whatever the template pre-filled, unchanged

    monkeypatch.setattr(SpacecraftTemplateDialog, "exec", fake_picker_exec)
    monkeypatch.setattr(SpacecraftTemplateDialog, "selected_template", fake_picker_selected_template)
    monkeypatch.setattr(SpacecraftEditorDialog, "exec", fake_editor_exec)
    changed_count = []
    lw.changed.connect(lambda: changed_count.append(1))

    qtbot.mouseClick(lw.new_from_template_button, Qt.MouseButton.LeftButton)

    assert lw.list_widget.count() == 1
    added = lw.to_list()[0]
    assert len(added.actuators) == 3
    assert added.fsw_mode == "sunSafePoint"
    assert changed_count == [1]


def test_list_widget_new_from_template_dedupes_name_on_collision(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.engine.spacecraft_templates import SPACECRAFT_TEMPLATES
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog, SpacecraftListWidget
    from spacemissionstudio.gui.spacecraft_template_dialog import SpacecraftTemplateDialog
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(name="template",
                                    orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0],
                                                  velocity_km_s=[0, 7.5, 0]))])

    first = SPACECRAFT_TEMPLATES[0]

    monkeypatch.setattr(SpacecraftTemplateDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(SpacecraftTemplateDialog, "selected_template", lambda self: first)
    captured_names = []

    def fake_editor_exec(self):
        captured_names.append(self.name_edit.text())
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SpacecraftEditorDialog, "exec", fake_editor_exec)

    qtbot.mouseClick(lw.new_from_template_button, Qt.MouseButton.LeftButton)

    assert lw.list_widget.count() == 2
    assert captured_names == ["template-2"]  # "template" already taken by the pre-existing spacecraft


def test_list_widget_new_from_template_cancel_does_nothing(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from spacemissionstudio.gui.spacecraft_template_dialog import SpacecraftTemplateDialog

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    monkeypatch.setattr(SpacecraftTemplateDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    qtbot.mouseClick(lw.new_from_template_button, Qt.MouseButton.LeftButton)

    assert lw.list_widget.count() == 0


def test_list_widget_edit_and_remove(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog, SpacecraftListWidget
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(name="orig",
                                    orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]))])
    lw.list_widget.setCurrentRow(0)

    def fake_exec(self):
        self.name_edit.setText("renamed")
        self.dry_mass_kg.setValue(321.0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SpacecraftEditorDialog, "exec", fake_exec)
    lw._on_edit()
    assert lw.to_list()[0].name == "renamed"
    assert lw.to_list()[0].dry_mass_kg == 321.0

    lw.list_widget.setCurrentRow(0)
    lw._on_remove()
    assert lw.to_list() == []


def test_list_widget_rejects_duplicate_name_on_add(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog, SpacecraftListWidget
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(name="dup",
                                    orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]))])

    def fake_exec(self):
        self.name_edit.setText("dup")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SpacecraftEditorDialog, "exec", fake_exec)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    lw._on_add()
    assert len(lw.to_list()) == 1  # not added
    assert len(critical_calls) == 1


def test_list_widget_generate_constellation_appends_generated_spacecraft(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.constellation_dialog import WalkerConstellationDialog
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(
        name="template-sat", dry_mass_kg=42.0,
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
    )])

    def fake_exec(self):
        self.total_satellites.setValue(4)
        self.num_planes.setValue(2)
        self.phasing_factor.setValue(0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(WalkerConstellationDialog, "exec", fake_exec)
    changed_calls = []
    lw.changed.connect(lambda: changed_calls.append(1))

    lw._on_generate_constellation()

    configs = lw.to_list()
    assert len(configs) == 1 + 4  # original template + 4 generated
    generated = [c for c in configs if c.name != "template-sat"]
    assert len(generated) == 4
    assert all(c.dry_mass_kg == 42.0 for c in generated)  # cloned from the template
    assert len(changed_calls) == 1
    toasts = getattr(lw.window(), "_spacemissionstudio_active_toasts", [])
    assert any("4" in t.text() and "constellation" in t.text() for t in toasts)


def test_list_widget_generate_constellation_uses_default_template_when_list_empty(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.constellation_dialog import WalkerConstellationDialog
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftListWidget

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)

    def fake_exec(self):
        self.total_satellites.setValue(2)
        self.num_planes.setValue(1)
        self.phasing_factor.setValue(0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(WalkerConstellationDialog, "exec", fake_exec)
    lw._on_generate_constellation()
    assert len(lw.to_list()) == 2


def test_list_widget_generate_constellation_reports_name_collision(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from spacemissionstudio.gui.constellation_dialog import WalkerConstellationDialog
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    # This name collides with the first satellite generate_walker_constellation
    # would produce for a 1-satellite/1-plane request with the default prefix.
    lw.from_list([SpacecraftConfig(
        name="sat-01-01",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
    )])

    def fake_exec(self):
        self.total_satellites.setValue(1)
        self.num_planes.setValue(1)
        self.phasing_factor.setValue(0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(WalkerConstellationDialog, "exec", fake_exec)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    lw._on_generate_constellation()
    assert len(lw.to_list()) == 1  # nothing added
    assert len(critical_calls) == 1


def test_list_widget_generate_constellation_cancel_does_nothing(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.constellation_dialog import WalkerConstellationDialog
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftListWidget

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    monkeypatch.setattr(WalkerConstellationDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    lw._on_generate_constellation()
    assert lw.to_list() == []


def test_list_widget_uses_central_body_provider(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.constellation_dialog import WalkerConstellationDialog
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftListWidget

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.set_central_body_provider(lambda: "mars")

    captured = {}

    def fake_exec(self):
        captured["central_body"] = self.to_request().central_body
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(WalkerConstellationDialog, "exec", fake_exec)
    lw._on_generate_constellation()
    assert captured["central_body"] == "mars"


@pytest.mark.requires_basilisk
def test_list_widget_generate_phasing_formation_appends_follower(qtbot, monkeypatch):
    """generate_phasing_follower() needs a real Basilisk build (see
    engine.formation's own docstring) -- unlike the Walker-constellation
    tests above, this one is requires_basilisk in addition to this file's
    own requires_gui.
    """
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(
        name="chief-1", dry_mass_kg=100.0,
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                      inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
    )])

    def fake_exec(self):
        self.chief_combo.setCurrentIndex(0)
        self.follower_name_edit.setText("follower-1")
        self.along_track_km.setValue(50.0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PhasingFormationDialog, "exec", fake_exec)
    changed_calls = []
    lw.changed.connect(lambda: changed_calls.append(1))

    lw._on_generate_phasing_formation()

    configs = lw.to_list()
    assert [c.name for c in configs] == ["chief-1", "follower-1"]
    follower = configs[1]
    assert follower.phasing_keeping.chief_spacecraft == "chief-1"
    assert follower.phasing_keeping.target_separation_km == [50.0]
    assert follower.station_keeping is not None
    assert follower.dry_mass_kg == 100.0  # cloned from the chief (also the default template)
    assert len(changed_calls) == 1
    toasts = getattr(lw.window(), "_spacemissionstudio_active_toasts", [])
    assert any("follower-1" in t.text() for t in toasts)


@pytest.mark.requires_basilisk
def test_list_widget_generate_phasing_formation_reports_name_collision(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([
        SpacecraftConfig(
            name="chief-1",
            orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                          inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
        ),
        SpacecraftConfig(
            name="follower-1",
            orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                          inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
        ),
    ])

    def fake_exec(self):
        self.chief_combo.setCurrentIndex(0)
        self.follower_name_edit.setText("follower-1")  # collides with the existing spacecraft
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PhasingFormationDialog, "exec", fake_exec)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    lw._on_generate_phasing_formation()
    assert len(lw.to_list()) == 2  # nothing added
    assert len(critical_calls) == 1


def test_list_widget_generate_phasing_formation_cancel_does_nothing(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftListWidget

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    monkeypatch.setattr(PhasingFormationDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    lw._on_generate_phasing_formation()
    assert lw.to_list() == []


def test_list_widget_generate_phasing_formation_reports_missing_basilisk(qtbot, monkeypatch):
    """Does NOT need requires_basilisk: generate_phasing_follower is
    monkeypatched to simulate the "no Basilisk build" case directly, same
    "clear error, not a traceback" pattern every other Basilisk-needing
    GUI action already uses (gui.run_worker) -- exercised here without
    actually needing Basilisk uninstalled.
    """
    from PySide6.QtWidgets import QDialog, QMessageBox

    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(
        name="chief-1",
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                      inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
    )])

    def fake_exec(self):
        self.chief_combo.setCurrentIndex(0)
        self.follower_name_edit.setText("follower-1")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PhasingFormationDialog, "exec", fake_exec)

    def fake_generate(*args, **kwargs):
        raise ImportError("No module named 'Basilisk'")

    monkeypatch.setattr("spacemissionstudio.engine.formation.generate_phasing_follower", fake_generate)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    lw._on_generate_phasing_formation()
    configs = lw.to_list()
    assert len(configs) == 1  # nothing added beyond the original chief
    assert configs[0].name == "chief-1"
    assert len(critical_calls) == 1
    assert "Basilisk" in critical_calls[0][1]


def test_list_widget_generate_phasing_formation_without_basilisk_reports_clear_error(qtbot, monkeypatch):
    """Same as the test above, but against the REAL no-Basilisk import
    path (no mocking of generate_phasing_follower itself) -- regression
    test for a real bug found while writing this feature: the ImportError
    this needs to catch is raised lazily INSIDE generate_phasing_follower()
    (see engine.formation's own docstring), not by importing the name
    itself (engine.formation has no Basilisk import at module level) --
    wrapping the wrong statement in try/except ImportError (as this
    file's cli.py sibling command originally did) lets it propagate
    uncaught. Skipped on a machine that DOES have Basilisk, where this
    test's premise doesn't hold.
    """
    import importlib.util

    from PySide6.QtWidgets import QDialog, QMessageBox

    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftListWidget
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig

    if importlib.util.find_spec("Basilisk") is not None:
        pytest.skip("this test's premise is specifically that Basilisk is unavailable")

    lw = SpacecraftListWidget()
    qtbot.addWidget(lw)
    lw.from_list([SpacecraftConfig(
        name="chief-1",
        orbit=OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                      inclination_deg=45.0, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
    )])

    def fake_exec(self):
        self.chief_combo.setCurrentIndex(0)
        self.follower_name_edit.setText("follower-1")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PhasingFormationDialog, "exec", fake_exec)
    critical_calls = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: critical_calls.append(a)))

    lw._on_generate_phasing_formation()  # must not raise

    assert len(lw.to_list()) == 1
    assert len(critical_calls) == 1
    assert "Basilisk" in critical_calls[0][1]


def test_dialog_momentum_dumping_defaults_to_none(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.momentum_dumping_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.momentum_dumping is None


def test_dialog_builds_momentum_dumping_config_when_group_checked(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import ActuatorConfig, OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-md",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        actuators=[
            ActuatorConfig(kind="reaction_wheel", name="rw-1", params={"gsHat_B": [1, 0, 0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0}),
            ActuatorConfig(kind="thruster", name="thr-1",
                            params={"r_B": [1, 0, 0], "tHat_B": [0, 1, 0], "MaxThrust": 1.0}),
        ],
        fsw_mode="sunSafePoint",
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    dialog.momentum_dumping_group.setChecked(True)
    dialog.md_hs_max.setValue(65.0)
    dialog.md_thr_min_fire_time.setValue(0.03)
    dialog.md_max_counter_value.setValue(50)

    sc = dialog.to_dataclass()
    assert sc.momentum_dumping is not None
    assert sc.momentum_dumping.hs_max == 65.0
    assert sc.momentum_dumping.thr_min_fire_time == 0.03
    assert sc.momentum_dumping.max_counter_value == 50


def test_dialog_round_trips_momentum_dumping(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import ActuatorConfig, MomentumDumpingConfig, OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-md",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        actuators=[
            ActuatorConfig(kind="reaction_wheel", name="rw-1", params={"gsHat_B": [1, 0, 0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0}),
            ActuatorConfig(kind="thruster", name="thr-1",
                            params={"r_B": [1, 0, 0], "tHat_B": [0, 1, 0], "MaxThrust": 1.0}),
        ],
        fsw_mode="sunSafePoint",
        momentum_dumping=MomentumDumpingConfig(hs_max=70.0, thr_min_fire_time=0.04, max_counter_value=80),
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)

    assert dialog.momentum_dumping_group.isChecked()
    assert dialog.md_hs_max.value() == 70.0
    assert dialog.md_thr_min_fire_time.value() == 0.04
    assert dialog.md_max_counter_value.value() == 80

    sc = dialog.to_dataclass()
    assert sc.momentum_dumping.hs_max == 70.0


def test_dialog_builds_fuel_tank_config_when_group_checked(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import ActuatorConfig, OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-ft",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        actuators=[
            ActuatorConfig(kind="thruster", name="thr-1",
                            params={"r_B": [1, 0, 0], "tHat_B": [0, 1, 0], "MaxThrust": 1.0}),
        ],
        fsw_mode="sunSafePoint",
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    dialog.fuel_tank_group.setChecked(True)
    dialog.ft_propellant_mass.setValue(15.0)
    dialog.ft_max_propellant_mass.setValue(25.0)
    dialog.ft_tank_pos_x.setValue(0.1)
    dialog.ft_tank_pos_y.setValue(0.2)
    dialog.ft_tank_pos_z.setValue(-0.3)

    sc = dialog.to_dataclass()
    assert sc.fuel_tank is not None
    assert sc.fuel_tank.propellant_mass_kg == 15.0
    assert sc.fuel_tank.max_propellant_mass_kg == 25.0
    assert sc.fuel_tank.tank_position_b_m == [0.1, 0.2, -0.3]


def test_dialog_round_trips_fuel_tank(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import ActuatorConfig, FuelTankConfig, OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-ft",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        actuators=[
            ActuatorConfig(kind="thruster", name="thr-1",
                            params={"r_B": [1, 0, 0], "tHat_B": [0, 1, 0], "MaxThrust": 1.0}),
        ],
        fsw_mode="sunSafePoint",
        fuel_tank=FuelTankConfig(propellant_mass_kg=12.0, max_propellant_mass_kg=20.0),
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)

    assert dialog.fuel_tank_group.isChecked()
    assert dialog.ft_propellant_mass.value() == 12.0
    assert dialog.ft_max_propellant_mass.value() == 20.0

    sc = dialog.to_dataclass()
    assert sc.fuel_tank.propellant_mass_kg == 12.0


def test_dialog_fuel_tank_defaults_to_none(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.fuel_tank_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.fuel_tank is None


def test_dialog_magnetic_momentum_management_defaults_to_none(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

    dialog = SpacecraftEditorDialog()
    qtbot.addWidget(dialog)
    assert not dialog.magnetic_momentum_management_group.isChecked()
    sc = dialog.to_dataclass()
    assert sc.magnetic_momentum_management is None


def test_dialog_builds_magnetic_momentum_management_config_when_group_checked(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import ActuatorConfig, OrbitIC, SpacecraftConfig

    existing = SpacecraftConfig(
        name="sat-mmm",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        actuators=[
            ActuatorConfig(kind="reaction_wheel", name="rw-1", params={"gsHat_B": [1, 0, 0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0}),
            ActuatorConfig(kind="reaction_wheel", name="rw-2", params={"gsHat_B": [0, 1, 0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0}),
            ActuatorConfig(kind="magnetic_torque_rod", name="mtb-1",
                            params={"gtHat_B": [1, 0, 0], "max_dipole_a_m2": 0.1}),
        ],
        fsw_mode="sunSafePoint",
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    dialog.magnetic_momentum_management_group.setChecked(True)
    assert dialog.mmm_wheel_speed_biases.labels() == ["rw-1", "rw-2"]
    first, second = dialog.mmm_wheel_speed_biases.boxes()
    first.setValue(83.8)  # [rad/s]
    second.setValue(62.8)  # [rad/s]
    dialog.mmm_c_gain.setValue(0.01)

    sc = dialog.to_dataclass()
    assert sc.magnetic_momentum_management is not None
    assert sc.magnetic_momentum_management.wheel_speed_biases_rad_s == [83.8, 62.8]
    assert sc.magnetic_momentum_management.c_gain == 0.01


def test_dialog_round_trips_magnetic_momentum_management(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import (
        ActuatorConfig, MagneticMomentumManagementConfig, OrbitIC, SpacecraftConfig,
    )

    existing = SpacecraftConfig(
        name="sat-mmm",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        actuators=[
            ActuatorConfig(kind="reaction_wheel", name="rw-1", params={"gsHat_B": [1, 0, 0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0}),
            ActuatorConfig(kind="magnetic_torque_rod", name="mtb-1",
                            params={"gtHat_B": [1, 0, 0], "max_dipole_a_m2": 0.1}),
        ],
        fsw_mode="sunSafePoint",
        magnetic_momentum_management=MagneticMomentumManagementConfig(
            wheel_speed_biases_rad_s=[12.5], c_gain=0.02,
        ),
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)

    assert dialog.magnetic_momentum_management_group.isChecked()
    assert dialog.mmm_wheel_speed_biases.values() == [12.5]
    assert dialog.mmm_c_gain.value() == 0.02

    sc = dialog.to_dataclass()
    assert sc.magnetic_momentum_management.wheel_speed_biases_rad_s == [12.5]


def test_wheel_speed_bias_rows_follow_the_reaction_wheel_list(qtbot):
    """Real user feedback: the biases were a comma-separated list matched
    to the wheels by position, with nothing showing which number was which
    wheel. Each wheel now has its own labelled row, kept in step with the
    Sensors/actuators tab."""
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import (
        ActuatorConfig, MagneticMomentumManagementConfig, OrbitIC, ScenarioValidationError, SpacecraftConfig,
    )

    wheel = {"gsHat_B": [1, 0, 0], "rw_type": "Honeywell_HR16", "maxMomentum": 100.0}
    existing = SpacecraftConfig(
        name="sat-mmm",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        actuators=[
            ActuatorConfig(kind="reaction_wheel", name="rw-x", params=wheel),
            ActuatorConfig(kind="magnetic_torque_rod", name="mtb-1",
                           params={"gtHat_B": [1, 0, 0], "max_dipole_a_m2": 0.1}),
            ActuatorConfig(kind="reaction_wheel", name="rw-y", params=wheel),
        ],
        fsw_mode="sunSafePoint",
        magnetic_momentum_management=MagneticMomentumManagementConfig(wheel_speed_biases_rad_s=[10.0, 20.0]),
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)
    biases = dialog.mmm_wheel_speed_biases
    assert biases.labels() == ["rw-x", "rw-y"] and biases.values() == [10.0, 20.0]
    assert "rad/s" in biases.boxes()[0].suffix()

    # A third wheel added on the Sensors/actuators tab gets its own row.
    actuators = dialog.actuator_list.to_list() + [ActuatorConfig(kind="reaction_wheel", name="rw-z", params=wheel)]
    dialog.actuator_list.from_list(actuators)
    dialog.actuator_list.changed.emit()
    assert biases.labels() == ["rw-x", "rw-y", "rw-z"] and biases.values() == [10.0, 20.0, 0.0]

    # No wheels at all: a clear message, not a silent empty list.
    dialog.actuator_list.from_list([a for a in actuators if a.kind != "reaction_wheel"])
    dialog.actuator_list.changed.emit()
    assert biases.values() == [] and not biases.empty_label.isHidden()
    with pytest.raises(ScenarioValidationError, match="at least one reaction wheel"):
        dialog.to_dataclass()


def test_dialog_round_trips_thruster_realism_settings(qtbot):
    from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig, StationKeepingConfig

    existing = SpacecraftConfig(
        name="sat-ep",
        orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0], velocity_km_s=[0, 7.5, 0]),
        station_keeping=StationKeepingConfig(target_altitude_km=550.0, deadband_km=5.0, thrust_n=0.05,
                                              isp_s=1500.0, propellant_kg=5.0, min_on_time_s=300.0,
                                              eccentricity_neutral_burns=True),
    )
    dialog = SpacecraftEditorDialog(config=existing)
    qtbot.addWidget(dialog)

    assert dialog.sk_min_on_time_s.value() == 300.0  # [s]
    assert dialog.sk_eccentricity_neutral_check.isChecked()
    assert dialog.to_dataclass().station_keeping == existing.station_keeping
