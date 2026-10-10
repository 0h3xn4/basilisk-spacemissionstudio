"""Tests for spacemissionstudio.schema.command.Command -- no Basilisk import,
runs anywhere.
"""

from dataclasses import asdict

import pytest

from spacemissionstudio.schema.command import Command


def test_default_command_has_no_children():
    assert Command(kind="script_block", params={"code": "x = 1"}).children == []


def test_unknown_kind_is_rejected():
    errors = Command(kind="nonsense").validate("mission_sequence[0]")
    assert len(errors) == 1
    assert "nonsense" in errors[0]
    assert "mission_sequence[0]" in errors[0]


def test_label_appears_in_error_paths():
    errors = Command(kind="nonsense", label="My Command").validate("mission_sequence[0]")
    assert "'My Command'" in errors[0]


# -- propagate -----------------------------------------------------------

def test_propagate_duration_valid():
    assert Command(kind="propagate", params={"stop_condition": "duration", "duration_days": 1.0}).validate("p") == []


def test_propagate_duration_missing_is_rejected():
    errors = Command(kind="propagate", params={"stop_condition": "duration"}).validate("p")
    assert any("duration_days" in e for e in errors)


def test_propagate_duration_zero_is_rejected():
    errors = Command(kind="propagate", params={"stop_condition": "duration", "duration_days": 0}).validate("p")
    assert any("duration_days" in e for e in errors)


def test_propagate_epoch_valid():
    cmd = Command(kind="propagate", params={"stop_condition": "epoch", "stop_epoch_utc": "2030-01-02T00:00:00"})
    assert cmd.validate("p") == []


def test_propagate_epoch_malformed_is_rejected():
    errors = Command(kind="propagate", params={"stop_condition": "epoch", "stop_epoch_utc": "not-a-date"}).validate("p")
    assert any("stop_epoch_utc" in e for e in errors)


def test_propagate_event_valid():
    cmd = Command(kind="propagate",
                  params={"stop_condition": "event", "event_kind": "periapsis", "spacecraft": "sat-1"})
    assert cmd.validate("p") == []


def test_propagate_event_missing_spacecraft_is_rejected():
    errors = Command(kind="propagate", params={"stop_condition": "event", "event_kind": "periapsis"}).validate("p")
    assert any("spacecraft" in e for e in errors)


def test_propagate_pass_event_needs_a_ground_station():
    command = Command(kind="propagate", params={"stop_condition": "event", "event_kind": "pass_start",
                                                "spacecraft": "sat-1"})
    assert any("propagate.ground_station must name the station" in e for e in command.validate("c"))
    command.params["ground_station"] = "berlin-gs"
    assert command.validate("c") == []


def test_propagate_event_bad_kind_is_rejected():
    errors = Command(kind="propagate",
                      params={"stop_condition": "event", "event_kind": "sunrise", "spacecraft": "sat-1"}).validate("p")
    assert any("event_kind" in e for e in errors)


def test_propagate_bad_stop_condition_is_rejected():
    errors = Command(kind="propagate", params={"stop_condition": "bogus"}).validate("p")
    assert any("stop_condition" in e for e in errors)


# -- maneuver --------------------------------------------------------------

def test_maneuver_valid():
    cmd = Command(kind="maneuver", params={"spacecraft": "sat-1", "delta_v_m_s": [1.0, 0.0, 0.0]})
    assert cmd.validate("m") == []


def test_maneuver_defaults_to_inertial_frame():
    cmd = Command(kind="maneuver", params={"spacecraft": "sat-1", "delta_v_m_s": [1.0, 0.0, 0.0]})
    assert cmd.validate("m") == []  # frame omitted -> "inertial" default is valid


def test_maneuver_missing_spacecraft_is_rejected():
    errors = Command(kind="maneuver", params={"delta_v_m_s": [1.0, 0.0, 0.0]}).validate("m")
    assert any("spacecraft" in e for e in errors)


def test_maneuver_bad_delta_v_shape_is_rejected():
    errors = Command(kind="maneuver", params={"spacecraft": "sat-1", "delta_v_m_s": [1.0, 0.0]}).validate("m")
    assert any("delta_v_m_s" in e for e in errors)


def test_maneuver_bad_frame_is_rejected():
    errors = Command(kind="maneuver",
                      params={"spacecraft": "sat-1", "delta_v_m_s": [1.0, 0.0, 0.0], "frame": "lvlh"}).validate("m")
    assert any("frame" in e for e in errors)


def test_maneuver_reports_every_problem_at_once():
    """The key requirement: a collecting validate(), not raise-fast."""
    errors = Command(kind="maneuver", params={}).validate("m")
    assert len(errors) >= 2  # missing spacecraft AND missing delta_v_m_s, both reported -- not just the first
    assert any("spacecraft" in e for e in errors)
    assert any("delta_v_m_s" in e for e in errors)


# -- lambert_transfer -------------------------------------------------------

def test_lambert_transfer_valid():
    cmd = Command(kind="lambert_transfer", params={
        "spacecraft": "sat-1", "target_position_m": [1.0, 0.0, 0.0], "time_of_flight_s": 3600.0,
    })
    assert cmd.validate("l") == []


def test_lambert_transfer_defaults_num_revolutions_and_constraints():
    cmd = Command(kind="lambert_transfer", params={
        "spacecraft": "sat-1", "target_position_m": [1.0, 0.0, 0.0], "time_of_flight_s": 3600.0,
    })
    assert cmd.validate("l") == []  # num_revolutions/max_distance_target_m/min_orbit_radius_m all optional


def test_lambert_transfer_missing_spacecraft_is_rejected():
    errors = Command(kind="lambert_transfer",
                      params={"target_position_m": [1.0, 0.0, 0.0], "time_of_flight_s": 3600.0}).validate("l")
    assert any("spacecraft" in e for e in errors)


def test_lambert_transfer_bad_target_position_shape_is_rejected():
    errors = Command(kind="lambert_transfer",
                      params={"spacecraft": "sat-1", "target_position_m": [1.0, 0.0],
                               "time_of_flight_s": 3600.0}).validate("l")
    assert any("target_position_m" in e for e in errors)


def test_lambert_transfer_missing_time_of_flight_is_rejected():
    errors = Command(kind="lambert_transfer",
                      params={"spacecraft": "sat-1", "target_position_m": [1.0, 0.0, 0.0]}).validate("l")
    assert any("time_of_flight_s" in e for e in errors)


def test_lambert_transfer_non_positive_time_of_flight_is_rejected():
    errors = Command(kind="lambert_transfer", params={
        "spacecraft": "sat-1", "target_position_m": [1.0, 0.0, 0.0], "time_of_flight_s": 0.0,
    }).validate("l")
    assert any("time_of_flight_s" in e for e in errors)


def test_lambert_transfer_negative_num_revolutions_is_rejected():
    errors = Command(kind="lambert_transfer", params={
        "spacecraft": "sat-1", "target_position_m": [1.0, 0.0, 0.0], "time_of_flight_s": 3600.0,
        "num_revolutions": -1,
    }).validate("l")
    assert any("num_revolutions" in e for e in errors)


def test_lambert_transfer_negative_min_orbit_radius_is_rejected():
    errors = Command(kind="lambert_transfer", params={
        "spacecraft": "sat-1", "target_position_m": [1.0, 0.0, 0.0], "time_of_flight_s": 3600.0,
        "min_orbit_radius_m": -1.0,
    }).validate("l")
    assert any("min_orbit_radius_m" in e for e in errors)


def test_lambert_transfer_reports_every_problem_at_once():
    errors = Command(kind="lambert_transfer", params={}).validate("l")
    assert len(errors) >= 2  # missing spacecraft AND missing target_position_m AND time_of_flight_s
    assert any("spacecraft" in e for e in errors)
    assert any("target_position_m" in e for e in errors)
    assert any("time_of_flight_s" in e for e in errors)


# -- assignment / report ----------------------------------------------------

def test_assignment_valid():
    cmd = Command(kind="assignment", params={"target": "sat-1.station_keeping.thrust_n", "value": 0.5})
    assert cmd.validate("a") == []


def test_assignment_missing_value_is_rejected():
    errors = Command(kind="assignment", params={"target": "sat-1.x"}).validate("a")
    assert any("value" in e for e in errors)


def test_assignment_target_without_dot_is_rejected():
    errors = Command(kind="assignment", params={"target": "sat-1", "value": 1}).validate("a")
    assert any("target" in e for e in errors)


def test_report_empty_series_is_valid():
    assert Command(kind="report", params={}).validate("r") == []


def test_report_bad_series_type_is_rejected():
    errors = Command(kind="report", params={"series": "sat-1.position_N"}).validate("r")
    assert any("series" in e for e in errors)


# -- if/while + children ----------------------------------------------------

def test_conditional_requires_condition():
    errors = Command(kind="if", params={}).validate("i")
    assert any("condition" in e for e in errors)


def test_non_conditional_kind_rejects_children():
    child = Command(kind="script_block", params={"code": "pass"})
    errors = Command(kind="maneuver", params={"spacecraft": "s", "delta_v_m_s": [0, 0, 0]},
                      children=[child]).validate("m")
    assert any("does not accept children" in e for e in errors)


def test_if_validates_children_recursively():
    bad_child = Command(kind="maneuver", params={})  # missing everything
    cmd = Command(kind="if", params={"condition": "True"}, children=[bad_child])
    errors = cmd.validate("mission_sequence[0]")
    assert any("mission_sequence[0].children[0]" in e for e in errors)


def test_nested_if_validates_grandchildren():
    grandchild = Command(kind="script_block", params={})  # missing code
    child = Command(kind="while", params={"condition": "True"}, children=[grandchild])
    root = Command(kind="if", params={"condition": "True"}, children=[child])
    errors = root.validate("mission_sequence[0]")
    assert any("children[0].children[0]" in e for e in errors)


def test_script_block_valid():
    assert Command(kind="script_block", params={"code": "x = 1"}).validate("s") == []


def test_script_block_missing_code_is_rejected():
    errors = Command(kind="script_block", params={}).validate("s")
    assert any("code" in e for e in errors)


# -- (de)serialization -------------------------------------------------------

def test_to_dict_via_asdict_and_from_dict_round_trip():
    original = Command(
        kind="if", label="Check altitude", params={"condition": "alt < 500"},
        children=[Command(kind="maneuver", label="Trim burn",
                            params={"spacecraft": "sat-1", "delta_v_m_s": [0.1, 0.0, 0.0], "frame": "vnb"})],
    )
    data = asdict(original)
    rebuilt = Command.from_dict(data)
    assert rebuilt == original


def test_from_dict_defaults_missing_optional_fields():
    rebuilt = Command.from_dict({"kind": "propagate"})
    assert rebuilt.label is None
    assert rebuilt.params == {}
    assert rebuilt.children == []


# -- report before any propagate ------------------------------------------------

def _report(label="r"):
    return Command(kind="report", label=label, params={"series": []})


def _propagate():
    return Command(kind="propagate", params={"stop_condition": "duration", "duration_days": 0.01})


def test_a_report_before_any_propagate_is_flagged():
    """The engine fails on such a report at run time ("no recorded samples
    yet") -- template 16 shipped that way; it is now caught up front."""
    from spacemissionstudio.schema.command import report_before_propagate_errors

    errors = report_before_propagate_errors([_report(), _propagate(), _report()])
    assert len(errors) == 1
    assert errors[0].startswith("mission_sequence[0]") and "before any propagate" in errors[0]


def test_a_report_after_a_propagate_is_fine():
    from spacemissionstudio.schema.command import report_before_propagate_errors

    assert report_before_propagate_errors([_propagate(), _report(), _report()]) == []
    assert report_before_propagate_errors([]) == []


def test_only_certain_cases_are_flagged():
    """A report inside if/while may never run, and a propagate nested in an
    earlier command may have run -- flagging either would block Run on a
    sequence that can work, so neither is an error."""
    from spacemissionstudio.schema.command import report_before_propagate_errors

    skipped = Command(kind="if", params={"condition": "t_s > 0.0"}, children=[_report()])
    assert report_before_propagate_errors([skipped, _propagate()]) == []
    loop = Command(kind="while", params={"condition": "t_s < 10.0"}, children=[_propagate()])
    assert report_before_propagate_errors([loop, _report()]) == []


def test_scenario_validation_reports_it(tmp_path):
    from pathlib import Path

    import pytest

    from spacemissionstudio.schema import ScenarioValidationError, load_scenario, validate_all

    templates = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
    scenario = load_scenario(templates / "08_mission_sequence_orbit_raise.json")
    scenario.mission_sequence.insert(0, _report("too early"))
    with pytest.raises(ScenarioValidationError, match="before any propagate"):
        scenario.validate()
    assert any("before any propagate" in error for error in validate_all(scenario))


# -- if/while conditions and script blocks (R15, security_analysis.md) ------

_CONTEXT = {"t_s": 120.0, "duration_days": 1.0,
            "spacecraft": {"sat-1": {"altitude_m": 400e3, "r_BN_N": [6778e3, 0.0, 0.0]}}}


@pytest.mark.parametrize("expression, expected", [
    ("t_s > 60", True),
    ("t_s < 60 or duration_days == 1", True),
    ("not (t_s >= 60 and t_s <= 180)", False),
    ("spacecraft['sat-1']['altitude_m'] < 500e3", True),
    ("spacecraft['sat-1']['r_BN_N'][0] / 1e3 > 6000", True),
    ("-t_s + 2 ** 3 * 15", 0.0),
    ("0 < t_s < 100", False),
    ("'sat-1' in spacecraft", True),
    ("1 if t_s > 100 else 2", 1),
    ("True", True),
])
def test_conditions_evaluate_like_python(expression, expected):
    """The allowed subset gives Python's own value for each expression."""
    from spacemissionstudio.schema.command import evaluate_condition

    assert evaluate_condition(expression, _CONTEXT) == expected


@pytest.mark.parametrize("expression", [
    "().__class__.__base__.__subclasses__()",
    "t_s.real",
    "__import__('os')",
    "open('/etc/passwd')",
    "(lambda: 1)()",
    "[x for x in spacecraft]",
])
def test_conditions_cannot_reach_beyond_their_values(expression):
    """Attribute access, calls, lambdas and comprehensions are refused, so
    a condition from a scenario file cannot reach any Python object
    (finding S-02)."""
    from spacemissionstudio.schema.command import ConditionError, evaluate_condition

    with pytest.raises(ConditionError, match="is not allowed in a condition"):
        evaluate_condition(expression, _CONTEXT)


def test_condition_errors_name_the_problem():
    """Unknown names list the available ones; a syntax error and a huge
    exponent are refused with a message."""
    from spacemissionstudio.schema.command import ConditionError, evaluate_condition

    with pytest.raises(ConditionError, match="unknown name 'alt'.*spacecraft"):
        evaluate_condition("alt < 500", _CONTEXT)
    with pytest.raises(ConditionError, match="not a valid expression"):
        evaluate_condition("t_s >", _CONTEXT)
    with pytest.raises(ConditionError, match="exponent"):
        evaluate_condition("10 ** 10 ** 10", _CONTEXT)



@pytest.mark.parametrize("expression, reason", [
    ("-" * 100_000 + "1", "longer than 2000 characters"),
    ("+".join(["1"] * 5000), "longer than 2000 characters"),
    ("-" * 1500 + "1", "nested more than 50 levels deep"),
    ("'x' * 10 ** 9", "repeats a text or list more than 1000000 times"),
    ("10 ** 999 * [0]", "repeats a text or list more than 1000000 times"),
], ids=["long-unary", "long-sum", "deep", "repeat-text", "repeat-list"])  # short: Windows caps the test id's env var
def test_a_condition_cannot_exhaust_memory_or_the_stack(expression, reason):
    """A crafted condition is refused with a message (security analysis
    S-12): too long or nested too deep (it raised MemoryError or
    RecursionError, which crashed loading the scenario; both are refused
    at validation), or repeating a text or list without bound (refused
    when evaluated). Ordinary nesting still works."""
    from spacemissionstudio.schema.command import ConditionError, evaluate_condition

    with pytest.raises(ConditionError, match=reason):
        evaluate_condition(expression, _CONTEXT)
    if not reason.startswith("repeats"):  # length and depth are refused already when the scenario is validated
        assert Command(kind="if", params={"condition": expression}).validate("mission_sequence[0]")
    assert evaluate_condition("((((1 + 2) * 3) - 4) / 5) > 0 and -(-(-1)) < 0", _CONTEXT) is True

def test_validation_reports_a_condition_outside_the_allowed_set():
    """The editor shows a disallowed condition before the run, with the
    command's path."""
    command = Command(kind="if", params={"condition": "t_s.real > 0"})
    assert any("if.condition: Attribute is not allowed" in error for error in command.validate("mission_sequence[0]"))


def test_script_blocks_are_found_at_any_depth():
    """script_blocks() lists every script_block with its item path, so the
    CLI and the GUI can ask for consent naming each one (SRS-S-03)."""
    from spacemissionstudio.schema.command import script_blocks

    commands = [
        Command(kind="script_block", params={"code": "pass"}),
        Command(kind="while", params={"condition": "t_s < 10"}, children=[
            Command(kind="if", params={"condition": "True"}, children=[
                Command(kind="script_block", params={"code": "pass"}),
            ]),
        ]),
    ]
    assert [path for path, _ in script_blocks(commands)] == [
        "mission_sequence[0]", "mission_sequence[1].children[0].children[0]"]
