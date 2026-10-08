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
"""Extract the requirements of the five standards the compliance audit
covers into ``compliance/requirements/<standard>.csv``.

Usage::

    python compliance/tools/extract_requirements.py <dir with the text files>

The input is the text of each standard, one file per standard, extracted
from the PDFs page by page with pages joined by ``=== PAGE BREAK ===``
(the PDFs are licensed documents and are not kept in this repository):

* ``ECSS-E-ST-40C.txt`` (Rev.1, 30 April 2025), ``ECSS-Q-ST-80C.txt``
  (Rev.2, 30 April 2025), ``ECSS-E-ST-10-04C.txt`` (Rev.1, 15 June 2020):
  each requirement carries its EARM identifier (e.g.
  ``ECSS-E-ST-40_0860001``) on the line before its text; the ID used here
  is the clause plus the requirement letter (``5.2.2.1a``), the form
  ECSS-E-ST-40C Table R-1 uses.
* ``ECSS-E-ST-10-09C.txt`` (31 July 2008): no EARM identifiers; the ID is
  the clause plus the letter.
* ``CCSDS_502.0-B-3.txt`` (April 2023): numbered paragraphs that contain
  "shall" (binding) or "should" (recommended), plus every item of the
  Annex A Implementation Conformance Statement requirements lists
  (keyword, reference, M/O/C status).

Criticality applicability (columns ``crit_A`` .. ``crit_D``) comes from
ECSS-E-ST-40C Table R-1 and ECSS-Q-ST-80C Table D-2. The ``type`` and
``applicability`` columns are a first, rule-based pass (``basis`` says
which rule); the gap analysis reviews them requirement by requirement.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "requirements"
COLUMNS = ("ID", "clause", "requirement_text", "type", "applicability", "earm_id", "level",
           "crit_A", "crit_B", "crit_C", "crit_D", "basis", "page")
MAX_TEXT = 500  # [chars] longer requirement texts are abbreviated (marked "...")

_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
                         " ": " ", "‘": "'", "’": "'", "“": '"', "”": '"'})
_HEADING = re.compile(r"^((?:\d+|[A-Z])(?:\.\d+)+|\d+)\s+([A-Z<][^\n]*)$")
# Q-ST-80C's untitled clauses: "5.1.2.1 ." (a line ending "... of clause 5.6.4.1." is text)
_BARE_HEADING = re.compile(r"^((?:\d+|[A-Z])(?:\.\d+)+)\s+\.\s*$")
_DRD_SECTION = re.compile(r"^<(\d+(?:\.\d+)*)>\s+([A-Z<].*)$")  # capital: not a NOTE's "<5.2> to <5.17> below."  # DRD annexes: "<4.2> Environmental ..."
_EARM = re.compile(r"^(ECSS-[EQ]-ST-[\d-]+_\d+)\s*$")
_LETTER = re.compile(r"^([a-z])\.\s+(.*)$")
_TOC = re.compile(r"\.{4,}")


def _pages(path: Path):
    text = path.read_text(encoding="utf-8").translate(_DASHES)
    return text.split("=== PAGE BREAK ===")


def _clean_lines(page: str, header_patterns):
    """The page's lines without running headers, footers and page numbers."""
    lines = []
    for raw in page.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or any(p.match(line) for p in header_patterns):
            continue
        lines.append(line)
    return lines


def _level(text: str) -> str:
    """The verbal form (ECSS: shall = requirement, should = recommendation, may = permission)."""
    for word in ("shall", "should", "may"):
        if re.search(rf"\b{word}\b", text):
            return word
    return ""


def _abbreviate(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(\w) -(\w)", r"\1-\2", text)  # pypdf splits hyphenated words: "co -engineering"
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT - 3].rstrip() + "..."


# -- classification (first pass; reviewed in the gap analysis) -------------------

def classify(text: str, clause: str, standard: str) -> str:
    t = text.lower()
    if clause[:1].isalpha() and standard in ("E-ST-40C", "Q-ST-80C", "E-ST-10-09C") and clause[:1] not in "R":
        return "documentation"  # DRD annexes
    if standard in ("E-ST-10-04C", "CCSDS-502.0-B-3"):
        if re.search(r"\b(document|report|record|specif(y|ied) in the)\b", t) and "shall be documented" in t:
            return "documentation"
        return "functional"
    if standard == "E-ST-10-09C" and clause.startswith("5.4"):
        return "functional"
    if re.search(r"\b(shall (be )?(produce|document|report|record|include)|documented|\bdocument\b|plan\b|drd)", t):
        return "documentation"
    if re.search(r"\b(the software|source code|code shall|software product shall|executable|coding standard)\b", t):
        return "product"
    return "process"


# -- ECSS documents with EARM identifiers -----------------------------------------

def parse_ecss_earm(path: Path, standard: str, doc_header: str):
    headers = [re.compile(re.escape(doc_header)), re.compile(r"^\d{1,2} \w+ \d{4}$"), re.compile(r"^\d{1,3}$")]
    rows, clause, section, current, page_no = [], "", "", None, 0
    stop_markers = ("NOTE", "EXPECTED OUTPUT")

    def flush():
        nonlocal current
        if current is None:
            return
        body = current["lines"]
        letter, text = "", ""
        if body:
            m = _LETTER.match(body[0])
            if m:
                letter = m.group(1)
                body = [m.group(2)] + body[1:]
            main, rest = [], []
            target = main
            for line in body:
                if line.startswith(stop_markers):
                    target = rest
                target.append(line)
            text = " ".join(main)
            expected = " ".join(rest)
            eo = re.search(r"EXPECTED OUTPUT:?\s*(.*)", expected)
            if eo:
                text += " [Expected output: " + eo.group(1) + "]"
        where = current["clause"] + (f"<{current['section']}>" if current["section"] else "")
        rid = f"{where}{letter}" if letter else f"{where} ({current['earm']})"
        rows.append({"ID": rid, "clause": current["clause"], "requirement_text": _abbreviate(text),
                     "earm_id": current["earm"], "level": _level(text), "page": current["page"]})
        current = None

    for page_no, page in enumerate(_pages(path), start=1):
        for line in _clean_lines(page, headers):
            if _TOC.search(line):
                continue
            m = _EARM.match(line)
            if m:
                flush()
                current = {"earm": m.group(1), "clause": clause, "section": section, "lines": [], "page": page_no}
                continue
            h = _HEADING.match(line)
            bare = _BARE_HEADING.match(line)
            if bare or (h and not line.endswith((".", ";", ",")) and len(h.group(2)) < 120):
                flush()
                clause, section = (bare or h).group(1), ""
                continue
            d = _DRD_SECTION.match(line)
            if d and clause[:1].isalpha():
                flush()
                section = d.group(1)
                continue
            if current is not None:
                current["lines"].append(line)
    flush()
    for row in rows:
        row["type"] = classify(row["requirement_text"], row["clause"], standard)
    return rows


# -- ECSS-E-ST-10-09C (2008): clause + letter -------------------------------------

def parse_ecss_letters(path: Path, standard: str, doc_header: str):
    headers = [re.compile(r"^" + re.escape(doc_header) + r"$"), re.compile(r"^\d{1,2} \w+ \d{4}$"),
               re.compile(r"^\d{1,3}$")]
    rows, clause, section, current, in_requirements = [], "", "", None, False

    def flush():
        nonlocal current
        if current is None:
            return
        main = []
        for line in current["lines"]:
            if line.startswith("NOTE"):
                break
            main.append(line)
        where = current["clause"] + (f"<{current['section']}>" if current["section"] else "")
        rows.append({"ID": f"{where}{current['letter']}", "clause": current["clause"],
                     "requirement_text": _abbreviate(" ".join(main)), "earm_id": "", "level": "shall",
                     "page": current["page"]})
        current = None

    for page_no, page in enumerate(_pages(path), start=1):
        for line in _clean_lines(page, headers):
            if _TOC.search(line):
                continue
            h = _HEADING.match(line)
            if h and not line.endswith((".", ";", ",")) and len(h.group(2)) < 120:
                flush()
                clause, section = h.group(1), ""
                # requirements: clause 5 and the normative Annex A (the CSD DRD)
                in_requirements = clause.startswith("5.") or clause.startswith("A.")
                continue
            d = _DRD_SECTION.match(line)
            if d and clause.startswith("A."):
                flush()
                section = d.group(1)
                continue
            if line.startswith("Annex B"):
                flush()
                in_requirements = False
            m = _LETTER.match(line)
            if in_requirements and m:
                flush()
                current = {"clause": clause, "section": section, "letter": m.group(1), "lines": [m.group(2)],
                           "page": page_no}
            elif current is not None:
                if line.startswith("NOTE"):
                    current["lines"].append(line)  # kept out of the text by flush()
                else:
                    current["lines"].append(line)
    flush()
    rows = [r for r in rows if re.search(r"\bshall\b", r["requirement_text"])]
    for row in rows:
        row["type"] = classify(row["requirement_text"], row["clause"], standard)
    return rows


# -- CCSDS 502.0-B-3 --------------------------------------------------------------

_CCSDS_HEADERS = [re.compile(r"^CCSDS RECOMMENDED STANDARD FOR ORBIT DATA MESSAGES$"),
                  re.compile(r"^CCSDS 502\.0-B-3 Page [\w-]+ April 2023$")]
_CCSDS_PARA = re.compile(r"^(\d+(?:\.\d+)+)\s+(.*)$")


def parse_ccsds(path: Path):
    pages = _pages(path)
    rows, current = [], None
    in_annex = False

    def flush():
        nonlocal current
        if current is None:
            return
        text = " ".join(current["lines"])
        text = re.split(r"\bNOTES?\b\s*[-–]", text)[0]
        level = "shall" if re.search(r"\b(shall|must)\b", text) else ("should" if re.search(r"\bshould\b", text)
                                                                       else "")
        same = [r for r in rows if r["clause"] == current["para"]]
        if same and level:  # the same paragraph resumed after a table: one row
            same[0]["requirement_text"] = _abbreviate(same[0]["requirement_text"] + " " + text)
        elif level:
            rows.append({"ID": f"CCSDS-502.0-B-3 {current['para']}", "clause": current["para"],
                         "requirement_text": _abbreviate(text), "earm_id": "", "level": level,
                         "page": current["page"]})
        current = None

    ics_lines = []
    for page_no, page in enumerate(pages, start=1):
        for line in _clean_lines(page, _CCSDS_HEADERS):
            if _TOC.search(line):  # before the annex test: the contents list the annexes too
                continue
            if re.fullmatch(r"ANNEX [A-J]", line):  # the annex itself (its title follows on the next line)
                flush()
                in_annex = True
            if in_annex:
                ics_lines.append((page_no, line))
                continue
            m = _CCSDS_PARA.match(line)
            # a paragraph starts with a capital ("7.5.10 for formatting rules.)" is a wrapped table cell)
            if m and not m.group(2)[:1].isupper() and not m.group(2).startswith(("'", '"')):
                m = None
            if m and not re.match(r"^\d+(\.\d+)+\s+[A-Z][A-Z /'&,\-()]+$", line):  # skip section titles
                flush()
                current = {"para": m.group(1), "lines": [m.group(2)], "page": page_no}
            elif m:
                flush()
            elif current is not None:
                if line.startswith(("Table ", "Figure ")):
                    flush()
                else:
                    current["lines"].append(line)
    flush()
    rows = [r for r in rows if not r["clause"].startswith(("1.", "2."))
            or re.search(r"\bshall\b", r["requirement_text"])]
    for row in rows:
        row["type"] = classify(row["requirement_text"], row["clause"], "CCSDS-502.0-B-3")
    rows.extend(_parse_ics(ics_lines))
    return rows


_ICS_ROW = re.compile(r"^(\d+)\s+(.*?)\s+(N/A|[A-Z][A-Z0-9_]*(?:\s*\[[^\]]*\])?|[A-Z][A-Za-z0-9_]*_x)\s+"
                      r"((?:Table|Section|Annex|Sec\.)\s*[\w.\-]+|[\d.]+[\w.\-]*)\s+(M|O|C|X)\s*$")
_ICS_LISTS = {"A2.5.1": "OPM", "A2.5.2": "OMM", "A2.5.3": "OEM", "A2.5.4": "OCM"}


def _parse_ics(lines):
    rows, message, section, buffer, start_page = [], None, "", [], 0
    for page_no, line in lines:
        head = re.match(r"^(A2\.5\.\d+(?:\.\d+)?)\s+(.*)$", line)
        if head:
            buffer = []
            section = head.group(1)
            message = _ICS_LISTS.get(section[:6], message)
            continue
        if line.startswith("ANNEX B"):
            break
        if message is None or line.startswith(("Item Feature", "Status", "M/O/C")):
            continue
        if re.match(r"^\d+\s", line) and not buffer:
            start_page = page_no
        if re.match(r"^\d+\s", line) or buffer:
            buffer.append(line)
            joined = " ".join(buffer)
            m = _ICS_ROW.match(joined)
            if m:
                item, feature, keyword, reference, status = m.groups()
                rows.append({"ID": f"ICS-{message}-{section[7:] + '.' if len(section) > 6 else ''}{item}",
                             "clause": f"Annex A {section}",
                             "requirement_text": _abbreviate(f"{message} {feature}: keyword {keyword}, "
                                                             f"{reference}, status {status}"),
                             "earm_id": "", "level": {"M": "mandatory", "O": "optional", "C": "conditional",
                                                      "X": "prohibited"}[status],
                             "type": "functional", "page": start_page})
                buffer = []
            elif len(buffer) > 8:  # not a row after all
                buffer = []
    return rows


# -- criticality matrices ------------------------------------------------------------

_CELL = {"Y", "N", "Ytba", "-"}


def _cells(text: str):
    """The A, B, C, D cells at the end of a matrix row: plain cells (Y, N,
    Ytba) as they are; a condition in their place fills the cells left
    (e.g. "Y Y Y Expected output not required" gives D that condition).
    None for a heading row ("- - - -") or a row without cells."""
    tokens = text.split()
    # a lone "-" is a dash in the description ("reuse - justification"); "- - - -" is a heading row
    start = next((i for i, t in enumerate(tokens)
                  if t in ("Y", "N", "Ytba") or (t == "-" and tokens[i:i + 4] == ["-"] * 4)), None)
    if start is None:
        return None
    cells = []
    i = start
    while i < len(tokens) and len(cells) < 4 and tokens[i] in _CELL:
        cells.append(tokens[i])
        i += 1
    if cells and all(c == "-" for c in cells):
        return None
    condition = " ".join(tokens[i:]).strip()
    while len(cells) < 4:
        cells.append(condition or "?")
    return tuple(cells)


def _matrix_rows(text: str, start_marker: str, end_marker: str, row_start: re.Pattern, skip: tuple):
    """(key, joined row text) for each row of a tailoring matrix."""
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    rows, key, buffer = [], None, []
    for raw in text[start:end].splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or line.startswith(skip) or re.fullmatch(r"\d{1,3}", line):
            continue
        m = row_start.match(line)
        if m:
            if key is not None:
                rows.append((key, " ".join(buffer)))
            key, buffer = m.group(1), [line[m.end():]]
        elif key is not None:
            buffer.append(line)
    if key is not None:
        rows.append((key, " ".join(buffer)))
    return rows


def tailoring_40c(path: Path):
    """``5.2.2.1a`` -> (A, B, C, D) from ECSS-E-ST-40C Table R-1. A
    requirement listed only per expected output ("5.4.2.1a eo a" ...) gets
    the common value of those rows, or a pointer to the table if they
    differ."""
    text = path.read_text(encoding="utf-8").translate(_DASHES)
    rows = _matrix_rows(text, "Table R-1: Criticality applicability", "Annex S",
                        re.compile(r"^(\d+(?:\.\d+)+[a-z](?: eo [a-z]+)?)\b"),
                        ("ECSS-E-ST-40C", "30 April", "===", "Requirement", "identification", "Expected Output"))
    plain, per_output = {}, {}
    for key, row in rows:
        cells = _cells(row)
        if cells is None and "See " in row:  # e.g. code coverage: "See 5.8.3.5b" (a note under the table)
            cells = tuple([f"see the note on {key} under Table R-1"] * 4)
        if cells is None:
            continue
        if " eo " in key:
            per_output.setdefault(key.split(" eo ")[0], []).append(cells)
        else:
            plain.setdefault(key, cells)
    for key, outputs in per_output.items():
        if key not in plain:
            plain[key] = outputs[0] if all(o == outputs[0] for o in outputs) else \
                tuple("per expected output (Table R-1)" for _ in range(4))
    return plain


def tailoring_80c(path: Path):
    """``5.2.7.2`` -> (A, B, C, D) from ECSS-Q-ST-80C Table D-2; a
    conditional cell keeps its text."""
    text = path.read_text(encoding="utf-8").translate(_DASHES)
    rows = _matrix_rows(text, "Table D-2: Applicability matrix", "Annex E (informative)",
                        re.compile(r"^(\d+(?:\.\d+)+)\b"), ("ECSS-Q-ST-80C", "30 April", "===",
                                                             "Clause Description"))
    table = {}
    for key, row in rows:
        cells = _cells(row)
        if cells is None and re.search(r"[a-z]{4,}", row) and not re.search(r"\s-\s-", row):
            # a heading row's description, or a condition for every category
            if row.strip().lower().startswith(("to be applied", "applicable", "not applicable")):
                cells = tuple([row.strip()] * 4)
        if cells is not None:
            table[key] = cells
    return table


def apply_tailoring(rows, table, by_letter: bool):
    for row in rows:
        key = row["ID"] if by_letter else row["clause"]
        cells = table.get(key)
        if cells is None and not by_letter:  # a clause row covering sub-clauses (e.g. "5.2.3 Audits")
            parts = row["clause"].split(".")
            while len(parts) > 1 and cells is None:
                parts = parts[:-1]
                cells = table.get(".".join(parts))
        if cells is not None:
            row["crit_A"], row["crit_B"], row["crit_C"], row["crit_D"] = cells


# -- applicability (first pass) -----------------------------------------------------------

_GROUND_TOOL_NA = re.compile(r"\b(on-?board|flight software|in[- ]flight|onboard|real-time|autocod|"
                             r"hardware/software co-engineering|hw/sw co-engineering|patch|"
                             r"operational and maintenance sites|maintenance site|system database|"
                             r"OBSW|space segment software)\b", re.I)


def applicability_software(row, category="C"):
    cell = row.get(f"crit_{category}", "")
    if cell == "N":
        return "Not applicable", f"criticality {category}: N in the tailoring matrix"
    if _GROUND_TOOL_NA.search(row["requirement_text"]):
        return "Review", f"criticality {category}: {cell or 'not in matrix'}; mentions flight/on-board aspects"
    if not cell:
        return "Review", "not found in the tailoring matrix"
    if cell in ("Y", "Ytba"):
        return "Applicable", f"criticality {category}: {cell}"
    return "Applicable (conditional)", f"criticality {category}: {cell}"


_E1004_SCOPE = (
    ("4", "Applicable", "gravity: spherical harmonics and third bodies are modelled"),
    ("5", "Applicable", "geomagnetic field: modelled for torque rods and magnetometers"),
    ("6", "Applicable", "solar flux and F10.7/Ap indices: drive SRP and the atmosphere"),
    ("7.2.3", "Review", "planetary atmospheres: only Earth's is modelled"),
    ("7", "Applicable", "neutral atmosphere: NRLMSISE-00 and exponential models"),
    ("8", "Not applicable", "plasma environments are not modelled (no charging analysis)"),
    ("9", "Not applicable", "energetic particle radiation is not modelled (no dose analysis)"),
    ("10", "Not applicable", "no impact-risk analysis (collision-avoidance counts are user inputs)"),
    ("11", "Not applicable", "contamination is not modelled"),
    ("A.", "Applicable", "normative annex: electromagnetic radiation and indices"),
    ("B.", "Not applicable", "normative annex: energetic particle radiation"),
    ("C.", "Not applicable", "normative annex: debris and meteoroids"),
)


def applicability_10_04(row):
    for prefix, verdict, why in _E1004_SCOPE:
        if row["clause"] == prefix or row["clause"].startswith(prefix + ("" if prefix.endswith(".") else ".")):
            return verdict, why
    return "Review", "clause outside the scope table"


def applicability_10_09(row):
    clause = row["clause"]
    if clause.startswith("5.2"):
        return "Applicable (tool scope)", "process/documentation requirement read for the tool's own frames"
    if clause.startswith("5.4.5"):
        return "Applicable (partial)", "mechanical frames: only the body frame B and facets are defined"
    return "Applicable", "the tool defines and transforms frames and time scales"


def applicability_ccsds(row):
    clause = row["clause"]
    rid = row["ID"]
    if clause.startswith("6") or "-OCM-" in rid or "8.11" == clause[:4]:
        return "Not requested", "OCM: not in the requested scope (OPM, OMM, OEM)"
    if clause.startswith(("3", "4", "5", "7", "8")) or rid.startswith("ICS-"):
        return "Applicable", "OPM/OMM/OEM and their KVN/XML syntax"
    return "Review", "general clause"


STANDARDS = (
    ("ECSS-E-ST-40C", "E-ST-40C", "ECSS-E-ST-40C Rev.1"),
    ("ECSS-Q-ST-80C", "Q-ST-80C", "ECSS-Q-ST-80C Rev.2"),
    ("ECSS-E-ST-10-04C", "E-ST-10-04C", "ECSS-E-ST-10-04C Rev.1"),
    ("ECSS-E-ST-10-09C", "E-ST-10-09C", "ECSS-E-ST-10-09C"),
    ("CCSDS_502.0-B-3", "CCSDS-502.0-B-3", None),
)


_DRD_DOCUMENTS = {  # annex letter -> document whose DRD it is
    "E-ST-40C": {"B": "SSS", "C": "IRD", "D": "SRS", "E": "ICD", "F": "SDD", "G": "SRelD", "H": "SUM", "I": "SVerP",
                 "J": "SValP", "K": "SUITP", "L": "SVS", "M": "SVR", "N": "SRF", "O": "SDP", "P": "SRevP",
                 "T": "SMP"},
    "Q-ST-80C": {"B": "SPAP", "C": "SPAMR"},
    "E-ST-10-09C": {"A": "CSD"},
}


def refine(row, standard: str) -> None:
    """Deleted requirements, data tables and DRD contents."""
    text = row["requirement_text"]
    if "<<deleted>>" in text.lower():
        row["type"], row["applicability"], row["basis"] = "deleted", "Deleted", "<<deleted>> in this issue"
        return
    if not row["level"] and re.match(r"^(Table|Figure) [A-Z]?[\d-]+", text):
        row["type"] = "table"
    document = _DRD_DOCUMENTS.get(standard, {}).get(row["clause"][:1]) if row["clause"][:1].isalpha() else None
    if document and row["clause"][1:2] == ".":
        row["type"] = "documentation"
        if standard != "E-ST-10-09C":
            row["applicability"] = f"Applicable via the {document} DRD"
            row["basis"] = f"content of the {document}; applies where the {document} is required"


def main(text_dir: Path) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    counts = {}
    for stem, short, header in STANDARDS:
        path = text_dir / f"{stem}.txt"
        if short == "CCSDS-502.0-B-3":
            rows = parse_ccsds(path)
        elif short == "E-ST-10-09C":
            rows = parse_ecss_letters(path, short, header)
        else:
            rows = parse_ecss_earm(path, short, header)
        if short == "E-ST-40C":
            apply_tailoring(rows, tailoring_40c(path), by_letter=True)
        elif short == "Q-ST-80C":
            apply_tailoring(rows, tailoring_80c(path), by_letter=False)
        for row in rows:
            if short in ("E-ST-40C", "Q-ST-80C"):
                verdict, why = applicability_software(row)
            elif short == "E-ST-10-04C":
                verdict, why = applicability_10_04(row)
            elif short == "E-ST-10-09C":
                verdict, why = applicability_10_09(row)
            else:
                verdict, why = applicability_ccsds(row)
            row["applicability"], row["basis"] = verdict, why
            refine(row, short)
        out = OUT_DIR / f"{stem.replace('_', '-')}.csv"
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({c: row.get(c, "") for c in COLUMNS})
        counts[out.name] = len(rows)
    for name, n in counts.items():
        print(f"{name}: {n} requirements")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
