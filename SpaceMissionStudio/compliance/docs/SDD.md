# SpaceMissionStudio: Software Design Document (SDD)

DRD: ECSS-E-ST-40C Annex F
Document: SMS-SDD, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft. It describes the design as implemented (version 2.0.0)
after the fact; the design was not produced in this form before the code
was written. It has not been reviewed (H01: PDR/CDR).

## 1 Introduction (F.2.1<1>)

This SDD describes the architecture and the components of
SpaceMissionStudio. It was written during the ECSS/CCSDS audit because the
tool had no design documentation (`compliance/gap_analysis.md`, R14). It
lets a maintainer find where a requirement is implemented and what a change
affects.

The component descriptions and the traceability are generated from the
source (`SDD_components.md`, RD1) so they stay correct as the code changes.
This document gives the architecture and the design choices that the
generated part cannot show.

## 2 Applicable and reference documents (F.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | SRS (`SRS.md`) |
| AD2 | ICD (`ICD.md`) |
| AD3 | Coding standard (`coding_standard.md`) |
| RD1 | `SDD_components.md`, generated component descriptions and traceability |
| RD2 | `ICD_scenario_fields.md`, generated scenario data dictionary |
| RD3 | `CSD.md`, coordinate systems and time |
| RD4 | `SRF.md`, software reuse file (Basilisk and the third-party packages) |
| RD5 | `compliance/phase3_log.md`, findings F-01 to F-08 |
| RD6 | Basilisk 2.12.0 documentation, `https://avslab.github.io/basilisk/` |

## 3 Terms, definitions and abbreviated terms (F.2.1<3>)

As in the SRS, and:

| Term | Meaning |
|---|---|
| SysModel | A Basilisk simulation module, called once per task step in priority order |
| Message | A Basilisk typed data payload connecting SysModels |
| Task | A Basilisk list of SysModels updated at a fixed rate |
| Worker | A Qt `QThread` running a long operation outside the GUI thread |

## 4 Software design overview

### 4.1 Software static architecture (F.2.1<4.1>)

The software is one Python package, `spacemissionstudio`, in three layers.
Each layer uses only the layers below it:

```
   +------------------------------+   +---------------------------+
   | gui/  (PySide6)              |   | cli.py                    |
   | editors, results, analyses   |   | headless commands         |
   +--------------+---------------+   +-------------+-------------+
                  |                                 |
   +--------------v---------------------------------v-------------+
   | engine/   simulation service, analyses, data and exchange    |
   |           (Basilisk only where a simulation is built)        |
   +--------------+-----------------------------------------------+
                  |
   +--------------v---------------+   +---------------------------+
   | schema/  scenario data model |   | data/  bundled data files |
   | and validation               |   | (space weather, catalogs) |
   +------------------------------+   +---------------------------+
```

- **schema:** the scenario data model (dataclasses), its validation and its
  migrations. No dependency on Basilisk or Qt.
- **engine:** builds and runs simulations (`service`, `long_run`,
  `mission_engine`); runs analyses (lifetime, budget, Monte Carlo, link
  budget, formation and constellation design); provides data and exchange
  (space weather, Earth orientation, kernels, CCSDS, results). Only the
  modules that build a simulation import Basilisk, and they import it
  inside functions, so the rest imports without it (SRS-D-03).
- **gui** and **cli:** two front ends over the same engine. Nothing is
  duplicated between them.

**States and modes:**
- The GUI is either idle (editing) or running one long operation (a run, a
  Monte Carlo batch, a lifetime or budget analysis, a download) in a
  worker.
- While an operation runs, the controls that would start another are
  disabled. Closing the window is refused until the worker has finished or
  been cancelled.
- The engine has no persistent modes. A run is a transformation, scenario
  → results.

**Mission and configuration data are kept apart from the code:**
- Mission data is the scenario file (JSON, RD2).
- Configuration data:
  - bundled data under `spacemissionstudio/data/` (space weather, device
    catalog);
  - installed data under the user or installation directory (Earth
    orientation kernels, cached space weather, Vizard);
  - Basilisk's SPICE kernels, from Basilisk's data fetcher.
- Physical constants come from Basilisk or are named in
  `engine/environment_models.py` and `engine/ccsds_odm.py`, with their
  source (SRS-D-03).

### 4.2 Software dynamic architecture (F.2.1<4.2>)

The tool has no real-time constraints. A run computes as fast as the host
allows; nothing is synchronised with a clock.

- **Computational model inside a run:** Basilisk's.
  - One process, `dynProcess`, holds one task, `dynTask`, at the scenario's
    dynamics step (`sim_settings.dynamics_task_rate_s`, default 10 s).
  - In each step, Basilisk calls the SysModels in decreasing priority
    order:
    - SPICE (500);
    - the mid-step planet orientation (450);
    - space weather (400);
    - the geodetic proxy (395);
    - the atmosphere (390);
    - the wind (380);
    - eclipse (370);
    - the effectors (100);
    - power (40–50);
    - the FSW modules;
    - the spacecraft integration (10).
  - The order makes each module read messages already written in the same
    step.
- **Threads:**
  - The GUI thread handles the user interface only.
  - Each long operation runs in its own worker thread and reports to the
    GUI through queued Qt signals.
  - The engine runs a simulation in chunks (`run_live`). After each chunk
    it reports progress and checks for cancellation, so a cancel takes
    effect at the next chunk boundary and never kills a thread.
- **Processes:**
  - Monte Carlo with `thread_count` > 1 uses a `multiprocessing.Pool`.
  - Vizard is a separate program, fed through a save file or a ZMQ
    stream.
- **Long runs:** runs past 100 days are split into segments
  (`engine/long_run.py`). Each segment is a fresh Basilisk simulation that
  starts from the previous segment's final state, because Basilisk's
  64-bit nanosecond clock limits one simulation to about 104 days.

**Behaviour:**
1. A GUI run: the user presses Run → the scenario is validated → a worker
   builds the simulation → chunks execute, with live plots updated → the
   run ends (complete, cancelled or failed) → the results are shown.
2. A CLI run follows the same path without live plots.
3. A mission sequence (`engine/mission_engine.py`) runs its commands in
   order on one simulation. Propagate commands stop on a duration, an
   epoch or an event.

**Error handling and fault containment:**
- **Input errors:**
  - Invalid input raises `ScenarioValidationError`, naming the field,
    before anything is built.
  - The GUI shows the error at the field.
  - The CLI prints it and exits with code 1.
- **Build and run errors:**
  - These raise `SimulationServiceError` with an explanation, for example
    a Basilisk `RuntimeError` translated by `raise_clear_execution_error`,
    or a detected re-entry.
  - The results recorded up to the failure are kept (SRS-RE-01).
- **Data errors:**
  - The data modules raise their own exceptions, each stating the file and
    the problem: `SpaceWeatherError`, `EarthOrientationError`,
    `KernelError`, `OdmError`, `LongRunError`.
  - A file that does not cover the run is refused, never extrapolated.
- **Containment:**
  - The worker thread is the GUI's fault containment: an exception ends
    the operation, not the application.
  - Each Monte Carlo run is contained in its own process.
- **Logging:**
  - Every module logs through `logging_setup` to a log file.
  - Warnings that affect accuracy are also added to the results'
    warnings, for example the IAU_EARTH fallback (F-06).
  - Whether the Basilisk in use is the qualified one is recorded in the
    provenance (`basilisk_qualified`).

### 4.4 Interfaces context (F.2.1<4.4>)

The external interfaces are defined in the ICD (AD2). In context:

```
            user
             |  GUI / CLI (ICD-02)
             v
   +-------------------+   scenario JSON (ICD-01)  +----------------+
   |                   |<------------------------->| file system    |
   | SpaceMissionStudio|   results CSV, provenance |                |
   |                   |-------------------------->| (ICD-03)       |
   |                   |   CCSDS OPM/OMM/OEM       |                |
   |                   |<------------------------->| (ICD-04)       |
   +---+-----+-----+---+                           +----------------+
       |     |     |
       |     |     +-- space weather, Earth PCKs (ICD-05, ICD-06); downloaded only on consent
       |     +-------- Basilisk 2.12.0 Python API (ICD-07)
       +-------------- Vizard: save file or ZMQ stream (ICD-08)
```

### 4.5 Long lifetime software (F.2.1<4.5>)

- **Portability:** the tool is written in Python and runs where Basilisk
  and PySide6 install (SRS-PO-01). It has no operating-system-specific
  code except the paths of the data directories, which follow each
  platform's convention.
- **Version pinning:** the reused software is pinned (Basilisk 2.12.0,
  checked at start-up) and recorded in each run's provenance, so a result
  can be reproduced with the same versions.
- **Workarounds:** those for Basilisk defects are isolated in their own
  modules (`engine/planet_rotation.py`, `engine/geodetic_atmosphere.py`).
  They are attached at one point each in `engine/service.py`, so they can
  be removed when a qualified Basilisk release fixes the defects (SRS-M-02,
  H10).
- **Data formats:** these are open and documented: JSON, CSV and CCSDS KVN.
  Older scenario files are migrated by `schema/migrations.py`.

### 4.6 Memory and CPU budget (F.2.1<4.6>)

No budget has been allocated to components, and none was measured
systematically (SRS-P-09 and SRS-R-02 are "desirable" and wait for
measurement).

What is known from use:
- The simulation (Basilisk's C++ modules, called from the engine) uses
  almost all of a run's processing time.
- The recorded series use most of its memory. Memory grows with the
  duration divided by the recording interval and with the number of
  series; `sim_settings.record_interval_s` bounds it.
- The GUI's live plots are throttled so that plotting does not slow the
  run.

### 4.7 Design standards, conventions and procedures (F.2.1<4.7>)

| Item | Adopted |
|---|---|
| Architectural design method | Layered functional decomposition (4.1); data flow as in the SRS logical model (SRS section 8) |
| Detailed design method | Python modules, dataclasses for data, functions and classes; Basilisk SysModels in Python for in-simulation behaviour |
| Code documentation standard | Docstrings on every public module, class and function (coding standard AD3); units in names or trailing comments |
| Naming conventions | PEP 8; units and frames as suffixes (AD3 rule C-3; RD3) |
| Programming standard | AD3, rules C-1 to C-15; enforced by `ruff` in CI |
| Reused components | Basilisk 2.12.0, numpy, sgp4, pyerfa, PySide6, plotly (RD4) |
| Main design trade-offs | 1. Use Basilisk unmodified and correct its two accuracy defects in the tool (F-01, F-07), so that the reused software stays qualified as it is. 2. Hand-written schema validation instead of a schema library (SRS-D-04): field-precise messages, one fewer dependency. 3. Offline by design: no download without the user's consent (SRS-S-01). |

## 5 Software design

### 5.1 General (F.2.1<5.1>)

The architecture is described in section 4 and the components in 5.2 to
5.5. The software is not flight software, so in-flight modification does
not apply.

### 5.2 Overall architecture (F.2.1<5.2>)

- **Static architecture:** 4.1.
- **Dynamic architecture:** 4.2, covering the computational model of a run,
  the thread and process model, segmentation and cancellation.
- **Behaviour:** the scenarios of 4.2.
- **Error handling and fault containment:** 4.2.

The design method is the one of 4.7: layered decomposition, with Basilisk's
own task and message model inside a run.

### 5.3 Software components design – general (F.2.1<5.3>)

The components are the 80 modules of the package. RD1 lists each with:
- its identifier;
- its purpose;
- the SRS requirements it implements;
- its subordinates (public classes and functions);
- the package modules and the third-party packages it uses;
- its size.

Every component is new development, except the reused software (RD4). The
reused software is not part of the package.

Each component is uniquely identified by its module path. The software
requirements are allocated to components in RD1's forward traceability.

### 5.4 Software components design – aspects of each component

#### 5.4.1 General (F.2.1<5.4.1>)

As F.2.1<5.4.1>a allows, the component aspects are produced from the code
itself (RD1, generated by `compliance/tools/build_sdd_components.py`)
rather than written out per component. That this is acceptable has to be
agreed with the customer (H01).

#### 5.4.2 Component identifier (F.2.1<5.4.2>)

The module path, for example `engine/service`. It is hierarchical (package,
then module) and follows Python's naming rules.

#### 5.4.3 Type (F.2.1<5.4.3>)

- **Logical type:** the sub-package (`schema`, `engine`, `gui`) and the
  module.
- **Physical type:** a Python source module.
- The public classes and functions it contains are listed in RD1.

#### 5.4.4 Purpose (F.2.1<5.4.4>)

RD1's "Purpose" column (the module docstring's first sentence) and its
"SRS" column (the requirements traced to it).

#### 5.4.5 Function (F.2.1<5.4.5>)

What a component does is stated in its module docstring. RD1 quotes that
statement; the full text is in the source.

#### 5.4.6 Subordinates (F.2.1<5.4.6>)

The public classes and functions of each module, in RD1.

#### 5.4.7 Dependencies (F.2.1<5.4.7>)

The constraints on a component's use are its imports (RD1, "Uses" columns),
plus two rules:
- the Basilisk-free modules of SRS-D-03 must not import Basilisk at module
  level;
- GUI modules must not be imported by the engine or the schema (4.1).

#### 5.4.8 Interfaces (F.2.1<5.4.8>)

- **Control flow:** every component is a Python module, and execution
  enters by function call or method call and leaves by return or
  exception. As F.2.1<5.4.8>d allows, this is not repeated per component.
- **Asynchronous control flow:** exists only in two places:
  - Qt signals from the workers to the GUI (4.2);
  - Basilisk calling the tool's SysModels (`UpdateState`) once per step.
- **Data flow:** through call arguments and returns, typed by the
  dataclasses of `schema` (RD2) and the result types of `engine/results`
  (`ResultSet`, series, provenance).
- **Files:** the scenario JSON, the results CSV and the CCSDS messages
  (ICD).

#### 5.4.9 Resources (F.2.1<5.4.9>)

From their environment, the components need:

| Component | Needs |
|---|---|
| Simulation components (`engine/service`, `long_run`, `mission_engine`, `lifetime`, `monte_carlo`) | Basilisk 2.12.0; the SPICE kernels; for full accuracy, the Earth PCKs |
| GUI components | PySide6 and a display (or `QT_QPA_PLATFORM=offscreen`) |
| Everything else | numpy and the standard library; the bundled data files |

#### 5.4.10 References (F.2.1<5.4.10>)

Module docstrings cite the clauses, papers and Basilisk documentation they
implement; for example `engine/earth_orientation.py` cites
ECSS-E-ST-10-09C 5.4.9f. The references for the models are listed in
RD3 and in `USER_MANUAL.md`.

#### 5.4.11 Data (F.2.1<5.4.11>)

- **Scenario data structures:** defined in RD2, with each element's name,
  type, default (initial value) and unit or range. The structure follows
  the nesting of the dataclasses.
- **Data internal to a module:** its module-level constants (named, with
  units) and its private classes, documented in the source.

### 5.5 Internal interface design (F.2.1<5.5>)

The main internal interfaces:

| From → to | Data | Defined in |
|---|---|---|
| gui, cli → schema | `Scenario` (built, loaded, validated, saved) | RD2 |
| gui, cli → engine/service | `Scenario`; progress and cancellation callbacks → `ResultSet` | `engine/service.py` (`SimulationService.run_live`) |
| engine/service → engine/long_run | `Scenario`, callbacks → `ResultSet` (segments joined) | `engine/long_run.py` |
| engine/mission_engine → engine/service | a built simulation; `Command` list (`schema/command.py`) → `ResultSet` and report rows | `engine/mission_engine.py` |
| engine/service → engine/spaceweather | date span → records (observed, forecast, MSFC) | `engine/spaceweather.py` (`resolve`) |
| engine/service → engine/earth_orientation | → Earth PCK files and notes | `engine/earth_orientation.py` (`available_files`, `notes`) |
| engine/service ↔ planet_rotation, geodetic_atmosphere | Basilisk messages (`SpicePlanetStateMsgPayload`, `SCStatesMsgPayload`) | the two modules |
| engine/results → gui/results_widget, cli | `ResultSet`: series (time, columns, units, frame) and provenance | `engine/results.py` |
| engine/ccsds_odm ↔ schema, engine/results | `OdmMessage` ↔ `OrbitIC` and recorded states | `engine/ccsds_odm.py` |
| gui/run_worker → gui/main_window | Qt signals: progress, partial results, finished, failed | `gui/run_worker.py` |

RD1 gives the complete import map, with each module's package
dependencies, from which the interface map can be cross-checked. The data
elements are those of the dataclasses named.

## 6 Requirements to design components traceability (F.2.1<6>)

- **Forward (requirement → components):** RD1, "Forward traceability". The
  generator fails if an SRS requirement is not traced, or if a trace names
  a module that does not exist.
- **Backward (component → requirements):** the "SRS" column of RD1. The
  modules that trace to no requirement are listed there; they are support
  code.
- **Critical software:** category C is critical software (ECSS-Q-ST-80C
  3.2.8), and the whole tool is category C (decisions 1 and 10). The
  measures applied are in `dependability_safety_analysis.md` section 4.
  In the design they are:
  - the isolated workarounds (4.5);
  - the start-up version check;
  - the provenance record;
  - the warnings and plausibility checks;
  - the containment of runs in workers (4.2).
