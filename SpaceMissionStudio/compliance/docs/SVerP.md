# SpaceMissionStudio: Software Verification Plan (SVerP)

DRD: ECSS-E-ST-40C Annex I
Document: SMS-SVerP, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft. This plan describes the verification set up during the
audit, and what it still needs from people.
- The organisation, roles, independence and schedule are human decisions
  (H01, H02, H06). They are stated here as gaps, not filled in.

## 1 Introduction (I.2.1<1>)

This plan defines how SpaceMissionStudio is verified: how each product of
the life cycle is checked against its inputs, by which methods and tools,
and with which outputs. Verification here means E-ST-40C 5.8. The
validation against the SRS is planned separately in the SValP.

## 2 Applicable and reference documents (I.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | ECSS-E-ST-40C Rev.1, 5.8 |
| AD2 | ECSS-Q-ST-80C Rev.2 |
| RD1 | SRS, ICD, SDD, CSD (`compliance/docs/`) |
| RD2 | SValP, SUITP, SVS, SVR (`compliance/docs/`) |
| RD3 | `coding_standard.md` (rules C-1 to C-15) |
| RD4 | `.github/workflows/spacemissionstudio.yml` (CI) |
| RD5 | `SDP.md`: development, configuration management and maintenance |
| RD6 | `compliance/human_actions.md` |

## 3 Terms, definitions and abbreviated terms (I.2.1<3>)

| Term | Meaning |
|---|---|
| CI | The GitHub Actions workflow RD4, run on every push and pull request that touches the tool |
| Generated document | A document written by a tool in `compliance/tools/` from the code, which cannot drift from it |

## 4 Software verification process overview

### 4.1 Organization (I.2.1<4.1>)

**Approach:** verification is automated wherever a check can be computed,
and run on every change:
- lint;
- complexity;
- tests and coverage;
- traceability;
- DRD completeness;
- the currency of the generated documents.

What cannot be computed is a human action:
- the review of requirements and design (H01);
- the independent review of the code (H06; guide in
  `compliance/reviews/code_review_guide.md`).

**Effort:**
- A CI run takes about 6 minutes; the test step took 305 s in run 3.
  The timeout is 90 minutes.
- The human effort is not estimated (H02).

**Independence:**
- **There is none at present.** The code, its tests and the audit were
  all produced by the same supplier, an AI coding assistant working for
  the user.
- Category C does not require independent verification, but ECSS-Q-ST-80C
  6.2.6 expects review of the code. Independent human review of at least
  the budget, lifetime, frame and time, and environment code is H06.

### 4.2 Organization of the verification activities (I.2.1<4.2>)

| Topic | Status |
|---|---|
| Roles | The supplier (developer and verifier); the user (requirements, decisions, acceptance). An SPA manager and reviewers are to be named (H02). |
| Reporting channels | CI results on GitHub; findings in the audit logs (`phase2_log.md`, `phase3_log.md`); problem reports as GitHub issues (decision 11) |
| Authority for resolving problems | The user |
| Organisational relationships | One person and the supplier; no separate PA or CM function (H02) |
| Independence | None (4.1) |

### 4.3 Master schedule (I.2.1<4.3>)

- No master schedule exists. The SDP (RD5) describes an event-driven life
  cycle.
- **Verification schedule:**
  - The CI checks run on every change.
  - The documentation reviews (H01) take place before a release.
  - The SVR is updated for each release.

### 4.4 Resources summary (I.2.1<4.4>)

| Resource | Use |
|---|---|
| GitHub Actions runner, Ubuntu 24.04, Python 3.11 | CI (RD4) |
| A developer PC with Basilisk 2.12.0, GMAT R2026a and the IERS-based Earth files | Validation references (SValP) |
| ruff, pytest, pytest-cov, pytest-xdist, pytest-qt | Lint, tests, coverage |
| `compliance/tools/*.py` | Metrics, traceability, ICS, matrix, DRD checks, generated documents |
| People | The user. Reviewers: H01, H06. |

### 4.5 Responsibilities (I.2.1<4.5>)

| Activity | Responsible |
|---|---|
| Automated verification (CI), test design, analysis of failures | Supplier |
| Review of requirements and design documents | Customer and user, at the reviews of H01 |
| Independent code review | A person other than the supplier (H06) |
| Acceptance of the verification results | User |

### 4.6 Risks and level of independence (I.2.1<4.6>)

| Risk | Mitigation |
|---|---|
| No independent verification: the same supplier writes code and tests, so a misunderstanding can be built into both | External references wherever possible: GMAT, IERS, SOFA, CCSDS examples, Basilisk's and sgp4's own tests (SValP); human review H06 |
| External reference data change or disappear (NAIF, CelesTrak, GMAT) | The references used are committed (`tests/data/validation/`), with the scripts that produced them (`compliance/validation/`) |
| Tests depend on installed data (Earth files) and skip without them | CI installs the Earth files before the tests (RD4); a skipped validation case is reported as not run in the SVR |

### 4.7 Methods, tools and techniques (I.2.1<4.7>)

| Method | Tool | Used for |
|---|---|---|
| Static analysis | `ruff` with the rule set of RD3 | Code |
| Complexity and metrics | `compliance/tools/metrics.py` (ruff C901; size; coverage; corrective commits) | Code quality (SPAMR) |
| Testing | `pytest` (unit, integration, validation) | Code against design and requirements |
| Coverage | `pytest-cov` (statement and branch) | Test completeness, ≥ 90 % statements (C-10) |
| Traceability | `build_traceability.py` (standards → code → tests), `build_sdd_components.py` (SRS → components) | Requirements, design |
| Document completeness | `check_drds.py` (every DRD section present and not empty) | Documents |
| Inspection | Reading by the supplier, recorded in the audit logs | Requirements, design, code |
| Review | Human review (H01, H06) | All products |

## 5 Control procedures for verification process (I.2.1<5>)

- **Problem reporting and resolution:**
  - A failing CI check blocks the change until it is fixed.
  - Findings from verification are recorded with an identifier, for
    example F-01 in `phase3_log.md`.
  - Problem reports and nonconformances are GitHub issues (decision 11;
    SMP 10.1); the procedure is not yet in use.
- **Deviation and waiver policy:**
  - Deviations from the standards are listed in `deviations.md`, with
    their justification, and take effect only when signed (H08).
  - A test is never skipped or weakened to pass. A tolerance that is
    changed is recorded as a revision, with the reason; see
    `phase3_log.md`.
- **Control procedures:** the configuration control of the SDP (RD5)
  applies. The verified item is the commit that CI ran on.

## 6 Verification activities

### 6.1 Software process verification (I.2.1<6.1>)

- The software item is SpaceMissionStudio (the `spacemissionstudio`
  package).
- All its code is written by hand; no code is generated by a model-based
  tool. The SWIG bindings belong to Basilisk, which is reused software
  (SRF).
- The generated documents are not code. They are verified by being
  regenerated in CI and compared with the committed copy.

### 6.2 Software quality requirements verification (I.2.1<6.2>)

| Process | Verification activity | Inputs | Outputs |
|---|---|---|---|
| Requirements (5.4) | Check that every SRS requirement is verifiable, traced (SRS section 7) and allocated to components (`build_sdd_components.py` fails if not); DRD completeness (`check_drds.py`); human review (H01) | SRS, ICD | `SDD_components.md`; checker output; review report (H01) |
| Design (5.5) | Traceability requirement → component; layer rules (SDD 5.4.7); DRD completeness; human review (H01) | SDD | `SDD_components.md`; review report |
| Coding (5.5.3) | Lint; complexity ≤ 15 for new code; docstrings; independent review (H06) | Code | CI log; `metrics.md` |
| Unit and integration testing (5.5.4, 5.6) | The SUITP's tests in CI | Code, tests | `test-report.xml`, `coverage.json` |
| Validation (5.6) | The SValP | SRS, references | SVR, `phase3_log.md` |
| Documentation (5.8.3) | DRD completeness; generated documents current | Documents | Checker output |

### 6.3 Software quality requirements verification

#### 6.3.1 Activities (I.2.1<6.3.1>)

| SRS requirement | Activity | How |
|---|---|---|
| SRS-Q-01 statement coverage ≥ 90 % | Measure | `metrics.py --fail-under 90` on the CI coverage |
| SRS-Q-02 zero static-analysis findings | Analyse | `ruff check` in CI |
| SRS-Q-03 complexity ≤ 15 for new code | Measure | `metrics.py` lists every function above 15 |
| SRS-M-01 CI on every change | Inspect | The workflow's triggers (RD4) |
| SRS-M-02 workarounds isolated | Inspect | The SDD and the two modules |

#### 6.3.2 Inputs (I.2.1<6.3.2>)

The code at the verified commit; the CI coverage and test reports;
`pyproject.toml` (the ruff configuration).

#### 6.3.3 Outputs (I.2.1<6.3.3>)

`compliance/metrics.md` and `metrics.json`, the CI log and artefacts, and
the SVR.

#### 6.3.4 Methods, tools and facilities (I.2.1<6.3.4>)

Those of 4.7, run on the CI facility of 4.4.
