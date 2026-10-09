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

"""Reads a spacecraft's flight software out of a built Basilisk simulation.

Nothing is declared twice: :func:`capture` builds the scenario with the
same ``engine.service`` the runs use, stops before
``InitializeSimulation()``, and reads from the Basilisk objects
themselves:

* **Modules.** Every ``Basilisk.fswAlgorithms`` module in the dynamics
  task whose ``ModelTag`` belongs to the spacecraft, in the task's own
  execution order (priority, then insertion). Each must be in
  :data:`.catalog.MODULES`.
* **Parameters.** Every field of the module's configuration struct (from
  its vendored header, :mod:`.cdecl`) with the value Basilisk holds before
  ``InitializeSimulation()``: what ``engine.fsw`` set, or the zero the
  wrapper's constructor gave it.
* **Connections.** An input container's ``payloadPointer`` is the
  address of the payload it reads. It is matched against every module
  output, every message of every other model in the task, or else it is a
  standalone message ``engine.fsw`` wrote once (a constant: vehicle,
  wheel, thruster, torque-rod or sun-sensor configuration).
* **Actuator outputs.** Each simulation reader is asked
  ``isSubscribedTo()`` each module output.

It then adds a recorder at the end of the task, runs ``initialize()``
(``InitializeSimulation()`` and the momentum-dumping priming re-Reset)
and a short run, and keeps, per step, the bytes each module read from the
boundary and every module output. Constants are checked unchanged at
every step.

**Timing equivalence.** In the simulation the flight-software modules
are spread through the task between simulation models. An external
flight software (SIL) runs at one point, where the last module runs. That
gives the same values only if no simulation model between the first and
last module reads a module output, and no model there produces an input a
module before it reads. :func:`capture` checks both and refuses an
export that would differ, naming the models.
"""

from __future__ import annotations

import copy
import ctypes
import platform
import sys
from typing import Dict, List, Tuple

from .. import __version__ as _tool_version
from . import cdecl, sources
from .catalog import BASILISK_REVISION, BASILISK_VERSION, MODULES, NOT_EXPORTED
from .digest import fsw_config_digest
from .model import (Constant, FswCapture, InputLink, MessageType, ModuleInstance, Param, Port, layout_of)
from .traceability import CONSTANT_MESSAGES, module_field_source

DEFAULT_STEPS = 200


class CaptureError(RuntimeError):
    """The spacecraft's flight software cannot be exported as it is."""


def _identifier(text: str) -> str:
    out = "".join(ch if (ch.isascii() and ch.isalnum()) or ch == "_" else "_" for ch in text)
    return out if not out[0].isdigit() else f"m_{out}"


def _payload_type(messaging, message_type: str):
    payload = getattr(messaging, f"{message_type}MsgPayload", None)
    if payload is None:
        raise CaptureError(f"Basilisk has no {message_type}MsgPayload")
    return payload


def _bytes_at(address: int, size: int) -> bytes:
    return ctypes.string_at(address, size)


def _execution_order(task) -> list:
    models = list(task.TaskModels)
    priorities = list(task.TaskModelPriorities)
    indexed = sorted(range(len(models)), key=lambda i: (-priorities[i], i))  # SysModelTask: higher first, then FIFO
    return [models[i] for i in indexed]


def _message_attributes(model, suffixes: Tuple[str, ...]):
    """``(attribute label, message object)`` for each message-like
    attribute whose name ends with one of ``suffixes``; vectors expanded."""
    for name in dir(model):
        if name.startswith("_") or not name.endswith(suffixes):
            continue
        try:
            value = getattr(model, name)
        except Exception:  # noqa: BLE001,S112 -- a SWIG attribute that cannot be read is not a message
            continue
        if hasattr(value, "getPayloadAddress") or hasattr(value, "isSubscribedTo"):
            yield name, value
        else:
            try:
                items = list(value)
            except TypeError:
                continue
            for index, item in enumerate(items):
                if hasattr(item, "getPayloadAddress") or hasattr(item, "isSubscribedTo"):
                    yield f"{name}[{index}]", item


# Element sizes for arrays SWIG hands back as a bare pointer (enum arrays such
# as thrFiringSchmitt's boolean_t lastThrustState[MAX_EFF_CNT]).
_RAW_ELEMENTS = {"boolean_t": "<i4", "int": "<i4", "int32_t": "<i4", "uint32_t": "<u4", "double": "<f8",
                 "uint64_t": "<u8", "int64_t": "<i8"}


def _macros() -> dict:
    found = {}
    for path in ("architecture/utilities/macroDefinitions.h", "fswAlgorithms/fswUtilities/fswDefinitions.h"):
        found.update(cdecl.integer_macros(sources.read_text(path)))
    return found


def _parameter_value(messaging, module, field: cdecl.Field):
    value = getattr(module, field.name)
    if type(value).__name__ == "SwigPyObject":  # an array SWIG gives back as a pointer: read it from memory
        import numpy as np

        kind = _RAW_ELEMENTS.get(field.c_type)
        if kind is None or not field.dims:
            raise CaptureError(f"{module.ModelTag}.{field.name}: cannot read a {field.c_type}{field.dims}")
        shape = cdecl.array_shape(field.dims, _macros())
        count = int(np.prod(shape))
        data = _bytes_at(int(value), count * np.dtype(kind).itemsize)
        values = np.frombuffer(data, dtype=kind).reshape(shape).tolist()
        return values
    if hasattr(value, "this"):  # a struct-typed field (e.g. RWArrayConfigMsgPayload): raw bytes
        type_name = field.c_type[: -len("MsgPayload")] if field.c_type.endswith("MsgPayload") else None
        if type_name is None:
            raise CaptureError(f"{module.ModelTag}.{field.name}: struct type {field.c_type} is not a message payload")
        size = _payload_type(messaging, type_name).__dtype__.itemsize
        return {"bytes": _bytes_at(int(value.this), size).hex(), "message_type": type_name}
    if isinstance(value, (list, tuple)):
        return [list(v) if isinstance(v, (list, tuple)) else v for v in value]
    return value


def capture(scenario, spacecraft_name: str, steps: int = DEFAULT_STEPS) -> FswCapture:
    """Reads ``spacecraft_name``'s flight software and records ``steps``
    flight-software steps. Raises :class:`CaptureError` with the reason
    when it cannot be exported."""
    from Basilisk.architecture import messaging, sysModel
    from Basilisk.utilities import macros

    from ..engine.service import SimulationService

    spacecraft = next((sc for sc in scenario.spacecraft if sc.name == spacecraft_name), None)
    if spacecraft is None:
        raise CaptureError(f"no spacecraft named {spacecraft_name!r} in this scenario")
    if spacecraft.comms_pointing is not None:
        raise CaptureError(f"{spacecraft_name}: comms pointing switches the attitude guidance with a Python module "
                           "(engine.fsw's arbitrator), which cannot be exported as C. Turn comms pointing off to "
                           "export the attitude chain.")
    if scenario.simulation_mode == "orbit_only" or spacecraft.fsw_mode is None:
        raise CaptureError(f"{spacecraft_name} has no attitude flight software (fsw_mode is not set)")
    if steps < 2:
        raise CaptureError("record at least 2 steps")

    run = copy.deepcopy(scenario)
    run.mission_sequence = []
    run.monte_carlo.enabled = False
    dt_s = float(run.sim_settings.dynamics_task_rate_s)  # [s]
    run.sim_settings.duration_days = steps * dt_s / 86400.0  # [day]
    run.sim_settings.record_interval_s = 0.0  # [s]
    service = SimulationService(run)
    service.build(initialize=False)
    task = next(t for t in service.scSim.TaskList if t.Name == service.dyn_task_name)
    rate_ns = int(task.TaskData.TaskPeriod)
    ordered = _execution_order(task)
    position = {id(m): i for i, m in enumerate(ordered)}
    prefix = f"{spacecraft_name}_"

    fsw_models = [m for m in ordered if type(m).__module__.startswith("Basilisk.fswAlgorithms.")
                  and str(getattr(m, "ModelTag", "")).startswith(prefix)]
    if not fsw_models:
        raise CaptureError(f"{spacecraft_name}: no Basilisk flight-software modules were built")
    unknown = sorted({type(m).__module__.rsplit(".", 1)[1] for m in fsw_models} - set(MODULES))
    if unknown:
        raise CaptureError(f"{spacecraft_name}: these modules cannot be exported yet: {', '.join(unknown)}")
    fsw_ids = {id(m) for m in fsw_models}
    sim_models = [m for m in ordered if id(m) not in fsw_ids]
    not_exported = sorted({f"{NOT_EXPORTED[type(m).__name__]} -- {getattr(m, 'ModelTag', '')}"
                           for m in sim_models if type(m).__name__ in NOT_EXPORTED
                           and spacecraft_name in str(getattr(m, "ModelTag", ""))})

    message_types: Dict[str, MessageType] = {}

    def message_type(name: str) -> MessageType:
        if name not in message_types:
            message_types[name] = MessageType(name, layout_of(_payload_type(messaging, name).__dtype__))
        return message_types[name]

    # Every message type the modules' headers include, not only those on a
    # connected field: the generated C interface covers them all.
    from .generate import source_closure

    for type_name in source_closure(sorted({type(m).__module__.rsplit(".", 1)[1] for m in fsw_models}))[1]:
        message_type(type_name)

    names = {}
    for m in fsw_models:
        name = _identifier(m.ModelTag[len(prefix):])
        if name in names.values():
            raise CaptureError(f"two modules would both be called {name}")
        names[id(m)] = name

    # Module outputs, by payload address.
    struct_fields: Dict[int, List[cdecl.Field]] = {}
    output_at: Dict[int, Tuple[object, str, str]] = {}
    for m in fsw_models:
        entry = MODULES[type(m).__module__.rsplit(".", 1)[1]]
        struct_fields[id(m)] = cdecl.parse_struct(sources.read_text(entry.header), entry.config_struct)
        for f in struct_fields[id(m)]:
            if f.is_output:
                output_at[int(getattr(m, f.name).payload.this)] = (m, f.name, f.message_type)

    # Messages of every other model, by payload address.
    sim_message_at: Dict[int, Tuple[object, str]] = {}
    for m in sim_models:
        for label, msg in _message_attributes(m, ("OutMsg", "OutMsgs", "Msg")):
            if hasattr(msg, "getPayloadAddress"):
                sim_message_at[int(msg.getPayloadAddress())] = (m, label)

    modules: List[ModuleInstance] = []
    inputs: Dict[int, Port] = {}
    input_read_from: Dict[str, Tuple[int, int]] = {}  # port -> (consumer local payload address, size)
    input_container: Dict[str, object] = {}  # port -> its first consumer's input container
    constants: Dict[int, Constant] = {}
    reads: List[Tuple[str, int, int]] = []  # ("<module>.<field>", local payload address, size)
    for m in fsw_models:
        python_name = type(m).__module__.rsplit(".", 1)[1]
        instance = ModuleInstance(tag=m.ModelTag, name=names[id(m)], python_name=python_name,
                                  module_id=int(m.moduleID))
        for f in struct_fields[id(m)]:
            if f.is_message:
                container = getattr(m, f.name)
                mtype = message_type(f.message_type)
                if f.is_output:
                    instance.outputs.append({"field": f.name, "message_type": f.message_type})
                    continue
                if not f.is_input:
                    raise CaptureError(f"{m.ModelTag}.{f.name}: cannot tell whether this message is an input")
                if not container.header.isLinked:
                    instance.inputs.append(InputLink(f.name, f.message_type, "unlinked"))
                    continue
                address = int(container.payloadPointer.this)
                local = int(container.payload.this)
                reads.append((f"{instance.name}.{f.name}", local, mtype.size))
                if address in output_at:
                    producer, field_name, _ = output_at[address]
                    instance.inputs.append(InputLink(f.name, f.message_type, "module",
                                                     f"{names[id(producer)]}.{field_name}"))
                elif address in sim_message_at:
                    producer, label = sim_message_at[address]
                    port = inputs.get(address)
                    if port is None:
                        tag = str(getattr(producer, "ModelTag", type(producer).__name__))
                        short = tag[len(prefix):] if tag.startswith(prefix) else tag
                        port = Port(_identifier(f"{short}_{label}".replace("[", "_").replace("]", "")),
                                    f.message_type, f"{tag}.{label} ({type(producer).__name__})")
                        inputs[address] = port
                        input_read_from[port.name] = (local, mtype.size)
                        input_container[port.name] = (container, address, mtype.size)
                    port.consumers.append(f"{instance.name}.{f.name}")
                    instance.inputs.append(InputLink(f.name, f.message_type, "input", port.name))
                else:
                    constant = constants.get(address)
                    if constant is None:
                        source = CONSTANT_MESSAGES.get(f.message_type)
                        constant = Constant(_identifier(f"{f.message_type}_config"), f.message_type,
                                            _bytes_at(address, mtype.size).hex(),
                                            scenario_path=source.scenario_path if source else None,
                                            gui=source.gui if source else "-", note=source.note if source else "")
                        if any(c.name == constant.name for c in constants.values()):
                            constant.name = _identifier(f"{f.message_type}_config_{len(constants)}")
                        constants[address] = constant
                    constant.consumers.append(f"{instance.name}.{f.name}")
                    instance.inputs.append(InputLink(f.name, f.message_type, "constant", constant.name))
            elif f.pointer:
                if f.c_type != "BSKLogger":
                    raise CaptureError(f"{m.ModelTag}.{f.name}: pointer field of type {f.c_type}")
            else:
                source = module_field_source(python_name, f.name)
                instance.params.append(Param(
                    f.name, f.c_type, f.dims, f.unit, f.description, _parameter_value(messaging, m, f),
                    scenario_path=source.scenario_path if source else None,
                    gui=source.gui if source else "-", note=source.note if source else ""))
        modules.append(instance)

    # Outputs read by the simulation, and the timing-equivalence check.
    outputs: Dict[str, Port] = {}
    first, last = position[id(fsw_models[0])], position[id(fsw_models[-1])]
    problems = []
    for m in sim_models:
        for label, reader in _message_attributes(m, ("InMsg", "InMsgs")):
            if not hasattr(reader, "isSubscribedTo"):
                continue
            for address, (producer, field_name, mtype_name) in output_at.items():
                try:
                    linked = bool(reader.isSubscribedTo(getattr(producer, field_name)))
                except (TypeError, NotImplementedError, AttributeError):
                    continue
                if not linked:
                    continue
                key = f"{names[id(producer)]}.{field_name}"
                port = outputs.setdefault(key, Port(_identifier(key.replace(".", "_")), mtype_name, key))
                port.consumers.append(f"{getattr(m, 'ModelTag', type(m).__name__)}.{label}")
                if position[id(producer)] < position[id(m)] < last:
                    problems.append(f"{getattr(m, 'ModelTag', '')} reads {key} between the flight-software modules")
    for address, port in inputs.items():
        producer = sim_message_at[address][0]
        consumers = [next(x for x in fsw_models if names[id(x)] == c.split(".")[0]) for c in port.consumers]
        if any(position[id(c)] < position[id(producer)] < last for c in consumers):
            problems.append(f"{port.producer} is written between the flight-software modules that read it")
    if problems:
        raise CaptureError("the flight software would see different values outside the simulation: "
                           + "; ".join(problems))
    del first

    telemetry = [Port(_identifier(f"{names[id(p)]}_{fname}"), mtype, f"{names[id(p)]}.{fname}")
                 for p, fname, mtype in output_at.values() if f"{names[id(p)]}.{fname}" not in outputs]
    priming = [names[id(m)] for m in service._desat_controls if id(m) in fsw_ids]

    # Record the run.
    output_sizes = {f"{names[id(p)]}.{fname}": (address, message_types[mtype].size)
                    for address, (p, fname, mtype) in output_at.items()}
    recorded = {"times": [], "inputs": [], "outputs": [], "constants_changed": set(), "step0": {},
                "reset_inputs": {}, "reset_outputs": {}}
    output_container = {f"{names[id(p)]}.{fname}": getattr(p, fname) for p, fname, _ in output_at.values()}
    constant_bytes = {address: bytes.fromhex(c.value_hex) for address, c in constants.items()}

    class _Recorder(sysModel.SysModel):
        def Reset(self, CurrentSimNanos):  # noqa: N802,N803 -- Basilisk's names; runs after every other Reset
            if recorded["times"]:
                return
            for port, (container, address, size) in input_container.items():
                written = bool(container.headerPointer.isWritten)
                recorded["reset_inputs"][port] = _bytes_at(address, size).hex() if written else None
            for key, (address, size) in output_sizes.items():
                written = bool(output_container[key].header.isWritten)
                recorded["reset_outputs"][key] = _bytes_at(address, size).hex() if written else None

        def UpdateState(self, CurrentSimNanos):  # noqa: N802,N803 -- Basilisk's names
            recorded["times"].append(int(CurrentSimNanos))
            recorded["inputs"].append({port: _bytes_at(a, s).hex() for port, (a, s) in input_read_from.items()})
            recorded["outputs"].append({key: _bytes_at(a, s).hex() for key, (a, s) in output_sizes.items()})
            for address, value in constant_bytes.items():
                if _bytes_at(address, len(value)) != value:
                    recorded["constants_changed"].add(constants[address].name)
            if len(recorded["times"]) == 1:
                recorded["step0"] = {key: _bytes_at(a, s).hex() for key, a, s in reads}

    recorder = _Recorder()
    recorder.ModelTag = "fswExportRecorder"
    service.scSim.AddModelToTask(service.dyn_task_name, recorder)
    service.initialize()
    service.scSim.ConfigureStopTime(macros.sec2nano((steps - 1) * dt_s))
    service.scSim.ExecuteSimulation()
    if recorded["constants_changed"]:
        raise CaptureError(f"configuration messages changed during the run: {sorted(recorded['constants_changed'])}")
    if len(recorded["times"]) != steps:
        raise CaptureError(f"recorded {len(recorded['times'])} steps, expected {steps}")

    return FswCapture(
        spacecraft=spacecraft_name, scenario_name=scenario.name, basilisk_version=BASILISK_VERSION,
        basilisk_revision=BASILISK_REVISION, rate_ns=rate_ns, modules=modules, message_types=message_types,
        inputs=list(inputs.values()), outputs=list(outputs.values()), telemetry=telemetry,
        constants=list(constants.values()), priming_resets=priming,
        priming_time_ns=int(macros.sec2nano(dt_s)) if priming else 0, not_exported=not_exported,
        config_digest=fsw_config_digest(scenario, spacecraft_name),
        times_ns=recorded["times"], input_trace=recorded["inputs"], output_trace=recorded["outputs"],
        step0_reads=recorded["step0"], reset_inputs=recorded["reset_inputs"],
        reset_outputs=recorded["reset_outputs"],
        exported_with={"spacemissionstudio": _tool_version, "python": sys.version.split()[0],
                       "platform": f"{platform.system()} {platform.machine()}"},
    )
