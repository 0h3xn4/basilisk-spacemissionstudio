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
"""Plausibility checks while editing (UX/UI guidelines): a perigee below
the surface, an inconsistent state, a run outside the installed data."""

from pathlib import Path

import pytest

from spacemissionstudio.engine import scenario_checks
from spacemissionstudio.schema import load_scenario
from spacemissionstudio.schema.scenario import OrbitIC

_TEMPLATES = Path(__file__).resolve().parents[2] / "spacemissionstudio" / "scenarios" / "templates"


def _template(prefix):
    return load_scenario(next(_TEMPLATES.glob(f"{prefix}_*.json")))


@pytest.mark.parametrize(("sma_km", "expected"), [
    (6300.0, "below Earth's surface"),  # [km] perigee 78 km below
    (6450.0, "re-enters"),  # [km] perigee at 72 km
    (6778.0, None),  # [km] 400 km, fine
])
def test_perigee_checks(sma_km, expected):
    """A perigee below the surface, or below 120 km, is flagged; 400 km is not."""
    scenario = _template("18")
    scenario.spacecraft[0].orbit.semi_major_axis_km = sma_km
    orbit_lines = [w for w in scenario_checks.plausibility_warnings(scenario) if w.startswith("leo-sat-1")]
    if expected is None:
        assert orbit_lines == []
    else:
        assert len(orbit_lines) == 1 and expected in orbit_lines[0]


def test_a_cartesian_state_inside_earth_or_escaping_is_flagged():
    """Position inside Earth; velocity of an escape trajectory (e.g. m/s typed as km/s)."""
    scenario = _template("18")
    sc = scenario.spacecraft[0]
    sc.orbit = OrbitIC(type="cartesian", position_km=[6000.0, 0.0, 0.0], velocity_km_s=[0.0, 7.7, 0.0])
    assert any("inside Earth" in w for w in scenario_checks.plausibility_warnings(scenario))
    sc.orbit = OrbitIC(type="cartesian", position_km=[6778.0, 0.0, 0.0], velocity_km_s=[0.0, 12.0, 0.0])
    assert any("escape trajectory" in w for w in scenario_checks.plausibility_warnings(scenario))


def test_a_drag_run_before_the_space_weather_data_is_flagged():
    """The bundled data start 1957-10-01; a 1950 drag run is refused at run time and flagged here."""
    scenario = _template("18")
    scenario.epoch_utc = "1950-01-01T00:00:00"
    assert any(w.startswith("space weather:") for w in scenario_checks.plausibility_warnings(scenario))


def test_no_earth_orientation_files_is_flagged_when_the_frame_matters(monkeypatch):
    """A gravity field or ground stations without IERS files fall back to IAU_EARTH."""
    from spacemissionstudio.engine import earth_orientation

    monkeypatch.setattr(earth_orientation, "installed", lambda directory=None: [])
    scenario = _template("18")  # degree-10 field
    assert any("no IERS files" in w for w in scenario_checks.plausibility_warnings(scenario))
    scenario.gravity.central_body_degree = 0
    assert not any("no IERS files" in w for w in scenario_checks.plausibility_warnings(scenario))


def test_the_editor_shows_the_warnings_while_editing(qtbot):
    """The scenario editor shows the checks under its validation line."""
    from spacemissionstudio.gui.scenario_editor import ScenarioEditorWidget

    editor = ScenarioEditorWidget()
    qtbot.addWidget(editor)
    scenario = _template("18")
    scenario.spacecraft[0].orbit.semi_major_axis_km = 6300.0  # [km]
    editor.from_scenario(scenario)
    editor.revalidate()
    assert "✓" in editor.validation_label.text()
    assert not editor.plausibility_label.isHidden()
    assert "below Earth's surface" in editor.plausibility_label.text()
