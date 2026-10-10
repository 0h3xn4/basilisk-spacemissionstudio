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

"""Running the flight software in the loop from the Flight Software tab
(SRS-F-19): the Run SIL dialog's consent (the program's path and SHA-256,
confirmed again for every new program), the request it hands to the main
window, and the comparison panel."""

import copy
import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_gui

_TEMPLATES = Path(__file__).resolve().parents[2] / "spacemissionstudio" / "scenarios" / "templates"
_LAYOUT = {"itemsize": 16, "fields": [{"name": "torque", "offset": 0, "shape": [2], "kind": "<f8"}]}


def _program(tmp_path, name="fsw_host"):
    path = tmp_path / name
    path.write_bytes(b"#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return path


def _report(missing=False):
    from spacemissionstudio.sil.contract import PortSpec
    from spacemissionstudio.sil.report import Comparator, SilReport, timing_summary

    port = PortSpec("rw_torqueOutMsg", "Demo", 16, "0" * 16)
    comparator = Comparator([port], [], {"Demo": _LAYOUT}, expected_steps=3)
    for t in (0.0, 1.0, 2.0):
        comparator.add(t, [None if missing else struct.pack("<2d", 1.0 + t, 0.5)], [struct.pack("<2d", 1.0, 0.5)])
    report = SilReport(spacecraft="sat-1", binary="/opt/fsw/fsw_host", binary_sha256="a" * 64, fsw_name="sat-1",
                       fsw_config_digest="1" * 64, scenario_config_digest="1" * 64, contract_version=1,
                       rate_ns=1_000_000_000, address_kind="unix", round_trip=timing_summary([200_000, 400_000]),
                       execution=timing_summary([5_000, 6_000]), completed=True)
    comparator.finish(report)
    report.steps = 3
    return report


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executable bit")
def test_the_dialog_shows_the_programs_hash_and_needs_consent_for_each_program(qtbot, tmp_path):
    """Run SIL stays off until the program exists, is executable and the
    user ticks the consent; a different program clears the consent. The
    options carry the hash the user saw, and the deadline."""
    from spacemissionstudio.gui.sil_dialog import SilRunDialog

    export = tmp_path / "export"
    (export / "build").mkdir(parents=True)
    program = _program(export / "build")
    dialog = SilRunDialog("sat-1", export)
    qtbot.addWidget(dialog)
    assert dialog.path_edit.text() == str(program)  # the export's own build found
    assert dialog.hash_label.text() == hashlib.sha256(program.read_bytes()).hexdigest()
    assert not dialog.run_button.isEnabled()
    dialog.consent_check.setChecked(True)
    assert dialog.run_button.isEnabled()
    plain = tmp_path / "notes.txt"
    plain.write_text("not a program")
    dialog.path_edit.setText(str(plain))
    assert not dialog.consent_check.isChecked() and not dialog.run_button.isEnabled()
    assert "not executable" in dialog.problem_label.text()
    other = _program(tmp_path, "fsw_adapter_host")
    dialog.path_edit.setText(str(other))
    dialog.consent_check.setChecked(True)
    dialog.deadline_spin.setValue(2.5)  # [ms]
    options = dialog.to_options()
    assert options.binary == str(other.resolve()) and options.expected_sha256 == dialog.hash_label.text()
    assert options.timeouts.deadline_s == pytest.approx(2.5e-3) and options.transport == "auto"


def test_the_tab_hands_the_confirmed_request_to_the_main_window(qtbot):
    """Run SIL... asks for the options and emits sil_requested; while the
    run is in progress no other SIL or export can start; the report comes
    back into the comparison panel. A spacecraft that cannot be exported
    cannot be run in the loop either."""
    from spacemissionstudio.gui.fsw_workbench_widget import FlightSoftwareWidget
    from spacemissionstudio.schema import load_scenario
    from spacemissionstudio.sil.runner import SilOptions

    scenario = load_scenario(next(_TEMPLATES.glob("06_*.json")))
    probe = copy.deepcopy(scenario.spacecraft[0])
    probe.name, probe.fsw_mode = "probe", None
    scenario.spacecraft.append(probe)
    widget = FlightSoftwareWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(scenario)
    widget._refresh()
    assert widget.card("sat-1").sil_button.isEnabled() and not widget.card("probe").sil_button.isEnabled()
    options = SilOptions("/opt/fsw/fsw_host")
    widget.ask_sil_options = lambda name: options
    with qtbot.waitSignal(widget.sil_requested) as signal:
        widget.card("sat-1").sil_button.click()
    assert signal.args == ["sat-1", options]
    widget.set_sil_running("sat-1")
    card = widget.card("sat-1")
    assert card.badge.text() == "In the loop..." and not card.sil_button.isEnabled()
    widget.show_sil_report(_report())
    assert card.sil_button.isEnabled() and widget.comparison.report is not None
    widget.ask_sil_options = lambda name: None  # cancelled: nothing is requested
    with qtbot.assertNotEmitted(widget.sil_requested):
        card.sil_button.click()


def test_the_comparison_panel_shows_the_numbers_and_saves_the_report(qtbot, tmp_path):
    """Tiles for steps, drops, the largest residual and timing; the signal
    table sorted by the largest residual, never-written outputs marked; the
    program's output; Save report writes the JSON and the residual CSV."""
    from spacemissionstudio.gui.sil_comparison_widget import SilComparisonWidget

    panel = SilComparisonWidget()
    qtbot.addWidget(panel)
    assert not panel.save_button.isEnabled() and panel.title_label.text() == "No SIL run yet"
    report = _report()
    report.log_tail = "fsw_host: connected\n"
    panel.show_report(report)
    tiles = [panel.tiles_row.itemAt(i).widget() for i in range(panel.tiles_row.count())
             if panel.tiles_row.itemAt(i).widget() is not None]
    texts = [label.text() for tile in tiles for label in tile.findChildren(type(panel.title_label))]
    assert "3" in texts and "2" in texts and "Max |residual|" in texts and "Round trip p99" in texts
    assert panel.table.item(0, 0).text() == "rw_torqueOutMsg.torque[0]" and panel.table.item(0, 2).text() == "2"
    assert panel.table.rowCount() == 2 and panel.log_view.toPlainText() == "fsw_host: connected\n"
    assert panel.title_label.text() == "sat-1 in the loop with fsw_host"
    panel.choose_report_path = lambda: tmp_path / "sil.json"
    panel.save_button.click()
    assert json.loads((tmp_path / "sil.json").read_text())["steps"] == 3
    assert (tmp_path / "sil.residuals.csv").read_text().startswith("time_s,")
    panel.show_report(_report(missing=True), failure="the flight software did not answer for 10 s")
    assert panel.table.item(0, 2).text() == "not written"
    assert panel.status_label.text().startswith("Stopped: the flight software did not answer")
    panel.show_report(None)
    assert panel.table.rowCount() == 0 and not panel.views.isVisibleTo(panel)


def test_the_mouse_wheel_changes_nothing_on_the_comparison_panel(qtbot, qapp):
    """With a report shown, scrolling over the panel's tabs and boxes
    changes no view (the app-wide no-wheel rule)."""
    from test_wheel_in_dialogs import _changed_by_wheel

    from spacemissionstudio.gui.sil_comparison_widget import SilComparisonWidget

    panel = SilComparisonWidget()
    qtbot.addWidget(panel)
    panel.show_report(_report())
    panel.resize(1000, 800)  # [px]
    panel.show()
    qtbot.waitExposed(panel)
    changed, count = _changed_by_wheel(panel, qapp)
    assert count > 0 and not changed, changed
