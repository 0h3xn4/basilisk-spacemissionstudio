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

"""Every input box in every dialog must look editable: a visible border.

Real user feedback on the Customize dialog: "I can't really distinguish if
the values are editable or not, there is no box around them" -- an
unscoped stylesheet on a container had erased its spin boxes' frames.
This renders each dialog with the app's theme, walks every tab (with every
optional group switched on) and checks each spin box, text field,
drop-down and text area draws an edge distinct from its interior.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_gui

_TEMPLATES = Path(__file__).resolve().parents[2] / "spacemissionstudio" / "scenarios" / "templates"


@pytest.fixture
def themed(qapp):
    from spacemissionstudio.gui.theme import apply_theme

    previous = qapp.styleSheet()
    apply_theme(qapp)
    yield
    qapp.setStyleSheet(previous)


def _template(name):
    from spacemissionstudio.schema import load_scenario

    return load_scenario(next(_TEMPLATES.glob(f"{name}_*.json")))


def _input_widgets(root):
    from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QLineEdit, QPlainTextEdit

    found = []
    for cls in (QAbstractSpinBox, QComboBox, QPlainTextEdit, QLineEdit):
        for widget in root.findChildren(cls):
            if isinstance(widget, QLineEdit) and isinstance(widget.parent(), (QAbstractSpinBox, QComboBox)):
                continue  # the editor inside a spin box/combo: the outer widget draws the frame
            if widget.isVisible() and widget.width() > 8 and widget.height() > 8:
                found.append(widget)
    return found


def _borderless(root):
    """Visible inputs whose left edge renders the same colour as their
    interior, i.e. no border."""
    bad = []
    for widget in _input_widgets(root):
        image = widget.grab().toImage()
        edge = image.pixelColor(0, image.height() // 2)
        interior = image.pixelColor(image.width() // 3, min(3, image.height() - 1))
        if edge == interior:
            bad.append(f"{type(widget).__name__} {widget.objectName() or widget.toolTip()[:40]!r}")
    return bad


def _expand_everything(dialog, qapp):
    from PySide6.QtWidgets import QGroupBox, QTabWidget, QToolButton

    for group in dialog.findChildren(QGroupBox):
        if group.isCheckable():
            group.setChecked(True)
    for button in dialog.findChildren(QToolButton):
        if button.isCheckable():
            button.setChecked(True)  # e.g. the "Advanced (JSON)" disclosures
    qapp.processEvents()
    return dialog.findChildren(QTabWidget)


def _check(dialog, qtbot, qapp):
    qtbot.addWidget(dialog)
    dialog.resize(max(dialog.width(), 1000), max(dialog.height(), 800))  # [px]
    dialog.show()
    qtbot.waitExposed(dialog)
    tab_widgets = _expand_everything(dialog, qapp)
    checked = len(_input_widgets(dialog))
    bad = _borderless(dialog)
    for tabs in tab_widgets:
        for index in range(tabs.count()):
            tabs.setCurrentIndex(index)
            qapp.processEvents()
            checked += len(_input_widgets(dialog))
            bad += [f"[{tabs.tabText(index)}] {item}" for item in _borderless(dialog)]
    assert checked > 0, "no visible inputs found -- the check would pass vacuously"
    assert not sorted(set(bad)), "inputs with no visible border:\n" + "\n".join(sorted(set(bad)))


def _dialogs():
    """(id, factory) for every editor dialog in the app. The Spacecraft
    Template dialog (a preset list) and the startup fetch dialog
    (checkboxes) have no input boxes, so they are not listed."""
    from spacemissionstudio.schema.command import SUPPORTED_COMMAND_KINDS
    from spacemissionstudio.schema.scenario import SUPPORTED_ACTUATOR_KINDS, SUPPORTED_SENSOR_KINDS

    def spacecraft(template, index=0):
        def make():
            from spacemissionstudio.gui.spacecraft_editor import SpacecraftEditorDialog

            scenario = _template(template)
            config = scenario.spacecraft[index]
            others = [sc.name for sc in scenario.spacecraft if sc.name != config.name]
            return SpacecraftEditorDialog(config, other_spacecraft_names=others,
                                          ground_station_names=[gs.name for gs in scenario.ground_stations])
        return make

    def item(kind, sensors):
        def make():
            from spacemissionstudio.gui.sensor_actuator_editor import _ItemEditorDialog
            from spacemissionstudio.schema.scenario import ActuatorConfig, SensorConfig

            dialog = _ItemEditorDialog(SensorConfig if sensors else ActuatorConfig,
                                       SUPPORTED_SENSOR_KINDS if sensors else SUPPORTED_ACTUATOR_KINDS)
            dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findText(kind))
            if dialog.catalog_combo.count() > 1:
                dialog.catalog_combo.setCurrentIndex(1)
            return dialog
        return make

    def command(kind):
        def make():
            from spacemissionstudio.gui.mission_sequence_editor import _CommandEditorDialog

            dialog = _CommandEditorDialog(spacecraft_names=["sat-1"], series_names=["sat-1.position_N"])
            dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findText(kind))
            return dialog
        return make

    def wizard(template):
        def make():
            from spacemissionstudio.gui.template_wizard import TemplateCustomizeWizard, get_wizard_spec

            path = next(_TEMPLATES.glob(f"{template}_*.json"))
            from spacemissionstudio.schema import load_scenario

            return TemplateCustomizeWizard(load_scenario(path), get_wizard_spec(path.name))
        return make

    def simple(module, cls, *args, **kwargs):
        def make():
            import importlib

            return getattr(importlib.import_module(f"spacemissionstudio.gui.{module}"), cls)(*args, **kwargs)
        return make

    def propagation():
        from spacemissionstudio.gui.propagation_setup_dialog import PropagationSetupDialog

        scenario = _template("02")
        return PropagationSetupDialog(scenario.gravity, scenario.sim_settings, scenario.space_weather)

    def ground_station():
        from spacemissionstudio.gui.ground_station_editor import GroundStationEditorDialog

        return GroundStationEditorDialog(_template("19").ground_stations[0])

    def dispersion():
        from spacemissionstudio.gui.monte_carlo_editor import _DispersionEditorDialog

        return _DispersionEditorDialog(["sat-1"])

    def phasing():
        from spacemissionstudio.gui.phasing_formation_dialog import PhasingFormationDialog

        scenario = _template("05")
        return PhasingFormationDialog([sc.name for sc in scenario.spacecraft], spacecraft=scenario.spacecraft)

    def main_window():
        from spacemissionstudio.gui.main_window import MainWindow

        window = MainWindow(prompt_startup_fetch=False, check_autosave_recovery=False)
        window.scenario_editor.from_scenario(_template("19"))
        return window

    cases = [
        ("spacecraft-07", spacecraft("07")), ("spacecraft-13", spacecraft("13")),
        ("spacecraft-19", spacecraft("19")), ("spacecraft-05-follower", spacecraft("05", 1)),
        ("propagation", propagation), ("ground-station", ground_station), ("dispersion", dispersion),
        ("phasing-formation", phasing), ("main-window", main_window),
        ("constellation", simple("constellation_dialog", "WalkerConstellationDialog", ["sat-1"])),
        ("vizard", simple("vizard_dialog", "VizardDialog")),
    ]
    cases += [(f"sensor-{kind}", item(kind, True)) for kind in SUPPORTED_SENSOR_KINDS]
    cases += [(f"actuator-{kind}", item(kind, False)) for kind in SUPPORTED_ACTUATOR_KINDS]
    cases += [(f"command-{kind}", command(kind)) for kind in SUPPORTED_COMMAND_KINDS]
    cases += [(f"customize-{path.name[:2]}", wizard(path.name[:2])) for path in sorted(_TEMPLATES.glob("*.json"))]
    return cases


_CASES = _dialogs()


@pytest.mark.parametrize("factory", [factory for _, factory in _CASES], ids=[name for name, _ in _CASES])
def test_every_input_box_has_a_visible_border(qtbot, qapp, themed, factory):
    _check(factory(), qtbot, qapp)
