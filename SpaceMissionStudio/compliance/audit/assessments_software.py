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
_REVIEW_FIX = "Hold the review (can be a documented self-review plus an independent reviewer); keep minutes."
_PLAN_FIX = "Draft the plan in Phase 4 (compliance/docs/); user approves."
_NO_SDP = "No software development plan; life cycle and standards are implicit."

SOFTWARE_RULES = [
    # ======================= ECSS-E-ST-40C Rev.1 =================================
    # 5.2 software related system requirements: customer side
    ("E-ST-40C", "5.2.*", _H, "-", "Customer-side system requirements (SSS/IRD) do not exist; the user, as "
     "customer, has not specified them.", "Customer writes the SSS/IRD; a draft can be derived from the SRS "
     "(Phase 4).", "M", "no", "H03,R14"),
    ("E-ST-40C", "5.2.2.4a", "NA", "-", "No hardware/software co-engineering: the tool runs on COTS desktops.",
     "-", "S", "no", ""),
    ("E-ST-40C", "5.2.4.4*", "NA", "-", "No system database.", "-", "S", "no", ""),
    ("E-ST-40C", "5.2.4.6a", "NA", "-", "No on-board control procedures.", "-", "S", "no", ""),
    ("E-ST-40C", "5.2.5a", _H, "-", "No SRR held.", _REVIEW_FIX, "S", "no", "H01"),
    # 5.3 management
    ("E-ST-40C", "5.3.2.1*", "N", "HISTORY.md (de-facto change history)", _NO_SDP, _PLAN_FIX, "M", "no", "R14"),
    ("E-ST-40C", "5.3.2.2a", "N", "-", _NO_SDP, _PLAN_FIX, "S", "no", "R14"),
    ("E-ST-40C", "5.3.2.3a", "N", "-", "No procurement process documented (Basilisk and other dependencies are "
     "reused open-source software).", "Describe reuse/procurement of OSS in the SDP and SRF.", "S",
     "yes (Basilisk reuse)", "R14,H07"),
    ("E-ST-40C", "5.3.2.4*", "NA", "-", "No automatic code generation from models.", "-", "S", "no", ""),
    ("E-ST-40C", "5.3.2.5a", "P", "git branches/commits; HISTORY.md", "Baselines are git commits but no "
     "configuration management process or release tags are defined for the tool.",
     "SCMP description (Phase 4) and tagged releases.", "S", "no", "R01,R14"),
    ("E-ST-40C", "5.3.3*", _H, "-", "No joint or technical reviews held.", _REVIEW_FIX, "M", "no", "H01"),
    ("E-ST-40C", "5.3.4*", _H, "-", "No project reviews (SRR, PDR, CDR, QR, AR) held.", _REVIEW_FIX, "M", "no",
     "H01"),
    ("E-ST-40C", "5.3.5*", _H, "-", "No TRR/TRB/DRB/SVSR held.", _REVIEW_FIX, "S", "no", "H01"),
    ("E-ST-40C", "5.3.6.1*", "NA", "-", "Flight-software review phasing; the tool is ground software.", "-", "S",
     "no", ""),
    ("E-ST-40C", "5.3.6.2a", "N", "-", "The ground-software life cycle has not been chosen and documented.",
     _PLAN_FIX, "S", "no", "R14"),
    ("E-ST-40C", "5.3.7.1a", "P", "schema/scenario.py (versioned JSON scenario schema with migrations); "
     "engine/results.py (CSV/JSON outputs)", "Interfaces exist and are versioned, but no interface "
     "management procedure or ICD.", "ICD (Phase 4) incl. scenario, results and CCSDS interfaces.", "M", "no",
     "R14"),
    ("E-ST-40C", "5.3.8*", "P", "HISTORY.md: measured run time and memory (e.g. 5-year run 50 min, 450 MB)",
     "Measured, but no budget targets or margin philosophy.", "Define CPU/memory budgets for reference runs "
     "in the SRS; measure them in the SVR.", "S", "no", "R14"),
    ("E-ST-40C", "5.3.9*", "P", "compliance/ (this audit: requirements, compliance matrix)",
     "Compliance matrix in progress (Phase 1).", "Complete it through Phase 4.", "S", "no", ""),
    # 5.4 requirements and architecture
    ("E-ST-40C", "5.4.2.1a", "N", "Requirements implicit in HISTORY.md, docstrings and tests",
     "No software requirements specification (SRS).", "SRS (Phase 4) with uniquely identified requirements.",
     "L", "no", "R14"),
    ("E-ST-40C", "5.4.2.2a", "NA", "-", "In-flight modification: flight software only.", "-", "S", "no", ""),
    ("E-ST-40C", "5.4.2.4a", _H, "-", "No SWRR.", _REVIEW_FIX, "S", "no", "H01"),
    ("E-ST-40C", "5.4.3.*", "P", "README.md (architecture overview: schema / engine / gui / cli layers); "
     "module docstrings", "Architecture exists and is described informally; no SDD.", "SDD (Phase 4).", "M",
     "yes (Basilisk is the simulation core)", "R14"),
    ("E-ST-40C", "5.4.3.2b", "N", "-", "No residual vulnerability analysis.", "Security analysis (R15).", "S",
     "no", "R15"),
    ("E-ST-40C", "5.4.3.6a", "NA", "-", "The tool is not developed for reuse.", "-", "S", "no", ""),
    ("E-ST-40C", "5.4.3.6b", "NA", "-", "As 5.4.3.6a.", "-", "S", "no", ""),
    ("E-ST-40C", "5.4.3.6c", "C", "Mission data (scenarios JSON, space-weather data files) separate from code",
     "-", "-", "S", "no", ""),
    ("E-ST-40C", "5.4.3.7a", "N", "-", "The reuse of Basilisk (and other OSS) has not been analysed and "
     "documented.", "Software reuse file for Basilisk (Phase 4).", "M", "yes", "R14"),
    ("E-ST-40C", "5.4.3.8a", "N", "-", "No integration strategy documented.", "In the SUITP (Phase 4).", "S",
     "no", "R14"),
    ("E-ST-40C", "5.4.4a", _H, "-", "No PDR.", _REVIEW_FIX, "S", "no", "H01"),
    # 5.5 design and implementation
    ("E-ST-40C", "5.5.2.*", "P", "Module and class docstrings (engine/, gui/, schema/)",
     "Detailed design is documented inline only; no SDD.", "SDD detailed-design part (Phase 4).", "M", "no",
     "R14"),
    ("E-ST-40C", "5.5.2.5*", "N", "gui/*_widget.py QThread workers; engine/propellant_budget.py process pool",
     "Concurrency (Qt worker threads, a spawned process pool, Basilisk single-thread runs) is not documented "
     "or justified; no real-time constraints apply.", "Describe threads, processes and shared data in the SDD.",
     "S", "no", "R14"),
    ("E-ST-40C", "5.5.2.8a", "P", "USER_MANUAL.md", "A user manual exists but not in the SUM DRD structure.",
     "SUM per Annex H (Phase 4), reusing USER_MANUAL.md.", "M", "no", "R14"),
    ("E-ST-40C", "5.5.2.9a", "N", "-", "No unit/integration test plan.", "SUITP (Phase 4).", "M", "no", "R14"),
    ("E-ST-40C", "5.5.2.10a", _H, "-", "No DDR.", _REVIEW_FIX, "S", "no", "H01"),
    ("E-ST-40C", "5.5.3.1a", "P", "spacemissionstudio/ source; pyproject.toml build", "Code and build exist; "
     "no coding standard documented, no build procedure in a release document.", "Coding standard (R10), "
     "SRelD (Phase 4).", "S", "no", "R10,R14"),
    ("E-ST-40C", "5.5.3.2*", "P", "tests/ (1403 test functions, 98 files; Basilisk-backed tests marked "
     "requires_basilisk)", "Unit tests exist but are not traced to requirements, boundary-value coverage is not "
     "systematic, and unit test reports are not produced.", "Requirement-tagged tests (R12), coverage (R11), "
     "test reports.", "M", "no", "R11,R12"),
    ("E-ST-40C", "5.5.4.*", "P", "tests/ integration tests against Basilisk 2.12 (test_service_*, "
     "test_template_claims.py)", "Integration testing happens but is not planned or reported.",
     "SUITP integration part; reports.", "S", "no", "R12,R14"),
    # 5.6 validation
    ("E-ST-40C", "5.6.2.1*", "N", "HISTORY.md validation notes (e.g. lifetime vs Basilisk decay +/-1%, drag "
     "estimate -5% vs 5-year runs)", "Validation is done case by case but no validation process/plan exists.",
     "SValP (Phase 4), Phase 3 validation campaign.", "M", "no", "R13,R14"),
    ("E-ST-40C", "5.6.3.*", "N", "-", "No validation specification/report against the technical specification.",
     "SVS/SVR (Phase 3-4).", "M", "no", "R13,R14"),
    ("E-ST-40C", "5.6.3.4a", _H, "-", "No CDR.", _REVIEW_FIX, "S", "no", "H01"),
    ("E-ST-40C", "5.6.4.*", "N", "-", "No validation against the requirements baseline.", "SVS/SVR (Phase 3-4).",
     "M", "no", "R13,R14"),
    ("E-ST-40C", "5.6.4.4a", _H, "-", "No QR.", _REVIEW_FIX, "S", "no", "H01"),
    ("E-ST-40C", "5.6.5a", "N", "-", "No validation control information.", "Validation status in the SVR.", "S",
     "no", "R14"),
    # 5.7 delivery and acceptance
    ("E-ST-40C", "5.7.2.1a", "P", "packaging/ (.deb, Windows installer, wheel scripts)", "Deliverable packaging "
     "exists; no release document.", "SRelD (Phase 4).", "S", "no", "R14"),
    ("E-ST-40C", "5.7.2.1b", "P", "packaging/; offline-by-design runtime (README)", "No signed/checksummed "
     "releases.", "Publish checksums with releases (R15).", "S", "no", "R15"),
    ("E-ST-40C", "5.7.2.2a", "NA", "-", "No training specified in a business agreement.", "-", "S", "no", ""),
    ("E-ST-40C", "5.7.2.3*", "P", "packaging/README.md, install.sh/install.ps1", "Installation procedures exist; "
     "security of installation not assessed.", "R15; installation section of the SUM.", "S", "no", "R15"),
    ("E-ST-40C", "5.7.2.4*", "P", "packaging/ (kernel pre-fetch at install)", "No installation report.",
     "Installation report template (Phase 4).", "S", "no", "R14"),
    ("E-ST-40C", "5.7.3.*", _H, "-", "No acceptance test plan, testing or AR.", "User defines and runs "
     "acceptance tests (a draft can be derived from the SVS).", "M", "no", "H01,H03"),
    # 5.8 verification
    ("E-ST-40C", "5.8.2.1*", "N", "-", "No verification process/plan.", "SVerP (Phase 4).", "M", "no", "R14"),
    ("E-ST-40C", "5.8.3.1a", _H, "-", "The customer has not verified a requirements baseline (none exists).",
     "After the SRS: customer verification.", "S", "no", "H03"),
    ("E-ST-40C", "5.8.3.*", "N", "-", "No verification of TS/architecture/design/documentation recorded.",
     "SVR (Phase 3-4).", "M", "no", "R14"),
    ("E-ST-40C", "5.8.3.5a", "P", "ruff static checks (no config); tests", "Code verified by tests and lint "
     "only; no recorded code verification against the design.", "Code verification in the SVR.", "M", "no",
     "R10,R14"),
    ("E-ST-40C", "5.8.3.5b", "N", "-", "Code coverage not measured (no coverage tool installed).",
     "pytest-cov in CI; report statement/branch coverage against the category C target of Table R-1's note.",
     "S", "no", "R11"),
    ("E-ST-40C", "5.8.3.5c", "N", "-", "Coverage not measured.", "R11.", "S", "no", "R11"),
    ("E-ST-40C", "5.8.3.5d", "N", "-", "Coverage not measured.", "R11.", "S", "no", "R11"),
    ("E-ST-40C", "5.8.3.5e", "NA", "-", "Python source is executed directly; no object code.", "-", "S", "no", ""),
    ("E-ST-40C", "5.8.3.5f", "P", "ruff (pyflakes-level checks)", "Static analysis exists but is minimal and "
     "unconfigured.", "R10: configured static analysis (ruff rule set, type checking).", "S", "no", "R10"),
    ("E-ST-40C", "5.8.3.11*", "NA", "-", "Schedulability: no real-time software.", "-", "S", "no", ""),
    ("E-ST-40C", "5.8.3.12*", "N", "-", "Technical budgets (CPU/memory) not estimated or tracked.", "As 5.3.8.",
     "S", "no", "R14"),
    # 5.9 operation, 5.10 maintenance, 5.11 security
    ("E-ST-40C", "5.9.*", _H, "USER_MANUAL.md", "No software operation support entity or procedures; the user "
     "operates the tool.", "User defines operation support (who answers, how problems are logged).", "S",
     "no", "H05"),
    ("E-ST-40C", "5.10.*", _H, "git history; HISTORY.md", "No maintenance plan or problem/modification "
     "procedures.", "SMP (Phase 4) and a problem-report procedure (e.g. GitHub issues).", "M", "no",
     "H05,R14"),
    ("E-ST-40C", "5.11.*", "N", "README.md: offline at runtime; schema validation of inputs",
     "No security analysis or security requirements.", "R15: security analysis (offline design, file inputs, "
     "dependencies).", "M", "no", "R15"),
    # Annexes: DRDs
    ("E-ST-40C", "B.*", "N", "-", "No SSS (customer document).", "Customer SSS; draft from the SRS.", "M", "no",
     "H03,R14"),
    ("E-ST-40C", "C.*", "N", "-", "No IRD.", "Customer IRD; draft from the ICD.", "S", "no", "H03,R14"),
    ("E-ST-40C", "D.*", "N", "-", "No SRS.", "SRS (Phase 4).", "L", "no", "R14"),
    ("E-ST-40C", "E.*", "N", "-", "No ICD.", "ICD (Phase 4).", "M", "no", "R14"),
    ("E-ST-40C", "F.*", "N", "-", "No SDD.", "SDD (Phase 4).", "M", "no", "R14"),
    ("E-ST-40C", "G.*", "P", "HISTORY.md (change history)", "No SRelD.", "SRelD (Phase 4).", "S", "no", "R14"),
    ("E-ST-40C", "H.*", "P", "USER_MANUAL.md", "Not in the SUM DRD structure.", "SUM (Phase 4).", "M", "no",
     "R14"),
    ("E-ST-40C", "I.*", "N", "-", "No SVerP.", "SVerP (Phase 4).", "M", "no", "R14"),
    ("E-ST-40C", "J.*", "N", "-", "No SValP.", "SValP (Phase 4).", "M", "no", "R14"),
    ("E-ST-40C", "K.*", "N", "-", "No SUITP.", "SUITP (Phase 4).", "M", "no", "R14"),
    ("E-ST-40C", "L.*", "N", "-", "No SVS.", "SVS (Phase 3-4).", "M", "no", "R14"),
    ("E-ST-40C", "M.*", "N", "-", "No SVR.", "SVR (Phase 3-4).", "M", "no", "R14"),
    ("E-ST-40C", "N.*", "N", "-", "No SRF for Basilisk.", "SRF (Phase 4).", "M", "yes", "R14"),
    ("E-ST-40C", "O.*", "N", "-", "No SDP.", "SDP (Phase 4).", "M", "no", "R14"),
    ("E-ST-40C", "P.*", "N", "-", "No SRevP.", "SRevP (Phase 4).", "S", "no", "R14"),
    ("E-ST-40C", "T.*", "N", "-", "No SMP.", "SMP (Phase 4).", "M", "no", "R14"),
    ("E-ST-40C", "R.*", "C", "compliance/phase0_tailoring.md; requirements/ECSS-E-ST-40C.csv crit_C",
     "-", "-", "S", "no", ""),

    # ======================= ECSS-Q-ST-80C Rev.2 =================================
    ("Q-ST-80C", "5.1.*", _H, "-", "No PA organisation, responsibilities, resources, SPA manager or training "
     "defined (single-person project).", "User assigns roles (can be the same person for C, documented in "
     "the SPAP) and records training.", "S", "no", "H02"),
    ("Q-ST-80C", "5.2.1*", "N", "-", "No software product assurance plan.", "SPAP outline (Phase 4).", "M", "no",
     "R14,H02"),
    ("Q-ST-80C", "5.2.2*", _H, "-", "No PA reporting.", "Milestone reports per Annex C (SPAMR).", "S", "no",
     "H02"),
    ("Q-ST-80C", "5.2.3*", _H, "-", "No audits.", "User plans audits as needed (category C: Y).", "S", "no",
     "H02"),
    ("Q-ST-80C", "5.2.4*", _H, "-", "No alert process.", "Subscribe to Basilisk/dependency advisories; record.",
     "S", "no", "H05"),
    ("Q-ST-80C", "5.2.5*", _H, "git history (fixes described in commits/HISTORY.md)", "No problem-reporting "
     "procedure.", "Problem reports in an issue tracker with a defined workflow.", "S", "no", "H05"),
    ("Q-ST-80C", "5.2.6*", _H, "-", "No nonconformance process.", "Define in the SPAP.", "S", "no", "H05"),
    ("Q-ST-80C", "5.2.7*", "N", "-", "No quality requirements or quality model.", "Quality model and "
     "requirements in the SPAP/SRS.", "S", "no", "R14"),
    ("Q-ST-80C", "5.3.*", _H, "-", "No risk management or critical-item control.", "Risk register (SPAP).", "S",
     "no", "H05"),
    ("Q-ST-80C", "5.4.*", _H, "-", "Supplier selection/control not applicable as such (no subcontractor); "
     "reused OSS suppliers (Basilisk) not assessed.", "Record OSS dependencies and their status in the SRF.",
     "S", "yes", "H07"),
    ("Q-ST-80C", "5.4.4a", "P", "compliance/phase0_tailoring.md (category C, user-approved 2026-10-08)",
     "Category set by the user without the system-level analysis of ECSS-Q-ST-30/-40 (not supplied).",
     "User records the justification and signs off.", "S", "no", "H04"),
    ("Q-ST-80C", "5.5.*", _H, "pyproject.toml dependencies", "No procurement documents for the reused/"
     "procured components (Basilisk, PySide6, numpy, sgp4, ...).", "Component list with versions and "
     "licences in the SRF; user reviews.", "S", "yes", "H07,R01"),
    ("Q-ST-80C", "5.6.*", "P", "pyproject.toml (Python, pytest, pytest-qt); ruff", "Tools exist but are not "
     "selected/justified or documented.", "Tools and environment section in the SDP.", "S", "no", "R14"),
    ("Q-ST-80C", "5.7.*", _H, "-", "No process assessment/improvement.", "User decides (category C: Y).", "S",
     "no", "H02"),
    ("Q-ST-80C", "6.1.*", "N", "-", "No documented life cycle.", "SDP (Phase 4).", "S", "no", "R14"),
    ("Q-ST-80C", "6.2.1*", "N", "-", "Processes not documented.", "SDP/SPAP (Phase 4).", "M", "no", "R14"),
    ("Q-ST-80C", "6.2.2.1a", "P", "compliance/phase0_tailoring.md", "As 5.4.4a.", "As 5.4.4a.", "S", "no", "H04"),
    ("Q-ST-80C", "6.2.2.*", _H, "-", "No software dependability and safety analysis.", "User performs it "
     "(e.g. a light SFMEA on budget/lifetime outputs); draft template in Phase 4.", "M", "no", "H04"),
    ("Q-ST-80C", "6.2.3.*", _H, "-", "Critical software components not identified.", "Identify (e.g. budget, "
     "lifetime, frame/time layer) in the dependability analysis.", "S", "no", "H04"),
    ("Q-ST-80C", "6.2.4.*", "P", "git; version 2.0.0 (pyproject.toml); schema_version + migrations; "
     "R01 (Phase 2): spacemissionstudio/dependencies.py QUALIFIED_BASILISK_VERSION = 2.12.0, installers pin "
     "bsk[all]==2.12.0, start-up check (GUI status bar, CLI run), RunProvenance/provenance.json records "
     "Basilisk version and qualification, dependency versions, scenario SHA-256 and reference data files "
     "(tests/test_dependencies.py)", "No SCMP; no tagged releases of this tool.",
     "SCMP description (Phase 4); tag releases.", "S", "yes (Basilisk version control)", "R01,R14"),
    ("Q-ST-80C", "6.2.5*", "N", "-", "No process metrics.", "R11 (metrics collected in CI).", "S", "no", "R11"),
    ("Q-ST-80C", "6.2.6.*", "P", "tests/; ruff", "Verification by tests; no verification plan or reports, no "
     "human review record of AI-written code.", "SVerP/SVR; documented human code review.", "M", "no",
     "R14,H06"),
    ("Q-ST-80C", "6.2.7.*", "N", "R01: the reused Basilisk version is fixed (2.12.0), pinned and checked; "
     "runs record it.", "Reuse of Basilisk not justified or documented (no SRF, no qualification evidence).", "SRF (Phase 4); evidence: Basilisk's own test suite and the tool's "
     "integration tests.", "M", "yes", "R14,R01"),
    ("Q-ST-80C", "6.2.8.*", "NA", "-", "No automatic code generation from models. (AI-assisted coding is "
     "covered by review, H06.)", "-", "S", "no", "H06"),
    ("Q-ST-80C", "6.2.9.*", _H, "README.md (offline at runtime)", "Security assurance level not set "
     "(Table D-2: 'To be applied based on security assurance and sensitivity levels').",
     "User sets the security level; R15.", "S", "no", "R15"),
    ("Q-ST-80C", "6.2.10.*", _H, "-", "As 6.2.9.", "As 6.2.9.", "S", "no", "R15"),
    ("Q-ST-80C", "6.3.1*", _H, "-", "Customer-side system requirements process (see ECSS-E-ST-40C 5.2).",
     "As ECSS-E-ST-40C 5.2.", "S", "no", "H03"),
    ("Q-ST-80C", "6.3.2*", "N", "-", "No SRS.", "SRS (Phase 4).", "M", "no", "R14"),
    ("Q-ST-80C", "6.3.3*", "P", "README.md, docstrings", "No SDD.", "SDD (Phase 4).", "M", "no", "R14"),
    ("Q-ST-80C", "6.3.4*", "P", "AGENTS.md (repository rules: units on literals, Basilisk coding guidelines, "
     "PEP 8); ruff", "No coding standard written for this tool; static analysis unconfigured.",
     "R10: written coding standard + configured ruff + CI.", "S", "no", "R10"),
    ("Q-ST-80C", "6.3.5.*", "P", "tests/ (1403 functions)", "Testing exists; not planned, not traced, no "
     "coverage, no reports.", "R11, R12, SVS/SVR.", "M", "no", "R11,R12,R14"),
    ("Q-ST-80C", "6.3.5.20a", "NA", "-", "Flight software on flight equipment.", "-", "S", "no", ""),
    ("Q-ST-80C", "6.3.6*", "P", "packaging/", "Delivery exists; no release documentation or integrity "
     "checks.", "SRelD; checksums (R15).", "S", "no", "R14,R15"),
    ("Q-ST-80C", "6.3.7*", _H, "-", "No acceptance.", "User acceptance testing.", "S", "no", "H01"),
    ("Q-ST-80C", "6.3.8*", "P", "USER_MANUAL.md", "Operations support informal.", "SUM; operation support "
     "(H05).", "S", "no", "H05"),
    ("Q-ST-80C", "6.3.9*", _H, "git; HISTORY.md", "No maintenance process.", "SMP; H05.", "S", "no", "H05,R14"),
    ("Q-ST-80C", "7.1.*", "N", "-", "No product quality objectives or metrics.", "R11 (metrics), quality "
     "requirements in the SRS.", "M", "no", "R11"),
    ("Q-ST-80C", "7.1.7*", "P", "HISTORY.md accuracy checks (lifetime +/-1-2% vs Basilisk; drag estimate "
     "-5% vs 5-year runs; budget formulas vs hand calculations)", "Numerical accuracy checked case by case; "
     "no accuracy requirements or systematic verification.", "Accuracy requirements in the SRS; Phase 3 "
     "validation against independent references (R13).", "M", "no", "R13"),
    ("Q-ST-80C", "7.2.*", "N", "-", "Requirements, design and test documentation missing.", "Phase 4 documents.",
     "L", "no", "R14"),
    ("Q-ST-80C", "7.3.*", "NA", "-", "The tool is not developed as software intended for reuse.", "-", "S", "no",
     ""),
    ("Q-ST-80C", "7.4.*", "NA", "-", "No standard ground hardware or services for an operational system.", "-",
     "S", "no", ""),
    ("Q-ST-80C", "7.5.*", "NA", "-", "No programmable devices.", "-", "S", "no", ""),
    ("Q-ST-80C", "B.*", "N", "-", "No SPAP.", "SPAP outline (Phase 4).", "M", "no", "R14"),
    ("Q-ST-80C", "C.*", _H, "-", "No PA milestone reports.", "User produces SPAMR at milestones.", "S", "no",
     "H02"),
]
