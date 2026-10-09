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
comparison": "a diff of their inputs").

:func:`diff` walks two scenario dicts (``Scenario.to_dict()``) and lists
every value that differs, by its path in the scenario file
(``spacecraft[sat-1].orbit.semi_major_axis_km``). List items that carry a
``name`` (spacecraft, ground stations, devices) are matched by name, not
position, so adding one spacecraft does not show every later one as
changed. Basilisk-free.
"""

from __future__ import annotations

from typing import Any, List, Tuple

_MISSING = "(none)"


def _key(item: Any, index: int) -> str:
    if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]:
        return item["name"]
    return str(index)


def _walk(path: str, a: Any, b: Any, out: List[Tuple[str, Any, Any]]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for name in list(a) + [k for k in b if k not in a]:
            _walk(f"{path}.{name}" if path else name, a.get(name, _MISSING), b.get(name, _MISSING), out)
        return
    if isinstance(a, list) and isinstance(b, list):
        keyed_a = {_key(item, i): item for i, item in enumerate(a)}
        keyed_b = {_key(item, i): item for i, item in enumerate(b)}
        if len(keyed_a) == len(a) and len(keyed_b) == len(b) and (
                any(isinstance(x, dict) for x in a + b)):
            for name in list(keyed_a) + [k for k in keyed_b if k not in keyed_a]:
                _walk(f"{path}[{name}]", keyed_a.get(name, _MISSING), keyed_b.get(name, _MISSING), out)
            return
    if a != b:
        out.append((path, a, b))


def diff(a: dict, b: dict) -> List[Tuple[str, Any, Any]]:
    """``(path, value in a, value in b)`` for every input that differs;
    ``"(none)"`` where one side does not have it."""
    out: List[Tuple[str, Any, Any]] = []
    _walk("", a, b, out)
    return out


def short(value: Any, limit: int = 60) -> str:
    """A value as one short line of text."""
    text = str(value)
    return text if len(text) <= limit else text[:limit - 3] + "..."
