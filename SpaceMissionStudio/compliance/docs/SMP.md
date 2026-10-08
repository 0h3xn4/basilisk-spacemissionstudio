# SpaceMissionStudio: Software Maintenance Plan (SMP)

DRD: ECSS-E-ST-40C Annex T
Document: SMS-SMP, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft.
- The tool is maintained by the same people and process that develop it
  (SDP).
- Problem reports are GitHub issues (decision 11). The procedure is
  defined in 10.1 but not yet in use: no labels have been created.
- A formal change board, risk management and operation support are waived
  (decision 11, deviation D-12): the user approves changes, CI gates them,
  and support is best effort.

## 1 Introduction (T.2.1<1>)

This plan describes how SpaceMissionStudio is corrected, adapted and
improved after delivery. Its scope is from the receipt of a request to the
delivery of the changed version.

## 2 Applicable and reference documents (T.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | SDP (`SDP.md`), configuration management in its section 6 |
| AD2 | SVerP, SValP, SUITP (`compliance/docs/`) |
| RD1 | SRelD (`SRelD.md`): known problems K-nn |
| RD2 | `compliance/human_actions.md` |

## 3 Terms, definitions and abbreviated terms (T.2.1<3>)

| Term | Meaning |
|---|---|
| SPR | Software problem report |
| SMR | Software modification request |
| Maintainer | The supplier (SDP 4.7) |

## 4 Software maintenance overview (T.2.1<4>)

**Kinds of maintenance:**
- **Corrective:** defects reported by users or found by CI.
- **Adaptive:**
  - a new Basilisk release, which needs requalification (5.3);
  - new Python, Qt or operating-system versions;
  - data-source changes: the CelesTrak and NAIF formats.
- **Perfective:** features.
- **Preventive:** dropping workarounds when Basilisk fixes F-01 and F-07
  (H10).

**Boundaries:**
- Maintenance starts when an SPR or SMR is received: a GitHub issue,
  proposed in 10.1.
- It ends when the changed version is delivered with its SRelD.

**Difference from development:**
- a change must keep every existing test passing;
- a change must keep the validation results within tolerance;
- the documents must stay current.

## 5 Maintenance process (T.2.1<5>)

**Steps:**
1. Receive: issue.
2. Analyse: reproduce; classify (10.1).
3. Design.
4. Implement on a branch.
5. Verify: CI, plus re-validation when a model or constant changes.
6. Accept: user.
7. Deliver: release with SRelD and checksums.

**Control and measurement:**
- each step leaves a record (issue, commits, CI run, HISTORY entry);
- CI measures every change: tests, coverage of at least 90 %, lint and
  complexity;
- the expected performance of the process (response times) is not
  defined: support is best effort (D-12).

## 6 Maintenance system

### 6.1 Mission of the system (T.2.1<6.1>)

- A desktop mission-analysis tool (SRS 4.1).
- Interoperability: CCSDS ODM with other flight-dynamics tools (ICD).

### 6.2 Software products identification (T.2.1<6.2>)

- **Initial status:** the release built from `compliance/ecss-ccsds-audit`
  (SRelD 4).
- **Product:** SpaceMissionStudio, the Python package `spacemissionstudio`,
  with the version of `spacemissionstudio/__init__.py`.

### 6.3 Support need (T.2.1<6.3>)

Support is needed because the tool depends on things outside it:
- the reused software (Basilisk);
- data that ages (space weather, Earth orientation, leap seconds);
- platforms that change.

The validation must also stay true as these change.

### 6.4 Maintainer (T.2.1<6.4>)

The supplier (SDP 4.7). A named maintainer and a deputy are H02.

### 6.5 Contractual protocols (T.2.1<6.5>)

None: no contract exists between a higher-level contractor and the
maintainer.

## 7 Maintenance concept

### 7.1 Maintenance scope (T.2.1<7.1>)

- **Scope:** the package, its tests, documents and installers.
- **Tailoring of the post-delivery process:** as in 5, for category C.
- **Excluded:**
  - Basilisk itself: problems are reported upstream (H10);
  - Vizard.

### 7.2 Level of support (T.2.1<7.2>)

Best effort. No response times are committed (decision 11, D-12).

### 7.3 Support period (T.2.1<7.3>)

Not defined. The latest release is maintained; earlier releases are not.

### 7.4 Tailoring of the maintenance process (T.2.1<7.4>)

No maintainer's process manual exists. This plan is the process.

## 8 Maintenance activities (T.2.1<8>)

| Activity | When | How |
|---|---|---|
| Update the bundled space weather | Each release; the forecast part ages within months | Download the current CelesTrak SW-All and NASA MSFC tables (with consent); test; commit |
| Leap seconds | When IERS announces one | ERFA (pyerfa) and `naif0012.tls` must both carry it; until then, epochs after the new leap second are 1 s off (`engine/time_system.py`) |
| Requalify a new Basilisk release | Before changing `QUALIFIED_BASILISK_VERSION` | Run the full suite and the validation (SValP) against the new release; re-run VP-0 if models changed; check F-01 and F-07; update the SRF |
| Review dependency versions | Each release | Record them in the SRF; check for security advisories |
| Review the security analysis | Each release | `security_analysis.md` section 7 |

## 9 Maintenance environment

### 9.1 Environment (T.2.1<9.1>)

The development environment (SDP 5.4) is the maintenance environment. It
needs:
- the CI;
- a PC with Basilisk 2.12.0;
- GMAT R2026a, to regenerate references.

### 9.2 Methods and standards (T.2.1<9.2>)

As in development:
- the coding standard;
- the test and validation plans;
- the DRD documents, kept current. CI checks the generated parts.

## 10 Maintenance process

### 10.1 Problem and modification analysis (T.2.1<10.1>)

**Decided (decision 11):**
- SPRs and SMRs as GitHub issues on `0h3xn4/basilisk`, labelled `bug`,
  `accuracy`, `security` or `feature`. The labels are created when the user
  agrees.
- **Priority:**
  - accuracy and security first;
  - then crashes and data loss;
  - then the rest.
- **Configuration control board:** none; the user decides alone (formal
  board waived, D-12). For a customer project, the customer and the
  supplier would form one.

**Phases:** analysis, design, implementation, acceptance test, delivery
(10.2 to 10.6).

### 10.2 Analysis phase (T.2.1<10.2>)

1. Reproduce the problem with a test that fails.
2. Find the root cause. A Basilisk cause is reported upstream; any
   workaround stays outside Basilisk.
3. Estimate the impact on results, as in `phase3_log.md` and `HISTORY.md`.
4. Decide whether a requirement or a document changes.

### 10.3 Design phase (T.2.1<10.3>)

Update the SDD where the architecture changes. The generated components
update themselves.

### 10.4 Implementation phase (T.2.1<10.4>)

- Branch, implement and add tests.
- Run lint and the suite locally.
- The commit message names the SPR or SMR and the requirements affected.

### 10.5 Acceptance test phase (T.2.1<10.5>)

- CI must pass.
- For accuracy-relevant changes, VP-1 must pass; when a model changed,
  VP-0 references are regenerated and reviewed.
- The user accepts.

### 10.6 Delivery phase (T.2.1<10.6>)

**Release:**
- set the version;
- update the SRelD and `HISTORY.md`;
- build with checksums;
- tag.

**Installing a new version:**
- It installs alongside the old one, in a new virtual environment.
  Scenario files carry `schema_version` and are migrated on load
  (`schema/migrations.py`).
- Users keep their scenario files. The old installation stays until they
  remove it.

**Before publishing,** update the user documentation (`USER_MANUAL.md`,
SUM).

## 11 Maintenance training (T.2.1<11>)

A maintainer needs:
- Python;
- Basilisk's architecture (messages, tasks, SysModels);
- the CI and the validation set-up (SValP).

No training material exists beyond these documents.

## 12 Maintenance software product assurance (T.2.1<12>)

- **SPAP:** applies to maintenance.
- **Nonconformances:** handled as SPRs, as GitHub issues (decision 11).
- **Qualification status:**
  - kept by re-running the suite and the validation on each change;
  - recorded in the SVR of each release;
  - the compliance matrix is rebuilt by CI.

## 13 Maintenance configuration management (T.2.1<13>)

- **Configuration management:** as in SDP 6.
- **Handling of change and problem records:**
  - SPRs, SMRs and change requests are issues (proposed);
  - NCRs and RFWs are deviations in `deviations.md`, signed by the
    customer (H08).

## 14 Maintenance records and reports (T.2.1<14>)

**Proposed maintenance record, per release:** the release's SRelD and the
issues it closes. Content:
- requests received;
- their status;
- the changes made;
- the versions affected;
- the tests added.

Maintenance reports go to the user on request (decision 8); the SRelD of each release lists its changes.

## 15 Maintenance report templates (T.2.1<15>)

**Report template:** no template modules exist. The SRelD (Annex G) serves
as the report template for each release.

**Changes to this plan:** this plan is versioned with the code. Changes to
it go through the same change control.
