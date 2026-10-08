"""Tests for spacemissionstudio.engine.spaceweather -- no Basilisk import, runs
anywhere. Real data only: "bundled" (CelesTrak's SW-All shipped with the app)
and "local_file" are the sources; the fixtures below are excerpts of that
real record. resolve() makes no network calls; fetch() (only reached via
gui.startup_fetch_dialog's consent-gated prompt) is tested with
urllib.request.urlopen mocked.
"""

import csv
from datetime import date, datetime

import numpy as np
import pytest

from spacemissionstudio.engine import spaceweather as sw

_KIND_TO_TYPE = {"observed": "OBS", "daily_forecast": "PRD", "monthly_forecast": "PRM"}
_SHIPPED = sw.BUNDLED_DATA_PATH  # kept: some tests point BUNDLED_DATA_PATH elsewhere


def _real_excerpt_csv(path, first, last):
    """Days ``first``..``last`` of the shipped CelesTrak record, written in
    CelesTrak's own CSV layout (monthly-forecast rows once per month,
    with no Ap, as CelesTrak publishes them)."""
    data = sw.load_celestrak(_SHIPPED)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["DATE"] + [f"AP{k}" for k in range(1, 9)]
                        + ["AP_AVG", "F10.7_OBS", "F10.7_DATA_TYPE", "F10.7_OBS_CENTER81"])
        for day in sorted(d for d in data.days if first <= d <= last):
            rec = data.days[day]
            if rec.kind == "monthly_forecast":
                if day.day == 1:
                    writer.writerow([day.isoformat()] + [""] * 9 + [rec.f107_obs, "PRM", rec.f107_center81])
                continue
            writer.writerow([day.isoformat()] + list(rec.ap)
                            + [rec.ap_avg, rec.f107_obs, _KIND_TO_TYPE[rec.kind], rec.f107_center81])
    return path


def test_the_shipped_record_parses_as_published():
    """Spot checks against the raw lines of data/spaceweather/SW-All.txt."""
    data = sw.load_celestrak(sw.BUNDLED_DATA_PATH)
    assert data.updated == "2025 Jul 21 10:37:15 UTC"
    assert (data.first_date, data.last_date) == (date(1957, 10, 1), date(2041, 10, 31))
    first = data.days[date(1957, 10, 1)]
    assert first.ap == (32, 27, 15, 7, 22, 9, 32, 22) and first.ap_avg == 21
    assert (first.f107_obs, first.f107_center81) == (269.3, 266.6)
    assert data.days[date(2025, 7, 20)].kind == "observed"
    assert data.days[date(2025, 7, 21)].kind == "daily_forecast"
    month = data.days[date(2030, 1, 17)]
    assert month.kind == "monthly_forecast" and month.f107_obs == 77.8  # [sfu] NOAA's January 2030 value
    assert month.ap_avg == pytest.approx(data.long_term_ap)
    observed = [r.ap_avg for r in data.days.values() if r.kind == "observed"]
    assert data.long_term_ap == pytest.approx(np.mean(observed)) == pytest.approx(12.83, abs=0.01)


def test_a_past_run_gets_the_observed_days_unchanged(tmp_path):
    """The 2003 Halloween storms, as observed."""
    resolved = sw.resolve("bundled", datetime(2003, 10, 28), datetime(2003, 11, 2), cache_dir=tmp_path)
    assert resolved.data_file == sw.BUNDLED_DATA_PATH and resolved.warnings == []
    rows = {row["DATE"]: row for row in csv.DictReader(open(resolved.path))}
    record = sw.load_celestrak(sw.BUNDLED_DATA_PATH).days[date(2003, 10, 29)]
    assert float(rows["2003-10-29"]["AP_AVG"]) == record.ap_avg > 150.0
    assert float(rows["2003-10-29"]["F10.7_OBS"]) == record.f107_obs
    assert sw.validate_file(resolved.path, datetime(2003, 10, 28), datetime(2003, 11, 2)).ok


def test_a_future_run_uses_msfcs_prediction_at_the_chosen_percentile(tmp_path):
    """January 2030 from MSFC's October 2026 table: 74.2 sfu / Ap 11.5 at
    the 50th percentile, 78.7 / 16.2 at the 95th (AD10: operations)."""
    for percentile, f107, ap in ((50.0, 74.2, 11.5), (95.0, 78.7, 16.2)):  # [%], [sfu], [-]
        resolved = sw.resolve("bundled", datetime(2030, 1, 1), datetime(2030, 2, 1), cache_dir=tmp_path,
                              forecast_percentile=percentile)
        assert resolved.warnings == [f"space weather uses MSFC's prediction (oct2026f10-prd.txt), "
                                     f"{percentile:g}th percentile F10.7 and Ap"]
        row = next(r for r in csv.DictReader(open(resolved.path)) if r["DATE"] == "2030-01-15")
        assert (float(row["F10.7_OBS"]), float(row["F10.7_OBS_CENTER81"]), float(row["AP_AVG"])) == (f107, f107, ap)
        assert all(float(row[f"AP{k}"]) == ap for k in range(1, 9))


def test_noaa_fills_only_the_months_before_msfc_starts(tmp_path):
    """The shipped CelesTrak file ends its 45-day forecast in August 2025;
    MSFC's table starts in April 2026. In between, NOAA's monthly F10.7
    (with the observed-mean Ap) is all the real data there is."""
    resolved = sw.resolve("bundled", datetime(2025, 11, 1), datetime(2026, 5, 1), cache_dir=tmp_path)
    assert any("NOAA's monthly F10.7 forecast" in w and "where MSFC's prediction does not reach" in w
               for w in resolved.warnings)
    rows = {r["DATE"]: r for r in csv.DictReader(open(resolved.path))}
    assert float(rows["2026-01-15"]["F10.7_OBS"]) == sw.load_celestrak(_SHIPPED).days[date(2026, 1, 15)].f107_obs
    assert float(rows["2026-04-15"]["F10.7_OBS"]) == 133.9  # [sfu] MSFC, April 2026, 50th


def test_msfc_parses_as_published_and_repeats_its_last_132_months():
    """AD10 Sec. 5.9: past the prediction's end, its last 132 months repeat."""
    msfc = sw.load_msfc(sw.MSFC_BUNDLED_PATH)
    assert (msfc.first_month, msfc.last_month, len(msfc.months)) == (date(2026, 4, 1), date(2041, 10, 1), 187)
    assert msfc.months[date(2026, 4, 1)] == ((137.7, 133.9, 131.3), (13.9, 13.1, 12.1))
    assert msfc.values(date(2041, 10, 1), 50.0) == (70.0, 8.9, False)
    assert msfc.values(date(2041, 11, 1), 50.0) == (*msfc.values(date(2030, 11, 1), 50.0)[:2], True)
    assert msfc.values(date(2052, 10, 1), 95.0) == (*msfc.values(date(2041, 10, 1), 95.0)[:2], True)
    assert msfc.values(date(2026, 3, 1), 50.0) is None


def test_runs_past_2041_continue_on_the_repeated_cycle(tmp_path):
    resolved = sw.resolve("bundled", datetime(2041, 6, 1), datetime(2045, 1, 1), cache_dir=tmp_path)
    assert "past 2041-10 MSFC's last 132 months repeat (ESA AD10 Sec. 5.9)" in resolved.warnings
    assert sw.data_coverage("bundled") == (date(1957, 10, 1), None)


def test_a_run_before_the_record_is_refused_with_the_range(tmp_path):
    with pytest.raises(sw.SpaceWeatherError, match=r"covers 1957-10-01; this run needs"):
        sw.resolve("bundled", datetime(1957, 9, 1), datetime(1957, 11, 1), cache_dir=tmp_path)


def test_an_unknown_forecast_percentile_is_refused():
    with pytest.raises(sw.SpaceWeatherError, match="forecast_percentile"):
        sw.resolve("bundled", datetime(2030, 1, 1), datetime(2030, 1, 5), forecast_percentile=90.0)


def test_a_short_table_is_not_taken_for_an_msfc_prediction(tmp_path):
    path = tmp_path / "short.txt"
    path.write_text("".join(sw.MSFC_BUNDLED_PATH.read_text().splitlines(keepends=True)[:40]))
    with pytest.raises(sw.SpaceWeatherError, match="needs at least 132"):
        sw.load_msfc(path)


def test_a_celestrak_csv_with_forecast_rows_reads_like_the_text_file(tmp_path):
    """CelesTrak's CSV layout (OBS/PRD/PRM rows, monthly rows without Ap)
    gives the same days as its text file."""
    path = _real_excerpt_csv(tmp_path / "SW-excerpt.csv", date(2025, 6, 1), date(2025, 12, 31))
    from_csv = sw.load_celestrak(path)
    shipped = sw.load_celestrak(sw.BUNDLED_DATA_PATH)
    for day in (date(2025, 6, 10), date(2025, 7, 25), date(2025, 11, 20)):
        assert from_csv.days[day].kind == shipped.days[day].kind
        assert from_csv.days[day].f107_obs == shipped.days[day].f107_obs
    # the excerpt's own observed days set its long-term Ap
    assert from_csv.days[date(2025, 11, 20)].ap_avg == pytest.approx(from_csv.long_term_ap)


def test_the_newer_of_the_shipped_and_downloaded_files_is_used(tmp_path, monkeypatch):
    """A startup download observed further than the shipped file wins."""
    older = _real_excerpt_csv(tmp_path / "old.csv", date(2023, 1, 1), date(2024, 12, 31))
    monkeypatch.setattr(sw, "BUNDLED_DATA_PATH", older)
    cache = tmp_path / "cache"
    cache.mkdir()
    newer = _real_excerpt_csv(cache / "SW-All.csv", date(2024, 1, 1), date(2025, 7, 20))
    assert sw.real_data_path("bundled", cache_dir=cache) == newer
    monkeypatch.setattr(sw, "BUNDLED_DATA_PATH", newer)
    _real_excerpt_csv(cache / "SW-All.csv", date(2023, 1, 1), date(2024, 6, 30))
    assert sw.real_data_path("bundled", cache_dir=cache) == newer


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


def test_resolve_local_file_source_reads_that_file(tmp_path):
    local_path = _real_excerpt_csv(tmp_path / "mine.csv", date(2024, 1, 1), date(2024, 3, 1))
    resolved = sw.resolve("local_file", datetime(2024, 1, 20), datetime(2024, 2, 1),
                          local_file_path=str(local_path), cache_dir=tmp_path / "cache")
    assert resolved.data_file == local_path
    assert sw.validate_file(resolved.path, datetime(2024, 1, 20), datetime(2024, 2, 1)).ok


def test_resolve_local_file_source_raises_if_missing():
    with pytest.raises(sw.SpaceWeatherError, match="does not exist"):
        sw.resolve("local_file", datetime(2030, 1, 1), datetime(2030, 1, 5), local_file_path="/nonexistent.csv")


def test_resolve_local_file_source_raises_without_path():
    with pytest.raises(sw.SpaceWeatherError, match="local_file_path was not set"):
        sw.resolve("local_file", datetime(2030, 1, 1), datetime(2030, 1, 5))


def test_resolve_unknown_source_raises():
    with pytest.raises(sw.SpaceWeatherError, match="unknown space_weather.source"):
        sw.resolve("magic", datetime(2030, 1, 1), datetime(2030, 1, 5))


@pytest.mark.parametrize("source", ["celestrak", "synthetic"])
def test_removed_sources_are_rejected_as_unknown(source):
    """"celestrak" (a runtime network fetch) and "synthetic" (a generated
    profile) were both removed; neither is quietly read as another source."""
    with pytest.raises(sw.SpaceWeatherError, match="unknown space_weather.source"):
        sw.resolve(source, datetime(2030, 1, 1), datetime(2030, 1, 5))


# -- Conservative = MSFC's 95th percentile (ESA AD10 Sec. 5.9) -------------

def test_the_conservative_case_is_msfcs_predicted_cycle_at_the_95th_percentile(tmp_path):
    """Conservative is no constant: the same predicted solar cycle as
    nominal, at MSFC's 95th percentile, so higher every month and still
    rising and falling with the cycle (2030 to 2034 here)."""
    start, end = datetime(2030, 1, 1), datetime(2034, 12, 31)
    rows = {}
    for percentile in (50.0, 95.0):
        resolved = sw.resolve("bundled", start, end, cache_dir=tmp_path, forecast_percentile=percentile)
        rows[percentile] = {r["DATE"]: float(r["F10.7_OBS"]) for r in csv.DictReader(open(resolved.path))}
        assert any(f"{percentile:g}th percentile" in w for w in resolved.warnings)
    months = [f"{year}-{month:02d}-15" for year in range(2030, 2035) for month in (1, 7)]
    assert all(rows[95.0][m] > rows[50.0][m] for m in months)
    assert max(rows[95.0][m] for m in months) - min(rows[95.0][m] for m in months) > 30.0  # [sfu] a cycle, not flat


def test_resolve_has_no_activity_level_any_more():
    """Schema v3's historical-percentile "conservative" mode is gone (schema
    v4: conservative is forecast_percentile 95)."""
    with pytest.raises(TypeError):
        sw.resolve("bundled", datetime(2030, 1, 1), datetime(2030, 1, 5), activity_level="conservative")


def test_resolve_never_calls_fetch(tmp_path, monkeypatch):
    """resolve() itself must NEVER touch the network, regardless of
    source -- fetch() is only ever reached explicitly, via
    gui.startup_fetch_dialog's consent-gated prompt. Fails loudly (instead
    of quietly passing) if resolve() is ever wired to call it.
    """
    def _unexpected_fetch(*args, **kwargs):
        raise AssertionError("resolve() must never call fetch() itself")

    monkeypatch.setattr(sw, "fetch", _unexpected_fetch)
    local_path = _real_excerpt_csv(tmp_path / "local.csv", date(2024, 1, 1), date(2024, 3, 1))
    sw.resolve("bundled", datetime(2030, 1, 1), datetime(2030, 1, 5), cache_dir=tmp_path)
    sw.resolve("local_file", datetime(2024, 1, 20), datetime(2024, 2, 1), local_file_path=str(local_path),
               cache_dir=tmp_path)


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
