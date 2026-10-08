# Compliance work -- progress

Branch: `compliance/ecss-ccsds-audit`, created from
`claude/awesome-knuth-2vlhqu` at a3e6b8a89.

## Configuration under audit

| Item | Value |
|---|---|
| SpaceMissionStudio | `SpaceMissionStudio/` in this repository, at the branch point above |
| Basilisk in this repository (`docs/source/bskVersion.txt`) | 2.13.0b0, last `src/` commit c1bf0d7d6 (2026-10-02) |
| Basilisk the tests ran against | `bsk` 2.12.0 (a separate installed build, not built from this repository's `src/`) |

The two Basilisk versions differ. Which one the tool is qualified with
is a configuration-management decision (Phase 1 records it as a gap).
Basilisk is not modified by this work.

## Baseline test run (before any change)

Command: `pytest tests/ -q -n 3` (Basilisk 2.12.0, offscreen Qt), on the
branch point.

Result: **2055 passed, 11 skipped, 0 failed** (245 s, 3 workers). Every later phase re-runs this and reports differences.

## Phases

| Phase | Status |
|---|---|
| 0 Requirements extraction and tailoring | done; **criticality category C approved by the user (2026-10-08)**; OCM confirmed out of scope |
| 1 Audit and gap analysis | done: `gap_analysis.md`, `compliance_matrix.csv` (2084 rows); plan and D1-D8 **approved by the user (2026-10-08)** |
| 2 Implementation | done: R01-R12 (`phase2_log.md`); deviations D-01 to D-07 (`deviations.md`) |
| 3 Verification and validation | done: V-01 to V-08 within tolerance (`phase3_log.md`, `tests/validation/`); findings F-01 to F-08, two Basilisk accuracy defects corrected in the tool (F-01, F-07) |
| 4 Documentation | not started |

## Decisions recorded

1. 2026-10-08, user: criticality category **C** approved.
2. 2026-10-08, user: the CCSDS OCM is **out of scope** (OPM, OMM, OEM only).
3. ECSS-Q-ST-30 / ECSS-Q-ST-40 not supplied: the classification is the
   user's decision, recorded above, not justified against them here.
4. 2026-10-08, user: Phase 1 remediation plan (R01-R15) approved and the
   recommendations for D1-D8 accepted (`gap_analysis.md` section 8):
   D1 AD10/MSFC only, deviation D-01; D2 WMM2025, deviation D-04; D3
   deviations D-02, D-03, D-05, D-06 accepted; D4 GM per IERS TN36 if the
   values can be sourced, else deviation D-07; D5 qualify Basilisk 2.12.0,
   pinned and checked at start-up; D6 CCSDS KVN first, XML when schemas are
   available; D7 REF_FRAME EME2000 for Earth-centred data, SPICE J2000
   equivalence documented in the CSD; D8 security assurance level low.
5. 2026-10-08, user: after the audit, and a review and update of the whole
   tool, the UX/UI guidelines (`UX_UI_Guidelines_for_SpaceMissionStudio.md`,
   2026-10-08) are applied. Not part of this audit.
6. 2026-10-08, user: Earth GM stays 398600.436 km^3/s^2 (Basilisk's) under
   deviation D-07 (Phase 3 finding F-02); templates 04, 05, 07, 08 and 21
   keep their gravity degree (the 4.2.1b Explain-tab note stays).

## Phase 1 test run

No code changed in Phase 1 (documents, CSVs and the `compliance/` build
scripts only). The suite was re-run on the Phase 1 commit; results are in
the table below.

| Run | Passed | Skipped | Failed |
|---|---|---|---|
| Baseline | 2055 | 11 | 0 |
| After Phase 1 | 2055 | 11 | 0 (no difference) |
| After Phase 2 (R01-R12) | 2188 | 11 | 0 (133 new tests; changed expectations listed in `phase2_log.md`) |
| After Phase 3 (R13) | 2209 | 11 | 0 (21 new tests; changed expectations listed in `phase3_log.md`) |

## Resuming

The standards' text is not in the repository. To resume, extract it again
(see `README.md`) and re-run `tools/extract_requirements.py`; the CSVs are
deterministic, so a diff shows any change.
