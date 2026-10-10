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
"""Sort the statements the test suite never executes (ECSS-Q-ST-80C
6.2.3.6a: unreachable code).

Input: the suite's ``coverage.json`` (``pytest --cov=spacemissionstudio
--cov-report=json``; see below for how to measure). Each missed statement is put in the
first group that fits its place in the source:

* ``handler``: inside an ``except`` block (an error path);
* ``platform``: under a test of ``sys.platform``, ``os.name`` or
  ``platform.system()``;
* ``guard``: a ``raise`` or ``return`` straight under an ``if`` (an input
  check or early exit);
* ``unentered``: in a function no test enters at all;
* ``branch``: any other statement in a function that tests do enter (a
  condition the tests do not set up).

A missed statement is not unreachable by itself: it may only be
untested. ``unentered`` functions are listed one by one with the number
of places that name them anywhere in the package, so a function that
nothing names (unreachable) stands apart from one that is named but not
tested.

Measure with Python 3.12 or later and ``COVERAGE_CORE=sysmon``, statements
only (``sys.monitoring`` does not measure branches before Python 3.14).
Basilisk calls the tool's Python ``SysModel`` callbacks (``UpdateState``,
``Reset`` and everything they call) from its own native thread, which
coverage's default tracer never sees: on the qualified Python 3.11 those
callbacks read as never executed although they run every step.

Usage::

    COVERAGE_CORE=sysmon python3.12 -m pytest tests --cov=spacemissionstudio --cov-report=json:coverage.json
    python compliance/tools/unreached_code.py coverage.json [--write] [--measured "<date>, commit <hash>"]

``--write`` stores the report in ``compliance/unreached_code.md``.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT.parent
PACKAGE = TOOL / "spacemissionstudio"
GROUPS = ("handler", "platform", "guard", "unentered", "branch")
_PLATFORM_TEST = re.compile(r"sys\.platform|os\.name|platform\.system\(\)")


class _Context(ast.NodeVisitor):
    """For each source line: the innermost function, and whether it is
    inside an ``except`` block or a platform test."""

    def __init__(self, source: str):
        self.source = source
        self.function = {}  # line -> qualified function name
        self.functions = {}  # qualified name -> (first line, last line)
        self.handler = set()
        self.platform = set()
        self.guard = set()
        self._stack = []

    def _mark(self, node, target: set) -> None:
        for line in range(node.lineno, (node.end_lineno or node.lineno) + 1):
            target.add(line)

    def _visit_function(self, node) -> None:
        self._stack.append(node.name)
        name = ".".join(self._stack)
        self.functions[name] = (node.lineno, node.end_lineno or node.lineno)
        for line in range(node.lineno, (node.end_lineno or node.lineno) + 1):
            self.function[line] = name
        self.generic_visit(node)
        self._stack.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_ClassDef(self, node) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_ExceptHandler(self, node) -> None:
        for statement in node.body:
            self._mark(statement, self.handler)
        self.generic_visit(node)

    def visit_If(self, node) -> None:
        if _PLATFORM_TEST.search(ast.get_source_segment(self.source, node.test) or ""):
            for statement in node.body + node.orelse:
                self._mark(statement, self.platform)
        for statement in node.body:
            if isinstance(statement, (ast.Raise, ast.Return)):
                self._mark(statement, self.guard)
        self.generic_visit(node)


def _names_in_package(name: str, texts: dict) -> int:
    """Places in the package that name ``name`` (its definition excluded)."""
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    return sum(len(pattern.findall(text)) for text in texts.values()) - 1


def analyse(coverage: dict) -> dict:
    """Group the missed statements of every package file.

    :param coverage: the parsed ``coverage.json``.
    :return: totals per group, per-file counts, and the unentered functions.
    """
    texts = {path: path.read_text(encoding="utf-8") for path in PACKAGE.rglob("*.py")}
    totals = Counter()
    per_file = {}
    unentered = []
    statements = 0
    for name, data in sorted(coverage["files"].items()):
        path = (TOOL / name) if not Path(name).is_absolute() else Path(name)
        if not path.exists() or PACKAGE not in path.resolve().parents:
            continue
        source = path.read_text(encoding="utf-8")
        context = _Context(source)
        context.visit(ast.parse(source))
        executed = set(data["executed_lines"])
        missing = set(data["missing_lines"])
        statements += len(executed) + len(missing)
        entered = {context.function[line] for line in executed if line in context.function}
        counts = Counter()
        for line in sorted(missing):
            function = context.function.get(line)
            if line in context.handler:
                group = "handler"
            elif line in context.platform:
                group = "platform"
            elif line in context.guard:
                group = "guard"
            elif function is not None and function not in entered:
                group = "unentered"
            else:
                group = "branch"
            counts[group] += 1
        totals.update(counts)
        relative = path.resolve().relative_to(TOOL).as_posix()
        per_file[relative] = dict(counts)
        for function, (first, last) in sorted(context.functions.items(), key=lambda item: item[1]):
            body = {line for line in missing | executed if first <= line <= last}
            if function in entered or not body or any(
                    other != function and other.startswith(function + ".") for other in entered):
                continue
            unentered.append({"file": relative, "function": function, "line": first, "statements": len(body),
                              "named": _names_in_package(function.rsplit(".", 1)[-1], texts)})
    return {"statements": statements, "missed": sum(totals.values()), "totals": dict(totals),
            "per_file": per_file, "unentered": unentered}


def report(analysis: dict, measured: str = "") -> str:
    """The analysis as Markdown; ``measured`` says when and on what the
    coverage was measured."""
    totals = analysis["totals"]
    lines = ["# Statements the test suite does not execute (Q-ST-80C 6.2.3.6a)", "",
             "Generated by `compliance/tools/unreached_code.py` from the suite's `coverage.json`, measured on",
             "Python 3.12 with `COVERAGE_CORE=sysmon` (statements), which also sees Basilisk's native thread.",
             "The review of these statements is in `review_log.md` (F-13 to F-15, F-18).", ""]
    if measured:
        lines += [f"Measured: {measured}.", ""]
    lines += [f"{analysis['missed']} of {analysis['statements']} statements are not executed.", "",
             "| Group | Statements |", "|---|---|"]
    lines += [f"| {group} | {totals.get(group, 0)} |" for group in GROUPS]
    lines += ["", "## Functions no test enters", "",
              "`Named` counts the places in the package that use the name; 0 means nothing can call it.", "",
              "| File | Function | Line | Statements | Named |", "|---|---|---|---|---|"]
    lines += [f"| `{u['file']}` | `{u['function']}` | {u['line']} | {u['statements']} | {u['named']} |"
              for u in analysis["unentered"]]
    lines += ["", "## Per file", "", "| File | " + " | ".join(GROUPS) + " |", "|---|" + "---|" * len(GROUPS)]
    for name, counts in analysis["per_file"].items():
        if counts:
            lines.append(f"| `{name}` | " + " | ".join(str(counts.get(group, 0)) for group in GROUPS) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("coverage", type=Path, help="coverage.json from the test suite")
    parser.add_argument("--write", action="store_true", help="store the report in compliance/unreached_code.md")
    parser.add_argument("--measured", default="", help='when and on what, e.g. "2026-10-10, commit abc1234"')
    args = parser.parse_args(argv)
    analysis = analyse(json.loads(args.coverage.read_text(encoding="utf-8")))
    text = report(analysis, args.measured)
    print(text)
    if args.write:
        (ROOT / "unreached_code.md").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
