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
"""The input differences between two runs (UX/UI guidelines, "run
comparison": "a diff of their inputs")."""

from pathlib import Path

from spacemissionstudio.engine.scenario_diff import diff, short
from spacemissionstudio.schema import load_scenario

_TEMPLATES = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"


def test_named_list_items_are_matched_by_name_not_position():
    a = {"spacecraft": [{"name": "sat-1", "mass": 100}, {"name": "sat-2", "mass": 200}]}
    b = {"spacecraft": [{"name": "new", "mass": 50}, {"name": "sat-1", "mass": 100}, {"name": "sat-2", "mass": 210}]}
    assert diff(a, b) == [("spacecraft[sat-2].mass", 200, 210), ("spacecraft[new]", "(none)", {"name": "new",
                                                                                               "mass": 50})]


def test_plain_values_lists_and_missing_keys():
    a = {"gravity": {"degree": 10, "third_body_perturbers": ["sun"]}, "only_a": 1}
    b = {"gravity": {"degree": 20, "third_body_perturbers": ["sun", "moon"]}}
    assert diff(a, b) == [("gravity.degree", 10, 20), ("gravity.third_body_perturbers", ["sun"], ["sun", "moon"]),
                          ("only_a", 1, "(none)")]
    assert diff(a, a) == []


def test_a_real_template_edit_names_the_field():
    scenario = load_scenario(_TEMPLATES / "05_formation_flying_phasing.json")
    before = scenario.to_dict()
    scenario.spacecraft[1].orbit.semi_major_axis_km += 1.0  # [km]
    scenario.sim_settings.duration_days = 30.0  # [day]
    paths = [path for path, _old, _new in diff(before, scenario.to_dict())]
    assert sorted(paths) == ["sim_settings.duration_days",
                             f"spacecraft[{scenario.spacecraft[1].name}].orbit.semi_major_axis_km"]
    assert short("x" * 100).endswith("...") and len(short("x" * 100)) == 60
