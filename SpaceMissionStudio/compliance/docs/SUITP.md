# SpaceMissionStudio: Software Unit and Integration Test Plan (SUITP)

DRD: ECSS-E-ST-40C Annex K
Document: SMS-SUITP, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft.
- The tests exist and run in CI. This plan describes them after the fact.
- The test-case list (RD1) is generated from the test sources.
- Organisation, schedule and independence are human decisions (H01, H02).

## 1 Introduction (K.2.1<1>)

This plan covers the unit and integration testing of SpaceMissionStudio:
- the strategy;
- the organisation and the facility;
- the test designs, cases and procedures.

Validation testing against the SRS is in the SValP and the SVS.

## 2 Applicable and reference documents (K.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | ECSS-E-ST-40C Rev.1, 5.5.3, 5.5.4, 5.6 |
| RD1 | `SUITP_test_cases.md`: the generated list of test designs and test cases |
| RD2 | SDD (`SDD.md`, `SDD_components.md`): the components under test |
| RD3 | SVerP, SValP, SVS, SVR, SDP |
| RD4 | `coding_standard.md`, rules C-9 (tests) and C-10 (coverage) |
| RD5 | `tests/conftest.py`: markers, fixtures and test isolation |

## 3 Terms, definitions and abbreviated terms (K.2.1<3>)

| Term | Meaning |
|---|---|
| Unit test | A test that runs without Basilisk and without Qt |
| Integration test | A test that builds and runs a Basilisk simulation, or drives the Qt GUI (offscreen) |
| Test design | A test file of `tests/` |
| Test case | A test function: `<file>::<function>` |
| Test procedure | A `pytest` invocation (section 10) |

## 4 Software overview (K.2.1<4>)

The software under test is the `spacemissionstudio` package (SDD 4.1):
- `schema`, the scenario model;
- `engine`, simulation, analyses and exchange, built on Basilisk 2.12.0;
- `gui` and `cli`, the front ends.

It runs on a PC with Python 3.11. It is configured by scenario files and
by the data files of SDD 4.1.

## 5 Software unit testing and integration testing

### 5.1 Organization (K.2.1<5.1>)

| Topic | Status |
|---|---|
| Roles | The supplier writes and runs the tests; the user decides on failures that need a requirement change |
| Reporting channels | CI results (GitHub Actions) and the JUnit report artefact |
| Authority for resolving problems | The user |
| Relationship to other activities | Every change runs the tests (SDP); results feed the SVR and the PA metrics (SPAMR) |
| Independence | None (SVerP 4.1) |

### 5.2 Master schedule (K.2.1<5.2>)

- No master schedule exists (SVerP 4.3).
- The tests run in CI on every push and pull request that touches the
  tool: about 5 minutes for the suite.
- There are no other test milestones.

### 5.3 Resources summary (K.2.1<5.3>)

- **Staff:** the supplier.
- **Hardware:** the GitHub Actions Ubuntu 24.04 runner, or a Linux PC.
- **Software:**
  - Python 3.11;
  - pytest 8 or later, pytest-qt, pytest-cov, pytest-xdist;
  - Basilisk 2.12.0;
  - PySide6 with the offscreen platform plugin.

### 5.4 Responsibilities (K.2.1<5.4>)

The supplier manages, designs, prepares and executes the tests. No
separate group exists.

### 5.5 Tools, techniques and methods (K.2.1<5.5>)

- **Tools:**
  - `pytest`, with `pytest-xdist` (parallel), `pytest-qt` (GUI) and
    `pytest-cov` (statement and branch coverage);
  - `tests/conftest.py`, which isolates every test from the user's files:
    home directory, log files, space-weather cache and Earth-orientation
    directory.
- **Techniques:**
  - comparison with expected values (analytical solutions, published
    examples, previous runs);
  - round trips (save and load, write and read);
  - checks that invalid inputs are refused.
- **Method:** each component of the SDD has a test design (RD1). New code
  comes with tests (rule C-9).

### 5.6 Personnel and personnel training requirements (K.2.1<5.6>)

Python and pytest; knowledge of astrodynamics for the engine tests. No
training is planned.

### 5.7 Risks (K.2.1<5.7>)

| Risk | Contingency |
|---|---|
| Tests share the supplier's misunderstanding of a requirement | Validation against external references (SValP); human review (H06) |
| Tests depend on the machine's files (home, cache) | `conftest.py` isolation fixtures, autouse |
| Order dependence under parallel runs | Each test is independent; CI distributes them across parallel workers (`-n auto`), so an order dependence shows as a failure |
| Slow Basilisk tests | Short durations in tests; parallel execution |

## 6 Control procedures for software unit testing and integration testing (K.2.1<6>)

- **Problem reporting:**
  - A failing test blocks the change.
  - A failure found outside CI is recorded with the fix in the commit
    message.
  - A formal procedure is H05.
- **Deviations and waivers:** tests are not skipped or disabled to make
  a change pass. Skips are allowed only for missing optional components
  (Basilisk, PySide6, data files), through markers.
- **Configuration control:** the tests are versioned with the code (SDP).

## 7 Software unit testing and integration testing approach

### 7.1 Unit and integration testing strategy (K.2.1<7.1>)

The integration is bottom-up, following the layers of SDD 4.1:
1. `schema`, and the Basilisk-free engine modules (unit level);
2. the engine with Basilisk (integration level), up to complete runs of
   every bundled template;
3. the GUI and the CLI over the engine (integration level).

### 7.2 Tasks and items under test (K.2.1<7.2>)

- **Items:** the 80 components of RD2.
- **Tasks:** one test design per component or feature, as listed in
  RD1.
- **Criteria:** 7.5.

### 7.3 Features to be tested (K.2.1<7.3>)

All the features of the SRS functional, interface, operational and
robustness requirements. The SRS validation matrix (SRS section 6) names
the test designs for each requirement.

### 7.4 Features not to be tested (K.2.1<7.4>)

| Feature or combination | Reason |
|---|---|
| Vizard live streaming to a running Vizard | Needs the Vizard program and a display; the save-file path is tested |
| The installers (Debian package, Windows installer) | Not part of the test suite. The Debian package was installed and launched by hand during development. |
| Network downloads against the real servers | Network access is not available in tests; the downloads are tested with local stand-ins |
| Every combination of scenario options | Not feasible. The 21 templates cover the supported features together, and each option is tested on its own. |

### 7.5 Test pass and fail criteria (K.2.1<7.5>)

- **Per test case:** a case passes when it runs to completion with every
  assertion true and no unexpected exception. A skip is not a pass.
- **For the campaign:** all cases pass, statement coverage is at least
  90 % (rule C-10), and lint is clean.

### 7.6 Manually and automatically generated code (K.2.1<7.6>)

All code under test is written by hand (SVerP 6.1).

## 8 Software unit test and integration test design

### 8.1 General (K.2.1<8.1>)

A test design is a test file. RD1 lists the 100 test designs, with their
description, their number of cases, their level and what they need.

### 8.2 Organization of each software unit test and integration test design

#### 8.2.1 Test design identifier (K.2.1<8.2.1>)

The file path, for example `tests/test_ccsds_odm.py`. The file's
docstring describes the design, and RD1 quotes it.

#### 8.2.2 Features to be tested (K.2.1<8.2.2>)

- The features are those of the component the file is named after (RD2).
- Traceability:
  - the cases' `requirement` markers name the standard requirements they
    verify, collected into `compliance/traceability_matrix.csv`;
  - the SRS validation matrix maps the SRS requirements to the designs.

#### 8.2.3 Approach refinements (K.2.1<8.2.3>)

- **Selection of cases:**
  - nominal behaviour;
  - boundary values;
  - refused inputs, with their message;
  - regressions for each fixed defect: the case names the defect in its
    docstring.
- **Grouping:** one design per component. All designs run in one
  procedure (section 10).
- **Analysis of results:** comparison with expected output, by assertion.
- **Facility:** as in 5.3, with `QT_QPA_PLATFORM=offscreen`.

#### 8.2.4 Test case identification (K.2.1<8.2.4>)

RD1 lists every case of each design with a summary (the docstring's first
sentence).

## 9 Software unit and integration test case specification

### 9.1 General (K.2.1<9.1>)

RD1 identifies the 1488 unit and integration test cases (test functions).
Parametrized functions run once per parameter set, so the suite runs more
cases than functions (about 2200 with the validation set).

### 9.2 Organization of each software unit and integration test case

#### 9.2.1 Test case identifier (K.2.1<9.2.1>)

`<file>::<function>`. The purpose is the docstring.
- 500 of the 1488 functions have a docstring.
- The others are described only by their name. Adding docstrings to them
  is an open item; rule C-9 requires them for new tests.

#### 9.2.2 Test items (K.2.1<9.2.2>)

- The component of the design (RD2).
- The requirements are in the case's `requirement` marker, where it has
  one.

#### 9.2.3 Inputs specification (K.2.1<9.2.3>)

In the case's code:
- its arguments (fixtures and parameters);
- the scenario or data it loads: templates, `tests/data/`;
- the values it builds.

#### 9.2.4 Outputs specification (K.2.1<9.2.4>)

The case's assertions state the expected outputs.

#### 9.2.5 Test pass-fail criteria (K.2.1<9.2.5>)

As in 7.5: every assertion true.

#### 9.2.6 Environmental needs (K.2.1<9.2.6>)

RD1's "Needs" column:
- Basilisk for `requires_basilisk` cases;
- Qt, offscreen, for `tests/gui` cases.

No special test equipment is needed.

#### 9.2.7 Special procedural constraints (K.2.1<9.2.7>)

None. Cases needing an optional component are skipped automatically
without it (`conftest.py`).

#### 9.2.8 Interfaces dependencies (K.2.1<9.2.8>)

None. Every case is independent of every other and may run in any order.

#### 9.2.9 Test script (K.2.1<9.2.9>)

The case's function is its script.

## 10 Software unit and integration test procedures

### 10.1 General (K.2.1<10.1>)

There is one procedure, `TP-1`, which runs all unit and integration test
cases. A subset can be run by passing a file or a `-k` expression.

### 10.2 Organization of each software unit and integration test procedure

#### 10.2.1 Identifier (K.2.1<10.2.1>)

`TP-1`: unit and integration tests.

#### 10.2.2 Purpose (K.2.1<10.2.2>)

TP-1 runs every case of RD1, together with the validation cases of the SVS,
and measures coverage.

#### 10.2.3 Procedure steps (K.2.1<10.2.3>)

1. **Set up:**
   - `pip install "bsk==2.12.0"`;
   - `pip install -e ".[dev,gui]"`;
   - `export QT_QPA_PLATFORM=offscreen`.
2. **Start:**
   `python -m pytest tests -q -n auto -p no:cacheprovider --cov=spacemissionstudio --cov-branch --cov-report=json:coverage.json --junitxml=test-report.xml`.
3. **Log:** the JUnit report (`test-report.xml`) and the coverage report
   (`coverage.json`).
4. **Measure:** `python compliance/tools/metrics.py --coverage coverage.json --junit test-report.xml --fail-under 90`.
5. **Shut down:** none.
6. **Restart:** re-run step 2, or only the failed cases (`--lf` without
   `-p no:cacheprovider`).
7. **Wrap up:** the CI uploads the reports as the artefact
   `spacemissionstudio-quality`.
8. **Contingencies:**
   - A failing case is analysed (SVerP 5).
   - A case that crashes a worker under xdist is re-run alone to tell a
     test fault from a parallel-run fault.

## 11 Software test plan additional information (K.2.1<11>)

| Matrix | Where |
|---|---|
| Test procedures → test cases | TP-1 runs all cases of RD1 |
| Test cases → test procedures | Every case → TP-1 |
| Test cases → requirements | `requirement` markers (RD1, `traceability_matrix.csv`); SRS section 6 |
| Components → test designs | RD1 (design names follow component names), RD2 |
