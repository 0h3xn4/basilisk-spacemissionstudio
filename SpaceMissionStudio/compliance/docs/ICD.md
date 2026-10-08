# SpaceMissionStudio: Interface Control Document (ICD)

DRD: ECSS-E-ST-40C Annex E
Document: SMS-ICD, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft, derived from the implemented interfaces (version 2.0.0).
It has not been reviewed (H01), and no IRD exists (H03).

## 1 Introduction (E.2.1<1>)

This ICD defines the external interfaces of SpaceMissionStudio: how users
and other software give it data and receive data from it. It details
interface requirements SRS-I-01 to SRS-I-08 of the SRS.

## 2 Applicable and reference documents (E.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | SRS (`SRS.md`) |
| AD2 | CCSDS 502.0-B-3, Orbit Data Messages |
| AD3 | ECSS-E-ST-10-09C (frames and time) |
| RD1 | `ICD_scenario_fields.md`, generated field dictionary of the scenario file |
| RD2 | `CSD.md`, coordinate systems and time scales |
| RD3 | `compliance/ics_ccsds_502.csv`, CCSDS Annex A conformance statement |
| RD4 | CelesTrak space-weather format, `https://celestrak.org/SpaceData/SpaceWx-format.php` |

## 3 Terms, definitions and abbreviated terms (E.2.1<3>)

As in the SRS. KVN means keyword = value notation (CCSDS).

## 4 Software overview (E.2.1<4>)

See SRS section 4 for the software overview.

## 5 Requirements and design

### 5.1 General provisions (E.2.1<5.1>)

- **Identifiers:** each interface requirement has an identifier `ICD-nn`,
  traced to the SRS interface requirement it details.
- **Units:** SI unless the format prescribes otherwise. CCSDS messages use
  km and km/s, as AD2 requires.
- **Naming conventions:** RD2 and coding standard rule C-3. Units and
  frames appear as suffixes, e.g. `r_BN_N`, `semi_major_axis_km`,
  `inclination_deg`.

### 5.2 Interface requirements (E.2.1<5.2>)

| ID | Requirement | SRS |
|---|---|---|
| ICD-01 | Scenario files are UTF-8 JSON with the fields of RD1. Files of an older `schema_version` are migrated on load. An unknown field is refused with an error naming it. | SRS-I-01 |
| ICD-02 | The command-line interface is `spacemissionstudio <command> [options]`. Commands are listed in 5.3.2. The exit code is 0 on success, 1 on an input or validation error, and 2 or 3 on a run failure. | SRS-I-02 |
| ICD-03 | Each result series is one CSV file. The first column is `time_s`. Columns are named `<column>_<unit>`. A run writes a `provenance.json` alongside its results. | SRS-I-03 |
| ICD-04 | CCSDS OPM, OMM and OEM are read and written in KVN per AD2. The items supported are those in RD3. | SRS-I-04 |
| ICD-05 | Space weather is read from CelesTrak SW-All files (CSV or legacy text, RD4) and from NASA MSFC prediction tables. Files are validated for coverage before use. | SRS-I-05 |
| ICD-06 | SPICE kernels come from Basilisk's data fetcher. IERS-based NAIF Earth PCKs come from the user directory or the installation directory. | SRS-I-06 |
| ICD-07 | Basilisk is used only through its public Python API (2.12.0). | SRS-I-07 |
| ICD-08 | Vizard is used through Basilisk's `vizSupport`: a save file or a live stream to a separate Vizard process. | SRS-I-08 |

The interfaces are of three kinds:

- **Software to software:** ICD-04 to ICD-08.
- **Software to hardware:** none. The tool uses only the host computer.
- **Man-machine:** the GUI and the CLI (ICD-02). The GUI is described in
  the SUM.

### 5.3 Interface design (E.2.1<5.3>)

Each interface of 5.2 is defined below: its service, data items, format,
ranges, units and frequency. The scenario file's complete field list is
RD1, generated from the code so that it cannot drift from it.

#### 5.3.1 Scenario file (ICD-01)

| Item | Definition |
|---|---|
| Service | Complete description of one simulation. Read by the GUI, the CLI and the engine; written by the GUI and by `ccsds-import`. |
| Format | JSON object; root `Scenario`. Every field, its type, default and unit are in RD1, generated from `spacemissionstudio/schema/scenario.py` and `command.py`. |
| Key items | `epoch_utc` (ISO 8601 UTC, required); `spacecraft` (one or more items); `gravity.central_body`; `gravity.central_body_degree` (0–180); `sim_settings.duration_days` (> 0; runs over 100 days are segmented); `sim_settings.dynamics_task_rate_s` (> 0 s, default 10); `space_weather.source` (`bundled` or `local_file`). |
| Range and initial values | As in RD1 and each class's `validate()`. An invalid value is refused with a message naming the field. |
| Versioning | `schema_version` is currently 4. `schema/migrations.py` upgrades older files. |
| Frequency | On load and save. |

#### 5.3.2 Command-line interface (ICD-02)

| Command | Service | Main options |
|---|---|---|
| `validate <scenario>` | Schema validation and plausibility checks; no Basilisk needed | — |
| `run <scenario>` | Headless run; writes CSV, provenance and optional OEMs | `--out-dir`, `--oem`, `--oem-stride N`, `--oem-interpolation {hermite,lagrange}`, `--vizard-save-file`, `--vizard-live-stream` |
| `monte-carlo <scenario>` | Monte Carlo batch | archive directory, runs |
| `lifetime <scenario>` | Re-entry estimate and disposal rules | `--deorbit-perigee-km` |
| `budget <scenario>` | AD10-style delta-V and propellant budget | — |
| `kernels-status` | SPICE kernel cache state | — |
| `earth-orientation` | Fetch, import, list or roll back the IERS-based Earth PCKs | sub-actions |
| `ccsds-validate <files>` | 502.0-B-3 conformance check of OPM, OMM and OEM files | — |
| `ccsds-export <scenario>` | One OPM per spacecraft (initial state) | `--out` |
| `ccsds-import <odm> <scenario>` | Set a spacecraft's orbit from an OPM or a TLE-based OMM | `--spacecraft`, `--out` |
| `spaceweather-resolve` | Show which space-weather data a date range uses | dates |
| `gui` | Start the GUI | — |

#### 5.3.3 Results (ICD-03)

| Item | Definition |
|---|---|
| Series CSV | `<series name>.csv` (for example `sat-1.position_N.csv`). Header: `time_s`, then `<column>_<unit>`. One row per recorded sample. Values have 9 significant digits. |
| `time_s` | TDB seconds since the scenario epoch. Convert to UTC with `engine.time_system.elapsed_to_utc` (RD2). |
| `provenance.json` | `spacemissionstudio_version`; `basilisk_version`; `qualified_basilisk_version`; `basilisk_qualified`; `run_started_utc`; `integrator`; `dynamics_task_rate_s`; `dependency_versions`; `data_files` (path, size, SHA-256 per file used); `time_system`; `frames`; `transformations`; `series_frames`; the scenario's SHA-256. |
| Frames | `series_frames` gives each series' frame mnemonic (N, B, L, ...) per RD2. |
| Frequency | Once per run. A series' sample interval is the dynamics step, or `sim_settings.record_interval_s` if set. |

#### 5.3.4 CCSDS orbit data messages (ICD-04)

| Item | Definition |
|---|---|
| Read and validate | OPM, OMM and OEM in KVN. Every item of the Annex A ICS is read (RD3). Errors (shall/must) and warnings (should) cite the clause. A message declaring a version other than 3.0 is checked against 3.0 rules, with a warning. |
| Write: OPM | Initial state and osculating elements (GM = 398600.436 km^3/s^2, the simulation's) in EME2000, UTC. |
| Write: OMM | From a TLE: TEME, UTC, SGP4/SGP4-XP. |
| Write: OEM | From a run: EME2000; UTC epochs converted from TDB; position in km to 1 mm; velocity in km/s to 1 um/s; Hermite (default) or Lagrange interpolation of degree 7. |
| Conversion | TLE ↔ OMM; an OPM or a TLE-based OMM becomes a scenario orbit. |
| Interoperability | GMAT R2026a reads only version 1.0 OEMs with Lagrange interpolation. See finding F-08 in `compliance/phase3_log.md` and the SUM. |

#### 5.3.5 Space-weather files (ICD-05)

| Item | Definition |
|---|---|
| Bundled | CelesTrak SW-All (observed daily Kp/Ap and F10.7, then CelesTrak's forecast), shipped in `spacemissionstudio/data/spaceweather/`, together with NASA MSFC's prediction (13-month smoothed F10.7 and Ap at the 5th, 50th and 95th percentiles). |
| Local file | The user's CelesTrak `.txt` or `.csv` (RD4). |
| Use | `engine.spaceweather.resolve()` assembles the records for the run's span. It refuses a span outside the data, naming the range. It never accesses the network. |
| Download | `engine.spaceweather.fetch()`, only on explicit user action (GUI start-up prompt or menu). |

#### 5.3.6 SPICE and Earth orientation kernels (ICD-06)

| Item | Definition |
|---|---|
| SPICE | `naif0012.tls`, `de430.bsp`, `de-403-masses.tpc`, `pck00010.tpc`, through Basilisk's data fetcher. |
| Earth PCKs | `earth_1962_*_combined.bpc` and `earth_latest_high_prec.bpc` from NAIF. Location: `~/.cache/SpaceMissionStudio/earth_orientation/` (user) or `<prefix>/share/spacemissionstudio/earth_orientation/` (installation). A manifest records the source, the SHA-256 and the last datum. |

#### 5.3.7 Basilisk (ICD-07)

The engine creates Basilisk objects through their public Python classes and
messages (`SimulationBaseClass`, `spacecraft`, `gravityEffector`,
`spiceInterface`, `msisAtmosphere`, FSW modules, ...).

- Its own SysModels (controllers, the mid-step orientation and the
  geodetic proxy) subscribe to Basilisk messages by Basilisk's messaging
  API.
- Basilisk is not modified.
- Version 2.12.0 is checked at start-up.

#### 5.3.8 Vizard (ICD-08)

- **Save file:** a `.bin` file written through `vizSupport`.
- **Live:** a ZMQ stream to a Vizard process started by the tool or by the
  user.
- Vizard is downloaded only on consent.

## 6 Validation requirements (E.2.1<6>)

| ID | Method | Evidence |
|---|---|---|
| ICD-01 | T | `tests/test_scenario_schema.py` (incl. `test_load_scenario_rejects_an_unknown_field_naming_it`), `tests/test_migrations.py`, `tests/test_scenario_templates.py` |
| ICD-02 | T | `tests/test_cli.py` |
| ICD-03 | T | `tests/test_results.py`, `tests/test_frames.py` |
| ICD-04 | T | `tests/test_ccsds_odm.py` (Annex G examples, every rule, every ICS keyword), `tests/validation/test_v06_ccsds_oem.py` (exchange with GMAT) |
| ICD-05 | T | `tests/test_spaceweather.py` |
| ICD-06 | T | `tests/test_earth_orientation.py`, `tests/test_dependencies.py` |
| ICD-07 | T, I | the test suite against Basilisk 2.12.0 (CI); `tests/test_dependencies.py` |
| ICD-08 | T | `tests/test_vizard*.py` |

## 7 Traceability (E.2.1<7>)

- **Backward (ICD → SRS):** column "SRS" of 5.2.
- **Forward (SRS-I-01 to SRS-I-08 → ICD):** one-to-one. ICD-nn details
  SRS-I-nn.
- **Further:** the CCSDS items are traced in
  `compliance/traceability_matrix.csv`.
