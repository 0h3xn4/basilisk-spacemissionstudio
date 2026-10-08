# SpaceMissionStudio: Software Development Plan (SDP), with the configuration management description

DRD: ECSS-E-ST-40C Annex O
Document: SMS-SDP, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft.
- It describes how the tool is developed now, after the audit introduced
  CI, a coding standard, traceability and these documents.
- Organisation, schedule, reviews and risk management need people: H01,
  H02, H05.

**SCMP:**
- E-ST-40C refers to a software configuration management plan (SCMP)
  (for example 5.3.2.4e).
- The SCMP DRD is in ECSS-M-ST-40C, which is **not among the supplied
  documents**. Its required contents could therefore not be checked.
- Section 6 of this SDP describes the configuration management that is
  in place. It does not claim to meet an SCMP DRD.

## 1 Introduction (O.2.1<1>)

This plan describes how SpaceMissionStudio is developed and maintained:
- objectives;
- life cycle;
- methods;
- environment;
- documentation;
- configuration management.

It applies from the ECSS/CCSDS audit (2026-10-08) onwards.

## 2 Applicable and reference documents (O.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | ECSS-E-ST-40C Rev.1; ECSS-Q-ST-80C Rev.2 |
| RD1 | `compliance/phase0_tailoring.md`: category C tailoring |
| RD2 | `compliance/compliance_matrix.csv`: the coverage matrix of the tailored requirements |
| RD3 | `coding_standard.md`; SVerP; SValP; SUITP; SMP; SPAP |
| RD4 | `compliance/human_actions.md` |

## 3 Terms, definitions and abbreviated terms (O.2.1<3>)

| Term | Meaning |
|---|---|
| CI | The GitHub Actions workflow `.github/workflows/spacemissionstudio.yml` |
| Supplier | The developer: the user, assisted by an AI coding assistant that writes most of the code and documents |

## 4 Software project management approach

### 4.1 Management objectives and priorities (O.2.1<4.1>)

The objectives, in order:
1. **Results the user can trust and trace:** validated models, recorded
   provenance, stated limitations.
2. **No modification of the reused Basilisk framework.**
3. **Offline by design.**
4. **Usability for mission analysts.**

### 4.2 Master schedule (O.2.1<4.2>)

No project master schedule exists. Development is continuous and driven by
the user's requests. Releases are made when the user decides (H05).

### 4.3 Assumptions, dependencies and constraints (O.2.1<4.3>)

- **Assumptions:**
  - one user, who is also the customer;
  - category C (decision 1);
  - security assurance level low (D8).
- **Dependencies:**
  - Basilisk releases;
  - the data sources (NAIF, CelesTrak, NASA MSFC);
  - GMAT, for regenerating validation references.
- **Constraints:**
  - Basilisk is reused unmodified (decision D5);
  - only real space-weather data, never synthetic;
  - downloads only with the user's consent.

### 4.4 Work breakdown structure (O.2.1<4.4>)

The audit's remediations R01 to R15 (`gap_analysis.md`) form the current
work breakdown. Later work packages are the items of SRelD section 7.

### 4.5 Risk management (O.2.1<4.5>)

There is no project risk management process (H05). Technical risks are
recorded where they arise:
- findings F-nn (`phase3_log.md`);
- security risks S-nn (`security_analysis.md`);
- known problems K-nn (SRelD).

### 4.6 Monitoring and controlling mechanisms (O.2.1<4.6>)

- CI on every change.
- The metrics (`compliance/metrics.md`).
- The compliance matrix (RD2).
- `compliance/PROGRESS.md`, the progress log of the audit.

### 4.7 Staffing plan (O.2.1<4.7>)

- **People:** the user (customer, developer, reviewer of decisions) and an
  AI coding assistant (implementation, tests, documents).
- **Missing:**
  - independent review: H06;
  - an SPA manager: H02.
- **Skills:** astrodynamics, Python, Basilisk.

### 4.8 Software procurement process (O.2.1<4.8>)

No software is procured under contract. The reused open-source components
and their evaluation are in the SRF. Their acceptance is H07.

### 4.9 Supplier management (O.2.1<4.9>)

Not applicable: there are no lower-level suppliers. Defects found in
Basilisk are reported upstream (H10).

## 5 Software development approach

### 5.1 Strategy to the software development (O.2.1<5.1>)

Incremental development on the `develop` line.
- Every change goes through CI.
- New features are added behind tests.
- Accuracy-relevant code is validated against external references.

### 5.2 Software project development life cycle

#### 5.2.1 Software development life cycle identification (O.2.1<5.2.1>)

- **Life cycle:** incremental.
  - Each increment is a set of commits on a branch, merged after CI
    passes.
  - Each increment is recorded in `HISTORY.md` with what was found, what
    was changed and how it was verified.
- **Versioning:** semantic version (`MAJOR.MINOR.PATCH`) in
  `spacemissionstudio/__init__.py` and `pyproject.toml`, set at release
  (H05).
- **Processes covered:**
  - requirements: SRS;
  - design: SDD;
  - coding: coding standard;
  - verification: SVerP;
  - validation: SValP;
  - delivery: packaging;
  - maintenance: SMP.

#### 5.2.2 Relationship with the system development cycle (O.2.1<5.2.2>)

The tool is not part of a space system's development. It supports mission
analysis, so there is no system life cycle to phase with.

#### 5.2.3 Reviews and milestones identification and associated documentation (O.2.1<5.2.3>)

**Proposed reviews (H01):**
- A reduced set suited to category C: SRR/PDR combined, then CDR/QR
  combined, then AR. The review sets the formalism.
- **Purposes:**
  - SRR/PDR: SRS, ICD, SDD, SVerP, SValP, SDP;
  - CDR/QR: the code, SUITP, SVS, SVR;
  - AR: SRelD, SUM, the open items.
- **Roles:** the user as customer. A reviewer independent of the
  development is needed (H06).

### 5.3 Software engineering standards and techniques (O.2.1<5.3>)

| Process | Method or standard |
|---|---|
| Requirements analysis | Requirements derived from the implemented functions, the standards' applicable requirements and the user's decisions; recorded in the SRS with sources (SRS section 7) |
| Architectural and detailed design | Layered decomposition (SDD 4.1, 4.7); generated component descriptions |
| Coding | `coding_standard.md` (C-1 to C-15), PEP 8, ruff |
| Automatic code generation | None (SVerP 6.1) |
| Human-machine interface | Qt (PySide6); the UX/UI guidelines of 2026-10-08 are planned (PROGRESS.md, decision 5) |
| Delivery format | Wheel, sdist, `.deb`, Windows installer, with SHA-256 checksums |

### 5.4 Software development and software-testing environment (O.2.1<5.4>)

| Item | Tool |
|---|---|
| Language and interpreter | Python 3.9+ (CI: 3.11) |
| Requirements analysis | Markdown documents, `compliance/tools/*.py` (CSV extraction, traceability) |
| Design | Markdown; `build_sdd_components.py` |
| Configuration management | git, GitHub |
| Static analysis | ruff (rules of `pyproject.toml`, security rules S included) |
| Testing | pytest, pytest-qt, pytest-xdist, pytest-cov |
| Metrics | `compliance/tools/metrics.py` |
| Validation references | GMAT R2026a, ERFA |
| Hardware | x86-64 Linux PCs; GitHub-hosted Ubuntu 24.04 runners |

**Evidence of suitability:** the tools are standard. The validation results
(SVR) show the toolchain produces correct software for the cases tested.

### 5.5 Software documentation plan

#### 5.5.1 Introduction (O.2.1<5.5.1>)

The documentation consists of:
- the documents in `compliance/docs/` (one per DRD);
- `USER_MANUAL.md`, `README.md`, `HISTORY.md`;
- the docstrings in the code.

#### 5.5.2 Software documentation identification (O.2.1<5.5.2>)

| Document | DRD | Format | Produced | Updated |
|---|---|---|---|---|
| SRS, ICD, SDD, CSD | E-40 D, E, F; E-10-09 A | Markdown | Audit Phase 4 | With every requirement or design change |
| SVerP, SValP, SUITP, SVS, SVR | E-40 I, J, K, L, M | Markdown, partly generated | Audit Phase 4 | Each release |
| SUM, SRelD, SRF, SDP, SMP | E-40 H, G, N, O, T | Markdown | Audit Phase 4 | Each release |
| SPAP, SPAMR | Q-80 B, C | Markdown | Audit Phase 4 | Each release |
| Security analysis | – (no DRD supplied) | Markdown | Audit R15 | Per its section 7 |
| Generated parts (`*_fields.md`, `*_cli.md`, `*_components.md`, `*_test_cases.md`) | – | Markdown | `compliance/tools/` | Every change; CI fails if out of date |

#### 5.5.3 Deliverable items (O.2.1<5.5.3>)

- **Deliverables:**
  - the source repository at the release commit;
  - the wheel, sdist, `.deb` and Windows installer, with checksums;
  - the documents of 5.5.2.
- **Internal items:**
  - the CI artefacts (test report, coverage, metrics, matrices);
  - the GMAT scripts and references.
- **For each delivery:**
  - sender and receiver: the supplier and the user;
  - the version and commit;
  - the SRelD;
  - the checksums.

#### 5.5.4 Software documentation standards (O.2.1<5.5.4>)

- Documents follow their DRDs, section by section.
- `compliance/tools/check_drds.py` checks that every DRD section is present
  and not empty.
- **Tailoring:** a section that does not apply says why; a section that
  waits for a human action names it.

### 5.6 Coverage matrix of the tailoring (O.2.1<5.6>)

`compliance/compliance_matrix.csv` lists every requirement of E-ST-40C clause 5 with its applicability under
the category C tailoring (RD1) and its status. This SDP does not repeat it.

## 6 Configuration management (description, not an SCMP)

| Item | In place |
|---|---|
| Configuration items | `SpaceMissionStudio/` (code, tests, data, documents), `.github/workflows/spacemissionstudio.yml` |
| Identification | git commits. Release versions are set in `__init__.py` and `pyproject.toml`. No SpaceMissionStudio release is tagged (the repository's tags are Basilisk's); tagging releases is proposed (H05). |
| Baselines | A release commit. The reused baseline is recorded in the SRF (Basilisk 2.12.0 with its published SHA-256). |
| Change control | Branches. CI must pass. Commit messages reference requirement IDs or findings. A change board does not exist (H05). |
| Status accounting | `HISTORY.md`; `compliance/PROGRESS.md`; each run's `provenance.json` records the tool and dependency versions and the data files used |
| Releases | Build scripts with checksums (`packaging/`) |
| Proposed | A lock file with hashes for release dependencies (security analysis S-08); signed tags or releases (S-07) |
