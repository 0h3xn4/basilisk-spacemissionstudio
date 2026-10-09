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

"""Every script in examples/ imports and runs, shortened where it allows,
and prints what its docstring promises."""

import importlib.util
import math
from pathlib import Path

import pytest

from spacemissionstudio.schema import load_scenario

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _example(name):
    spec = importlib.util.spec_from_file_location(f"examples_{name}", _EXAMPLES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_example_is_listed_in_the_examples_readme():
    """examples/README.md is where a newcomer finds them."""
    readme = (_EXAMPLES / "README.md").read_text(encoding="utf-8")
    scripts = sorted(p.name for p in _EXAMPLES.glob("*.py"))
    assert scripts
    for script in scripts:
        assert script in readme, script


def test_build_a_scenario_writes_a_valid_scenario_file(tmp_path, capsys):
    """No Basilisk: the scenario it saves loads, validates and is
    Sun-synchronous at the asked altitude."""
    path = _example("build_a_scenario").main([str(tmp_path / "mission.json"), "--altitude-km", "500",
                                              "--days", "0.5"])
    scenario = load_scenario(path)
    scenario.validate()
    orbit = scenario.spacecraft[0].orbit
    assert orbit.semi_major_axis_km == pytest.approx(6878.0)  # [km]
    assert orbit.inclination_deg == pytest.approx(97.4, abs=0.1)  # [deg] Sun-synchronous at 500 km
    assert scenario.sim_settings.duration_days == 0.5  # [day]
    assert "Sun-synchronous" in capsys.readouterr().out  # the Explain summary


def test_build_a_scenario_reports_an_invalid_setting_plainly(tmp_path, capsys):
    """A bad argument ends with the validation message, not a traceback."""
    with pytest.raises(SystemExit):
        _example("build_a_scenario").main([str(tmp_path / "bad.json"), "--days", "0"])
    assert "duration_days must be > 0" in capsys.readouterr().err
    assert not (tmp_path / "bad.json").exists()


@pytest.mark.requires_basilisk
def test_run_a_template_runs_template_22_and_exports_csv(tmp_path, capsys):
    """A short run of the starter template, its first Berlin pass and CSV export."""
    result = _example("run_a_template").main(["22", "--days", "0.02", "--csv", str(tmp_path)])
    assert "my-sat.position_N" in result.series
    assert (tmp_path / "my-sat.position_N.csv").is_file()
    assert "pass over berlin-gs" in capsys.readouterr().out  # the first pass starts ~10 min in


@pytest.mark.requires_basilisk
def test_hohmann_transfer_lands_on_the_target_circle():
    """The Mission Sequence's apoapsis stop comes half a transfer orbit in,
    and the second burn leaves a circle at the target altitude."""
    module = _example("hohmann_transfer")
    outcome = module.main(["--from-km", "550", "--to-km", "700"])
    r1_m, r2_m = 6928.0e3, 7078.0e3  # [m]
    _dv1, _dv2, coast_s = module.hohmann(r1_m, r2_m)
    assert outcome["coast_s"] == pytest.approx(coast_s, abs=20.0)  # [s] two 10 s steps
    radius_km = outcome["final_radius_km"]
    assert radius_km.min() > outcome["target_radius_km"] - 0.5  # [km]
    assert radius_km.max() < outcome["target_radius_km"] + 0.5  # [km]


@pytest.mark.requires_basilisk
def test_altitude_lifetime_sweep_finds_a_lower_orbit_comes_down_sooner():
    """400 km re-enters within the 5-year rule and well before 450 km."""
    lifetimes = _example("altitude_lifetime_sweep").main(["--altitudes", "400,450", "--max-years", "10"])
    assert lifetimes[400.0] is not None and 1.0 < lifetimes[400.0] < 5.0  # [year]
    assert lifetimes[450.0] is not None and lifetimes[450.0] > lifetimes[400.0]


@pytest.mark.requires_basilisk
def test_monte_carlo_spread_runs_a_batch_and_reads_it_back(tmp_path):
    """Two short runs of template 25: the archive reads back, the runs
    drew different drag coefficients, and they have spread apart."""
    module = _example("monte_carlo_spread")
    spread = module.main(["--runs", "2", "--days", "0.2", "--archive", str(tmp_path)])
    assert list(spread) == [0.2]
    assert spread[0.2] > 0.0 and math.isfinite(spread[0.2])  # [km]
    drag = {next(v for k, v in run.items() if k.endswith("dragCoeff")) for run in module.drawn_values(tmp_path)}
    assert len(drag) == 2
    assert module.main(["--read", str(tmp_path)]) == spread  # reading back gives the same numbers
