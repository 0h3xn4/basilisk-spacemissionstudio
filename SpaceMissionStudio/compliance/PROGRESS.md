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
| 1 Audit and gap analysis | done: `gap_analysis.md`, `compliance_matrix.csv` (2084 rows); **awaiting approval of the remediation plan (section 9) and decisions D1-D8** |
| 2 Implementation | not started (waits on Phase 1 approval) |
| 3 Verification and validation | not started |
| 4 Documentation | not started |

## Decisions recorded

1. 2026-10-08, user: criticality category **C** approved.
2. 2026-10-08, user: the CCSDS OCM is **out of scope** (OPM, OMM, OEM only).
3. ECSS-Q-ST-30 / ECSS-Q-ST-40 not supplied: the classification is the
   user's decision, recorded above, not justified against them here.

## Phase 1 test run

No code changed in Phase 1 (documents, CSVs and the `compliance/` build
scripts only). The suite was re-run on the Phase 1 commit; results are in
the table below.

| Run | Passed | Skipped | Failed |
|---|---|---|---|
| Baseline | 2055 | 11 | 0 |
| After Phase 1 | 2055 | 11 | 0 (no difference) |

## Resuming

The standards' text is not in the repository. To resume, extract it again
(see `README.md`) and re-run `tools/extract_requirements.py`; the CSVs are
deterministic, so a diff shows any change.
