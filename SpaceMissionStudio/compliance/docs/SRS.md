# SpaceMissionStudio – Software Requirements Specification (SRS)

DRD: ECSS-E-ST-40C Annex D
Document: SMS-SRS, issue 1 (draft), 2026-10-08. Remediation R14.

**Status: draft, written by the supplier, not reviewed.**
- No customer requirements baseline (SSS, IRD) exists for this tool, so
  this SRS is derived from the software as implemented (version 2.0.0 on
  branch `compliance/ecss-ccsds-audit`) and from the user's recorded
  decisions (`compliance/PROGRESS.md`).
- Whether it states what the customer needs is for the customer to decide:
  H03 (requirements baseline) and H01 (SRR/PDR reviews).

## 1 Introduction (D.2.1<1>)

This SRS states what SpaceMissionStudio, a desktop mission-analysis tool
built on the Basilisk astrodynamics framework, shall do.

It was prepared during the ECSS/CCSDS compliance audit because the tool had
no written requirements (`compliance/gap_analysis.md`, R14). It serves:

- as the technical specification against which the tool is verified and
  validated (SVS, SVR);
- as the starting point for the customer's review.

## 2 Applicable and reference documents (D.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | ECSS-E-ST-40C Rev.1, Software |
| AD2 | ECSS-Q-ST-80C Rev.2, Software product assurance |
| AD3 | ECSS-E-ST-10-09C, Reference coordinate systems |
| AD4 | ECSS-E-ST-10-04C, Space environment |
| AD5 | CCSDS 502.0-B-3, Orbit Data Messages |
| AD6 | ESA AD10, EOP-FM/2024-07-177 v3.0 (cited only by identifier) |
| RD1 | `compliance/phase0_tailoring.md`: criticality category C tailoring |
| RD2 | `compliance/deviations.md`: deviations D-01 to D-07 |
| RD3 | `compliance/docs/ICD.md`: interface control document |
| RD4 | `compliance/docs/SDD.md`: software design document |
| RD5 | `compliance/docs/CSD.md`: coordinate systems document |
| RD6 | `compliance/docs/coding_standard.md` |
| RD7 | `USER_MANUAL.md`, `README.md` |

## 3 Terms, definitions and abbreviated terms (D.2.1<3>)

| Term | Meaning |
|---|---|
| Scenario | The JSON file describing one simulation: epoch, spacecraft, gravity, ground stations, space weather, settings, mission sequence |
| Run | One execution of a scenario by the simulation service (Basilisk) |
| Series | A named time history in a run's results, with units and frame |
| EOP files | IERS-based NAIF Earth orientation PCKs (ITRF93) |
| ODM | CCSDS Orbit Data Message: OPM, OMM, OEM |
| MSFC | NASA Marshall solar-activity prediction |

Other terms are as in AD1–AD5 and the `USER_MANUAL.md` glossary.

## 4 Software overview

### 4.1 Function and purpose (D.2.1<4.1>)

SpaceMissionStudio lets a mission analyst set up and run spacecraft
mission simulations without writing code, and turn the results into
analysis products. The products are:

- orbits and attitude;
- ground-station access;
- power and thermal;
- delta-V and propellant budgets;
- orbital lifetime and disposal checks;
- Monte Carlo dispersions;
- CCSDS orbit data messages.

The physics is Basilisk's. The tool configures it, checks inputs, runs it,
post-processes it and presents the results. It is a ground tool for mission
analysis. It is not flight software and is not operational ground-segment
software.

### 4.2 Environmental considerations (D.2.1<4.2>)

- **Physical environment:** office desktop or laptop.
- **Hardware:** x86-64 PC with at least 8 GB RAM (16 GB for multi-year
  runs), and about 2 GB of disk for Basilisk and its data files.
- **Operating environment:**
  - Linux (Ubuntu 22.04/24.04 tested) or Windows 10/11;
  - Python >= 3.9 (3.11 tested);
  - Basilisk 2.12.0, pinned;
  - Qt (PySide6) for the GUI.
- **Network:** none is needed at run time. Downloads happen only on explicit
  user consent (SRS-S-01).

### 4.3 Relation to other systems (D.2.1<4.3>)

The tool is standalone. It is not a component of an integrated
hardware/software product. It uses or exchanges data with:

- **Basilisk 2.12.0:** reused, unmodified simulation framework (SRF).
- **Vizard:** optional 3-D viewer, separate process.
- **SPICE kernels:** DE430, NAIF leap seconds and PCKs.
- **IERS-based NAIF Earth orientation files.**
- **CelesTrak space weather and NASA MSFC prediction files.**
- **Other tools, through CCSDS OPM/OMM/OEM files** (e.g. GMAT) and CSV
  results.

Block diagram:

```
 user ──► GUI / CLI ──► schema (scenario JSON, validation)
                         │
                         ▼
                 engine (service, analyses) ──► Basilisk 2.12 (SPICE, gravity, drag, FSW, ...)
                         │                      ▲
                         │                      └─ data files: DE430, GGM03S, WMM2025, EOP, space weather
                         ▼
         results: CSV, provenance.json, CCSDS OEM/OPM, plots ──► Vizard (optional)
```

### 4.4 Constraints (D.2.1<4.4>)

1. **Basilisk is reused unmodified.** It is not edited, patched or
   monkey-patched (user constraint).
   - Its shortcomings are corrected outside it, where needed (R06, F-01,
     F-07).
   - Basilisk's own limits stay limits of the tool: no thermospheric wind,
     no tides, no IGRF, no Jacchia models (deviations D-02 to D-05), and
     single runs of at most 100 days (longer runs are segmented).
2. **Real data only:** no synthetic space weather (user rule).
3. **Offline by design:** no network access without consent.
4. **Criticality category C** (RD1).

## 5 Requirements

### 5.1 General (D.2.1<5.1>)

- **Identifiers:** each requirement has a unique identifier,
  `SRS-<group>-<nn>`.
- **Traceability:**
  - "Source" names the requirement it derives from: a clause of AD1–AD5, a
    deviation (RD2), or a user decision (UD-n = decision n in
    `compliance/PROGRESS.md`). "Tool" means the requirement states existing
    behaviour, not a higher-level requirement.
  - Section 6 gives the validation approach.
- **Priority:** every requirement is "essential" unless marked "(desirable)".

### 5.2 Functional requirements (D.2.1<5.2>)

Grouped by the logical model of section 8. The tool has no operational
states or modes beyond those in 5.5.

| ID | Requirement | Source |
|---|---|---|
| SRS-F-01 | Scenarios shall be stored as versioned JSON (`schema_version`). Older versions shall be migrated on load. Validation errors shall name the field at fault. | Tool |
| SRS-F-02 | Orbit initial conditions shall be accepted in three forms: classical elements (true or mean anomaly); Cartesian EME2000 state; TLE. A TLE shall be propagated by SGP4 to the scenario epoch and rotated TEME → EME2000 (IAU 1976/1980). The run shall warn when the TLE is more than 3 days from the epoch. | E-ST-10-09C 5.3.1b/c; CCSDS 4.2.4.9 |
| SRS-F-03 | Orbits shall be propagated with Basilisk using: central-body point mass or GGM03S spherical harmonics up to degree 180; DE430 third bodies; NRLMSISE-00 (default) or exponential drag; cannonball or faceted SRP; a chosen integrator (Euler, RK2, RKF45, RKF78). | E-ST-10-04C 4.2.1a, 4.2.2c, 7.2.1.1a |
| SRS-F-04 | The gravity model shall use the planet orientation at the middle of each integration step (F-01). The atmosphere model shall use the WGS-84 geodetic altitude and latitude (F-07). | Q-ST-80C 7.1.7a; E-ST-10-04C 7.2.1.1a |
| SRS-F-05 | Solar and geomagnetic activity shall come only from real data: CelesTrak observations and forecast; beyond them, NASA MSFC's prediction at the chosen percentile (5, 50 or 95). The run shall report the source it used. | UD-4 (D1), deviation D-01; user rule |
| SRS-F-06 | The Earth-fixed frame shall be ITRF93 from installed IERS-based NAIF files. Without them it shall be IAU_EARTH, with a warning stating the accuracy cost. | E-ST-10-09C 5.4.9f; E-ST-10-04C 4.2.1c |
| SRS-F-07 | Time shall be converted UTC → TAI → TT → TDB with ERFA. The simulation time variable shall be TDB seconds since the scenario epoch. Results shall be convertible to UTC. | E-ST-10-09C 5.4.4 |
| SRS-F-08 | Ground stations shall be WGS-84 geodetic sites. Access shall use the geodetic elevation above a mask. Passes shall be predicted and recorded. | E-ST-10-09C 5.4.6a |
| SRS-F-09 | Attitude guidance and control shall use Basilisk FSW chains for: inertial, Hill, velocity, Sun-safe and location pointing. Sensors and actuators shall be modelled with noise, bias, saturation and faults where Basilisk provides them. | Tool |
| SRS-F-10 | Orbit maintenance shall be available: LEO station keeping, along-track phasing, GEO longitude/inclination keeping, momentum management. | Tool |
| SRS-F-11 | A mission sequence shall run these commands: propagate (duration, epoch or event); impulsive maneuver; Lambert transfer; assignment; report; if; while; script block. | Tool |
| SRS-F-12 | Each run shall produce named series. Each series shall carry units and its frame. Results shall export to CSV with a `provenance.json` recording: tool and Basilisk versions; qualification; dependencies; scenario SHA-256; data files; time system; frames. | E-ST-10-09C 5.4.1a/h, 5.4.2a, 5.4.3; Q-ST-80C 6.2.4 |
| SRS-F-13 | Analyses: orbital lifetime and disposal rules (5-year and 25-year); ESA AD10-style delta-V and propellant budget; launch-delay sweep; altitude trade; Monte Carlo dispersions; RF link budget; power and thermal. | AD6; Tool |
| SRS-F-14 | CCSDS OPM, OMM and OEM (KVN) shall be read and validated against 502.0-B-3. Validation errors and warnings shall cite the clause. The tool shall write OPMs of initial states and OEMs of runs (Hermite or Lagrange), convert TLE ↔ OMM, and set orbits from OPM/OMM. | CCSDS 502.0-B-3 sections 3–5, 7; Annex A (ICS) |
| SRS-F-15 | The GUI shall offer: scenario editing; validation feedback; results plots; mission dashboard; mission output; kernel status; explanation of the scenario; end of life; budget; template loading. The CLI shall offer the same functions headless. | Tool |
| SRS-F-16 | Vizard visualisation, live or from a file. (desirable) | Tool |
| SRS-F-17 | At start-up the tool shall check the Basilisk version against the qualified one (2.12.0). It shall warn when they differ, and record the outcome in provenance. | Q-ST-80C 6.2.7; UD-4 (D5) |

There is no safety or dependability function. The software does not command
equipment, and category C does not call for one (RD1). The dependability
analysis is human action H04.

### 5.3 Performance requirements (D.2.1<5.3>)

Accuracy requirements are stated against independent references.

| ID | Requirement | Source |
|---|---|---|
| SRS-P-01 | Two-body propagation at the default 10 s step shall agree with GMAT to 0.05 m per day (implementation difference). | Q-ST-80C 7.1.7a |
| SRS-P-02 | With GGM03S 20 × 20 and IERS EOP files, propagation shall agree with GMAT to 1 m per day. | Q-ST-80C 7.1.7a |
| SRS-P-03 | Sun/Moon third-body propagation shall agree with GMAT to 1 m over 7 days. Cannonball SRP shall agree to 10 m over 7 days. | Q-ST-80C 7.1.7a |
| SRS-P-04 | NRLMSISE-00 drag shall agree with GMAT to 5 % of the drag-induced displacement over 1 day. | Q-ST-80C 7.1.7a |
| SRS-P-05 | Time scales: TAI−UTC and TT−TAI shall agree with GMAT to 2 µs, and TDB−TT to 50 µs. The TDB series shall reproduce SOFA's test value. | E-ST-10-09C 5.4.4b |
| SRS-P-06 | The Earth frame with EOP files shall agree with IERS 20 C04 to 1 m at the Earth's surface. | E-ST-10-09C 5.4.9f |
| SRS-P-07 | Ground-station pass start and end times shall agree with GMAT to 1 s. | E-ST-10-09C 5.4.6a |
| SRS-P-08 | The lifetime estimate shall agree with a full Basilisk decay run to 3 %. | Tool |
| SRS-P-09 | A one-day LEO run with drag and a degree-20 field shall complete in under 5 minutes on the reference PC. (desirable; not yet measured systematically) | Tool |

### 5.4 Interface requirements (D.2.1<5.4>)

External interfaces are specified in the ICD (RD3), requirements
SRS-I-01 to SRS-I-08:

| ID | Interface |
|---|---|
| SRS-I-01 | Scenario JSON |
| SRS-I-02 | CLI |
| SRS-I-03 | Results CSV and `provenance.json` |
| SRS-I-04 | CCSDS OPM/OMM/OEM |
| SRS-I-05 | Space-weather files |
| SRS-I-06 | SPICE and EOP kernels |
| SRS-I-07 | Basilisk API |
| SRS-I-08 | Vizard |

Naming conventions for data and commands are those of the CSD (RD5) and of
coding standard rule C-3: units and frames in names. Each data item's
definition (name, type, dimension, range, initial value) is in the ICD.

### 5.5 Operational requirements (D.2.1<5.5>)

| ID | Requirement |
|---|---|
| SRS-O-01 | The tool shall run interactively (GUI) or headless (CLI). A GUI run shall run in a worker thread, show live progress and be cancellable without corrupting the session. |
| SRS-O-02 | Intended use: open a template or a saved scenario; edit; validate; run; inspect and export results; run analyses. |

The GUI's modes are idle, running, and running live with Vizard. Running
disables editing of the running scenario; cancelling returns to idle with
the results so far.

### 5.6 Resources requirements (D.2.1<5.6>)

| ID | Requirement |
|---|---|
| SRS-R-01 | The tool shall run on the hardware of 4.2 without special hardware (no GPU needed; Vizard benefits from one). |
| SRS-R-02 | Memory use shall stay below 2 GB for a one-year run recorded at 60 s (desirable; not yet measured systematically). |

### 5.7 Design requirements and implementation constraints (D.2.1<5.7>)

| ID | Requirement |
|---|---|
| SRS-D-01 | Python, following the coding standard (RD6). |
| SRS-D-02 | Basilisk 2.12.0 used through its public Python API only. |
| SRS-D-03 | Engine modules that do not need Basilisk shall import without it (schema, space weather, CCSDS, geodesy, time system, frames). |
| SRS-D-04 | No third-party schema library. JSON is validated by hand-written checks. |

### 5.8 Security and privacy requirements (D.2.1<5.8>)

| ID | Requirement |
|---|---|
| SRS-S-01 | No network access unless the user starts it. Each download states what it fetches and from where. |
| SRS-S-02 | Downloaded files shall be checked before use (format, coverage) and recorded with their SHA-256. |
| SRS-S-03 | Scenario files that run Python code (`script_block`) shall not run without the user knowing; see the security analysis (`security_analysis.md`, R15). |
| SRS-S-04 | `if`/`while` conditions from a scenario file shall be evaluated without executing code: only names, numbers, subscripts, arithmetic, comparisons and logical operators (security analysis S-02). |

The security assurance level is low (UD-4, D8).

### 5.9 Portability requirements (D.2.1<5.9>)

| ID | Requirement |
|---|---|
| SRS-PO-01 | Linux and Windows. macOS where Basilisk and PySide6 install (not tested). |

### 5.10 Software quality requirements (D.2.1<5.10>)

| ID | Requirement |
|---|---|
| SRS-Q-01 | Statement coverage >= 90 % (coding standard C-10; target to be agreed, H09). |
| SRS-Q-02 | Zero static-analysis findings for the configured rule set. |
| SRS-Q-03 | Function complexity <= 15 for new code. |

### 5.11 Software reliability requirements (D.2.1<5.11>)

| ID | Requirement |
|---|---|
| SRS-RE-01 | A run that fails inside Basilisk (for example a re-entry, or a non-finite state) shall end with a clear message and keep the results so far. It shall not crash the GUI. |
| SRS-RE-02 | An autosave shall protect unsaved scenario edits. |

### 5.12 Software maintainability requirements (D.2.1<5.12>)

| ID | Requirement |
|---|---|
| SRS-M-01 | Every change shall run the CI workflow (lint, tests, metrics, traceability). |
| SRS-M-02 | Workarounds for Basilisk defects shall be isolated in their own modules (`engine/planet_rotation.py`, `engine/geodetic_atmosphere.py`) and removable when Basilisk is fixed (H10). |

### 5.13 Software safety requirements (D.2.1<5.13>)

None. Category C ground analysis tool; no safety function (5.2). Results
used for safety-relevant decisions (for example disposal compliance) are
the analyst's responsibility, and the tool states its model limits (SUM).

### 5.14 Software configuration and delivery requirements (D.2.1<5.14>)

| ID | Requirement |
|---|---|
| SRS-DEL-01 | Delivery shall be as a Python package, a Debian package and a Windows installer. Each installer shall pin Basilisk 2.12.0 and offer to pre-fetch the data files (SRelD). |

### 5.15 Data definition and database requirements (D.2.1<5.15>)

| ID | Requirement |
|---|---|
| SRS-DF-01 | CCSDS 502.0-B-3 KVN for orbit data exchange. |
| SRS-DF-02 | CSV with a header row and SI units for results. |
| SRS-DF-03 | JSON for scenarios and provenance. |

There is no database.

### 5.16 Human factors related requirements (D.2.1<5.16>)

| ID | Requirement |
|---|---|
| SRS-H-01 | Every input shall show its unit and, where relevant, its frame or epoch. Errors shall point to the field. |
| SRS-H-02 | Templates shall show worked examples. |
| SRS-H-03 | The Explain tab shall summarise what a scenario models. |

The UX/UI guidelines applied after this audit (UD-5) will refine these
requirements.

### 5.17 Adaptation and installation requirements (D.2.1<5.17>)

| ID | Requirement |
|---|---|
| SRS-A-01 | Data files shall be installable per user or for the whole installation: Earth orientation, space weather, Vizard. |
| SRS-A-02 | The Basilisk data files shall come from Basilisk's own data fetcher. |

No other adaptation data exists.

## 6 Validation requirements (D.2.1<6>)

Methods: T = test, A = analysis, I = inspection, R = review of design.

| Requirement | Method | Evidence |
|---|---|---|
| SRS-F-01 | T | `tests/test_scenario_schema.py`, `tests/test_migrations.py`, `tests/test_validation.py` |
| SRS-F-02 | T | `tests/test_tle.py`, `tests/test_osculating_elements.py` |
| SRS-F-03 | T | `tests/test_two_body_validation.py`, `tests/validation/test_v04_propagation.py` |
| SRS-F-04 | T | `tests/test_planet_rotation.py`, `tests/test_geodesy.py`, V-04 |
| SRS-F-05 | T | `tests/test_spaceweather.py` |
| SRS-F-06 | T | `tests/test_earth_orientation.py`, `tests/validation/test_v02_earth_orientation.py` |
| SRS-F-07 | T | `tests/test_time_system.py`, `tests/validation/test_v01_time_scales.py` |
| SRS-F-08 | T | `tests/test_geodesy.py`, `tests/validation/test_v05_passes.py` |
| SRS-F-09 | T | `tests/test_device_realism.py`, `tests/test_css_estimation.py`, FSW tests |
| SRS-F-10 | T | `tests/test_orbit_maintenance*.py`, `tests/test_geo_station_keeping.py`, `tests/test_momentum_dumping.py` |
| SRS-F-11 | T | `tests/test_mission_engine.py`, `tests/test_command.py` |
| SRS-F-12 | T | `tests/test_results.py`, `tests/test_frames.py`, `tests/test_dependencies.py` |
| SRS-F-13 | T | `tests/test_lifetime.py`, `tests/test_propellant_budget.py`, `tests/test_monte_carlo.py`, `tests/test_link_budget.py`, `tests/test_thermal_simulation.py` |
| SRS-F-14 | T | `tests/test_ccsds_odm.py`, `tests/validation/test_v06_ccsds_oem.py` |
| SRS-F-15 | T, I | `tests/gui/`, `tests/test_cli.py` |
| SRS-F-16 | T | `tests/test_vizard*.py` |
| SRS-F-17 | T | `tests/test_dependencies.py` |
| SRS-P-01 to P-07 | T | `tests/validation/` (V-01, V-02, V-04, V-05) |
| SRS-P-08 | T | `tests/test_lifetime.py::test_reentry_date_matches_a_basilisk_decay_run` |
| SRS-P-09, SRS-R-02 | A | not yet done (open item in SVR) |
| SRS-I-01 to I-08 | T | see the ICD validation matrix |
| SRS-O-01, O-02 | T | `tests/gui/test_run_worker*.py`, `tests/test_service_run_live.py` |
| SRS-S-01 to S-04 | T, R | `tests/test_spaceweather.py` (fetch never called by `resolve`), `tests/gui/test_startup_fetch_dialog.py`; S-03: `tests/test_mission_engine.py`, `tests/test_cli.py`, `tests/gui/test_main_window.py` (script consent); S-04: `tests/test_command.py` (condition evaluator); security analysis |
| SRS-Q-01 to Q-03 | A | CI metrics (`compliance/metrics.md`) |
| SRS-RE-01, RE-02 | T | `tests/test_service_execution_errors.py`, `tests/test_lifetime.py::test_a_run_stops_cleanly_when_its_spacecraft_reenters`, `tests/test_autosave.py` |
| SRS-M-01, M-02 | I | CI workflow; module structure |
| SRS-D-01 to D-04 | I | coding standard checks (ruff); import tests |
| SRS-PO-01 | T | CI (Linux); Windows installer test (manual, H01) |
| SRS-DEL-01 | T, I | `tests/test_dependencies.py` (installer pins) |
| SRS-DF-01 to DF-03 | T | as SRS-F-12, SRS-F-14 |
| SRS-H-01 to H-03 | I, T | GUI tests; UX review (UD-5) |
| SRS-A-01, A-02 | T | `tests/test_earth_orientation.py`, `tests/gui/test_startup_fetch_dialog.py` |

## 7 Traceability (D.2.1<7>)

- **Backward (SRS → upper level):** the "Source" column of 5.2 and 5.3.
- **Forward:** the upper levels are AD1–AD5 and the user's decisions. For
  each requirement of AD1–AD5, `compliance/traceability_matrix.csv` lists:
  - its status;
  - its code evidence;
  - its tests;
  - its verification method.
- No SSS exists to trace from (H03).

## 8 Logical model description (D.2.1<8>)

**Method:** a functional decomposition into data flows, described in text
and the diagram of 4.3.

**Top level:** define → check → run → analyse → exchange.

1. **Define:** `schema`, the scenario data model. The GUI editors and
   the CLI produce and change scenarios. Templates are complete scenarios.
2. **Check:**
   - `schema` validation (field-level);
   - `engine/scenario_checks.py` plausibility (pass prediction, TLE age,
     gravity fidelity);
   - `engine/scenario_explainer.py` (what is modelled).
3. **Run:** `engine/service.py` builds a Basilisk simulation. It contains:
   - SPICE;
   - gravity with mid-step orientation;
   - atmosphere with geodetic proxy;
   - spacecraft, FSW, sensors, actuators;
   - ground stations;
   - recorders.

   It runs the simulation (segmented beyond 100 days,
   `engine/long_run.py`) and collects series into a `ResultSet` with
   provenance. `engine/mission_engine.py` runs a mission sequence on top.
4. **Analyse:**
   - lifetime;
   - budget;
   - Monte Carlo;
   - link budget;
   - formation and constellation design.

   These run on scenarios or on results.
5. **Exchange:**
   - CSV and provenance export;
   - CCSDS ODM read/write;
   - Vizard.

**Behaviour:** a run is a batch transformation, scenario → results. It
starts on request (Run button or CLI) and ends on completion,
cancellation or error (5.5, SRS-RE-01). The GUI stays responsive
because the run executes in a worker thread.
