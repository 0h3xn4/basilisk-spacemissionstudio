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

"""A hand-edited or shared scenario file that is malformed is refused with
a message naming the field, never with a Python traceback (SRS-F-01:
"Validation errors shall name the field at fault"; ``load_scenario``
promises a ScenarioValidationError "on anything malformed").

Found by an audit that mutated the bundled templates: 62 kinds of wrong
value got through as TypeError, ValueError or AttributeError (the GUI's
Open showed nothing, ``validate`` printed a traceback), and a deeply
nested condition crashed loading with MemoryError."""

import copy
import json
import random
from pathlib import Path

import pytest

from spacemissionstudio.schema import load_scenario
from spacemissionstudio.schema.scenario import ScenarioValidationError

_TEMPLATES = sorted((Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates")
                    .glob("*.json"))


def _template(prefix):
    return json.loads(next(p for p in _TEMPLATES if p.name.startswith(prefix)).read_text())


def _set(data, path, value):
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


@pytest.mark.parametrize("prefix, path, value, message", [
    ("18", ["spacecraft", 0, "station_keeping", "isp_s"], [1], "spacecraft[0].station_keeping.isp_s: expected a number, got a list"),
    ("06", ["space_weather", "forecast_percentile"], "x", "space_weather.forecast_percentile: expected a number, got text"),
    ("03", ["sim_settings", "dynamics_task_rate_s"], {}, "sim_settings.dynamics_task_rate_s: expected a number, got an object"),
    ("07", ["spacecraft", 0, "name"], [1], "spacecraft[0].name: expected text, got a list"),
    ("14", ["spacecraft", 0, "sensors", 0, "params"], "oops", "spacecraft[0].sensors[0].params: expected an object, got text"),
    ("05", ["spacecraft", 0, "station_keeping", "thrust_n"], True, "expected a number, got true/false"),
])
def test_a_wrong_typed_value_is_refused_naming_the_field(tmp_path, prefix, path, value, message):
    data = _template(prefix)
    _set(data, path, value)
    file = tmp_path / "s.json"
    file.write_text(json.dumps(data))
    with pytest.raises(ScenarioValidationError, match=message.replace("[", r"\[").replace("]", r"\]")):
        load_scenario(file)


def test_a_condition_that_would_exhaust_memory_is_refused_on_load(tmp_path):
    """A shared scenario whose if-condition nests 100 000 levels deep
    raised MemoryError while loading; now it is refused with the reason."""
    data = _template("08")
    data["mission_sequence"] = [{"kind": "if", "params": {"condition": "-" * 100_000 + "1"}, "children": []}]
    file = tmp_path / "s.json"
    file.write_text(json.dumps(data))
    with pytest.raises(ScenarioValidationError, match="longer than 2000 characters"):
        load_scenario(file)


_WEIRD = [None, "x", -1, 0, 1e308, [], {}, [1, 2], {"a": 1}, True, "", 10 ** 20]


def test_mutated_templates_load_or_are_refused_never_crash(tmp_path):
    """400 random single changes to the bundled templates (a value replaced
    by a wrong type, a key removed or added): each loads, or is refused
    with ScenarioValidationError. Seeded, so a failure repeats."""
    rng = random.Random(20261010)
    file = tmp_path / "s.json"
    for _ in range(400):
        data = json.loads(rng.choice(_TEMPLATES).read_text())
        paths, todo = [], [((), data)]
        while todo:
            prefix, node = todo.pop()
            items = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ()
            for key, child in items:
                paths.append(prefix + (key,))
                todo.append((prefix + (key,), child))
        path = rng.choice(paths)
        parent = data
        for key in path[:-1]:
            parent = parent[key]
        if isinstance(parent, dict) and rng.random() < 0.2:
            del parent[path[-1]]
        else:
            parent[path[-1]] = copy.deepcopy(rng.choice(_WEIRD))
        file.write_text(json.dumps(data))
        try:
            load_scenario(file)
        except ScenarioValidationError:
            pass
