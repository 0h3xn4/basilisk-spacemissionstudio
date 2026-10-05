"""Tests for spacemissionstudio.schema.migrations -- no Basilisk import,
runs anywhere. The v1->v2 migration exists because removing "celestrak"
as a valid SpaceWeatherConfig.source (see engine.spaceweather's own
"Closed-off/offline policy" docstring) would otherwise strand every
scenario file saved before that change: "celestrak" was the v1 DEFAULT,
so essentially all of them have it, and load_scenario() would start
raising ScenarioValidationError for files that used to load fine.
"""

import json

import pytest

from spacemissionstudio.schema import CURRENT_SCHEMA_VERSION, ScenarioValidationError, load_scenario
from spacemissionstudio.schema.migrations import migrate


def _v1_scenario(space_weather: dict | None = None) -> dict:
    data = {
        "schema_version": 1,
        "name": "v1 scenario",
        "epoch_utc": "2030-01-01T00:00:00",
        "spacecraft": [
            {
                "name": "sat-1",
                "orbit": {
                    "type": "classical_elements", "semi_major_axis_km": 7000.0, "eccentricity": 0.001,
                    "inclination_deg": 51.6, "raan_deg": 0.0, "arg_periapsis_deg": 0.0, "true_anomaly_deg": 0.0,
                },
            }
        ],
    }
    if space_weather is not None:
        data["space_weather"] = space_weather
    return data


def test_migrate_bumps_schema_version_to_current():
    data = migrate(_v1_scenario())
    assert data["schema_version"] == CURRENT_SCHEMA_VERSION


def test_migrate_rewrites_celestrak_source_to_synthetic():
    data = migrate(_v1_scenario({"source": "celestrak"}))
    assert data["space_weather"]["source"] == "synthetic"


def test_migrate_downgrades_conservative_celestrak_to_nominal_synthetic():
    data = migrate(_v1_scenario({"source": "celestrak", "activity_level": "conservative",
                                  "activity_percentile": 95.0}))
    assert data["space_weather"]["source"] == "synthetic"
    assert data["space_weather"]["activity_level"] == "nominal"


def test_migrate_leaves_local_file_source_untouched():
    data = migrate(_v1_scenario({"source": "local_file", "local_file_path": "/some/file.csv"}))
    assert data["space_weather"]["source"] == "local_file"
    assert data["space_weather"]["local_file_path"] == "/some/file.csv"


def test_migrate_leaves_conservative_local_file_untouched():
    data = migrate(_v1_scenario({"source": "local_file", "local_file_path": "/some/file.csv",
                                  "activity_level": "conservative", "activity_percentile": 97.7}))
    assert data["space_weather"]["source"] == "local_file"
    assert data["space_weather"]["activity_level"] == "conservative"


def test_migrate_handles_a_file_with_no_space_weather_block_at_all():
    """space_weather is optional (defaults via dataclass field) -- a v1
    file that never set it explicitly must migrate cleanly, not crash on
    a missing key.
    """
    data = migrate(_v1_scenario())
    assert "space_weather" not in data or data["space_weather"] is None
    assert data["schema_version"] == CURRENT_SCHEMA_VERSION


def test_load_scenario_migrates_an_old_celestrak_file_end_to_end(tmp_path):
    """The real regression this migration exists to prevent: a v1 file
    with the old default source must still load_scenario()+validate()
    successfully, not raise ScenarioValidationError.
    """
    path = tmp_path / "old.json"
    path.write_text(json.dumps(_v1_scenario({"source": "celestrak"})))

    scenario = load_scenario(path)

    assert scenario.space_weather.source == "synthetic"
    assert scenario.schema_version == CURRENT_SCHEMA_VERSION


def test_load_scenario_migrates_an_old_conservative_celestrak_file_end_to_end(tmp_path):
    path = tmp_path / "old_conservative.json"
    path.write_text(json.dumps(_v1_scenario({
        "source": "celestrak", "activity_level": "conservative", "activity_percentile": 95.0,
    })))

    scenario = load_scenario(path)

    assert scenario.space_weather.source == "synthetic"
    assert scenario.space_weather.activity_level == "nominal"


def test_migrate_rejects_a_version_with_no_registered_step(monkeypatch):
    import spacemissionstudio.schema.migrations as migrations_module

    monkeypatch.setattr(migrations_module, "MIGRATIONS", {})
    with pytest.raises(ScenarioValidationError, match="no migration registered"):
        migrate(_v1_scenario())
