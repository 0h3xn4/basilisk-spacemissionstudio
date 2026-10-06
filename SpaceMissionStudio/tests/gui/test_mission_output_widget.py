"""Tests for gui.mission_output_widget.MissionOutputWidget."""

import numpy as np
import pytest

pytestmark = pytest.mark.requires_gui


def test_none_summary_clears_text(qtbot):
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    widget.text_edit.setPlainText("stale content")

    widget.set_command_summary(None)
    assert widget.text_edit.toPlainText() == ""


def test_summary_lists_reports_in_order_with_values(qtbot):
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)

    summary = CommandSummary(reports=[
        ReportEntry(label="checkpoint", t_s=100.0, values={"sat-1.position_N": np.array([1.0, 2.0, 3.0])}),
        ReportEntry(label=None, t_s=200.0, values={"sat-1.mass_kg": np.array([500.0])}),
    ], commands_executed=7)

    widget.set_command_summary(summary)
    text = widget.text_edit.toPlainText()

    assert "7 command(s) executed, 2 report(s)" in text
    assert "t = 100.000 s (checkpoint)" in text
    assert "sat-1.position_N = [1.0, 2.0, 3.0]" in text
    assert "t = 200.000 s" in text
    assert "sat-1.mass_kg = [500.0]" in text


def test_filter_hides_non_matching_reports(qtbot):
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    summary = CommandSummary(reports=[
        ReportEntry(label="apogee", t_s=100.0, values={"sat-1.position_N": np.array([1.0, 2.0, 3.0])}),
        ReportEntry(label="perigee", t_s=200.0, values={"sat-1.mass_kg": np.array([500.0])}),
    ], commands_executed=2)
    widget.set_command_summary(summary)

    widget.filter_edit.setText("apogee")
    text = widget.text_edit.toPlainText()

    assert "apogee" in text
    assert "perigee" not in text
    assert "1 of 2 report(s) match" in text


def test_filter_matches_series_name_and_value_not_just_label(qtbot):
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    summary = CommandSummary(reports=[
        ReportEntry(label=None, t_s=1.0, values={"sat-1.mass_kg": np.array([500.0])}),
        ReportEntry(label=None, t_s=2.0, values={"sat-2.mass_kg": np.array([999.0])}),
    ], commands_executed=2)
    widget.set_command_summary(summary)

    widget.filter_edit.setText("999.0")
    text = widget.text_edit.toPlainText()

    assert "sat-2.mass_kg" in text
    assert "sat-1.mass_kg" not in text


def test_clearing_the_filter_restores_the_full_list(qtbot):
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    summary = CommandSummary(reports=[
        ReportEntry(label="apogee", t_s=100.0, values={"sat-1.position_N": np.array([1.0, 2.0, 3.0])}),
        ReportEntry(label="perigee", t_s=200.0, values={"sat-1.mass_kg": np.array([500.0])}),
    ], commands_executed=2)
    widget.set_command_summary(summary)

    widget.filter_edit.setText("apogee")
    assert "perigee" not in widget.text_edit.toPlainText()

    widget.filter_edit.setText("")
    text = widget.text_edit.toPlainText()
    assert "apogee" in text
    assert "perigee" in text


def test_filter_is_case_insensitive_and_persists_across_a_new_run(qtbot):
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    widget.filter_edit.setText("APOGEE")

    widget.set_command_summary(CommandSummary(reports=[
        ReportEntry(label="apogee", t_s=100.0, values={"sat-1.mass_kg": np.array([500.0])}),
        ReportEntry(label="perigee", t_s=200.0, values={"sat-1.mass_kg": np.array([500.0])}),
    ], commands_executed=2))
    text = widget.text_edit.toPlainText()

    assert "apogee" in text
    assert "perigee" not in text


def test_export_button_tooltip_notes_filter_does_not_affect_export(qtbot):
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    assert "filter" in widget.export_button.toolTip().lower()


def test_export_writes_every_report_regardless_of_active_filter(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from spacemissionstudio.engine.results import CommandSummary, ReportEntry
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    widget.set_command_summary(CommandSummary(commands_executed=2, reports=[
        ReportEntry(label="apogee", t_s=100.0, values={"sat-1.position_N": np.array([1.0, 2.0, 3.0])}),
        ReportEntry(label="perigee", t_s=200.0, values={"sat-1.mass_kg": np.array([500.0])}),
    ]))
    widget.filter_edit.setText("apogee")  # the view is filtered, but export must ignore that

    dest = tmp_path / "output.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(dest), "")))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    widget._on_export()

    content = dest.read_text()
    assert "sat-1.position_N" in content
    assert "sat-1.mass_kg" in content  # the filtered-out "perigee" report is still exported


def test_clear_empties_text(qtbot):
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    widget.text_edit.setPlainText("something")
    widget.clear()
    assert widget.text_edit.toPlainText() == ""


def test_clear_also_resets_the_filter_box(qtbot):
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    widget.filter_edit.setText("apogee")
    widget.clear()
    assert widget.filter_edit.text() == ""


def test_export_button_disabled_until_a_summary_with_reports_is_set(qtbot):
    """Regression guard for a real gap found while auditing this tab:
    CommandSummary.export_csv() already existed and was already tested
    at the engine layer, but nothing in this widget ever called it --
    the neighboring Results tab has had CSV export since the Plotly
    migration, but mission-sequence report output had no way out of the
    GUI except manually copying the text log.
    """
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    assert not widget.export_button.isEnabled()

    widget.set_command_summary(CommandSummary(commands_executed=3, reports=[]))
    assert not widget.export_button.isEnabled()  # nothing to export -- no report commands ran

    widget.set_command_summary(CommandSummary(commands_executed=3, reports=[
        ReportEntry(label=None, t_s=1.0, values={"sat-1.mass_kg": np.array([500.0])}),
    ]))
    assert widget.export_button.isEnabled()

    widget.clear()
    assert not widget.export_button.isEnabled()


def test_export_writes_a_csv_file(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from spacemissionstudio.engine.results import CommandSummary, ReportEntry
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    widget.set_command_summary(CommandSummary(commands_executed=1, reports=[
        ReportEntry(label="checkpoint", t_s=100.0, values={"sat-1.position_N": np.array([1.0, 2.0, 3.0])}),
    ]))

    dest = tmp_path / "output.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(dest), "")))
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))

    widget._on_export()

    assert dest.exists()
    content = dest.read_text()
    assert "sat-1.position_N" in content
    assert len(info_calls) == 1


def test_export_with_no_summary_is_a_no_op(qtbot, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    calls = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: calls.append(1) or ("", "")))
    widget._on_export()  # self._summary is None
    assert calls == []
