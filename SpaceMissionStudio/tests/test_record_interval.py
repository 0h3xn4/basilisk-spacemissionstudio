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

"""sim_settings.record_interval_s: thinner results, same physics."""

from pathlib import Path

import numpy as np
import pytest

from spacemissionstudio.engine.scenario_checks import scenario_warnings
from spacemissionstudio.schema import load_scenario
from spacemissionstudio.schema.scenario import Scenario, ScenarioValidationError, SimSettings

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"


def _template(prefix):
    return load_scenario(next(_TEMPLATES_DIR.glob(f"{prefix}_*.json")))


def test_interval_is_validated_and_round_trips():
    with pytest.raises(ScenarioValidationError, match="record_interval_s must be in"):
        SimSettings(record_interval_s=-1.0).validate()
    scenario = _template("18")
    scenario.sim_settings.record_interval_s = 600.0  # [s]
    assert Scenario.from_dict(scenario.to_dict()).sim_settings.record_interval_s == 600.0


def test_old_files_without_the_field_record_every_step():
    data = _template("18").to_dict()
    del data["sim_settings"]["record_interval_s"]
    assert Scenario.from_dict(data).sim_settings.record_interval_s == 0.0


def test_a_coarse_interval_warns_when_passes_are_short():
    scenario = _template("19")  # Berlin passes of ~4 and ~8 min
    scenario.sim_settings.record_interval_s = 600.0  # [s]
    assert scenario_warnings(scenario) == [
        "passes last as little as 5 min but results are recorded every 10 min -- some may show coarsely or "
        "not at all"]
    scenario.sim_settings.record_interval_s = 60.0  # [s]
    assert scenario_warnings(scenario) == []


@pytest.mark.requires_basilisk
def test_thinning_changes_the_data_not_the_physics():
    """Template 18 over 2 days, every 30 s step vs every 10 min: identical
    final state and propellant, 1/20 of the samples, every burn still
    flagged (burn flags record 'fired since the last sample')."""
    from spacemissionstudio.engine.service import SimulationService

    runs = {}
    for interval in (0.0, 600.0):  # [s]
        scenario = _template("18")
        scenario.sim_settings.duration_days = 2.0  # [day]
        scenario.sim_settings.record_interval_s = interval
        runs[interval] = SimulationService(scenario).run()
    full, thin = runs[0.0], runs[600.0]
    for name in ("leo-sat-1.position_N", "leo-sat-1.station_keeping.propellant_remaining"):
        assert np.allclose(full.series[name].data[-1], thin.series[name].data[-1], rtol=0.0, atol=1e-9)
        assert len(thin.series[name].time_s) == len(full.series[name].time_s) // 20 + 1
    assert thin.series["leo-sat-1.position_N"].time_s[-1] == full.series["leo-sat-1.position_N"].time_s[-1]

    def burn_starts(result):
        on = result.series["leo-sat-1.station_keeping.burn_on"].data[:, 0] > 0.5
        return np.count_nonzero(np.diff(on.astype(int)) == 1)

    assert burn_starts(thin) == burn_starts(full) > 0


@pytest.mark.requires_basilisk
def test_log_thinner_samples_on_the_interval():
    from spacemissionstudio.engine.orbit_maintenance import LogThinner

    thinner = LogThinner(600.0)  # [s]
    due = [t for t in np.arange(0.0, 3001.0, 30.0) if thinner.due(t)]  # [s]
    assert due == [0.0, 600.0, 1200.0, 1800.0, 2400.0, 3000.0]
    every_step = LogThinner(0.0)
    assert all(every_step.due(t) for t in (0.0, 30.0, 60.0))
