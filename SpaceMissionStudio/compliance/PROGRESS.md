# Compliance work -- progress

Branch: `compliance/ecss-ccsds-audit`, created from
`claude/awesome-knuth-2vlhqu` at a3e6b8a89.

## Configuration under audit

| Item | Value |
|---|---|
| SpaceMissionStudio | `SpaceMissionStudio/` in this repository, at the branch point above |
| Basilisk in this repository (`docs/source/bskVersion.txt`) | 2.13.0b0, last `src/` commit c1bf0d7d6 (2026-10-02) |
| Basilisk the tests ran against | `bsk` 2.12.0 (a separate installed build, not built from this repository's `src/`) |

The two Basilisk versions differ. Which one the tool is qualified with
is a configuration-management decision (Phase 1 records it as a gap).
Basilisk is not modified by this work.

## Baseline test run (before any change)

Command: `pytest tests/ -q -n 3` (Basilisk 2.12.0, offscreen Qt), on the
branch point.

Result: **2055 passed, 11 skipped, 0 failed** (245 s, 3 workers). Every later phase re-runs this and reports differences.

## Phases

| Phase | Status |
|---|---|
| 0 Requirements extraction and tailoring | done; **criticality category C approved by the user (2026-10-08)**; OCM confirmed out of scope |
| 1 Audit and gap analysis | done: `gap_analysis.md`, `compliance_matrix.csv` (2084 rows); plan and D1-D8 **approved by the user (2026-10-08)** |
| 2 Implementation | done: R01-R12 (`phase2_log.md`); deviations D-01 to D-07 (`deviations.md`) |
| 3 Verification and validation | done: V-01, V-02 and V-04 to V-08 within tolerance (no case V-03 was defined) (`phase3_log.md`, `tests/validation/`); findings F-01 to F-08, two Basilisk accuracy defects corrected in the tool (F-01, F-07) |
| 4 Documentation | done: R14 (16 documents to their DRDs in `docs/`, checked by `tools/check_drds.py`; generated parts kept current by CI), R15 (`docs/security_analysis.md`; script-block consent, safe conditions, checksums, security lint); `human_actions.md` (H01-H13); `summary_report.md`. Not written: SSS/IRD (H03), SRevP and SCMP (DRDs not supplied, H12). |

## Decisions recorded

1. 2026-10-08, user: criticality category **C** approved.
2. 2026-10-08, user: the CCSDS OCM is **out of scope** (OPM, OMM, OEM only).
3. ECSS-Q-ST-30 / ECSS-Q-ST-40 not supplied: the classification is the
   user's decision, recorded above, not justified against them here.
4. 2026-10-08, user: Phase 1 remediation plan (R01-R15) approved and the
   recommendations for D1-D8 accepted (`gap_analysis.md` section 8):
   D1 AD10/MSFC only, deviation D-01; D2 WMM2025, deviation D-04; D3
   deviations D-02, D-03, D-05, D-06 accepted; D4 GM per IERS TN36 if the
   values can be sourced, else deviation D-07; D5 qualify Basilisk 2.12.0,
   pinned and checked at start-up; D6 CCSDS KVN first, XML when schemas are
   available; D7 REF_FRAME EME2000 for Earth-centred data, SPICE J2000
   equivalence documented in the CSD; D8 security assurance level low.
5. 2026-10-08, user: after the audit, and a review and update of the whole
   tool, the UX/UI guidelines (`UX_UI_Guidelines_for_SpaceMissionStudio.md`,
   2026-10-08) are applied. Not part of this audit.
6. 2026-10-08, user: Earth GM stays 398600.436 km^3/s^2 (Basilisk's) under
   deviation D-07 (Phase 3 finding F-02); templates 04, 05, 07, 08 and 21
   keep their gravity degree (the 4.2.1b Explain-tab note stays).
7. 2026-10-08, user: reviews (H01) are waived, deviation D-08; the
   reviewer is to be decided later; no review data packages for now.
8. 2026-10-08, user (H02): the SPA manager and security manager roles are
   left open; the software security management plan is waived (D-10);
   training records and process assessment are waived (D-09); PA reports
   only on request.
9. 2026-10-08, user (H03): no customer baseline (SSS, IRD), deviation
   D-11; a default CCSDS file naming and exchange method is defined in the
   ICD, to be agreed with each exchange partner.
10. 2026-10-08, user (H04): category C signed off; the supplier drafts the
    dependability and safety analysis for approval
    (`docs/dependability_safety_analysis.md`). Category C is critical
    software (Q-ST-80C 3.2.8), so 6.2.3 applies to the whole tool.
11. 2026-10-08, user (H05): problem reports and nonconformances as GitHub
    issues with labels (not created until the user agrees); formal change
    board, risk process and operation support waived (D-12); the release
    of this candidate is 2.1.0, tagged, not signed (D-13), when the user
    says release.
12. 2026-10-08, user (H06): the independent reviewer is to be named
    later; the supplier prepares a review guide
    (`reviews/code_review_guide.md`).
13. 2026-10-08, user (H07): Basilisk 2.12.0 accepted as-is for every
    function used, including those not externally validated; licences
    accepted as listed in the SRF (Basilisk's dependencies and Vizard not
    reviewed); export status left open.
14. 2026-10-08, user (H08): D-08 to D-13 signed; D-01 to D-07 stay
    unsigned; the user will supply IERS TN36 for D-07; the figures of D-02
    and D-03 are accepted as the supplier's estimates.
15. 2026-10-08, user (H09): statement coverage >= 90 % and decision
    (branch) coverage >= 80 %, both enforced in CI; MC/DC not required;
    complexity <= 15 for new code and the metric set of `metrics.py` kept.
16. 2026-10-08, user (H10): the user reports F-01 and F-07 to the Basilisk
    developers; a workaround is removed only in the requalification of a
    Basilisk release that fixes its defect, with V-04 showing the results
    stay within tolerance.
17. 2026-10-08, user (H11): no change to the tool. Checking before the
    change showed that S-06 was wrong: in live-stream mode Basilisk
    connects to Vizard (`zmq_connect`) and opens no listening port, and
    port 5570 is bound only in broadcast mode, which the tool does not
    use. S-06 is corrected; a change built for the earlier decision was
    discarded uncommitted.
18. 2026-10-08, user (H12): none of the missing documents (ECSS-M-ST-40C,
    ECSS-M-ST-10-01, ECSS-Q-ST-30/40, NOAA's WMM2025 report) will be
    supplied; the audit proceeds without them. IERS TN36 stays with H08
    (decision 14). No SRevP: covered by the review waiver D-08.
19. 2026-10-08, user (H13): the reference PC is the audit's cloud
    container; Windows and macOS are tested in CI. Results: SRS-P-09 and
    SRS-R-02 met (`performance.md`); 34 test failures on Windows and 10 on
    macOS (SRelD K-10), one a possible wrong altitude-trade result on
    Windows, which turned out to be finding F-09 (`review_log.md`). The
    one-day run's warning about NOAA's monthly F10.7 forecast is the
    designed order of the real data, not a defect. After the fixes
    (F-09 to F-12, test portability) the suite passes in CI on Linux,
    Windows and macOS: 2259 passed, 11 skipped, 0 failed each, commit
    `41b73b1c3`, run 37854361784. SRS-PO-01 is met by test (SVR 4.6);
    the Windows installer is still to be run by hand. The macOS plot-page
    load stall of CI run 27 did not recur after the results-widget tests
    began showing their widget (commit `6e9cbacd7`).

## Phase 1 test run

No code changed in Phase 1 (documents, CSVs and the `compliance/` build
scripts only). The suite was re-run on the Phase 1 commit; results are in
the table below.

| Run | Passed | Skipped | Failed |
|---|---|---|---|
| Baseline | 2055 | 11 | 0 |
| After Phase 1 | 2055 | 11 | 0 (no difference) |
| After Phase 2 (R01-R12) | 2188 | 11 | 0 (133 new tests; changed expectations listed in `phase2_log.md`) |
| After Phase 3 (R13) | 2209 | 11 | 0 (21 new tests; changed expectations listed in `phase3_log.md`) |
| After Phase 4 (R14, R15) | 2239 | 11 | 0 (30 new tests; changed expectations: the script-block tests pass consent, the condition hint text; listed in the R15 commit) |
| After H09 (decision 15) | 2243 | 11 | 0 (4 new tests of the branch coverage gate; no changed expectations) |
| After the K-10 fixes (F-09 to F-12) | 2256 | 11 | 0 (13 new tests; changed expectations: the wizard sizing and hint tests, three width limits in character widths, the kernel path tooltip; listed in the commits) |
| CI, Linux/Windows/macOS, `41b73b1c3` | 2259 | 11 | 0 (3 new tests in the K-10 follow-ups; no changed expectations) |
| After the 6.2.3.6a removals (F-13), Python 3.11 | 2259 | 11 | 0 (no difference: the removed code had no tests) |
| After F-13 and F-14, Python 3.12 with `sys.monitoring` coverage | 2261 | 11 | 0 (2 new tests, constant thrust; no changed expectations) |
| CI run 48, `5c2805085` (UX step 1, F-16, F-17) | 2286 | 11 | Linux and Windows 0; macOS 1: the F1 test, as Qt's HelpContents key is Ctrl+? there. F1 is now set on every platform (`3214f1855`) |
| After UX steps 2 and 3 and K-01, Python 3.11, `1d937c70b` | 2317 | 10 | 0 (new tests: the Data tab, the event model, the Events tab, the cursor on plots, dashboard and output, a real-run eclipse check; changed expectations: template 05's series count 40 -> 42 (eclipse series), template 21's claim figures (K-01). One skip fewer: the Kernel Status tests went with that tab, and one of them only ran without Basilisk) |
| After UX step 4 and Open in Vizard, Python 3.11 | 2338 | 10 | 0 (21 new tests: Vizard playback naming and launch, command palette, undo history, run comparison, input diff; no changed expectations) |

## Resuming

The standards' text is not in the repository. To resume, extract it again
(see `README.md`) and re-run `tools/extract_requirements.py`; the CSVs are
deterministic, so a diff shows any change.
