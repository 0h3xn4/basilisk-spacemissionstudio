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

"""Reads struct declarations out of Basilisk's C headers.

Basilisk's C module and message headers declare one field per line, with
a Doxygen trailing comment that starts with the unit in brackets::

    double K;                   //!< [rad/sec] Proportional gain applied to MRP errors
    AttGuidMsg_C guidInMsg;     //!< attitude guidance input message

That regularity is all this relies on. :func:`parse_struct` returns each
field's C type, name, array dimensions (as written), unit and
description; nothing here evaluates C. Field values and binary layouts
come from the running Basilisk objects and the payloads' numpy dtypes
(:mod:`.capture`), and the generated C checks the layouts at compile time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_FIELD = re.compile(
    r"^\s*(?P<type>(?:unsigned\s+|signed\s+|const\s+|struct\s+)*[A-Za-z_]\w*)\s*(?P<pointer>\*?)\s*"
    r"(?P<name>[A-Za-z_]\w*)\s*(?P<dims>(?:\[[^\]]+\])*)\s*;\s*(?P<comment>.*)$")
_COMMENT = re.compile(r"^(?://!<|//|/\*!<|/\*\*<|/\*)\s*(?P<text>.*?)\s*(?:\*/)?\s*$")
_UNIT = re.compile(r"^\[(?P<unit>[^\]]*)\]\s*(?P<rest>.*)$")


@dataclass(frozen=True)
class Field:
    c_type: str
    name: str
    dims: str  # e.g. "[3]" or "[MAX_EFF_CNT]" or ""
    pointer: bool
    unit: str  # without the brackets; "" when the comment gives none
    description: str

    @property
    def is_message(self) -> bool:
        return self.c_type.endswith("Msg_C")

    @property
    def message_type(self) -> Optional[str]:
        """``AttGuid`` for ``AttGuidMsg_C``."""
        return self.c_type[: -len("Msg_C")] if self.is_message else None

    @property
    def is_input(self) -> bool:
        return self.is_message and ("InMsg" in self.name)

    @property
    def is_output(self) -> bool:
        return self.is_message and ("OutMsg" in self.name)


class StructNotFound(LookupError):
    pass


def integer_macros(header_text: str) -> dict:
    """``#define NAME <integer>`` lines, e.g. ``MAX_EFF_CNT`` -> 36."""
    return {name: int(value) for name, value in re.findall(r"^\s*#\s*define\s+(\w+)\s+(\d+)\s*$", header_text, re.M)}


def array_shape(dims: str, macros: dict) -> List[int]:
    """``"[MAX_EFF_CNT]"`` -> ``[36]``; ``"[3*3]"`` -> ``[9]``; ``"[3][3]"`` -> ``[3, 3]``. Only integers,
    known macros and ``*``/``+``/``-`` are accepted."""
    shape = []
    for expression in re.findall(r"\[([^\]]+)\]", dims):
        parts = re.findall(r"\w+|[*+-]", expression)
        value, operator = None, "+"
        for part in parts:
            if part in ("*", "+", "-"):
                operator = part
                continue
            number = int(part) if part.isdigit() else macros.get(part)
            if number is None:
                raise ValueError(f"unknown size {part!r} in {dims}")
            value = number if value is None else (value * number if operator == "*" else
                                                  value + number if operator == "+" else value - number)
        shape.append(int(value))
    return shape


def _strip_block_comments(text: str) -> str:
    """Removes ``/* ... */`` comments that are not trailing field comments,
    keeping line structure."""
    def keep_lines(match):
        return "\n" * match.group(0).count("\n")
    return re.sub(r"/\*(?![!*]<).*?\*/", keep_lines, text, flags=re.S)


def parse_struct(header_text: str, struct_name: str) -> List[Field]:
    """The fields of ``typedef struct {...} <struct_name>;`` in order."""
    text = _strip_block_comments(header_text)
    pattern = re.compile(r"typedef\s+struct\s*\w*\s*\{(?P<body>.*?)\}\s*" + re.escape(struct_name) + r"\s*;", re.S)
    match = pattern.search(text)
    if match is None:
        raise StructNotFound(f"no 'typedef struct {{...}} {struct_name};' in the header")
    fields = []
    for line in match.group("body").splitlines():
        found = _FIELD.match(line)
        if found is None:
            continue
        comment = _COMMENT.match(found.group("comment")) if found.group("comment") else None
        text_part = comment.group("text") if comment else ""
        unit_match = _UNIT.match(text_part)
        unit, description = (unit_match.group("unit").strip(), unit_match.group("rest")) if unit_match \
            else ("", text_part)
        fields.append(Field(c_type=" ".join(found.group("type").split()), name=found.group("name"),
                            dims=found.group("dims").replace(" ", ""), pointer=bool(found.group("pointer")),
                            unit=unit, description=description.strip()))
    return fields
