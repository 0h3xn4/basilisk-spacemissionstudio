# SpaceMissionStudio: Software Product Assurance Milestone Report (SPAMR)

DRD: ECSS-Q-ST-80C Annex C
Document: SMS-SPAMR, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft, written by the supplier at the end of the ECSS/CCSDS
audit, the first milestone with PA reporting.
- No PA function exists (H02). This report is therefore not independent.
- It states the evidence and leaves judgement to the reviewers (H01).

## 1 Introduction (C.2.1<1>)

This report gives the product assurance status of SpaceMissionStudio at
the end of the audit:
- the verification done;
- the methods and tools;
- adherence to standards;
- metrics;
- testing;
- problems.

## 2 Applicable and reference documents (C.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | SPAP (`SPAP.md`) |
| RD1 | SVR (`SVR.md`) |
| RD2 | `compliance/metrics.md` and `metrics.json` (generated) |
| RD3 | `compliance/compliance_matrix.csv`; `compliance/summary_report.md` |
| RD4 | SRelD (`SRelD.md`), known problems K-01 to K-09 |
| RD5 | `compliance/human_actions.md` |

## 3 Terms, definitions and abbreviated terms (C.2.1<3>)

As in the SPAP.

## 4 Verification activities performed (C.2.1<4>)

| Activity | Done | Result |
|---|---|---|
| Reviews | None held (H01) | – |
| Inspections | The supplier inspected the code and documents during the audit: Phases 1 to 4 | Findings F-01 to F-08 (`phase3_log.md`); S-01 to S-12 (security analysis); corrections recorded in the commits. The Phase 4 inspection of documents against code found and corrected: the ICD's CLI table and exit codes, the SRF's citation of 5.4.3.1, an unused V-03 identifier claimed as done, the SDD's description of logging and plotting, and the manual's package name. |
| Walk-throughs | None | – |
| Audits | This ECSS/CCSDS audit (by the supplier, not independent) | `compliance/` |
| Testing | Full suite and validation | RD1 4.6 |

**Critical software:** the whole tool, being category C (Q-ST-80C 3.2.8;
decision 10). The measures and their verification status are in
`dependability_safety_analysis.md` section 4. The supplier verified them;
there is no independent verification (H06). The unreachable-code analysis
is open.

## 5 Methods and tools (C.2.1<5>)

**Suitability:**
- The methods and tools are standard: Python, pytest, ruff, git and
  GitHub Actions (SDP 5.3, 5.4).
- The validation shows that they produced software meeting its
  performance requirements in the cases tested (RD1).

**Correct use:**
- CI runs them on every change.
- The CI history of the audit branch, with runs 1 to 3 failing:
  - Run 3 failed with 2 test failures, 1 error and statement coverage
    of 88.7 %. Runs 4 (the Phase 3 head) and 5 (the first Phase 4 push)
    passed.
  - The failures of runs 1 to 3 were corrected in the following commits.
  - Run 3's log also shows tracebacks from a GUI timer, though no test
    fails on them (K-08).

## 6 Adherence to design and coding standards (C.2.1<6>)

| Standard | Adherence |
|---|---|
| Coding standard C-1 to C-15 | Lint: 0 findings, security rules included. Complexity: 19 functions above 15, all pre-existing. Docstrings: present on public modules; 988 of 1488 unit and integration test functions have none (rule C-9 applies to new tests). |
| Units on physical literals (AGENTS.md rule 1) | Applied to new code; not audited over legacy code |
| DRD structure of the documents | `check_drds.py`: 16 documents, 0 problems |

## 7 Product and process metrics (C.2.1<7>)

From `metrics.py` on this milestone's code and coverage run (RD2):

| Metric | Value | Target |
|---|---|---|
| Size, package (SLOC) | 29119 | – |
| Size, tests (SLOC) | 20862 | – |
| Functions | 1099 | – |
| Cyclomatic complexity, median / max | 2 / 79 | ≤ 15 for new code |
| Functions above 15 | 19 | not to grow |
| Statement coverage | 91.5 % | ≥ 90 % (met) |
| Branch coverage | 81.7 % | not set (H09) |
| Test functions / requirement-tagged | 1511 / 99 | – |
| Corrective commits (proxy) per kSLOC | 10 / 0.34 | – |

**Analyses:**
- Coverage has stayed above the gate since Phase 2; it dipped to 88.7 % in
  CI run 3 before the Phase 3 tests.
- The functions above complexity 15 are refactoring candidates (rule C-7).
  Refactoring them was outside the audit's scope.

**Corrective actions:** the new evaluator was refactored during this phase
to stay under 15 (SVR 4.5).

**Software maturity:**
- Maturity is not assessed by a maturity model.
- Indicators:
  - 2239 tests passing;
  - validation within tolerance;
  - nine known problems (RD4).

## 8 Testing and validation (C.2.1<8>)

**Adequacy of the test and validation documentation:**
- The SUITP and the SVS exist. Their case lists are generated from the
  tests, so they are complete and traceable to the code.
- 99 test functions (89 unit and integration, 10 validation) carry
  requirement markers. The SRS validation matrix
  covers the rest.
- **Repeatability:**
  - every case is automated except VP-0 (GMAT) and VP-2 (third-party
    suites), whose commands are recorded;
  - CI now fetches the Earth files, so the validation also runs there.

**Achievement:**

| Measure | Result |
|---|---|
| Unit and integration tests | 2239 passed, 11 skipped, 0 failed |
| Validation | V-01, V-02, V-04 to V-08 and V-L within tolerance |
| Coverage | 91.5 % statements, 81.7 % branches |

**Not achieved:**
- run time and memory (H13);
- other platforms (H13);
- independent verification (H06).

## 9 Problem reports and nonconformances (C.2.1<9>)

- Problem reports and nonconformances are to be GitHub issues (decision 11);
  the procedure is not yet in use.
- The known open problems are K-01 to K-09 (RD4).
- The deviations D-01 to D-07 are unsigned (H08).

## 10 Reference to progress reports (C.2.1<10>)

There is no regular PA progress reporting. The audit's progress log is
`compliance/PROGRESS.md`.
