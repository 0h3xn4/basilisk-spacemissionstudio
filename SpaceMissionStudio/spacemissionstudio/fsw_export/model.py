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

"""What :mod:`.capture` reads out of a built simulation, as plain data.

Everything here is Basilisk-free and JSON-serialisable, so the generator,
the GUI and the tests work from it without Basilisk. Message payloads are
kept as raw bytes, exactly as Basilisk held them, with their binary
layout (:func:`layout_of`, from the payload's numpy dtype) to read them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


def layout_of(dtype: np.dtype) -> dict:
    """``{"itemsize", "fields": [{"name", "offset", "shape", "kind" | "struct"}]}``."""
    fields = []
    for name in dtype.names:
        sub, offset = dtype.fields[name][:2]
        entry = {"name": name, "offset": int(offset), "shape": [int(n) for n in sub.shape]}
        if sub.base.names:
            entry["struct"] = layout_of(sub.base)
        else:
            entry["kind"] = sub.base.str  # e.g. "<f8", "<i4", "<u8", "|i1"
        fields.append(entry)
    return {"itemsize": int(dtype.itemsize), "fields": fields}


def dtype_of(layout: dict) -> np.dtype:
    return np.dtype({
        "names": [f["name"] for f in layout["fields"]],
        "formats": [((dtype_of(f["struct"]) if "struct" in f else np.dtype(f["kind"])), tuple(f["shape"]))
                    if f["shape"] else (dtype_of(f["struct"]) if "struct" in f else np.dtype(f["kind"]))
                    for f in layout["fields"]],
        "offsets": [f["offset"] for f in layout["fields"]],
        "itemsize": layout["itemsize"],
    })


def layout_hash(message_type: str, layout: dict) -> str:
    """16 hex digits identifying a payload type and its exact binary layout
    (the SIL contract compares these before the first step)."""
    text = json.dumps({"type": message_type, "layout": layout}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def leaves(layout: dict, base: int = 0, prefix: str = "") -> List[Tuple[int, int, str, str]]:
    """``(offset, count, kind, name)`` runs of scalars, nested structs
    flattened; padding is in no run. The generated ``fsw_leaves.c`` and the
    SIL comparison both read payloads this way."""
    out = []
    for entry in layout["fields"]:
        count = 1
        for n in entry["shape"]:
            count *= n
        name = prefix + entry["name"]
        if "struct" in entry:
            size = entry["struct"]["itemsize"]
            for i in range(count):
                out += leaves(entry["struct"], base + entry["offset"] + i * size,
                              f"{name}[{i}]." if count > 1 or entry["shape"] else f"{name}.")
        else:
            out.append((base + entry["offset"], count, entry["kind"], name))
    return out


def decode(layout: dict, data: bytes):
    """A payload's bytes as nested Python values: ``{field: value}``, arrays
    as (nested) lists."""
    return _decode_fields(layout, data, 0)


def _decode_fields(layout: dict, data: bytes, base: int) -> dict:
    out = {}
    for f in layout["fields"]:
        count = int(np.prod(f["shape"])) if f["shape"] else 1
        if "struct" in f:
            size = f["struct"]["itemsize"]
            items = [_decode_fields(f["struct"], data, base + f["offset"] + i * size) for i in range(count)]
        else:
            kind = np.dtype(f["kind"])
            items = np.frombuffer(data, dtype=kind, count=count, offset=base + f["offset"]).tolist()
        out[f["name"]] = _reshape(items, f["shape"]) if f["shape"] else items[0]
    return out


def _reshape(items: list, shape: List[int]):
    if len(shape) <= 1:
        return list(items)
    step = int(np.prod(shape[1:]))
    return [_reshape(items[i * step:(i + 1) * step], shape[1:]) for i in range(shape[0])]


@dataclass
class MessageType:
    name: str  # "AttGuid"
    layout: dict

    @property
    def size(self) -> int:
        return self.layout["itemsize"]

    @property
    def hash(self) -> str:
        return layout_hash(self.name, self.layout)


@dataclass
class Param:
    """One field of a module's configuration struct and the value Basilisk
    held before ``InitializeSimulation()``."""
    name: str
    c_type: str
    dims: str
    unit: str
    description: str
    value: object  # number, (nested) list of numbers, or {"bytes": hex} for a struct-typed field
    scenario_path: Optional[str] = None
    gui: str = "-"
    note: str = ""


@dataclass
class InputLink:
    field: str
    message_type: str
    kind: str  # "module", "input", "constant" or "unlinked"
    ref: str = ""  # "<module>.<field>", the input port's name, or the constant's name


@dataclass
class ModuleInstance:
    tag: str  # Basilisk ModelTag, e.g. "sat-1_mrpFeedback"
    name: str  # C identifier used in the export, e.g. "mrpFeedback"
    python_name: str  # catalog key
    module_id: int
    params: List[Param] = field(default_factory=list)
    inputs: List[InputLink] = field(default_factory=list)
    outputs: List[Dict[str, str]] = field(default_factory=list)  # [{"field", "message_type"}]


@dataclass
class Port:
    """A message crossing the flight-software boundary."""
    name: str  # C identifier, e.g. "simpleNav_attOutMsg"
    message_type: str
    producer: str  # "sat-1_simpleNav.attOutMsg (simpleNav)" for inputs; "<module>.<field>" for outputs
    consumers: List[str] = field(default_factory=list)


@dataclass
class Constant:
    name: str
    message_type: str
    value_hex: str
    consumers: List[str] = field(default_factory=list)
    scenario_path: Optional[str] = None
    gui: str = "-"
    note: str = ""


@dataclass
class FswCapture:
    spacecraft: str
    scenario_name: str
    basilisk_version: str
    basilisk_revision: str
    rate_ns: int
    modules: List[ModuleInstance]  # in execution order
    message_types: Dict[str, MessageType]
    inputs: List[Port]
    outputs: List[Port]  # actuator commands: read by the simulation
    telemetry: List[Port]  # every other module output
    constants: List[Constant]
    priming_resets: List[str]  # module names re-Reset after the step at priming_time_ns
    priming_time_ns: int
    not_exported: List[str]
    config_digest: str
    # Recorded run: one entry per step, payloads as hex.
    times_ns: List[int] = field(default_factory=list)
    input_trace: List[Dict[str, str]] = field(default_factory=list)  # {port: hex}
    output_trace: List[Dict[str, str]] = field(default_factory=list)  # {"<module>.<field>": hex}
    # What each module read at step 0 ({"<module>.<field>": hex}), for its unit test.
    step0_reads: Dict[str, str] = field(default_factory=dict)
    # State when InitializeSimulation() had run every Reset(): each input
    # port and module output, hex if it had been written, else None.
    reset_inputs: Dict[str, Optional[str]] = field(default_factory=dict)
    reset_outputs: Dict[str, Optional[str]] = field(default_factory=dict)
    exported_with: Dict[str, str] = field(default_factory=dict)  # tool and Python versions

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "FswCapture":
        data = json.loads(text)
        data["modules"] = [ModuleInstance(**{**m, "params": [Param(**p) for p in m["params"]],
                                             "inputs": [InputLink(**i) for i in m["inputs"]]})
                           for m in data["modules"]]
        data["message_types"] = {k: MessageType(**v) for k, v in data["message_types"].items()}
        for key in ("inputs", "outputs", "telemetry"):
            data[key] = [Port(**p) for p in data[key]]
        data["constants"] = [Constant(**c) for c in data["constants"]]
        return cls(**data)

    def module(self, name: str) -> ModuleInstance:
        return next(m for m in self.modules if m.name == name)
