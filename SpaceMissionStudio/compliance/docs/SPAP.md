# SpaceMissionStudio: Software Product Assurance Plan (SPAP), outline

DRD: ECSS-Q-ST-80C Annex B
Document: SMS-SPAP, issue 1 (outline), 2026-10-08. Remediation R14.

**Status:** an outline, as planned for R14 (`gap_analysis.md`).
- It states the product assurance measures in place and leaves to people
  what only people can provide:
  - the PA organisation, roles and resources (H02);
  - the criticality sign-off and the dependability and safety analysis
    (H04);
  - nonconformance and problem handling (H05);
  - independent review (H06);
  - the agreement of metric thresholds (H09).
- Each section names its gap.

## 1 Introduction (B.2.1<1>)

This plan describes how the quality of SpaceMissionStudio is assured:
- organisation;
- processes;
- methods;
- metrics;
- the compliance with ECSS-Q-ST-80C as tailored for category C.

## 2 Applicable and reference documents (B.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | ECSS-Q-ST-80C Rev.2 |
| RD1 | `compliance/phase0_tailoring.md` (category C tailoring) |
| RD2 | `compliance/compliance_matrix.csv` |
| RD3 | SDP, SVerP, SValP, SUITP, SMP, SRF, security analysis |
| RD4 | `coding_standard.md`, `compliance/metrics.md` |
| RD5 | `compliance/human_actions.md` |

## 3 Terms, definitions and abbreviated terms (B.2.1<3>)

| Term | Meaning |
|---|---|
| PA | Product assurance |
| SPA | Software product assurance |

## 4 System overview (B.2.1<4>)

SRS section 4 and SDD section 4. In brief, SpaceMissionStudio is:
- a desktop mission-analysis tool;
- built on Basilisk 2.12.0, which it reuses unmodified;
- category C (decision 1).

## 5 Software product assurance programme implementation

### 5.1 Organization (B.2.1<5.1>)

**Gap: H02.**
- No PA organisation exists. The user develops and accepts the software,
  assisted by an AI coding assistant.
- No PA function is independent of the development.
- The user left the roles open (decision 8, 2026-10-08). Still to be
  defined:
  - the organisational structure;
  - the interfaces (customer, supplier, Basilisk upstream);
  - the PA manager's independence and reporting line.

### 5.2 Responsibilities (B.2.1<5.2>)

**Proposed:** an SPA manager, who may be the user, is responsible for:
- this plan;
- the PA reports (SPAMR);
- the metrics;
- the compliance matrix;
- nonconformances;
- accepting reused software (H07).

The person is not yet named (H02).

### 5.3 Resources (B.2.1<5.3>)

- **Tools in place:**
  - CI (GitHub Actions), with ruff, pytest and coverage;
  - `compliance/tools/` (metrics, traceability, ICS, matrix, DRD checks).
- **Human resources and skills:** not allocated (H02).

### 5.4 Reporting (B.2.1<5.4>)

- The SPAMR on request only (decision 8). There is no regular PA
  reporting; the audit's SPAMR is the only one so far.
- The CI artefacts on every change: test report, coverage, metrics,
  matrices.

### 5.5 Quality models (B.2.1<5.5>)

The quality characteristics used are those of the SRS:
- functional suitability and accuracy (SRS-P, validated);
- reliability (SRS-RE);
- maintainability (SRS-M, SRS-Q);
- security (SRS-S);
- portability (SRS-PO);
- usability (SRS-H).

No formal quality model has been agreed (H09).

### 5.6 Risk management (B.2.1<5.6>)

PA contributes the technical risks it finds:
- findings F-nn;
- security risks S-nn;
- known problems K-nn.

There is no project risk process (H05).

### 5.7 Supplier selection and control (B.2.1<5.7>)

Not applicable: there are no lower-level suppliers. The reused software is
covered in 6.7.

### 5.8 Methods and tools (B.2.1<5.8>)

SDP 5.3 and 5.4. All are mature, widely used open-source tools.

### 5.9 Process assessment and improvement (B.2.1<5.9>)

- **Scope:** none. Process assessment and improvement (Q-ST-80C 5.7) are
  waived by the user (decision 8, deviation D-09).
- **Improvement:** the audit's findings and remediations (R01 to R15) are
  the improvement actions so far.

### 5.10 Operations and maintenance (B.2.1<5.10>)

- **Quality measures for maintenance:** the same CI gates (SMP 5).
- **Records:** the release records (SMP 14).

## 6 Software process assurance

### 6.1 Software development cycle (B.2.1<6.1>)

- **Life cycle:** SDP 5.2.
- **Milestone before validation:** a test readiness review is proposed in
  the review set of SDP 5.2.3 (H01).

### 6.2 Projects plans (B.2.1<6.2>)

| Plan | Status |
|---|---|
| SDP (with CM description) | Draft |
| SVerP, SValP, SUITP | Draft |
| SMP | Draft |
| SPAP | This outline |
| Software security management plan (E-ST-40C 5.11.2) | Waived by the user (decision 8, deviation D-10) |
| SCMP | Its DRD (ECSS-M-ST-40C) is not supplied; described in SDP 6 |

All plans are updated at each release (SDP 5.5.2).

### 6.3 Dependability and safety (B.2.1<6.3>)

**Gap: H04.**
- No dependability or safety analysis exists.
- The tool is category C by the user's decision. The criticality
  classification is to be signed off with an analysis.
- No measures for critical software are applied (SDD 6).

### 6.4 Security (B.2.1<6.4>)

- **Security assurance:** `security_analysis.md`:
  - S-01 to S-12;
  - the treatment and its tests;
  - the ruff S rules in CI.
- **Level:** low (D8).
- **Gaps:**
  - the security management plan and the security manager (H02);
  - the open items S-05, S-06 (H11) and S-08.

### 6.5 Documentation and configuration management (B.2.1<6.5>)

- **Documentation:** the DRD checker and the generated parts keep the
  documents complete and current (SDP 5.5).
- **Configuration management:** SDP 6.
- **Nonconformance control:** not established (H05). It should apply from
  the first release after this audit.
- **Protection of delivered software:**
  - SHA-256 checksums of every built package (security analysis S-07);
  - releases are labelled by version;
  - signing is H05.

### 6.6 Process metrics (B.2.1<6.6>)

- **Metrics collected:** `compliance/tools/metrics.py`:
  - corrective commits per kSLOC (a proxy);
  - test counts.
- **Missing:** effort and schedule metrics (no records).
- **Use:** reported in the SPAMR.

### 6.7 Reused software (B.2.1<6.7>)

- **Assessment:** in the SRF (Basilisk and the packages).
- **Delta qualification:** the tool's validation (V-01, V-02, V-04 to
  V-08) against the pinned version.
- **Requalification:** at each new Basilisk version (SMP 8).
- **Acceptance:** H07.

### 6.8 Process activities (B.2.1<6.8>)

| Process | Assurance |
|---|---|
| Requirements analysis | SRS with sources and verification methods; traced to components; review H01 |
| Architectural and detailed design | SDD; generated traceability; review H01 |
| Coding | Coding standard; lint (incl. security) in CI; complexity in metrics; independent review H06 |
| Testing and validation | SUITP, SVS; coverage of at least 90 % in CI; external references |
| Delivery and acceptance | SRelD, checksums; acceptance H01 |
| Operations and maintenance | SMP |

### 6.9 Procedures and standards (B.2.1<6.9>)

| Aspect | Standard or procedure |
|---|---|
| Project management | SDP |
| Risk management | None (H05) |
| Configuration and documentation management | SDP 5.5, 6 |
| Verification and validation | SVerP, SValP |
| Requirements and design | SRS and SDD per E-ST-40C Annexes D and F |
| Coding | `coding_standard.md` |
| Metrication | `metrics.py` |
| Nonconformance control | None (H05) |
| Security | `security_analysis.md` |

**Adherence:** CI enforces what can be computed: lint, tests, coverage,
documents. The rest needs review (H01, H06).

## 7 Software product quality assurance (B.2.1<7>)

| Product metric | Target | Collection |
|---|---|---|
| Statement coverage | ≥ 90 % (C-10; category C target to be agreed, H09) | CI, `metrics.py --fail-under 90` |
| Static analysis findings | 0 (C-8) | CI, ruff |
| Cyclomatic complexity | ≤ 15 for new code; existing functions above it listed (C-7) | `metrics.py` |
| Requirement traceability | Every SRS requirement allocated (SDD); tests tagged with requirements | `build_sdd_components.py`, `build_traceability.py` |
| Validation accuracy | SRS-P-01 to SRS-P-08 tolerances | VP-1 |

The current values are in the SPAMR.

## 8 Compliance matrix to software product assurance requirements (B.2.1<8>)

`compliance/compliance_matrix.csv` (rebuilt by CI from
`compliance/audit/`) lists, for every ECSS-Q-ST-80C requirement:
- its identifier;
- its applicability under the category C tailoring;
- its status: C, P (partial), NC, N/A, or "requires human or process
  action";
- its evidence or justification.

The summary counts are in the SPAMR.
