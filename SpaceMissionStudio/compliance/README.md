# ECSS / CCSDS compliance work

Audit, review and update of SpaceMissionStudio against five standards, as
far as software and documentation can achieve. Basilisk is reused,
unmodified software throughout (ECSS-Q-ST-80C reuse); nothing here changes
it.

| Standard | Edition used | Requirements file |
|---|---|---|
| ECSS-E-ST-40C Software | Rev.1, 30 April 2025 | `requirements/ECSS-E-ST-40C.csv` (783) |
| ECSS-Q-ST-80C Software product assurance | Rev.2, 30 April 2025 | `requirements/ECSS-Q-ST-80C.csv` (347) |
| ECSS-E-ST-10-09C Reference coordinate systems | 31 July 2008 | `requirements/ECSS-E-ST-10-09C.csv` (92) |
| ECSS-E-ST-10-04C Space environment | Rev.1, 15 June 2020 | `requirements/ECSS-E-ST-10-04C.csv` (152) |
| CCSDS 502.0-B Orbit Data Messages | B-3, April 2023 | `requirements/CCSDS-502.0-B-3.csv` (715) |

The task named the standards without issue; the editions above are the
ones supplied, and every requirement ID and text here comes from them.

## Layout

* `requirements/` -- every requirement, one CSV per standard (Phase 0).
* `phase0_tailoring.md` -- criticality category proposal and tailoring.
* `PROGRESS.md` -- where the work stands, to resume across sessions.
* `tools/extract_requirements.py` -- regenerates the CSVs from the
  standards' text.

Later phases add `gap_analysis.md`, `compliance_matrix.csv`, the
traceability matrix, the deviation list and `docs/` (the DRD-based
documents).

## Requirement CSV columns

| Column | Meaning |
|---|---|
| `ID` | ECSS: clause + letter (`5.2.2.1a`), the form ECSS-E-ST-40C Table R-1 uses; DRD contents add the DRD section (`D.2.1<5.2>a`). CCSDS: `CCSDS-502.0-B-3 <paragraph>`, and `ICS-<message>-<item>` for the Annex A conformance items. |
| `clause` | clause or paragraph of the standard |
| `requirement_text` | the text, abbreviated past 500 characters ("..."); the expected output appended for ECSS |
| `type` | process / product / functional / documentation (also: deleted, table) -- first pass, rule-based |
| `applicability` | first pass for the intended use and the proposed criticality category C; `basis` says which rule decided it |
| `earm_id` | the ECSS EARM identifier (ECSS-E-ST-40C, -Q-ST-80C, -E-ST-10-04C) |
| `level` | shall / should / may (ECSS); shall / should, or mandatory / optional / conditional for CCSDS conformance items |
| `crit_A` .. `crit_D` | ECSS-E-ST-40C Table R-1 and ECSS-Q-ST-80C Table D-2 cells, conditions kept as text |
| `page` | page of the PDF the requirement starts on |

`type` and `applicability` are a first pass: the gap analysis (Phase 1)
reviews them requirement by requirement and records the final decision in
`compliance_matrix.csv`.

## Regenerating the CSVs

The standards are licensed documents and are not kept in this repository.
Extract their text page by page (pages joined by `=== PAGE BREAK ===`, one
file per standard named as in `STANDARDS` in the tool), e.g. with pypdf:

```python
import pypdf
reader = pypdf.PdfReader("ECSS-E-ST-40C.pdf")
reader.decrypt("")  # the ECSS and CCSDS PDFs carry permission-only encryption
text = "\n\n=== PAGE BREAK ===\n\n".join(page.extract_text() or "" for page in reader.pages)
```

then run `python compliance/tools/extract_requirements.py <text dir>`.
