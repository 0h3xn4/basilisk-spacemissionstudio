# SpaceMissionStudio: Interface Control Document (ICD)

DRD: ECSS-E-ST-40C Annex E
Document: SMS-ICD, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft, derived from the implemented interfaces (version 2.0.0).
It has not been reviewed (H01), and no IRD exists (waived, D-11).

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
| RD5 | `ICD_cli.md`, generated command and argument list of the CLI |

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
| ICD-02 | The command-line interface is `spacemissionstudio <command> [arguments]`. Commands and arguments are those of RD5. The exit code is 0 on success; 1 on an input or validation error; 2 when a required component is missing (Basilisk, or PySide6 and plotly for `gui`) or on a usage error (argparse); 3 when a run or analysis fails. | SRS-I-02 |
| ICD-03 | Each result series is one CSV file. The first column is `time_s`. Columns are named `<column>_<unit>`. A run writes a `provenance.json` alongside its results. | SRS-I-03 |
| ICD-04 | CCSDS OPM, OMM and OEM are read and written in KVN per AD2. The items supported are those in RD3. | SRS-I-04 |
| ICD-05 | Space weather is read from CelesTrak SW-All files (CSV or legacy text, RD4) and from NASA MSFC prediction tables. Files are validated for coverage before use. | SRS-I-05 |
| ICD-06 | SPICE kernels come from Basilisk's data fetcher. IERS-based NAIF Earth PCKs come from the user directory or the installation directory. | SRS-I-06 |
| ICD-07 | Basilisk is used only through its public Python API (2.12.0). | SRS-I-07 |
| ICD-08 | Vizard is used through Basilisk's `vizSupport`: a save file or a live stream to a separate Vizard process. | SRS-I-08 |
| ICD-09 | A flight-software export is a folder holding a standalone C project for one spacecraft, its interface control document, its traceability table, a `manifest.json` with the configuration digest and the SHA-256 of every file, and the recorded run (`capture.json`, `tests/data/*.trace`). | SRS-F-18 |
| ICD-10 | A software-in-the-loop run exchanges frames of the SIL transport contract, version 1 (`SIL_CONTRACT.md` in every export), between the tool and the flight-software program it started: HELLO with the program's ports and layout hashes, RESET, one STEP and OUTPUT per step, ERROR, BYE. | SRS-F-19 |

The interfaces are of three kinds:

- **Software to software:** ICD-04 to ICD-10.
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

Every command, argument and help text is in RD5, generated from the CLI's
parser. The commands are:

- **Scenario:** `validate`, `run`, `monte-carlo`.
- **Analyses:** `lifetime`, `budget`, `spaceweather-resolve`.
- **Design:** `generate-constellation`, `generate-phasing-formation`.
- **Data:** `kernels-status`, `earth-orientation` (status, `--fetch`,
  `--import`, `--rollback`).
- **Exchange:** `ccsds-validate`, `ccsds-export`, `ccsds-import`.
- **GUI:** `gui`.

Results and errors go to standard output and standard error; the exit
codes are those of ICD-02.

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
| File naming (default, AD2 3.1.6, 4.1.6, 5.1.4) | One message per spacecraft, named `<spacecraft name>.opm`, `.omm` or `.oem`, in the output directory the user chooses; this is what `ccsds-export` and `run --oem` write. The message's `CREATION_DATE` and `ORIGINATOR` identify its version and source. To be adjusted with each exchange partner (decision 9). |
| Exchange method (default, AD2 3.1.7, 4.1.7, 5.1.5) | Plain KVN text files, exchanged by whatever file transfer the partners use; the tool has no network interface for them. To be agreed with each exchange partner. |

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

#### 5.3.9 Flight-software export (ICD-09)

| Item | Definition |
|---|---|
| Service | `export-fsw` (CLI) or the Flight Software tab writes one spacecraft's attitude flight software as a C project; `fsw-status` and the tab check a recorded export against the scenario. |
| Format | A folder: `CMakeLists.txt`; `basilisk/` (the Basilisk 2.12.0 C sources the modules need, unchanged, with Basilisk's licence); `generated/` (C message interface, `fsw_config.[ch]`, scheduler, port tables, layout checks); `host/fsw_host.c`; `tests/` (one C unit test per module, replay traces); `ICD.md`; `TRACEABILITY.md`; `README.md`; `capture.json`; `manifest.json`. |
| Key items | `manifest.json`: `format` (1), `config_digest` (64 hex digits), `basilisk_revision`, `rate_ns`, `ports` (name, message type, size in bytes, 16-hex-digit layout hash), `files` (path to SHA-256). Trace files: magic `SMSFTRC1`, little-endian, one record per step of time in ns, written flags and raw payloads (`generated/fsw_trace.h`). |
| Record in the scenario | `Scenario.fsw_exports[]`: spacecraft, folder, `config_digest`, per-group hashes (`parts`), export time, Basilisk revision (RD1). |
| Frequency | On the user's request. |

#### 5.3.10 Software-in-the-loop link (ICD-10)

| Item | Definition |
|---|---|
| Service | `sil` (CLI) or Run SIL... in the Flight Software tab runs the scenario with one spacecraft's flight software in an external program, one step at a time. |
| Parties | The tool listens; the program, started as `<program> sil <address>` with the session token in `SMS_SIL_TOKEN`, connects. |
| Transport | A Unix-domain stream socket in a folder only the user can open (Linux, macOS), or TCP on 127.0.0.1 (Windows, or on request). The protocol needs only a reliable ordered byte stream (`generated/fsw_transport.h`, `spacemissionstudio.sil.transport.Transport`). |
| Format | Frames of a 28-byte little-endian header (magic `SMSL`, contract version 1, type, sequence number, payload length, simulation time in ns, CRC-32) and a payload. HELLO carries the token, name, configuration digest, step and every port (name, message type, size, 16-hex-digit layout hash); RESET and STEP carry a written flag and the raw payload per input port; OUTPUT the program's execution time and the same per output and telemetry port. Normative: `spacemissionstudio/fsw_export/templates/SIL_CONTRACT.md`. |
| Errors | A wrong magic, version, type, length, CRC, token, step or port list; a frame out of order; no answer within the step timeout (10 s by default); a closed link; an exited program: ERROR with the reason, and the run stops. |
| Frequency | Every flight-software step of the run. |

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
| ICD-09 | T | `tests/test_fsw_export.py`, `tests/test_fsw_export_units.py`, `tests/test_fsw_vendored_sources.py` |
| ICD-10 | T | `tests/test_sil_contract.py` (both sides of the frames, every refusal), `tests/test_sil.py` (the C harness against the Python side) |

## 7 Traceability (E.2.1<7>)

- **Backward (ICD → SRS):** column "SRS" of 5.2.
- **Forward (SRS-I-01 to SRS-I-08 → ICD):** one-to-one. ICD-nn details
  SRS-I-nn. ICD-09 details the export format of SRS-F-18, ICD-10 the
  SIL link of SRS-F-19.
- **Further:** the CCSDS items are traced in
  `compliance/traceability_matrix.csv`.
