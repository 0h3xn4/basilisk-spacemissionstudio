# Phase 0 -- Requirements extraction and criticality tailoring

Status: **complete. Criticality category C approved by the user on 2026-10-08; the CCSDS OCM confirmed out of scope.**

## 1. Extraction

| Standard (edition) | Requirements | Notes |
|---|---|---|
| ECSS-E-ST-40C Rev.1 | 783 | every EARM ID in the text (783) extracted; 503 are DRD contents (Annexes B-P, T) |
| ECSS-Q-ST-80C Rev.2 | 347 | every EARM ID (347); 51 are DRD contents (Annexes B, C); 3 are `<<deleted>>` |
| ECSS-E-ST-10-04C Rev.1 | 152 | every EARM ID (152); 13 deleted, 13 are normative data tables |
| ECSS-E-ST-10-09C | 92 | no EARM IDs in this 2008 issue: clause + letter; 87 "shall" and 5 "should"; clause 5 and the CSD DRD (Annex A) |
| CCSDS 502.0-B-3 | 710 | 286 numbered paragraphs with "shall" (262) or "should" (24), and 424 items of the Annex A Implementation Conformance Statement requirements lists (92 mandatory, 87 conditional, 245 optional) |

Checks run on the result: no duplicate IDs in any file; every EARM ID found
in the text appears once in the CSV; every ECSS-E-ST-40C requirement listed
in Table R-1 carries its A-D cells.

## 2. Criticality category: proposal

**Category C** (proposed here, approved by the user on 2026-10-08).

ECSS-Q-ST-80C Rev.2 Table D-1 defines the categories from the category of
the functions the software is involved in and whether compensating
provisions exist:

* C = "Software involved in category II functions AND: at least one of the
  following compensating provisions is available, ... An operational
  procedure", or "Software involved in category III functions AND: no
  compensating provisions exist".
* D = "Software involved in category III functions AND: at least one of the
  following compensating provisions is available", or "Software involved in
  category IV functions AND: no compensating provisions exist".

Justification:

* SpaceMissionStudio is ground software for mission analysis and design:
  orbit propagation, attitude and environment simulation, lifetime and
  disposal checks, delta-V and propellant budgets. It runs no flight or
  operational function and commands nothing.
* Its outputs feed design decisions, e.g. propellant to load and whether a
  disposal meets the 5-year rule. A wrong budget that went unnoticed could
  degrade or shorten a mission. That is the kind of failure consequence the
  function categories grade.
* The usual compensating provision for mission-analysis results is an
  operational procedure: an independent check (review, a second tool) before
  a result is used for a design or operational decision.

If the functions it supports are category II with that procedure in place,
or category III without it, Table D-1 gives C either way. Category D would
need category III functions with the independent check, or category IV.

What decides it, and what I could not check:

* ECSS-Q-ST-80C 6.2.2.1a: "For the system-level analyses leading to the
  criticality classification of software products based on the severity of
  failures consequences, ECSS-Q-ST-40 clause 6.5.6.3, and ECSS-Q-ST-30
  clause 5.4, shall apply." The function categories I-IV are defined there.
  **ECSS-Q-ST-30 and ECSS-Q-ST-40 were not supplied**, so this proposal
  cannot cite their severity definitions. The classification itself is a
  system-level, human decision (expected output: "Criticality
  classification of software products [PAF, -; SRR, PDR]").
* Whether an independent check of the tool's results is a documented
  procedure in the projects that use it.

What the choice changes (cells of Table R-1 / Table D-2):

| | ECSS-E-ST-40C (278 rows in Table R-1) | ECSS-Q-ST-80C (293 rows in Table D-2) |
|---|---|---|
| C instead of D | 15 more apply, e.g. 5.8.3.5a software code verification, 5.5.4.1a/5.5.4.2a software integration and its test plan, 5.8.3.11a schedulability analysis | 68 more apply, e.g. 5.6.1.1a methods and tools (for D: only if used before on a project), 5.7 process assessment and improvement, 6.2.2.2-6.2.2.7 software dependability and safety analysis, 6.2.3 handling of critical software |
| B instead of C | 25 more apply, e.g. 5.4.2.3 software logical model, 5.8.3.13a behaviour verification on that model, 5.5.2.5 real-time dynamic design model (Ytba for C) | 7 more, e.g. 6.2.6.13a "Independent software verification shall be performed by a third party", 6.2.3.7a tests re-run on non-instrumented code |

## 3. Tailoring applied

* ECSS-E-ST-40C: Table R-1 ("For tailoring of this standard based on
  software criticality categories, Table R-1 shall be applied",
  ECSS-E-ST-40_0860664). Rows given only per expected output ("eo a" ...)
  take the common value of those rows. The code-coverage rows 5.8.3.5b and
  5.8.3.5e defer to the note under the table; that pointer is kept.
* ECSS-Q-ST-80C: Table D-2, applied per clause. Security clauses 6.2.9 and
  6.2.10 are "To be applied based on security assurance and sensitivity
  levels." for every category; they are marked conditional.
* DRD contents (ECSS-E-ST-40C Annexes B-P, T; ECSS-Q-ST-80C Annexes B, C)
  are not in the matrices; they apply wherever the document they define is
  required, and are marked "Applicable via the <document> DRD".
* ECSS-E-ST-10-09C, ECSS-E-ST-10-04C and CCSDS 502.0-B-3 have no
  criticality tailoring; their applicability follows from what the tool
  models and exchanges (section 4).

## 4. Applicability rules (first pass)

* **ECSS-E-ST-10-04C** by clause: gravity (4), geomagnetic fields (5),
  electromagnetic radiation and indices (6, Annex A) and the Earth's
  neutral atmosphere (7) apply. Plasmas (8), energetic particles (9,
  Annex B), debris and meteoroids (10, Annex C) and contamination (11) are
  not applicable: the tool does not model them. Planetary atmospheres
  (7.2.3) need review: only the Earth's is modelled.
* **ECSS-E-ST-10-09C**: everything applies. The process and documentation
  clauses (5.2) are read for the tool's own frames and time scales (its
  Coordinate Systems Document). Mechanical frames (5.4.5) apply partially.
* **CCSDS 502.0-B-3**: OPM, OMM and OEM (sections 3, 4, 5), the KVN syntax
  (7) and the XML instantiation (8) apply, with their ICS items. The OCM
  (section 6, 8.11, ICS A2.5.4) was not requested and is marked "Not
  requested" (confirmed by the user).
* **ECSS-E-ST-40C / -Q-ST-80C**: the category C cell; requirements that
  mention flight or on-board aspects (in-flight modification, real-time,
  HW/SW co-engineering, ...) are marked "Review" for the intended use.

## 5. Flags (ambiguous or not found)

1. ECSS-Q-ST-30 and ECSS-Q-ST-40, which define the function categories
   behind Table D-1, were not supplied (section 2).
2. ECSS-Q-ST-80C 6.2.3.1 is `<<deleted>>` and absent from Table D-2; 6.3.7.4
   is absent from Table D-2 (6.3.7.1-3 and 6.3.7.5-7 are listed). Its
   applicability needs a decision.
3. ECSS-E-ST-40C and -Q-ST-80C split responsibilities between customer and
   supplier. For this tool you act as both. Phase 1 assigns customer-side
   requirements to you as human actions.
4. The editions supplied are newer than the bare titles in the task:
   ECSS-E-ST-40C Rev.1 and -Q-ST-80C Rev.2 (both April 2025),
   -E-ST-10-04C Rev.1 (2020), CCSDS 502.0-B-3 (2023, which adds the OCM).
5. No EARM spreadsheet was supplied. The IDs come from the standards'
   own EARM identifiers (ECSS) and paragraph/ICS numbering (CCSDS).
6. `type` and `applicability` are rule-based first passes, not decisions.
