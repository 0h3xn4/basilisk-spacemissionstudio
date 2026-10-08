#
#  ISC License
#
#  Copyright (c) 2026, Autonomous Vehicle Systems Lab, University of Colorado at Boulder
#
#  Permission to use, copy, modify, and/or distribute this software for any
#  purpose with or without fee is hereby granted, provided that the above
#  copyright notice and this permission notice appear in all copies.
#
#  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
#  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
#  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
#  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
#  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
#  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
#  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#
"""Phase 1 assessments: ECSS-E-ST-40C Rev.1 and ECSS-Q-ST-80C Rev.2 at
criticality C. Same rule format as ``assessments_technical``. Most rules
cover a clause group; exceptions follow their group.

Context used throughout:

* Single-person project. The user is customer, supplier, maintainer and
  operator. Every one of the 118 commits touching SpaceMissionStudio/ is
  authored by an AI assistant ("Claude"); there is no record of independent
  human review of the code.
* What exists: git history; HISTORY.md (change log with rationale and
  verification notes); README.md; USER_MANUAL.md; docs/ux_audit.md;
  1403 pytest functions in 98 files (tests/); installers (packaging/);
  run provenance (engine/results.py RunProvenance: tool and Basilisk
  versions, integrator, step).
* What does not: plans (SDP, SPAP, SVerP, SValP, SCMP, SMP), SRS, SDD, ICD,
  SVS/SVR, SRF, reviews, coverage measurement, metrics, a written coding
  standard, CI for this tool (the repository's workflows build Basilisk only).
"""

_H = "H"
_REVIEW_FIX = ("Reviews waived by the user 2026-10-08 (deviation D-08, decision 7; signature pending, H08); "
               "the requirement stays open.")
_PLAN_FIX = "Draft the plan in Phase 4 (compliance/docs/); user approves."
_NO_SDP = "No software development plan; life cycle and standards are implicit."

SOFTWARE_RULES = [
    # ======================= ECSS-E-ST-40C Rev.1 =================================
    # 5.2 software related system requirements: customer side
    ("E-ST-40C", "5.2.*", "N", "-", "No customer requirements baseline: waived by the user (decision 9, 2026-10-08); the SRS is derived from the tool, not from a baseline.", "-", "M", "no", "H03,D-11"),
    ("E-ST-40C", "5.2.2.4a", "NA", "-", "No hardware/software co-engineering: the tool runs on COTS desktops.",
     "-", "S", "no", ""),
    ("E-ST-40C", "5.2.4.4*", "NA", "-", "No system database.", "-", "S", "no", ""),
    ("E-ST-40C", "5.2.4.6a", "NA", "-", "No on-board control procedures.", "-", "S", "no", ""),
    ("E-ST-40C", "5.2.5a", "N", "-", "No SRR held.", _REVIEW_FIX, "S", "no", "H01,D-08"),
    # 5.3 management
    ("E-ST-40C", "5.3.2.1*", "P", "compliance/docs/SDP.md", "SDP drafted; no master schedule, risk process or staffing (H02, H05).", "Approve the SDP; close H02, H05.", "M", "no", "R14,H02,H05"),
    ("E-ST-40C", "5.3.2.2a", "P", "compliance/docs/SDP.md", "SDP drafted, not approved.", "Approve the SDP (H01).", "S", "no", "R14,H01"),
    ("E-ST-40C", "5.3.2.3a", "P", "compliance/docs/SRF.md (reused items, versions, checksums, licences); reuse "
     "accepted by the user as-is (decision 13)", "No procurement process as such (the items are open-source "
     "software installed from PyPI); exportability not identified (left open, decision 13).", "-", "S",
     "yes (Basilisk reuse)", "R14,H07"),
    ("E-ST-40C", "5.3.2.4*", "NA", "-", "No automatic code generation from models.", "-", "S", "no", ""),
    ("E-ST-40C", "5.3.2.5a", "P", "compliance/docs/SDP.md section 6 (configuration management description); git", "Changes go through git and CI; no change board (waived, D-12) and no release tags yet (version 2.1.0 to be tagged, decision 11).", "-", "S", "no", "R14,D-12"),
    ("E-ST-40C", "5.3.3*", "N", "-", "No joint or technical reviews held.", _REVIEW_FIX, "M", "no", "H01,D-08"),
    ("E-ST-40C", "5.3.4*", "N", "-", "No project reviews (SRR, PDR, CDR, QR, AR) held.", _REVIEW_FIX, "M", "no", "H01,D-08"),
    ("E-ST-40C", "5.3.5*", "N", "-", "No TRR/TRB/DRB/SVSR held.", _REVIEW_FIX, "S", "no", "H01,D-08"),
    ("E-ST-40C", "5.3.6.1*", "NA", "-", "Flight-software review phasing; the tool is ground software.", "-", "S",
     "no", ""),
    ("E-ST-40C", "5.3.6.2a", "N", "-", "The ground-software life cycle has not been chosen and documented.",
     _PLAN_FIX, "S", "no", "R14"),
    ("E-ST-40C", "5.3.7.1a", "P", "compliance/docs/ICD.md (interfaces, versioned scenario schema with migrations)", "Interfaces defined in the ICD, drafted by the supplier; reviews waived (D-08). ECSS-M-ST-40 not supplied (H12).", "-", "S", "no", "R14,H12"),
    ("E-ST-40C", "5.3.8*", "P", "HISTORY.md: measured run time and memory (e.g. 5-year run 50 min, 450 MB)",
     "Measured, but no budget targets or margin philosophy.", "Define CPU/memory budgets for reference runs "
     "in the SRS; measure them in the SVR.", "S", "no", "R14"),
    ("E-ST-40C", "5.3.9*", "C", "compliance/compliance_matrix.csv (every requirement with status, evidence, gap; rebuilt by CI from compliance/audit/)", "-", "-", "S", "no", "R14"),
    # 5.4 requirements and architecture
    ("E-ST-40C", "5.4.2.1a", "P", "compliance/docs/SRS.md (SRS-F/P/I/O/R/D/S/PO/Q/RE/M/DEL/DF/H/A, 63 requirements with identifiers, sources and verification methods)", "SRS drafted from the implementation, not from a requirements baseline (H03); not reviewed.", "Review at SRR/PDR (H01).", "L", "no", "R14,H01,H03"),
    ("E-ST-40C", "5.4.2.2a", "NA", "-", "In-flight modification: flight software only.", "-", "S", "no", ""),
    ("E-ST-40C", "5.4.2.4a", "N", "-", "No SWRR.", _REVIEW_FIX, "S", "no", "H01,D-08"),
    ("E-ST-40C", "5.4.3.*", "P", "compliance/docs/SDD.md, SDD_components.md (generated component descriptions and traceability)", "Architecture documented after the fact; not reviewed (PDR, H01).", "Review at PDR (H01).", "M", "yes (Basilisk is the simulation core)", "R14,H01"),
    ("E-ST-40C", "5.4.3.2b", "P", "compliance/docs/security_analysis.md section 5 (residual vulnerabilities after treatment)", "Analysis by the supplier; not reviewed at PDR.", "Review at PDR (H01).", "S", "no", "R15,H01"),
    ("E-ST-40C", "5.4.3.6a", "NA", "-", "The tool is not developed for reuse.", "-", "S", "no", ""),
    ("E-ST-40C", "5.4.3.6b", "NA", "-", "As 5.4.3.6a.", "-", "S", "no", ""),
    ("E-ST-40C", "5.4.3.6c", "C", "Mission data (scenarios JSON, space-weather data files) separate from code",
     "-", "-", "S", "no", ""),
    ("E-ST-40C", "5.4.3.7a", "P", "compliance/docs/SRF.md (reuse analysis of Basilisk 2.12.0 and the packages)", "Analysis done; the user accepted the reuse as-is (decision 13), for all functions used; no requirements baseline (D-11).", "-", "S", "no", "R14,H07"),
    ("E-ST-40C", "5.4.3.8a", "P", "compliance/docs/SUITP.md 7.1 (integration strategy)", "Strategy documented; drafted by the supplier; reviews waived (D-08).", "-", "S", "no", "R14"),
    ("E-ST-40C", "5.4.4a", "N", "-", "No PDR.", _REVIEW_FIX, "S", "no", "H01,D-08"),
    # 5.5 design and implementation
    ("E-ST-40C", "5.5.2.*", "P", "compliance/docs/SDD.md, SDD_components.md (generated component descriptions)", "Detailed design described from the code; drafted by the supplier; reviews waived (D-08).", "-", "M", "no", "R14"),
    ("E-ST-40C", "5.5.2.5*", "N", "gui/*_widget.py QThread workers; engine/propellant_budget.py process pool",
     "Concurrency (Qt worker threads, a spawned process pool, Basilisk single-thread runs) is not documented "
     "or justified; no real-time constraints apply.", "Describe threads, processes and shared data in the SDD.",
     "S", "no", "R14"),
    ("E-ST-40C", "5.5.2.8a", "P", "compliance/docs/SUM.md (maps the DRD to USER_MANUAL.md and adds data files, security, messages, recovery)", "SUM drafted; not reviewed with users; the message list is not exhaustive.", "Review with users (H01).", "M", "no", "R14,H01"),
    ("E-ST-40C", "5.5.2.9a", "P", "compliance/docs/SUITP.md, SUITP_test_cases.md", "Unit and integration test plan drafted by the supplier; reviews waived (D-08).", "-", "S", "no", "R14"),
    ("E-ST-40C", "5.5.2.10a", "N", "-", "No DDR.", _REVIEW_FIX, "S", "no", "H01,D-08"),
    ("E-ST-40C", "5.5.3.1a", "P", "spacemissionstudio/ source; R10 (Phase 2): compliance/docs/coding_standard.md (rules C-1 to C-15); "
     "build and install steps in pyproject.toml and the CI workflow .github/workflows/spacemissionstudio.yml", "Coding standard and an automated "
     "build exist; the build procedure is not yet in a release document.", "SRelD (Phase 4).", "S", "no",
     "R10,R14"),
    ("E-ST-40C", "5.5.3.2*", "P", "tests/ (1479 test functions; Basilisk-backed tests marked requires_basilisk); "
     "R11/R12 (Phase 2): requirement markers traced by compliance/tools/build_traceability.py "
     "(compliance/traceability_matrix.csv), JUnit test report and coverage produced by .github/workflows/spacemissionstudio.yml", "Unit tests "
     "are traced and reported, but boundary values (5.5.3.2c) are tested only where a rule needs them, not "
     "systematically for every unit, and the test procedures are not in a SUITP.", "SUITP (Phase 4); "
     "boundary-value tests under coding standard rule C-9 as units change.", "M", "no", "R11,R12,R14"),
    ("E-ST-40C", "5.5.4.*", "P", "tests/ integration tests against Basilisk 2.12 (test_service_*, "
     "test_template_claims.py)", "Integration testing happens but is not planned or reported.",
     "SUITP integration part; reports.", "S", "no", "R12,R14"),
    # 5.6 validation
    ("E-ST-40C", "5.6.2.1*", "P", "compliance/docs/SValP.md", "Validation plan drafted by the supplier; reviews waived (D-08).", "-", "M", "no", "R14"),
    ("E-ST-40C", "5.6.3.*", "P", "compliance/docs/SValP.md, SVS.md, SVR.md; tests/validation (V-01, V-02, V-04 to V-08 within tolerance)", "Validation against the TS is specified, done and reported; not reviewed (CDR, H01); SRS-P-09/R-02 not measured (H13).", "Review (H01); measure (H13).", "M", "no", "R13,R14,H01,H13"),
    ("E-ST-40C", "5.6.3.4a", "N", "-", "No CDR.", _REVIEW_FIX, "S", "no", "H01,D-08"),
    ("E-ST-40C", "5.6.4.*", "N", "compliance/docs/SValP.md 4.1", "Validation against a requirements baseline is not possible: the baseline is waived (decision 9). Validation against the technical specification (5.6.3) is done.", "-", "M", "no", "H03,D-11"),
    ("E-ST-40C", "5.6.4.4a", "N", "-", "No QR.", _REVIEW_FIX, "S", "no", "H01,D-08"),
    ("E-ST-40C", "5.6.5a", "P", "compliance/docs/SVR.md 4.6 (validation status per case)", "Status reported by the supplier; not reviewed.", "Review (H01).", "S", "no", "R14,H01"),
    # 5.7 delivery and acceptance
    ("E-ST-40C", "5.7.2.1a", "P", "packaging/; compliance/docs/SRelD.md", "Release document drafted for an unreleased candidate (version still 2.0.0).", "Release with a new version (H05).", "S", "no", "R14,H05"),
    ("E-ST-40C", "5.7.2.1b", "P", "packaging/build_wheel.sh, build_wheel.ps1, build_deb.sh write SHA-256 checksums (security analysis S-07)", "Releases are checksummed; signing waived by the user (decision 11); dependencies not pinned by hash (S-08).", "Lock file with hashes (S-08).", "S", "no", "R15,D-13"),
    ("E-ST-40C", "5.7.2.2a", "NA", "-", "No training specified in a business agreement.", "-", "S", "no", ""),
    ("E-ST-40C", "5.7.2.3*", "P", "packaging/README.md, install scripts; compliance/docs/security_analysis.md section 6; SUM 9.2, 9.9", "Installation security assessed; installs from PyPI without hash checking (S-08); Windows installer not tested (H13).", "S-08 lock file; test (H13).", "S", "no", "R15,H13"),
    ("E-ST-40C", "5.7.2.4*", "P", "packaging/ (kernel pre-fetch at install); SUM 9.2", "No installation report or template.", "Write one when installing for another user.", "S", "no", "R14"),
    ("E-ST-40C", "5.7.3.*", _H, "-", "No acceptance test plan, testing or AR.", "User defines and runs "
     "acceptance tests (a draft can be derived from the SVS).", "M", "no", "H01,H03"),
    # 5.8 verification
    ("E-ST-40C", "5.8.2.1*", "P", "compliance/docs/SVerP.md", "Verification plan drafted by the supplier; reviews waived (D-08).", "-", "M", "no", "R14"),
    ("E-ST-40C", "5.8.3.1a", "N", "-", "No customer requirements baseline: waived by the user (decision 9, 2026-10-08); the SRS is derived from the tool, not from a baseline.", "-", "S", "no", "H03,D-11"),
    ("E-ST-40C", "5.8.3.*", "P", "compliance/docs/SVR.md (verification by the supplier)", "Verification done and reported by the supplier; no independent verification (H06); drafted by the supplier; reviews waived (D-08).", "-", "M", "no", "R14,H06"),
    ("E-ST-40C", "5.8.3.5a", "P", "R10 (Phase 2): ruff rule set configured in pyproject.toml, zero findings, run "
     "by .github/workflows/spacemissionstudio.yml; tests", "Code verified by tests and static analysis; no independent human review yet: the reviewer is to be named "
     "(decision 12); the review guide is prepared (compliance/reviews/code_review_guide.md).", "Independent review "
     "with the guide (H06).", "M",
     "no", "R10,R14,H06"),
    ("E-ST-40C", "5.8.3.5b", "P", "R11 (Phase 2): statement and branch coverage measured by pytest-cov in "
     ".github/workflows/spacemissionstudio.yml (statement coverage >= 90 % enforced by metrics.py --fail-under 90) and reported in compliance/metrics.md", "Coverage is measured and "
     "enforced, but Table 5-1 gives 'TBA' for category C: the 90 % target of coding standard rule C-10 is "
     "the supplier's proposal, not an agreed figure.", "Customer agrees the coverage target (H09).", "S", "no",
     "R11,H09"),
    ("E-ST-40C", "5.8.3.5c", "C", "R11 (Phase 2): coverage measured from the execution of the test suite "
     "(pytest-cov, .github/workflows/spacemissionstudio.yml; compliance/metrics.md)", "-", "-", "S", "no", "R11"),
    ("E-ST-40C", "5.8.3.5d", "P", "R11 (Phase 2): coding standard rule C-10 requires inspection of code not "
     "reached by tests", "The uncovered code has not yet been inspected and justified.", "Coverage analysis "
     "of the uncovered lines in the SVR (Phase 4).", "S", "no", "R11,R14"),
    ("E-ST-40C", "5.8.3.5e", "NA", "-", "Python source is executed directly; no object code.", "-", "S", "no", ""),
    ("E-ST-40C", "5.8.3.5f", "P", "R10 (Phase 2): ruff (pyflakes, pycodestyle, bugbear; complexity C901) "
     "configured in pyproject.toml, zero findings, run in .github/workflows/spacemissionstudio.yml; security rules (ruff S) reviewed in R15",
     "Robustness is checked by static analysis; the robustness verification report (SVR) is not written and "
     "no type checker is used.", "SVR (Phase 4).", "S", "no", "R10,R14"),
    ("E-ST-40C", "5.8.3.11*", "NA", "-", "Schedulability: no real-time software.", "-", "S", "no", ""),
    ("E-ST-40C", "5.8.3.12*", "N", "-", "Technical budgets (CPU/memory) not estimated or tracked.", "As 5.3.8.",
     "S", "no", "R14"),
    # 5.9 operation, 5.10 maintenance, 5.11 security
    ("E-ST-40C", "5.9.*", "N", "compliance/docs/SMP.md 7.2 (best effort)", "No operation support entity or procedure: formal operation support waived by the user (decision 11); support is best effort.", "-", "S", "no", "H05,D-12"),
    ("E-ST-40C", "5.10.*", "P", "compliance/docs/SMP.md (process; problem reports as GitHub issues, decision 11)", "Maintenance process defined; the issue procedure is not yet in use; no change board (D-12).", "-", "M", "no", "R14,H05"),
    ("E-ST-40C", "5.11.2*", "N", "-", "No software security management plan: waived by the user (decision 8); no security manager named (roles open, H02).", "-", "S", "no", "H02,D-10"),
    ("E-ST-40C", "5.11.*", "P", "compliance/docs/security_analysis.md (S-01 to S-12, treatments with tests); ruff security rules in CI", "Analysis by the supplier at security level low (D8); not reviewed at the milestones (H01); open items S-05, S-06 (H11), S-08.", "Review (H01); close H11, S-08.", "M", "no", "R15,H01,H11"),
    # Annexes: DRDs
    ("E-ST-40C", "B.*", "N", "-", "No SSS: the customer baseline is waived (decision 9).", "-", "M", "no", "H03,D-11"),
    ("E-ST-40C", "C.*", "N", "-", "No IRD: the customer baseline is waived (decision 9).", "-", "S", "no", "H03,D-11"),
    ("E-ST-40C", "D.*", "P", "compliance/docs/SRS.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("E-ST-40C", "D.2.1<1>*", "C", "compliance/docs/SRS.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "D.2.1<2>*", "C", "compliance/docs/SRS.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "D.2.1<3>*", "C", "compliance/docs/SRS.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "E.*", "P", "compliance/docs/ICD.md, ICD_scenario_fields.md, ICD_cli.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("E-ST-40C", "E.2.1<1>*", "C", "compliance/docs/ICD.md, ICD_scenario_fields.md, ICD_cli.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "E.2.1<2>*", "C", "compliance/docs/ICD.md, ICD_scenario_fields.md, ICD_cli.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "E.2.1<3>*", "C", "compliance/docs/ICD.md, ICD_scenario_fields.md, ICD_cli.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "F.*", "P", "compliance/docs/SDD.md, SDD_components.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "yes (Basilisk is the simulation core)", "R14,H01"),
    ("E-ST-40C", "F.2.1<1>*", "C", "compliance/docs/SDD.md, SDD_components.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "F.2.1<2>*", "C", "compliance/docs/SDD.md, SDD_components.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "F.2.1<3>*", "C", "compliance/docs/SDD.md, SDD_components.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "G.*", "P", "compliance/docs/SRelD.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("E-ST-40C", "G.2.1<1>*", "C", "compliance/docs/SRelD.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "G.2.1<2>*", "C", "compliance/docs/SRelD.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "G.2.1<3>*", "C", "compliance/docs/SRelD.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "H.*", "P", "compliance/docs/SUM.md, USER_MANUAL.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("E-ST-40C", "H.2.1<1>*", "C", "compliance/docs/SUM.md, USER_MANUAL.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "H.2.1<2>*", "C", "compliance/docs/SUM.md, USER_MANUAL.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "H.2.1<3>*", "C", "compliance/docs/SUM.md, USER_MANUAL.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "I.*", "P", "compliance/docs/SVerP.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("E-ST-40C", "I.2.1<1>*", "C", "compliance/docs/SVerP.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "I.2.1<2>*", "C", "compliance/docs/SVerP.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "I.2.1<3>*", "C", "compliance/docs/SVerP.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "J.*", "P", "compliance/docs/SValP.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("E-ST-40C", "J.2.1<1>*", "C", "compliance/docs/SValP.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "J.2.1<2>*", "C", "compliance/docs/SValP.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "J.2.1<3>*", "C", "compliance/docs/SValP.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "K.*", "P", "compliance/docs/SUITP.md, SUITP_test_cases.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("E-ST-40C", "K.2.1<1>*", "C", "compliance/docs/SUITP.md, SUITP_test_cases.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "K.2.1<2>*", "C", "compliance/docs/SUITP.md, SUITP_test_cases.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "K.2.1<3>*", "C", "compliance/docs/SUITP.md, SUITP_test_cases.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "L.*", "P", "compliance/docs/SVS.md, SVS_test_cases.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("E-ST-40C", "L.2.1<1>*", "C", "compliance/docs/SVS.md, SVS_test_cases.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "L.2.1<2>*", "C", "compliance/docs/SVS.md, SVS_test_cases.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "L.2.1<3>*", "C", "compliance/docs/SVS.md, SVS_test_cases.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "M.*", "P", "compliance/docs/SVR.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("E-ST-40C", "M.2.1<1>*", "C", "compliance/docs/SVR.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "M.2.1<2>*", "C", "compliance/docs/SVR.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "M.2.1<3>*", "C", "compliance/docs/SVR.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "N.*", "P", "compliance/docs/SRF.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "yes", "R14,H01"),
    ("E-ST-40C", "N.2.1<1>*", "C", "compliance/docs/SRF.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "N.2.1<2>*", "C", "compliance/docs/SRF.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "N.2.1<3>*", "C", "compliance/docs/SRF.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "O.*", "P", "compliance/docs/SDP.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("E-ST-40C", "O.2.1<1>*", "C", "compliance/docs/SDP.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "O.2.1<2>*", "C", "compliance/docs/SDP.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "O.2.1<3>*", "C", "compliance/docs/SDP.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "P.*", "N", "-", "No SRevP written: reviews are not yet planned by the customer and the SRevP cites ECSS-M-ST-10-01, which was not supplied.", "Decide whether an SRevP is wanted; supply ECSS-M-ST-10-01 (H12).", "S", "no", "H01,H12"),
    ("E-ST-40C", "T.*", "P", "compliance/docs/SMP.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("E-ST-40C", "T.2.1<1>*", "C", "compliance/docs/SMP.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "T.2.1<2>*", "C", "compliance/docs/SMP.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "T.2.1<3>*", "C", "compliance/docs/SMP.md section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("E-ST-40C", "R.*", "C", "compliance/phase0_tailoring.md; requirements/ECSS-E-ST-40C.csv crit_C",
     "-", "-", "S", "no", ""),

    # ======================= ECSS-Q-ST-80C Rev.2 =================================
    ("Q-ST-80C", "5.1.*", _H, "-", "No SPA manager or security manager named: the user left the roles open (decision 8, 2026-10-08); responsibilities, resources and independence (5.1.4.2a, 5.1.3.2a) undefined.", "User names the roles (H02).", "S", "no", "H02"),
    ("Q-ST-80C", "5.1.5*", "N", "-", "No training plan or training records: waived by the user (decision 8).", "-", "S", "no", "H02,D-09"),
    ("Q-ST-80C", "5.2.1*", "P", "compliance/docs/SPAP.md (outline)", "SPAP is an outline; organisation sections wait for H02.", "Complete the SPAP once the roles are named (H02).", "M", "no", "R14,H02"),
    ("Q-ST-80C", "5.2.2*", _H, "compliance/docs/SPAMR.md (the audit's report)", "PA reporting only on request (decision 8); no regular reports.", "Report on request.", "S", "no", "H02"),
    ("Q-ST-80C", "5.2.3*", _H, "-", "No audits.", "User plans audits as needed (category C: Y).", "S", "no",
     "H02"),
    ("Q-ST-80C", "5.2.4*", _H, "-", "No alert process.", "Subscribe to Basilisk/dependency advisories; record.",
     "S", "no", "H05"),
    ("Q-ST-80C", "5.2.5*", "P", "compliance/docs/SMP.md 10.1 (GitHub issues with labels, decision 11)", "Procedure defined, not yet in use (no labels created).", "Create the labels when the user agrees.", "S", "no", "H05"),
    ("Q-ST-80C", "5.2.6*", "P", "compliance/docs/SMP.md 12, 13 (nonconformances handled as issues)", "Procedure defined, not yet in use.", "-", "S", "no", "H05"),
    ("Q-ST-80C", "5.2.7*", "P", "compliance/docs/SRS.md 5.10 (SRS-Q-01 to Q-03), SPAP.md 5.5", "Quality requirements stated; no formal quality model; thresholds not agreed (H09).", "-", "S", "no", "R14,H09"),
    ("Q-ST-80C", "5.3.*", "N", "Technical risks logged as findings F-nn, S-nn, K-nn", "No risk management or critical-item control process: waived by the user (decision 11).", "-", "S", "no", "H05,D-12"),
    ("Q-ST-80C", "5.4.*", _H, "-", "Supplier selection/control not applicable as such (no subcontractor); "
     "reused OSS suppliers (Basilisk) not assessed.", "Record OSS dependencies and their status in the SRF.",
     "S", "yes", "H07"),
    ("Q-ST-80C", "5.4.4a", "P", "compliance/docs/dependability_safety_analysis.md section 1 (category C signed off by the user, decision 10)", "Not derived from a system-level analysis: ECSS-Q-ST-30/-40 not supplied (H12); no lower-level suppliers to inform.", "-", "S", "no", "H04,H12"),
    ("Q-ST-80C", "5.5.*", "P", "compliance/docs/SRF.md section 4 (items, versions, licences), 9 (SHA-256); "
     "pyproject.toml", "Components listed with versions and licences and accepted by the user as listed "
     "(decision 13); no procurement documents or receiving inspection reports; licences of Basilisk's own "
     "dependencies and of Vizard not reviewed.", "-", "S", "yes", "H07,R01"),
    ("Q-ST-80C", "5.5.6a", _H, "-", "Exportability constraints not identified: left open by the user "
     "(decision 13).", "Classify the tool and the reused items, or have export control do it (H07).", "S",
     "yes", "H07"),
    ("Q-ST-80C", "5.6.*", "P", "pyproject.toml (Python, pytest, pytest-qt); ruff", "Tools exist but are not "
     "selected/justified or documented.", "Tools and environment section in the SDP.", "S", "no", "R14"),
    ("Q-ST-80C", "5.7.*", "N", "-", "No process assessment or improvement process: waived by the user (decision 8).", "-", "S", "no", "H02,D-09"),
    ("Q-ST-80C", "6.1.*", "P", "compliance/docs/SDP.md 5.2, SPAP.md 6.1", "Life cycle defined (incremental); drafted by the supplier; reviews waived (D-08).", "-", "S", "no", "R14"),
    ("Q-ST-80C", "6.1.5a", "N", "-", "No TRR: reviews waived (decision 7).", "-", "S", "no", "H01,D-08"),
    ("Q-ST-80C", "6.2.1*", "P", "compliance/docs/SDP.md, SPAP.md 6.2 (plans and their status)", "Plans written after the activities they cover; drafted by the supplier; reviews waived (D-08).", "-", "M", "no", "R14"),
    ("Q-ST-80C", "6.2.2.1a", "P", "compliance/docs/dependability_safety_analysis.md section 1", "Classification by the user's judgement; the ECSS-Q-ST-40 6.5.6.3 analysis is not available (H12).", "-", "S", "no", "H04,H12"),
    ("Q-ST-80C", "6.2.2.*", "P", "compliance/docs/dependability_safety_analysis.md (functional FMEA, FM-01 to FM-12, safeguards with evidence)", "Drafted by the supplier, waiting for the user's approval; methods not agreed with a separate customer; no system-level analysis to start from.", "User approves the analysis (H04).", "S", "no", "H04"),
    ("Q-ST-80C", "6.2.3.*", "P", "compliance/docs/dependability_safety_analysis.md section 4 (measures for critical software: the whole tool, category C)", "Measures applied and verified by the supplier; unreachable-code analysis (6.2.3.6a) open; no independent verification (H06).", "Analyse the uncovered branches; H06.", "S", "no", "H04,H06"),
    ("Q-ST-80C", "6.2.4.*", "P", "git; version 2.0.0 (pyproject.toml); schema_version + migrations; "
     "R01 (Phase 2): spacemissionstudio/dependencies.py QUALIFIED_BASILISK_VERSION = 2.12.0, installers pin "
     "bsk[all]==2.12.0, start-up check (GUI status bar, CLI run), RunProvenance/provenance.json records "
     "Basilisk version and qualification, dependency versions, scenario SHA-256 and reference data files "
     "(tests/test_dependencies.py)", "No SCMP; no tagged releases of this tool.",
     "SCMP description (Phase 4); tag releases.", "S", "yes (Basilisk version control)", "R01,R14"),
    ("Q-ST-80C", "6.2.5*", "P", "R11 (Phase 2): compliance/tools/metrics.py run in .github/workflows/spacemissionstudio.yml (size, complexity, "
     "coverage, failures, corrective-commit count as a problem proxy) -> compliance/metrics.md", "Product "
     "metrics are collected on every change; process metrics against a plan and their analysis are not.",
     "Metrics section of the SPAP and PA reports (Phase 4).", "S", "no", "R11,R14"),
    ("Q-ST-80C", "6.2.5.3a", "H", "-", "Duration and effort against a planned schedule need a schedule and "
     "effort records, which only the project can keep.", "Keep a schedule and effort log (H02).", "S", "no",
     "H02"),
    ("Q-ST-80C", "6.2.5.5a", "P", "compliance/docs/SPAMR.md section 7 (metrics)", "Metrics in the audit's PA report; further reports on request (decision 8).", "-", "S", "no", "R14"),
    ("Q-ST-80C", "6.2.6.*", "P", "tests/; ruff; compliance/docs/SVerP.md, SVR.md; compliance/reviews/code_review_guide.md",
     "Verification by tests and static analysis, planned and reported by the supplier; no independent human review "
     "of the AI-written code yet (reviewer to be named, decision 12).", "Independent review with the guide (H06).", "M", "no",
     "R14,H06"),
    ("Q-ST-80C", "6.2.7.*", "P", "compliance/docs/SRF.md; R01 version pin and check; validation V-01 to V-08 of the reused models", "Reuse analysed and documented; accepted by the user as-is (decision 13). Basilisk lacks ECSS documentation and coverage figures; functions outside V-01 to V-08 rest on Basilisk's own tests.", "-", "M", "yes", "R14,R01,H07"),
    ("Q-ST-80C", "6.2.8.*", "NA", "-", "No automatic code generation from models. (AI-assisted coding is "
     "covered by review, H06.)", "-", "S", "no", "H06"),
    ("Q-ST-80C", "6.2.9.*", "P", "compliance/docs/security_analysis.md; security level low (decision D8)", "Analysis done and reported by the supplier; methods not agreed with the customer; no security manager (H02).", "Agree methods; name the security manager (H02).", "S", "no", "R15,H02"),
    ("Q-ST-80C", "6.2.10.*", _H, "-", "As 6.2.9.", "As 6.2.9.", "S", "no", "R15"),
    ("Q-ST-80C", "6.3.1*", "N", "-", "No customer requirements baseline: waived by the user (decision 9, 2026-10-08); the SRS is derived from the tool, not from a baseline.", "-", "S", "no", "H03,D-11"),
    ("Q-ST-80C", "6.3.2*", "P", "compliance/docs/SRS.md", "Requirements derived from the implementation; drafted by the supplier; reviews waived (D-08). no baseline (D-11).", "-", "M", "no", "R14,D-11"),
    ("Q-ST-80C", "6.3.3*", "P", "compliance/docs/SDD.md", "Design described after the fact; drafted by the supplier; reviews waived (D-08).", "-", "M", "no", "R14"),
    ("Q-ST-80C", "6.3.4*", "P", "R10 (Phase 2): compliance/docs/coding_standard.md (naming, comment, security rules C-1 to C-15; tools; "
     "code evaluation); ruff configured in pyproject.toml; .github/workflows/spacemissionstudio.yml", "The standard is written and checked "
     "automatically where a tool can; rules C-4 and C-5 have not been re-checked on the existing code, and "
     "no product quality requirements (SRS) exist to check it against.", "Review in H06; SRS (Phase 4).",
     "S", "no", "R10,R14,H06"),
    ("Q-ST-80C", "6.3.4.3a", "P", "compliance/docs/coding_standard.md section 3; SPAP.md 5.8 (refers to SDP 5.3, 5.4)", "Tools identified; drafted by the supplier; reviews waived (D-08).", "-", "S", "no", "R14"),
    ("Q-ST-80C", "6.3.4.4a", "H", "compliance/docs/coding_standard.md", "The coding standard has not been reviewed with the customer.",
     "Customer review of the coding standard (H09).", "S", "no", "H09"),
    ("Q-ST-80C", "6.3.4.5a", "C", "compliance/docs/coding_standard.md rule C-1: no low-level language is used (Python only; C/C++ only "
     "inside reused Basilisk)", "-", "-", "S", "no", "R10"),
    ("Q-ST-80C", "6.3.4.6a", "C", "compliance/docs/coding_standard.md: measurements and criteria (C-7 complexity <= 15, C-8 zero ruff "
     "findings, C-10 coverage >= 90 %) and tools (section 3); compliance/tools/metrics.py", "-", "-", "S",
     "no", "R10,R11"),
    ("Q-ST-80C", "6.3.4.6b", "C", ".github/workflows/spacemissionstudio.yml evaluates the code (ruff, tests, coverage, metrics) on every push "
     "and pull request touching the tool", "-", "-", "S", "no", "R10"),
    ("Q-ST-80C", "6.3.4.7a", "P", "compliance/docs/SPAMR.md section 6 (code analysis: lint, complexity, coverage)", "Synthesis in the audit's PA report; corrective actions recorded in the commits.", "-", "S", "no", "R14"),
    ("Q-ST-80C", "6.3.4.8a", "C", "git; compliance/docs/coding_standard.md rule C-15 (branch work, CI green before merge); .github/workflows/spacemissionstudio.yml", "-", "-",
     "S", "no", "R10"),
    ("Q-ST-80C", "6.3.5.*", "P", "tests/ (1403 functions)", "Testing exists; not planned, not traced, no "
     "coverage, no reports.", "R11, R12, SVS/SVR.", "M", "no", "R11,R12,R14"),
    ("Q-ST-80C", "6.3.5.20a", "NA", "-", "Flight software on flight equipment.", "-", "S", "no", ""),
    ("Q-ST-80C", "6.3.6*", "P", "packaging/", "Delivery exists; no release documentation or integrity "
     "checks.", "SRelD; checksums (R15).", "S", "no", "R14,R15"),
    ("Q-ST-80C", "6.3.7*", _H, "-", "No acceptance.", "User acceptance testing.", "S", "no", "H01"),
    ("Q-ST-80C", "6.3.8*", "P", "USER_MANUAL.md", "Operations support informal.", "SUM; operation support "
     "(H05).", "S", "no", "H05"),
    ("Q-ST-80C", "6.3.9*", _H, "git; HISTORY.md", "No maintenance process.", "SMP; H05.", "S", "no", "H05,R14"),
    ("Q-ST-80C", "7.1.*", "P", "R11 (Phase 2): quantitative code criteria in compliance/docs/coding_standard.md (C-7, C-10); "
     "compliance/tools/metrics.py in .github/workflows/spacemissionstudio.yml", "Metrics are collected; product quality requirements derived "
     "from system level and a metrication programme in a SPAP do not exist.", "Quality requirements in the "
     "SRS, metrication in the SPAP (Phase 4).", "M", "no", "R11,R14"),
    ("Q-ST-80C", "7.1.1a", "H", "-", "Quality requirements derive from system-level requirements the customer "
     "has not stated.", "Customer states system-level quality requirements (H03).", "S", "no", "H03"),
    ("Q-ST-80C", "7.1.5a", "P", "R11 (Phase 2): compliance/metrics.md: size (SLOC), complexity (ruff C901), "
     "test coverage, number of failed tests; fault density by a corrective-commit proxy", "Fault density and "
     "failure intensity need problem reports from verification and use, which do not exist (H05).",
     "Problem reporting (H05) feeds metrics.py.", "S", "no", "R11,H05"),
    ("Q-ST-80C", "7.1.6a", "P", "compliance/docs/SPAMR.md section 7", "Metrics reported in the audit's PA report; further reports on request (decision 8).", "-", "S", "no", "R14"),
    ("Q-ST-80C", "7.1.7*", "C", "R13 (Phase 3): accuracy estimated and verified against independent references "
     "(compliance/phase3_log.md; tests/validation): orbit propagation vs GMAT R2026a (two-body 4 mm/day, 20x20 "
     "0.12 m/day, Sun+Moon 9 mm and SRP 1.1 m in 7 days at GEO, NRLMSISE-00 drag 2.4 %), time scales vs GMAT and "
     "SOFA, Earth frame vs IERS 20 C04 (0.43 m), passes vs GMAT (0.08 s), OEM exchange (8 mm); two accuracy defects "
     "found and corrected (F-01, F-07)", "-", "-", "M", "no", "R13"),
    ("Q-ST-80C", "7.2.*", "P", "compliance/docs/SRS.md, SDD.md, SUITP.md, SVS.md, SVR.md", "Documented; drafted by the supplier; reviews waived (D-08). no requirements baseline (D-11).", "-", "M", "no", "R14,D-11"),
    ("Q-ST-80C", "7.2.1.3a", "C", "compliance/docs/SRS.md section 6 (verification method for every requirement)", "-", "-", "S", "no", "R14"),
    ("Q-ST-80C", "7.3.*", "NA", "-", "The tool is not developed as software intended for reuse.", "-", "S", "no",
     ""),
    ("Q-ST-80C", "7.4.*", "NA", "-", "No standard ground hardware or services for an operational system.", "-",
     "S", "no", ""),
    ("Q-ST-80C", "7.5.*", "NA", "-", "No programmable devices.", "-", "S", "no", ""),
    ("Q-ST-80C", "B.*", "P", "compliance/docs/SPAP.md (outline)", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("Q-ST-80C", "B.2.1<1>*", "C", "compliance/docs/SPAP.md (outline) section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("Q-ST-80C", "B.2.1<2>*", "C", "compliance/docs/SPAP.md (outline) section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("Q-ST-80C", "B.2.1<3>*", "C", "compliance/docs/SPAP.md (outline) section 3 (terms)", "-", "-", "S", "no", "R14"),
    ("Q-ST-80C", "C.*", "P", "compliance/docs/SPAMR.md", "Draft per the DRD: every DRD section present and not empty (compliance/tools/check_drds.py); not reviewed (H01); sections that depend on people state the gap and name the human action.", "Review and approve at the reviews of H01; close the human actions named in the document.", "M", "no", "R14,H01"),
    ("Q-ST-80C", "C.2.1<1>*", "C", "compliance/docs/SPAMR.md section 1 (introduction)", "-", "-", "S", "no", "R14"),
    ("Q-ST-80C", "C.2.1<2>*", "C", "compliance/docs/SPAMR.md section 2 (applicable and reference documents)", "-", "-", "S", "no", "R14"),
    ("Q-ST-80C", "C.2.1<3>*", "C", "compliance/docs/SPAMR.md section 3 (terms)", "-", "-", "S", "no", "R14"),
]
