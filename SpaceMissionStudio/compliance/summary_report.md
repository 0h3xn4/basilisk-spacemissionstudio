# ECSS/CCSDS audit of SpaceMissionStudio: summary report

2026-10-08. Branch `compliance/ecss-ccsds-audit` of `0h3xn4/basilisk`.

**What this report claims, and what it does not:**
- It reports what was done and what the evidence shows.
- It does not claim that SpaceMissionStudio *complies* with any of the
  five standards. Most requirements are now partially met. The main gaps
  need people: reviews, signatures, an organisation, independent review.
  `human_actions.md` lists them.
- Every status below comes from `compliance_matrix.csv`, which lists the
  evidence for each requirement.

## 1 Scope

**Standards** (as supplied; IDs and text only from them):
- ECSS-E-ST-40C Rev.1;
- ECSS-Q-ST-80C Rev.2;
- ECSS-E-ST-10-09C;
- ECSS-E-ST-10-04C Rev.1;
- CCSDS 502.0-B-3.

ESA AD10 (EOP-FM/2024-07-177 v3.0) is cited by identifier only.

**Criticality and decisions:**
- category C (decision 1);
- the OCM is out of scope (decision 2);
- D1 to D8 (`PROGRESS.md`).

**Basilisk:**
- Reused, unmodified, as existing software in the sense of ECSS-Q-ST-80C.
- Pinned at **2.12.0** (PyPI); the version is checked at start-up and
  recorded in every run. The SRF records the release's SHA-256.
- Against `develop`, the branch changes only `SpaceMissionStudio/` and the
  tool's CI workflow; no Basilisk file
  (`git diff --name-only origin/develop HEAD`).

## 2 What was done

| Phase | Result |
|---|---|
| 0 | Every requirement extracted: 2089 rows in five CSVs; category C tailoring |
| 1 | Gap analysis and compliance matrix; remediation plan R01–R15; decisions D1–D8 approved |
| 2 | R01–R12: Basilisk pin; frame and time layer; TLE/SGP4; IERS-based Earth orientation; WGS-84 stations; environment constants; real space weather (D-01); WMM (D-04); CCSDS OPM/OMM/OEM; coding standard, CI, metrics, traceability |
| 3 | R13: validation against GMAT R2026a, IERS 20 C04, SOFA and the reused packages' tests (V-01, V-02, V-04 to V-08). Findings F-01 to F-08; two Basilisk accuracy defects corrected in the tool without modifying Basilisk (F-01 gravity, F-07 drag) |
| 4 | R14: 16 documents to their DRDs (all sections present, checked by `check_drds.py`), generated parts kept current by CI. R15: security analysis, with script-block consent, a safe condition evaluator, download and release checksums, and security lint. Human actions H01–H13. |

**Documents (`docs/`):**
- Requirements and design: SRS, ICD (+ generated field and CLI lists),
  SDD (+ generated components and traceability), CSD.
- Reuse: SRF.
- Plans: SVerP, SValP, SUITP (+ generated test cases).
- Specification and report: SVS (+ generated test cases), SVR.
- User and release: SUM, SRelD.
- Management: SDP (with a configuration management description), SMP.
- Product assurance: SPAP (outline), SPAMR.
- Security analysis.

**Not written:**
- SSS and IRD: customer documents, waived (decision 9, D-11).
- SRevP: not wanted, covered by the review waiver D-08 (decision 18).
- SCMP: its DRD is in ECSS-M-ST-40C, which will not be supplied; the
  configuration management is described in SDP 6 (decision 18).
- Software security management plan: waived (decision 8, D-10).

## 3 Compliance status

From `compliance_matrix.csv`. "Was" is after Phase 3; Phase 1 values are in
`gap_analysis.md`.

| Standard | Compliant | Partially | Non-compliant | Not applicable | Human/process action |
|---|---|---|---|---|---|
| ECSS-E-ST-40C | 45 (was 4) | 533 (was 86) | 165 (was 553) | 33 | 7 (was 107) |
| ECSS-Q-ST-80C | 12 (was 5) | 236 (was 96) | 22 (was 96) | 33 | 44 (was 117) |
| ECSS-E-ST-10-09C | 23 | 59 | 0 | 6 | 4 |
| ECSS-E-ST-10-04C | 9 | 4 | 17 | 122 | 0 |
| CCSDS 502.0-B-3 | 263 | 10 | 71 | 369 | 2 |

Counts as of the human-action decisions 7 to 19 (2026-10-08): a waived
requirement counts as non-compliant (with its deviation), and a decided
human action moves its rows out of the last column.

**How to read it:**
- Most of the E-ST-40C and Q-ST-80C change is the DRD contents.
  - A drafted document makes its DRD rows **partial**, not compliant:
    the documents are drafts and not reviewed.
  - Only the introduction, reference-document and terms sections are
    counted compliant, because their presence is verifiable.
- **E-ST-10-04C:** the 17 non-compliant rows are the reference values of
  Tables 6-3, 6-4 and A-1, the models Basilisk lacks, and the GM source.
  - 15 of them are covered by deviations D-01 to D-07, which are not yet
    signed (H08).
  - The other 2 are the table data of clause 6.3, which follow D-01.
    Their rule names R07 but no deviation.
- **CCSDS:** the 71 non-compliant rows are all clause 8, the XML formats
  (decision D6: KVN first).
- **Human/process actions** cannot be closed by software.

## 4 Verification and validation

**Tests:**
- Full suite: **2239 passed, 11 skipped, 0 failed**.
- The 11 skips are tests of behaviour without Basilisk.
- The earlier runs, with the same 11 skips throughout:
  - baseline before the audit: 2055 passed;
  - after Phase 2: 2188;
  - after Phase 3: 2209.
- No test was skipped, disabled or weakened to pass. Expectations that
  changed are recorded with their reason in `phase2_log.md`,
  `phase3_log.md` and the Phase 4 commits.

**Coverage and lint:**
- statement coverage 91.5 %, branch coverage 81.7 % (gate:
  90 % statements);
- lint: 0 findings, security rules included.

**Validation** (all within tolerance):

| Case | Result |
|---|---|
| V-01 time scales | TAI, TT 0.15 µs and 0.11 µs; TDB 34 µs |
| V-02 Earth frame | 0.43 m |
| V-04 propagation | two-body 0.004 m/day; 20 × 20 0.116 m/day; Sun/Moon 0.009 m/7 days; SRP 1.135 m/7 days; drag 0.78 km of 32 km |
| V-05 passes | 0.081 s |
| V-06 OEM exchange with GMAT | 8.4 mm |
| V-07, V-08 reused models | 294 and 49 tests passed |
| V-L lifetime | +0.9 % |

Two tolerances were revised, and are recorded as revisions: TDB, and drag.
There is no case V-03.

**CI:** the CI runs 1 to 3 of this branch failed, and their failures were
fixed in later commits. Runs 4 (Phase 3 head) and 5 (the first Phase 4
push, SRF commit) passed. Runs on the later Phase 4 commits were pending at
the time of writing.

## 5 Findings that change results

- **F-01 and F-07:** Basilisk defects, corrected in the tool. Every drag
  result changes:
  - template 18's spacecraft re-enters from 300 km after 34 days, not 25;
  - drag figures published earlier (5-year run, altitude trade, budgets)
    are out of date (SRelD K-01).
- **F-02:** the Earth GM is 398600.436 km³/s² (Basilisk's), under
  deviation D-07 (decision 6).
- **Security:** a scenario file could run code without the user's
  consent:
  - through `script_block` (S-01);
  - through the `eval` of conditions (S-02).

  Both are fixed: consent is now required, and conditions use a whitelist
  evaluator.

## 6 Open items

| Item | Where |
|---|---|
| Human actions H01–H13: reviews, PA organisation, customer baseline, criticality sign-off, problem and change control, independent code review, reuse acceptance, deviation signatures, thresholds, upstream reports, Vizard binding, missing documents, platform tests | `human_actions.md` |
| Known problems K-01 to K-09 | `docs/SRelD.md` 5.2 |
| Residual security risks S-05, S-06, S-08, S-12 | `docs/security_analysis.md` |
| Unexplained 1.6 % in the drag validation | `phase3_log.md` |

## 7 Next steps (planned)

1. The whole-tool review and update, starting from the known problems:
   re-measure K-01, investigate K-08.
2. Then the UX/UI guidelines (decision 5).
