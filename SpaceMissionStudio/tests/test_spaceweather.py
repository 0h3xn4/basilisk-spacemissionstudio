"""Tests for spacemissionstudio.engine.spaceweather -- no Basilisk import, runs
anywhere. resolve() itself makes no network calls at all (see its own
"Closed-off/offline policy" docstring) -- only "local_file" and "synthetic"
are valid source values; "celestrak" (and anything else) is rejected as an
unknown source. fetch() is a separate, never-automatically-called utility
(only reached via gui.startup_fetch_dialog's consent-gated prompt) --
its own network calls are mocked here (urllib.request.urlopen), same as
gui/test_vizard_launcher.py's fetch_vizard() tests.
"""

from datetime import datetime

import pytest

from spacemissionstudio.engine import spaceweather as sw


def test_generate_synthetic_passes_its_own_validation(tmp_path):
    start, end = datetime(2030, 1, 1), datetime(2030, 1, 10)
    path = sw.generate_synthetic(start, end, tmp_path / "synth.csv")
    result = sw.validate_file(path, start, end)
    assert result.ok, result.message


def test_generate_synthetic_is_deterministic(tmp_path):
    start, end = datetime(2030, 1, 1), datetime(2030, 1, 5)
    path_a = sw.generate_synthetic(start, end, tmp_path / "a.csv", seed=7)
    path_b = sw.generate_synthetic(start, end, tmp_path / "b.csv", seed=7)
    assert path_a.read_text() == path_b.read_text()


def test_validate_file_rejects_missing_file(tmp_path):
    result = sw.validate_file(tmp_path / "nope.csv", datetime(2030, 1, 1), datetime(2030, 1, 2))
    assert not result.ok
    assert "does not exist" in result.message


def test_validate_file_rejects_missing_required_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("DATE,AP1\n2030-01-01,5\n")
    result = sw.validate_file(path, datetime(2030, 1, 1), datetime(2030, 1, 2))
    assert not result.ok
    assert "AP_AVG" in result.message


def test_validate_file_rejects_insufficient_date_range(tmp_path):
    path = tmp_path / "short.csv"
    header = ",".join(sw.REQUIRED_COLUMNS)
    row = "2030-01-01," + ",".join(["5"] * 8) + ",5,100,100"
    path.write_text(header + "\n" + row + "\n")
    result = sw.validate_file(path, datetime(2030, 1, 1), datetime(2030, 1, 10))
    assert not result.ok
    assert not result.covers_range


def test_validate_file_covers_range_ignores_time_of_day(tmp_path):
    """Regression test for an audit finding: covers_range used to compare
    a date-only (midnight) timestamp parsed from the CSV's last row
    against a full end_utc datetime, so a file whose last row IS the
    scenario's own end date was wrongly rejected whenever end_utc carried
    a non-zero time-of-day (daily-resolution data covers its whole day,
    not just its midnight instant). service.py builds end_utc as
    datetime.fromisoformat(scenario.epoch_utc) + a timedelta, and
    Scenario.validate() does not require epoch_utc to be midnight, so this
    is a real, reachable scenario shape.
    """
    path = tmp_path / "covers.csv"
    header = ",".join(sw.REQUIRED_COLUMNS)
    row_tail = "," + ",".join(["5"] * 8) + ",5,100,100"
    path.write_text(header + "\n" + "2030-01-01" + row_tail + "\n" + "2030-01-05" + row_tail + "\n")

    start_utc = datetime(2030, 1, 1, 14, 0, 0)
    end_utc = datetime(2030, 1, 5, 14, 0, 0)  # same calendar date as the file's last row, but later in the day
    result = sw.validate_file(path, start_utc, end_utc)

    assert result.covers_range, result.message


def test_validate_file_detects_unsorted_dates(tmp_path):
    path = tmp_path / "unsorted.csv"
    header = ",".join(sw.REQUIRED_COLUMNS)
    row_tail = "," + ",".join(["5"] * 8) + ",5,100,100"
    path.write_text(header + "\n" + "2030-01-05" + row_tail + "\n" + "2030-01-01" + row_tail + "\n")
    result = sw.validate_file(path, datetime(2030, 1, 1), datetime(2030, 1, 5))
    assert not result.ok
    assert result.unsorted


def test_validate_file_detects_duplicate_dates(tmp_path):
    path = tmp_path / "dupe.csv"
    header = ",".join(sw.REQUIRED_COLUMNS)
    row_tail = "," + ",".join(["5"] * 8) + ",5,100,100"
    path.write_text(header + "\n" + "2030-01-01" + row_tail + "\n" + "2030-01-01" + row_tail + "\n")
    result = sw.validate_file(path, datetime(2030, 1, 1), datetime(2030, 1, 1))
    assert not result.ok
    assert result.duplicate_dates == ["2030-01-01"]


def test_resolve_synthetic_source_returns_flagged_synthetic(tmp_path):
    resolved = sw.resolve("synthetic", datetime(2030, 1, 1), datetime(2030, 1, 5), cache_dir=tmp_path)
    assert resolved.is_synthetic
    assert any("SYNTHETIC" in w for w in resolved.warnings)


def test_resolve_local_file_source_uses_exact_file(tmp_path):
    start, end = datetime(2030, 1, 1), datetime(2030, 1, 5)
    local_path = sw.generate_synthetic(start, end, tmp_path / "mine.csv")
    resolved = sw.resolve("local_file", start, end, local_file_path=str(local_path))
    assert resolved.path == local_path
    assert not resolved.is_synthetic


def test_resolve_local_file_source_raises_if_missing():
    with pytest.raises(sw.SpaceWeatherError, match="does not exist"):
        sw.resolve("local_file", datetime(2030, 1, 1), datetime(2030, 1, 5), local_file_path="/nonexistent.csv")


def test_resolve_local_file_source_raises_without_path():
    with pytest.raises(sw.SpaceWeatherError, match="local_file_path was not set"):
        sw.resolve("local_file", datetime(2030, 1, 1), datetime(2030, 1, 5))


def test_resolve_unknown_source_raises():
    with pytest.raises(sw.SpaceWeatherError, match="unknown space_weather.source"):
        sw.resolve("magic", datetime(2030, 1, 1), datetime(2030, 1, 5))


def test_resolve_celestrak_source_is_rejected_as_unknown():
    """"celestrak" used to be a real fetch-from-network source; the
    closed-off/offline policy removed it entirely (not just defaulted away
    from -- see spaceweather.py's own module docstring), so it must now be
    rejected the same as any other unknown source string, never silently
    treated as "local_file" or "synthetic".
    """
    with pytest.raises(sw.SpaceWeatherError, match="unknown space_weather.source"):
        sw.resolve("celestrak", datetime(2030, 1, 1), datetime(2030, 1, 5))


# -- Conservative ("worst-case") drag margin -------------------------------
# See this module's own docstring, "Conservative ('worst-case') drag
# margin", for the real user request this implements. generate_synthetic()
# stands in for "a real historical CSV" purely as test data here (its
# solar-cycle-shaped F10.7 and storm-episode Ap give a genuinely varied
# distribution to compute a percentile over) -- compute_worst_case_activity
# itself is source-agnostic file parsing + percentile math; the "must
# actually BE real data" policy is enforced one layer up, in resolve()'s
# own source handling, and tested separately below.

def _write_long_history(tmp_path, years: int = 15, seed: int = 3):
    start = datetime(2000, 1, 1)
    end = datetime(2000 + years, 1, 1)
    return sw.generate_synthetic(start, end, tmp_path / "history.csv", seed=seed), start, end


def test_compute_worst_case_activity_matches_numpy_percentile(tmp_path):
    import numpy as np

    path, _start, _end = _write_long_history(tmp_path)
    f107_all, ap_all = sw._load_historical_activity(path)

    f107_p, ap_p, n_samples = sw.compute_worst_case_activity(path, 95.0)

    assert n_samples == len(f107_all) == len(ap_all)
    assert f107_p == pytest.approx(np.percentile(f107_all, 95.0))
    assert ap_p == pytest.approx(np.percentile(ap_all, 95.0))


def test_compute_worst_case_activity_rejects_short_history(tmp_path):
    start, end = datetime(2030, 1, 1), datetime(2030, 6, 1)  # well under a year
    path = sw.generate_synthetic(start, end, tmp_path / "short.csv")
    with pytest.raises(sw.SpaceWeatherError, match="need at least"):
        sw.compute_worst_case_activity(path, 95.0)


def test_generate_worst_case_holds_values_constant_and_validates(tmp_path):
    start, end = datetime(2030, 1, 1), datetime(2030, 1, 10)
    path = sw.generate_worst_case(230.5, 45.0, start, end, tmp_path / "worst.csv")

    result = sw.validate_file(path, start, end)
    assert result.ok, result.message

    import csv as _csv
    with open(path, newline="") as f:
        rows = list(_csv.DictReader(f))
    assert rows  # non-empty
    for row in rows:
        assert float(row["F10.7_OBS"]) == pytest.approx(230.5)
        assert float(row["F10.7_OBS_CENTER81"]) == pytest.approx(230.5)
        assert float(row["AP_AVG"]) == pytest.approx(45.0)
        for i in range(1, 9):
            assert float(row[f"AP{i}"]) == pytest.approx(45.0)


def test_resolve_conservative_local_file_computes_real_percentile(tmp_path):
    import numpy as np

    history_path, _hist_start, _hist_end = _write_long_history(tmp_path)
    f107_all, ap_all = sw._load_historical_activity(history_path)
    expected_f107 = np.percentile(f107_all, 95.0)
    expected_ap = np.percentile(ap_all, 95.0)

    scenario_start, scenario_end = datetime(2030, 1, 1), datetime(2030, 1, 5)
    resolved = sw.resolve("local_file", scenario_start, scenario_end, local_file_path=str(history_path),
                           cache_dir=tmp_path / "cache", activity_level="conservative", activity_percentile=95.0)

    assert resolved.is_synthetic  # not real per-day data for THESE dates -- see resolve()'s own docstring
    assert any("CONSERVATIVE" in w for w in resolved.warnings)
    result = sw.validate_file(resolved.path, scenario_start, scenario_end)
    assert result.ok, result.message

    import csv as _csv
    with open(resolved.path, newline="") as f:
        first_row = next(_csv.DictReader(f))
    # abs=0.05: generate_worst_case's CSV rounds to 1 decimal place, so the
    # round-tripped value can differ from the unrounded percentile by up to
    # half of that -- real float formatting, not slack for a bug.
    assert float(first_row["F10.7_OBS"]) == pytest.approx(expected_f107, abs=0.05)
    assert float(first_row["AP_AVG"]) == pytest.approx(expected_ap, abs=0.05)


def test_resolve_conservative_synthetic_source_raises():
    with pytest.raises(sw.SpaceWeatherError, match="needs REAL historical"):
        sw.resolve("synthetic", datetime(2030, 1, 1), datetime(2030, 1, 5), activity_level="conservative")


def test_resolve_conservative_local_file_without_path_raises():
    with pytest.raises(sw.SpaceWeatherError, match="local_file_path was not set"):
        sw.resolve("local_file", datetime(2030, 1, 1), datetime(2030, 1, 5), activity_level="conservative")


def test_resolve_unknown_activity_level_raises():
    with pytest.raises(sw.SpaceWeatherError, match="unknown space_weather.activity_level"):
        sw.resolve("synthetic", datetime(2030, 1, 1), datetime(2030, 1, 5), activity_level="extreme")


def test_resolve_never_calls_fetch(tmp_path, monkeypatch):
    """resolve() itself must NEVER touch the network, regardless of
    source/activity_level -- fetch() is only ever reached explicitly, via
    gui.startup_fetch_dialog's consent-gated prompt. Fails loudly (instead
    of quietly passing) if resolve() is ever wired to call it.
    """
    def _unexpected_fetch(*args, **kwargs):
        raise AssertionError("resolve() must never call fetch() itself")

    monkeypatch.setattr(sw, "fetch", _unexpected_fetch)
    start, end = datetime(2030, 1, 1), datetime(2030, 1, 5)
    local_path = sw.generate_synthetic(start, end, tmp_path / "local.csv")

    sw.resolve("synthetic", start, end)
    sw.resolve("local_file", start, end, local_file_path=str(local_path))


class _FakeFetchResponse:
    """Minimal stand-in for ``urllib.request.urlopen``'s return value."""

    def __init__(self, data: bytes):
        self._data = data

    def read(self, n: int = -1) -> bytes:
        return self._data if n < 0 else self._data[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_fetch_downloads_and_caches(tmp_path, monkeypatch):
    fake_csv = b"DATE,AP1,AP2,AP3,AP4,AP5,AP6,AP7,AP8,AP_AVG,F10.7_OBS,F10.7_OBS_CENTER81\n"
    monkeypatch.setattr(sw.urllib.request, "urlopen", lambda *a, **k: _FakeFetchResponse(fake_csv))

    path = sw.fetch(dataset="SW-All", cache_dir=tmp_path)

    assert path == tmp_path / "SW-All.csv"
    assert path.read_bytes() == fake_csv


def test_fetch_is_a_cache_hit_without_force(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sw.urllib.request, "urlopen",
                         lambda *a, **k: calls.append(1) or _FakeFetchResponse(b"x"))

    dest = tmp_path / "SW-All.csv"
    dest.write_bytes(b"already here")

    path = sw.fetch(dataset="SW-All", cache_dir=tmp_path)

    assert path == dest
    assert path.read_bytes() == b"already here"
    assert calls == []  # no network touched -- cache hit


def test_fetch_force_redownloads_even_if_cached(tmp_path, monkeypatch):
    fake_csv = b"DATE,AP1,AP2,AP3,AP4,AP5,AP6,AP7,AP8,AP_AVG,F10.7_OBS,F10.7_OBS_CENTER81\nfresh\n"
    monkeypatch.setattr(sw.urllib.request, "urlopen", lambda *a, **k: _FakeFetchResponse(fake_csv))

    dest = tmp_path / "SW-All.csv"
    dest.write_bytes(b"stale")

    path = sw.fetch(dataset="SW-All", cache_dir=tmp_path, force=True)

    assert path.read_bytes() == fake_csv


def test_fetch_rejects_unknown_dataset():
    with pytest.raises(sw.SpaceWeatherError, match="unknown CelesTrak dataset"):
        sw.fetch(dataset="not-a-real-dataset")


def test_fetch_reports_network_failure(tmp_path, monkeypatch):
    def _raise(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(sw.urllib.request, "urlopen", _raise)

    with pytest.raises(sw.SpaceWeatherError, match="could not fetch"):
        sw.fetch(dataset="SW-All", cache_dir=tmp_path)


def test_fetch_reports_a_disk_write_failure(tmp_path, monkeypatch):
    """A full/read-only disk failing the write step, AFTER a successful
    download, must be reported as a SpaceWeatherError too -- not a raw
    OSError the caller (gui.startup_fetch_dialog's worker, in practice)
    would need its own special handling for.
    """
    monkeypatch.setattr(sw.urllib.request, "urlopen", lambda *a, **k: _FakeFetchResponse(b"data"))

    from pathlib import Path as _Path

    def _raise_write(self, data):
        raise OSError("disk full")

    monkeypatch.setattr(_Path, "write_bytes", _raise_write)

    with pytest.raises(sw.SpaceWeatherError, match="could not write"):
        sw.fetch(dataset="SW-All", cache_dir=tmp_path)


def test_fetch_reports_a_cache_dir_creation_failure(tmp_path, monkeypatch):
    from pathlib import Path as _Path

    def _raise_mkdir(self, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(_Path, "mkdir", _raise_mkdir)

    with pytest.raises(sw.SpaceWeatherError, match="could not create cache directory"):
        sw.fetch(dataset="SW-All", cache_dir=tmp_path / "nested")


def test_cached_fetch_path_is_none_when_nothing_fetched(tmp_path):
    assert sw.cached_fetch_path(cache_dir=tmp_path) is None


def test_cached_fetch_path_finds_a_real_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(sw.urllib.request, "urlopen", lambda *a, **k: _FakeFetchResponse(b"data"))
    fetched = sw.fetch(dataset="SW-All", cache_dir=tmp_path)

    assert sw.cached_fetch_path(cache_dir=tmp_path) == fetched


def test_synthetic_cycle_follows_the_calendar():
    """Cycle 25: minimum Dec 2019, maximum ~Oct 2024, next minimum ~Dec
    2030. The profile used to start every run 2 years before a maximum,
    so a 2030 mission saw near-maximum drag."""
    from datetime import datetime

    from spacemissionstudio.engine.spaceweather import _F107_SOLAR_MAX, _F107_SOLAR_MIN, _f107_base

    def level(year, month):
        return float(_f107_base([datetime(year, month, 1)])[0])  # [sfu]

    assert level(2019, 12) == pytest.approx(_F107_SOLAR_MIN, abs=0.5)
    assert level(2024, 10) == pytest.approx(_F107_SOLAR_MAX, abs=0.5)
    assert level(2030, 1) < 80.0  # the quiet end of cycle 25
    assert level(2030, 12) == pytest.approx(_F107_SOLAR_MIN, abs=1.0)
    assert level(2035, 9) > 145.0  # cycle 26's maximum


def test_synthetic_cache_name_carries_the_profile_version(tmp_path):
    """Files generated by an older profile must not be picked up again."""
    from datetime import datetime

    from spacemissionstudio.engine.spaceweather import _SYNTHETIC_VERSION, _synthetic_cache_path

    path = _synthetic_cache_path(tmp_path, datetime(2030, 1, 1), datetime(2030, 2, 1))
    assert path.name == f"synthetic_v{_SYNTHETIC_VERSION}_20300101_20300201.csv"
