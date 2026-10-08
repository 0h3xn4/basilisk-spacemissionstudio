"""Tests for gui.template_wizard -- the guided, multi-step "Customize..."
wizard built over a curated subset of a bundled template's own
parameters (see that module's own docstring for scope/rationale).
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_gui

_ALL_TEMPLATE_FILENAMES = sorted(
    p.name for p in (Path(__file__).resolve().parent.parent.parent
                      / "spacemissionstudio" / "scenarios" / "templates").glob("*.json")
)


def test_every_registered_spec_matches_a_real_bundled_template():
    """Regression guard: a typo'd filename in _SPECS would otherwise
    silently mean that template's "Customize..." button never lights up,
    with no error anywhere pointing at why.
    """
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import _SPECS

    bundled = {p.name for p in TEMPLATES_DIR.glob("*.json")}
    for filename in _SPECS:
        assert filename in bundled, f"{filename} has a wizard spec but no matching bundled template file"


def test_every_bundled_template_has_a_registered_spec():
    """Every template ('01' through '18') has one -- see this module's
    own docstring for the staged rollout history (a 3-template pilot,
    then every other template in one follow-up pass).
    """
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import get_wizard_spec

    bundled = sorted(p.name for p in TEMPLATES_DIR.glob("*.json"))
    assert len(bundled) >= 18
    missing = [name for name in bundled if get_wizard_spec(name) is None]
    assert missing == [], f"these bundled templates have no registered wizard spec: {missing}"


def test_get_wizard_spec_returns_none_for_an_unregistered_template():
    from spacemissionstudio.gui.template_wizard import get_wizard_spec

    assert get_wizard_spec("99_not_a_real_template.json") is None


@pytest.mark.parametrize("filename", _ALL_TEMPLATE_FILENAMES)
def test_wizard_pages_are_prefilled_with_the_templates_own_current_values(qtbot, filename):
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / filename)
    spec = get_wizard_spec(filename)
    wizard = TemplateCustomizeWizard(scenario, spec)
    qtbot.addWidget(wizard)

    for page_id, page_spec in zip(wizard.pageIds(), spec.pages):
        page = wizard.page(page_id)
        assert page.title() == page_spec.title
        for field_spec, box in zip(page_spec.fields, page._boxes):
            assert box.value() == pytest.approx(field_spec.get(scenario))


def test_finishing_without_changes_reproduces_the_original_scenario(qtbot):
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    path = TEMPLATES_DIR / "03_geo_station_keeping.json"
    scenario = load_scenario(path)
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(path.name))
    qtbot.addWidget(wizard)

    wizard.accept()

    result = wizard.result_scenario()
    result.validate()
    assert result.to_dict() == scenario.to_dict()


def test_finishing_applies_edited_values_and_leaves_the_original_scenario_untouched(qtbot):
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    path = TEMPLATES_DIR / "03_geo_station_keeping.json"
    scenario = load_scenario(path)
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(path.name))
    qtbot.addWidget(wizard)

    slot_page = wizard.page(0)
    slot_page._boxes[0].setValue(20.0)  # target longitude [deg], 10 deg further east
    slot_page._boxes[1].setValue(0.1)  # longitude box [deg]
    duration_page = wizard.page(2)
    duration_page._boxes[0].setValue(30.0)  # duration_days

    wizard.accept()

    result = wizard.result_scenario()
    result.validate()
    sat = result.spacecraft[0]
    original = scenario.spacecraft[0]
    assert sat.geo_station_keeping.target_longitude_deg == 20.0
    assert sat.geo_station_keeping.longitude_deadband_deg == 0.1
    # The satellite moves with its slot, or the controller would see a 10 deg drift to undo.
    assert (sat.orbit.true_anomaly_deg - original.orbit.true_anomaly_deg) % 360.0 == pytest.approx(10.0)
    assert result.sim_settings.duration_days == 30.0
    # The Scenario the wizard was constructed from must be untouched --
    # it operates on its own internal copy (see TemplateCustomizeWizard's
    # own docstring).
    assert original.geo_station_keeping.target_longitude_deg == 10.0
    assert scenario.sim_settings.duration_days == 45.0
    # And the bundled template FILE itself must be untouched too.
    assert load_scenario(path).spacecraft[0].geo_station_keeping.longitude_deadband_deg == 0.05


def test_leo_altitude_field_moves_both_target_altitude_and_orbit_semi_major_axis(qtbot):
    """The one field in this first pass whose setter touches two
    dataclass locations at once -- see template_wizard._set_leo_altitude_km's
    own comment for why (orbit.semi_major_axis_km is measured from the
    central body's CENTER, station_keeping.target_altitude_km from its
    surface). The expected offset is THIS TEMPLATE's own
    (semi_major_axis_km - target_altitude_km = 6778.0 - 400.0 = 6378.0,
    not Basilisk's more precise earth.radEquator (6378.1366) -- see
    _set_leo_altitude_km's own comment for why using that constant
    directly instead of this template's own offset was a real,
    now-fixed bug).
    """
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    path = TEMPLATES_DIR / "18_leo_station_keeping.json"
    scenario = load_scenario(path)
    original_offset_km = scenario.spacecraft[0].orbit.semi_major_axis_km - 400.0
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(path.name))
    qtbot.addWidget(wizard)

    altitude_page = wizard.page(0)
    altitude_page._boxes[0].setValue(350.0)
    wizard.accept()

    result = wizard.result_scenario()
    result.validate()
    sat = result.spacecraft[0]
    assert sat.station_keeping.target_altitude_km == 350.0
    assert sat.orbit.semi_major_axis_km == pytest.approx(350.0 + original_offset_km)


def test_reaction_wheel_max_momentum_applies_to_every_wheel_uniformly(qtbot):
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    path = TEMPLATES_DIR / "07_attitude_pointing_with_adcs_hardware.json"
    scenario = load_scenario(path)
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(path.name))
    qtbot.addWidget(wizard)

    wizard.page(0)._boxes[0].setValue(250.0)
    wizard.accept()

    result = wizard.result_scenario()
    result.validate()
    wheel_momenta = [a.params["maxMomentum"] for a in result.spacecraft[0].actuators if a.kind == "reaction_wheel"]
    assert wheel_momenta == [250.0, 250.0, 250.0]


@pytest.mark.parametrize("filename", _ALL_TEMPLATE_FILENAMES)
def test_wizard_is_sized_to_fit_its_own_busiest_page_not_a_flat_default(qtbot, filename):
    """Every section card fits the dialog's width (no sideways scrolling),
    and the dialog stays a sensible size: sections scroll vertically on one
    page. History: a flat QWizard default clipped pages; later one section
    at a time left near-empty dialogs (real user feedback)."""
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / filename)
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(filename))
    qtbot.addWidget(wizard)
    wizard.show()
    _assert_no_sideways_scrolling(wizard)
    widest_section = max(p.sizeHint().width() for p in wizard._field_pages)
    # The dialog grows to the widest card's one-line layout, up to its cap:
    # 1100 px, or less where the screen is narrower (the macOS CI runner's
    # is 1024 px wide).
    cap = min(1100, wizard.screen().availableGeometry().width())
    assert wizard._scroll.viewport().width() >= widest_section or wizard.size().width() >= cap
    assert wizard.size().width() <= 1100 and wizard.size().height() <= 700


def _assert_no_sideways_scrolling(wizard):
    content = wizard._scroll.widget()
    assert content.width() <= wizard._scroll.viewport().width()
    assert max(p.minimumSizeHint().width() for p in wizard._field_pages) <= wizard._scroll.viewport().width()


@pytest.mark.parametrize("filename", ["02_elliptical_orbit_with_perturbations.json", "16_lambert_transfer.json"])
def test_wizard_fits_without_sideways_scrolling_with_large_fonts(qtbot, filename):
    """SRelD K-10: with wider fonts (the Windows CI measured cards about
    1.5 times as wide) the cards no longer fit on one line; hints then wrap
    and long rows put the field under its label, instead of the dialog
    scrolling sideways."""
    from PySide6.QtWidgets import QApplication

    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    app = QApplication.instance()
    original = app.font()
    large = app.font()
    large.setPointSizeF(original.pointSizeF() * 1.5)
    app.setFont(large)
    try:
        wizard = TemplateCustomizeWizard(load_scenario(TEMPLATES_DIR / filename), get_wizard_spec(filename))
        qtbot.addWidget(wizard)
        wizard.show()
        app.processEvents()
        assert max(p.sizeHint().width() for p in wizard._field_pages) > wizard._scroll.viewport().width()
        _assert_no_sideways_scrolling(wizard)
    finally:
        app.setFont(original)


@pytest.mark.parametrize("filename", _ALL_TEMPLATE_FILENAMES)
def test_every_spec_round_trips_with_no_edits(qtbot, filename):
    """Every registered spec, finished with no edits at all, must
    reproduce the original template byte-for-byte -- confirms every
    field's get()/set() pair agrees on the same value (a get() that
    reads the wrong list index/attribute would otherwise still "work"
    right up until a round-trip test like this one actually compared
    before/after).
    """
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / filename)
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec(filename))
    qtbot.addWidget(wizard)

    wizard.accept()

    result = wizard.result_scenario()
    result.validate()
    assert result.to_dict() == scenario.to_dict()


@pytest.mark.parametrize("filename", _ALL_TEMPLATE_FILENAMES)
def test_every_spec_still_validates_after_nudging_every_field(qtbot, filename):
    """Nudges every field by one step within its own declared range and
    confirms the result is still a schema-valid Scenario -- a cheap,
    broad check that no field's chosen (minimum, maximum, step) combination
    can produce an invalid Scenario via entirely ordinary use of the
    spin box (as opposed to typing an extreme value by hand).
    """
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / filename)
    spec = get_wizard_spec(filename)
    wizard = TemplateCustomizeWizard(scenario, spec)
    qtbot.addWidget(wizard)

    for page, page_spec in zip(wizard._field_pages, spec.pages):
        for box, field_spec in zip(page._boxes, page_spec.fields):
            nudged = box.value() + field_spec.step
            if nudged > field_spec.maximum:
                nudged = box.value() - field_spec.step
            box.setValue(nudged)

    wizard.accept()
    result = wizard.result_scenario()
    result.validate()  # must not raise


@pytest.mark.parametrize("filename", sorted(p.name for p in __import__(
    "spacemissionstudio.gui.load_scenario_widget", fromlist=["TEMPLATES_DIR"]).TEMPLATES_DIR.glob("*.json")))
def test_every_wizard_offers_every_setting_of_its_template(qtbot, filename):
    """A real user found the wizards "very incomplete" (each offered 5-20%
    of its template's settings). Every numeric/on-off setting must now be
    reachable: through a curated field, or on a generated page."""
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, _paths_set_by, get_wizard_spec
    from spacemissionstudio.gui.wizard_settings import (
        build_all_settings_pages, setting_paths, vizard_model_settings_hidden,
    )
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / filename)
    spec = get_wizard_spec(filename)
    curated = _paths_set_by(spec, scenario)
    generated = set()
    for page in build_all_settings_pages(scenario, exclude=curated):
        for field in page.fields:
            generated.add(field.get.__defaults__[0])
    hidden = set(vizard_model_settings_hidden(scenario))  # no effect without a Vizard model
    missing = [p for p in setting_paths(scenario) if p not in curated and p not in generated
               and p[:-1] not in curated and p not in hidden]
    assert not missing, missing
    assert not (curated & generated)  # nothing offered twice

    wizard = TemplateCustomizeWizard(scenario, spec)
    qtbot.addWidget(wizard)
    assert len(wizard.pageIds()) == len(spec.pages) + len(build_all_settings_pages(scenario, exclude=curated))


def _set_field(wizard, label_fragment, page_fragment, value):
    for page in wizard._field_pages:
        if page_fragment in page.title():
            for field_spec, box in zip(page._fields, page._boxes):
                if label_fragment in field_spec.label:
                    box.setChecked(value) if field_spec.kind == "bool" else box.setValue(value)
                    return
    raise AssertionError(f"no field {label_fragment!r} on a page {page_fragment!r}")


def test_formation_wizard_sets_the_correction_window_and_the_chiefs_parameters(qtbot):
    """The user's two examples: the correction window, and the chief's own
    parameters (its orbit and station-keeping)."""
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / "05_formation_flying_phasing.json")
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec("05_formation_flying_phasing.json"))
    qtbot.addWidget(wizard)
    _set_field(wizard, "Correction window", "follower-1: phasing keeping", 1.5)  # [day]
    _set_field(wizard, "Deadband", "chief-1: station-keeping", 4.0)  # [km]
    _set_field(wizard, "Inclination", "chief-1: orbit", 97.0)  # [deg]
    _set_field(wizard, "Eccentricity-neutral burns", "chief-1: station-keeping", True)
    wizard.accept()
    result = wizard.result_scenario()
    result.validate()
    chief, follower = result.spacecraft
    assert follower.phasing_keeping.correction_window_days == 1.5
    assert chief.station_keeping.deadband_km == 4.0
    assert chief.orbit.inclination_deg == 97.0
    assert chief.station_keeping.eccentricity_neutral_burns is True
    assert scenario.spacecraft[0].station_keeping.deadband_km != 4.0  # the template itself is untouched


def test_filter_shows_only_matching_sections_and_jumps_to_the_first(qtbot):
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / "05_formation_flying_phasing.json")
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec("05_formation_flying_phasing.json"))
    qtbot.addWidget(wizard)
    wizard._filter.setText("correction")
    visible = [wizard._sections.item(row).text().strip() for row in range(wizard._sections.count())
               if not wizard._sections.item(row).isHidden()]
    assert visible == ["follower-1", "Phasing keeping"]
    assert wizard.current_page().title() == "follower-1: phasing keeping"
    wizard._filter.setText("")
    assert all(not wizard._sections.item(row).isHidden() for row in range(wizard._sections.count()))


def test_value_fields_keep_a_visible_border(qtbot):
    """Real user feedback: "I can't really distinguish if the values are
    editable or not, there is no box around them". The row holder's
    transparent/no-border style leaked into the spin boxes inside it. Each
    field must render a visible edge, distinct from its own interior."""
    from PySide6.QtWidgets import QAbstractSpinBox

    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    filename = "05_formation_flying_phasing.json"
    wizard = TemplateCustomizeWizard(load_scenario(TEMPLATES_DIR / filename), get_wizard_spec(filename))
    qtbot.addWidget(wizard)
    wizard.show()
    qtbot.waitExposed(wizard)
    boxes = [box for box in wizard.findChildren(QAbstractSpinBox) if box.isVisible()][:10]
    assert boxes
    for box in boxes:
        image = box.grab().toImage()
        edge = image.pixelColor(0, image.height() // 2)
        interior = image.pixelColor(image.width() // 3, 3)
        assert edge != interior, f"{box.objectName() or box.text()!r} has no visible border"


def test_inline_hints_and_intros_are_short_plain_lines(qtbot):
    """Real user feedback: three-line help paragraphs in small grey type
    beside each field were "cramped" (e.g. "The along-track distance
    phasing_keeping actively holds..."). Hints are now one short line,
    intros one short sentence, neither with code names; the full text is
    the tooltip."""
    import re

    from PySide6.QtWidgets import QLabel

    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import _MAX_HINT_CHARS, _SPECS, TemplateCustomizeWizard
    from spacemissionstudio.schema import load_scenario

    code_name = re.compile(r"[a-z]_[a-z]|docstring|\(\)")
    for filename, spec in _SPECS.items():
        for page in spec.pages:
            assert len(page.intro) <= 90 and not code_name.search(page.intro), (filename, page.intro)
            for field in page.fields:
                hint = field.inline_hint
                assert hint, (filename, field.label)  # every curated field gets a hint
                assert len(hint) <= _MAX_HINT_CHARS and not code_name.search(hint), (filename, hint)

    filename = "05_formation_flying_phasing.json"
    wizard = TemplateCustomizeWizard(load_scenario(TEMPLATES_DIR / filename), _SPECS[filename])
    qtbot.addWidget(wizard)
    wizard.show()
    hint = next(label for label in wizard.findChildren(QLabel)
                if label.text() == "Distance the follower holds ahead of the chief")
    # One line at the normal font size; it may wrap only when the dialog is
    # too narrow (large fonts, SRelD K-10). Measured on the text itself: the
    # label's own height is pinned to the spin box beside it.
    from PySide6.QtCore import QRect, Qt

    metrics = hint.fontMetrics()
    text_height = metrics.boundingRect(QRect(0, 0, hint.contentsRect().width(), 0),
                                       int(Qt.TextFlag.TextWordWrap), hint.text()).height()
    assert text_height < 1.6 * metrics.height()
    assert "follower-1" in hint.toolTip() and "phasing_keeping" not in hint.toolTip()


def test_lambert_wizard_time_of_flight_moves_the_arrival_coast_not_the_pre_burn_coast(qtbot):
    """Template 16 now coasts to the burn point first; the time-of-flight
    field must keep the coast AFTER the burn in step, and leave the one
    before it alone (it has its own field)."""
    from spacemissionstudio.gui.load_scenario_widget import TEMPLATES_DIR
    from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(TEMPLATES_DIR / "16_lambert_transfer.json")
    wizard = TemplateCustomizeWizard(scenario, get_wizard_spec("16_lambert_transfer.json"))
    qtbot.addWidget(wizard)
    _set_field(wizard, "Time of flight", "Transfer target", 3000.0)  # [s]
    _set_field(wizard, "Coast to burn point", "Transfer target", 1200.0)  # [s]
    wizard.accept()
    result = wizard.result_scenario()
    result.validate()
    before, _report, lambert, after, _report2 = result.mission_sequence
    assert lambert.params["time_of_flight_s"] == 3000.0
    assert after.params["duration_days"] * 86400.0 == pytest.approx(3000.0)
    assert before.params["duration_days"] * 86400.0 == pytest.approx(1200.0)
