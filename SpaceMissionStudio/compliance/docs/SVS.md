# SpaceMissionStudio: Software Validation Specification (SVS) with respect to the technical specification

DRD: ECSS-E-ST-40C Annex L
Document: SMS-SVS, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft.
- It specifies the validation cases run in Phase 3 (`phase3_log.md`).
- The case definitions in the code
  (`tests/validation/validation_cases.py`) are the reference; this
  document restates them.
- There is no SVS with respect to a requirements baseline: no baseline
  exists (H03).

## 1 Introduction (L.2.1<1>)

This specification defines the validation tests of SpaceMissionStudio
against its technical specification, the SRS:
- test designs;
- test cases, with their inputs, expected outputs and criteria;
- test procedures.

It also defines the methods used where a test is not possible. The plan is
the SValP.

## 2 Applicable and reference documents (L.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | SRS (`SRS.md`), sections 5.3 and 6 |
| AD2 | SValP (`SValP.md`) |
| RD1 | `SVS_test_cases.md`: the generated list of the validation test functions |
| RD2 | `compliance/phase3_log.md`: references, results, findings |
| RD3 | `tests/validation/validation_cases.py`: case definitions; `compliance/validation/make_gmat_references.py`, `compliance/validation/gmat/*.script`: reference generation |
| RD4 | SUITP (`SUITP.md`): the unit and integration tests that the SRS matrix cites for functional requirements |

## 3 Terms, definitions and abbreviated terms (L.2.1<3>)

As in the SValP. "Same-UTC difference" is the difference at the same UTC
instant, which includes the TDB/TAI time-argument effect (F-05).

## 4 Software overview (L.2.1<4>)

As in SUITP section 4. The configuration under validation:
- SpaceMissionStudio on branch `compliance/ecss-ccsds-audit`;
- Basilisk 2.12.0;
- the NAIF IERS-based Earth PCKs installed.

## 5 Software validation testing specification task identification

### 5.1 Tasks and items under test (L.2.1<5.1>)

The tasks are V-01, V-02 and V-04 to V-08 of SValP section 5. The items
are the components named there. Criteria are in 5.4.

### 5.2 Features to be tested (L.2.1<5.2>)

| Feature | SRS |
|---|---|
| Time scales UTC, TAI, TT, TDB | SRS-F-07, SRS-P-05 |
| Earth-fixed frame with IERS-based files | SRS-F-06, SRS-P-06 |
| Orbit propagation: two-body, spherical harmonics, third bodies, SRP, drag | SRS-F-03, SRS-F-04, SRS-P-01 to SRS-P-04 |
| Ground-station passes | SRS-F-08, SRS-P-07 |
| CCSDS OEM exchange with another tool | SRS-F-14, SRS-I-04 |
| Reused atmosphere, magnetic-field and SGP4 models | SRS-F-02, SRS-F-03 (through the SRF) |
| Lifetime estimate against a full decay run | SRS-P-08 |

### 5.3 Features not to be tested (L.2.1<5.3>)

| Feature | Reason |
|---|---|
| Earth-fixed frame without IERS-based files (IAU_EARTH) | Its accuracy is known to be about 1.5 mrad (F-06); the run warns. Validating it would only confirm the warning. |
| Attitude dynamics and control, sensors, actuators, power, thermal | Not covered by an external reference in this campaign. They rest on Basilisk's own tests and the tool's integration tests (SUITP). This is a gap for SRS-F-09 validation. |
| Mission sequence, Lambert transfer, orbit maintenance | Integration tests only (SUITP) |
| Monte Carlo, budgets, link budget, formation and constellation design | Integration tests only (SUITP) |
| GUI | Integration tests only (SUITP); usability is not validated (SRS-H-01 to H-03, inspection) |

### 5.4 Test pass-fail criteria (L.2.1<5.4>)

- A case passes when the largest difference from the reference is below
  its tolerance (section 7).
- Tolerances are fixed in RD3 before the comparison. A revision is
  recorded with its reason (RD2).
- A case that is skipped has not passed.

### 5.5 Items that cannot be validated by test (L.2.1<5.5>)

| Item | Justification | Method proposed |
|---|---|---|
| SRS-P-09 run time, SRS-R-02 memory | Depend on the reference PC, which is not defined | Analysis: measure on the user's PC with a profiled one-day and one-year run |
| SRS-PO-01 Windows and macOS | Not available | Test on those platforms (human action) |
| SRS-H-01 to H-03 human factors | Usability is a judgement | Review with users |
| SRS-S-03 script blocks | Partly a design property | Review of the security analysis (`security_analysis.md`), plus tests |

### 5.6 Manually and automatically generated code (L.2.1<5.6>)

All code is written by hand (SVerP 6.1).

## 6 Software validation testing specification design

### 6.1 General (L.2.1<6.1>)

The tests are grouped by feature into one design per file. RD1 lists the
files and their functions:

| Design | File | Cases |
|---|---|---|
| VD-01 time scales | `tests/validation/test_v01_time_scales.py` | V-01 |
| VD-02 Earth orientation | `tests/validation/test_v02_earth_orientation.py` | V-02 |
| VD-04 propagation | `tests/validation/test_v04_propagation.py` | V-04a to V-04e |
| VD-05 passes | `tests/validation/test_v05_passes.py` | V-05 |
| VD-06 CCSDS OEM | `tests/validation/test_v06_ccsds_oem.py` | V-06a to V-06c |
| VD-07 reused models | Basilisk's and sgp4's own test suites (run by hand) | V-07, V-08 |
| VD-L lifetime | `tests/test_lifetime.py::test_reentry_date_matches_a_basilisk_decay_run` | V-L |

There is no V-03 (SValP section 5).

### 6.2 Organization of each test design

#### 6.2.1 Test designs identifier (L.2.1<6.2.1>)

As in 6.1: VD-nn.
- VD-01 to VD-06 each compare the tool with a stored reference.
- VD-07 runs third-party tests.
- VD-L compares two methods of the tool.

#### 6.2.2 Features to be tested (L.2.1<6.2.2>)

As in 5.2, one row per design. The traceability to the SRS is in section 11
and in the files' `requirement` markers.

#### 6.2.3 Approach refinements (L.2.1<6.2.3>)

- **Selection of cases:**
  - one case per force model, added one at a time: two-body, then the
    field, then third bodies, then SRP, then drag;
  - LEO for the field and drag, and GEO for third bodies and SRP, where
    each effect is largest;
  - time-scale epochs on both sides of leap seconds.
- **Analysis:**
  - comparison with the expected output (the reference), as the largest
    difference over the arc;
  - for propagation, both the implementation difference and the same-UTC
    difference (F-05).
- **Facility:** SValP section 7.

## 7 Test case specification

### 7.1 General (L.2.1<7.1>)

The test cases are those of the table in 7.2. Their code is listed in RD1.

### 7.2 Organization of each test case

#### 7.2.1 Test case identifier (L.2.1<7.2.1>)

| Case | Purpose |
|---|---|
| V-01 | TAI−UTC, TT−TAI, TDB−TT at 11 epochs, 1980 to 2030; the TDB series against SOFA's test value |
| V-02 | Earth-fixed frame against ERFA with IERS 20 C04 at 882 epochs, 1990 to 2026-03; Vallado's 2004 example |
| V-04a | Two-body, 400 km circular, 52.5° inclination, 1 day |
| V-04b | As V-04a with GGM03S 20 × 20 |
| V-04c | GEO, Sun and Moon point masses (DE430), 7 days |
| V-04d | As V-04c with cannonball SRP and eclipses |
| V-04e | As V-04a with NRLMSISE-00 drag, observed 2024 indices, 100 kg, 1 m² |
| V-05 | Passes over a WGS-84 station at Berlin (10° geodetic mask), V-04a's orbit, 1 day |
| V-06a | GMAT's OEM read and checked against 502.0-B-3 |
| V-06b | The tool's OEM conforms to 502.0-B-3 |
| V-06c | GMAT interpolating the tool's OEM reproduces the tool's trajectory |
| V-07 | Basilisk's NRLMSISE-00 and WMM2025 unit tests against the pinned release |
| V-08 | sgp4's test suite, including Vallado's verification set |
| V-L | Lifetime estimate against a full Basilisk decay run from 300 km |

#### 7.2.2 Inputs specification (L.2.1<7.2.2>)

| Case | Inputs |
|---|---|
| V-01 | The epochs `TIME_EPOCHS` (RD3); GMAT's time report `tests/data/validation/gmat/` |
| V-02 | `tests/data/validation/eopc04_excerpt.txt`; the NAIF Earth PCKs |
| V-04 | The initial states of RD3 (LEO r = [6778.137, 0, 0] km, v = [0, 4.668322, 6.083876] km/s; GEO r = [42164.17, 0, 0] km, v = [0, 3.07466, 0.0537] km/s); the epochs 2024-06-01 (LEO) and 2024-03-15 (GEO); GMAT ephemerides at 600 s; the tool at its 10 s default step |
| V-05 | `STATION` of RD3; GMAT's ContactLocator report |
| V-06 | `gmat_written.oem`; `tool_written.oem` (Lagrange, degree 7, 60 s); GMAT's report reading the tool's OEM |
| V-07, V-08 | The third-party tests' own inputs |
| V-L | Template 18's spacecraft from 300 km, no station keeping, 40 days, MSFC prediction |

#### 7.2.3 Outputs specification (L.2.1<7.2.3>)

The expected outputs are the reference values: GMAT, ERFA with IERS C04,
SOFA, Vallado. For V-06b, the expected output is an empty issue list. For
V-L, it is the decay run's re-entry day.

#### 7.2.4 Test pass-fail criteria (L.2.1<7.2.4>)

| Case | Criterion (largest difference) | SRS |
|---|---|---|
| V-01 | TAI−UTC and TT−TAI ≤ 2 µs; TDB−TT ≤ 50 µs; SOFA value to 1e-15 s | SRS-P-05 |
| V-02 | ≤ 1 m at the Earth's surface | SRS-P-06 |
| V-04a | ≤ 0.05 m (implementation difference) | SRS-P-01 |
| V-04b | ≤ 1 m | SRS-P-02 |
| V-04c | ≤ 1 m in 7 days | SRS-P-03 |
| V-04d | ≤ 10 m in 7 days | SRS-P-03 |
| V-04e | ≤ 1600 m, which is 5 % of GMAT's 32 km drag-induced displacement | SRS-P-04 |
| V-05 | Each pass start and end within 1 s; same number of passes | SRS-P-07 |
| V-06a | Only the known error (CENTER_NAME, F-08) and the version warning; states equal GMAT's report to 1 mm | SRS-F-14 |
| V-06b | No issue | SRS-F-14 |
| V-06c | ≤ 1 cm | SRS-I-04 |
| V-07, V-08 | All tests pass | SRF |
| V-L | Re-entry day within 3 % | SRS-P-08 |

#### 7.2.5 Environmental needs (L.2.1<7.2.5>)

- **Facility:** SValP section 7.
- **For the references:** GMAT R2026a, needed only to regenerate the
  stored references (RD3).
- **For running the cases:** Basilisk 2.12.0, and the NAIF Earth PCKs for
  V-02, V-04b and V-05.
- No special test equipment is needed.

#### 7.2.6 Special procedural constraints (L.2.1<7.2.6>)

- The cases that need the Earth PCKs skip without them.
- In CI the PCKs are fetched before the tests. A skip in the report means
  the case was not run.

#### 7.2.7 Interfaces dependencies (L.2.1<7.2.7>)

None between cases. Each reference must exist (`make_gmat_references.py`
writes them), and they are committed.

## 8 Software validation test procedures

### 8.1 General (L.2.1<8.1>)

There are two procedures:
- `VP-1` runs VD-01 to VD-06 and VD-L;
- `VP-2` runs VD-07 by hand.

The regeneration of the references, `VP-0`, is a preparatory procedure.

### 8.2 Organization of each validation test procedure

#### 8.2.1 Identifier (L.2.1<8.2.1>)

- `VP-0`: regenerate the GMAT references.
- `VP-1`: automated validation.
- `VP-2`: reused models.

#### 8.2.2 Purpose (L.2.1<8.2.2>)

| Procedure | Purpose | Cases |
|---|---|---|
| VP-0 | Produce the reference files from GMAT | References for V-01, V-04, V-05, V-06 |
| VP-1 | Compare the tool with the references | V-01, V-02, V-04a–e, V-05, V-06a–c, V-L |
| VP-2 | Run the reused packages' tests against the pinned versions | V-07, V-08 |

#### 8.2.3 Procedure steps (L.2.1<8.2.3>)

**VP-0:**
1. Install GMAT R2026a and check its SHA-256 (RD2).
2. Run `python compliance/validation/make_gmat_references.py --gmat <GMAT bin directory>`.
3. Review the change in `tests/data/validation/gmat/` as a change of the
   expected results.

**VP-1:**
1. **Set up:** as SUITP TP-1, then
   `spacemissionstudio earth-orientation --fetch`.
2. **Start:**
   `QT_QPA_PLATFORM=offscreen python -m pytest tests/validation tests/test_lifetime.py -v -p no:cacheprovider`.
3. **Log:** the pytest output. The largest differences are recorded as
   JUnit properties (for example `implementation_difference_m`,
   `max_difference_at_surface_m`).
4. **Contingency:** a failure is analysed as a finding (SValP 8).

**VP-2:**
1. `pytest ../src/simulation/environment/MsisAtmosphere/_UnitTest ../src/simulation/environment/magneticFieldWMM/_UnitTest`,
   with the pinned Basilisk installed.
2. `python -m unittest sgp4.tests`.
3. Record the counts in the SVR.

#### 8.2.4 Test script (L.2.1<8.2.4>)

The test functions of RD1, and the commands above.

## 9 Validation methods other than test (L.2.1<9>)

As in 5.5. In addition, the SRS validation matrix (SRS section 6) marks
these requirements for inspection (I) or analysis (A), as the SValP
section 6 describes:
- SRS-D-01 to D-04;
- SRS-M-01, SRS-M-02;
- SRS-Q-01 to Q-03.

## 10 Validation test platform requirements (L.2.1<10>)

| Need | Capability |
|---|---|
| Host | x86-64 Linux, 4 cores, 15 GB of memory (the audit's container) |
| Software | Python 3.11, Basilisk 2.12.0, the packages of `pyproject.toml` |
| Data | The NAIF Earth PCKs; Basilisk's SPICE kernels (Basilisk's data fetcher) |
| References | GMAT R2026a (only for VP-0) |

## 11 Additional information (L.2.1<11>)

| Requirement | Case | Method |
|---|---|---|
| SRS-P-01 | V-04a | T |
| SRS-P-02 | V-04b | T |
| SRS-P-03 | V-04c, V-04d | T |
| SRS-P-04 | V-04e | T |
| SRS-P-05 | V-01 | T |
| SRS-P-06 | V-02 | T |
| SRS-P-07 | V-05 | T |
| SRS-P-08 | V-L | T |
| SRS-P-09, SRS-R-02 | – | A (not yet done) |
| SRS-F-14, SRS-I-04 | V-06a–c | T |
| SRS-F-02, SRS-F-03 (reused models) | V-07, V-08 | T |
| Other SRS requirements | The SUITP cases of the SRS validation matrix | T, I, A, R as marked there |

The reverse matrix (case → requirement) is the "SRS" column of 7.2.4.
