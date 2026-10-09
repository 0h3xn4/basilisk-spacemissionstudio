# SpaceMissionStudio

> **AI authorship disclosure.** SpaceMissionStudio was entirely conceived,
> written, tested, and documented by Claude (Anthropic's AI model), via
> Claude Code -- every line of application code, every test, this README,
> [`HISTORY.md`](HISTORY.md)'s entire development log, and every commit
> and pull request in this repository's history. No human wrote any of
> it directly. A human reviewed Claude's output, decided what to build
> next, and approved what got merged -- but did not author the code or
> prose themselves. Stated here plainly, not as a footnote, because
> anyone evaluating this project should know that going in.

A standalone, GUI-based mission-analysis application for Linux and
Windows 11, using the Basilisk astrodynamics framework (AVS Lab,
University of Colorado Boulder) as its sole simulation/dynamics engine.
Think "STK/FreeFlyer-lite" -- every capability maps to a specific
Basilisk module, or is explicitly flagged as custom/out-of-scope, never
fabricated.

**Status: v2.0.0**. See "Version 2.0.0" below for what's new in this
release, "Capabilities" for the full current feature set, and
[`HISTORY.md`](HISTORY.md) for the full phase-by-phase development log
this README used to carry inline (every feature's design rationale, every
bug found and fixed, the full crash-investigation writeups) -- nothing
was deleted, it just moved out of the way of a README someone installing
this for the first time should actually be able to read.

## Start here

| You want to | Read |
|---|---|
| Install it and run a first simulation | [`GETTING_STARTED.md`](GETTING_STARTED.md): installers, one-command script or `pip`, step by step for Linux and Windows, plus troubleshooting |
| Learn to use the app (no programming or spacecraft background needed) | [`USER_MANUAL.md`](USER_MANUAL.md), also in the app under **Help > User Manual** (`F1`) |
| Learn by example | The 25 [template missions](spacemissionstudio/scenarios/templates/README.md), from a single circular orbit to complete missions, with a suggested order |
| Start your own mission | Templates **22** (a realistic satellite, orbit only) and **23** (a complete small satellite with hardware, radio link and Mission Sequence) |
| Script it from Python | [`examples/`](examples/README.md): build a scenario, run templates, a Mission Sequence, a parameter sweep, Monte Carlo results |
| Know what is verified, and how | "Verification status" below, and [`compliance/`](compliance/) |
| Know why something is the way it is | [`HISTORY.md`](HISTORY.md), the development log |

## Getting started

Quick version, from a checkout, on Linux (Windows: the same commands in
PowerShell, with `.venv\Scripts\Activate.ps1`):

```bash
cd SpaceMissionStudio
python3 -m venv .venv && source .venv/bin/activate
pip install "bsk[all]==2.12.0"          # Basilisk, the verified version, as a prebuilt wheel
pip install -e ".[gui]"                 # SpaceMissionStudio and its GUI (".[dev,gui]" adds the test tools)
spacemissionstudio kernels-status       # fetches the reference data once (~116 MB) and checks it
spacemissionstudio gui                  # opens on the Load Scenario tab: pick 22, Open Template, Ctrl+R
```

There are also installers that need no typing: a `.deb` for Linux
(`packaging/build_deb.sh`) and an Inno Setup `-setup.exe` for Windows
(`packaging/windows/spacemissionstudio.iss`), and one-command install
scripts (`packaging/install.sh`, `packaging/install.ps1`).
[`GETTING_STARTED.md`](GETTING_STARTED.md) covers all of them, how to check
the installation, and what to do when something fails.

What has been run where: the Linux `.deb`, `install.sh` and the `pip`
path above were run end to end on Linux with a real Basilisk build
(`packaging/README.md` says exactly what and when). The Windows
installer, `install.ps1` and the PowerShell commands follow Basilisk's
own documented Windows install path but have not been run on a real
Windows machine; please report anything that goes wrong. macOS has
Basilisk wheels too, but SpaceMissionStudio has not been tried there.

## Verification status

* **Everything Basilisk-independent** (`spacemissionstudio/schema/`,
  `engine/spaceweather.py`, `engine/results.py`, `engine/link_budget.py`,
  `engine/constellation.py`, `engine/spacecraft_templates.py`,
  `engine/propellant_bookkeeping.py`, `engine/time_system.py`,
  `engine/orbit_design.py`, `engine/scenario_explainer.py`, `engine/scenario_checks.py`, `cli.py`, and
  the entire `spacemissionstudio/gui/` package) has no Basilisk import
  and is fully exercised either way -- `pytest tests/` runs every test
  not marked `requires_basilisk` without Basilisk installed (see
  "Running the tests" below).
  That includes the PySide6 GUI: built, run headless, and driven with
  `pytest-qt` for real -- every form field, every menu action, every
  dialog -- not asserted about in the abstract.
* **Everything Basilisk-dependent** (`kernels.py`,
  `service.py`, `fsw.py`/`vizard.py`, `monte_carlo.py`,
  `orbit_maintenance.py`, `mission_engine.py`) has been confirmed
  against a real `pip install "bsk[all]"` Basilisk build, including a
  **real, full multi-day end-to-end run**: a real user ran the
  `05_formation_flying_phasing.json` template (station-keeping +
  phasing-keeping + live Vizard streaming, both active on the same
  spacecraft) to 100% completion -- the full 7 simulated days, no
  errors. Getting there involved finding and fixing a real,
  previously-unreproducible crash (root-caused with a real `gdb`
  session down to a dangling-pointer bug in `engine/vizard.py`'s Vizard
  live-data panels -- full story in `HISTORY.md`).
* **This development sandbox** (where most of this project's code was
  written) has no route to the NAIF SPICE kernel host, so a handful of
  things could only be confirmed correct up to that point here, not run
  end-to-end in-sandbox -- not a project limitation, just this one
  sandbox's own network policy. Anything with that specific gap says so
  in its own docstring/module comment.
* **Packaging.** The scriptable install path
  (`packaging/build_wheel.sh`/`install.sh`, including the
  Basilisk-wheel-vendoring path) AND the real, double-click Linux
  installer (`packaging/build_deb.sh`'s `.deb` package) were both fully
  verified end-to-end on Linux -- a real Basilisk build installed for
  real, confirmed with its own `printBuildInfo()`, and hundreds of this
  project's own Basilisk-dependent tests genuinely passing against it
  (not auto-skipping) when run from the installed copy. Their Windows
  counterparts (`build_wheel.ps1`/`install.ps1`, and the Inno Setup
  installer `packaging/windows/spacemissionstudio.iss`, all new for 1.0.0)
  were written against the same already-verified logic and Basilisk's
  own documented Windows install path, but have not been run on a real
  Windows 11 machine (none has ever been available in this development
  sandbox) -- see `packaging/README.md` for exactly what's verified
  where, and please report anything that doesn't work as documented.
  That end-to-end packaging pass predates `results_widget.py`'s
  matplotlib-to-Plotly migration (see the "GUI & CLI" bullet under
  "Capabilities" below): the plots now render inside a `QWebEngineView`,
  which -- unlike plain PySide6 widgets, matplotlib included -- embeds a
  full Chromium renderer with its own system-library footprint (things
  like `libnss3`/`libatk-bridge2.0-0`/`libgbm1`, beyond the
  `libegl1`/`libopengl0`/`libxcb-cursor0` already called out below for
  plain PySide6). This development sandbox's container already had
  everything `QtWebEngineProcess` needs (confirmed with `ldd` --
  nothing reported missing) and the full headless `pytest-qt` suite
  exercises real `QWebEngineView` instances, but that is not the same
  as confirming a fresh install on a minimal target machine (the `.deb`
  postinst's or the Windows installer's own actual end user); if
  `spacemissionstudio gui` starts but the results plot stays blank, that is
  the first thing to check. Unrelated to that migration: `build_deb.sh`
  itself was re-run for the 2.0.0 release and still produces a valid,
  installable `spacemissionstudio_2.0.0_all.deb` via `dpkg-deb` (it reads
  `spacemissionstudio.__version__` rather than hardcoding a version string),
  but the full real-Basilisk install chain this paragraph describes was
  not independently re-run against that specific 2.0.0 artifact -- only
  the unchanged underlying install logic has been.

## Capabilities

What's actually implemented, grouped by concern (full design rationale
and the order each landed in: `HISTORY.md`).

**Scenario model & data** -- a versioned, human-readable JSON format
(spacecraft, orbit ICs in three forms -- classical elements with true or
mean anomaly, Cartesian, TLE --, gravity, ground stations, space
weather, sim settings, Monte Carlo dispersions, a GMAT/FreeFlyer-style
**Mission Sequence**), hand-written validation with specific error
messages, a schema-migration registry, and reference-integrity checking
(rename a spacecraft and every reference to it updates atomically;
deleting one that's still referenced is refused, listing exactly what
references it). No third-party schema library.

**Orbital dynamics & propagation** -- central-body point-mass or Earth
spherical-harmonics gravity plus third-body point-mass perturbers,
atmospheric drag (Earth-only; a choice of NRLMSISE-00 or a simple
exponential model -- see `SpaceWeatherConfig.atmosphere_model`'s own
docstring for why not Jacchia-Roberts too: Basilisk has no such model)
and SRP (per spacecraft, on that spacecraft's own "Orbit / mass" tab),
a selectable integrator (`euler`/`rk2`/`rkf45`/`rkf78`), and osculating
Keplerian elements computed and exported alongside inertial
position/velocity at every sample -- plus, when a real J2 term is
actually modeled (Earth with spherical-harmonics degree >= 2), MEAN
(first-order-J2, osc -> mean) elements alongside the osculating ones,
via Basilisk's own `orbitalMotion.clMeanOscMap` (the same tool its
`meanOEFeedback` FSW module uses -- not a bespoke implementation).
NRLMSISE-00 drag takes its solar activity at one of three levels:
nominal (NASA MSFC's 50th-percentile prediction), conservative (its 95th
percentile, ESA AD10's operations case) or low (its 5th). The
conservative case follows the predicted solar cycle; it is not a
constant.

**Attitude, sensors & actuators** -- every `fsw_mode` maps to a real
Basilisk FSW module chain (attitude nav/guidance/control), idealized or
real reaction-wheel actuation, and star tracker/IMU/coarse-sun-sensor/
magnetometer sensors (magnetometer is Earth-only). A `"thermal"` sensor
(`sensorThermal.SensorThermal`) models the real temperature of any
flat-plate component -- radiative absorption/emission driven by the
actual simulated attitude and (when shared with a power/eclipse-aware
spacecraft) real eclipse state, plus an optional internal power draw --
with its own measurement noise/bias/fault layer
(`tempMeasurement.TempMeasurement`). `"reaction_wheel"` actuators
separately gain an OPTIONAL per-wheel motor-thermal model
(`motorThermal.MotorThermal`, motor inefficiency/friction heat vs.
ambient dissipation) via the `motor_thermal_*` params. See template '20'.

**Mission planning** -- a GMAT/FreeFlyer-inspired Resources / Mission
Sequence / Output architecture: `propagate` (duration, epoch, or
event stop conditions: periapsis, apoapsis, or the start/end of the next
ground-station pass), `maneuver` (impulsive
delta-V, inertial/VNB/RTN), `lambert_transfer` (solves for the
impulsive delta-V that reaches a target position after a given time of
flight, via Basilisk's own `lambertPlanner`/`lambertSolver`/
`lambertValidator`), `assignment`, `report`, `if`/`while`
conditionals, and `script_block` commands, run by a real execution
engine (`engine.mission_engine.MissionEngine`) with a dedicated GUI
editor and output console.

**Mission analysis** -- ground-station access analysis (has-access,
slant range, elevation, azimuth per station/spacecraft pair), a real
power budget (solar panel/battery/eclipse, driven by actual simulated
attitude and eclipse state, not a flat duty cycle), a downlink RF
link-margin estimate evaluated against real simulated slant range, and
Monte Carlo batch analysis (`Basilisk.utilities.MonteCarlo`: dry mass,
attitude, orbital elements, inertia, body rate, drag and SRP
coefficients), shown in the GUI's Monte Carlo tab (each run, the spread
along, across and out of the orbit, and a table of what each run drew).

**Automatic Sun-pointing / ground-station-pointing attitude switching** --
`SpacecraftConfig.comms_pointing` (`engine.fsw.build_comms_pointing`): a
small arbitrator `SysModel` that holds a spacecraft Sun-pointing (for
solar-panel power generation) by default, and switches it to point a
body-fixed antenna boresight at a named ground station instead, entirely
driven by that station's own REAL `groundLocation.GroundLocation` access
state -- never a manually-specified time window. Only the attitude
REFERENCE switches; the spacecraft's own integrated attitude state is
untouched, so the existing closed-loop `mrpFeedback` controller physically
slews across the transition rather than snapping instantly. An optional
`comms_power_w` draws extra battery power only while actually
ground-station-pointing, and `RFLinkConfig.antenna_beamwidth_deg` (when
set) feeds the spacecraft's own, actually-achieved pointing error into
`engine.link_budget`'s margin calculation as a parabolic-pattern
antenna-pointing-loss term -- so the link margin, gated on both real
access AND the spacecraft having actually switched modes, can show a
real "geometrically visible but not yet actually linked" period right at
each transition. See template '19' (below).

**Orbit maintenance** -- altitude/semi-major-axis station-keeping, GEO
east-west (longitude box) and north-south (inclination limit)
station-keeping measured in Earth's own rotating frame, and
constellation-wide phasing maintenance, both with real delta-V/
propellant bookkeeping (rocket-equation mass depletion fed back into
simulated spacecraft mass every tick) and eclipse-gated burns; a
constant-frame (VNB/RTN) continuous-thrust maneuver mode; a
Walker-pattern constellation generator (satellite count, planes,
phasing factor, altitude, inclination -> a full set of spacecraft with
pre-computed orbital elements); a **Generate phasing formation...**
wizard (`engine.formation`) that turns an existing chief spacecraft plus
a desired Radial/Transverse/Normal (Hill-frame) offset at epoch into a
new follower spacecraft with `phasing_keeping`/`station_keeping`
pre-wired -- the along-track (T) component becomes the actively-held
separation target; radial/cross-track (R/N) only set the follower's
starting geometry, since the phasing controller has no radial/
cross-track control authority (the wizard says so up front).

**Fuel tank** -- real propellant depletion for `"thruster"` actuators
(`SpacecraftConfig.fuel_tank`, `engine.fsw.build_fuel_tank`): Basilisk's
own `fuelTank` state effector (`FuelTankModelUniformBurn`), tied to the
thruster hardware so it reads the SAME mass-flow rate the thruster
itself already computes (`mDot = F / (steadyIsp * g0)`) -- a materially
different, more physical mechanism than the orbit-maintenance
bookkeeping above (which is a hand-rolled Python estimate specific to
station-keeping/phasing/constant-thrust burns); this one is Basilisk's
own effector, including the resulting center-of-mass shift as
propellant depletes.

**Vizard visualization** -- live-stream or `.bin` playback file, an
Earth-centered default camera view with orbit trace lines, live
data panels (battery charge, station-keeping propellant remaining,
delta-V used -- station-keeping and phasing-keeping reported as separate
panels, since both draw from one shared tank -- for a phasing formation,
the real chief/follower offset broken out into Radial/Transverse/Normal
panels (the same R/T/N terms the phasing-formation wizard itself uses,
not an abstract single number), ground-station access-window indicators,
and -- for a `comms_pointing` spacecraft -- a pointing-error bar plus
"Mode"/"Link status" badges mirroring the Mission Dashboard's own live
GUI telemetry -- all driven by real, already-simulated values, not
static snapshots, with Vizard's own native live current/max readout on
every panel), custom 3D models per spacecraft (purely cosmetic), and a **Launch
Vizard** action that starts the external application itself (offering
to download AVS's own pre-built binary automatically if none can be
found -- see "Running the CLI" above), not just configures what feeds
it.

**Reusable starting points** -- four spacecraft "bus" templates
(100 kg ESPA-class, 150 kg microsatellite, 300 kg and 500 kg small
satellites) and
twenty-five complete example scenarios: most cover one concept each,
two integrate several, and four are starting points for your own mission
(see "Template missions" below). Five Python scripts in `examples/` use
the same layer from code.

**Safe cancellation** -- **Abort Simulation** cooperatively cancels an
in-progress run (or Monte Carlo batch, or Mission Sequence) between
simulation chunks or commands, keeping whatever partial results were
already produced -- never a forced kill that could leave Basilisk's C++
state mid-mutation.

**Long runs and end of life** -- runs of up to about 10 years, chained
past Basilisk's ~104-day limit, with a "Record every" setting to keep
them in memory; and an **End of Life** tab (and `spacemissionstudio
lifetime`) estimating when a spacecraft re-enters, with or without a
deorbit burn, checked against the 5- and 25-year disposal rules. The
estimate agrees with full Basilisk decay runs to within ~2% in seconds.

**Propellant budgets (ESA AD10 style)** -- a Budget tab and
`spacemissionstudio budget`: delta-V and propellant per mission phase with
the guideline's margins, residuals and iteration, simulated orbit control
taken from the last run (or estimated from the drag), the disposal burn
sized for a 5-year lifetime, and a launch-delay sweep for launches up to
5 years late (`budget --launch-delays`), and an altitude trade of that
sweep against the tank (`budget --altitudes`, in parallel processes); solar activity from NASA MSFC's
prediction at the 95th/50th percentile. Templates use AD10's operations
drag coefficient, 3.0.

**GUI & CLI** -- a full PySide6 desktop shell (scenario editor,
Monte Carlo, live progress feedback, a real visual theme/icon/
toolbar) and an equivalent headless CLI (`spacemissionstudio validate/run/
monte-carlo/lifetime/budget/kernels-status/generate-constellation/gui`), both built on
the exact same `schema`/`engine` layer -- neither is a thin wrapper
around the other. Result plots are Plotly figures (a validated,
colorblind-safe categorical palette; a unified hover tooltip; plain
decimal axis ticks -- never matplotlib's scientific/offset notation)
rendered in an embedded `QWebEngineView`, with the epoch/elapsed-time
x-axis toggle and per-series km-unit conversion described above still
applying unchanged; see `results_widget.py`'s own module docstring for
why `QWebEngineView` over a static image, and "Verification status"
above for this migration's one open packaging caveat. A "Mission
Dashboard" tab (`mission_dashboard_widget.py`) shows the same live run
as a set of grouped status readouts (operating state, attitude, power,
RF link) instead of a plot, for a `comms_pointing`-configured
spacecraft -- fed from the exact same `RunWorker.progress`/
`finished_ok`/`cancelled` signals the Results tab already uses, so it
updates live during a run with no extra plumbing.

## Repository layout

```
SpaceMissionStudio/
  README.md                          -- this file
  GETTING_STARTED.md                 -- install, check and first run, step by step, with troubleshooting
  HISTORY.md                         -- the full phase-by-phase development log
  USER_MANUAL.md                     -- end-user walkthrough of the GUI (screenshots in docs/images/)
  examples/                          -- Python scripts using the schema/engine layer (README.md lists them;
                                        tests/test_examples.py runs each)
  LICENSE                            -- ISC license (bundled IBM Plex fonts: SIL OFL 1.1,
                                        spacemissionstudio/gui/assets/fonts/OFL.txt)
  pyproject.toml                     -- packaging metadata, pytest config, CLI entry point
  docs/
    images/                          -- USER_MANUAL.md's own screenshots
  spacemissionstudio/
    cli.py                           -- batch/headless CLI + GUI launcher
    logging_setup.py                 -- file-backed logging (so a GUI crash leaves more than one bare line)
    plot_categories.py               -- per-series display metadata (title, axis label, unit, display-only conversion)
    schema/
      scenario.py                    -- Scenario and friends, validation, save/load
      migrations.py                  -- schema-version migration registry
      command.py                     -- Phase 6: Command (Mission Sequence), collecting validate()
      references.py                  -- Phase 6: reference-integrity (find/rename) for resources + commands
      validation.py                  -- Phase 6: validate_all() -- fully-collecting scenario-wide validation
    engine/
      time_system.py                 -- UTC epoch -> SPICE time string for Basilisk (locale-independent; no Basilisk import)
      kernels.py                     -- SPICE kernel fetch/status (needs Basilisk; network only at install time/startup prompt)
      spaceweather.py                -- real CelesTrak data (bundled or local file) resolve+validate (no network); fetch() is opt-in only (no Basilisk needed)
      results.py                     -- TimeSeries/ResultSet, CSV export (no Basilisk needed)
      service.py                     -- SimulationService (needs Basilisk)
      fsw.py                         -- Phase 2: attitude nav/guidance/control/actuation chain (needs Basilisk)
      vizard.py                      -- Phase 2: Vizard integration (needs Basilisk, imported lazily)
      monte_carlo.py                 -- Phase 3: Basilisk.utilities.MonteCarlo bridge (needs Basilisk)
      monte_carlo_results.py         -- a batch's pickle-free summary (batch_results.npz/.json) and its spread (no Basilisk needed)
      link_budget.py                 -- Phase 4: downlink RF link-margin estimate (no Basilisk needed)
      device_catalog.py              -- real, sourced, European-manufactured sensor/actuator device presets for gui/sensor_actuator_editor.py (no Basilisk needed)
      orbit_maintenance.py           -- Phase 4/5: station-keeping + phasing-keeping + constant-frame-thrust controllers, delta-V/propellant bookkeeping (needs Basilisk)
      geo_station_keeping.py         -- GEO east-west (longitude box) and north-south (inclination) station-keeping (needs Basilisk)
      propellant_bookkeeping.py      -- Phase 5: shared per-tick mass/propellant delta math (no Basilisk needed)
      constellation.py               -- Phase 4: Walker-pattern constellation generator + SeparationSchedule (no Basilisk needed)
      formation.py                   -- phasing-formation generator: chief + Hill-frame (R/T/N) offset -> follower spacecraft (needs Basilisk)
      spacecraft_templates.py        -- Phase 5: reusable spacecraft "bus" templates (no Basilisk needed)
      facets.py                      -- flat-plate facet models (box + solar array) for attitude-dependent drag/SRP (no Basilisk needed)
      mission_engine.py              -- Phase 6: MissionEngine -- walks mission_sequence against a SimulationService (needs Basilisk)
      orbit_design.py                -- Sun-synchronous orbit design helpers (sun_synchronous_inclination_deg/raan_for_ltan_deg) -- Basilisk-free
      scenario_explainer.py          -- explain(scenario) -> a structured, always-current "recipe" summary (stat tiles/badges/table) -- Basilisk-free
      scenario_checks.py             -- pre-run checks: ground-station pass prediction from the initial orbits, and warnings for setups that can't work as configured -- Basilisk-free
    gui/
      app.py                         -- QApplication entry point
      theme.py                       -- Phase 5: app-wide QSS stylesheet + palette
      assets/                        -- SVG glyphs: combo/spin arrows, check marks (theme.py) + toolbar line icons (icons.py)
      widgets.py                     -- PreciseDoubleSpinBox (stores full precision, not just its display decimals) + exact_number_text()
      autosave.py                    -- crash-recovery autosave of in-progress scenario edits
      feedback.py                    -- toast notifications + inline (per-field) validation highlighting
      badges.py                      -- colored pill/badge QLabel styling helper, shared by mission_dashboard_widget.py and scenario_explainer_widget.py
      icons.py                       -- Phase 5: procedurally-drawn app icon + toolbar_icon() for the toolbar SVGs
      main_window.py                 -- MainWindow: File/Run/Help menus + toolbar, ties everything together
      load_scenario_widget.py        -- "Load Scenario" tab: built-in template picker + browse-for-a-file
      template_wizard.py             -- "Customize: <template name>..." guided wizard spec registry + dialog
      scenario_editor.py             -- the full scenario form + live validation
      mission_sequence_editor.py     -- Phase 6: mission_sequence tree editor (Command Add/Edit/Remove/nesting)
      mission_output_widget.py       -- Phase 6: "Mission Output" tab (report values as a quantity x report table) + CSV export
      propagation_setup_dialog.py    -- Phase 5: gravity/perturbations + integrator + space weather, one dedicated window
      spacecraft_editor.py           -- spacecraft list + add/edit/remove dialog (tabbed: orbit, sensors/actuators, FSW, power/propulsion/link budget)
      sensor_actuator_editor.py      -- Phase 2: generic sensor/actuator list + add/edit/remove dialog, with a "select from catalog" picker (engine/device_catalog.py) alongside the fully custom editor
      vizard_dialog.py               -- Phase 2: "enable Vizard for the next run" dialog
      vizard_launcher.py             -- find/launch the external Vizard application (no Basilisk needed)
      startup_fetch_dialog.py        -- startup prompt to fetch cached support data/Vizard when missing (no Basilisk needed)
      monte_carlo_editor.py          -- Phase 3: Monte Carlo settings + dispersion list editor
      monte_carlo_results_widget.py  -- "Monte Carlo" tab: a batch's tiles, per-run plots and run table
      ground_station_editor.py       -- ground station list + add/edit/remove dialog
      orbit_ic_widget.py             -- classical-elements (true/mean anomaly)/Cartesian/TLE orbit editor
      constellation_dialog.py        -- Phase 4: "Generate Walker constellation" dialog
      phasing_formation_dialog.py    -- "Generate phasing formation..." dialog
      spacecraft_template_dialog.py  -- Phase 5: "New from template" picker dialog
      data_panel_widget.py           -- Data tab: every reference data file; consented downloads, import, rollback
      help_dialog.py                 -- Help: the bundled user manual and keyboard shortcuts
      results_widget.py              -- Plotly results plot (QWebEngineView) + CSV export + save-plot-as-PNG
      flow_layout.py                 -- wrapping chip layout (the Results tab's "Suggested" series)
      mission_dashboard_widget.py    -- "Mission Dashboard" tab: live operating-state/attitude/power/RF-link telemetry for a comms_pointing spacecraft
      scenario_explainer_widget.py   -- "Explain" tab: renders engine/scenario_explainer.py's output as stat tiles/badges/a per-spacecraft table, live-updated from ScenarioEditorWidget.changed
      formation_diagram_widget.py    -- QPainter-drawn along-track formation-geometry diagram (target separation + trigger/restore tolerance bands) for the Explain tab
      run_worker.py                  -- SimulationService/Monte Carlo on a background QThread
    scenarios/
      two_body_validation.json       -- the Phase 0 validation scenario
      templates/                     -- education/starter-template scenarios -- see that directory's own README
        README.md                    -- the template catalog: what each one teaches, how to open/run one
        01_two_body_circular_orbit.json
        02_elliptical_orbit_with_perturbations.json
        03_geo_station_keeping.json
        04_walker_constellation.json
        05_formation_flying_phasing.json
        06_attitude_pointing_basic.json
        07_attitude_pointing_with_adcs_hardware.json
        08_mission_sequence_orbit_raise.json
        09_monte_carlo_dispersion_analysis.json
        10_gravity_gradient_torque.json
        11_thruster_attitude_control.json
        12_reaction_wheel_momentum_dumping.json
        13_magnetic_torque_rod_momentum_management.json
        14_css_sun_heading_estimation.json
        15_celestial_body_pointing.json
        16_lambert_transfer.json
        17_fuel_tank_depletion.json
        18_leo_station_keeping.json
        19_sun_pointing_comms_link.json
        20_thermal_simulation.json
        21_disturbance_torques.json
        22_starter_first_leo_satellite.json        -- starting points for your own mission (22-23)
        23_starter_complete_small_satellite.json
        24_formation_mean_element_control.json     -- 05 under Basilisk's meanOEFeedback
        25_monte_carlo_orbit_and_drag_dispersions.json
  scripts/
    _generate_templates.py            -- regenerates scenarios/templates/*.json from schema dataclasses (not installed/imported elsewhere)
    _template_descriptions.py         -- the templates' user-facing descriptions
    sync_help.py                      -- copies USER_MANUAL.md and its images into the package for Help > User Manual
  packaging/                          -- build_wheel.sh/.ps1, install.sh/.ps1, .desktop entry (Linux) -- see packaging/README.md
    build_deb.sh                     -- builds the real, double-click Linux .deb installer
    build_wheel.sh / build_wheel.ps1 -- build a plain, platform-independent wheel (Linux/Windows)
    install.sh / install.ps1         -- venv + Basilisk + SpaceMissionStudio install script (Linux/Windows)
    spacemissionstudio.desktop.in    -- Linux desktop-entry template (filled in by build_deb.sh)
    deb/                              -- .deb package skeleton (DEBIAN/control.in + postinst/prerm/postrm, desktop entry, copyright)
    windows/                          -- the real Windows installer wizard
      spacemissionstudio.iss              -- Inno Setup script -> spacemissionstudio-2.0.0-setup.exe
      bootstrap_env.ps1              -- venv + Basilisk + SpaceMissionStudio install step the installer runs
  tests/
    conftest.py                      -- requires_basilisk / requires_gui auto-skip markers
    test_scenario_schema.py
    test_command.py                    -- Phase 6
    test_references.py                 -- Phase 6
    test_validation.py                 -- Phase 6
    test_migrations.py                 -- schema-version migration registry round-trips
    test_spaceweather.py
    test_results.py
    test_link_budget.py              -- Phase 4
    test_device_catalog.py           -- real, sourced sensor/actuator device catalog, no Basilisk needed
    test_device_realism.py           -- sensor/actuator fault/saturation/encoder realism, requires_basilisk
    test_comms_pointing.py           -- Sun-pointing/ground-station comms-pointing mode arbitrator, requires_basilisk
    test_thermal_simulation.py       -- "thermal" sensor + reaction_wheel motor-thermal model, requires_basilisk
    test_propellant_bookkeeping.py   -- shared per-tick mass/propellant delta math, no Basilisk needed
    test_constellation.py            -- Phase 4
    test_scenario_templates.py       -- load/validate/round-trip every scenarios/templates/*.json
    test_template_claims.py          -- runs templates for real and checks their descriptions' claims, requires_basilisk
    test_examples.py                 -- runs every examples/*.py script (most require_basilisk)
    test_cli.py
    test_two_body_validation.py      -- requires_basilisk
    test_mission_engine.py           -- Phase 6, requires_basilisk
    test_time_system.py              -- UTC -> SPICE epoch string (locale-independent), no Basilisk needed
    test_orbit_design.py             -- Sun-synchronous inclination / RAAN-for-LTAN helpers, no Basilisk needed
    test_scenario_explainer.py       -- explain(): structure, short strings, never raises on any template
    test_scenario_checks.py          -- pass prediction (vs. an independent propagation) and pre-run warnings, no Basilisk needed
    test_autosave.py                 -- crash-recovery autosave (Qt-free half)
    test_conservation_check.py       -- when the two-body energy/momentum drift check applies
    test_orbit_maintenance_j2_regression.py -- phasing/station-keeping regressions under real J2 gravity, requires_basilisk
    test_formation_keeping_regression.py -- follower mirrors the chief's reboosts; closed-loop relative SMA, requires_basilisk
    test_gravity_gradient.py         -- GravityGradientEffector wiring, requires_basilisk
    test_thruster_control.py         -- real "thruster" actuator control path, requires_basilisk
    test_momentum_dumping.py         -- RW momentum desaturation via thrusters, requires_basilisk
    test_mtb_desaturation.py         -- RW momentum management via magnetic torque rods, requires_basilisk
    test_mtb_dipole_result_series.py -- commanded MTB dipole exposed as its own result series, requires_basilisk
    test_css_estimation.py           -- real CSS-based sun-heading estimation (sunSafePoint), requires_basilisk
    test_location_pointing_target_body.py -- direct celestial-body pointing (locationPointing), requires_basilisk
    test_default_mrp_gain_scaling.py -- DEFAULT_MRP_GAINS auto-scaled to a spacecraft's own inertia
    test_lambert_transfer.py         -- Mission Sequence lambert_transfer command, requires_basilisk
    test_fuel_tank.py                -- real FuelTank state effector, requires_basilisk
    test_vizard_fuel_tank_panel.py   -- live Vizard "Fuel Tank" panel for the fuel-tank effector
    test_osculating_elements.py      -- osculating + first-order-J2 mean Keplerian elements export
    test_orbit_maintenance.py        -- station-keeping/phasing-keeping/constant-frame-thrust VNB/RTN math, requires_basilisk
    test_orbit_maintenance_true_mass.py -- delta-V estimate accounts for fuel-tank mass too
    test_spacecraft_templates.py     -- reusable spacecraft "bus" templates
    test_facets.py                   -- facet models: schema, box generator, facet drag/SRP physics in Basilisk
    test_geo_station_keeping.py      -- GEO station-keeping: true-equator placement, schema, J22 drift, drift fit
    test_formation.py                -- phasing-formation generator (chief + R/T/N offset), requires_basilisk
    test_monte_carlo.py              -- Basilisk.utilities.MonteCarlo bridge, requires_basilisk
    test_service_execution_errors.py -- clear error message for a real ExecuteSimulation() crash class
    test_service_run_live.py         -- chunked run_live() streaming for the GUI's live-updating plot
    test_vizard.py                   -- Vizard GenericStorage/GenericSensor dangling-pointer regression, requires_basilisk
    test_vizard_labels.py            -- Vizard RTN panel label helpers, no Basilisk needed
    test_logging_setup.py            -- file-backed logging so a GUI crash leaves more than one bare line
    data/
      vizard_station_keeping_crash_regression.json -- input scenario for test_vizard.py
    gui/
      conftest.py                    -- joins every QThread a test started (a GC'd running QThread aborts the process)
      test_app.py
      test_widgets.py                -- PreciseDoubleSpinBox / exact_number_text
      test_feedback.py               -- toast + inline-validation helpers
      test_mission_dashboard_widget.py
      test_scenario_explainer_widget.py
      test_formation_diagram_widget.py
      test_theme.py
      test_icons.py
      test_scenario_templates_gui.py -- every template round-trips through ScenarioEditorWidget and every editor dialog unchanged
      test_orbit_ic_widget.py
      test_spacecraft_editor.py
      test_spacecraft_template_dialog.py
      test_sensor_actuator_editor.py
      test_vizard_dialog.py
      test_vizard_launcher.py
      test_monte_carlo_editor.py
      test_ground_station_editor.py
      test_constellation_dialog.py   -- Phase 4
      test_phasing_formation_dialog.py
      test_scenario_editor.py
      test_propagation_setup_dialog.py
      test_results_widget.py
      test_data_panel_widget.py
      test_run_worker.py
      test_main_window.py
      test_mission_sequence_editor.py -- Phase 6
      test_mission_output_widget.py  -- Phase 6
      test_load_scenario_widget.py   -- "Load Scenario" tab: built-in template picker + browse
      test_template_wizard.py        -- the "Customize: <template name>..." guided wizard
      test_startup_fetch_dialog.py   -- startup prompt to fetch cached support data/Vizard when missing
```

## Running the tests

```bash
cd SpaceMissionStudio
python3 -m pip install -e ".[dev,gui]"
python3 -m pytest tests/ -v
```

The suite has 2499 tests. Without Basilisk, the 344 marked
`requires_basilisk` (and a few that check for Basilisk themselves, per
`tests/conftest.py`) are skipped; the rest -- schema, space weather,
results, link budget, constellation generation, CLI, the Basilisk-free
examples and the full PySide6 GUI, run headless -- run and pass.

With Basilisk 2.12.0 installed (see "Getting started" above), those
tests run for real: 2489 pass and 10 skip (the ones whose premise is
specifically "Basilisk is unavailable"; Python 3.11, Linux). The
first run needs internet access once, so Basilisk can download its
SPICE ephemeris kernels; without them, the ~45 kernel-dependent tests
fail with `KernelError`.
`pip install pytest-xdist` and `pytest tests/ -n auto` runs the suite
on all CPU cores.
See "Verification status" above for how thoroughly that's actually been
exercised -- short version: yes, including a real full multi-day run.

`packaging/build_wheel.sh`/`install.sh` are NOT run by `pytest` (they're
shell scripts that build/install a real wheel, not something worth
wrapping in a slow subprocess-spawning test) -- see `packaging/README.md`
for how they were verified instead.

If PySide6 fails to import with `ImportError: libEGL.so.1: cannot open
shared object file` (a minimal Linux install, or a container like the one
this session used), install the missing system libraries first --
Debian/Ubuntu: `apt-get install libegl1 libopengl0 libxcb-cursor0` (this
session also needed `libgl1`/`libxkbcommon0`, but those were already
present on the base image; a truly minimal system may need them too).

## Using the schema/space-weather layer standalone (no Basilisk needed)

```python
from spacemissionstudio.schema import Scenario, GravityConfig, OrbitIC, SpacecraftConfig

scenario = Scenario(
    name="demo",
    epoch_utc="2030-01-01T00:00:00",
    gravity=GravityConfig(central_body="earth", central_body_degree=0),
    spacecraft=[
        SpacecraftConfig(
            name="sat-1",
            orbit=OrbitIC(type="classical_elements", semi_major_axis_km=7000.0,
                          eccentricity=0.001, inclination_deg=51.6, raan_deg=0.0,
                          arg_periapsis_deg=0.0, true_anomaly_deg=0.0),
        )
    ],
)
scenario.validate()
scenario.save("my_scenario.json")
```

```python
from datetime import datetime
from spacemissionstudio.engine import spaceweather as sw

# Real data only, and resolve() never touches the network. "bundled" (the
# default) is CelesTrak's SW-All shipped with the app (or a newer copy the
# GUI's consent-gated startup prompt downloaded); "local_file" is your own
# CelesTrak .txt/.csv download.
resolved = sw.resolve("bundled", datetime(2030, 1, 1), datetime(2030, 4, 1))
print(resolved.path, resolved.data_file, resolved.warnings)
```

## Running a scenario (requires a Basilisk build)

```python
from spacemissionstudio.schema import load_scenario
from spacemissionstudio.engine.service import SimulationService

scenario = load_scenario("spacemissionstudio/scenarios/two_body_validation.json")
service = SimulationService(scenario)
result = service.run()
result.export_csv("out/")
```

To also get attitude control and a Vizard playback file, set a
spacecraft's `fsw_mode`/`sensors`/`actuators` (see `engine/fsw.py`) and
pass a `VizardRequest`:

```python
from spacemissionstudio.engine.vizard import VizardRequest

service = SimulationService(scenario, vizard_request=VizardRequest(save_file="out/viz.bin"))
result = service.run()
```

## Running the CLI

The `spacemissionstudio` command (installed by `pip install -e .`; `python3 -m
spacemissionstudio.cli` works identically without installing) is the
batch/headless entry point, built on exactly the calls above -- see
`cli.py`'s own docstring.

```bash
# no Basilisk needed:
spacemissionstudio validate spacemissionstudio/scenarios/two_body_validation.json
spacemissionstudio spaceweather-resolve spacemissionstudio/scenarios/two_body_validation.json

# needs a Basilisk build:
spacemissionstudio run spacemissionstudio/scenarios/two_body_validation.json --out-dir results/
spacemissionstudio run scenario_with_fsw.json --out-dir results/ --vizard-save-file results/viz.bin
spacemissionstudio monte-carlo scenario_with_dispersions.json --archive-dir mc_results/
spacemissionstudio lifetime scenario.json --deorbit-perigee-km 250
spacemissionstudio budget scenario.json --run
spacemissionstudio kernels-status

# launches the PySide6 GUI (needs the 'gui' extra; does NOT need Basilisk
# to open -- only runs need it, and report clearly if it's
# missing rather than crashing):
spacemissionstudio gui
```

Without Basilisk, `run` and `kernels-status` print a specific "Basilisk is
not installed/built" message and exit with status 2 -- genuinely
verified, not just designed to behave that way.

Two more commands worth knowing: **Launch Vizard** (Run menu/toolbar,
GUI only) starts the external Vizard application itself, separate from
configuring how a run feeds it -- if it can't be found automatically
(a remembered path, or a short list of common per-OS install
locations), a dialog offers **Download Vizard** (fetches AVS's own
pre-built binary for your platform, cached locally -- an explicit click,
never automatic; see "Closed-off/offline policy" below) alongside the
original **Browse...** for an existing install (see
`docs/source/Vizard/VizardDownload.rst` in the Basilisk checkout for the
same published links, if you'd rather install it yourself);
**Abort Simulation** (Run menu, GUI only, also while
a Monte Carlo batch or Mission Sequence is running) cooperatively
cancels an in-progress run between simulation chunks or
mission-sequence commands -- never a forced kill, so partial results
from before the cancellation are kept, not discarded. Full detail on
both in `HISTORY.md`.

## Running the GUI

```bash
python3 -m pip install -e ".[gui]"
spacemissionstudio gui
# or: python3 -m spacemissionstudio.gui.app
```

The GUI opens on its **Load Scenario** tab (left pane) -- pick one of the
twenty-five built-in template missions (see "Template missions" below) or
browse for any other scenario file; either one switches you to the
**Scenario Editor** tab next to it with that scenario loaded and ready to
edit. Every row of the template list carries its own **Customize...**
button (always enabled, no selection needed; its accessible name is
"Customize: \<template name\>"): a short, multi-step walkthrough of just that template's own key
tunable parameters (pre-filled with its current values), ending in the
same Scenario Editor tab with those changes already applied -- a faster
path than the full editor form for someone who wants "GEO
station-keeping, but with a tighter longitude box and twice the propellant"
rather than every field on every spacecraft. The
original template file is never modified either way (both still need
File > Save As to write anywhere). File > New/Open/Save/Save As work against the same
`schema.Scenario`/`load_scenario()`/`.save()` the CLI uses (File > Open
and the Load Scenario tab's own "Browse for a file..." button are two
paths to the same `open_path()`); the scenario form's validation status
label updates live as you type, including its Monte Carlo section
(enable/num_runs/thread_count + a dispersion list, referencing spacecraft
by name). Run > Run Simulation runs `SimulationService` on a background
thread (the UI stays responsive) and switches to the Results tab when
done, with a plot per result series, a CSV export button (every series
at once), and "Save PNG..."/"Save SVG..." buttons (just the currently
displayed plot, to a user-chosen location via a native Save As dialog --
rendered client-side through the same `plotly.js` already on the page,
not a new `kaleido` dependency). A
**"Mission Dashboard"** tab alongside Results shows the same run's live,
at-a-glance telemetry (sim time/mode/ground-station visibility, pointing
error/tracking status, battery charge-SOC-net power, and a live RF
link-budget breakdown) whenever the scenario has a
`comms_pointing`-configured spacecraft (see template '19'); it stays on
its own empty-state placeholder otherwise. Run > Check
Kernels shows SPICE kernel fetch/cache status. Both Run actions report a
clear error (not a crash) if Basilisk isn't installed/built.

## Template missions for learning and for starting your own

`spacemissionstudio/scenarios/templates/` has twenty-five ready-to-run
scenario files. Its [`README.md`](spacemissionstudio/scenarios/templates/README.md)
lists them with what each teaches and a suggested learning order; in the
GUI, the Load Scenario tab lists them by name with their descriptions.

* **01-18, 21: one concept each** -- two-body orbits, J2 and third-body
  perturbations, GEO and LEO station keeping, a Walker constellation,
  formation flying, attitude pointing (ideal, then with real ADCS
  hardware), a Mission Sequence orbit raise, Monte Carlo, gravity-gradient
  torque, thruster attitude control, momentum management with thrusters or
  torque rods, sun-heading estimation, celestial-body pointing, a Lambert
  transfer, fuel-tank depletion, and disturbance torques from a facet model.
* **19, 20: integrated** -- Sun pointing with an automatic ground-station
  link (power and link budget follow), and thermal models on full ADCS
  hardware.
* **22-25: starting points** -- 22 a realistic satellite with its
  environment and a ground station (orbit only), 23 a complete small
  satellite (hardware, power, radio link, a Mission Sequence stopping on a
  ground pass), 24 template 05's formation under Basilisk's mean-element
  control law, and 25 a Monte Carlo batch over orbit insertion and drag.

Each file's `description` says what to look at after running it and what
to try changing, and every row has a **Customize...** dialog over all its
settings (see "Running the GUI" above). The files are generated by
`scripts/_generate_templates.py` through `schema.scenario`'s dataclasses
and `Scenario.validate()`, never written by hand; their descriptions live
in `scripts/_template_descriptions.py`.

How they are checked:

* `tests/test_scenario_templates.py` (Basilisk-free): every template loads,
  validates, round-trips through save/load and keeps a short, structured
  description, plus each template's own structural claims.
* `tests/gui/test_scenario_templates_gui.py`, `test_load_scenario_widget.py`
  and `test_template_wizard.py`: each one round-trips through the editor
  form, the Load Scenario tab and its Customize dialog.
* `tests/test_template_claims.py` (Basilisk): templates 03, 07, 08, 10-14,
  16, 17 and 19-24 run for real and their descriptions' headline numbers
  are checked; 25 runs in `tests/test_examples.py`. The numbers in the
  other descriptions come from real runs but are not re-checked by a test.

```bash
spacemissionstudio validate spacemissionstudio/scenarios/templates/22_starter_first_leo_satellite.json  # no Basilisk needed
spacemissionstudio run spacemissionstudio/scenarios/templates/22_starter_first_leo_satellite.json --out-dir out
```

To use one as a starting point for your own mission: **Save As...** under
a new name before editing (the original stays intact), then add what you
need step by step (User Manual section 6, "Building your own scenario,
step by step").

## Vendoring vs. building Basilisk from source

Building from source in an automated/CI/sandboxed context is fragile --
this project hit exactly that failure mode early on (see `HISTORY.md`
for the full story). The plan flagged from the start was to
**vendor a prebuilt wheel pinned to a specific Basilisk release/commit**
as the default install path for end users, keeping "build from source" a
documented, opt-in developer path only.

That plan turned out to be simpler to satisfy than expected: Basilisk
itself now publishes prebuilt wheels to PyPI (`pip install "bsk[all]"`),
so there is usually no separate wheel to hunt down or vendor at all --
"Getting started" above IS the vendoring story for most users.
`packaging/install.sh --basilisk-wheel` still exists and still works (it
was run end-to-end against `"bsk[all]"` for real -- see
`packaging/README.md`) for the cases that DO need something other than
the published PyPI package: a specific pinned/older release for
reproducibility, a locally-built wheel with custom modules, or an offline
install from a wheel file already on disk. `--basilisk-wheel` accepts any
string `pip install` would (a path, a URL, or a plain requirement
specifier like `"bsk[all]==2.12.0"`), not literally only a `.whl` file.

### Qualified Basilisk version

SpaceMissionStudio is verified against **Basilisk 2.12.0**
(`spacemissionstudio.dependencies.QUALIFIED_BASILISK_VERSION`; ECSS
compliance decision D5). The `.deb` and Windows installers install
`bsk[all]==2.12.0`. Another version still runs, but the GUI status bar and
`spacemissionstudio run` say so, and every run's `provenance.json` records
the Basilisk version, whether it is the qualified one, the other dependency
versions, a SHA-256 of the scenario and the reference data files used
(SPICE kernels, gravity field, magnetic model, space weather). The Basilisk
sources in this repository (`../src`, currently 2.13.0b0) are not the
qualified version.

### CCSDS orbit data messages

SpaceMissionStudio reads, validates and writes CCSDS 502.0-B-3 (April 2023)
Orbit Parameter, Mean-Elements and Ephemeris Messages in KVN
(`spacemissionstudio/engine/ccsds_odm.py`; the OCM and the XML form are not
supported):

* `spacemissionstudio ccsds-validate FILE...` checks files against the
  standard; every breach of a "shall" is an error and of a "should" a
  warning, each with its clause.
* `spacemissionstudio run SCENARIO --oem` also writes each spacecraft's
  ephemeris as an OEM (EME2000, UTC; `--oem-stride N` thins it).
* `spacemissionstudio ccsds-export SCENARIO --out DIR` writes each
  spacecraft's initial state as an OPM (with osculating elements and GM for
  Earth), or a TLE spacecraft's elements as an OMM.
* `spacemissionstudio ccsds-import FILE SCENARIO --spacecraft NAME` sets a
  spacecraft's orbit from an OPM (EME2000, ICRF or GCRF; UTC, TAI, TT or
  TDB; `--set-epoch` moves the scenario epoch to the OPM's) or from a
  TLE-based OMM (converted to the TLE it represents).

`compliance/ics_ccsds_502.csv` is the Implementation Conformance Statement
(Annex A) for the three messages.

### Earth orientation

With NAIF's IERS-based Earth PCKs installed, the Earth-fixed frame of a run
is **ITRF93** (precession, nutation with IERS corrections, UT1, polar
motion); without them it is SPICE's `IAU_EARTH` rotation model (about
1.5 mrad, roughly 10 km at the surface, away from ITRF93 in 2026) and every
Earth run says so. The files (about 36 MB from naif.jpl.nasa.gov) are
fetched by the installers, by the startup prompt when you agree, or with
`spacemissionstudio earth-orientation --fetch`; `--import FILE` installs
them from disk and `--rollback` restores the previous set. After the files'
last measured data plus about ten weeks the orientation is NAIF's
long-term prediction, which the Explain tab notes.

## Closed-off/offline policy

SpaceMissionStudio makes **no network calls implicitly**. Nothing here ever
fetches anything without asking first -- there are exactly three places
network access can happen, all opt-in:

* **Installation** -- `pip install "bsk[all]"` (an ordinary PyPI install
  step) and a one-time pre-fetch of SPICE/gravity-harmonics/magnetic-field
  support data (`engine.kernels.require_kernels()`, called by all four
  packaging installers right after installing SpaceMissionStudio itself)
  that warms Basilisk's own local `pooch`-backed cache for good -- see
  `packaging/README.md`'s "Closed-off/offline policy" section for exactly
  where in each script and why.
* **The startup fetch/update prompt** (`gui.startup_fetch_dialog`) -- a
  dialog shown once each time the GUI starts, asking whether to check for
  updates to support-data kernels and/or real space-weather history
  (CelesTrak) now, and cache the result locally for later use. **Always
  asks first** -- there is no "don't ask again" setting and nothing here
  is ever fetched silently; clicking **Skip**, or unchecking both items,
  touches no network at all, same as if the dialog didn't exist. A
  successful space-weather fetch is an ordinary local CSV afterward -- the
  Propagation Setup dialog's Local file field pre-fills with it
  automatically (`engine.spaceweather.cached_fetch_path()`) when the
  scenario doesn't already have its own `local_file_path` set.
* **Launch Vizard's "Download Vizard" button** (`gui.vizard_launcher
  .fetch_vizard`) -- reached only via an explicit click in the "Vizard not
  found" dialog (Run menu's **Launch Vizard**), never automatically;
  downloads AVS's own pre-built Vizard binary and caches it locally, same
  "ask first, store locally for next time" shape as the startup prompt.
  The original manual **Browse...** option (point this app at an existing
  Vizard install yourself, from `docs/source/Vizard/VizardDownload.rst`'s
  published links) is always available alongside it.

`engine.spaceweather.resolve()` itself -- the function actually called
while a scenario runs -- never touches the network. Space weather is real
data only: `source` is `"bundled"` (the default: CelesTrak's SW-All file
shipped in `spacemissionstudio/data/spaceweather/`, or a newer copy the
startup prompt downloaded) or `"local_file"` (your own CelesTrak file).
The shipped file (updated 2025-07-21; <https://celestrak.org/SpaceData/>)
holds observed daily F10.7 and Ap from 1957-10-01 and CelesTrak's 45-day
forecast. Beyond that, solar activity comes from NASA MSFC's October 2026
prediction (also shipped; F10.7 and Ap at the 95th/50th/5th percentiles,
2026-04 to 2041-10, the last 132 months repeated after that), as ESA's
AD10 guideline (EOP-FM/2024-07-177, Sec. 5.9) prescribes. "Solar
activity" picks the column: Nominal (50th) by default, Conservative
(95th) as AD10 asks for operations budgets, the 50th for end of life. Months before MSFC's
first use NOAA's monthly F10.7 with Ap at the observed mean (12.8). Runs
say which data they used in their warnings. The earlier `"synthetic"` profile was
removed; older scenario files are migrated to `"bundled"`. So was the
old "conservative" margin (a constant percentile of the observed
record): schema v4 turns it into the 95th percentile.

## Known limitations

* **No `svIntegratorRK4` in this checkout.** Only `svIntegratorEuler`,
  `svIntegratorRK2`, `svIntegratorRKF45`, `svIntegratorRKF78` exist (see
  `../src/simulation/dynamics/Integrators/`). `schema.scenario.SimSettings`
  and `engine.service._INTEGRATORS` only offer those four; `"rkf78"` is
  the default.
* **Spherical-harmonics gravity is Earth-only in `service.py`**
  (GGM03S, the same file `../missionAnalysis` uses). Other central bodies
  are limited to point-mass gravity (`central_body_degree=0`) until a
  later phase adds their gravity-field files.
* **Magnetometer sensors are Earth-only** (`magneticFieldWMM`, same
  reasoning as spherical-harmonics gravity) -- `engine.fsw` raises a clear
  error for a magnetometer on any other central body rather than silently
  producing a sensor with no field to read.
* **Both actuator kinds beyond `"reaction_wheel"` are wired up, each for
  a specific role**: `"thruster"` either as primary attitude control
  (real `thrusterDynamicEffector` + `thrForceMapping` + `thrFiringSchmitt`
  -- a spacecraft uses `"reaction_wheel"` OR `"thruster"` for control, not
  both) or, together with `"reaction_wheel"`, as `MomentumDumpingConfig`'s
  desaturation hardware; `"magnetic_torque_rod"` ONLY as
  `MagneticMomentumManagementConfig`'s desaturation hardware (continuous
  RW momentum biasing via the real geomagnetic field, not a discrete
  burst) -- there is no standalone magnetic-torque-rod attitude-control/
  detumble mode, so a `"magnetic_torque_rod"` actuator without
  `magnetic_momentum_management` set is rejected early with a specific
  error.
* **The attitude control loop closes on truth spacecraft state**, EXCEPT
  for sun heading specifically. `simpleNav` is in the loop (not raw
  `scStateOutMsg`), but its error-model matrices are left at Basilisk's
  own zero defaults -- there is no GUI/schema field yet to configure
  realistic navigation error. `fsw_mode: sunSafePoint`'s
  `fsw_params['use_css_estimation']` is the one exception: it drives the
  controller from a real `cssWlsEst` weighted-least-squares estimate
  computed from a dedicated `coarse_sun_sensor` cluster, not truth (see
  `14_css_sun_heading_estimation.json`). A full attitude DETERMINATION
  filter (star tracker + rate gyro + reaction-wheel speeds through
  Basilisk's `inertialUKF`) is deliberately not built -- no clean shipped
  Basilisk example was found to verify one against safely.
* **`engine.fsw.DEFAULT_MRP_GAINS` (`K=3.5`, `P=30.0`), lifted directly
  from Basilisk's own `examples/BskSim` reference, is tuned for a
  900 kg*m^2 spacecraft** running its FSW task at a 0.1s rate -- applied
  unscaled to a much smaller spacecraft (this schema's own default
  inertia is 10 kg*m^2), the resulting discrete-time control update
  reliably diverges to NaN within seconds. **No longer a trap for a new
  spacecraft**: `engine.fsw.build_mrp_feedback` now auto-scales K/P by
  that spacecraft's own `inertia_kg_m2` relative to the 900 kg*m^2
  reference (`_default_mrp_gains_for_inertia`) whenever
  `SpacecraftConfig.control_params` doesn't explicitly set `K`/`P` --
  confirmed against a real Basilisk build to converge cleanly even at the
  schema's own coarse `dynamics_task_rate_s` default, where the unscaled
  reference gains diverge (`tests/test_default_mrp_gain_scaling.py`).
  This was previously applied only by hand, to specific templates
  (`07_attitude_pointing_with_adcs_hardware.json`,
  `14_css_sun_heading_estimation.json`'s explicit scaled
  `control_params`; `06_attitude_pointing_basic.json`'s finer task rate)
  before it was generalized into `engine.fsw` itself for every
  spacecraft -- those templates' own explicit choices are now redundant
  but harmless. Passing explicit `control_params={"K": ..., "P": ...}`
  still overrides this unscaled, same as always -- that choice stays on
  you.
* **Monte Carlo dispersions** cover dry mass, starting attitude, orbital
  elements, inertia, body rate and the drag and SRP coefficients (User
  Manual section 10). Raw Cartesian position/velocity dispersion is
  deliberately NOT offered: Basilisk's Cartesian dispersion classes
  replace each component with an absolute random value, not a
  perturbation around the nominal orbit; the orbit varies as orbital
  elements instead. The Monte Carlo tab tracks position and velocity
  only (attitude, wheel speeds and other series are not kept per run).
* **`monte_carlo.thread_count > 1`** has been run in this project's Linux
  environment (template 25 and three-run batches with 3 threads, Basilisk
  2.12.0); the schema default stays `1`.
* **Monte Carlo retains a fixed set of data per run** (each spacecraft's
  position/velocity) -- there is no per-run custom retention-policy
  selection in the schema yet.
* **No Jacchia-Roberts atmosphere model, no Earth-albedo/IR radiation
  pressure, no `TabularAtmosphere` (user-supplied density table).** All
  three were real user questions/requests, checked directly against
  Basilisk's own source (not assumed) before answering:
  * Jacchia-Roberts genuinely doesn't exist anywhere in Basilisk (checked
    `src/simulation/environment/` -- only `ExponentialAtmosphere`,
    `MsisAtmosphere`, `TabularAtmosphere` do); `atmosphere_model` offers
    the first two (see "Orbital dynamics & propagation" above), not the
    one that doesn't exist.
  * Basilisk's `earthRadiationModel` module computes Earth albedo/IR
    flux, but its own payload comment names `facetERPDynamicEffector` as
    the consumer that turns that flux into an actual orbital force --
    and that module doesn't exist in this Basilisk build either (checked
    the source tree and the installed package). Wiring this up for real
    would mean writing a brand-new, never-before-exercised force
    -effector from scratch (the same `extForceTorque` manual-force
    -injection pattern this project's own thrust controllers use, plus
    the standard flux/c * area * Cr formula solar SRP already uses) --
    deliberately not done this round; real user decision, not a gap that
    slipped through unnoticed.
  * `TabularAtmosphere` (a user-supplied altitude/density CSV) would need
    a new file-upload schema/GUI concept of its own -- out of scope for
    the atmosphere-model-choice work that added `ExponentialAtmosphere`
    as the second option.
* **This development sandbox itself still can't reach the NAIF SPICE
  kernel host** (its network policy blocks it), so `engine.kernels`'s
  download step always fails here specifically -- correctly, with a
  clear error, not a code defect. This is a sandbox limitation, not a
  project limitation: a real user's machine, with ordinary internet
  access, has since run full multi-day simulations successfully (see
  "Verification status" above) -- kept in this list only because it's
  still true of THIS development sandbox specifically.

## Version 2.0.0

A **MAJOR** version bump under semver -- the only breaking change in
this project's history so far, and the reason it's 2.0.0 and not 1.1.1:
every scenario file, template, and simulation capability from 1.1.0
carries over completely unchanged (see "Version 1.1.0" below for all of
that); what breaks is anyone's own code that imports the old package
name or invokes the old CLI command.

* **Renamed from "missionStudio" to "SpaceMissionStudio"** (short form
  "SMS" -- in prose only, never the CLI command or package name, since
  that would collide confusingly with Short Message Service), requested
  directly. A full technical rename, not just branding:
  * Directory: `missionStudio/` -> `SpaceMissionStudio/`.
  * Python package/import name: `missionstudio` -> `spacemissionstudio`.
    **Migration**: change `import missionstudio` / `from missionstudio
    import ...` to `import spacemissionstudio` / `from
    spacemissionstudio import ...` anywhere you've scripted against this
    project.
  * CLI command: `missionstudio ...` -> `spacemissionstudio ...`
    (`pyproject.toml`'s `[project.scripts]` entry point).
  * PyPI/`.deb` package name: `missionstudio` -> `spacemissionstudio`.
  * Windows installer: app name/publisher/install directory/Start Menu
    group/output filename all updated, plus a freshly-regenerated
    `AppId` GUID (the field's own comment says not to reuse a GUID for a
    different application identity, and this is one -- no end user has
    ever installed the old build via this installer, which has still
    never been run on a real Windows machine).
  * Desktop entry (`packaging/spacemissionstudio.desktop.in` and the
    packaged `.desktop`): `Name=`/`Exec=`/`Icon=`/`StartupWMClass=` all
    updated, files themselves renamed.
  * Every in-app GUI string (window title, About dialog, Load Scenario
    tab text, ...) -- confirmed with a real headless render, not just
    grep.
  * All 120 files referencing the old name in any case form
    (`missionstudio`, `missionStudio`, `Missionstudio`,
    `MISSIONSTUDIO` -- all four variants genuinely appeared somewhere,
    including a PowerShell PascalCase parameter name and an
    env-var-style all-caps pair in a template's own description field)
    updated consistently.
  * Deliberately NOT touched: `HISTORY.md`'s development log keeps
    saying "missionStudio"/"missionstudio" throughout, since it's an
    honest record of what was actually true when each entry was written
    -- the same "nothing below was deleted or altered" discipline that
    file already states about itself. One note near the top explains
    the rename instead of rewriting history.
* **Removed `missionAnalysis`**, a standalone, one-off constellation
  mission-design case study that predates this project and was never
  run end-to-end in this development sandbox (its own README said so).
  Not imported or depended on anywhere -- the only references elsewhere
  were prose provenance comments ("ported directly from
  `../missionAnalysis`'s X"), left as historical design-rationale notes,
  not functional dependencies. This project has since absorbed and
  generalized essentially everything it did (constellation generation,
  station-keeping/phasing controllers, power budget, link-margin
  estimate, Vizard comm-ring visualization) with far more capability
  than the one fixed case study ever covered.
* **Version bumped** `1.1.0` -> `2.0.0` in `pyproject.toml`,
  `spacemissionstudio/__init__.py`, and
  `packaging/windows/spacemissionstudio.iss`'s `MyAppVersion` (the
  `.deb` reads `spacemissionstudio.__version__` directly, no change
  needed there). No scenario schema version bump -- `
  CURRENT_SCHEMA_VERSION` is still `1`, every scenario file valid under
  1.1.0 is still valid, unmodified, under 2.0.0; the breaking surface is
  entirely the package/CLI identity above, not the scenario format.

## Version 1.1.0

A feature release on top of 1.0.0 -- new simulation capabilities, nine
more templates, and a GUI stability pass, all backward-compatible (no
scenario schema migration needed: every new field is purely additive,
see `schema/migrations.py`'s own docstring for that rule). What changed:

* **Four new actuator/effector capabilities, each with its own template**
  to learn from: real gravity-gradient disturbance torque
  (`enable_gravity_gradient` -> Basilisk's own `GravityGradientEffector`,
  `10_gravity_gradient_torque.json`); real thruster-actuated attitude
  control (`thrusterDynamicEffector` + `thrForceMapping` +
  `thrFiringSchmitt`, `11_thruster_attitude_control.json`); reaction
  -wheel momentum desaturation via a thruster cluster
  (`MomentumDumpingConfig`, `12_reaction_wheel_momentum_dumping.json`)
  and, as an alternative, via magnetic torque rods
  (`MagneticMomentumManagementConfig`,
  `13_magnetic_torque_rod_momentum_management.json`); and real propellant
  depletion through Basilisk's own `fuelTank` state effector, tied to a
  thruster's own mass-flow rate (`FuelTankConfig`,
  `17_fuel_tank_depletion.json`).
* **Two new attitude-guidance capabilities**: real CSS-based sun-heading
  ESTIMATION (not truth) feeding `sunSafePoint` via a `cssWlsEst`
  weighted-least-squares estimator (`14_css_sun_heading_estimation.json`),
  and direct celestial-body pointing -- `locationPointing` aimed at a
  body other than a ground station, via `build_ephemeris_converter`
  (`15_celestial_body_pointing.json`).
* **A new Mission Sequence command**: `lambert_transfer` solves for
  whatever delta-V takes a spacecraft to a target position after a given
  time of flight (rather than specifying the delta-V directly), via
  Basilisk's own `lambertPlanner` -> `lambertSolver` -> `lambertValidator`
  chain (`16_lambert_transfer.json`).
* **A direct LEO counterpart to GEO station-keeping**:
  `18_leo_station_keeping.json` -- drag-driven decay instead of GEO's
  Sun/Moon/SRP drift, same `station_keeping` controller. Eighteen
  built-in templates total now, up from the nine 1.0.0 shipped with.
* **The "Customize: \<template name\>..." guided wizard, rolled out to
  all eighteen templates** (`gui/template_wizard.py`, piloted on three in
  an earlier round) -- a short, multi-step walkthrough over just one
  template's own key tunable parameters, pre-filled with its current
  values, for anyone who wants "this template, but with X changed"
  without learning the full Scenario Editor form.
* **A real, previously-silent attitude-control instability closed by
  default.** `engine.fsw.DEFAULT_MRP_GAINS` (tuned for a 900 kg*m^2
  reference spacecraft) reliably diverges to NaN when applied unscaled to
  a much smaller one -- previously fixed by hand, per template, wherever
  it was noticed. `engine.fsw.build_mrp_feedback` now auto-scales K/P by
  a spacecraft's own inertia by default, closing this for every new
  spacecraft, not just the templates someone remembered to fix (see
  "Known limitations" below and `tests/test_default_mrp_gain_scaling.py`).
* **A GUI stability pass**, prompted by real user reports of windows that
  "don't allow maximizing" and visual corruption on resize: audited every
  `QDialog`/`QWizard` in `gui/` for the same root cause (a widget's
  `sizeHint()` not reflecting its real content, confirmed from real
  user screenshots -- the offscreen Qt platform plugin used for automated
  testing could not reproduce any of these), fixing `SpacecraftEditorDialog`
  and every `TemplateCustomizeWizard` spec's sizing, and wrapping
  `LoadScenarioWidget`'s content in its own `QScrollArea` after a real
  screenshot showed overlapping, garbled text in its Load Scenario tab on
  resize/maximize.
* **A beginner-friendly user manual** ([`USER_MANUAL.md`](USER_MANUAL.md)),
  illustrated with real screenshots of the running app, plus a README
  accuracy pass (the repository layout tree, test counts, and template
  catalog had drifted behind the real codebase; one factually-reversed
  "Known limitations" claim about MRP gain scaling was corrected).
* **Version bumped** `1.0.0` -> `1.1.0` in `pyproject.toml`,
  `spacemissionstudio/__init__.py`, and both installers' version strings
  (`packaging/windows/spacemissionstudio.iss`'s `MyAppVersion`; the `.deb`
  reads `spacemissionstudio.__version__` directly, so it needed no change).
  No schema version bump and no breaking changes -- every scenario file
  valid under 1.0.0 is still valid, unmodified, under 1.1.0.

## Version 1.0.0

The first tagged release. What changed for it, and what "1.0.0" actually
means here:

* **A real end-to-end run, on a real Basilisk install, finally happened**
  -- the one specific gap this project had flagged since Phase 0 (this
  development sandbox's network policy blocks the NAIF SPICE kernel
  host, so a full run past kernel loading was never independently
  confirmed here). A real user ran the full `05_formation_flying_phasing.json`
  template -- both `StationKeepingController` and `PhasingKeepingController`
  active, Vizard live-streaming on -- to 100% completion (`t=604800.0 s`
  of `604800.0 s`, the full 7 simulated days) with no errors. Getting
  there involved finding and fixing a real, previously-unreproducible
  crash along the way -- a long investigation that initially misidentified
  eclipse-handling as the cause before a real `gdb` session traced it to
  a dangling-pointer bug in `engine/vizard.py`'s Vizard live-data panels
  (see "Verification status" above, and `HISTORY.md` for the full
  investigation).
* **Cross-platform install.** `python -m venv` + `pip install "bsk[all]"`
  + `pip install -e ".[dev,gui]"` (the "Getting started" section above)
  works identically on Linux and Windows 11 -- Basilisk's own prebuilt
  wheels are published for both (`../docs/source/Install.rst`'s "Prebuilt
  wheel availability" table), and SpaceMissionStudio's own code was already
  written with per-OS awareness where it matters (`gui/vizard_launcher.py`'s
  `_candidate_roots()`/`_EXECUTABLE_NAME` branch on `sys.platform` for
  finding the external Vizard app; `Path.home()`, never a raw `$HOME`/
  POSIX assumption, for every user-data location). `packaging/install.ps1`/
  `build_wheel.ps1` are new this release -- direct PowerShell ports of
  the already-verified `install.sh`/`build_wheel.sh`, giving Windows the
  same one-command install + Start Menu shortcut experience Linux has had
  since Phase 3. Per this project's own verification discipline: the
  Linux install scripts and the Linux Basilisk-wheel install have been
  run for real; their Windows counterparts have not (no Windows
  environment has ever been available in this development sandbox) --
  see `packaging/README.md`'s "Windows support" section for exactly
  what that does and doesn't cover, and please report anything that
  doesn't work as documented on a real Windows 11 machine.
* **Version bumped** `0.1.0.dev0` -> `1.0.0` in `pyproject.toml` and
  `spacemissionstudio/__init__.py`.

## What's next

Scoped but not yet built, from real GUI usage feedback (full detail in
`HISTORY.md`'s "What Phase 4 adds" and "What Phase 5 adds"):

* **`engine.constellation`'s Walker generator doesn't auto-wire
  `PhasingKeepingConfig`** for the satellites it produces -- each
  follower's chief/target-separation still needs setting up by hand in
  the spacecraft editor afterward. A natural, well-scoped follow-on once
  that manual step is felt to be tedious in practice: the generator
  already knows each plane's membership and phase ordering, so it could
  assign chief = "first satellite in the plane" and a sensible default
  target separation automatically.
* **A live NUMERIC link-margin gauge in Vizard** -- still deliberately
  not built: Vizard's `GenericStorage` only accepts Battery/DataStorage/
  FuelTank-shaped messages, and forcing a dB margin value (which can be
  legitimately negative) through would need a fabricated adapter message
  with no natural floor/ceiling -- the same bug class the RTN separation
  panels already hit once and had fixed (see `HISTORY.md`). What WAS
  built instead, per direct user feedback that the Mission Dashboard's
  live telemetry "shall also be in the vizard live visualization, not
  only in the GUI itself": a colored "Link status" `GenericSensor` badge
  (link OK vs. no/degraded link, computed live from the exact same
  `engine.link_budget.link_margin_db` the GUI uses), plus "Mode" and
  "Pointing Error" panels for the rest of that same dashboard -- see
  `engine.vizard`'s own "Live-data panels" docstring section. The exact
  dB breakdown still only appears in the GUI's dashboard; if a live
  NUMBER (not just a status) is wanted in Vizard too, the right path
  remains a real custom Vizard protobuf message/panel type, not a reused
  `GenericStorage` shape.

Beyond that, the "Known limitations" section above is the rest of the
honest map: non-Earth spherical harmonics/magnetometer, navigation
error modeling, and richer Monte Carlo retention. None of the
remaining items is blocked on a design decision; each is scoped and
documented at its own call site (or in `HISTORY.md`) for whoever picks
it up next.
