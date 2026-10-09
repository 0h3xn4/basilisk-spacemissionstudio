# SpaceMissionStudio: Software Verification Report (SVR)

DRD: ECSS-E-ST-40C Annex M
Document: SMS-SVR, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft, by the supplier.
- It reports the verification and validation of the release candidate
  (SRelD) at the end of the audit: commit `23a78d885` plus the Phase 4
  documents.
- The review of these results (CDR/QR, H01) has not taken place.
- No verification was independent (SVerP 4.1).

## 1 Introduction (M.2.1<1>)

This report gathers the results of the verification planned in the SVerP
and of the validation planned in the SValP, and states what was not done.

## 2 Applicable and reference documents (M.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | SVerP, SValP, SUITP, SVS (`compliance/docs/`) |
| RD1 | `compliance/phase3_log.md`: validation results and findings |
| RD2 | `compliance/metrics.md`, `compliance/traceability_matrix.csv`, `compliance/compliance_matrix.csv` |
| RD3 | `compliance/phase2_log.md`: implementation results R01 to R12 |
| RD4 | Security analysis (`security_analysis.md`) |

## 3 Terms, definitions and abbreviated terms (M.2.1<3>)

As in the SVerP and the SValP.

## 4 Verification activities reporting

### 4.1 General (M.2.1<4.1>)

All code is written by hand. There is no automatically generated code to
report on separately (SVerP 6.1).

### 4.2 Verification of the requirements baseline (M.2.1<4.2>)

- **Requirements baseline:** not verified, because no requirements
  baseline (SSS, IRD) exists (waived, D-11). E-ST-40C 5.8.3.1 is a customer
  activity.
- **Model checking:** no system models exist, so there is no
  model-checking report.

### 4.3 Verification of the technical specification

#### 4.3.1 Traceability (M.2.1<4.3.1>)

| Matrix | Where | Result |
|---|---|---|
| Software requirements → system requirements | SRS section 7: each requirement's source (standard clause, user decision or tool) | No system requirements exist (waived, D-11); traced to the standards instead |
| Architectural design → requirements | `SDD_components.md`, forward and backward | 63 SRS requirements, each allocated to components or to a process (CI, packaging); the build fails otherwise. 10 of 80 components are support code with no direct requirement. |
| Standards' requirements → code and tests | `traceability_matrix.csv` (RD2) | Built by CI; figures in section 8 |

#### 4.3.2 Verification reports (M.2.1<4.3.2>)

| Report | Result |
|---|---|
| Software requirements verification (5.8.3.2) | **Done by the supplier only.** Every SRS requirement has an identifier, a source and a verification method (SRS section 6). The SDD build checks completeness of allocation. Not reviewed (H01). |
| HMI evaluation | **Not done.** No mock-up evaluation with users. The UX/UI guidelines are planned (decision 5). |
| Behavioural verification of the logical model, and model checking | **Not applicable:** the logical model is a data-flow description (SRS 8); no behavioural model exists. |
| Architectural and interface design verification (5.8.3.3) | **Done by the supplier.** The ICD's claims were checked against the code; one claim lacked a test, and the test was added (unknown fields). The CLI table was found wrong and is now generated from the parser. Not reviewed (H01). |

### 4.4 Verification of the detailed design (M.2.1<4.4>)

**Traceability:**
- Detailed design → architectural design: the components are the modules
  of the SDD (one level). The generated descriptions list each module's
  subordinates.
- Code → detailed design: one-to-one, because the design is described from
  the code.
- Unit tests → requirements and design: the `requirement` markers (RD2),
  and the test designs named after components (SUITP).

**Feasibility:** none of the detailed design was assessed for feasibility
separately; it is implemented and tested.

### 4.5 Verification of code (M.2.1<4.5>)

| Check | Result |
|---|---|
| Coding standard (C-1 to C-15), static analysis | ruff, rule set of `pyproject.toml` including the security rules: **0 findings** over the package, tests, scripts and tools |
| Complexity | 19 functions above 15 (all pre-existing, listed in `metrics.md`); no new function above 15 |
| Structural coverage | Statement **91.5 %**, branch **81.7 %** (gate: statements ≥ 90 %, met) |
| Code review | **Not done** by anyone other than the supplier (H06) |
| Acceptance testing → requirements baseline | Not applicable: no baseline (waived, D-11) |

### 4.6 Verification of software unit testing, integration and validation (M.2.1<4.6>)

**Unit and integration tests:** the full suite, procedure TP-1 of the
SUITP, run on 2026-10-08 on the audit's container (Python 3.11, Basilisk
2.12.0, IERS Earth files installed):

| Run | Passed | Skipped | Failed |
|---|---|---|---|
| Baseline, before the audit | 2055 | 11 | 0 |
| After Phase 2 | 2188 | 11 | 0 |
| After Phase 3 | 2209 | 11 | 0 |
| After Phase 4 (R14, R15) | 2239 | 11 | 0 |

- **The 11 skips:** all are tests that check behaviour without Basilisk.
  They are skipped because Basilisk is installed. No validation case was
  skipped.
- **Changes between runs:**
  - The 30 tests added in Phase 4 are listed in the R15 commit and in the
    test-case lists.
  - Existing tests changed only where behaviour changed by design: the
    script tests now pass consent, and the condition hint text changed.
    Every change is recorded with its reason in the commits.

**Validation (SVS, VP-1 and VP-2):**

| Case | Result | Tolerance | Requirement | Status |
|---|---|---|---|---|
| V-01 TAI−UTC / TT−TAI / TDB−TT | 0.15 µs / 0.11 µs / 34 µs | 2 µs / 2 µs / 50 µs (revised from 20 µs) | SRS-P-05 | Met |
| V-01 SOFA TDB value | 1e-15 s | 1e-15 s | SRS-P-05 | Met |
| V-02 Earth frame vs IERS 20 C04 | 0.43 m max, 0.13 m median | 1 m | SRS-P-06 | Met |
| V-02 Vallado example | 0.37 m | 1 m | SRS-P-06 | Met |
| V-04a two-body | 0.004 m/day | 0.05 m | SRS-P-01 | Met |
| V-04b GGM03S 20 × 20 | 0.116 m/day | 1 m | SRS-P-02 | Met |
| V-04c Sun and Moon, GEO | 0.009 m / 7 days | 1 m | SRS-P-03 | Met |
| V-04d SRP, GEO | 1.135 m / 7 days | 10 m | SRS-P-03 | Met |
| V-04e drag | 0.78 km of 32 km | 1.6 km (revised from 500 m) | SRS-P-04 | Met |
| V-05 passes | 0.081 s | 1 s | SRS-P-07 | Met |
| V-06a GMAT's OEM read | the known error only | – | SRS-F-14 | Met |
| V-06b tool OEM conforms | no issue | – | SRS-F-14 | Met |
| V-06c GMAT reads the tool's OEM | 8.4 mm | 1 cm | SRS-I-04 | Met |
| V-07 Basilisk NRLMSISE-00, WMM2025 tests | 294 passed | – | SRF | Met (WMM values not checked against NOAA's report, which was not supplied; decision 18) |
| V-08 sgp4 tests | 49 passed | – | SRF | Met |
| V-L lifetime vs a decay run | +0.9 % | 3 % | SRS-P-08 | Met |

**Reference PC measurements** (decision 19; `compliance/performance.md`,
made with `compliance/tools/measure_performance.py` on 2026-10-08):

| Requirement | Case | Result | Limit | Verdict |
|---|---|---|---|---|
| SRS-P-09 | 1 day, 550 km SSO, NRLMSISE-00 drag, degree-20 field, every 10 s step recorded | 12.1 s wall time, 256 MiB peak | 300 s | Met |
| SRS-R-02 | Same orbit and models, 365 days, recorded every 60 s | 457.5 MiB peak, 2914 s wall time | 2048 MiB | Met |

The reference PC is the audit's cloud container: 4 x86-64 cores, 15.7 GiB
memory, Linux, Python 3.11, Basilisk 2.12.0.

**Other platforms** (SRS-PO-01). First run: CI run 20, commit
`ddd15ab61`, the `platforms` job:

| Platform | Passed | Failed | Skipped | Verdict |
|---|---|---|---|---|
| Linux (ubuntu-24.04) | all | 0 | 11 | Met |
| Windows (windows-latest, Python 3.11) | 2209 | 34 | 11 | Not met |
| macOS (macos-latest, arm64, Python 3.11) | 2234 | 10 | 11 | Not met |

The failures (SRelD K-10, now closed): the Vizard download tests, which
assumed the Linux layout (both); the template wizard and dialog width
tests (Windows); a path-separator assertion (Windows); a cancel-timing
test (Windows); the PNG export tests (macOS); a test-isolation error in
`test_ccsds_odm` (macOS). Most were test portability or layout
differences. Four were tool defects, F-09 to F-12 (`review_log.md`), all
fixed. One of them changed results: in the
altitude trade the 400 km case gave 1.45 kg of propellant on Windows,
against 7.26 kg on Linux, because parallel processes raced writing the
space-weather file (F-09).

After the fixes: commit `41b73b1c3`, GitHub Actions run 37854361784 (the
same commit's pull-request run, 37854357729, gave the same counts):

| Platform | Passed | Failed | Skipped | Verdict |
|---|---|---|---|---|
| Linux (ubuntu-24.04, Python 3.11) | 2259 | 0 | 11 | Met |
| Windows (windows-latest, Python 3.11, `offscreen` Qt platform) | 2259 | 0 | 11 | Met |
| macOS (macos-latest, arm64, Python 3.11, `cocoa` Qt platform) | 2259 | 0 | 11 | Met |

SRS-PO-01 is met by test for the tool installed from source with pip.
Limits of this evidence: the Windows tests draw no window (`offscreen`);
macOS uses its native window system. Nobody has used the GUI on Windows
or macOS by hand. The macOS plot-page load stall of CI run 27 did not
recur after the results-widget tests began showing their widget
(commit `6e9cbacd7`).

**Not done:** the Windows installer has not been run (SRS-DEL-01, manual
test, H13; SRelD K-06).

**Traceability:**
- Validation specification → technical specification: SVS section 11.
- Validation specification → requirements baseline: none (waived, D-11).

### 4.7 Software quality requirements verification (M.2.1<4.7>)

| Requirement | Result |
|---|---|
| SRS-Q-01 statement coverage ≥ 90 %, branch coverage ≥ 80 % | 91.5 % and 81.7 %, met |
| SRS-Q-02 zero static-analysis findings | 0, met |
| SRS-Q-03 complexity ≤ 15 for new code | Met: no new function above 15 |
| Q-ST-80C 6.2.6.1 verification of the quality requirements | As above; thresholds agreed with the customer (decision 15) |
| Automatically generated code | None |

## 5 Margins and technical budgets

### 5.1 Technical budgets (M.2.1<5.1>)

- **Budgets:** none were allocated (SDD 4.6).
- **Measured:** peak memory and wall time of the two reference runs on
  the reference PC (section above; decision 19).

### 5.2 Margins (M.2.1<5.2>)

**Not established.** The tool is not real-time, so deadlines, stack sizes
and processor utilisation per component (5.2c, 5.2d) do not apply.

The only figures available are:
- the test suite's run time, 431 s on 3 workers;
- the five-year run of HISTORY.md: 51 min, 452 MB.

### 5.3 Schedulability (M.2.1<5.3>)

Not applicable: no real-time constraints (SDD 4.2).

## 6 Numerical accuracy (M.2.1<6>)

Estimated and verified by the validation of 4.6 (V-01 to V-08 and V-L)
against independent references. The findings that bound the accuracy are
in RD1:

| Finding | Effect | Status |
|---|---|---|
| F-01 | Linear orientation extrapolation | Corrected in the tool |
| F-03 | Field GM and radius | Accepted, centimetres per day |
| F-05 | TDB time argument | Accepted, 0.1 m/day |
| F-06 | IAU_EARTH without the Earth files | Warned, 160 m/day |
| F-07 | Spherical altitude in the atmosphere | Corrected in the tool |

## 7 Throughput and latency of external interfaces (M.2.1<7>)

Not applicable. The tool controls no external interface in real time (ICD
5.2): its interfaces are files, a CLI and the optional Vizard stream.

## 8 Compliance status (supplementary)

The status of every applicable requirement of the five standards, after
Phase 4, is in `compliance_matrix.csv` and its summary in
`compliance/summary_report.md`.
