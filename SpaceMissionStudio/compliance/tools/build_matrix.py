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
"""Build ``compliance/compliance_matrix.csv`` from the requirement CSVs and
the assessment rules in ``compliance/audit/``.

Every requirement gets a row. Requirements the Phase 0 tailoring left out
(not applicable, deleted, OCM not requested) carry status "Not applicable"
with that reason; every other one must be covered by an assessment rule,
or the build fails and names it. Usage::

    python compliance/tools/build_matrix.py
"""

from __future__ import annotations

import collections
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "audit"))

from assessments_software import SOFTWARE_RULES  # noqa: E402
from assessments_technical import TECHNICAL_RULES  # noqa: E402

STATUS = {
    "C": "Compliant",
    "P": "Partially compliant",
    "N": "Non-compliant",
    "NA": "Not applicable",
    "H": "Requires human or process action",
}
FILES = {
    "E-ST-40C": "ECSS-E-ST-40C.csv",
    "Q-ST-80C": "ECSS-Q-ST-80C.csv",
    "E-ST-10-09C": "ECSS-E-ST-10-09C.csv",
    "E-ST-10-04C": "ECSS-E-ST-10-04C.csv",
    "CCSDS-502.0-B-3": "CCSDS-502.0-B-3.csv",
}
COLUMNS = ("standard", "ID", "clause", "level", "requirement_text", "applicability", "status", "evidence", "gap",
           "proposed_fix", "effort", "near_basilisk", "remediation", "assessed_by")
_TAILORED_OUT = ("Not applicable", "Deleted", "Not requested")


def _rules():
    rules = collections.defaultdict(list)
    for rule in TECHNICAL_RULES + SOFTWARE_RULES:
        standard, match, status = rule[0], rule[1], rule[2]
        if status not in STATUS:
            raise ValueError(f"rule {standard} {match}: unknown status {status!r}")
        if standard not in FILES:
            raise ValueError(f"rule {standard} {match}: unknown standard")
        rules[standard].append(rule)
    return rules


def _match(rules, rid: str):
    """The most specific rule: an exact ID, else the longest prefix (``x*``)."""
    exact = [r for r in rules if r[1] == rid]
    if exact:
        return exact[0]
    prefixed = [r for r in rules if r[1].endswith("*") and rid.startswith(r[1][:-1])]
    return max(prefixed, key=lambda r: len(r[1])) if prefixed else None



def _quote(text: str, limit: int = 240) -> str:
    """The requirement as quoted in the matrix: whole when short, else its
    first ``limit`` characters marked as cut, so a quote never seems to end
    where the requirement does not (the full text is in requirements/)."""
    return text if len(text) <= limit else text[:limit - 5].rstrip() + " [...]"

def build() -> int:
    rules = _rules()
    rows, missing, used = [], [], set()
    for standard, filename in FILES.items():
        with open(ROOT / "requirements" / filename, encoding="utf-8") as f:
            requirements = list(csv.DictReader(f))
        for req in requirements:
            row = {"standard": standard, "ID": req["ID"], "clause": req["clause"], "level": req["level"],
                   "requirement_text": _quote(req["requirement_text"]), "applicability": req["applicability"]}
            if req["applicability"] in _TAILORED_OUT:
                reason = {"Not requested": "OCM out of scope (user decision 2026-10-08)",
                          "Deleted": "deleted in this issue"}.get(req["applicability"], req["basis"])
                row.update(status=STATUS["NA"], evidence="-", gap="-", proposed_fix="-", effort="-",
                           near_basilisk="-", remediation="", assessed_by=f"Phase 0 tailoring: {reason}")
            else:
                rule = _match(rules[standard], req["ID"])
                if rule is None:
                    missing.append(f"{standard} {req['ID']}")
                    continue
                used.add((standard, rule[1]))
                _std, match, status, evidence, gap, fix, effort, near, remediation = rule
                deviations = re.findall(r"D-0\d", remediation)
                if deviations and status in ("N", "P"):
                    fix = (f"Deviation {', '.join(deviations)} selected by the user 2026-10-08 "
                           "(compliance/deviations.md; signature pending)")
                row.update(status=STATUS[status], evidence=evidence, gap=gap, proposed_fix=fix, effort=effort,
                           near_basilisk=near, remediation=remediation, assessed_by=f"rule {match}")
            rows.append(row)
    if missing:
        print(f"{len(missing)} applicable requirement(s) without an assessment:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        return 1
    unused = [f"{r[0]} {r[1]}" for std in rules for r in rules[std] if (std, r[1]) not in used]
    with open(ROOT / "compliance_matrix.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"compliance_matrix.csv: {len(rows)} rows")
    totals = collections.Counter((r["standard"], r["status"]) for r in rows)
    for standard in FILES:
        counts = ", ".join(f"{STATUS[k]}: {totals[(standard, STATUS[k])]}" for k in STATUS
                           if totals[(standard, STATUS[k])])
        print(f"  {standard}: {counts}")
    if unused:
        print(f"note: {len(unused)} rule(s) matched nothing: {', '.join(unused)}")
    return 0


if __name__ == "__main__":
    sys.exit(build())
