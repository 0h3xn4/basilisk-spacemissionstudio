"""Tests for gui.autosave -- the Qt-free half of design-philosophy
roadmap item M4 (crash-recovery autosave). No QApplication needed:
this module is plain functions operating on a Scenario/dict and a
filesystem path (see its own module docstring). Every test
monkeypatches ``autosave._AUTOSAVE_DIR``/``_RECOVERY_FILE`` to a
``tmp_path`` location -- this module must never touch a real user's
home directory from an automated test run.
"""

import pytest

from spacemissionstudio.gui import autosave
from spacemissionstudio.schema.scenario import OrbitIC, Scenario, SpacecraftConfig


@pytest.fixture(autouse=True)
def _isolated_recovery_file(tmp_path, monkeypatch):
    recovery_dir = tmp_path / "autosave"
    monkeypatch.setattr(autosave, "_AUTOSAVE_DIR", recovery_dir)
    monkeypatch.setattr(autosave, "_RECOVERY_FILE", recovery_dir / "recovery.json")


def _sample_scenario() -> Scenario:
    scenario = Scenario(name="recoverable", epoch_utc="2030-01-01T00:00:00Z")
    scenario.spacecraft = [
        SpacecraftConfig(name="sat-1", orbit=OrbitIC(type="cartesian", position_km=[7000, 0, 0],
                                                      velocity_km_s=[0, 7.5, 0]))
    ]
    scenario.validate()
    return scenario


def test_read_with_no_recovery_file_returns_none():
    assert autosave.read_recovery_file() is None


def test_write_then_read_round_trips_scenario_and_original_path(tmp_path):
    scenario = _sample_scenario()
    original_path = tmp_path / "mission.json"

    autosave.write_recovery_file(scenario, original_path)
    info = autosave.read_recovery_file()

    assert info is not None
    assert info.scenario.to_dict() == scenario.to_dict()
    assert info.original_path == original_path
    assert info.saved_at_utc  # non-empty, real timestamp string


def test_write_with_no_original_path_round_trips_to_none():
    autosave.write_recovery_file(_sample_scenario(), None)
    info = autosave.read_recovery_file()
    assert info is not None
    assert info.original_path is None


def test_clear_removes_the_file(tmp_path):
    autosave.write_recovery_file(_sample_scenario(), tmp_path / "mission.json")
    assert autosave._RECOVERY_FILE.exists()

    autosave.clear_recovery_file()

    assert not autosave._RECOVERY_FILE.exists()
    assert autosave.read_recovery_file() is None


def test_clear_with_no_file_present_is_a_no_op():
    autosave.clear_recovery_file()  # must not raise


def test_read_corrupt_json_returns_none_not_raise():
    autosave._AUTOSAVE_DIR.mkdir(parents=True, exist_ok=True)
    autosave._RECOVERY_FILE.write_text("{not valid json")
    assert autosave.read_recovery_file() is None


def test_read_malformed_envelope_missing_scenario_key_returns_none():
    import json

    autosave._AUTOSAVE_DIR.mkdir(parents=True, exist_ok=True)
    autosave._RECOVERY_FILE.write_text(json.dumps({"original_path": None, "saved_at_utc": "now"}))
    assert autosave.read_recovery_file() is None


def test_read_non_dict_envelope_returns_none():
    autosave._AUTOSAVE_DIR.mkdir(parents=True, exist_ok=True)
    autosave._RECOVERY_FILE.write_text("[1, 2, 3]")
    assert autosave.read_recovery_file() is None


def test_read_invalid_scenario_dict_returns_none():
    """A recovery file whose embedded scenario fails validate() (e.g.
    hand-edited, or from a version whose own invariants changed) must
    not be offered for restore -- it would just fail again on
    Scenario.validate() inside the GUI's own restore path.
    """
    import json

    scenario_dict = _sample_scenario().to_dict()
    scenario_dict["spacecraft"][0]["dry_mass_kg"] = -5.0  # invalid: must be > 0
    autosave._AUTOSAVE_DIR.mkdir(parents=True, exist_ok=True)
    autosave._RECOVERY_FILE.write_text(json.dumps(
        {"original_path": None, "saved_at_utc": "now", "scenario": scenario_dict}
    ))
    assert autosave.read_recovery_file() is None


def test_write_failure_is_swallowed_not_raised(monkeypatch):
    """Best-effort per the module's own docstring -- a write failure
    (full disk, permissions) must never propagate out and interrupt
    whatever triggered the autosave tick.
    """
    from pathlib import Path

    def _raise(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", _raise)
    autosave.write_recovery_file(_sample_scenario(), None)  # must not raise


def test_clear_failure_is_swallowed_not_raised(tmp_path, monkeypatch):
    from pathlib import Path

    autosave.write_recovery_file(_sample_scenario(), None)

    def _raise(*args, **kwargs):
        raise PermissionError("nope")

    monkeypatch.setattr(Path, "unlink", _raise)
    autosave.clear_recovery_file()  # must not raise
