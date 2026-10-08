"""Tests for spacemissionstudio.engine.results -- no Basilisk import, runs anywhere."""

import csv

import json

import numpy as np
import pytest

from spacemissionstudio.engine.results import (
    CommandSummary,
    ReportEntry,
    ResultSet,
    ResultsError,
    RunProvenance,
    TimeSeries,
    conservation_drift_warnings,
)

_EARTH_MU = 3.986004418e14  # [m^3/s^2]


def _circular_orbit_rv(radius_m=7.0e6, n=200, num_orbits=1.0):
    """An exact (to floating-point precision) circular two-body orbit --
    specific energy and angular momentum are both truly constant, so this
    is the clean "no warning" baseline for conservation_drift_warnings.
    """
    omega = np.sqrt(_EARTH_MU / radius_m ** 3)
    t = np.linspace(0.0, num_orbits * 2.0 * np.pi / omega, n)
    r = radius_m * np.column_stack([np.cos(omega * t), np.sin(omega * t), np.zeros_like(t)])
    v = radius_m * omega * np.column_stack([-np.sin(omega * t), np.cos(omega * t), np.zeros_like(t)])
    return r, v


def _sample_series(name="s", n=10):
    t = np.linspace(0.0, 90.0, n)
    data = np.column_stack([np.sin(t), np.cos(t), t * 0.01])
    return TimeSeries(name=name, time_s=t, columns=("x", "y", "z"), data=data, units="m")


def test_time_series_shape_mismatch_rejected():
    t = np.linspace(0, 10, 5)
    data = np.zeros((4, 3))  # one row short
    with pytest.raises(ResultsError, match="must match"):
        TimeSeries(name="bad", time_s=t, columns=("x", "y", "z"), data=data)


def test_time_series_column_count_mismatch_rejected():
    t = np.linspace(0, 10, 5)
    data = np.zeros((5, 3))
    with pytest.raises(ResultsError, match="columns"):
        TimeSeries(name="bad", time_s=t, columns=("x", "y"), data=data)  # 2 names for 3 columns


def test_time_series_accepts_1d_data_as_single_column():
    t = np.linspace(0, 10, 5)
    ts = TimeSeries(name="scalar", time_s=t, columns=("value",), data=np.arange(5.0))
    assert ts.data.shape == (5, 1)


def test_to_csv_round_trips_values(tmp_path):
    ts = _sample_series()
    path = ts.to_csv(tmp_path / "out.csv")
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["time_s", "x_m", "y_m", "z_m"]
    assert len(rows) == 1 + len(ts.time_s)
    # spot-check the first data row round-trips numerically
    assert float(rows[1][0]) == pytest.approx(ts.time_s[0])
    assert float(rows[1][1]) == pytest.approx(ts.data[0, 0])


def test_result_set_add_and_export(tmp_path):
    rs = ResultSet(scenario_name="test")
    rs.add(_sample_series("sat-1.position_N"))
    rs.add(_sample_series("sat-1.velocity_N"))
    paths = rs.export_csv(tmp_path / "out")
    assert set(paths) == {"sat-1.position_N", "sat-1.velocity_N"}
    for p in paths.values():
        assert p.exists()


def _sample_provenance(**overrides) -> RunProvenance:
    defaults = dict(
        spacemissionstudio_version="9.9.9", basilisk_version="2.12.0",
        run_started_utc="2030-01-01T00:00:00+00:00", integrator="rkf78", dynamics_task_rate_s=10.0,
    )
    defaults.update(overrides)
    return RunProvenance(**defaults)


def test_result_set_provenance_defaults_to_none():
    rs = ResultSet(scenario_name="test")
    assert rs.provenance is None


def test_result_set_export_csv_without_provenance_writes_no_sidecar(tmp_path):
    rs = ResultSet(scenario_name="test")
    rs.add(_sample_series("sat-1.position_N"))
    paths = rs.export_csv(tmp_path / "out")
    assert "provenance" not in paths
    assert not (tmp_path / "out" / "provenance.json").exists()


def test_result_set_export_csv_with_provenance_writes_sidecar_json(tmp_path):
    rs = ResultSet(scenario_name="test", provenance=_sample_provenance())
    rs.add(_sample_series("sat-1.position_N"))
    paths = rs.export_csv(tmp_path / "out")
    assert "provenance" in paths
    written = json.loads(paths["provenance"].read_text())
    assert written == {
        "spacemissionstudio_version": "9.9.9",
        "basilisk_version": "2.12.0",
        "run_started_utc": "2030-01-01T00:00:00+00:00",
        "integrator": "rkf78",
        "dynamics_task_rate_s": 10.0,
        "rng_seed_note": RunProvenance.__dataclass_fields__["rng_seed_note"].default,
        # configuration record (R01), empty when not filled by engine.service
        "qualified_basilisk_version": "",
        "basilisk_qualified": False,
        "dependency_versions": {},
        "scenario_sha256": "",
        "data_files": {},
        # frames and time scales (R02), empty when not filled by engine.service
        "time_system": {},
        "frames": {},
        "transformations": {},
        "series_frames": {},
    }


def test_result_set_export_csv_with_provenance_and_no_series_still_writes_sidecar(tmp_path):
    # export_csv() must mkdir the output directory itself in this case --
    # with at least one series, TimeSeries.to_csv() already does that, but
    # a ResultSet with ONLY provenance and no series (e.g. a mission with
    # no propagate command) must not silently skip writing it.
    rs = ResultSet(scenario_name="test", provenance=_sample_provenance())
    paths = rs.export_csv(tmp_path / "out")
    assert set(paths) == {"provenance"}
    assert paths["provenance"].exists()


def test_result_set_rejects_duplicate_series_name():
    rs = ResultSet(scenario_name="test")
    rs.add(_sample_series("dup"))
    with pytest.raises(ResultsError, match="already added"):
        rs.add(_sample_series("dup"))


def test_result_set_warnings_defaults_to_empty_list():
    assert ResultSet(scenario_name="test").warnings == []


# -- conservation_drift_warnings ---------------------------------------------

def test_conservation_drift_warnings_clean_circular_orbit_has_no_warnings():
    r, v = _circular_orbit_rv(num_orbits=3.0)
    assert conservation_drift_warnings("sat-1", _EARTH_MU, r, v) == []


def test_conservation_drift_warnings_too_few_samples_has_no_warnings():
    r, v = _circular_orbit_rv(n=1)
    assert conservation_drift_warnings("sat-1", _EARTH_MU, r, v) == []


def test_conservation_drift_warnings_detects_injected_energy_and_momentum_drift():
    r, v = _circular_orbit_rv(n=200, num_orbits=1.0)
    # A velocity magnitude that grows 10% over the run is not anything a
    # real two-body orbit would do on its own -- injected here to
    # simulate exactly the kind of silent numerical blowup this function
    # exists to catch.
    growth = np.linspace(1.0, 1.10, r.shape[0])[:, None]
    drifting_v = v * growth

    warnings = conservation_drift_warnings("sat-1", _EARTH_MU, r, drifting_v)

    assert len(warnings) == 2  # both energy and angular momentum exceed tolerance
    assert any("sat-1" in w and "energy" in w for w in warnings)
    assert any("sat-1" in w and "angular momentum" in w for w in warnings)


def test_conservation_drift_warnings_respects_custom_tolerance():
    r, v = _circular_orbit_rv(n=200, num_orbits=1.0)
    growth = np.linspace(1.0, 1.001, r.shape[0])[:, None]  # a tiny, sub-1% drift
    drifting_v = v * growth

    assert conservation_drift_warnings("sat-1", _EARTH_MU, r, drifting_v) == []  # within the default 1% tolerance
    # The same tiny drift DOES trip a much tighter tolerance.
    tight = conservation_drift_warnings("sat-1", _EARTH_MU, r, drifting_v, energy_tol=1e-6, momentum_tol=1e-6)
    assert len(tight) == 2


def test_command_summary_export_csv_long_format(tmp_path):
    summary = CommandSummary(reports=[
        ReportEntry(label="checkpoint", t_s=100.0, values={
            "sat-1.position_N": np.array([1.0, 2.0, 3.0]),
            "sat-1.mass_kg": np.array([500.0]),
        }),
        ReportEntry(label=None, t_s=200.0, values={"sat-1.position_N": np.array([4.0, 5.0, 6.0])}),
    ], commands_executed=5)

    path = summary.export_csv(tmp_path / "command_summary.csv")
    with open(path, newline="") as f:
        rows = list(csv.reader(f))

    assert rows[0] == ["report_index", "t_s", "label", "series", "component", "value"]
    # 3 components (position) + 1 (mass) for report 0, 3 components for report 1.
    assert len(rows) == 1 + 4 + 3

    position_rows = [r for r in rows[1:] if r[0] == "0" and r[3] == "sat-1.position_N"]
    assert len(position_rows) == 3
    assert [r[4] for r in position_rows] == ["0", "1", "2"]
    assert [float(r[5]) for r in position_rows] == pytest.approx([1.0, 2.0, 3.0])
    assert position_rows[0][2] == "checkpoint"

    unlabeled_rows = [r for r in rows[1:] if r[0] == "1"]
    assert all(r[2] == "" for r in unlabeled_rows)


def test_command_summary_export_csv_creates_parent_dir(tmp_path):
    summary = CommandSummary(reports=[
        ReportEntry(label="x", t_s=0.0, values={"s": np.array([1.0])}),
    ])
    path = summary.export_csv(tmp_path / "nested" / "dir" / "out.csv")
    assert path.exists()


def test_command_summary_export_csv_with_no_reports_writes_header_only(tmp_path):
    path = CommandSummary().export_csv(tmp_path / "out.csv")
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    assert rows == [["report_index", "t_s", "label", "series", "component", "value"]]


def test_conservation_drift_warnings_stay_short():
    """Each warning is one scannable line in the Results tab (they used to
    be ~330-character paragraphs); the explanation lives in a tooltip."""
    r, v = _circular_orbit_rv(n=200, num_orbits=1.0)
    drifting_v = v * np.linspace(1.0, 1.10, r.shape[0])[:, None]
    for warning in conservation_drift_warnings("sat-1", _EARTH_MU, r, drifting_v):
        assert len(warning) <= 120, warning
