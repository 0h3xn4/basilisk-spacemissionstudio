"""Tests for gui.phasing_formation_dialog.PhasingFormationDialog. No
Basilisk needed -- this dialog only builds a
engine.formation.PhasingFormationRequest (that module's own Basilisk
import is lazy, inside generate_phasing_follower() -- see this module's
own docstring), so these tests are requires_gui only, not
requires_basilisk (unlike tests/test_formation.py's own).
"""

import pytest

pytestmark = pytest.mark.requires_gui


def test_description_label_wraps_instead_of_blowing_up_dialog_width(qtbot):
    """Regression guard for a real bug, found via an actual user
    screenshot: the top description QLabel had no setWordWrap(True), so
    Qt sized it (and the whole dialog) to fit its entire paragraph on
    ONE line -- thousands of pixels wide. The window manager then
    centered that oversized dialog, pushing most of it (including every
    row's own label) off the left edge of the screen. The width bound
    below is loose (not pixel-exact) -- it just needs to catch "the
    dialog is absurdly wide again", not pin an exact layout.
    """
    from PySide6.QtWidgets import QLabel

    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1", "follower-1"], central_body="earth")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)

    description_labels = [
        w for w in dialog.findChildren(QLabel) if len(w.text()) > 100
    ]
    assert description_labels, "expected to find the long top description QLabel"
    assert all(w.wordWrap() for w in description_labels)
    # 900 px at the Linux CI's font; as a count of average characters, so a
    # platform with wider fonts (Windows) gets the same bound (SRelD K-10).
    assert dialog.sizeHint().width() < 150 * dialog.fontMetrics().averageCharWidth()


def test_defaults_produce_a_valid_request(qtbot):
    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1", "follower-1"], central_body="earth")
    qtbot.addWidget(dialog)
    request = dialog.to_request()
    assert request.chief_name == "chief-1"
    assert dialog.selected_chief_name() == "chief-1"
    assert dialog.selected_template_name() == "chief-1"
    assert request.along_track_km != 0.0
    assert request.station_keeping_target_altitude_km is None  # "derive" checkbox defaults checked
    assert request.eclipse_sunlit_threshold == 0.99


def test_station_keeping_target_altitude_defaults_to_disabled_spin_box(qtbot):
    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1"])
    qtbot.addWidget(dialog)
    assert dialog.derive_altitude_check.isChecked()
    assert not dialog.station_keeping_target_altitude_km.isEnabled()


def test_unchecking_derive_altitude_enables_spin_box_and_is_used(qtbot):
    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1"])
    qtbot.addWidget(dialog)
    dialog.derive_altitude_check.setChecked(False)
    assert dialog.station_keeping_target_altitude_km.isEnabled()
    dialog.station_keeping_target_altitude_km.setValue(650.0)

    request = dialog.to_request()
    assert request.station_keeping_target_altitude_km == 650.0


def test_editing_eclipse_sunlit_threshold_updates_request(qtbot):
    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1"])
    qtbot.addWidget(dialog)
    dialog.eclipse_sunlit_threshold.setValue(0.9)

    request = dialog.to_request()
    assert request.eclipse_sunlit_threshold == 0.9


def test_the_control_law_choice_reaches_the_request(qtbot):
    """The dialog offers the drift orbit and Basilisk's two formation laws."""
    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1"])
    qtbot.addWidget(dialog)
    combo = dialog.control_law_combo
    assert [combo.itemData(i) for i in range(combo.count())] == ["drift_orbit", "mean_oe", "hill_pd"]
    assert dialog.to_request().control_law == "drift_orbit"
    combo.setCurrentIndex(combo.findData("mean_oe"))
    assert dialog.to_request().control_law == "mean_oe"


def test_central_body_is_not_independently_selectable(qtbot):
    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1"], central_body="mars")
    qtbot.addWidget(dialog)
    # No combo/edit for it -- just the read-only label built in __init__;
    # nothing here should let central_body drift from what the caller passed.
    assert dialog._central_body == "mars"


def test_empty_spacecraft_list_disables_combos(qtbot):
    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog([])
    qtbot.addWidget(dialog)
    assert not dialog.chief_combo.isEnabled()
    assert not dialog.template_combo.isEnabled()
    assert dialog.selected_chief_name() is None


def test_editing_fields_updates_request(qtbot):
    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1", "chief-2"])
    qtbot.addWidget(dialog)
    dialog.chief_combo.setCurrentIndex(1)
    dialog.follower_name_edit.setText("wingman")
    dialog.radial_km.setValue(1.5)
    dialog.along_track_km.setValue(-75.0)
    dialog.cross_track_km.setValue(3.0)
    dialog.thrust_n.setValue(0.1)

    request = dialog.to_request()
    assert request.chief_name == "chief-2"
    assert request.follower_name == "wingman"
    assert request.radial_km == 1.5
    assert request.along_track_km == -75.0
    assert request.cross_track_km == 3.0
    assert request.thrust_n == 0.1


def test_accept_blocked_on_invalid_request(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    dialog = PhasingFormationDialog(["chief-1"])
    qtbot.addWidget(dialog)
    dialog.along_track_km.setValue(0.0)  # invalid: phasing needs a nonzero along-track target
    dialog._on_accept()
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_accept_blocked_when_follower_name_equals_chief_name(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    dialog = PhasingFormationDialog(["chief-1"])
    qtbot.addWidget(dialog)
    dialog.follower_name_edit.setText("chief-1")
    dialog._on_accept()
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_dialog_resizes_to_its_own_sizehint_on_construction(qtbot):
    """See test_constellation_dialog.py's identical test for why --
    measured directly for THIS dialog before the fix: 497x545 vs its own
    497x601 sizeHint().
    """
    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1"])
    qtbot.addWidget(dialog)

    assert dialog.size() == dialog.sizeHint()


def test_thruster_realism_settings_reach_the_request(qtbot):
    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1"])
    qtbot.addWidget(dialog)
    dialog.min_on_time_s.setValue(120.0)  # [s]
    dialog.eccentricity_neutral_check.setChecked(True)

    request = dialog.to_request()
    assert request.min_on_time_s == 120.0  # [s]
    assert request.eccentricity_neutral_burns is True


def test_dialog_defaults_match_the_generator_request_defaults(qtbot):
    import dataclasses

    from spacemissionstudio.engine.formation import PhasingFormationRequest
    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

    dialog = PhasingFormationDialog(["chief-1"], central_body="earth")
    qtbot.addWidget(dialog)
    defaults = {f.name: f.default for f in dataclasses.fields(PhasingFormationRequest)}
    assert dialog.correction_window_days.value() == defaults["correction_window_days"]


def test_chief_station_keeping_is_shown_and_set_from_the_dialog(qtbot):
    """Real user feedback: the generator couldn't set anything on the
    chief. Its station-keeping is prefilled from the selected chief, and
    whatever the user sets (or unchecks) is returned for the chief."""
    from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog
    from spacemissionstudio.schema.scenario import OrbitIC, SpacecraftConfig, StationKeepingConfig

    orbit = OrbitIC(type="classical_elements", semi_major_axis_km=6928.0, eccentricity=0.001,
                    inclination_deg=97.6, raan_deg=0.0, arg_periapsis_deg=0.0, true_anomaly_deg=0.0)
    chief = SpacecraftConfig(name="chief-1", orbit=orbit,
                             station_keeping=StationKeepingConfig(target_altitude_km=545.0, deadband_km=7.0, thrust_n=0.05,
                                                                  isp_s=1500.0, propellant_kg=5.0))
    bare = SpacecraftConfig(name="bare-1", orbit=orbit)
    dialog = PhasingFormationDialog(["chief-1", "bare-1"], parent=None, spacecraft=[chief, bare])
    qtbot.addWidget(dialog)

    assert dialog.chief_group.isChecked()
    assert dialog.chief_deadband_km.value() == 7.0  # [km]
    dialog.chief_deadband_km.setValue(3.0)  # [km]
    dialog.chief_eccentricity_neutral_check.setChecked(True)
    result = dialog.chief_station_keeping()
    assert result.deadband_km == 3.0 and result.target_altitude_km == 545.0
    assert result.eccentricity_neutral_burns is True

    dialog.chief_combo.setCurrentIndex(1)  # a chief with no station-keeping yet
    assert not dialog.chief_group.isChecked()
    assert dialog.chief_target_altitude_km.value() == pytest.approx(6928.0 - 6378.1366)  # [km] from its orbit
    assert dialog.chief_station_keeping() is None
