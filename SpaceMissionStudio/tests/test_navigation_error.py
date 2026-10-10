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

"""Navigation error (SRS-F-09: sensors modelled with noise where Basilisk
provides it): what simpleNav tells the flight software, as a bounded
random walk. The schema's refusals and round trip, the per-segment seeds
of long runs, and, with Basilisk, the errors staying within their bounds,
repeatable by seed, the plots keeping the true attitude, and the exported
flight software in the loop still reproducing the run exactly."""

import copy
import math
import subprocess
from pathlib import Path

import numpy as np
import pytest

from spacemissionstudio.schema import load_scenario
from spacemissionstudio.schema.scenario import NavigationErrorConfig, ScenarioValidationError

_TEMPLATES = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
_ERRORS = dict(attitude_step_deg=0.002, attitude_bound_deg=0.02, rate_step_deg_s=0.0005,  # [deg], [deg], [deg/s]
               rate_bound_deg_s=0.005, sun_step_deg=0.05, sun_bound_deg=1.0,  # [deg/s], [deg], [deg]
               position_step_m=1.0, position_bound_m=10.0, velocity_step_m_s=0.01,  # [m], [m], [m/s]
               velocity_bound_m_s=0.1)  # [m/s]


def _template(prefix, minutes, **errors):
    scenario = load_scenario(next(_TEMPLATES.glob(f"{prefix}_*.json")))
    scenario.sim_settings.duration_days = minutes / 1440.0  # [day]
    if errors:
        scenario.spacecraft[0].navigation_error = NavigationErrorConfig(**errors)
    scenario.validate()
    return scenario


@pytest.mark.parametrize("errors, reason", [
    ({"attitude_step_deg": -0.1, "attitude_bound_deg": 1.0}, "attitude step must be a number >= 0"),
    ({"rate_step_deg_s": 0.01}, "body rate needs a bound > 0"),
    ({"position_bound_m": math.inf}, "position bound must be a number >= 0"),
    ({"sun_step_deg": 0.1, "sun_bound_deg": 180.0}, "below 180 deg"),
    ({"seed": 2 ** 32}, "seed must be an integer"),
])
def test_the_schema_refuses_errors_basilisk_cannot_bound(errors, reason):
    """Negative or infinite values, a step without a bound (Basilisk would
    let it grow without limit), an angle bound of 180 deg or more and a
    seed outside 32 bits are refused, naming the channel."""
    with pytest.raises(ScenarioValidationError, match=reason):
        _template("07", 1, **errors)


def test_navigation_error_needs_attitude_flight_software_and_round_trips(tmp_path):
    """Only a spacecraft with a pointing mode or comms pointing has
    navigation to perturb; the block saves and loads unchanged."""
    scenario = _template("07", 1, seed=7, **_ERRORS)
    path = tmp_path / "s.json"
    scenario.save(path)
    assert load_scenario(path).spacecraft[0].navigation_error == scenario.spacecraft[0].navigation_error
    assert scenario.spacecraft[0].navigation_error.channel("velocity") == (0.01, 0.1)
    orbit_only = _template("22", 1)
    orbit_only.spacecraft[0].navigation_error = NavigationErrorConfig(**_ERRORS)
    with pytest.raises(ScenarioValidationError, match="needs attitude flight software"):
        orbit_only.validate()


def test_each_long_run_segment_gets_its_own_seed():
    """A segmented run rebuilds the simulation per segment: the scenario's
    seed (or Basilisk's default) plus the segment number, so the random
    walk does not repeat itself."""
    from spacemissionstudio.engine import long_run

    scenario = _template("07", 1, seed=41, **_ERRORS)
    second = copy.deepcopy(scenario)
    long_run._seed_navigation_errors(scenario, second, 3)
    assert second.spacecraft[0].navigation_error.seed == 44 and scenario.spacecraft[0].navigation_error.seed == 41
    scenario.spacecraft[0].navigation_error.seed = None
    long_run._seed_navigation_errors(scenario, second, 0)
    assert second.spacecraft[0].navigation_error.seed == 0x1badcad1


@pytest.mark.requires_basilisk
def test_simple_nav_gets_the_errors_in_its_own_units():
    """PMatrix holds the step and walkBounds the bound per axis, in
    simpleNav's units: m, m/s, MRP (tan(angle/4)), rad/s."""
    from spacemissionstudio.engine.fsw import navigation_error_matrices

    p_matrix, bounds = navigation_error_matrices(NavigationErrorConfig(**_ERRORS))
    assert [p_matrix[i][i] for i in (0, 3, 9)] == [1.0, 0.01, math.radians(0.0005)]
    assert p_matrix[6][6] == pytest.approx(math.tan(math.radians(0.002) / 4.0))
    assert bounds[8] == pytest.approx(math.tan(math.radians(0.02) / 4.0)) and bounds[14] == pytest.approx(
        math.tan(math.radians(1.0) / 4.0))
    assert bounds[15:] == [0.0, 0.0, 0.0] and p_matrix[0][1] == 0.0


@pytest.mark.requires_basilisk
def test_errors_stay_within_their_bounds_repeat_by_seed_and_leave_the_truth_plotted():
    """Template 07 for 30 minutes: every error is non-zero and within what
    its per-axis bound allows (sqrt(3) times it for a vector; for attitude
    and Sun heading the rotation whose three MRP components sit at the
    bound); the same seed repeats the run exactly and
    another seed does not; the attitude series stay the true attitude (the
    error series is their difference from what the software was told); an
    all-zero block changes nothing."""
    from spacemissionstudio.engine.service import SimulationService

    plain = SimulationService(_template("07", 30)).run()
    zero = SimulationService(_template("07", 30, seed=7)).run()
    assert set(zero.series) == set(plain.series)
    assert all(np.array_equal(plain.series[k].data, zero.series[k].data) for k in plain.series)

    first = SimulationService(_template("07", 30, seed=7, **_ERRORS)).run()
    again = SimulationService(_template("07", 30, seed=7, **_ERRORS)).run()
    other = SimulationService(_template("07", 30, seed=8, **_ERRORS)).run()
    def rotation_limit_deg(bound_deg):  # each MRP component held within tan(bound/4)
        return math.degrees(4.0 * math.atan(math.sqrt(3) * math.tan(math.radians(bound_deg) / 4.0)))

    limits = {"attitude": rotation_limit_deg(0.02), "rate": 0.005 * math.sqrt(3),
              "sun_heading": rotation_limit_deg(1.0), "position": 10.0 * math.sqrt(3),
              "velocity": 0.1 * math.sqrt(3)}
    for part, limit in limits.items():
        error = first.series[f"sat-1.navigation_error.{part}"].data[:, 0]
        assert 0.0 < error.max() <= limit * (1 + 1e-6), part
    assert all(np.array_equal(first.series[k].data, again.series[k].data) for k in first.series)
    assert not np.array_equal(first.series["sat-1.navigation_error.attitude"].data,
                              other.series["sat-1.navigation_error.attitude"].data)
    sigma = first.series["sat-1.attitude_sigma_BN"].data
    assert sigma.shape == plain.series["sat-1.attitude_sigma_BN"].data.shape
    assert not np.array_equal(sigma, plain.series["sat-1.attitude_sigma_BN"].data)  # flown on noisy navigation


@pytest.mark.requires_basilisk
@pytest.mark.requires_c_toolchain
def test_the_exported_flight_software_in_the_loop_sees_the_same_noisy_navigation(tmp_path):
    """With navigation errors on, the exported fsw_host in the loop still
    reproduces the normal run bit for bit: it is given the same noisy
    navigation the simulation's own modules read."""
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.fsw_export.records import export_flight_software
    from spacemissionstudio.sil.runner import SilOptions, run_sil

    scenario = _template("07", 5, seed=11, **_ERRORS)
    export_flight_software(scenario, "sat-1", tmp_path / "export", steps=10)
    build = tmp_path / "build"
    for args in (["-S", str(tmp_path / "export"), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release"],
                 ["--build", str(build), "--config", "Release", "-j", "4"]):
        done = subprocess.run(["cmake", *args], capture_output=True, text=True)  # noqa: S603,S607
        assert done.returncode == 0, done.stdout + done.stderr
    program = next(p for p in build.rglob("fsw_host*") if p.is_file() and p.suffix in ("", ".exe"))
    normal = SimulationService(copy.deepcopy(scenario)).run()
    result, report = run_sil(scenario, "sat-1", SilOptions(str(program)))
    assert report.completed and report.max_abs_error == 0.0 and report.steps == 301
    for name, series in normal.series.items():
        assert np.array_equal(series.data, result.series[name].data, equal_nan=True), name
