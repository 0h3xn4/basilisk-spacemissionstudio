# SpaceMissionStudio: Software Release Document (SRelD)

DRD: ECSS-E-ST-40C Annex G
Document: SMS-SRelD, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft for a release candidate.
- This branch has not been released. Its version string is still 2.0.0,
  although it contains about 150 commits made after the 2.0.0 release
  commit.
- The release will be **2.1.0** (decision 11): the version is set and the
  release tagged, without signing (D-13), when the user says release.

## 1 Introduction (G.2.1<1>)

This SRelD describes the release candidate built from branch
`compliance/ecss-ccsds-audit` of `0h3xn4/basilisk`: what it contains, what
changed since 2.0.0, what is known to be wrong, and how to use it.

## 2 Applicable and reference documents (G.2.1<2>)

| Ref. | Document |
|---|---|
| RD1 | `HISTORY.md`: the change log, with an entry per change |
| RD2 | SVR (`SVR.md`): the verification and validation results of this candidate |
| RD3 | SRF (`SRF.md`): the reused software baseline |
| RD4 | `compliance/deviations.md`, `compliance/human_actions.md` |
| RD5 | SUM (`SUM.md`) |

## 3 Terms, definitions and abbreviated terms (G.2.1<3>)

| Term | Meaning |
|---|---|
| SPR | Software problem report: here, a known open problem listed in 5.2 (no SPR system exists yet, H05) |
| SW&D | Software waiver and deviation: the deviations D-01 to D-07 |

## 4 Software release overview (G.2.1<4>)

| Item | Value |
|---|---|
| Configuration item | SpaceMissionStudio (`SpaceMissionStudio/` in the repository) |
| Baseline | The head commit of `compliance/ecss-ccsds-audit` at release. Previous release: 2.0.0, commit `56938840d`, 2026-10-01. |
| Reused software baseline | Basilisk 2.12.0 (PyPI), numpy, sgp4, pyerfa, PySide6, plotly (RD3) |
| Delivery | Python wheel and sdist (`packaging/build_wheel.sh`), Debian package (`packaging/build_deb.sh`), Windows installer (`packaging/windows/spacemissionstudio.iss`), each with SHA-256 checksums |
| Documentation | SUM and `USER_MANUAL.md`; the documents in `compliance/docs/` |
| Basilisk framework | Unchanged. Against `develop`, the branch changes only `SpaceMissionStudio/` and `.github/workflows/spacemissionstudio.yml` (`git diff --name-only origin/develop HEAD`). |

## 5 Status of the software configuration item

### 5.1 Evolution since previous version (G.2.1<5.1>)

The changes are in RD1 since "Version 2.0.0: renamed to
SpaceMissionStudio". In summary:

**Features:**
- template claims checked against real runs;
- every template flies a 100–500 kg spacecraft;
- next-pass prediction and propagate-until-pass;
- facet models;
- GEO station keeping;
- recording interval;
- runs longer than 100 days;
- end-of-life lifetime and deorbit;
- real space weather only, with the synthetic profile removed;
- NASA MSFC solar activity;
- ESA AD10-style budgets, launch-delay sweep and altitude trade.

**ECSS/CCSDS audit (R01 to R15):**
- the Basilisk version pin and check;
- the frame and time layer;
- TLE import with SGP4;
- IERS-based Earth orientation;
- WGS-84 ground stations;
- environment constants;
- CCSDS OPM, OMM and OEM;
- the coding standard, CI and metrics;
- validation against GMAT, IERS and SOFA;
- corrections of two Basilisk accuracy defects (F-01 gravity, F-07
  drag), which change every drag result;
- the documents of `compliance/docs/`;
- the security changes: script-block consent and safe conditions.

**Changes users notice:**
- Drag results (lifetimes, budgets) change after F-07.
- A scenario with script blocks now asks before running them.
- A condition using attribute access or a call is refused.
- Unknown scenario fields are refused, as before.

### 5.2 Known problems and limitations (G.2.1<5.2>)

**Known problems (no SPR system exists, so these stand in for SPRs):**

| # | Problem | Effect | Ref. |
|---|---|---|---|
| K-01 | The drag figures in the HISTORY entries for the 5-year run, the altitude trade and the budgets were measured before the F-07 correction | Those published numbers are out of date | HISTORY.md; to re-measure |
| K-02 | The drag case of V-04 has an unexplained 1.6 % decay difference from GMAT (within tolerance) | Drag results carry it | `phase3_log.md` |
| K-03 | The time argument is TDB, not TAI (F-05) | About 0.1 m/day in LEO | `phase3_log.md` |
| K-04 | The field's GM and radius are the body's, not the field file's (F-03) | Centimetres per day | `phase3_log.md` |
| K-05 | Vizard live streaming listens on all interfaces | Network exposure during a live run | security analysis S-06, H11 |
| K-06 | Not tested on Windows or macOS in this audit; the Windows installer was not run | Unknown | SValP 9 |
| K-07 | Run time and memory requirements (SRS-P-09, SRS-R-02) not measured | Unknown | SVR |
| K-08 | Tracebacks from `results_widget._poll_plot_png` ("'NoneType' object is not subscriptable") appear in the CI log of the GUI tests | Possibly a timer firing after its state was cleared; no test fails | CI run 3 log; to investigate |
| K-09 | 988 of 1488 unit and integration tests have no docstring | Weaker test documentation | `SUITP_test_cases.md` |

**Waivers and deviations:** D-01 to D-07 (RD4). None is signed yet (H08).

## 6 Operational aspects (G.2.1<6>)

- **Install Basilisk 2.12.0.** Other versions run, but with a warning:
  their results are not covered by the validation.
- **Install the IERS-based Earth orientation files** for any run with a
  gravity field:
  - start-up prompt, or
  - `spacemissionstudio earth-orientation --fetch`.

  Without them, the Earth frame costs about 160 m/day at degree 20.
- **Re-run drag-dependent studies made with earlier versions.** F-07
  changes drag.
- **Run script blocks only from scenarios you trust and have read**
  (SUM 9.9).
- **Exchanging OEMs with GMAT R2026a:** use
  `run --oem-interpolation lagrange`, and convert to version 1.0
  (F-08).

## 7 Future evolutions (G.2.1<7>)

Planned, in order:
1. The human actions of RD4: reviews, PA organisation, signatures.
2. A review and update of the whole tool: re-measure K-01, investigate
   K-08.
3. The UX/UI guidelines (`PROGRESS.md`, decision 5).

Dropping the two Basilisk workarounds also depends on Basilisk: they go
once a qualified Basilisk release fixes F-01 and F-07 (H10).
