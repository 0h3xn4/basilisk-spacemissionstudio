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

"""engine.monte_carlo_results: the pickle-free batch summary and the
spread measured from it (Basilisk-free, on synthetic circular orbits)."""

import json
import math

import numpy as np
import pytest

from spacemissionstudio.engine import monte_carlo_results as mcr

_R_M = 6778.0e3  # [m] orbit radius
_N_RAD_S = math.sqrt(3.986004415e14 / _R_M ** 3)  # [rad/s] mean motion


def _circular_batch(phase_rad, radius_offsets_m=None, inclinations_rad=None, samples=50, names=("sat-1",)):
    """Equatorial (or slightly inclined) circular orbits, one per run, each
    ``phase_rad[k]`` ahead of the others and ``radius_offsets_m[k]`` higher."""
    runs = len(phase_rad)
    radius_offsets_m = np.zeros(runs) if radius_offsets_m is None else np.asarray(radius_offsets_m)
    inclinations_rad = np.zeros(runs) if inclinations_rad is None else np.asarray(inclinations_rad)
    t = np.linspace(0.0, 6000.0, samples)  # [s]
    positions, velocities = [], []
    for k in range(runs):
        r = _R_M + radius_offsets_m[k]
        u = _N_RAD_S * t + phase_rad[k]
        ci, si = math.cos(inclinations_rad[k]), math.sin(inclinations_rad[k])
        pos = np.stack([r * np.cos(u), r * np.sin(u) * ci, r * np.sin(u) * si], axis=1)
        vel = np.stack([-r * _N_RAD_S * np.sin(u), r * _N_RAD_S * np.cos(u) * ci, r * _N_RAD_S * np.cos(u) * si], 1)
        positions.append(pos)
        velocities.append(vel)
    positions, velocities = np.stack(positions), np.stack(velocities)
    return mcr.MonteCarloBatch("synthetic", "earth", t, list(range(runs)), [],
                               {name: positions for name in names}, {name: velocities for name in names},
                               [{f"{names[0]} drag coefficient [-]": 2.2 + 0.1 * k} for k in range(runs)],
                               "2030-01-01T00:00:00")


def test_a_large_along_track_spread_does_not_show_up_as_radial():
    """Runs on the same circle 450 km apart along track: a straight-line
    frame gave them a false radial spread of ~15 km (the orbit curving away
    from the chord); the curvilinear offsets give none."""
    spread_rad = 450e3 / _R_M  # [rad]
    batch = _circular_batch(np.linspace(-spread_rad, spread_rad, 11))
    rel = mcr.offsets(batch.positions["sat-1"], batch.velocities["sat-1"])
    assert np.abs(rel[..., 0]).max() < 1.0  # [m] radial
    assert rel[:, 0, 1] == pytest.approx(np.linspace(-450e3, 450e3, 11), rel=1e-6)  # [m] arc along track
    assert np.abs(rel[..., 2]).max() < 1.0  # [m] cross-track


def test_radial_and_cross_track_offsets_are_measured_from_the_mean():
    """A run 2 km higher, and one tilted out of the plane, show up where they should."""
    batch = _circular_batch([0.0, 0.0, 0.0], radius_offsets_m=[0.0, 2000.0, 0.0],
                            inclinations_rad=[0.0, 0.0, 1e-3])
    rel = mcr.offsets(batch.positions["sat-1"], batch.velocities["sat-1"])
    radial = rel[:, 0, 0]
    assert radial[1] - radial[0] == pytest.approx(2000.0, abs=1.0)  # [m]
    quarter = int(np.argmin(np.abs(batch.time_s - math.pi / 2 / _N_RAD_S)))  # the third run's most northern point
    cross = rel[:, quarter, 2]
    assert cross[2] - cross[0] == pytest.approx(_R_M * 1e-3, rel=0.01)  # [m]


def test_save_and_load_round_trip_without_pickles(tmp_path):
    """The summary is a plain .npz and .json; reading it never unpickles
    (S-04): every array loads with allow_pickle=False."""
    batch = _circular_batch([0.0, 1e-4, -1e-4], names=("chief", "follower"))
    mcr.save(batch, tmp_path)
    with np.load(tmp_path / mcr.SUMMARY_NPZ, allow_pickle=False) as data:
        assert all(data[key].dtype != object for key in data.files)
    loaded = mcr.load(tmp_path)
    assert loaded.spacecraft == ["chief", "follower"]
    assert loaded.runs == [0, 1, 2] and loaded.failed == [] and loaded.epoch_utc == "2030-01-01T00:00:00"
    np.testing.assert_array_equal(loaded.positions["follower"], batch.positions["follower"])
    assert loaded.drawn == batch.drawn


def test_a_folder_without_a_summary_or_of_another_format_is_refused(tmp_path):
    """A plain message, never a traceback, so the GUI can show it."""
    with pytest.raises(mcr.MonteCarloResultsError, match="has no Monte Carlo results"):
        mcr.load(tmp_path)
    mcr.save(_circular_batch([0.0, 1e-4]), tmp_path)
    meta = json.loads((tmp_path / mcr.SUMMARY_JSON).read_text())
    meta["format"] = 99
    (tmp_path / mcr.SUMMARY_JSON).write_text(json.dumps(meta))
    with pytest.raises(mcr.MonteCarloResultsError, match="format-1"):
        mcr.load(tmp_path)
    meta["format"] = 1
    meta["runs"] = [0, 1, 2]  # one more run than the arrays hold
    (tmp_path / mcr.SUMMARY_JSON).write_text(json.dumps(meta))
    with pytest.raises(mcr.MonteCarloResultsError, match="do not match"):
        mcr.load(tmp_path)


def test_result_set_has_per_run_series_and_the_spread(monkeypatch):
    """Per-run series hold at most MAX_PLOTTED_RUNS columns; the spread is
    computed over every run."""
    monkeypatch.setattr(mcr, "MAX_PLOTTED_RUNS", 4)
    batch = _circular_batch(np.linspace(-1e-3, 1e-3, 9))
    result = mcr.to_result_set(batch)
    assert sorted(result.series) == [f"sat-1.monte_carlo.{field}" for field in
                                     ("along_track_offset", "altitude", "cross_track_offset", "radial_offset",
                                      "spread")]
    assert list(result.series["sat-1.monte_carlo.altitude"].columns) == ["run_0", "run_1", "run_2", "run_3"]
    altitude = result.series["sat-1.monte_carlo.altitude"].data
    assert altitude == pytest.approx(_R_M - 6378.1366e3)  # [m] above Earth's equatorial radius
    spread = result.series["sat-1.monte_carlo.spread"]
    assert list(spread.columns) == ["radial", "along_track", "cross_track"]
    expected = np.std(np.linspace(-1e-3, 1e-3, 9)) * _R_M  # [m] all nine runs
    assert spread.data[:, 1] == pytest.approx(expected, rel=1e-6)


def test_run_table_lists_drawn_values_and_where_each_run_ended():
    batch = _circular_batch([0.0, 1e-4, -1e-4])
    labels, rows = mcr.run_table(batch)
    assert labels == ["Run", "sat-1 drag coefficient [-]", "sat-1 final radial offset [km]",
                      "sat-1 final along-track offset [km]", "sat-1 final cross-track offset [km]"]
    assert [row[0] for row in rows] == [0.0, 1.0, 2.0]
    assert rows[1][1] == pytest.approx(2.3)
    assert rows[1][3] == pytest.approx(1e-4 * _R_M / 1e3, rel=1e-6)  # [km] leads the mean
    summary = mcr.final_spread(batch, "sat-1")
    assert summary.along_track_m == pytest.approx(np.std([0.0, 1e-4, -1e-4]) * _R_M, rel=1e-6)
    assert summary.altitude_min_m == pytest.approx(_R_M - 6378.1366e3)


def test_the_summary_keeps_at_most_max_samples():
    assert mcr.stride_for(mcr.MAX_SAMPLES) == 1
    assert mcr.stride_for(mcr.MAX_SAMPLES + 1) == 2
    assert -(-86401 // mcr.stride_for(86401)) <= mcr.MAX_SAMPLES  # a day at 1 s


def test_identical_runs_report_zero_spread_not_rounding_noise():
    """Template 09's runs differ only in mass, which two-body motion ignores:
    the spread is ~1e-28 km and must read 0 km."""
    batch = _circular_batch([0.0, 0.0, 0.0])
    assert mcr.format_km(4.14e-25) == "0 km" and mcr.format_km(447960.0) == "448 km"
    assert "along-track 0 km, radial 0 km, cross-track 0 km" in mcr.summary_lines(batch)[1]
