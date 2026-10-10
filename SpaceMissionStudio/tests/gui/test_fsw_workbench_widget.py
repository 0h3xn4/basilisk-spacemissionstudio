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
"""The Flight Software tab (SRS-F-18): each spacecraft's export state,
and an export recorded back into the scenario."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_gui

_TEMPLATES = Path(__file__).resolve().parents[2] / "spacemissionstudio" / "scenarios" / "templates"


def _scenario():
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(next(_TEMPLATES.glob("06_*.json")))
    probe = copy.deepcopy(scenario.spacecraft[0])
    probe.name, probe.fsw_mode, probe.actuators = "probe", None, []
    scenario.spacecraft.append(probe)
    return scenario


def _record(tmp_path, scenario):
    from spacemissionstudio.fsw_export import digest
    from spacemissionstudio.schema.scenario import FswExportRecord

    folder = tmp_path / "fsw"
    folder.mkdir()
    (folder / "ICD.md").write_bytes(b"# ICD\n")  # the bytes hashed below, on Windows too
    record = FswExportRecord(spacecraft="sat-1", path=str(folder),
                             config_digest=digest.fsw_config_digest(scenario, "sat-1"), exported_utc="earlier",
                             parts=digest.fsw_config_parts(scenario, "sat-1"))
    (folder / "manifest.json").write_text(json.dumps({"config_digest": record.config_digest,
                                                      "files": {"ICD.md": hashlib.sha256(b"# ICD\n").hexdigest()}}))
    return folder, record


def test_each_spacecraft_shows_its_export_state(qtbot, tmp_path):
    """Up to date, then stale naming what changed, then folder missing;
    a spacecraft without attitude flight software cannot be exported."""
    from spacemissionstudio.gui.fsw_workbench_widget import FlightSoftwareWidget

    scenario = _scenario()
    folder, record = _record(tmp_path, scenario)
    scenario.fsw_exports = [record]
    widget = FlightSoftwareWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(scenario)
    widget._refresh()
    card = widget.card("sat-1")
    assert card.badge.text() == "Up to date" and card.export_button.isEnabled() and card.open_button.isEnabled()
    probe = widget.card("probe")
    assert probe.badge.text() == "Not exportable" and not probe.export_button.isEnabled()
    assert "pointing mode not set" in probe.detail.text()
    scenario.spacecraft[0].control_params["K"] = 1.0
    widget._refresh()
    assert card.badge.text() == "Stale" and "control_params" in card.detail.text()
    (folder / "manifest.json").unlink()
    widget._refresh()
    assert card.badge.text() == "Folder missing"
    widget.set_scenario(None)
    widget._refresh()
    assert widget._placeholder.isVisibleTo(widget) and widget.card("sat-1") is None


def test_the_scenario_editor_keeps_the_export_records(qtbot, tmp_path):
    """No widget edits them, so they must survive opening and every edit."""
    from spacemissionstudio.gui.scenario_editor import ScenarioEditorWidget

    scenario = _scenario()
    _, record = _record(tmp_path, scenario)
    scenario.fsw_exports = [record]
    editor = ScenarioEditorWidget()
    qtbot.addWidget(editor)
    editor.from_scenario(scenario)
    assert editor.draft_scenario().fsw_exports == [record]
    with qtbot.waitSignal(editor.changed):
        editor.set_fsw_exports([])
    assert editor.draft_scenario().fsw_exports == []


@pytest.mark.requires_basilisk
def test_export_from_the_tab_records_it(qtbot, tmp_path):
    """Export... records a short run in a worker, writes the project and
    hands the new record to the scenario; the card then shows Up to date."""
    from spacemissionstudio.gui.fsw_workbench_widget import FlightSoftwareWidget

    scenario = _scenario()
    widget = FlightSoftwareWidget()
    qtbot.addWidget(widget)
    widget.set_scenario(scenario)
    widget._refresh()
    assert widget.card("sat-1").badge.text() == "Not exported"
    widget.choose_folder = lambda name: tmp_path / "export"
    with qtbot.waitSignal(widget.exports_changed, timeout=120000) as signal:
        widget.card("sat-1").export_button.click()
    widget.wait_for_worker()
    (records,) = signal.args
    assert [r.spacecraft for r in records] == ["sat-1"] and (tmp_path / "export" / "CMakeLists.txt").is_file()
    assert widget.card("sat-1").badge.text() == "Up to date"
