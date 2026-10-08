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
"""Collect the product metrics of ECSS-Q-ST-80C 7.1.5a and write
``compliance/metrics.json`` and ``compliance/metrics.md`` (remediation R11):

1. size: source lines of code per package (non-blank, non-comment lines);
2. complexity: McCabe cyclomatic complexity of every function, measured
   by ruff's C901 rule (mccabe), with the functions above the coding
   standard's limit (``docs/coding_standard.md`` rule C-7);
3. fault density: corrective commits touching the tool per thousand SLOC
   (a proxy: commit subjects starting with "Fix"; the problem reports of a
   nonconformance system would replace it, human action H05);
4. test coverage: statement and branch coverage from ``coverage.json``
   (``pytest --cov=spacemissionstudio --cov-branch --cov-report=json``);
5. number of failures: failed and errored tests from a JUnit XML report
   (``pytest --junitxml=...``), when given.

Usage::

    python compliance/tools/metrics.py [--coverage coverage.json] [--junit report.xml] [--fail-under 90]
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT.parent
PACKAGE = TOOL / "spacemissionstudio"
TESTS = TOOL / "tests"
COMPLEXITY_LIMIT = 15  # coding_standard.md rule C-7


def sloc(path: Path) -> int:
    """Non-blank lines that are not ``#`` comments."""
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.strip().startswith("#"))


def complexities():
    """``[(location and name, complexity)]`` of every function, from ruff's
    mccabe rule C901 with a zero threshold (every function is reported);
    None when ruff is not installed."""
    command = [sys.executable, "-m", "ruff"] if _has_ruff_module() else ["ruff"]
    try:
        out = subprocess.run(command + ["check", str(PACKAGE), "--select", "C901", "--config",
                                        "lint.mccabe.max-complexity=0", "--output-format", "json", "--exit-zero"],
                             capture_output=True, text=True, check=True, cwd=TOOL).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    result = []
    for item in json.loads(out):
        match = re.match(r"`(.+)` is too complex \((\d+) > 0\)", item["message"])
        if match:
            where = f"{Path(item['filename']).relative_to(TOOL)}:{item['location']['row']}"
            result.append((f"{where} {match.group(1)}", int(match.group(2))))
    return result


def _has_ruff_module() -> bool:
    import importlib.util

    return importlib.util.find_spec("ruff") is not None


def corrective_commits() -> int:
    """Commits touching the tool whose subject starts with "Fix"."""
    try:
        subjects = subprocess.run(["git", "log", "--format=%s", "--", str(TOOL)], capture_output=True, text=True,
                                  check=True, cwd=TOOL).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return -1
    return sum(1 for s in subjects if s.lower().startswith("fix"))


def junit_failures(path: Path) -> dict:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    return {key: sum(int(s.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped")}


def collect(coverage_json: Path = None, junit: Path = None) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_traceability import collect_markers

    size = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        part = path.relative_to(PACKAGE).parts[0] if len(path.relative_to(PACKAGE).parts) > 1 else "(top level)"
        size[part] = size.get(part, 0) + sloc(path)
    total_sloc = sum(size.values())
    every_function = complexities() or []
    values = sorted(value for _name, value in every_function)
    test_functions = sum(1 for path in TESTS.rglob("test_*.py")
                         for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                         if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"))
    fixes = corrective_commits()
    metrics = {
        "date": date.today().isoformat(),
        "size": {"sloc_total": total_sloc, "sloc_by_package": size, "test_sloc": sum(sloc(p) for p in
                                                                                   TESTS.rglob("*.py"))},
        "complexity": {"tool": "ruff C901 (mccabe)" if values else "not measured (ruff not installed)",
                       "functions": len(values), "median": values[len(values) // 2] if values else 0,
                       "max": values[-1] if values else 0, "limit": COMPLEXITY_LIMIT,
                       "above_limit": sorted(([n, v] for n, v in every_function if v > COMPLEXITY_LIMIT),
                                             key=lambda item: -item[1])},
        "tests": {"test_functions": test_functions, "requirement_tagged_tests": len(collect_markers())},
        "fault_density": {"corrective_commits": fixes,
                          "per_ksloc": round(fixes / total_sloc * 1000, 2) if fixes >= 0 and total_sloc else None,
                          "note": "proxy: commit subjects starting with 'Fix' (no problem-report system yet, H05)"},
    }
    if coverage_json and coverage_json.exists():
        totals = json.loads(coverage_json.read_text())["totals"]
        metrics["coverage"] = {"statements": totals["num_statements"], "statement_percent":
                               round(100.0 * totals["covered_lines"] / max(totals["num_statements"], 1), 1),
                               "branches": totals.get("num_branches"),
                               "branch_percent": round(100.0 * totals["covered_branches"]
                                                       / max(totals["num_branches"], 1), 1)
                               if totals.get("num_branches") else None}
    if junit and junit.exists():
        metrics["failures"] = junit_failures(junit)
    return metrics


def report(metrics: dict) -> str:
    lines = [f"# Product metrics ({metrics['date']})", "",
             "Generated by `compliance/tools/metrics.py` (ECSS-Q-ST-80C 7.1.5a; remediation R11). "
             "Thresholds are those of `docs/coding_standard.md`; agreeing them with the customer is human action H09.", "",
             "| Metric | Value |", "|---|---|",
             f"| Size (SLOC, package) | {metrics['size']['sloc_total']} |",
             f"| Size (SLOC, tests) | {metrics['size']['test_sloc']} |",
             f"| Functions | {metrics['complexity']['functions']} |",
             f"| Cyclomatic complexity, median / max | {metrics['complexity']['median']} / "
             f"{metrics['complexity']['max']} |",
             f"| Functions above {metrics['complexity']['limit']} | {len(metrics['complexity']['above_limit'])} |",
             f"| Test functions / requirement-tagged | {metrics['tests']['test_functions']} / "
             f"{metrics['tests']['requirement_tagged_tests']} |",
             f"| Corrective commits (proxy) / per kSLOC | {metrics['fault_density']['corrective_commits']} / "
             f"{metrics['fault_density']['per_ksloc']} |"]
    if "coverage" in metrics:
        c = metrics["coverage"]
        lines.append(f"| Statement coverage | {c['statement_percent']} % of {c['statements']} |")
        if c["branch_percent"] is not None:
            lines.append(f"| Branch coverage | {c['branch_percent']} % of {c['branches']} |")
    else:
        lines.append("| Coverage | not measured in this run (no coverage.json) |")
    if "failures" in metrics:
        f = metrics["failures"]
        lines.append(f"| Tests run / failed / errors / skipped | {f['tests']} / {f['failures']} / {f['errors']} / "
                     f"{f['skipped']} |")
    lines += ["", "## Size by package", "", "| Package | SLOC |", "|---|---|"]
    lines += [f"| {name} | {value} |" for name, value in sorted(metrics["size"]["sloc_by_package"].items())]
    lines += ["", f"## Functions above complexity {metrics['complexity']['limit']}", "",
              "Each is a refactoring candidate or needs a justification under rule C-7.", "",
              "| Function | Complexity |", "|---|---|"]
    lines += [f"| `{name}` | {value} |" for name, value in metrics["complexity"]["above_limit"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--coverage", type=Path, default=TOOL / "coverage.json")
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--fail-under", type=float, metavar="PERCENT",
                        help="exit 1 if statement coverage is below PERCENT (coding standard rule C-10)")
    args = parser.parse_args(argv)
    metrics = collect(args.coverage, args.junit)
    (ROOT / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n", encoding="utf-8")
    (ROOT / "metrics.md").write_text(report(metrics), encoding="utf-8")
    print(f"metrics: {metrics['size']['sloc_total']} SLOC, {metrics['complexity']['functions']} functions "
          f"({len(metrics['complexity']['above_limit'])} above complexity {COMPLEXITY_LIMIT}), "
          f"coverage {metrics.get('coverage', {}).get('statement_percent', 'not measured')}")
    if args.fail_under is not None:
        percent = metrics.get("coverage", {}).get("statement_percent")
        if percent is None or percent < args.fail_under:
            print(f"statement coverage {percent} is below {args.fail_under} % (rule C-10)", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
