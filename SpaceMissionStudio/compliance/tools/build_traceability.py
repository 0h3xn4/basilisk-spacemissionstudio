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
"""Build ``compliance/traceability_matrix.csv``: requirement -> status,
code evidence (from the compliance matrix) and the tests that verify it
(ECSS-E-ST-40C 5.5.3.2, 5.6, 5.8.3.5; remediation R12).

Tests name the requirements they verify with the pytest marker
``requirement(*ids)``, at module level (``pytestmark``) or on a test. An ID
is ``"<standard> <requirement ID>"`` (``"E-ST-10-09C 5.4.6a"``,
``"CCSDS-502.0-B-3 4.2.4.9"``); a requirement ID without a letter
(``"Q-ST-80C 6.2.4"``) or ending in ``*`` (``"ICS-OPM-*"``) covers every
requirement it prefixes. A marker that matches no requirement fails the
build. A compliant requirement without a test is verified by inspection of
its evidence (a document or a design property). Usage::

    python compliance/tools/build_traceability.py
"""

from __future__ import annotations

import ast
import collections
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT.parent / "tests"
STANDARDS = ("E-ST-40C", "Q-ST-80C", "E-ST-10-09C", "E-ST-10-04C", "CCSDS-502.0-B-3")


def _marker_ids(node) -> list:
    """Requirement IDs of a ``pytest.mark.requirement(...)`` call node."""
    calls = node.elts if isinstance(node, (ast.List, ast.Tuple)) else [node]
    ids = []
    for call in calls:
        if isinstance(call, ast.Call) and getattr(call.func, "attr", None) == "requirement":
            ids += [arg.value for arg in call.args if isinstance(arg, ast.Constant)]
    return ids


def collect_markers():
    """``{test node id: [requirement ids]}`` from every test file."""
    markers = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_ids = []
        for statement in tree.body:
            if isinstance(statement, ast.Assign) and any(getattr(t, "id", None) == "pytestmark"
                                                         for t in statement.targets):
                module_ids += _marker_ids(statement.value)
        for statement in tree.body:
            if isinstance(statement, ast.FunctionDef) and statement.name.startswith("test_"):
                ids = list(module_ids)
                for decorator in statement.decorator_list:
                    ids += _marker_ids(decorator)
                if ids:
                    markers[f"{path.relative_to(TESTS.parent)}::{statement.name}"] = ids
    return markers


def _resolve(marker: str, rows_by_standard):
    standard, _, requirement = marker.partition(" ")
    if marker.startswith("ICS-"):
        standard, requirement = "CCSDS-502.0-B-3", marker
    elif standard == "CCSDS-502.0-B-3":
        requirement = marker  # CCSDS row IDs carry the standard's name
    if standard not in rows_by_standard:
        return []
    rows = rows_by_standard[standard]
    if requirement.endswith("*"):
        return [r for r in rows if r["ID"].startswith(requirement[:-1])]
    exact = [r for r in rows if r["ID"] == requirement]
    return exact or [r for r in rows if r["ID"].startswith(requirement + ".") or
                     (r["ID"].startswith(requirement) and r["ID"][len(requirement):].isalpha())]


def build() -> int:
    with open(ROOT / "compliance_matrix.csv", encoding="utf-8") as f:
        matrix = list(csv.DictReader(f))
    rows_by_standard = collections.defaultdict(list)
    for row in matrix:
        rows_by_standard[row["standard"]].append(row)
    tests_by_requirement = collections.defaultdict(set)
    unresolved = []
    for test, ids in collect_markers().items():
        for marker in ids:
            matched = _resolve(marker, rows_by_standard)
            if not matched:
                unresolved.append(f"{test}: {marker}")
            for row in matched:
                tests_by_requirement[(row["standard"], row["ID"])].add(test)
    if unresolved:
        print("requirement markers that match no requirement:", *unresolved, sep="\n  ", file=sys.stderr)
        return 1
    out = []
    for row in matrix:
        if row["status"] == "Not applicable":
            continue
        tests = sorted(tests_by_requirement.get((row["standard"], row["ID"]), ()))
        out.append({"standard": row["standard"], "ID": row["ID"], "status": row["status"],
                    "remediation": row["remediation"], "code_evidence": row["evidence"][:300],
                    "verification": "test" if tests else ("inspection of the evidence" if
                                                            row["status"] == "Compliant" else "-"),
                    "tests": "; ".join(tests), "test_count": len(tests)})
    with open(ROOT / "traceability_matrix.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, list(out[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(out)
    compliant = [r for r in out if r["status"] == "Compliant"]
    tested = [r for r in compliant if r["test_count"]]
    print(f"traceability_matrix.csv: {len(out)} applicable requirements; {len(compliant)} compliant, "
          f"{len(tested)} of them traced to tests; {sum(1 for r in out if r['test_count'])} traced in total")
    return 0


if __name__ == "__main__":
    sys.exit(build())
