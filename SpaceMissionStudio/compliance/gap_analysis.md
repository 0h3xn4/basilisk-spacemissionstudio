# Phase 1 -- Audit and gap analysis

Status: **complete; awaiting approval of the remediation plan (section 9)
and the decisions in section 8.** No code has been changed in this phase.

Configuration audited: branch `compliance/ecss-ccsds-audit` at its branch
point (see `PROGRESS.md`), SpaceMissionStudio 2.0.0, running on Basilisk
2.12.0 (installed build). Criticality category C (user-approved). The per-
requirement record is `compliance_matrix.csv` (2084 rows); this document
summarises it and adds what a matrix cannot hold: the frame/time and
environment inventories, decisions and the plan.

## 1. Method

* Every requirement extracted in Phase 0 has a row in
  `compliance_matrix.csv`. Requirements the tailoring left out (category C
  "N", deleted, OCM) are "Not applicable" with the reason. Every other one
  is covered by an assessment rule in `audit/assessments_technical.py` or
  `audit/assessments_software.py`: an exact requirement ID or a clause
  prefix, the most specific winning. `tools/build_matrix.py` fails if any
  applicable requirement has no rule.
* Statuses: **Compliant** (evidence named), **Partially compliant**,
  **Non-compliant**, **Not applicable** (reason given), **Requires human or
  process action** (reviews, sign-offs, organisation, customer-side
  specifications: code cannot satisfy them).
* Evidence was taken from the code and from runs, not from memory. Facts
  about Basilisk were checked against the installed 2.12.0 build where it
  matters (e.g. solar flux measured: 1361.0 W/m^2 at 1 AU) and otherwise
  against this repository's 2.13.0b0 source, marked "src".
* Effort: S = under a day, M = 1-3 days, L = more, for the code or
  document work only (not reviews).

## 2. Summary

| Standard | Compliant | Partially | Non-compliant | Human/process | Not applicable | Rows |
|---|---|---|---|---|---|---|
| ECSS-E-ST-40C, body | 3 | 36 | 101 | 107 | 33 | 280 |
| ECSS-E-ST-40C, DRD contents | 0 | 37 | 466 | 0 | 0 | 503 |
| ECSS-Q-ST-80C, body | 0 | 95 | 67 | 101 | 33 | 296 |
| ECSS-Q-ST-80C, DRD contents | 0 | 0 | 38 | 13 | 0 | 51 |
| ECSS-E-ST-10-09C | 4 | 32 | 46 | 4 | 6 | 92 |
| ECSS-E-ST-10-04C | 6 | 6 | 18 | 0 | 122 | 152 |
| CCSDS 502.0-B-3 | 0 | 0 | 351 | 6 | 353 | 710 |

What this says:

* **The tool does not exchange orbit data in CCSDS form at all.** Every
  applicable CCSDS requirement is non-compliant because there is no ODM
  code (section 5).
* **Frames and time scales are handled correctly in most of the
  simulation, but not specified, labelled or documented**, and three
  places are wrong: TLE input, ground-station geodesy and Earth orientation
  (section 3).
* **Environment models are largely the ones ECSS-E-ST-10-04C names**
  (NRLMSISE-00, a GRACE gravity field, DE430, TSI 1361 W/m^2), with gaps
  in the geomagnetic field (WMM instead of IGRF), winds, tides and Earth
  orientation, and a **direct conflict between the standard's solar-
  activity rules and the ESA AD10 approach the tool now follows**
  (section 4).
* **ECSS-E-ST-40C and -Q-ST-80C are mostly unmet because their documents,
  plans and reviews do not exist.** The code itself is tested (1403 test
  functions) and change-tracked, but nothing is planned, specified, traced,
  measured or independently reviewed (section 6). 225 requirements need you
  or an organisation: reviews, sign-offs, roles.

## 3. ECSS-E-ST-10-09C -- frames and time scales

### 3.1 Inventory

Frames used anywhere in the tool, including inside Basilisk calls:

| Frame (tool notation) | Definition as implemented | Where | Finding |
|---|---|---|---|
| Inertial **N** (`r_BN_N`, `v_BN_N`) | SPICE `J2000` axes, origin at the central body (`spice_object.zeroBase = central body`) | engine/service.py, Basilisk spiceInterface | Correct; NAIF aligns its J2000 with the ICRF. Not labelled in outputs, epoch not stated (5.4.1h). CCSDS has no "J2000" REF_FRAME value: mapping is decision D7. |
| Planet-fixed **P** (`J20002Pfix`) | SPICE `IAU_<body>` from `pck00010` (IAU rotation model) | Basilisk gravBody `spicePlanetFrame="IAU_earth"` | For Earth this is not the IERS terrestrial frame: no IERS precession-nutation detail, no polar motion, no UT1-UTC. Used for spherical-harmonic gravity, NRLMSISE-00 latitude/longitude, WMM, ground stations (5.4.9f; ECSS-E-ST-10-04C 4.2.2b). |
| Body **B** (`sigma_BN` MRP) | Basilisk hub frame; facets, sensor and actuator axes given in B | engine/service.py, engine/fsw.py | Right-handed, orthonormal. Its relation to a mechanical frame is undefined (5.4.5a). |
| Guidance frames **R**, Hill **H** | Basilisk guidance (hillPoint, sunSafePoint, locationPointing, ...) | engine/fsw.py | Basilisk definitions, not specified in a CSD. |
| Topocentric (ground station) | Basilisk groundLocation from latitude/longitude/altitude | engine/service.py | **Defect: placed on a sphere of radius REQ_EARTH, not the WGS-84 ellipsoid** (src geodeticConversion LLA2PCPF with no polar radius). Up to ~21 km height and ~0.19 deg latitude error at mid-latitudes (5.4.6a). Fix tool-side: R05. |
| Orbital elements | osculating via `rv2elem` in N; mean via `clMeanOscMap` (first-order J2 short-period terms) | engine/service.py, engine/lifetime.py | Correct; theory undocumented (5.4.7). |
| **TEME** (TLE input) | SGP4 at the TLE epoch, TEME -> GCRF (Basilisk 2.12) | engine/service.py TLE branch -> Basilisk `tleHandling.satTle2elem` | **Defect: the state at the TLE epoch is used as the state at the scenario epoch** (no propagation between them, no epoch check), and the result is GCRF (ICRS frame bias applied, ~0.7 m) rather than the simulation's EME2000 (5.3.1b; CCSDS 4.2.4.9). Fix tool-side: R03. *Corrected in Phase 2: Phase 1 wrongly said that 2.12 used the mean elements as Keplerian elements without SGP4 or TEME rotation; re-reading the installed 2.12 `tleHandling.py` shows `_convertMean2osculating` runs SGP4 and `_teme2j2000` rotates the state.* |
| Lifetime Earth rotation | own GMST formula, UT1 = UTC | engine/lifetime.py `_gmst_rad` | A second, separate Earth-orientation model; consistent to ~0.1 deg with IAU_EARTH, adequate for orbit-averaged drag, but undocumented. |

Time scales:

| Scale | Used for | Conversion | Finding |
|---|---|---|---|
| UTC | scenario epoch (`epoch_utc`, ISO 8601; offsets converted to UTC); GUI "Epoch (UTC)" axis; space-weather day lookup | UTC -> ET by SPICE `str2et` with `naif0012` | The Epoch axis is UTC epoch + elapsed seconds, i.e. it ignores leap seconds inside a run and the TDB-UTC rate; no check that `naif0012` (last leap second 2017-01-01) covers the run. |
| TDB (SPICE ET) | ephemerides, planet orientation | SPICE | Not exposed or labelled. |
| Simulation time | Basilisk nanoseconds since the epoch | -- | Results are tagged in elapsed seconds without scale or epoch in the file (5.4.4a). |
| TAI, TT | only inside SPICE | -- | Not exposed; UTC/TAI/TT/TDB relationship nowhere documented (5.4.4b). |
| UT1 | lifetime GMST | UT1 = UTC assumed | |UUT1-UTC| < 0.9 s ignored; acceptable, undocumented. |

Leap seconds: `naif0012` (SPICE). Separately, Basilisk's `tleHandling` (src)
hard-codes `DELTA_AT = 37`. Nothing in the tool checks either against the run
dates.

### 3.2 Gaps

* No Coordinate Systems Document (Annex A DRD; 5.2.2a, A.2.1). Most of the
  46 non-compliant rows are documentation.
* No frame/time metadata on state vectors and series (5.4.1h, 5.4.2a,
  5.4.4a/b).
* The three defects above (TLE/TEME, spherical ground stations, IAU_EARTH
  Earth orientation).

## 4. ECSS-E-ST-10-04C -- environment

| Domain | ECSS-E-ST-10-04C Rev.1 | Tool (Basilisk 2.12) | Status |
|---|---|---|---|
| Earth gravity | global static GRACE/GOCE model on ICGEM, degree/order >= 70 (4.2.2a) | GGM03S (GRACE, ICGEM, degree 180), degree chosen by the user (templates: 10) | Partial |
| Truncation vs accuracy | consistent with accuracy needs and non-gravitational perturbations (4.2.1b) | left to the user, no guidance | Partial |
| Third bodies | DE-430 / LE-430 (4.2.2c) | de430.bsp | Compliant |
| Tides, Earth orientation | from IERS (4.2.2b) | none; IAU_EARTH | Non-compliant |
| Planetary masses | IERS 2010, TN36 (4.2.2d) | Basilisk astroConstants (e.g. MU_EARTH 398600.436 km^3/s^2), de-403-masses | Non-compliant (TN36 not supplied; values not checked) |
| Internal geomagnetic field | IGRF-12 with secular variation (5.2.1a, 5.2.1.1a) | WMM2025 (Basilisk magneticFieldWMM) | Non-compliant. IGRF-12 predicts only to 2020: decision D2 |
| External geomagnetic field | Alexeev 2001 or Tsyganenko 1996 (5.2.2a) | none (not in Basilisk) | Non-compliant, deviation D-05 |
| Solar irradiance | TSI 1361 W/m^2 (6.2.1a, Table 6-2) | 1361.0 W/m^2 in SRP, facet SRP, solar panels (measured on 2.12) | Compliant |
| Thermal sensor | TSI 1361, space sink 3 K (6.2.1a, c) | Basilisk sensorThermal: src S = 1366 W/m^2 (not settable in 2.12), sink 0 K, and a Stefan-Boltzmann constant of 5.76051e-8 (physical value 5.670374e-8, ~1.6% high) | Partial / non-compliant; the constant is a Basilisk defect to report upstream |
| Solar/geomagnetic indices | Table A-1 (cycle 23) for realistic future sequences (6.2.3c, 7.2.1.2d); Table 6-3 fixed values for long analyses and worst cases (6.2.2b, 7.2.1.2b/c); Table 6-4 ap storm profile (6.2.2c) | CelesTrak observations, then NASA MSFC's prediction at the 50th/95th percentile (ESA AD10 Sec. 5.9) | **Non-compliant by design: decision D1** |
| Neutral atmosphere | NRLMSISE-00 (7.2.1.1a) | NRLMSISE-00 (default); exponential optional, flagged as too thin | Compliant |
| Winds | HWM07 (7.2.2a) | zero wind, co-rotating atmosphere (Basilisk has no HWM) | Non-compliant, deviation D-02 |
| Plasma, radiation, debris, contamination | clauses 8-11 | not modelled | Not applicable |

The solar-activity conflict (D1) is the main issue: ECSS-E-ST-10-04C fixes
the inputs to standard reference tables, whereas the tool, on your
instruction, follows ESA AD10 (MSFC predictions, 95th percentile for
operations). Both are ESA guidance; a project has to choose, and the
choice must be recorded as a deviation from one of them.

## 5. CCSDS 502.0-B-3 -- orbit data messages

There is no OPM, OMM or OEM reader or writer, in KVN or XML (no ODM code
in the repository). The tool reads scenarios (JSON), TLEs and CelesTrak/
MSFC data, and writes CSV/JSON results.

What compliance needs, from the ICS requirements lists (Annex A):

| Message | Mandatory items | Conditional | Optional |
|---|---|---|---|
| OPM | 19 | 35 | 22 |
| OMM | 20 | 26 | 23 |
| OEM | 17 | 4 | 8 |

plus the KVN syntax rules (section 7), the XML instantiation (section 8),
units (7.7), and REF_FRAME / TIME_SYSTEM values (3.2.3.2-3.2.3.3: e.g.
EME2000, GCRF, ICRF, ITRF2000, TEME; UTC, TAI, TT, TDB). These rest on the
frame/time layer (R02, R04): an OEM cannot honestly state its REF_FRAME and
TIME_SYSTEM until the tool knows them. Covariance: the tool has no
covariance (no estimation), so it can write messages without covariance
and must read and preserve covariance from incoming files. XML validation
needs the NDM/XML schemas (SANA), which were not supplied (decision D6).
Six rows are agreements between exchange partners (file naming, exchange
method) and go into an ICD.

## 6. ECSS-E-ST-40C and ECSS-Q-ST-80C -- software engineering and PA

Evidence that exists:

* Version control (git), a detailed change log with rationale and
  verification notes (HISTORY.md), README.md and USER_MANUAL.md.
* 1403 pytest functions in 98 files, including integration tests against
  the real Basilisk and numerical checks recorded in HISTORY.md (e.g.
  lifetime against Basilisk decay runs to ~1-2%, the drag estimate 5% low
  against 5-year runs, budget formulas against hand calculations).
* A versioned scenario schema with migrations; installers; run provenance
  (tool and Basilisk versions, integrator, step) in every result.
* ruff lint passes (default rules, no configuration).

What does not:

* **No plans or specifications:** SDP, SPAP, SVerP, SValP, SUITP, SCMP,
  SMP, SRS, SDD, ICD, SVS, SVR, SRF, SRelD. The 503 + 51 DRD-content rows
  are non-compliant for that reason; Phase 4 drafts them.
* **No reviews** (SRR, PDR, CDR, QR, AR, TRR/TRB) and no independent
  review of the code. Every one of the 118 commits touching
  SpaceMissionStudio/ is authored by an AI assistant. A human code review
  is the first human action (H06).
* **No coverage measurement, metrics or written coding standard**, and the
  tool's tests are not run in CI: the repository's workflows build and
  test Basilisk only.
* **Basilisk reuse is not justified or controlled:** no Software Reuse
  File, and the version is not pinned. This repository's Basilisk source
  is 2.13.0b0, the tests ran on an installed 2.12.0 (decision D5).
* **Security:** the tool is offline by design at runtime and validates
  its scenario inputs, but there is no security analysis, and the security
  assurance level is not set (Q-ST-80C 6.2.9/6.2.10: "To be applied based
  on security assurance and sensitivity levels").

## 7. Basilisk-related limitations

Each is addressed in the tool's code or listed as a deviation; Basilisk is
not modified.

| # | Limitation | Affects | Handling |
|---|---|---|---|
| B1 | `tleHandling.satTle2elem` returns the SGP4 state at the TLE epoch (in GCRF), with no propagation to a given epoch (corrected in Phase 2, see section 3) | 10-09C 5.3.1b; CCSDS 4.2.4.9 | R03 (done): tool-side SGP4 to the scenario epoch, TEME of date -> EME2000 (`engine/tle.py`) |
| B2 | `groundLocation.specifyLocation` uses a spherical Earth; its horizon (elevation, access flag) is geocentric with either location call | 10-09C 5.4.6a | R05 (done): tool computes the WGS-84 position, calls `specifyLocationPCPF`, records geodetic elevation/azimuth; the access flag keeps the geocentric horizon (<= 0.19 deg) |
| B3 | Default Earth frame `IAU_earth` (pck00010), no EOP | 10-09C 5.4.9f; 10-04C 4.2.1c, 4.2.2b | R04: IERS-based high-precision Earth PCK through Basilisk's public `spicePlanetFrame` |
| B4 | No tide model | 10-04C 4.2.2b | D-03 |
| B5 | No IGRF; WMM only | 10-04C 5.2.1a | D2 / R08 |
| B6 | No external magnetic field model | 10-04C 5.2.2a | D-05 |
| B7 | Zero-wind model only (no HWM) | 10-04C 7.2.2a | D-02 |
| B8 | sensorThermal: solar constant 1366 (src), 0 K sink, Stefan-Boltzmann 5.76051e-8 | 10-04C 6.2.1a/c | R06 (measure on 2.12, set where exposed) / D-06; report upstream |
| B9 | GM values from astroConstants / DE-403, not IERS 2010 | 10-04C 4.2.2d | R06 (set `mu`) or D-07 |
| B10 | `nanoToSec()` loses precision past 2^53 ns (~104 days) | long runs | already handled: segmented runs (engine/long_run.py) |
| B11 | Repository Basilisk 2.13.0b0 vs installed 2.12.0 | Q-ST-80C 6.2.4, 6.2.7 | D5 / R01 |

## 8. Decisions needed from you

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Solar activity: ECSS-E-ST-10-04C reference tables vs ESA AD10 (MSFC) | (a) keep AD10 as the only source, deviation from 10-04C 6.2.2-6.2.3, 7.2.1.2b-d; (b) also offer an "ECSS-E-ST-10-04C reference" option: Table 6-3 low/moderate/high, Table 6-4 ap storm, Table A-1 cycle 23 | (a) as the default and documented deviation; (b) only if you accept the standard's reference values as "real data" (Table A-1 is observed cycle 23; Tables 6-3/6-4 are reference values, not observations) |
| D2 | Internal magnetic field | (a) deviation, keep WMM2025; (b) tool-side IGRF (current generation, still a deviation from "IGRF-12") | (a): IGRF-12 is obsolete for 2025+ epochs |
| D3 | Accept deviations D-02 winds, D-03 tides, D-05 external field, D-06 3 K sink | accept with justification / implement tool-side models (L each) | accept, justified (section 10) |
| D4 | Planetary GM values (4.2.2d) | supply IERS TN36 and set them, or deviation D-07 | supply TN36 if available |
| D5 | Basilisk version to qualify | 2.12.0 (installed, release, tested) / 2.13.0b0 (repository source, beta) | 2.12.0, pinned and checked at start-up |
| D6 | CCSDS XML | supply the NDM/XML schemas (SANA), or KVN first and XML later | KVN first; XML when the schemas are available |
| D7 | REF_FRAME for the tool's inertial frame | write EME2000, or GCRF/ICRF with a COMMENT stating SPICE J2000 | decide with your exchange partners; I would write EME2000 for Earth-centred data, the CCSDS default, and document the SPICE J2000 equivalence in the CSD |
| D8 | Security assurance level (Q-ST-80C 6.2.9/6.2.10) | none / low / ... | low: offline desktop tool, no sensitive data handled |

## 9. Prioritised remediation plan

Order by risk to results first, then foundations, then interfaces, then
quality infrastructure, then documents. Each item lists the requirement IDs
it addresses (from `compliance_matrix.csv`, column `remediation`).

| Prio | Item | What | Addresses (examples) | Effort | Near Basilisk |
|---|---|---|---|---|---|
| 1 | **R05** | WGS-84 geodetic ground stations | 10-09C 5.4.6a | S | public API (`specifyLocationPCPF`) |
| 1 | **R03** | Correct TLE import: SGP4 to the scenario epoch, TEME -> inertial, epoch check | 10-09C 5.3.1b/c; CCSDS 4.2.4.9 | M | replaces a Basilisk utility call |
| 1 | **R01** | Pin and check the Basilisk version; record it in provenance and the SRF | Q-ST-80C 6.2.4, 6.2.7, 5.5 | S | dependency only |
| 1 | **R06** | Environment constants: thermal constants (measure/set), GM per TN36 (if D4), gravity degree guidance and warning | 10-04C 4.2.1b, 4.2.2a, 4.2.2d, 6.2.1a | S | configures Basilisk objects |
| 2 | **R02** | Frame and time-system layer: every state vector and series carries frame (name, origin, epoch) and time scale; UTC/TAI/TT/TDB conversions through SPICE; leap-second-kernel validity check; correct UTC epoch axis | 10-09C 5.4.1h, 5.4.2a, 5.4.3, 5.4.4a/b, 5.3.2 | M | wraps SPICE/Basilisk outputs |
| 2 | **R04** | IERS-based Earth orientation (high-precision Earth PCK, ITRF93) for the Earth-fixed frame, kept offline (fetched at install) | 10-09C 5.4.9f; 10-04C 4.2.1c, 4.2.2b | M | public `spicePlanetFrame`; kernel management |
| 3 | **R09** | CCSDS ODM: OPM, OMM, OEM in KVN (read, write, validate); XML after D6; ICS completed | CCSDS 3.x, 4.x, 5.x, 7.x, 8.x, ICS | L | none (uses R02/R04) |
| 4 | **R07** | Solar-activity option per D1 | 10-04C 6.2.2, 6.2.3, 7.2.1.2 | S-M | none |
| 4 | **R08** | Geomagnetic field per D2 | 10-04C 5.2.1 | M | none (tool-side) |
| 5 | **R10** | Written coding standard; configured ruff (+ type checking); CI workflow for the tool's tests | E-ST-40C 5.5.3.1, 5.8.3.5f; Q-ST-80C 6.3.4 | S | none |
| 5 | **R11** | Coverage (pytest-cov) and metrics (size, complexity, coverage, defects) collected in CI | E-ST-40C 5.8.3.5b-d; Q-ST-80C 6.2.5, 7.1 | S | none |
| 5 | **R12** | Requirement-tagged tests (pytest markers) and generated traceability | E-ST-40C 5.5.3.2, 5.6, 5.7.3.5 | M | none |
| 6 | **R13** | Phase 3 validation against independent references (SOFA/IERS frame and time values, CCSDS example messages, GMAT where available), with stated tolerances | 10-09C 5.4.4b; Q-ST-80C 7.1.7; E-ST-40C 5.6 | M-L | none |
| 7 | **R14** | Phase 4 documents to their DRDs: SRS, SDD, ICD, SVerP/SValP/SVS/SVR, SUITP, SUM, SRF (Basilisk), SRelD, SDP, SMP, SPAP outline, SCMP description, CSD | most DRD rows | L | SRF covers Basilisk |
| 7 | **R15** | Security analysis (offline design, file inputs, dependencies, release checksums) | E-ST-40C 5.11, 5.4.3.2b, 5.7.2; Q-ST-80C 6.2.9 | S | none |

Every implementation step re-runs the full test suite and reports any
difference from the baseline (2055 passed, 11 skipped). Commits reference
the requirement IDs they address.

## 10. Deviation candidates

| # | Requirement(s) | Deviation | Justification (draft) |
|---|---|---|---|
| D-01 | 10-04C 6.2.2a-d, 6.2.3c, 7.2.1.2b-d | Solar/geomagnetic activity from CelesTrak observations and NASA MSFC predictions (ESA AD10 Sec. 5.9) instead of Tables 6-3, 6-4, A-1 | Project guideline AD10 prescribes MSFC predictions at the 95th (operations) and 50th (end of life) percentile; this is mission-specific and newer than solar cycle 23 |
| D-02 | 10-04C 7.2.2a | Zero wind (co-rotating atmosphere) instead of HWM07 | Basilisk has no wind model; thermospheric winds change drag by a few percent, below the drag-coefficient uncertainty |
| D-03 | 10-04C 4.2.2b (tides) | No solid-Earth or ocean tides | Basilisk has none; tidal accelerations (~1e-7 m/s^2 in LEO) are far below drag/SRP for mission analysis |
| D-04 | 10-04C 5.2.1a, 5.2.1.1a | WMM2025 instead of IGRF-12 | IGRF-12 predicts only to 2020; WMM2025 is a current main-field model of comparable fidelity |
| D-05 | 10-04C 5.2.2a | No external field model | Internal field dominates in LEO for magnetometer and torque-rod analysis; not in Basilisk |
| D-06 | 10-04C 6.2.1a/c (thermal) | Basilisk sensorThermal constants (solar constant, 0 K sink) | Effect of a 3 K sink is negligible (~(3/T)^4); solar-constant difference 0.4% |
| D-07 | 10-04C 4.2.2d | Basilisk/DE-403 GM values | Only if D4 is "no"; relative differences ~1e-8 |
| D-08 | E-ST-40C/Q-ST-80C process items not executed | Any review or plan you decide not to run for a single-person ground tool | To be decided per item |

## 11. Human and organisational actions

| # | Action | Requirement groups |
|---|---|---|
| H01 | Reviews: SRR, SWRR/PDR, DDR/CDR, QR, AR (or a documented reduced set for category C), TRR/TRB | E-ST-40C 5.2.5, 5.3.3-5.3.5, 5.4.4, 5.5.2.10, 5.6.3.4, 5.6.4.4, 5.7.3 |
| H02 | PA organisation: roles (SPA manager, can be you), resources, training, audits, PA reporting | Q-ST-80C 5.1, 5.2.2-5.2.3, 5.7, Annex C |
| H03 | Customer-side specification: SSS, IRD, installation and acceptance requirements, data exchange agreements (ICD) | E-ST-40C 5.2, 5.7.3, 5.8.3.1; CCSDS 3.1.6-3.1.7 |
| H04 | Criticality classification sign-off and a software dependability/safety analysis | Q-ST-80C 5.4.4, 6.2.2, 6.2.3 |
| H05 | Problem reporting, nonconformance, change control, risk management, operation support | Q-ST-80C 5.2.4-5.2.6, 5.3; E-ST-40C 5.9, 5.10 |
| H06 | Independent human review of the AI-written code (at least the budget, lifetime, frame/time and environment code) | Q-ST-80C 6.2.6; E-ST-40C 5.8.3.5a |
| H07 | Reused/procured components: list, licences, export status, acceptance (Basilisk, PySide6, numpy, sgp4, pyerfa (added by R03), ...) | Q-ST-80C 5.4, 5.5; E-ST-40C 5.3.2.3 |

## 12. Next step

Approve (or change) the plan in section 9 and decide D1-D8. Phase 2 then
starts with the priority 1 items. Each change gets tests linked to the
requirement IDs it verifies.
