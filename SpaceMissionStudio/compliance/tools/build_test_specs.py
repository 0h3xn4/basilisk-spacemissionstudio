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
"""Generate the test-case lists of the SUITP and the SVS (ECSS-E-ST-40C
K.2.1<8>, <9>, <11> and L.2.1<6>, <7>, <11>; remediation R14):

* ``compliance/docs/SUITP_test_cases.md``: the unit and integration tests
  (``tests/`` except ``tests/validation``);
* ``compliance/docs/SVS_test_cases.md``: the validation tests
  (``tests/validation``).

Read from the test sources with :mod:`ast` (nothing is imported or run).
A test design is a test file (its docstring describes it); a test case is a
test function (identifier ``<file>::<function>``, purpose from its
docstring, requirements from its ``requirement`` markers, level from its
markers and location). Usage::

    python compliance/tools/build_test_specs.py
"""

from __future__ import annotations

import ast
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT.parent / "tests"


def _mark(node: ast.AST) -> tuple:
    """``(marker name, [string arguments])`` of a ``pytest.mark.<name>(...)`` node."""
    call = node if isinstance(node, ast.Call) else None
    target = call.func if call else node
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Attribute) and \
            target.value.attr == "mark":
        args = [a.value for a in (call.args if call else []) if isinstance(a, ast.Constant)
                and isinstance(a.value, str)]
        return target.attr, args
    return None, []


def _module_marks(tree: ast.Module) -> list:
    marks = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "pytestmark" for t in node.targets):
            values = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
            marks += [_mark(v) for v in values]
    return marks


def _first_sentence(doc: str) -> str:
    text = " ".join((doc or "").split())
    end = text.find(". ")
    return (text if end < 0 else text[:end + 1])[:220].replace("|", "/")


def collect() -> list:
    """Every test function, as a dict."""
    cases = []
    for path in sorted(TESTS.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_marks = _module_marks(tree)
        rel = path.relative_to(TESTS.parent).as_posix()
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test_"):
                continue
            marks = module_marks + [_mark(d) for d in node.decorator_list]
            names = {name for name, _args in marks if name}
            requirements = [arg for name, args in marks if name == "requirement" for arg in args]
            if "validation" in path.parts:
                level = "validation"
            elif "requires_basilisk" in names or "gui" in path.parts:
                level = "integration"
            else:
                level = "unit"
            needs = [n for n, flag in (("Basilisk", "requires_basilisk" in names),
                                       ("Qt (offscreen)", "gui" in path.parts)) if flag]
            cases.append({"file": rel, "design_doc": _first_sentence(ast.get_docstring(tree) or ""),
                          "id": f"{rel}::{node.name}", "name": node.name,
                          "purpose": _first_sentence(ast.get_docstring(node) or ""),
                          "requirements": requirements, "level": level,
                          "parametrized": "parametrize" in names, "needs": needs})
    return cases


def _write(out: Path, title: str, intro: list, cases: list) -> None:
    by_file = collections.OrderedDict()
    for case in cases:
        by_file.setdefault(case["file"], []).append(case)
    documented = sum(1 for c in cases if c["purpose"])
    traced = sum(1 for c in cases if c["requirements"])
    levels = collections.Counter(c["level"] for c in cases)
    lines = [f"# {title} (generated)", "", *intro, "",
             f"**{len(cases)} test functions in {len(by_file)} test designs** "
             f"({', '.join(f'{n} {k}' for k, n in sorted(levels.items()))}). "
             f"{documented} have a docstring stating their purpose; {len(cases) - documented} do not "
             f"(their purpose is their name). {traced} name the requirements they verify with a "
             "`requirement` marker; the others trace through the SRS validation matrix (SRS section 6).", "",
             "## Test designs", "", "| Test design (file) | Description | Cases | Level | Needs |",
             "|---|---|---|---|---|"]
    for file, file_cases in by_file.items():
        file_levels = sorted({c["level"] for c in file_cases})
        needs = sorted({n for c in file_cases for n in c["needs"]})
        lines.append(f"| `{file}` | {file_cases[0]['design_doc'] or '-'} | {len(file_cases)} | "
                     f"{', '.join(file_levels)} | {', '.join(needs) or '-'} |")
    lines += ["", "## Test cases", ""]
    for file, file_cases in by_file.items():
        lines += [f"### `{file}`", "", "| Test case | Purpose | Requirements | Level |", "|---|---|---|---|"]
        for c in file_cases:
            name = f"`{c['name']}`" + (" (parametrized)" if c["parametrized"] else "")
            lines.append(f"| {name} | {c['purpose'] or '-'} | {', '.join(c['requirements']) or '-'} | "
                         f"{c['level']} |")
        lines.append("")
    out.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")  # one final newline (pre-commit end-of-file-fixer)
    print(f"{out.name}: {len(cases)} test cases, {len(by_file)} designs")


def build() -> int:
    cases = collect()
    common = ("Generated by `compliance/tools/build_test_specs.py` from the test sources (read with `ast`). "
              "Identifier of a test case: `<file>::<function>`; a parametrized case runs once per parameter set. "
              "Inputs, expected outputs and the pass criterion of each case are its code: the fixtures and data "
              "it uses, and its assertions. A case passes when it runs to the end with every assertion true.")
    _write(ROOT / "docs" / "SUITP_test_cases.md", "Unit and integration test cases",
           [common, "", "Levels: *unit* runs without Basilisk or Qt; *integration* runs a Basilisk simulation or "
                        "the Qt GUI (offscreen)."],
           [c for c in cases if c["level"] != "validation"])
    _write(ROOT / "docs" / "SVS_test_cases.md", "Validation test cases",
           [common, "", "The validation cases V-01 to V-08 and their references are specified in `SVS.md`."],
           [c for c in cases if c["level"] == "validation"])
    return 0


if __name__ == "__main__":
    sys.exit(build())
