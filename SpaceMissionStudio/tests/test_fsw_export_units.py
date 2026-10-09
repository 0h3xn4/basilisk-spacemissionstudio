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

"""The flight-software export's Basilisk-free parts (SRS-F-18): reading C
declarations, payload layouts, C literals, the generated message
interface, the configuration digest and the export status."""

import copy
import hashlib
import json
import math

import numpy as np
import pytest

from spacemissionstudio.fsw_export import cdecl, digest, generate, model, records, sources
from spacemissionstudio.schema.scenario import (ActuatorConfig, FswExportRecord, OrbitIC, Scenario,
                                                ScenarioValidationError, SensorConfig, SpacecraftConfig)


def _scenario():
    def spacecraft(name):
        return SpacecraftConfig(
            name=name, orbit=OrbitIC(type="cartesian", position_km=[7000.0, 0.0, 0.0], velocity_km_s=[0.0, 7.5, 0.0]),
            fsw_mode="sunSafePoint", fsw_params={"sHatBdyCmd": [0.0, 0.0, 1.0]}, control_params={"K": 0.1, "P": 3.0},
            sensors=[SensorConfig(kind="coarse_sun_sensor", name="css-1", params={"nHat_B": [0.0, 0.0, 1.0]}),
                     SensorConfig(kind="star_tracker", name="st-1", params={"noise_arcsec": 5.0})],
            actuators=[ActuatorConfig(kind="reaction_wheel", name="rw-x",
                                      params={"gsHat_B": [1.0, 0.0, 0.0], "rw_type": "Honeywell_HR16",
                                              "maxMomentum": 50.0})])
    return Scenario(name="digest test", epoch_utc="2030-01-01T00:00:00", spacecraft=[spacecraft("sat-1"),
                                                                                     spacecraft("sat-2")])


def test_struct_fields_units_and_message_roles_come_from_the_header():
    """mrpFeedback's header gives every field, its unit and whether a
    message is an input or an output."""
    fields = {f.name: f for f in cdecl.parse_struct(
        sources.read_text("fswAlgorithms/attControl/mrpFeedback/mrpFeedback.h"), "mrpFeedbackConfig")}
    assert fields["K"].c_type == "double" and fields["K"].unit == "rad/sec"
    assert fields["ISCPntB_B"].dims == "[9]" and fields["ISCPntB_B"].unit == "kg m^2"
    assert fields["guidInMsg"].is_input and fields["guidInMsg"].message_type == "AttGuid"
    assert fields["cmdTorqueOutMsg"].is_output and not fields["cmdTorqueOutMsg"].is_input
    assert fields["bskLogger"].pointer
    with pytest.raises(cdecl.StructNotFound):
        cdecl.parse_struct("typedef struct { int a; } other;", "mrpFeedbackConfig")


def test_array_sizes_resolve_macros_and_refuse_unknown_names():
    macros = cdecl.integer_macros(sources.read_text("architecture/utilities/macroDefinitions.h"))
    assert macros["MAX_EFF_CNT"] == 36
    assert cdecl.array_shape("[MAX_EFF_CNT]", macros) == [36]
    assert cdecl.array_shape("[3*MAX_EFF_CNT]", macros) == [108]
    assert cdecl.array_shape("[3][3]", macros) == [3, 3]
    with pytest.raises(ValueError, match="unknown size 'NOT_A_MACRO'"):
        cdecl.array_shape("[NOT_A_MACRO]", macros)


def test_layouts_round_trip_through_json_and_decode_payloads():
    """A nested, padded layout survives layout_of -> JSON -> dtype_of, and
    decode reads the same values numpy does."""
    inner = np.dtype({"names": ["n", "v"], "formats": ["<i4", ("<f8", (2,))], "offsets": [0, 8], "itemsize": 24})
    outer = np.dtype({"names": ["count", "items"], "formats": ["<i4", (inner, (2,))], "offsets": [0, 8],
                      "itemsize": 56})
    layout = json.loads(json.dumps(model.layout_of(outer)))
    assert model.dtype_of(layout) == outer
    value = np.zeros(1, outer)
    value["count"] = 2
    value["items"][0, 1]["v"] = [1.5, -2.25]
    decoded = model.decode(layout, value.tobytes())
    assert decoded == {"count": 2, "items": [{"n": 0, "v": [0.0, 0.0]}, {"n": 0, "v": [1.5, -2.25]}]}
    assert model.layout_hash("Thing", layout) == model.layout_hash("Thing", model.layout_of(outer))
    assert model.layout_hash("Thing", layout) != model.layout_hash("Other", layout)


def test_c_literals_are_exact_and_skip_zeros():
    """repr() round-trips doubles; inf/nan use math.h's macros; trailing
    zero elements and zero fields are left out of initializers."""
    assert generate._c_number("<f8", 0.1) == "0.1" and float(generate._c_number("<f8", 1 / 3)) == 1 / 3
    assert generate._c_number("<f8", 2.0) == "2.0"
    assert generate._c_number("<f8", math.inf) == "INFINITY" and generate._c_number("<f8", -math.inf) == "-INFINITY"
    assert generate._c_number("<f8", math.nan) == "NAN"
    assert generate._c_number("<u8", 5) == "5ULL" and generate._c_number("<u4", 5) == "5U"
    assert not generate._is_zero(-0.0)  # a negative zero is written out
    layout = model.layout_of(np.dtype([("a", "<f8", (3,)), ("b", "<i4"), ("c", "<f8")]))
    assert generate._c_struct(layout, {"a": [1.0, 0.0, 0.0], "b": 0, "c": 2.5}) == "{.a = {1.0}, .c = 2.5}"
    assert generate._c_struct(layout, {"a": [0.0, 0.0, 0.0], "b": 0, "c": 0.0}) == "{0}"


def test_the_message_interface_keeps_basilisks_c_functions_only():
    """Generated from Basilisk's own templates: every C-to-C function,
    none of the C++ (cpp_*, addr_*, unsubscribe) ones."""
    header, source = generate._message_interface("AttGuid")
    assert '#include "architecture/msgPayloadDefC/AttGuidMsgPayload.h"' in header
    for name in generate._C_FUNCTIONS:
        assert f"AttGuidMsg_{name}(" in header and f"AttGuidMsg_{name}(" in source
    for cpp in ("_cpp_subscribe", "_addr_subscribe", "_unsubscribe", "Message<", "reinterpret_cast", "messaging.h"):
        assert cpp not in source and cpp not in header.split("#ifdef __cplusplus")[0]
    assert "@MSG_AUTOSOURCE" not in header + source


def test_leaves_flatten_nested_payloads_without_padding():
    inner = np.dtype({"names": ["n", "v"], "formats": ["<i4", "<f8"], "offsets": [0, 8], "itemsize": 16})
    layout = model.layout_of(np.dtype({"names": ["k", "s"], "formats": ["<i4", (inner, (2,))], "offsets": [0, 8],
                                       "itemsize": 40}))
    assert generate._leaves(layout) == [(0, 1, "<i4", "k"), (8, 1, "<i4", "s[0].n"), (16, 1, "<f8", "s[0].v"),
                                        (24, 1, "<i4", "s[1].n"), (32, 1, "<f8", "s[1].v")]


def test_the_digest_follows_flight_software_settings_only():
    """Gains, pointing, actuators, inertia, sun sensors and the step make
    an export stale; the orbit, another spacecraft, star trackers and the
    duration do not. Each change names its group."""
    base = _scenario()
    parts = digest.fsw_config_parts(base, "sat-1")

    def changed(edit):
        s = copy.deepcopy(base)
        edit(s)
        return digest.changed_parts(parts, digest.fsw_config_parts(s, "sat-1"))

    assert changed(lambda s: s.spacecraft[0].control_params.update(K=0.2)) == ["control_params"]
    assert changed(lambda s: s.spacecraft[0].fsw_params.update(sHatBdyCmd=[1.0, 0.0, 0.0])) == ["fsw_params"]
    assert changed(lambda s: setattr(s.spacecraft[0], "fsw_mode", "inertial3D")) == ["fsw_mode"]
    assert changed(lambda s: s.spacecraft[0].actuators[0].params.update(maxMomentum=75.0)) == ["actuators"]
    assert changed(lambda s: s.spacecraft[0].inertia_kg_m2.__setitem__(0, 11.0)) == ["inertia_kg_m2"]
    assert changed(lambda s: s.spacecraft[0].sensors[0].params.update(nHat_B=[1.0, 0.0, 0.0])) == \
        ["coarse sun sensors"]
    assert changed(lambda s: setattr(s.sim_settings, "dynamics_task_rate_s", 0.5)) == ["dynamics step"]
    assert changed(lambda s: setattr(s.spacecraft[0].orbit, "position_km", [7100.0, 0.0, 0.0])) == []
    assert changed(lambda s: s.spacecraft[1].control_params.update(K=9.0)) == []
    assert changed(lambda s: s.spacecraft[0].sensors[1].params.update(noise_arcsec=1.0)) == []
    assert changed(lambda s: setattr(s.sim_settings, "duration_days", 3.0)) == []
    assert len(digest.fsw_config_digest(base, "sat-1")) == 64
    with pytest.raises(KeyError):
        digest.fsw_config_parts(base, "nobody")


def _fake_export(tmp_path, scenario, name="sat-1"):
    folder = tmp_path / "export"
    folder.mkdir()
    (folder / "ICD.md").write_text("# ICD\n")
    files = {"ICD.md": hashlib.sha256(b"# ICD\n").hexdigest()}
    record = FswExportRecord(spacecraft=name, path=str(folder),
                             config_digest=digest.fsw_config_digest(scenario, name),
                             exported_utc="2026-10-09T00:00:00Z", parts=digest.fsw_config_parts(scenario, name))
    (folder / "manifest.json").write_text(json.dumps({"config_digest": record.config_digest, "files": files}))
    return folder, record


def test_export_status_tells_current_stale_modified_and_missing(tmp_path):
    scenario = _scenario()
    folder, record = _fake_export(tmp_path, scenario)
    assert records.export_status(scenario, record).state == records.CURRENT
    scenario.spacecraft[0].control_params["P"] = 4.0
    stale = records.export_status(scenario, record)
    assert stale.state == records.STALE and stale.changed == ["control_params"] and "control_params" in stale.message
    (folder / "ICD.md").write_text("# edited\n")
    assert records.export_status(scenario, record).state == records.MODIFIED
    (folder / "manifest.json").unlink()
    assert records.export_status(scenario, record).state == records.MISSING
    relative = FswExportRecord(spacecraft="ghost", path="x", config_digest="0" * 64)
    assert records.export_status(scenario, relative).state == records.UNKNOWN_SPACECRAFT


def test_export_records_validate_and_round_trip_with_the_scenario(tmp_path):
    scenario = _scenario()
    _, record = _fake_export(tmp_path, scenario)
    scenario.fsw_exports = records.with_record(scenario, record)
    scenario.validate()
    path = tmp_path / "s.json"
    scenario.save(path)
    from spacemissionstudio.schema import load_scenario

    loaded = load_scenario(path)
    assert loaded.fsw_exports == [record]
    newer = FswExportRecord(**{**record.__dict__, "exported_utc": "later"})
    assert records.with_record(loaded, newer) == [newer]  # one record per spacecraft
    loaded.fsw_exports = [record, newer]
    with pytest.raises(ScenarioValidationError, match="more than once"):
        loaded.validate()
    loaded.fsw_exports = [FswExportRecord(spacecraft="sat-1", path="x", config_digest="xyz")]
    with pytest.raises(ScenarioValidationError, match="64 lower-case hex"):
        loaded.validate()
