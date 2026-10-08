# SpaceMissionStudio: Software Validation Plan (SValP)

DRD: ECSS-E-ST-40C Annex J
Document: SMS-SValP, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft.
- The validation it plans was carried out in Phase 3 of the audit
  (`compliance/phase3_log.md`) before this plan was written. This plan
  records that campaign and makes it repeatable.
- Organisation, independence and schedule are human decisions (H01, H02).

## 1 Introduction (J.2.1<1>)

This plan defines how SpaceMissionStudio is validated, that is, how it is
shown to meet its technical specification (the SRS) in its intended use.
Validation is done by comparing the tool with independent references:
- GMAT R2026a;
- IERS Earth orientation data;
- SOFA and ERFA;
- CCSDS example messages;
- the reused packages' own verification data.

## 2 Applicable and reference documents (J.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | ECSS-E-ST-40C Rev.1, 5.6 |
| AD2 | SRS (`SRS.md`), section 5.3 (performance) and section 6 (validation matrix) |
| RD1 | SVS (`SVS.md`, `SVS_test_cases.md`): the validation test specification |
| RD2 | SVR (`SVR.md`): results |
| RD3 | `compliance/phase3_log.md`: the Phase 3 campaign, references, findings |
| RD4 | SVerP (`SVerP.md`), SDP (`SDP.md`) |

## 3 Terms, definitions and abbreviated terms (J.2.1<3>)

| Term | Meaning |
|---|---|
| Reference | An independent source of expected values: GMAT, IERS 20 C04, SOFA/ERFA, a published example |
| Implementation difference | The difference between the tool and GMAT for the same models and the same elapsed integration time |
| Validation case | V-nn, a comparison with a reference, specified in the SVS |

## 4 Software validation process planning

### 4.1 General (J.2.1<4.1>)

- **Approach:** validation against the technical specification (the SRS).
  No requirements baseline exists (H03), so validation against it is not
  possible. The acceptance against a customer baseline is H03 and H01.
- **Method:**
  - Each SRS performance requirement (SRS-P-01 to SRS-P-08) has a
    validation case with a reference and a tolerance, fixed before the
    comparison.
  - The functional requirements are validated by the test cases named in
    the SRS validation matrix (SRS section 6).
- **Manually and automatically generated code:** all code is written by
  hand (SVerP 6.1).
- **Quality requirements:** SRS-Q-01 to SRS-Q-03 are validated by analysis
  of the CI metrics (SVerP 6.3).
- **Effort and independence:**
  - The campaign was carried out by the supplier.
  - There is no independence (SVerP 4.1). The use of external references
    is the main protection against errors common to the code and its tests.

### 4.2 Organization (J.2.1<4.2>)

- The supplier designs, prepares and runs the validation.
- The user accepts the results.
- **Relationships:**
  - Validation uses the configuration management of the SDP: references
    and scripts are committed.
  - It feeds the SVR.
  - It has no separate PA function (H02).

### 4.3 Schedule (J.2.1<4.3>)

- No master schedule exists (SVerP 4.3).
- The validation cases that need no external program run in CI on every
  change; this covers the comparisons against the stored references.
- The references themselves are regenerated with GMAT only when a model
  or a case changes.
- The full campaign is repeated before each release.

### 4.4 Resources summary (J.2.1<4.4>)

| Resource | Use |
|---|---|
| GMAT R2026a console (Ubuntu build, SHA-256 in RD3) | Generating the propagation, time, pass and OEM references |
| IERS 20 C04 excerpt (`tests/data/validation/eopc04_excerpt.txt`) | V-02 |
| NAIF IERS-based Earth PCKs | V-02, V-04 field cases, V-05 |
| Basilisk 2.12.0 source tree tests (`../src`), sgp4's tests | V-07, V-08 |
| A Linux PC (the audit used a cloud container: 4 cores, Python 3.11) | Running the tool |

### 4.5 Responsibilities (J.2.1<4.5>)

| Activity | Responsible |
|---|---|
| Managing the validation | The user |
| Designing, preparing and executing tests; checking results | The supplier |
| Witnessing | No one at present (H01: a test readiness review) |

### 4.6 Tools, techniques and methods (J.2.1<4.6>)

- **Tools:**
  - `pytest` for the comparisons (`tests/validation/`);
  - `compliance/validation/make_gmat_references.py`, which writes and runs
    the GMAT scripts;
  - GMAT, ERFA.
- **Technique:** comparison with the expected output, within a tolerance.
- **Facility:**
  - **Representativeness:** the tool runs on the same kind of host as in
    use (a PC), with the same software. No processor or real-time
    representativeness is needed (SDD 4.2).
  - **Loop:** software only; no hardware in the loop.
  - **Open or closed loop:** open loop (batch runs).

### 4.7 Personnel and training requirements (J.2.1<4.7>)

- Validation personnel need knowledge of astrodynamics and of GMAT.
- No training is planned.
- Independent validation personnel: none (4.1).

### 4.8 Risks (J.2.1<4.8>)

| Risk | Contingency |
|---|---|
| A reference is itself wrong or set up wrongly (two such errors were found: GMAT's GM from its default gravity file; a non-circular initial state) | Check each reference against a second source where one exists (Vallado's example for V-02; SOFA's test value for V-01); record set-up errors in RD3 |
| Tolerances chosen without analysis | Fix tolerances before the comparison; if one is revised, record it as a revision with the reason (two were: TDB 20 → 50 µs, drag 500 m → 5 %) |
| References unavailable later | All references are committed, with the scripts that produce them |
| Unexplained residual (the drag case's 1.6 %) | Recorded as open in RD3; within tolerance |

## 5 Software validation tasks identification (J.2.1<5>)

| Task | Items under test | Criterion | Inputs | Outputs |
|---|---|---|---|---|
| V-01 time scales | `engine/time_system` | SRS-P-05 | GMAT time-scale report; SOFA test value | `tests/validation/test_v01_time_scales.py` result |
| V-02 Earth orientation | `engine/earth_orientation` with SPICE | SRS-P-06 | IERS 20 C04 excerpt; Vallado's example | `test_v02_earth_orientation.py` result |
| V-04 propagation | `engine/service` with Basilisk | SRS-P-01 to SRS-P-04 | GMAT ephemerides (`tests/data/validation/gmat/`) | `test_v04_propagation.py` result |
| V-05 passes | `engine/geodesy`, `engine/service` | SRS-P-07 | GMAT ContactLocator report | `test_v05_passes.py` result |
| V-06 CCSDS OEM exchange | `engine/ccsds_odm` | SRS-F-14, SRS-I-04 | GMAT's OEM; GMAT reading the tool's OEM | `test_v06_ccsds_oem.py` result |
| V-07 reused atmosphere and magnetic field | Basilisk `msisAtmosphere`, `magneticFieldWMM` | their tests pass | Basilisk's unit tests | Test log (RD3) |
| V-08 reused SGP4 | sgp4 2.25 | its tests pass | sgp4's test suite, Vallado's verification set | Test log (RD3) |
| Functional validation | All SRS-F, SRS-I, SRS-O, SRS-RE, SRS-DF, SRS-A requirements | The tests of the SRS validation matrix pass | The test suite | CI test report |
| Lifetime | `engine/lifetime` | SRS-P-08 | A full Basilisk decay run | `tests/test_lifetime.py` |

There is no case V-03. The identifier was not used in Phase 3. The CCSDS
502.0-B-3 Annex G example messages are checked at unit level
(`tests/test_ccsds_odm.py`).

**Tasks repeated when testing resumes:** all of the above, because they
are automated. V-07 and V-08 are run by hand, with the commands in RD3.

**Detailed procedures:** in the SVS.

## 6 Software validation approach (J.2.1<6>)

**Overall requirements for the tests:**
- **References:**
  - Every validation case compares with a reference not produced by the
    tool.
  - Tolerances are set from the requirement, or from the stated accuracy
    of the reference, before the comparison.
  - A case that cannot run (missing data) is reported as skipped, never as
    passed.
- **Kinds of test:**
  - comparison of time histories (propagation);
  - comparison of event times (passes);
  - comparison of values (time scales, Earth orientation);
  - interchange in both directions (CCSDS).

**Requirements validated without test:** the SRS validation matrix marks
them I (inspection), A (analysis) or R (review):

| Requirement | Method | How |
|---|---|---|
| SRS-P-09, SRS-R-02 (run time, memory) | A | Measure on the reference PC; not yet done (SVR) |
| SRS-D-01 to D-04, SRS-M-01, SRS-M-02 | I | Inspection of code and CI |
| SRS-Q-01 to Q-03 | A | CI metrics |
| SRS-H-01 to H-03 | I, T | Inspection of the GUI, and GUI tests |
| SRS-S-01 to S-03 | T, R | Tests, and the security analysis |

**Regression testing:**
- The whole suite, validation included, runs in CI on every change.
- A change to a model, a constant or a case regenerates the affected GMAT
  references with `make_gmat_references.py`.
- A change of reference is reviewed as a change of the expected result.

## 7 Software validation testing facilities (J.2.1<7>)

| Item | Configuration |
|---|---|
| Software | SpaceMissionStudio at the commit under validation; Basilisk 2.12.0 (PyPI); Python 3.11; the packages of `pyproject.toml`; GMAT R2026a (references only) |
| Hardware | x86-64 PC or CI runner, Linux |
| Test data | `tests/data/validation/` (GMAT reports, IERS excerpt, OEMs); NAIF Earth PCKs (fetched); Basilisk's SPICE kernels |
| Communications | None during a run. Network only to fetch data beforehand. |

Validation against the technical specification and against the
requirements baseline would use the same environment; only the former is
planned (4.1).

## 8 Control procedures for software validation process (J.2.1<8>)

- **Problem reporting and resolution:**
  - A failing case is analysed and recorded as a finding (F-nn, RD3).
  - The fix is recorded in the code with the finding's identifier.
  - A formal procedure is H05.
- **Deviation and waiver policy:**
  - A requirement the tool does not meet by decision is a deviation
    (`deviations.md`, signature H08).
  - A tolerance revision is recorded with its reason.
- **Configuration control:** that of the SDP. References, cases and
  scripts are versioned with the code.

## 9 Requirements that cannot be tested in the validation environment (J.2.1<9>)

None of the SRS requirements needs a real system beyond a PC.

Three requirements need resources the validation environment lacks:
- SRS-PO-01 (Windows, macOS): not tested on those platforms.
- SRS-DEL-01 (installers): the Debian package was test-installed earlier
  in development; the Windows installer has not been tested in this
  audit.
- SRS-F-16 (Vizard): needs a display and the Vizard program; tested only
  through its save file.
