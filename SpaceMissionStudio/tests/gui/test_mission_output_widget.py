"""Tests for gui.mission_output_widget.MissionOutputWidget."""

import numpy as np
import pytest

pytestmark = pytest.mark.requires_gui


def _widget(qtbot, summary=None, result=None):
    from spacemissionstudio.gui.mission_output_widget import MissionOutputWidget

    widget = MissionOutputWidget()
    qtbot.addWidget(widget)
    if summary is not None:
        widget.set_command_summary(summary, result)
    return widget


def _apogee_perigee():
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry

    return CommandSummary(reports=[
        ReportEntry(label="apogee", t_s=100.0, values={"sat-1.position_N": np.array([1.0, 2.0, 3.0])}),
        ReportEntry(label="perigee", t_s=200.0, values={"sat-1.mass_kg": np.array([500.0])}),
    ], commands_executed=2)


def test_none_summary_clears_the_table(qtbot):
    widget = _widget(qtbot, _apogee_perigee())
    assert widget.table.rowCount() > 0

    widget.set_command_summary(None)
    assert widget.table.rowCount() == 0
    assert not widget.table.isVisibleTo(widget)


def test_summary_shows_one_column_per_report_and_one_row_per_value(qtbot):
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry

    summary = CommandSummary(reports=[
        ReportEntry(label="checkpoint", t_s=100.0, values={"sat-1.position_N": np.array([1.0, 2.0, 3.0])}),
        ReportEntry(label=None, t_s=7200.0, values={"sat-1.mass_kg": np.array([500.0])}),
    ], commands_executed=7)
    widget = _widget(qtbot, summary)
    text = widget.table_text()

    assert widget.summary_label.text() == "7 commands run · 2 reports"
    header = text.splitlines()[0]
    assert header == "Quantity\tcheckpoint 100 s\tReport 2 2 h\tChange"
    assert "Inertial Position (ECI) X [m]\t1\t–\t–" in text  # named like its plot; absent in report 2
    assert "Inertial Position (ECI) Z [m]\t3\t–\t–" in text
    assert "sat-1.mass_kg\t–\t500\t–" in text  # an uncategorized series keeps its code name
    assert widget.table.item(0, 0).toolTip() == "sat-1.position_N"


def test_values_use_display_units_and_change_column_for_two_reports(qtbot):
    """Template 08's before/after reports: angles in degrees, semi-major
    axis in km, no float noise, and the change across the burn in its
    own column -- a change below the shown precision reads 0."""
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry, ResultSet, TimeSeries

    def snapshot(a_m, inc_rad):
        return {"sat-1.orbit_elements.semi_major_axis": np.array([a_m]),
                "sat-1.orbit_elements.inclination": np.array([inc_rad])}

    summary = CommandSummary(commands_executed=5, reports=[
        ReportEntry("Before burn", 8640.0, snapshot(6878136.6, 0.9006898)),
        ReportEntry("After burn", 51840.0, snapshot(7071987.1234, 0.90069)),
    ])
    result = ResultSet(scenario_name="08")
    result.add(TimeSeries("sat-1.orbit_elements.semi_major_axis", np.zeros(1), ("value",), np.zeros((1, 1)), units="m"))
    result.add(TimeSeries("sat-1.orbit_elements.inclination", np.zeros(1), ("value",), np.zeros((1, 1)), units="rad"))
    text = _widget(qtbot, summary, result).table_text()

    assert "Before burn 2.4 h\tAfter burn 14.4 h\tChange" in text
    assert "Osculating elements" in text  # a group header row
    assert "Semi-Major Axis [km]\t6878.14\t7071.99\t+193.85" in text
    assert "Inclination [deg]\t51.6057\t51.6057\t0" in text


def test_change_in_an_angle_goes_the_short_way_round(qtbot):
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry

    summary = CommandSummary(commands_executed=3, reports=[
        ReportEntry("a", 1.0, {"sat-1.orbit_elements.true_anomaly": np.array([np.radians(350.0)])}),
        ReportEntry("b", 2.0, {"sat-1.orbit_elements.true_anomaly": np.array([np.radians(10.0)])}),
    ])
    assert "True Anomaly [deg]\t350\t10\t+20" in _widget(qtbot, summary).table_text()


def test_filter_on_a_report_label_shows_just_that_report(qtbot):
    widget = _widget(qtbot, _apogee_perigee())

    widget.filter_edit.setText("apogee")
    text = widget.table_text()

    assert "apogee" in text
    assert "perigee" not in text
    assert "sat-1.mass_kg" not in text  # only in the hidden report
    assert "1 of 2 reports match" in widget.summary_label.text()


def test_filter_on_a_quantity_keeps_only_matching_rows(qtbot):
    widget = _widget(qtbot, _apogee_perigee())

    widget.filter_edit.setText("mass")
    text = widget.table_text()

    assert "sat-1.mass_kg" in text
    assert "Position" not in text
    assert "1 of 4 rows match" in widget.summary_label.text()


def test_filter_matches_series_name_and_value_not_just_label(qtbot):
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry

    widget = _widget(qtbot, CommandSummary(reports=[
        ReportEntry(label=None, t_s=1.0, values={"sat-1.mass_kg": np.array([500.0])}),
        ReportEntry(label=None, t_s=2.0, values={"sat-2.mass_kg": np.array([999.0])}),
    ], commands_executed=2))

    widget.filter_edit.setText("999.0")
    text = widget.table_text()

    assert "sat-2.mass_kg" in text
    assert "sat-1.mass_kg" not in text


def test_clearing_the_filter_restores_the_full_table(qtbot):
    widget = _widget(qtbot, _apogee_perigee())

    widget.filter_edit.setText("apogee")
    assert "perigee" not in widget.table_text()

    widget.filter_edit.setText("")
    text = widget.table_text()
    assert "apogee" in text
    assert "perigee" in text


def test_filter_is_case_insensitive_and_persists_across_a_new_run(qtbot):
    widget = _widget(qtbot)
    widget.filter_edit.setText("APOGEE")

    widget.set_command_summary(_apogee_perigee())
    text = widget.table_text()

    assert "apogee" in text
    assert "perigee" not in text


def test_two_spacecraft_name_their_rows_and_groups(qtbot):
    from spacemissionstudio.engine.results import CommandSummary, ReportEntry

    widget = _widget(qtbot, CommandSummary(commands_executed=1, reports=[ReportEntry("r", 1.0, {
        "chief-1.orbit_elements.eccentricity": np.array([0.001]),
        "follower-1.orbit_elements.eccentricity": np.array([0.002]),
        "chief-1.position_N": np.array([1.0, 2.0, 3.0]),
    })]))
    text = widget.table_text()
    assert "chief-1: Osculating elements" in text and "follower-1: Osculating elements" in text
    assert "chief-1: Inertial Position (ECI) X [m]" in text


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


def test_clear_empties_the_table(qtbot):
    widget = _widget(qtbot, _apogee_perigee())
    widget.clear()
    assert widget.table.rowCount() == 0
    assert widget.summary_label.text() == ""


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
