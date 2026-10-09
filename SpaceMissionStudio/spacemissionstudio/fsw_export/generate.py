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

"""Writes the standalone C project for a :class:`.model.FswCapture`.

No Basilisk needed: the module sources come from the vendored, checked
Basilisk files (:mod:`.sources`), the C message interface is generated
from Basilisk's own templates (``msg_C.h.in``/``msg_C.cpp.in``, keeping
only their C-to-C functions), and every value comes from the capture.

Layout of an export::

    CMakeLists.txt  README.md  ICD.md  TRACEABILITY.md  manifest.json
    basilisk/         the Basilisk sources the modules need, unchanged, and Basilisk's LICENSE
    generated/        cMsgCInterface/, fsw_config.[ch], fsw_scheduler.c, fsw_ports.c, fsw_layout_check.c, ...
    host/fsw_host.c   info, replay and sil (the SIL harness, SIL_CONTRACT.md)
    adapter/          the SIL adapter template for flight software of your own (ADAPTER_GUIDE.md)
    tests/            one unit test per module; data/ the recorded replay traces
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import cdecl, sources
from .catalog import MODULES
from .digest import EXPORT_FORMAT_VERSION
from .model import FswCapture, Port, decode
from .model import leaves as _leaves

_TEMPLATES = Path(__file__).resolve().parent / "templates"
_STATIC_GENERATED = ("fsw_log.c", "fsw_log.h", "fsw_ports.h", "fsw_compare.c", "fsw_trace.c", "fsw_trace.h",
                     "fsw_scheduler.h", "fsw_sil.c", "fsw_sil.h", "fsw_transport.h", "fsw_transport_socket.c")
_STATIC_DOCUMENTS = ("SIL_CONTRACT.md", "ADAPTER_GUIDE.md")
_INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)
_STANDARD_HEADERS = {"math.h", "string.h", "stdio.h", "stdlib.h", "stdint.h", "stddef.h", "float.h", "limits.h"}
# The C-to-C half of Basilisk's C message interface template.
_C_FUNCTIONS = ("C_subscribe", "C_isSubscribedTo", "C_addAuthor", "C_init", "C_write", "C_zeroMsgPayload", "C_read",
                "C_isLinked", "C_isWritten", "C_timeWritten", "C_moduleID")
_LEAF_KINDS = {"<f8": "FSW_LEAF_F64", "<f4": "FSW_LEAF_F32", "|i1": "FSW_LEAF_I8", "|u1": "FSW_LEAF_U8",
               "<i2": "FSW_LEAF_I16", "<u2": "FSW_LEAF_U16", "<i4": "FSW_LEAF_I32", "<u4": "FSW_LEAF_U32",
               "<i8": "FSW_LEAF_I64", "<u8": "FSW_LEAF_U64"}
_LEAF_SIZES = {"<f8": 8, "<f4": 4, "|i1": 1, "|u1": 1, "<i2": 2, "<u2": 2, "<i4": 4, "<u4": 4, "<i8": 8, "<u8": 8}


class ExportError(RuntimeError):
    """The export cannot be written."""


@dataclass
class ExportResult:
    directory: Path
    files: List[str] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


def _isc_c() -> str:
    return (_TEMPLATES / "_isc_c.txt").read_text()


def _comment(text) -> str:
    """User text (scenario and spacecraft names) made safe inside a C ``/* */``
    or a CMake ``#`` comment: one line, printable ASCII, no comment delimiters.
    A shared scenario must never be able to put code into the export."""
    clean = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in str(text))
    while "*/" in clean or "/*" in clean:
        clean = clean.replace("*/", "* /").replace("/*", "/ *")
    return clean


def _c_string(text) -> str:
    """User text as the contents of a C string literal: printable ASCII as is,
    everything else (quotes, backslashes, newlines, ``?`` against trigraphs,
    UTF-8 bytes) as octal escapes."""
    out = []
    for byte in str(text).encode("utf-8"):
        ch = chr(byte)
        out.append(ch if 32 <= byte < 127 and ch not in "\\\"?" else f"\\{byte:03o}")
    return "".join(out)


# ----------------------------------------------------------------------------- C literals


def _c_number(kind: str, value) -> str:
    if kind in ("<f8", "<f4") or isinstance(value, float):
        value = float(value)
        if math.isnan(value):
            return "NAN"
        if math.isinf(value):
            return "INFINITY" if value > 0 else "-INFINITY"
        text = repr(value)
        return text if any(ch in text for ch in ".eE") else text + ".0"
    value = int(value)
    if kind == "<u8":
        return f"{value}ULL"
    if kind == "<i8":
        return f"{value}LL" if value >= 0 else f"({value + 1}LL - 1)"
    if kind == "<u4":
        return f"{value}U"
    return str(value)


def _is_zero(value) -> bool:
    if isinstance(value, dict):
        return all(_is_zero(v) for v in value.values())
    if isinstance(value, list):
        return all(_is_zero(v) for v in value)
    return value == 0 and not (isinstance(value, float) and math.copysign(1.0, value) < 0)


def _c_array(entry: dict, values: list, depth: int) -> str:
    """Nested braces for an array field, trailing zero elements left out."""
    items = list(values)
    while items and _is_zero(items[-1]):
        items.pop()
    if not items:
        return "{0}"
    inner = []
    for item in items:
        if isinstance(item, list):
            inner.append(_c_array(entry, item, depth + 1))
        elif isinstance(item, dict):
            inner.append(_c_struct(entry["struct"], item))
        else:
            inner.append(_c_number(entry["kind"], item))
    return "{" + ", ".join(inner) + "}"


def _c_struct(layout: dict, value: dict) -> str:
    """A designated initializer for a payload (zero fields left out)."""
    parts = []
    for entry in layout["fields"]:
        v = value[entry["name"]]
        if _is_zero(v):
            continue
        if entry["shape"]:
            parts.append(f".{entry['name']} = {_c_array(entry, v, 0)}")
        elif "struct" in entry:
            parts.append(f".{entry['name']} = {_c_struct(entry['struct'], v)}")
        else:
            parts.append(f".{entry['name']} = {_c_number(entry['kind'], v)}")
    return "{" + ", ".join(parts) + "}" if parts else "{0}"


def _wrap(text: str, indent: str = "    ", width: int = 116) -> str:
    """Breaks a long initializer after commas, for reading."""
    if len(text) <= width:
        return text
    lines, line = [], ""
    for piece in re.split(r"(?<=,) ", text):
        if line and len(line) + len(piece) + 1 > width:
            lines.append(line)
            line = indent + piece
        else:
            line = f"{line} {piece}" if line else piece
    lines.append(line)
    return "\n".join(lines)


# ----------------------------------------------------------------------------- sources


def source_closure(module_names: List[str]) -> Tuple[List[str], List[str]]:
    vendored = set(sources.paths())
    wanted, types = set(), set()
    todo = []
    for name in module_names:
        entry = MODULES[name]
        todo += [entry.header, entry.source]
    while todo:
        path = todo.pop()
        if path in wanted:
            continue
        wanted.add(path)
        for include in _INCLUDE.findall(sources.read_text(path)):
            generated = re.match(r"cMsgCInterface/(\w+)Msg_C\.h$", include)
            if generated:
                types.add(generated.group(1))
                todo.append(f"architecture/msgPayloadDefC/{generated.group(1)}MsgPayload.h")
                continue
            for candidate in (include, f"{path.rsplit('/', 1)[0]}/{include}"):
                if candidate in vendored:
                    todo.append(candidate)
                    companion = candidate.rsplit(".", 1)[0] + ".c"
                    if candidate.endswith(".h") and companion in vendored:
                        todo.append(companion)
                    break
            else:
                if include not in _STANDARD_HEADERS:
                    raise ExportError(f"{path}: #include \"{include}\" is not among the vendored sources")
    for extra in ("architecture/messaging/msgHeader.h", "architecture/utilities/bsk_Print.h",
                  "architecture/utilities/bskLogging.h"):
        wanted.add(extra)
    return sorted(wanted), sorted(types)


def _message_interface(type_name: str) -> Tuple[str, str]:
    """``<Type>Msg_C.h`` and ``.c`` from Basilisk's templates, C-to-C functions only."""
    licence = ("Generated by SpaceMissionStudio from Basilisk's architecture/messaging/cMsgCInterface/msg_C.h.in "
               "and msg_C.cpp.in (ISC licence, basilisk/LICENSE), as Basilisk's CMake fills them in, keeping the "
               "C-to-C functions; the C++ and address-based subscribe helpers are left out.")
    header = sources.read_text("architecture/messaging/cMsgCInterface/msg_C.h.in")
    header = header.replace("@MSG_AUTOSOURCE_LICENSE@", licence)
    header = header.replace("@MSG_AUTOSOURCE_HEADER@", f"architecture/msgPayloadDefC/{type_name}MsgPayload.h")
    header = header.replace("@MSG_AUTOSOURCE_TYPE@", f"{type_name}Msg")
    kept = []
    for line in header.splitlines():
        if re.search(rf"\b{type_name}Msg_(cpp_\w+|addr_\w+|unsubscribe)\s*\(", line):
            continue
        kept.append(line)
    header = "\n".join(kept) + "\n"

    template = sources.read_text("architecture/messaging/cMsgCInterface/msg_C.cpp.in")
    template = template.replace("@MSG_AUTOSOURCE_LICENSE@", licence).replace("@MSG_AUTOSOURCE_TYPE@",
                                                                              f"{type_name}Msg")
    template = template.replace('#include "architecture/messaging/messaging.h"\n', "")
    template = template.replace(f'#include "{type_name}Msg_C.h"', f'#include "cMsgCInterface/{type_name}Msg_C.h"')
    # Split into the preamble and one block per function (a //! comment, then the definition).
    blocks = re.split(r"\n(?=//!)", template)
    body = [blocks[0]]
    for block in blocks[1:]:
        found = re.search(rf"\b{type_name}Msg_(\w+)\s*\(", block)
        if found and found.group(1) in _C_FUNCTIONS:
            body.append(block)
    source = "\n".join(body).rstrip() + "\n"
    for name in _C_FUNCTIONS:
        if f"{type_name}Msg_{name}(" not in source:
            raise ExportError(f"Basilisk's msg_C.cpp.in has no {name} for {type_name}")
    return header, source


# ----------------------------------------------------------------------------- generation


@dataclass
class _Context:
    capture: FswCapture
    out: Path
    files: Dict[str, bytes] = field(default_factory=dict)
    config_lines: Dict[str, int] = field(default_factory=dict)  # "<module>.<field>" -> line in fsw_config.c
    config_marks: Dict[str, int] = field(default_factory=dict)  # the same, as an index into the list of chunks

    def write(self, relative: str, content) -> None:
        data = content.encode() if isinstance(content, str) else content
        self.files[relative] = data


def _plain_number_tree(value) -> bool:
    if isinstance(value, list):
        return all(_plain_number_tree(v) for v in value)
    return isinstance(value, (int, float)) and not isinstance(value, bool) or isinstance(value, bool)


def _param_statements(ctx: _Context, module, lines: List[str]) -> None:
    """``config->field = ...;`` for each parameter, with its provenance."""
    for param in module.params:
        if not (isinstance(param.value, dict) and "bytes" in param.value) and not _plain_number_tree(param.value):
            raise ExportError(f"{module.name}.{param.name}: the captured value {param.value!r:.60} is not a number")
        where = f" -- {param.scenario_path}" if param.scenario_path else ""
        gui = f" ({param.gui})" if param.gui != "-" else ""
        note = f"; {param.note}" if param.note else ""
        unit = f"[{param.unit}] " if param.unit else ""
        lines.append(f"    /* {param.name}: {_comment(unit + param.description + where + gui + note)} */")
        first = len(lines)
        value = param.value
        if isinstance(value, dict) and "bytes" in value:
            layout = ctx.capture.message_types[value["message_type"]].layout if value["message_type"] in \
                ctx.capture.message_types else None
            if layout is None:
                raise ExportError(f"{module.name}.{param.name}: no layout for {value['message_type']}")
            decoded = decode(layout, bytes.fromhex(value["bytes"]))
            if _is_zero(decoded):
                lines.append(f"    memset(&config->{param.name}, 0, sizeof config->{param.name});")
            else:
                lines.append(f"    {{ static const {param.c_type} value = {_wrap(_c_struct(layout, decoded))};")
                lines.append(f"      config->{param.name} = value; }}")
        elif param.dims:
            kind = "<f8" if param.c_type in ("double",) else ("<u8" if param.c_type == "uint64_t" else
                                                               "<u4" if param.c_type == "uint32_t" else "<i4")
            literal = _c_array({"kind": kind}, value if isinstance(value, list) else [value], 0)
            lines.append(f"    {{ static const {param.c_type} value{param.dims} = {_wrap(literal)};")
            lines.append(f"      memcpy(config->{param.name}, value, sizeof value); }}")
        else:
            kind = "<f8" if param.c_type in ("double", "float") else ("<u8" if param.c_type == "uint64_t" else
                                                                     "<i8" if param.c_type == "int64_t" else "<i4")
            lines.append(f"    config->{param.name} = {_c_number(kind, value)};")
        # The traceability table points at the line that sets the field.
        ctx.config_marks[f"{module.name}.{param.name}"] = next(
            i for i in range(first, len(lines)) if f"config->{param.name}" in lines[i])


def _generate_config(ctx: _Context, header_includes: List[str]) -> None:
    cap = ctx.capture
    h = [_isc_c(), "", f"/* Flight software of {_comment(cap.spacecraft)}: module instances, ports and constants.",
         f" * Generated by SpaceMissionStudio from scenario \"{_comment(cap.scenario_name)}\"; do not edit by hand, re-export. */",
         "", "#ifndef FSW_CONFIG_H", "#define FSW_CONFIG_H", "", "#include <stdint.h>", ""]
    h += [f'#include "{inc}"' for inc in header_includes]
    h += ["", "/*! @brief Every module's configuration, in execution order. */", "typedef struct {"]
    for m in cap.modules:
        h.append(f"    {MODULES[m.python_name].config_struct} {m.name}; /*!< {_comment(m.tag)} (Basilisk {m.python_name}) */")
    h += ["} FswModules;", "", "/*! @brief The input ports: what the flight software reads from outside. */",
          "typedef struct {"]
    h += [f"    {p.message_type}Msg_C {p.name}; /*!< from {_comment(p.producer)} */" for p in cap.inputs] or ["    int unused;"]
    h += ["} FswInputs;", "", "/*! @brief The fixed configuration messages. */", "typedef struct {"]
    h += [f"    {c.message_type}Msg_C {c.name}; /*!< read by {_comment(', '.join(c.consumers))} */"
          for c in cap.constants] or ["    int unused;"]
    h += ["} FswConstants;", "", "extern FswModules fsw_modules;", "extern FswInputs fsw_inputs;",
          "extern FswConstants fsw_constants;", ""]
    for c in cap.constants:
        h.append(f"/*! @brief The value of {c.name}. */")
        h.append(f"extern const {c.message_type}MsgPayload fsw_constant_{c.name};")
    h.append("")
    for m in cap.modules:
        h += ["/*!", f" * @brief Sets every field of {m.name}'s configuration to its exported value.",
              " * @param config the configuration to set", " */",
              f"void fsw_set_parameters_{m.name}({MODULES[m.python_name].config_struct} *config);"]
    h += ["", "/*! @brief Initialises the input and constant containers and writes the constants. */",
          "void fsw_write_constants(void);", "", "/*! @brief Connects every module input to its source. */",
          "void fsw_connect(void);", "", "#endif", ""]
    ctx.write("generated/fsw_config.h", "\n".join(h))

    c = [_isc_c(), "", f"/* Flight software of {_comment(cap.spacecraft)}: every exported value, with where it comes from.",
         f" * Scenario \"{_comment(cap.scenario_name)}\", Basilisk {cap.basilisk_version} ({cap.basilisk_revision[:9]}).",
         " * Generated by SpaceMissionStudio; do not edit by hand, re-export (TRACEABILITY.md). */", "",
         "#include <math.h>", "#include <string.h>", "", '#include "fsw_config.h"', "",
         "FswModules fsw_modules;", "FswInputs fsw_inputs;", "FswConstants fsw_constants;", ""]
    for const in cap.constants:
        layout = cap.message_types[const.message_type].layout
        where = f" -- {const.scenario_path}" if const.scenario_path else ""
        gui = f" ({const.gui})" if const.gui != "-" else ""
        note = f"; {const.note}" if const.note else ""
        c.append(f"/* {const.name}{_comment(where + gui + note)} */")
        ctx.config_marks[f"constant.{const.name}"] = len(c)
        value = _c_struct(layout, decode(layout, bytes.fromhex(const.value_hex)))
        c.append(_wrap(f"const {const.message_type}MsgPayload fsw_constant_{const.name} = {value};"))
        c.append("")
    for m in cap.modules:
        c.append(f"void fsw_set_parameters_{m.name}({MODULES[m.python_name].config_struct} *config)")
        c.append("{")
        c.append("    memset(config, 0, sizeof *config);")
        _param_statements(ctx, m, c)
        c += ["}", ""]
    c += ["void fsw_write_constants(void)", "{"]
    for p in cap.inputs:
        c.append(f"    {p.message_type}Msg_C_init(&fsw_inputs.{p.name});")
    for const in cap.constants:
        c.append(f"    {const.message_type}Msg_C_init(&fsw_constants.{const.name});")
        c.append(f"    {{ {const.message_type}MsgPayload value = fsw_constant_{const.name};")
        c.append(f"      {const.message_type}Msg_C_write(&value, &fsw_constants.{const.name}, 0, 0); }}")
    c += ["}", "", "void fsw_connect(void)", "{"]
    for m in cap.modules:
        for link in m.inputs:
            target = f"&fsw_modules.{m.name}.{link.field}"
            if link.kind == "module":
                producer, out_field = link.ref.split(".")
                c.append(f"    {link.message_type}Msg_C_subscribe({target}, &fsw_modules.{producer}.{out_field});")
            elif link.kind == "input":
                c.append(f"    {link.message_type}Msg_C_subscribe({target}, &fsw_inputs.{link.ref});")
            elif link.kind == "constant":
                c.append(f"    {link.message_type}Msg_C_subscribe({target}, &fsw_constants.{link.ref});")
    c += ["}", ""]
    # Chunks may hold several lines (the licence, wrapped initializers): number lines in the joined text.
    starts, line = [], 1
    for chunk in c:
        starts.append(line)
        line += chunk.count("\n") + 1
    ctx.config_lines = {key: starts[index] for key, index in ctx.config_marks.items()}
    ctx.write("generated/fsw_config.c", "\n".join(c))


def _generate_scheduler(ctx: _Context) -> None:
    cap = ctx.capture
    s = [_isc_c(), "", f"/* Running the flight software of {_comment(cap.spacecraft)} (fsw_scheduler.h).",
         " * One rate group: Basilisk ran these modules in one task, every step, in this order. */", "",
         "#include <string.h>", "", '#include "fsw_config.h"', '#include "fsw_scheduler.h"', "",
         f"const uint64_t fsw_rate_ns = {cap.rate_ns}ULL;"]
    if cap.priming_resets:
        s += ["", "/* SpaceMissionStudio re-Resets these modules once, after the step at this time, so that",
              " * momentum management starts from real wheel speeds (engine.service.SimulationService.initialize). */",
              f"static const uint64_t primingTimeNs = {cap.priming_time_ns}ULL;", "static int primed = 0;"]
    s += ["", "void fsw_init(void)", "{", "    memset(&fsw_modules, 0, sizeof fsw_modules);",
          "    memset(&fsw_inputs, 0, sizeof fsw_inputs);", "    memset(&fsw_constants, 0, sizeof fsw_constants);"]
    for m in cap.modules:
        s.append(f"    fsw_set_parameters_{m.name}(&fsw_modules.{m.name});")
    for m in cap.modules:
        s.append(f"    SelfInit_{MODULES[m.python_name].function_suffix}(&fsw_modules.{m.name}, {m.module_id});")
    s += ["    fsw_write_constants();", "    fsw_connect();", "}", "", "void fsw_reset(uint64_t timeNs)", "{"]
    for m in cap.modules:
        s.append(f"    Reset_{MODULES[m.python_name].function_suffix}(&fsw_modules.{m.name}, timeNs, {m.module_id});")
    if cap.priming_resets:
        s.append("    primed = 0;")
    s += ["}", "", "static void rateGroup0(uint64_t timeNs)", "{"]
    for m in cap.modules:
        s.append(f"    Update_{MODULES[m.python_name].function_suffix}(&fsw_modules.{m.name}, timeNs, {m.module_id});")
    s += ["}", "", "void fsw_step(uint64_t timeNs)", "{", "    rateGroup0(timeNs);"]
    if cap.priming_resets:
        s += ["    if (!primed && timeNs >= primingTimeNs) {"]
        for name in cap.priming_resets:
            m = cap.module(name)
            s.append(f"        Reset_{MODULES[m.python_name].function_suffix}(&fsw_modules.{m.name}, timeNs, "
                     f"{m.module_id});")
        s += ["        primed = 1;", "    }"]
    s += ["}", ""]
    ctx.write("generated/fsw_scheduler.c", "\n".join(s))


def _output_container(port: Port) -> str:
    module, out_field = port.producer.split(".")
    return f"fsw_modules.{module}.{out_field}"


def _generate_ports(ctx: _Context, types: List[str]) -> None:
    cap = ctx.capture
    p = [_isc_c(), "", f"/* The ports of {_comment(cap.spacecraft)}'s flight software (fsw_ports.h). Generated. */", "",
         "#include <string.h>", "", '#include "fsw_config.h"', '#include "fsw_ports.h"', '#include "fsw_leaves.h"', "",
         f'const char fsw_config_digest[] = "{cap.config_digest}";',
         f'const char fsw_spacecraft_name[] = "{_c_string(cap.spacecraft)}";', ""]
    leaves_h = [_isc_c(), "", "/* Each payload type's scalar runs, for comparing payloads (fsw_leaves.c). Generated. */",
                "", "#ifndef FSW_LEAVES_H", "#define FSW_LEAVES_H", "", '#include "fsw_ports.h"', ""]
    leaves_c = [_isc_c(), "", "/* Each payload type's scalar runs, from the layouts the simulation recorded. Generated. */",
                "", '#include "fsw_leaves.h"', ""]
    for t in types:
        layout = cap.message_types[t].layout
        runs = _leaves(layout)
        leaves_h += [f"extern const FswLeaf fsw_leaves_{t}[];", f"extern const uint32_t fsw_leaf_count_{t};"]
        leaves_c.append(f"const FswLeaf fsw_leaves_{t}[] = {{")
        leaves_c += [f'    {{{off}, {count}, {_LEAF_KINDS[kind]}, "{name}"}},' for off, count, kind, name in runs]
        leaves_c += ["};", f"const uint32_t fsw_leaf_count_{t} = {len(runs)};", ""]
    leaves_h += ["", "#endif", ""]
    ctx.write("generated/fsw_leaves.h", "\n".join(leaves_h))
    ctx.write("generated/fsw_leaves.c", "\n".join(leaves_c))
    for port in cap.inputs:
        p += [f"static void write_{port.name}(const void *payload, uint64_t timeNs)", "{",
              f"    {port.message_type}MsgPayload value;", "    memcpy(&value, payload, sizeof value);",
              f"    {port.message_type}Msg_C_write(&value, &fsw_inputs.{port.name}, 0, timeNs);", "}", ""]
    for port in cap.outputs + cap.telemetry:
        p += [f"static int read_{port.name}(void *payload)", "{",
              f"    memcpy(payload, FSW_OUTPUT_PAYLOAD({_output_container(port)}), sizeof({port.message_type}MsgPayload));",
              "    return 1;", "}", ""]

    _port_tables(cap, p)
    ctx.write("generated/fsw_ports.c", "\n".join(p))


def _port_tables(cap: FswCapture, p: List[str]) -> None:
    """The ``fsw_*_ports`` tables, with ``write_<port>``/``read_<port>`` glue
    defined before them."""

    def table(name: str, ports: List[Port], is_input: bool) -> None:
        if not ports:
            p.extend([f"const FswPort {name}[1] = {{{{0}}}};", f"const size_t {name[:-6]}_port_count = 0;", ""])
            return
        p.append(f"const FswPort {name}[] = {{")
        for port in ports:
            mtype = cap.message_types[port.message_type]
            access = f"write_{port.name}, NULL" if is_input else f"NULL, read_{port.name}"
            p.append(f'    {{"{port.name}", "{port.message_type}", {mtype.size}, "{mtype.hash}", '
                     f"fsw_leaves_{port.message_type}, {len(_leaves(mtype.layout))}, {access}}},")
        p.extend(["};", f"const size_t {name[:-6]}_port_count = {len(ports)};", ""])

    table("fsw_input_ports", cap.inputs, True)
    table("fsw_output_ports", cap.outputs, False)
    table("fsw_telemetry_ports", cap.telemetry, False)


def _adapter_struct(name: str, ports: List[Port], doc: str, flags: bool) -> List[str]:
    lines = [f"/*! @brief {doc} */", "typedef struct {"]
    for port in ports:
        lines.append(f"    uint8_t {port.name};" if flags else f"    {port.message_type}MsgPayload {port.name};")
    if not ports:
        lines.append("    int unused; /*!< no ports of this kind */")
    return lines + [f"}} {name};", ""]


def _generate_adapter(ctx: _Context) -> None:
    """``adapter/``: the same ports as the export, backed by plain payload
    structs, for flight software of your own (ADAPTER_GUIDE.md)."""
    cap = ctx.capture
    types = sorted({p.message_type for p in cap.inputs + cap.outputs + cap.telemetry}
                   | {c.message_type for c in cap.constants})
    h = [_isc_c(), "", f"/* SIL adapter for {_comment(cap.spacecraft)}'s ports: plain payload structs your flight software",
         " * reads and writes (ADAPTER_GUIDE.md). Generated with the export; re-export rather than edit. */", "",
         "#ifndef FSW_ADAPTER_H", "#define FSW_ADAPTER_H", "", "#include <stdint.h>", ""]
    h += [f'#include "architecture/msgPayloadDefC/{t}MsgPayload.h"' for t in types] + [""]
    h += _adapter_struct("FswAdapterInputs", cap.inputs, "The inputs, as last written by the simulation.", False)
    h += _adapter_struct("FswAdapterInputFlags", cap.inputs, "1 for each input the simulation has written.", True)
    h += _adapter_struct("FswAdapterOutputs", cap.outputs, "The actuator commands your flight software sets.", False)
    h += _adapter_struct("FswAdapterOutputFlags", cap.outputs, "Set to 1 for each command you set.", True)
    h += _adapter_struct("FswAdapterTelemetry", cap.telemetry,
                         "Telemetry compared with the simulation's own modules (optional).", False)
    h += _adapter_struct("FswAdapterTelemetryFlags", cap.telemetry, "Set to 1 for each telemetry value you set.", True)
    h += ["extern FswAdapterInputs fsw_adapter_inputs;", "extern FswAdapterInputFlags fsw_adapter_inputs_written;",
          "extern FswAdapterOutputs fsw_adapter_outputs;", "extern FswAdapterOutputFlags fsw_adapter_outputs_written;",
          "extern FswAdapterTelemetry fsw_adapter_telemetry;",
          "extern FswAdapterTelemetryFlags fsw_adapter_telemetry_written;", ""]
    for const in cap.constants:
        h += [f"/*! @brief {const.name}: the configuration the exported modules use (read by "
              f"{_comment(', '.join(const.consumers))}). */",
              f"extern const {const.message_type}MsgPayload fsw_adapter_constant_{const.name};"]
    h += ["", "/*! @brief Zeroes every input, output and telemetry payload and flag. */",
          "void fsw_adapter_clear(void);", "", "#endif", ""]
    ctx.write("adapter/fsw_adapter.h", "\n".join(h))

    c = [_isc_c(), "", f"/* SIL adapter port glue for {_comment(cap.spacecraft)} (fsw_adapter.h). Generated with the export. */",
         "", "#include <string.h>", "", '#include "fsw_adapter.h"', '#include "fsw_leaves.h"', '#include "fsw_ports.h"', "",
         "FswAdapterInputs fsw_adapter_inputs;", "FswAdapterInputFlags fsw_adapter_inputs_written;",
         "FswAdapterOutputs fsw_adapter_outputs;", "FswAdapterOutputFlags fsw_adapter_outputs_written;",
         "FswAdapterTelemetry fsw_adapter_telemetry;", "FswAdapterTelemetryFlags fsw_adapter_telemetry_written;", ""]
    for const in cap.constants:
        value = _payload_literal(cap, const.message_type, const.value_hex)
        c.append(_wrap(f"const {const.message_type}MsgPayload fsw_adapter_constant_{const.name} = {value};"))
    c += ["", "void fsw_adapter_clear(void)", "{"]
    for name in ("inputs", "inputs_written", "outputs", "outputs_written", "telemetry", "telemetry_written"):
        c.append(f"    memset(&fsw_adapter_{name}, 0, sizeof fsw_adapter_{name});")
    c += ["}", ""]
    for port in cap.inputs:
        c += [f"static void write_{port.name}(const void *payload, uint64_t timeNs)", "{", "    (void)timeNs;",
              f"    memcpy(&fsw_adapter_inputs.{port.name}, payload, sizeof fsw_adapter_inputs.{port.name});",
              f"    fsw_adapter_inputs_written.{port.name} = 1;", "}", ""]
    for group, ports in (("outputs", cap.outputs), ("telemetry", cap.telemetry)):
        for port in ports:
            c += [f"static int read_{port.name}(void *payload)", "{",
                  f"    memcpy(payload, &fsw_adapter_{group}.{port.name}, sizeof fsw_adapter_{group}.{port.name});",
                  f"    return fsw_adapter_{group}_written.{port.name} ? 1 : 0;", "}", ""]
    _port_tables(cap, c)
    ctx.write("adapter/fsw_adapter_ports.c", "\n".join(c))

    def listing(ports: List[Port]) -> List[str]:
        return [f" *     {p.name:<44} {p.message_type}MsgPayload" for p in ports] or [" *     (none)"]

    a = [_isc_c(), "",
         f"/* SIL adapter template for {_comment(cap.spacecraft)}: put your own flight software behind the same ports as",
         " * the export, then build fsw_adapter_host and run it from SpaceMissionStudio (Flight Software tab, Run SIL)",
         " * or with `fsw_adapter_host replay ...`. ADAPTER_GUIDE.md walks through it. As generated it builds and runs,",
         " * but sets no command: the simulation then holds the actuators at zero and reports the outputs missing.",
         " *",
         " * Inputs (fsw_adapter_inputs.<name>; fsw_adapter_inputs_written.<name> is 1 once written):", *listing(cap.inputs),
         " * Outputs (set fsw_adapter_outputs.<name> and fsw_adapter_outputs_written.<name> = 1):", *listing(cap.outputs),
         " * Telemetry (optional, same pattern with fsw_adapter_telemetry):", *listing(cap.telemetry), " */", "",
         "#include <string.h>", "", '#include "fsw_adapter.h"', '#include "fsw_ports.h"', '#include "fsw_scheduler.h"', "",
         "/* Your flight software's name, as the simulation shows it. */",
         'const char fsw_spacecraft_name[] = "adapter template";',
         "/* 64 zeros: this flight software was not exported from a SpaceMissionStudio scenario. */",
         f'const char fsw_config_digest[] = "{"0" * 64}";',
         "/* The step your flight software runs at; the simulation refuses a different one. */",
         f"const uint64_t fsw_rate_ns = {cap.rate_ns}ULL;", "",
         "void fsw_init(void)", "{", "    fsw_adapter_clear();", "    /* Initialise your flight software here. */", "}", "",
         "void fsw_reset(uint64_t timeNs)", "{", "    (void)timeNs;",
         "    /* Reset your flight software; fsw_adapter_inputs holds the inputs written at reset. */", "}", "",
         "void fsw_step(uint64_t timeNs)", "{", "    (void)timeNs;",
         "    /* 1. Read this step's inputs from fsw_adapter_inputs.",
         "     * 2. Run one step of your flight software.",
         "     * 3. Set each command in fsw_adapter_outputs and its flag in fsw_adapter_outputs_written. */", "}", ""]
    ctx.write("adapter/fsw_adapter.c", "\n".join(a))


def _struct_header(type_name: str) -> Optional[str]:
    for path in sources.paths():
        if path.startswith("architecture/msgPayloadDefC/") and re.search(
                r"\}\s*" + re.escape(type_name) + r"\s*;", sources.read_text(path)):
            return path
    return None


def _generate_layout_check(ctx: _Context, types: List[str]) -> None:
    cap = ctx.capture
    lines = [_isc_c(), "", "/* Compile-time check that every payload has the layout the simulation recorded (sizes and",
             " * field offsets from Basilisk's numpy dtypes). A mismatch stops the build here. Generated. */", "",
             "#include <stddef.h>", "", '#include "fsw_config.h"', "",
             "#define FSW_LAYOUT_CHECK(name, condition) typedef char fsw_layout_##name[(condition) ? 1 : -1]", ""]
    checked = set()

    def check(c_type: str, layout: dict, tag: str) -> None:
        if c_type in checked:
            return
        checked.add(c_type)
        lines.append(f"FSW_LAYOUT_CHECK({tag}_size, sizeof({c_type}) == {layout['itemsize']});")
        header = _struct_header(c_type)
        declared = {f.name: f for f in cdecl.parse_struct(sources.read_text(header), c_type)} if header else {}
        for entry in layout["fields"]:
            lines.append(f"FSW_LAYOUT_CHECK({tag}_{entry['name']}, offsetof({c_type}, {entry['name']}) == "
                         f"{entry['offset']});")
            if "struct" in entry and entry["name"] in declared:
                inner = declared[entry["name"]].c_type
                check(inner, entry["struct"], re.sub(r"\W", "_", inner))

    for t in types:
        check(f"{t}MsgPayload", cap.message_types[t].layout, t)
    lines.append("")
    ctx.write("generated/fsw_layout_check.c", "\n".join(lines))


def _payload_literal(cap: FswCapture, message_type: str, hex_value: str) -> str:
    layout = cap.message_types[message_type].layout
    return _c_struct(layout, decode(layout, bytes.fromhex(hex_value)))


def _generate_unit_tests(ctx: _Context) -> List[str]:
    cap = ctx.capture
    positions = {m.name: i for i, m in enumerate(cap.modules)}
    names = []
    for m in cap.modules:
        entry = MODULES[m.python_name]
        lines = [_isc_c(), "",
                 f"/* Unit test of {m.name} ({_comment(m.tag)}, Basilisk {m.python_name}): the module alone, with its exported",
                 " * parameters, fed the messages it read at the first step of the recorded run (time 0); its outputs",
                 " * must equal what it wrote there. Generated from the recording. */", "",
                 "#include <stdio.h>", "#include <math.h>", "#include <string.h>", "",
                 '#include "fsw_config.h"', '#include "fsw_leaves.h"', '#include "fsw_ports.h"', "",
                 f"static {entry.config_struct} config;"]
        linked = [link for link in m.inputs if link.kind != "unlinked"]
        for link in linked:
            lines.append(f"static {link.message_type}Msg_C source_{link.field};")
        lines += ["", "int main(void)", "{", "    int failures = 0;", "    double maxError;",
                  f"    fsw_set_parameters_{m.name}(&config);",
                  f"    SelfInit_{entry.function_suffix}(&config, {m.module_id});"]
        for link in linked:
            src = f"source_{link.field}"
            lines.append(f"    {link.message_type}Msg_C_init(&{src});")
            reset_value = None
            if link.kind == "constant":
                reset_value = next(c for c in cap.constants if c.name == link.ref).value_hex
            elif link.kind == "input":
                reset_value = cap.reset_inputs.get(link.ref)
            elif link.kind == "module":
                reset_value = cap.reset_outputs.get(link.ref)
            if reset_value is not None:
                lines.append(f"    {{ {link.message_type}MsgPayload value = "
                             f"{_wrap(_payload_literal(cap, link.message_type, reset_value), '          ')};")
                lines.append(f"      {link.message_type}Msg_C_write(&value, &{src}, 0, 0); }}")
            lines.append(f"    {link.message_type}Msg_C_subscribe(&config.{link.field}, &{src});")
        lines.append(f"    Reset_{entry.function_suffix}(&config, 0, {m.module_id});")
        for link in linked:
            if link.kind == "constant":
                continue
            if link.kind == "module" and positions[link.ref.split(".")[0]] > positions[m.name]:
                continue  # its producer runs later: at time 0 the module read the reset state
            read = cap.step0_reads.get(f"{m.name}.{link.field}")
            if read is None:
                continue
            lines.append(f"    {{ {link.message_type}MsgPayload value = "
                         f"{_wrap(_payload_literal(cap, link.message_type, read), '          ')};")
            lines.append(f"      {link.message_type}Msg_C_write(&value, &source_{link.field}, 0, 0); }}")
        lines.append(f"    Update_{entry.function_suffix}(&config, 0, {m.module_id});")
        for out in m.outputs:
            t, f_name = out["message_type"], out["field"]
            expected = cap.output_trace[0][f"{m.name}.{f_name}"]
            mtype = cap.message_types[t]
            lines += [f"    {{ static const {t}MsgPayload expected = "
                      f"{_wrap(_payload_literal(cap, t, expected), '          ')};",
                      f"      const FswPort port = {{\"{f_name}\", \"{t}\", {mtype.size}, \"{mtype.hash}\", "
                      f"fsw_leaves_{t}, fsw_leaf_count_{t}, NULL, NULL}};",
                      f"      if (!fsw_payloads_match(&port, FSW_OUTPUT_PAYLOAD(config.{f_name}), &expected, 1e-9, 1e-12, "
                      "&maxError)) {",
                      f'          printf("{m.name}.{f_name}: differs from the recording, max |error| %g\\n", maxError);',
                      "          failures++;", "      } else {",
                      f'          printf("{m.name}.{f_name}: matches the recording (max |error| %g)\\n", maxError);',
                      "      } }"]
        lines += ["    return failures ? 1 : 0;", "}", ""]
        ctx.write(f"tests/test_{m.name}.c", "\n".join(lines))
        names.append(m.name)
    return names


def _trace_bytes(cap: FswCapture, kind: int, ports: List[Port], records: List[Tuple[int, List[Optional[bytes]]]]) -> bytes:
    out = bytearray(b"SMSFTRC1")
    out += struct.pack("<III", kind, len(ports), len(records))
    for port in ports:
        mtype = cap.message_types[port.message_type]
        out += struct.pack("<I", mtype.size) + mtype.hash.encode()
    for time_ns, payloads in records:
        out += struct.pack("<Q", time_ns)
        out += bytes(1 if p is not None else 0 for p in payloads)
        for port, payload in zip(ports, payloads):
            size = cap.message_types[port.message_type].size
            out += payload if payload is not None else bytes(size)
    return bytes(out)


def _generate_traces(ctx: _Context) -> None:
    cap = ctx.capture
    reset = [bytes.fromhex(cap.reset_inputs[p.name]) if cap.reset_inputs.get(p.name) else None for p in cap.inputs]
    records = [(0, reset)] + [(t, [bytes.fromhex(step[p.name]) for p in cap.inputs])
                              for t, step in zip(cap.times_ns, cap.input_trace)]
    ctx.write("tests/data/replay_inputs.trace", _trace_bytes(cap, 1, cap.inputs, records))
    out_ports = cap.outputs + cap.telemetry
    expected = [(t, [bytes.fromhex(step[p.producer]) for p in out_ports])
                for t, step in zip(cap.times_ns, cap.output_trace)]
    ctx.write("tests/data/replay_expected.trace", _trace_bytes(cap, 2, out_ports, expected))


def _generate_cmake(ctx: _Context, basilisk_sources: List[str], types: List[str], tests: List[str]) -> None:
    cap = ctx.capture
    project = re.sub(r"[^A-Za-z0-9_]", "_", f"fsw_{cap.spacecraft}")
    lib = ["    " + f"basilisk/{p}" for p in basilisk_sources if p.endswith(".c")]
    lib += [f"    generated/cMsgCInterface/{t}Msg_C.c" for t in types]
    lib += [f"    generated/{name}" for name in ("fsw_config.c", "fsw_scheduler.c", "fsw_ports.c", "fsw_layout_check.c",
                                                   "fsw_log.c")]
    cm = [f"# Flight software of {_comment(cap.spacecraft)}, exported by SpaceMissionStudio (see README.md).",
          "cmake_minimum_required(VERSION 3.16)", f"project({project} C)", "",
          "# Basilisk's C modules use M_PI: C99 with the compiler's extensions (gnu99 for GCC and Clang).",
          "set(CMAKE_C_STANDARD 99)", "set(CMAKE_C_STANDARD_REQUIRED ON)", "set(CMAKE_C_EXTENSIONS ON)", "",
          "# Comparing payloads, trace files and the SIL link: shared by the exported flight software and the adapter.",
          "add_library(fsw_support STATIC generated/fsw_compare.c generated/fsw_trace.c generated/fsw_leaves.c",
          "    generated/fsw_transport_socket.c)",
          "target_include_directories(fsw_support PUBLIC basilisk generated)",
          "if(MSVC)", "    target_compile_definitions(fsw_support PUBLIC _USE_MATH_DEFINES _CRT_SECURE_NO_WARNINGS)",
          "else()", "    target_link_libraries(fsw_support PUBLIC m)", "endif()",
          "if(WIN32)", "    target_link_libraries(fsw_support PUBLIC ws2_32)", "endif()", "",
          "add_library(fsw STATIC", *lib, ")",
          "target_link_libraries(fsw PUBLIC fsw_support)", "",
          "# info, replay and sil (SIL_CONTRACT.md).",
          "add_executable(fsw_host host/fsw_host.c generated/fsw_sil.c)", "target_link_libraries(fsw_host PRIVATE fsw)",
          "target_compile_definitions(fsw_host PRIVATE FSW_HAVE_BSK_LOG)", "",
          "# The SIL adapter for flight software of your own (ADAPTER_GUIDE.md).",
          'option(FSW_BUILD_ADAPTER "Build the SIL adapter in adapter/" ON)',
          "if(FSW_BUILD_ADAPTER)",
          "    add_library(fsw_adapter STATIC adapter/fsw_adapter.c adapter/fsw_adapter_ports.c)",
          "    target_include_directories(fsw_adapter PUBLIC adapter)",
          "    target_link_libraries(fsw_adapter PUBLIC fsw_support)",
          "    add_executable(fsw_adapter_host host/fsw_host.c generated/fsw_sil.c)",
          "    target_link_libraries(fsw_adapter_host PRIVATE fsw_adapter)",
          "endif()", "",
          "enable_testing()"]
    for name in tests:
        cm += [f"add_executable(test_{name} tests/test_{name}.c)",
               f"target_link_libraries(test_{name} PRIVATE fsw)", f"add_test(NAME unit_{name} COMMAND test_{name})"]
    cm += ["add_test(NAME replay COMMAND fsw_host replay",
           "         ${CMAKE_CURRENT_SOURCE_DIR}/tests/data/replay_inputs.trace",
           "         ${CMAKE_CURRENT_BINARY_DIR}/replay_outputs.trace",
           "         --expect ${CMAKE_CURRENT_SOURCE_DIR}/tests/data/replay_expected.trace)",
           "if(FSW_BUILD_ADAPTER)", "    add_test(NAME adapter_ports COMMAND fsw_adapter_host info)", "endif()", ""]
    ctx.write("CMakeLists.txt", "\n".join(cm))


def _remove_previous(out: Path, overwrite: bool) -> None:
    if not out.exists():
        return
    if not out.is_dir():
        raise ExportError(f"{out} is a file")
    entries = list(out.iterdir())
    if not entries:
        return
    manifest_path = out / "manifest.json"
    if not manifest_path.exists():
        raise ExportError(f"{out} is not empty and holds no earlier export: choose an empty folder")
    if not overwrite:
        raise ExportError(f"{out} holds an earlier export; export again with overwrite to replace it")
    previous = json.loads(manifest_path.read_text()).get("files", {})
    for relative in previous:
        target = (out / relative).resolve()
        if out.resolve() in target.parents and target.is_file():
            target.unlink()
    manifest_path.unlink()
    for directory in sorted((p for p in out.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()


def generate(capture: FswCapture, out_dir, overwrite: bool = False) -> ExportResult:
    """Writes the C project into ``out_dir`` (created; an earlier export
    there is replaced only with ``overwrite``)."""
    from .documents import icd_markdown, readme_markdown, traceability_markdown

    out = Path(out_dir)
    _remove_previous(out, overwrite)
    ctx = _Context(capture, out)
    module_names = sorted({m.python_name for m in capture.modules})
    basilisk_files, types = source_closure(module_names)
    missing = [t for t in types if t not in capture.message_types]
    if missing:
        raise ExportError(f"the capture has no layout for {missing}")
    for path in basilisk_files:
        ctx.write(f"basilisk/{path}", sources.read(path))
    ctx.write("basilisk/LICENSE", sources.read("LICENSE"))
    for t in types:
        header, source = _message_interface(t)
        ctx.write(f"generated/cMsgCInterface/{t}Msg_C.h", header)
        ctx.write(f"generated/cMsgCInterface/{t}Msg_C.c", source)
    for name in _STATIC_GENERATED:
        ctx.write(f"generated/{name}", (_TEMPLATES / name).read_text())
    ctx.write("host/fsw_host.c", (_TEMPLATES / "fsw_host.c").read_text())
    for name in _STATIC_DOCUMENTS:
        ctx.write(name, (_TEMPLATES / name).read_text())
    _generate_config(ctx, [MODULES[n].header for n in module_names])
    _generate_scheduler(ctx)
    _generate_ports(ctx, types)
    _generate_layout_check(ctx, types)
    _generate_adapter(ctx)
    tests = _generate_unit_tests(ctx)
    _generate_traces(ctx)
    _generate_cmake(ctx, basilisk_files, types, tests)
    ctx.write("ICD.md", icd_markdown(capture))
    ctx.write("TRACEABILITY.md", traceability_markdown(capture, ctx.config_lines))
    ctx.write("README.md", readme_markdown(capture))

    manifest = {
        "format": EXPORT_FORMAT_VERSION,
        "spacecraft": capture.spacecraft,
        "scenario": capture.scenario_name,
        "config_digest": capture.config_digest,
        "basilisk_version": capture.basilisk_version,
        "basilisk_revision": capture.basilisk_revision,
        "exported_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exported_with": capture.exported_with,
        "rate_ns": capture.rate_ns,
        "modules": [{"name": m.name, "basilisk_module": m.python_name, "tag": m.tag} for m in capture.modules],
        "ports": {kind: [{"name": p.name, "message_type": p.message_type,
                          "size": capture.message_types[p.message_type].size,
                          "layout_hash": capture.message_types[p.message_type].hash} for p in ports]
                  for kind, ports in (("inputs", capture.inputs), ("outputs", capture.outputs),
                                      ("telemetry", capture.telemetry))},
        "recorded_steps": len(capture.times_ns),
        "files": {path: hashlib.sha256(data).hexdigest() for path, data in sorted(ctx.files.items())},
    }
    out.mkdir(parents=True, exist_ok=True)
    for relative, data in ctx.files.items():
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (out / "capture.json").write_text(capture.to_json() + "\n")
    manifest["files"]["capture.json"] = hashlib.sha256((capture.to_json() + "\n").encode()).hexdigest()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return ExportResult(out, sorted(ctx.files) + ["capture.json", "manifest.json"], manifest)
