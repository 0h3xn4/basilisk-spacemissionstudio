# SpaceMissionStudio: Software User Manual (SUM)

DRD: ECSS-E-ST-40C Annex H
Document: SMS-SUM, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft.
- The user documentation already exists:
  - `USER_MANUAL.md` (UM), the tutorial and reference for users;
  - `README.md` (RM), installation from source, features and the CLI.
- This SUM maps each DRD section to them and adds what they do not cover:
  - data files;
  - security;
  - error messages;
  - recovery.
- Its fitness for users is for users to judge (H01).

## 1 Introduction (H.2.1<1>)

This SUM is the entry point to the user documentation of SpaceMissionStudio
2.0.0. Users should read the UM; this document points to it section by
section and holds the information ECSS-E-ST-40C asks for that the UM does
not.

## 2 Applicable and reference documents (H.2.1<2>)

| Ref. | Document |
|---|---|
| UM | `USER_MANUAL.md` |
| RM | `README.md` |
| AD1 | ICD (`ICD.md`, `ICD_cli.md`): file formats and CLI |
| AD2 | CSD (`CSD.md`): frames, time scales, units |
| AD3 | Security analysis (`security_analysis.md`) |
| AD4 | `packaging/README.md`: installers |

## 3 Terms, definitions and abbreviated terms (H.2.1<3>)

UM section 12 (glossary) and the SRS terms.

## 4 Conventions (H.2.1<4>)

- **Menus and buttons:** in bold (**Run > Abort Run**).
- **Typed text and commands:** in `code`.
- **CLI syntax:** `spacemissionstudio <command> [arguments]`. Optional
  arguments are in brackets; AD1 lists every argument.
- **Units:** in each field's label or name: km, deg, s, days (AD2).

## 5 Purpose of the software (H.2.1<5>)

UM section 1.

The tool lets a mission analyst do the following without writing code:
- define spacecraft, orbits, ground stations and a mission sequence;
- simulate them with Basilisk, at validated accuracy (SVR);
- analyse the results: lifetime, delta-V and propellant budgets, passes,
  link budget, Monte Carlo;
- exchange orbits with other tools through CCSDS OPM, OMM and OEM.

## 6 Referenced documentation (H.2.1<6>)

**Files the software needs:**

| File | Location | Notes |
|---|---|---|
| Basilisk 2.12.0 and its data (SPICE kernels) | Python environment; Basilisk's data cache | Installed by the installer; runs never download. The **Data** tab lists every file (source, dates, SHA-256) and downloads only after asking |
| Space weather (CelesTrak SW-All, NASA MSFC prediction) | Bundled in the package; optional newer copy in `~/.cache/SpaceMissionStudio/` | Downloaded only when you agree (start-up prompt) |
| IERS-based Earth orientation files (NAIF PCKs) | `~/.cache/SpaceMissionStudio/earth_orientation/` or the installation's `share/` | Optional. Without them the Earth frame is less accurate and runs say so. `spacemissionstudio earth-orientation --fetch` |
| Vizard (optional) | Downloaded on request, or your own installation | 3-D view only |
| Scenario files (`.json`) | Where you save them | Your data |
| Results (`.csv`, `provenance.json`, `.oem`) | The output folder you choose | Your data |
| Log file | `~/.spacemissionstudio/logs/` | For problem reports |

**Security and privacy:**
- The tool sends nothing about you or your work anywhere.
- Downloads go only to the sources named above, and only when you agree.
- Scenario files can contain script blocks, which run code (9.9).

## 7 Software overview

### 7.1 Software application (H.2.1<7.1>)

- Install with the `.deb` (Linux) or the `.exe` (Windows) (UM section 2;
  AD4), or from source with `pip` (RM, "Getting started").
- The installer needs the internet once, to fetch Basilisk.
- No other manual operation is needed.

### 7.2 Software inventory (H.2.1<7.2>)

- **Hardware:** a PC (x86-64), with no special hardware.
  - Memory: not measured systematically (SRS-R-02). A five-year run
    recorded at the default interval used 452 MB (HISTORY.md).
  - Disk: the audit's environment, with Basilisk and the development
    tools, took 1.4 GB. Basilisk's kernels take about 100 MB (UM
    section 11), and the tool's data cache 42 MB.
  - A display for the GUI. Vizard benefits from a graphics card.
- **No FPGAs and no communications equipment.**

### 7.3 Software environment (H.2.1<7.3>)

```
  Operating system (Linux, Windows)
    Python 3.9+ virtual environment
      SpaceMissionStudio  --uses-->  Basilisk 2.12.0, numpy, sgp4, pyerfa, PySide6, plotly
      Vizard (optional, separate program)
```

### 7.4 Software organization and overview of operation (H.2.1<7.4>)

- **Window layout:** UM section 3:
  - left tabs **Load Scenario** and **Scenario Editor**;
  - right tabs **Results**, **Mission Dashboard**, **Mission Output**,
    **Data**, **Explain**.
- **States:**
  - **Editing:** everything available.
  - **Running:** the run controls are disabled and **Abort Run** is
    enabled.
  - **Degraded:**
    - without Basilisk, you can edit but not run (UM section 11);
    - without the Earth orientation files, runs are less accurate and
      say so;
    - without network access, everything works except downloads.

## 8 Operations manual set-up and use (H.2.1<8>)

- The tool has one role, the analyst, and no staffing.
- A typical session:
  1. Open a template or a scenario.
  2. Edit it.
  3. Check the **Explain** tab and the validation messages.
  4. Run.
  5. Inspect the results.
  6. Export, and run analyses.
- **Contingency:** abort a run (9.6); recover from errors (9.8).

## 9 Reference manual

### 9.1 Operational organisation (H.2.1<9.1>)

Not applicable: SpaceMissionStudio is a desktop tool, not an operations
site. It has no schedule, operational profile or site personnel.

### 9.2 Installation procedures (H.2.1<9.2>)

- **Installers:** UM section 2; AD4.
  - No account or password is needed.
  - Installing the `.deb` needs administrator rights (apt). The Windows
    installer needs the rights its wizard asks for.
- **Configuration:** none is needed.
  - Data files are fetched on request (section 6).
  - The Vizard path is remembered after the first launch.
- **Removal:**
  - Linux: `sudo apt remove spacemissionstudio`.
  - Windows: **Settings > Apps**.
  - Your scenario files, results and the `~/.cache/SpaceMissionStudio/`
    directory are not removed. Delete them by hand if you want.
- **Checking a download:** compare it with the published `SHA256SUMS`
  (`sha256sum -c SHA256SUMS`).

### 9.3 Getting started (H.2.1<9.3>)

UM section 4 ("Your first simulation, in five minutes").

**Check-list when something does not start:**
- Is Basilisk installed? **Help > About** shows the versions.
- Is a display available (GUI)?
- Read the log file (section 6).

### 9.4 Access and security features (H.2.1<9.4>)

The tool has no passwords, accounts or access levels. It runs with your
operating-system rights. See 9.9.

### 9.5 Normal operations (H.2.1<9.5>)

| Task | UM section |
|---|---|
| Choose a template, tweak it | 4, 5 |
| Edit a scenario | 6 (each field has a tooltip with its meaning and unit) |
| Read the results; plots, epoch and elapsed time | 7 |
| Save and open | 8 |
| Vizard | 9 |
| Monte Carlo | 10 |
| Lifetime, budgets, launch delays, altitude trade, long runs | 11 |
| CLI | RM; AD1 (`ICD_cli.md`) |
| CCSDS import and export | AD1 (ICD 5.3.4); `ccsds-import`, `ccsds-export`, `run --oem` |

### 9.6 Normal termination (H.2.1<9.6>)

- **Close the window:** the tool refuses to close while a run is in
  progress. Abort the run first.
- **Run > Abort Run:** stops a run at the next checkpoint and keeps the
  results so far. The status says "cancelled".
- **CLI:** a finished command prints its result and returns 0 (AD1).

### 9.7 Error conditions (H.2.1<9.7>)

The common error conditions are in 10.5. An error is reported in a dialog
or at the field in the GUI, and on standard error with a non-zero exit code
in the CLI. An error never closes the application.

### 9.8 Recover runs (H.2.1<9.8>)

- **Unsaved edits:** an autosave keeps them. After a crash the tool offers
  to recover them at the next start.
- **A failed run:** the message says why. The results up to the failure
  are kept. Fix the cause (10.5) and run again.
- **Damaged data files:**
  - `spacemissionstudio earth-orientation --rollback` restores the
    previous Earth files;
  - a space-weather file that does not cover a run is refused, naming the
    range, and the bundled data still works.

### 9.9 Secure installation and operation (H.2.1<9.9>)

- **Scenario files from others:** may contain **script blocks**, which run
  Python with your rights.
  - The tool asks before running them and shows their code (GUI). In the
    CLI it needs `--allow-scripts`.
  - Run script blocks only if you trust the file and have read the code.
  - Conditions (`if`/`while`) cannot run code (AD3, S-02).
- **Monte Carlo archives:** Basilisk writes them as pickle files. Do not
  load archives you did not create (AD3, S-04).
- **Vizard live streaming:** the tool opens no network port. Vizard
  listens on port 5556 while a run streams, and the simulation connects
  to it.
  - To see whether Vizard listens on all interfaces, run
    `netstat -an | grep 5556` (Linux, macOS) or
    `netstat -an | findstr 5556` (Windows) during a live run.
  - On an untrusted network, block port 5556 in your firewall, or use a
    save file instead (AD3, S-06).
- **Downloads:**
  - These happen only when you agree, and only from the sources in
    section 6.
  - The Vizard download's SHA-256 is shown and recorded in
    `download.json` (AD3, S-05).

## 10 Reference manual: commands and messages

### 10.1 Quick-reference guide (H.2.1<10.1>)

| Action | GUI | CLI |
|---|---|---|
| Validate | automatic while editing | `spacemissionstudio validate FILE` |
| Run | **Run > Run Simulation** | `spacemissionstudio run FILE --out-dir DIR [--oem] [--allow-scripts]` |
| Abort | **Run > Abort Run** | Ctrl+C |
| Lifetime | **End of life** panel | `spacemissionstudio lifetime FILE` |
| Budget | **Budget** tab | `spacemissionstudio budget FILE` |
| Earth orientation files | start-up prompt | `spacemissionstudio earth-orientation [--fetch \| --import FILES \| --rollback]` |
| CCSDS | – | `ccsds-validate`, `ccsds-export`, `ccsds-import` |

### 10.2 Help method (H.2.1<10.2>)

- Every field has a tooltip: meaning, unit, range.
- Validation messages name the field.
- The **Explain** tab summarises what the scenario models.
- `spacemissionstudio <command> --help` lists the arguments.
- UM section 11 answers common questions.

### 10.3 Screen definitions and formats (H.2.1<10.3>)

- The window opens at 1400 × 850 and is resizable; the tabs and panels
  scroll.
- No minimum screen size has been specified or tested.
- Screen layout: UM section 3, with screenshots in `docs/images/`.

### 10.4 Commands and operations (H.2.1<10.4>)

The CLI command language is in AD1 (`ICD_cli.md`, generated from the CLI
itself). The mission-sequence commands are in UM section 6 and RM:
- `propagate`, `maneuver`, `lambert_transfer`, `assignment`, `report`;
- `if`, `while`, whose conditions use the subset of 9.9;
- `script_block`.

### 10.5 Error messages (H.2.1<10.5>)

| Message (beginning) | Meaning | Action |
|---|---|---|
| `INVALID: ... <field> ...` / a red field | A value is out of range or inconsistent | Correct the named field |
| `malformed scenario structure (... unexpected keyword argument 'x')` | The file has a field this version does not know | Remove the field, or use the version that wrote it |
| `Basilisk is not installed/built` | No simulation engine (exit code 2) | Install Basilisk 2.12.0 (UM section 2) |
| `Basilisk <v> ... results are not covered by its verification` | A Basilisk version other than 2.12.0 | Install 2.12.0, or accept unverified results |
| `Earth orientation: IAU rotation model, no IERS data installed` / `~160 m/day position error` | No IERS-based Earth files | `spacemissionstudio earth-orientation --fetch` |
| `no real space-weather data for <day>` | The run's dates are outside the data | Shorten the run, or fetch newer data |
| `script_block runs unrestricted Python ... --allow-scripts` | The scenario has script blocks | Read the code; run with consent (9.9) |
| `... is not allowed in a condition` | A condition uses an attribute or a call | Rewrite it with names, indexing and operators |
| `while loop exceeded ... iterations` | The condition never became false | Fix the condition |
| `re-entered: below 100 km` | The spacecraft re-entered; the run stopped | Expected for a decaying orbit; the results so far are kept |
| `run failed: ...` (exit code 3) | Basilisk or the engine failed | Read the message and the log; report it with the log if unclear |
| CCSDS `error: ... (CCSDS 502.0-B-3 <clause>)` / `warning: ...` | The message breaks a 502.0-B-3 rule | Fix the message; warnings can be accepted |

Other messages explain themselves and name what to change. A full
catalogue of every message has not been compiled; that is an open item of
this SUM.

## 11 Tutorial

### 11.1 Introduction (H.2.1<11.1>)

The UM combines a tutorial (sections 3 to 5) with reference material
(sections 6 to 12) for novices and experts.

### 11.2 Getting started (H.2.1<11.2>)

UM section 1, "What is SpaceMissionStudio?"

### 11.3 Using the software on a typical task (H.2.1<11.3>)

UM section 4, with screenshots: load a template, run it, read the results.

## 12 Analytical index (H.2.1<12>)

The SUM and the UM are each under 40 pages; the UM's table of contents
serves as the index.
