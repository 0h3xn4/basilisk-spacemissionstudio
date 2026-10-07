# SpaceMissionStudio development history

The full phase-by-phase development log: every feature's design
rationale as it was built, every real bug found and fixed (never swept
under the rug), and the complete crash-investigation writeups --
including one that took an extensive real-hardware debugging session
(culminating in a `gdb` backtrace) to actually root-cause. Moved out of
`README.md` for the 1.0.0 release so that file can be a normal,
readable project README; nothing below was deleted or altered beyond
fixing a handful of now-dangling `README.md` cross-references to point
here instead.

Read `README.md` first for current install/usage/status. Read this file
for *why* things are the way they are, or to see a real, honest account
of this project's actual development process: every line below was
written by Claude (Anthropic's AI model), via Claude Code, working
through real bugs on a real user's machine -- not a human-written log
with AI assistance, but the reverse. See `README.md`'s own "AI
authorship disclosure" at the top for the full, plain statement of what
that means and doesn't mean.

**A note on the name.** This project was renamed from "missionStudio"
(Python package `missionstudio`) to "SpaceMissionStudio" (package
`spacemissionstudio`, short form "SMS" in prose only -- never the CLI
command or package name, which would collide confusingly with Short
Message Service) after the 1.1.0 release. Everything below this point
still says "missionStudio"/"missionstudio" throughout, deliberately left
untouched: it's an honest record of what was actually true at the time
each entry was written, not a current reference -- the same "nothing
below was deleted or altered" discipline already described above. Read
`missionStudio` as `SpaceMissionStudio` wherever it appears below.

---

## Environment honesty note (read this first)

Earlier in this project, this checkout had no Basilisk Python package
available: a from-source build was attempted and failed (`conanfile.py`
couldn't reach Conan Center through this sandbox's outbound-network
policy). That's no longer the full picture -- `pip install "bsk[all]"`
(Basilisk's own published PyPI wheel) turned out to work in the same
sandbox, and was used to genuinely re-verify most of the Basilisk
-dependent code below for the first time. `celestrak.org` and the NAIF
kernel host (`naif.jpl.nasa.gov`, plus its `hanspeterschaub.info` backup
mirror) remain blocked, which is the one gap left -- see the per-item
notes below for exactly what that does and doesn't affect.

Status, as of this Basilisk-build re-verification pass:

* Everything in `missionstudio/schema/`, `missionstudio/engine/spaceweather.py`,
  `missionstudio/engine/results.py`, `missionstudio/cli.py`, and **the
  entire `missionstudio/gui/` package** (including Phase 2's sensor/
  actuator/FSW-mode/Vizard-request editors and Phase 3's Monte Carlo
  editor) has **no Basilisk import** and has been fully exercised, with or
  without Basilisk present -- `pytest tests/` genuinely runs and passes
  150 tests either way (see ``README.md``'s "Running the tests" section
  for the current, up-to-date with-Basilisk count -- this number is a
  Phase 0-era snapshot, kept here as-written). That includes the PySide6 GUI: it was built, run
  headless (`QT_QPA_PLATFORM=offscreen`, set automatically by
  `tests/conftest.py`), and driven with `pytest-qt` for real -- every form
  field, every Save/Open/Run menu action, dirty-state tracking, and the
  unsaved-changes close-confirmation prompt is exercised by an actual
  running `QApplication`, not asserted about in the abstract. Getting
  PySide6 itself running headless needed three system packages beyond
  what was preinstalled (`libegl1 libopengl0 libxcb-cursor0` on the
  Ubuntu-based image this was developed on, via `apt-get`) -- worth
  knowing if a deployment target hits the same `ImportError:
  libEGL.so.1: cannot open shared object file`.
* `missionstudio/engine/time_system.py`, `kernels.py`, `service.py`,
  `fsw.py`/`vizard.py` (Phase 2), and `monte_carlo.py` (Phase 3) import
  Basilisk. Against a real `bsk[all]` install: every Basilisk module/class
  any of these files import was confirmed to exist under the expected
  name; `time_system.py`'s SPICE call sequence was run for real
  (round-tripping an epoch through ET and back, computing TAI/TT) and a
  real bug was found and fixed doing so (a bare `import pyswice` that
  doesn't match the published package's layout -- see that module's own
  docstring); `service.py`'s `build()` was confirmed to run correctly
  through gravity/spacecraft/attitude/sensor/actuator/ground-station
  construction, failing only at the SPICE kernel DOWNLOAD step (blocked
  network to NAIF, not a code issue -- see `kernels.py`'s own note). A
  FULL run past kernel loading -- and so `fsw.py`/`vizard.py`/
  `monte_carlo.py`'s own module-construction logic, and
  `tests/test_two_body_validation.py`'s analytical check -- was NOT
  achieved, purely because that needs the blocked kernel download to
  succeed first. Each file's own docstring says precisely what was and
  wasn't confirmed, updated after this pass -- nothing here should be
  trusted as "tested" beyond what its docstring claims.
* **Packaging (`packaging/build_wheel.sh`, `packaging/install.sh`) was
  fully verified, including the Basilisk-vendoring path**: with a real
  `bsk[all]` available, `install.sh --basilisk-wheel "bsk[all]"` was run
  end-to-end and the resulting installed venv's `missionstudio.engine.service`
  imported correctly. See `packaging/README.md`.
* The GUI/CLI's no-Basilisk error handling (`gui.run_worker.RunWorker`,
  `gui.kernel_status_widget`, `cli.py`'s `run`/`kernels-status`) was
  separately confirmed for real in an environment WITHOUT Basilisk
  installed: each correctly reports "Basilisk is not installed/built"
  (no crash, no hang, no silent no-op) rather than a bare traceback.
* `tests/test_two_body_validation.py` -- the end-to-end analytical
  validation scenario this project's own requirements call for -- is
  written and ready, correctly auto-skips without Basilisk (see
  `tests/conftest.py`), and correctly ATTEMPTS a real run with Basilisk
  present, but could not complete because of the blocked kernel download
  above. **Run it on a machine with ordinary internet access** to get the
  first full confirmation that `engine.service.SimulationService`
  actually produces correct physics.

None of this is a reason to distrust the design -- it's the same
"write carefully against verified source, disclose what's untested"
discipline `../missionAnalysis` used throughout this project, now backed
by an actual Basilisk install for most of it. The one thing a user should
take away: get this running on a machine with normal internet access
(specifically, access to `naif.jpl.nasa.gov`) and the whole pipeline
should work end-to-end -- that's the one link in the chain this project's
own sandbox could never close.

## What Phase 0 delivers

* **`missionstudio/schema/`** -- a versioned, human-readable JSON scenario
  format (spacecraft, orbit ICs in three forms, gravity, ground stations,
  space weather, sim settings), with hand-written validation (clear,
  specific error messages -- never a silent NaN or a bare `KeyError`) and
  a migration registry so old scenario files keep loading as the schema
  grows. No Basilisk dependency; no third-party schema library.
* **`missionstudio/engine/time_system.py`** -- single source of truth for
  time: every scenario stores exactly one epoch representation
  (`epoch_utc`, ISO 8601 UTC); every other representation (SPICE ET, TAI,
  TT, or a Basilisk `EpochMsg`) is derived from it on demand by this
  module, via the real CSPICE time API (through `pyswice`) -- not
  hand-rolled date math.
* **`missionstudio/engine/kernels.py`** -- SPICE kernel management: wraps
  Basilisk's own versioned, `pooch`-cached kernel fetcher
  (`Basilisk.utilities.supportDataTools.dataFetcher`) and adds a status
  report (path, fetched-or-not, cache-file modified time) so kernel state
  is always visible, never silently assumed current.
* **`missionstudio/engine/spaceweather.py`** -- CelesTrak space-weather
  fetch → validate → fallback, exactly per this project's own
  instruction: try CelesTrak first; if that isn't possible, fall back to
  a user-provided local file; only fall back further than that (a
  synthetic, solar-cycle-shaped profile) loudly, with an explicit warning
  in the returned result, never silently. The CSV format check mirrors
  Basilisk's own `spaceWeatherData.cpp` loader validation exactly (same
  required columns, same duplicate/sort checks), so a bad file is caught
  here with a specific message instead of failing deep inside Basilisk.
* **`missionstudio/engine/results.py`** -- a typed result container
  (`TimeSeries`/`ResultSet`) with CSV export, independent of how the data
  was produced -- reusable by the future GUI (plotting) and by headless
  runs (export) without either depending on the other.
* **`missionstudio/engine/service.py`** -- `SimulationService`: the one
  GUI-agnostic backend class both the GUI and a headless/batch CLI call.
  Phase 0/1 scope: central-body point-mass or Earth spherical-harmonics
  gravity, PLUS third-body point-mass perturbers (`gravity.third_body_perturbers`
  -- genuinely wired up via `addBodiesTo()`, the same mechanism already
  verified in `../missionAnalysis`; an earlier draft of this file's
  docstring incorrectly called this schema-only, since corrected), one or
  more spacecraft from a classical-elements/Cartesian/TLE initial
  condition, propagation with a selectable integrator
  (`euler`/`rk2`/`rkf45`/`rkf78` -- **note: no `rk4`**, this Basilisk
  checkout doesn't ship one; see `schema.scenario.SUPPORTED_INTEGRATORS`'s
  docstring). Drag, SRP, sensors/actuators/FSW modes, ground stations, and
  Monte Carlo are validated by the schema and carried through save/load
  starting now, but not yet wired into the service -- that's Phase 2/3.
  The Phase 1 GUI's scenario editor mirrors this exactly: it edits
  everything the service actually consumes, and deliberately has no
  editor for the not-yet-wired-up fields, so nothing in the GUI looks
  like it does something it doesn't.
* **`missionstudio/scenarios/two_body_validation.json`** +
  **`tests/test_two_body_validation.py`** -- the required end-to-end
  validation scenario: Earth point-mass gravity only, propagated for
  several orbital periods, checked against an independently-computed
  analytical Kepler solution (position/velocity) and against conservation
  of specific orbital energy and angular momentum.

Two Phase 0 bugs were also found and fixed while building Phase 1 on top
of it (both are visible in `git log` for this file's history, not swept
under the rug): `schema.SimSettings` used to carry a second,
redundant `earth_grav_degree` field alongside `GravityConfig.
central_body_degree`, which could disagree with it -- removed, there is
now one field; and `schema.load_scenario()` didn't catch a missing/
unreadable file (`FileNotFoundError` propagated as a raw traceback
instead of the promised `ScenarioValidationError`) -- fixed, with a
regression test.

## What Phase 1 adds

* **`missionstudio/gui/`** -- the PySide6 GUI shell, one widget module per
  concern, none of it duplicating scenario/sim state or logic that
  already lives in `schema`/`engine`:
  * `scenario_editor.py` -- the full scenario form (name/epoch/description,
    gravity incl. third-body perturbers, sim settings, space weather
    source), with a live-updating "valid / here's exactly what's wrong"
    status label re-evaluated on every edit.
  * `spacecraft_editor.py` / `ground_station_editor.py` -- list + add/edit/
    remove dialogs for each. Spacecraft editing deliberately covers only
    what `engine.service.SimulationService` actually consumes (name,
    orbit IC, dry mass, inertia, initial attitude/rate) -- no
    sensors/actuators/FSW-mode/drag/SRP editor yet, so nothing in the GUI
    implies an effect the engine doesn't actually have. Ground stations
    ARE editable despite not being consumed yet, since they're pure
    scenario data (this project's own spec draws exactly that
    distinction) rather than a "looks like it does something" control.
  * `orbit_ic_widget.py` -- one widget covering all three
    `schema.OrbitIC` forms (classical elements / Cartesian / TLE).
  * `kernel_status_widget.py` -- SPICE kernel fetch/cache status with a
    "Check / fetch kernels" button, runs on a background thread.
  * `results_widget.py` -- matplotlib-embedded (`FigureCanvasQTAgg`) plot
    of any `ResultSet` series, plus a "export all series to CSV" button.
  * `run_worker.py` -- runs `SimulationService` on a background `QThread`
    so propagation never freezes the UI.
  * `main_window.py` / `app.py` -- ties it together: File (New/Open/Save/
    Save As, with an unsaved-changes indicator and close-confirmation) and
    Run (Run Simulation, Check Kernels) menus.
* **`missionstudio/cli.py`** -- the batch/headless CLI, built on exactly
  the same `schema`/`engine` calls the GUI makes (`validate`, `run`,
  `kernels-status`, `spaceweather-resolve`, `gui`) -- see "Running the
  CLI" below.

## What Phase 2 adds

* **`missionstudio/engine/fsw.py`** -- builds the attitude navigation/
  guidance/control/actuation module chain per spacecraft, kept separate
  from `service.py` so that file stays orchestration-only. Every
  `schema.scenario.SpacecraftConfig.fsw_mode` maps to a real Basilisk FSW
  module: `inertial3D`/`hillPoint`/`velocityPoint` (routed through
  `attTrackingError`) and `sunSafePoint`/`locationPointing` (which already
  output an `AttGuidMsg`), all closing on `mrpFeedback` control. Actuation
  is either idealized (`extForceTorque`, the default) or real reaction
  -wheel hardware (`simIncludeRW`/`reactionWheelStateEffector`/
  `rwMotorTorque`) when a spacecraft has `"reaction_wheel"` actuators.
  Sensors (`star_tracker`/`imu`/`coarse_sun_sensor`/`magnetometer`) attach
  independently of `fsw_mode` since they read truth state/SPICE/the
  magnetic-field model directly. `"thruster"`/`"magnetic_torque_rod"`
  actuators and `locationPointing`'s `target_body` option are schema-valid
  but raise a specific, actionable error rather than being silently
  ignored -- see `fsw.py`'s module docstring for the full scoping list and
  exactly which example script each call sequence was copied from.
* **`missionstudio/engine/vizard.py`** -- the "no embedded 3D viewer, but
  good Vizard visualization with valuable live simulation data"
  requirement: wraps `vizSupport.enableUnityVisualization()` (live-stream
  or `.bin` playback file), passes reaction-wheel effectors through so
  Vizard draws its native per-wheel speed bars, and draws every ground
  station via `vizSupport.addLocation()` (lat/lon/alt + elevation-mask
  cone) so `locationPointing`'s target geometry is actually visible.
* **`ResultSet` now carries Phase 2 series** for any spacecraft that has
  them configured: `{name}.attitude_sigma_BN`, `{name}.body_rate_omega_BN_B`,
  `{name}.sun_heading_body`, `{name}.control_torque`, `{name}.rw_speeds`,
  and one `{name}.sensor.{sensor_name}` series per attached sensor --
  always in addition to, never instead of, the Phase 0 position/velocity
  series.
* **GUI**: `spacecraft_editor.py` gained a tabbed dialog (Orbit/mass,
  Sensors/actuators, Attitude control) backed by the new
  `gui/sensor_actuator_editor.py` (a generic Add/Edit/Remove list widget
  shared by sensors and actuators, since their shape is identical --
  `params` is edited as raw JSON text rather than a bespoke form per kind,
  since the schema deliberately keeps `params` an open dict). A real bug
  was fixed along the way: editing an existing spacecraft used to silently
  DROP its `sensors`/`actuators`/`fsw_mode`/`fsw_params`/`control_params`
  (the dialog built a brand new `SpacecraftConfig` without passing them
  through) -- harmless while nothing set them, a real data-loss bug the
  moment this phase's own editors did; fixed with a regression test. The
  Run menu gained a **Vizard...** action (`gui/vizard_dialog.py`) to pick
  disabled / save-a-playback-file / live-stream for the next run, plumbed
  through `RunWorker` into `SimulationService`.
* **CLI**: `missionstudio run` gained `--vizard-save-file`/
  `--vizard-live-stream` (mutually exclusive).

## What Phase 3 adds

* **Ground-station access analysis.** `engine.service.SimulationService`
  now builds a `groundLocation.GroundLocation` for EVERY
  `GroundStationConfig` in a scenario (not just ones a spacecraft's
  `locationPointing` mode targets), and calls the new
  `engine.fsw.add_access_analysis()` once every spacecraft exists so every
  station sees every spacecraft -- the standard access-analysis question.
  `ResultSet` gains four series per (station, spacecraft) pair:
  `{station}.access_to_{spacecraft}.has_access`/`.slant_range`/
  `.elevation`/`.azimuth`.
* **`missionstudio/engine/monte_carlo.py`** -- wraps
  `Basilisk.utilities.MonteCarlo` (`Controller`/`Dispersions`/
  `RetentionPolicy`, real native Basilisk infrastructure, not reimplemented
  here). `schema.scenario.MonteCarloConfig`/`DispersionConfig` describe a
  batch (`num_runs`, `thread_count`, `verbose`) and per-spacecraft
  dispersions (`dry_mass_kg` uniform/normal, `attitude_sigma_bn`
  uniform-random-attitude via `UniformEulerAngleMRPDispersion`) --
  deliberately NOT Cartesian position/velocity dispersion, since
  Basilisk's Cartesian dispersion classes replace each component with an
  ABSOLUTE random value rather than perturbing around the nominal orbit,
  which would silently produce a physically nonsensical result (see that
  module's docstring). `engine.service.SimulationService.build()` gained
  an `initialize` parameter so Monte Carlo can apply dispersions BEFORE
  `InitializeSimulation()` runs (applying them after would silently have
  no effect, since `Reset()` would already have latched the un-dispersed
  values). `missionstudio monte-carlo` (CLI) and Run > **Run Monte
  Carlo...** (GUI, via the new `gui/monte_carlo_editor.py` scenario-form
  section) both drive it.
* **`packaging/`** -- `build_wheel.sh`/`install.sh`/`missionstudio.desktop.in`,
  genuinely built and run in this sandbox (see the honesty note above and
  `packaging/README.md` for two real bugs found and fixed this way: a
  missing scenario data file in the wheel, and a `./build/`-directory
  import-shadowing bug in repeated builds).

## What Phase 4 adds

Driven directly by feedback from actually using the Phase 3 GUI:

* **Vizard's default view is now Earth-centered with the orbit visible**,
  not locked onto the spacecraft with no context. `engine.vizard`'s
  `VizardRequest` gained `camera_target` (defaults to the scenario's
  central body) and `show_orbit_lines` (osculating + true trajectory
  lines, on by default), set via `VizSettings.mainCameraTarget`/
  `orbitLinesOn`/`trueTrajectoryLinesOn` -- `enableUnityVisualization()`
  itself doesn't expose these. Configurable from the GUI's Vizard dialog
  or `--vizard-camera-target`/`--vizard-no-orbit-lines` (CLI).
* **Live feedback while a run is in progress.** `gui.main_window` used to
  show only a static "Running..." status-bar string with no other
  indication anything was happening. Run Simulation and Run Monte Carlo
  now show a busy indicator (indeterminate progress bar + elapsed-time
  label) and disable every Run-menu action until the worker finishes --
  Basilisk exposes no per-step/per-run progress callback to drive a real
  percentage, so this is deliberately indeterminate rather than a
  fabricated number.
* **Mean anomaly as a classical-elements orbit input.** `OrbitIC` gained
  `anomaly_type` (`"true"`/`"mean"`, default `"true"` for backward
  compatibility) and `mean_anomaly_deg`; `engine.service` converts mean to
  true anomaly via Kepler's equation (`orbitalMotion.M2E`/`E2f`) before
  calling `elem2rv`, which only accepts true anomaly. The GUI orbit editor
  exposes this as a combo box next to the angle field.
* **Real power budget.** `schema.scenario.PowerConfig` (optional, per
  spacecraft) wires Basilisk's actual `simpleSolarPanel`/
  `simplePowerSink`/`simpleBattery`/`eclipse` modules into
  `engine.service` -- the same pattern `../missionAnalysis/power_budget.py`
  already uses -- so generated power depends on the real simulated
  attitude (panel-normal-to-sun angle) and eclipse state, not a flat duty
  cycle. `ResultSet` gains `{spacecraft}.battery_charge` [W\*hr] and
  `{spacecraft}.battery_net_power` [W] per spacecraft that opts in; no
  per-subsystem (instrument/downlink) load gating is modeled yet, only a
  constant bus load, since missionStudio has no EO-payload data model to
  gate against (unlike `../missionAnalysis`).
* **Downlink RF link-margin estimate.** `schema.scenario.RFLinkConfig`
  (optional, per spacecraft) plus two new `GroundStationConfig` fields
  (`rx_antenna_gain_dbi`, `system_noise_temp_k`) feed the new
  `engine.link_budget` module -- a simplified free-space-path-loss Eb/N0
  budget ported directly from `../missionAnalysis`'s
  `_rf_link_margin_db()`. It is evaluated against the REAL simulated slant
  range from Phase 3's access analysis (not a worst-case estimate), giving
  `{station}.access_to_{spacecraft}.link_margin_db` in `ResultSet` --
  `NaN` outside access windows, since there's no link (and so no
  meaningful margin) when there's no access. Like the missionAnalysis
  original, this is a reported ESTIMATE only (no atmosphere/rain/
  pointing-loss/coding-gain terms) and does not feed back into simulated
  physics anywhere.
* **Orbit-maintenance / station-keeping automation, with delta-V and
  propellant bookkeeping.** `schema.scenario.StationKeepingConfig`
  (optional, per spacecraft) wires the new `engine.orbit_maintenance`
  module -- `StationKeepingController`, ported from `../missionAnalysis`'s
  `AltitudeKeepingController` -- into `engine.service`: a dedicated
  `extForceTorque` effector fires a continuous prograde reboost burn
  whenever a smoothed altitude estimate decays `deadband_km` below
  `target_altitude_km`, gated off during eclipse and once propellant is
  depleted. Propellant use is tracked via the rocket equation
  (explicit-Euler) and fed back into the spacecraft's simulated mass every
  tick, so thrust-to-mass stays physically consistent as it burns off --
  see `SpacecraftConfig.dry_mass_kg`'s docstring for how that field's
  meaning sharpens once `station_keeping` is set (it becomes the mass
  *without* propellant; the initial simulated mass becomes
  `dry_mass_kg + station_keeping.propellant_kg`). `ResultSet` gains
  `{spacecraft}.station_keeping.altitude` (raw + smoothed),
  `.burn_on`, `.propellant_remaining`, and `.delta_v` (cumulative);
  `missionstudio run` also prints a one-line delta-V/propellant-used
  summary per spacecraft so the headline numbers don't require opening a
  CSV. This needs something actually decaying the orbit to have any
  effect -- with only point-mass gravity (the default), altitude never
  decays and the burn never fires; enable `SpacecraftConfig.enable_drag`
  for a station-keeping scenario. Shares the same eclipse model
  `PowerConfig` uses when both are configured on the same spacecraft.
* **Constellation design: a Walker-pattern generator.** The new
  `engine.constellation` module ("user supplies the requirement, the tool
  designs the constellation") turns a handful of high-level numbers --
  total satellite count, number of planes, Walker phasing factor,
  altitude, inclination -- into a full set of `SpacecraftConfig`s with
  every satellite's orbital elements pre-computed via the standard
  Walker-Delta/Walker-Star RAAN/mean-anomaly formula (Vallado; Wertz's
  SMAD). Every generated satellite is a deep copy of ONE template
  spacecraft the user configures the normal way (mass, sensors, actuators,
  power, station-keeping, RF link, ...) -- only `name`/`orbit` differ, so
  designing a 12-satellite constellation is exactly as much data entry as
  designing one satellite. Pure orbital mechanics, no Basilisk import
  (central-body radii for the altitude-to-semi-major-axis conversion are
  copied from Basilisk's own `astroConstants.h`, so they match what
  `engine.service` actually simulates). Available from the GUI (spacecraft
  list's new "Generate Walker constellation..." button -- central body is
  read from the scenario, not independently selectable, so it can't drift
  out of sync with what actually gets simulated) and the CLI
  (`missionstudio generate-constellation`, `--append` to add to an
  existing scenario instead of replacing its spacecraft).
* **Constellation-wide phasing maintenance, with its own delta-V and
  propellant bookkeeping.** `schema.scenario.PhasingKeepingConfig`
  (optional, per follower spacecraft) wires
  `engine.orbit_maintenance.PhasingKeepingController` -- ported from
  `../missionAnalysis`'s controller of the same name -- to hold a
  follower's along-track separation from a `chief_spacecraft` at a target
  value (optionally stepped through a schedule of several values over the
  mission, e.g. tightening a formation from 1000 km to 100 km every few
  months) via a drift-orbit maneuver: a small temporary semi-major-axis
  offset, natural drift, then a restoring burn -- the same technique a
  differential corrector (GMAT's Target/Vary/Achieve) would normally
  automate, done here as a direct two-body calculation re-evaluated every
  tick. REQUIRES `station_keeping` to also be set on the same spacecraft:
  phasing and altitude-keeping share ONE physical thruster and propellant
  tank (this config deliberately has no `thrust_n`/`isp_s`/`propellant_kg`
  fields of its own -- `engine.service` reads those off `station_keeping`
  instead), with altitude-keeping taking priority whenever both want to
  fire on the same tick. `ResultSet` gains
  `{spacecraft}.phasing_keeping.separation_error`/`.state`/`.delta_v`
  (its own delta-V, tracked separately from -- but drawing from the same
  shared tank as -- `station_keeping`'s); `missionstudio run`'s
  delta-V/propellant summary line now includes a breakdown when both are
  configured. Not yet wired into `engine.constellation`'s Walker generator
  automatically (each follower's chief/target-separation still needs
  setting up by hand in the spacecraft editor after generating the
  constellation) -- a natural follow-on if that manual step turns out to
  be tedious in practice.
* **Live Vizard data panels**, responding directly to "the live-stream of
  the simulation with Vizard is not really understandable, improve" --
  three real, already-simulated data feeds now drive native Vizard HUD
  elements (`engine.vizard`, extended), not a static snapshot or an
  analytical estimate:
  * **Battery state of charge**, for any spacecraft with `PowerConfig` --
    a `GenericStorage` bar panel wired straight to that spacecraft's
    `simpleBattery.SimpleBattery.batPowerOutMsg`.
  * **Station-keeping propellant remaining**, for any spacecraft with
    `StationKeepingConfig` -- a second `GenericStorage` panel, fed by a
    new `FuelTankMsgPayload` output
    `engine.orbit_maintenance.StationKeepingController` now publishes
    specifically for this (that controller still doesn't use a Basilisk
    `fuelTank` state effector for the actual physics -- see its own
    docstring).
  * **Ground-station access windows** -- one `GenericSensor` marker per
    (station, spacecraft) pair Phase 3's access analysis tracks, changing
    color live between "no access"/"access" as the real, already
    -simulated `hasAccess` flag changes, via a small bridge module this
    phase adds (`GenericSensor` takes an integer mode, not a boolean, so
    something has to republish `hasAccess` as one -- see `engine.vizard`'s
    docstring for exactly how and why 0/2, not 0/1, are the two values
    used).

  The battery/propellant panel pattern is copied line-for-line from a
  real, shipped Basilisk example
  (`examples/MultiSatBskSim/scenariosMultiSat/scenario_StationKeepingMultiSat.py`);
  the access-window bridge composes verified pieces
  (`examples/scenarioGroundLocationImaging.py`'s `GenericSensor`/
  `DeviceCmdMsgPayload` wiring, `../missionAnalysis/attitude_controllers.py`'s
  `AccessMsgReader` usage) in a way that's this module's own, not copied
  from one example -- like the Phase 4 camera/orbit-line work, none of
  this has been checked against a real running Vizard display (no display
  in this development sandbox). A live **link-margin** panel was
  considered and deliberately NOT built: Vizard's `GenericStorage` only
  accepts Battery/DataStorage/FuelTank-shaped messages, and forcing a dB
  margin value through the DataStorage shape would need a fabricated
  adapter message with no natural floor/ceiling -- the link-margin numbers
  stay exactly where they already were (the plotted/exported
  `.link_margin_db` series from `engine.link_budget`), which is the
  honest choice over a misleading gauge.

`PowerConfig`, `RFLinkConfig`, `StationKeepingConfig`, and
`PhasingKeepingConfig` all default to `None` (off) on every existing
scenario -- turning any one on is the only input needed; the GUI's new
"Power / propulsion / link budget" spacecraft-editor tab (its "Phasing
keeping" group reads the chief-spacecraft choice from the OTHER
spacecraft already in the scenario, not a free-text field, so it can't
name one that doesn't exist) and the ground-station editor's two new
fields are pre-filled with reasonable placeholder defaults, matching this
phase's "user only supplies numbers, the tool does the rest" design goal.

Four real bugs were found by a full codebase audit after this phase
shipped, and fixed (all visible in `git log` for the files below, not
swept under the rug):

* **`SpacecraftConfig.enable_drag`/`enable_srp` were schema-valid and
  documented above as functional (see the station-keeping bullet's
  "enable `enable_drag`" instruction) but were never actually wired into
  `engine.service` -- station-keeping's reboost burn could never fire on
  any scenario, since nothing ever decayed the orbit.** Fixed: `enable_drag`
  now wires `engine.spaceweather`'s resolver into `spaceWeatherData` ->
  `msisAtmosphere` -> `zeroWindModel` -> a per-spacecraft
  `dragDynamicEffector`, ported from
  `../missionAnalysis/run_constellation_mission.py`'s verified chain;
  `enable_srp` wires a per-spacecraft `radiationPressure` effector off the
  same eclipse model `PowerConfig`/`StationKeepingConfig` already share.
  Both are Earth-only (NRLMSISE-00 has no other-body atmosphere model
  here), matching the spherical-harmonics-gravity precedent.
* **`_AccessIndicatorBridge` (the Live Vizard access-window indicator
  above) could be garbage-collected while still registered on the
  Basilisk sim task** -- a SWIG-director use-after-free (the Python side
  of a custom `SysModel` must outlive its C++ task registration, same
  requirement `StationKeepingController`/`PhasingKeepingController`
  already followed), surfacing as a `basic_string::_M_create` crash deep
  in an unrelated libstdc++ call, well after the actual corruption.
  Fixed: `engine.vizard`/`engine.service` now retain it the same way.
* **Editing an existing spacecraft with `enable_drag`/`enable_srp` already
  set silently reset them to the schema defaults** -- the spacecraft-editor
  dialog has no UI for these fields (by design, per above) but also never
  carried them through from the original config in `to_dataclass()`, unlike
  every other not-yet-editable field. Fixed.
* **The phasing-keeping chief-spacecraft combo, and the Monte Carlo
  dispersion spacecraft combo, silently fell back to whichever spacecraft
  happened to be first** whenever the stored name didn't match a current
  spacecraft (e.g. renamed after the config was saved) -- re-targeting a
  controller or dispersion at the wrong spacecraft with no visible
  indication. Fixed: the stale name is now surfaced as its own selectable
  entry and round-tripped as-is instead.

## What Phase 5 adds

Driven directly by feedback from actually using the Phase 4 GUI + engine
(this phase is in progress; bullets are added as pieces land):

* **Result plots/CSV export now include osculating Keplerian elements**,
  not just inertial position/velocity. `engine.service` computes semi-major
  axis, eccentricity, inclination, RAAN, argument of periapsis, and true
  anomaly at every recorded sample (`orbitalMotion.rv2elem`, the exact
  inverse of the classical-elements orbit-IC conversion already used
  elsewhere in this file) and adds them to `ResultSet` as
  `{spacecraft}.orbit_elements.{semi_major_axis,eccentricity,inclination,
  raan,arg_periapsis,true_anomaly}` -- one series per element (mixed units:
  m/-/rad), matching the existing convention for e.g.
  `station_keeping.burn_on`/`.delta_v`. `gui.results_widget`/the CLI's CSV
  export need no changes for these to show up -- both are already driven
  generically by whatever `ResultSet.series` contains. Near-circular
  and/or near-equatorial orbits have an inherent singularity in RAAN/
  argument of periapsis/true anomaly (see
  `engine.service._osculating_elements`'s docstring) -- not a bug, just
  how classical elements behave at those limits.
* **Sensor/actuator/FSW-mode setup is no longer a blank JSON box with zero
  guidance.** User feedback: configuring a spacecraft's sensors, actuators,
  and attitude-control mode was "confusing and not beginner friendly" --
  each dialog offered only a Kind/mode combo and an empty `{}` params box,
  so a user had to already know (by reading `engine/fsw.py`'s source)
  which JSON keys a given kind needs, their units, and which are required.
  A missing required key (e.g. `coarse_sun_sensor`'s `nHat_B`,
  `reaction_wheel`'s `gsHat_B`, `locationPointing`'s
  `target_ground_station`) wasn't caught there either -- only much later,
  decontextualized, when the whole spacecraft dialog's
  `SpacecraftConfig.validate()` ran (sensors/actuators) or not at all
  until `Run Simulation` actually failed deep inside `engine.fsw`
  (FSW mode). Fixed in both `gui.sensor_actuator_editor` and
  `gui.spacecraft_editor`'s FSW tab: a per-kind/per-mode help label (key
  name, required/optional, units, one-line description) that updates live
  as the Kind/FSW-mode combo changes; a new spacecraft/sensor/actuator
  starts pre-filled with a working example instead of `{}`; a "Reset to
  template" button refills the params box for the CURRENTLY selected
  kind/mode on demand (switching kind never silently overwrites what's
  already typed, to avoid destroying in-progress edits); and both dialogs
  now check required keys themselves and raise an immediate, specific
  error naming exactly what's missing, right where the params box is.
  `SUPPORTED_ACTUATOR_KINDS`'s `"thruster"`/`"magnetic_torque_rod"`
  (schema-valid but not wired up -- see the Phase 0 section above) and
  `locationPointing`'s `fsw_params["target_body"]` option now show an
  explicit in-dialog warning instead of silently accepting a
  configuration that fails only when the simulation actually runs.
* **Sensor/actuator body-frame direction vectors get dedicated X/Y/Z spin
  boxes**, not a bare 3-element array inside the params JSON box -- see
  `gui.sensor_actuator_editor`'s module docstring for exactly why
  DIRECTION (not position) is the one thing about sensor/actuator
  "placement" that actually affects the physics these Basilisk modules
  simulate here, plus a Normalize button since Basilisk does not
  renormalize a non-unit vector itself.
* **Reusable spacecraft "bus" templates.** A brand-new spacecraft used to
  start from `SpacecraftConfig()`'s bare dataclass defaults (100 kg, flat
  10 kg*m^2 inertia, no sensors/actuators/power/attitude control) -- a
  placeholder, not anything resembling a real vehicle. The new
  `engine.spacecraft_templates` module (pure schema data, no Basilisk
  import, same split as `engine.constellation`) ships three starting
  points -- a passive 3U CubeSat (drag/SRP enabled, no ADCS, good for
  orbit-only delta-V/lifetime studies), a 3-axis-stabilized 3U CubeSat
  (coarse sun sensor + 3 reaction wheels + `sunSafePoint` + a small power
  budget), and a 100 kg ESPA-class smallsat (star tracker + coarse sun
  sensor + 3 reaction wheels + `inertial3D` + a ~1 m-class power budget) --
  each internally consistent and validated, with rounded,
  order-of-magnitude-reasonable numbers (never a fabricated-precision
  datasheet figure; see that module's docstring). The spacecraft list's
  new "New from template..." button (next to "Add...") opens a small
  picker, then the ordinary `SpacecraftEditorDialog` pre-filled with the
  chosen template so the user still sets the actual name/orbit/anything
  else themselves, exactly like editing any other spacecraft.
* **Custom 3D models in Vizard.** The last piece of "adequately represent
  the correct placement" feedback: `SpacecraftConfig.vizard_model_path`
  (plus `vizard_model_offset_m`/`_rotation_deg`/`_scale`) wires
  `Basilisk.utilities.vizSupport.createCustomModel()` in, replacing a
  spacecraft's default cube icon with a real `.obj` mesh (or Vizard's
  `CUBE`/`CYLINDER`/`SPHERE` primitives) at a chosen body-frame offset/
  rotation/scale. PURELY COSMETIC -- it changes nothing about simulated
  physics (mass, drag/SRP area, etc. are unaffected either way); the
  spacecraft editor's new "Vizard model (cosmetic)" tab says so up front,
  same "don't offer a control that looks like it does something it
  doesn't" discipline as everywhere else in this app.
* **Orbit-only simulation mode, plus a constant-frame thrust maneuver.**
  `Scenario.simulation_mode` ("full_attitude", the default and everything
  this schema always supported, or "orbit_only") is the first field in
  the scenario editor's form, chosen before anything else per the
  feature request this responds to. "Orbit only" is a stricter,
  beginner-friendly mode for pure orbit-propagation questions (delta-V
  budgets, orbit lifetime, station-keeping cadence, ...): no spacecraft
  may have `fsw_mode`/`sensors`/`actuators`/`power` set (`Scenario.
  validate()` rejects it with a specific per-field error), so the
  spacecraft editor hides the Sensors/actuators and FSW tabs and the
  Power budget group while it's selected -- the spacecraft is simulated
  as a cannonball with `drag_area_m2`/`srp_area_m2` (which finally got a
  real editor too, on the Orbit/mass tab -- previously round-tripped only,
  with no UI to actually SET them anywhere) as its average cross-section.
  `station_keeping`/`phasing_keeping`/the new `constant_thrust` remain
  available in EITHER mode, since none of them need attitude knowledge.

  `SpacecraftConfig.constant_thrust` is new: a continuous (always-on),
  constant-magnitude thrust with a fixed direction in a ROTATING orbit
  frame -- VNB (velocity/orbit-normal/binormal) or RTN (radial/
  transverse/orbit-normal), re-evaluated every simulation tick from the
  spacecraft's current state (`engine.orbit_maintenance._vnb_basis`/
  `_rtn_basis`) -- rather than a direction fixed in the inertial frame,
  which would drift relative to the orbit as the spacecraft moves. Delta
  -V/propellant bookkeeping mirrors `StationKeepingConfig`'s own rocket
  -equation approach (station-keeping's burn model itself is UNCHANGED --
  still a fixed prograde reboost -- this is a separate, independent
  mechanism with its own propellant tank, addable alongside station
  -keeping on the same spacecraft). `missionstudio run` prints a
  "Constant-thrust summary" line per spacecraft, same idea as the
  existing station-keeping summary.
* **A real visual theme, an app icon, a toolbar, and assorted UI polish.**
  Direct user feedback: "looks very unfinished... not very intuitive and
  comfortable". The app previously ran on whatever the platform's native
  Qt style happened to render, with no icon and no toolbar. Now:
  * `gui/theme.py` -- one QSS stylesheet + palette (`apply_theme()`,
    called once from `gui/app.py`), on top of Qt's "Fusion" base style
    (the one built-in style that renders identically, and predictably
    styleable via QSS, across Linux/macOS/Windows). A small, consistent
    color system (one neutral slate scale + one accent blue, reused
    everywhere -- focus rings, selection highlight, the primary action
    button, progress bars) rather than per-widget rules picked ad hoc.
    Pure presentation layer: no widget's behavior, signals, or layout
    structure changed because of it.
  * `gui/icons.py` -- the app icon, drawn procedurally with `QPainter`
    (a central body + an inclined orbit ellipse + a satellite dot) rather
    than shipped as a bitmap asset, so there's no binary file to keep in
    sync with the theme's colors. Used as the window/taskbar icon
    (`app.py`) and, rendered to a real PNG under the standard XDG
    hicolor icon theme location, the Linux desktop entry's icon
    (`packaging/install.sh`, closing a gap that `Icon=missionstudio` was
    falling back to a generic icon).
  * `MainWindow` gained a toolbar (New/Open/Save, Run Simulation/Monte
    Carlo/Vizard/Check Kernels) using the SAME `QAction` instances the
    menu bar already had -- one signal connection each, so toolbar and
    menu always agree, including which actions are disabled while a run
    is in flight. "Run Simulation" is visually the primary action
    (accent-colored), the same "one obvious main button" convention a
    web app would use.
  * The results panel used to be a blank white plot with no explanation
    before any run -- now shows "Run a simulation to see results here".
  * `SpacecraftEditorDialog`'s five tabs used to share ONE height (a
    `QTabWidget` sizes every tab to fit whichever page is tallest, a
    real, easy-to-miss Qt behavior -- the "Power / propulsion / link
    budget" tab's five stacked groups forced "Orbit / mass", a third the
    height, to render with a large dead-space gap, and pushed the whole
    dialog's natural size to over 1000px tall). Caught by actually
    rendering the dialog and looking at it, not from reading the layout
    code. Fixed: each tab now scrolls independently (`_scrollable()`),
    same pattern `gui.scenario_editor.ScenarioEditorWidget`'s own
    top-level form already used.
  * The Monte Carlo group box was labeled "Monte Carlo (Phase 3)" --
    internal development-phase numbering with no meaning to an end user,
    now just "Monte Carlo".
* **Fixed a silent mass-bookkeeping bug found by a full-codebase audit.**
  `StationKeepingController`/`PhasingKeepingController`/
  `ConstantFrameThrustController` each used to recompute an ABSOLUTE
  `scObject.hub.mHub = dryMass + propellant` every tick, from their own
  construction-time-captured belief about the spacecraft's mass. That's
  fine in isolation, but two real, previously-silent failure modes fall out
  of it: (1) `station_keeping` and the new `constant_thrust` are an
  explicitly supported combination on the same spacecraft, and whichever
  controller's `UpdateState` happened to run last each tick would overwrite
  `hub.mHub`, discarding the other controller's propellant burn entirely;
  (2) a Monte Carlo `dry_mass_kg` dispersion writes directly to `hub.mHub`
  before any controller's first tick (see `engine.monte_carlo`'s "why
  `SimulationService.build(initialize=False)`" docstring section) -- the
  very first `UpdateState` call would then silently reset that dispersed
  mass back to the nominal, undispersed value, quietly defeating the
  dispersion for the rest of the run. Fixed at the root: all three
  controllers now read the spacecraft's CURRENT total mass at the top of
  each tick and subtract only what THIS tank burns THIS tick -- a
  self-contained delta, order-independent no matter how many other
  controllers or a prior dispersion already touched the same mass. The
  shared fix lives in a new `engine.propellant_bookkeeping.
  apply_propellant_burn()` (pure math, no Basilisk import -- same "pure
  math, no Basilisk" split as `engine.constellation`/
  `engine.spacecraft_templates`, and for the same reason:
  `engine.orbit_maintenance` itself can never be unit-tested in a sandbox
  without a Basilisk build, so factoring the actual arithmetic out is what
  makes `tests/test_propellant_bookkeeping.py`'s regression coverage for
  this bug possible at all).
* **A live-updating Results plot.** Previously the plot stayed on "Run a
  simulation to see results here" for the entire duration of a run, then
  jumped straight to the finished result -- no feedback beyond the
  indeterminate busy bar for however long the run took. `engine.service.
  SimulationService` gained `run_live(on_progress, live_step_s=None)`: a
  variant of `run()` that executes the simulation in small time chunks
  (repeated `ConfigureStopTime()`/`ExecuteSimulation()` pairs -- a
  documented, supported Basilisk pattern, since `ExecuteSimulation()`
  always resumes from wherever it last stopped rather than restarting)
  instead of one uninterrupted call, calling `on_progress(partial_result,
  fraction_complete)` after each chunk. Recorders keep accumulating
  samples across chunks exactly as they would across one call, so each
  chunk's result is genuinely "whatever has been logged so far", not a
  separate/approximate bookkeeping path from `run()` -- confirmed by
  `tests/test_service_run_live.py`, which checks a chunked `run_live()`
  run reproduces a plain `run()` run's final position/velocity exactly.
  The new "Live Plot" toggle (Run menu and toolbar, on by default)
  controls whether `gui.run_worker.RunWorker` drives the run through
  `run_live()` (emitting a new `progress` Qt signal per chunk, connected
  to `gui.results_widget.ResultsWidget.set_live_result()`) or the
  original one-shot `run()`; the status bar's busy indicator also becomes
  a real 0-100% progress bar instead of the indeterminate one whenever
  Live Plot is on, since `run_live()` is the one case where a genuine
  completion fraction exists. `set_live_result()` deliberately never
  rebuilds the series dropdown once it already holds the running result's
  series names (which are fixed from the first chunk -- only the amount
  of data grows), so watching a live run doesn't keep resetting whichever
  series the user is currently looking at.
* **Another full-codebase audit, this time with real fan-out coverage.**
  A single-pass review of the live-plot/mass-bookkeeping commits found
  and fixed two issues in `engine.service.run_live()`: a scenario whose
  `duration_days` is small enough to round to 0 ns via `macros.sec2nano()`
  (schema-valid -- `sim_settings.validate()` only requires `> 0`) used to
  raise a bare `ZeroDivisionError` computing `fraction_complete` instead
  of a clear error; and `_LIVE_DEFAULT_FRAMES` was lowered from 200 to 60,
  since each live callback's `_extract_results()` redoes O(samples-so-far)
  work from the FULL recorder history rather than just the new samples,
  so total extraction cost scaled with frame count. A follow-up pass
  fanned out across the rest of the codebase (GUI layer, remaining engine
  modules, schema/CLI/packaging) and found six more real, independently
  -verified bugs:
  * `gui.main_window._on_run_finished` called `ResultsWidget.set_result()`
    instead of `set_live_result()` -- so the moment a live-watched run
    actually finished, whichever series the user had selected to watch
    snapped back to the first one, undoing the whole point of
    `set_live_result()`'s selection-preserving design at the one moment
    the final data matters most.
  * `gui.kernel_status_widget.KernelStatusWidget.refresh()` had no
    re-entrancy guard: `MainWindow`'s "Check Kernels" menu/toolbar action
    calls it directly, independent of `refresh_button`'s own disabled
    -while-fetching state, so triggering it again mid-fetch reassigned
    `self._worker`, dropping the only Python reference to the
    still-running (unparented) `QThread` -- a real Qt crash risk ("QThread:
    Destroyed while thread is still running"). Now a no-op while a fetch
    is already in flight.
  * `gui.main_window.MainWindow.closeEvent` never checked whether
    `_run_worker`/`_mc_worker` was still running before accepting the
    close -- starting a run doesn't mark the scenario dirty, so closing
    the window mid-run (no cooperative-cancellation hook exists for a
    synchronous `SimulationService.run()`/`run_live()`/`run_monte_carlo()`
    call) could tear down the process out from under a live `QThread`.
    Now refuses to close (with a clear message) while either worker is
    running.
  * `engine.spaceweather.validate_file()`'s `covers_range` check compared
    a date-only (midnight) timestamp parsed from the CSV's last row
    against a full `end_utc` datetime that can carry a non-zero
    time-of-day (`scenario.epoch_utc` isn't required to be midnight) --
    so a CelesTrak file that genuinely covered the scenario's end date
    was often misclassified as not covering it, forcing an unnecessary
    fallback to synthetic (fabricated) space weather. Fixed to compare
    calendar dates.
  * `engine.time_system.utc_iso_to_spice_string()` hardcoded a literal
    `.000` milliseconds field instead of deriving it from `epoch_utc`,
    silently discarding any sub-second precision a user specified.
  * `cli.py`'s `cmd_spaceweather_resolve` had no exception handling
    around `sw.resolve()` (every other command in the file does), and
    `engine.monte_carlo.run_monte_carlo()`'s `archive_dir.mkdir(...)`
    sat outside its own `try`/`except` -- both let a real, reachable
    failure (a missing `local_file_path`; `--archive-dir` already
    existing as a plain file) surface as a raw traceback instead of this
    project's "ERROR: ..." + specific exit code convention. Both now
    report cleanly.
  * `packaging/install.sh` picked the just-built wheel with
    `ls | tail -n1` (lexicographic order) -- since `build_wheel.sh` never
    cleans its output directory, re-running `install.sh` against the same
    `--prefix` after a version bump left old and new wheels side by side,
    and `"...-1.10.0..."` sorts BEFORE `"...-1.9.0..."` as a string,
    silently installing the OLDER version. Fixed to pick by modification
    time (`ls -t`) instead, so the wheel `build_wheel.sh` just built is
    always the one selected.
* **A dedicated "Propagation setup" window, and an explicit on/off switch
  for every perturbation.** Direct feedback: gravity/integrator/space
  -weather settings were three separate, always-visible group boxes
  buried in the middle of the main scenario form, and spherical-harmonics
  gravity had no explicit enable control -- unchecking it meant zeroing
  out (and losing) whatever degree/order the user had typed. Fixed:
  * New `gui.propagation_setup_dialog.PropagationSetupDialog` -- one
    window for everything that governs how a scenario's orbits
    propagate: central body, gravity model, the numerical integrator/
    step/duration, and the space-weather source atmospheric drag reads.
    `gui.scenario_editor.ScenarioEditorWidget`'s main form now shows a
    compact read-only summary of the current settings plus a single
    "Edit Propagation Setup..." button that opens it, replacing the three
    scattered group boxes.
  * Every perturbation this app actually wires up in `engine.service` now
    has its own explicit on/off control: a new "Enable spherical
    -harmonics gravity" checkbox (GUI-only concept -- `schema.scenario.
    GravityConfig` still has just the one `central_body_degree` field,
    `0` still means point-mass; the checkbox folds back into it on OK,
    but the spin box's value is never reset by unchecking it, so
    re-checking it brings the same degree/order right back); third-body
    point-mass perturbers (already a per-body checkbox list, moved into
    the new dialog unchanged); atmospheric drag and solar radiation
    pressure (`enable_drag`/`enable_srp`, already per-spacecraft -- see
    below for why). The harmonics checkbox is also auto-disabled (and
    unchecked) whenever the central body isn't Earth, since
    `engine.service.build()` only has gravity-field data (GGM03S) for
    Earth -- the GUI can no longer construct that invalid combination in
    the first place, rather than letting the user discover it only when
    a run fails.
  * **Cannonball (orbit-only) mode already exposed every spacecraft
    parameter the active perturbations need** -- confirmed, not new:
    `dry_mass_kg`, `drag_coeff`/`drag_area_m2`, and `srp_coeff`/
    `srp_area_m2` all live on `SpacecraftEditorDialog`'s "Orbit / mass"
    tab, which (unlike Sensors/actuators/FSW/Power) is never hidden in
    "orbit_only" mode, from Phase 5's earlier drag/SRP work.
  * Caught while rendering the new dialog and looking at it, not from
    reading the layout code (same discipline as every other UI bug this
    project has found this way): a word-wrapped `QLabel`'s `sizeHint()`
    reports the width needed to lay its text out on ONE line unless
    something else constrains it -- without a cap, the dialog's intro
    label alone stretched the whole window to ~1360px wide.
* **Another audit round, two more real bugs found and fixed.** A
  fan-out re-sweep after the Propagation Setup work landed:
  * `schema.scenario.GravityConfig.validate()` never checked that
    spherical-harmonics gravity (`central_body_degree > 0`) is only wired
    up for Earth -- `engine.service.SimulationService.build()` already
    rejects any other central body with that combination, but only at
    simulation time. Without a matching schema-layer check,
    `missionstudio validate`/`Scenario.save()` (both deliberately
    Basilisk-independent, meant as an early correctness check) gave a
    clean bill of health to a scenario guaranteed to fail the moment it
    was actually run. Now rejected at the schema layer too.
  * `engine.monte_carlo`'s `dry_mass_kg` dispersion wrote its generated
    value ABSOLUTELY to `hub.mHub` (Basilisk's dispersion framework has
    no notion of "add this on top of what's already there") -- but
    `hub.mHub` is `dry_mass_kg + propellant` for any spacecraft with
    `station_keeping`/`constant_thrust` configured, not just
    `dry_mass_kg` (see `SpacecraftConfig.dry_mass_kg`'s own documented
    contract). A `dry_mass_kg` dispersion on such a spacecraft was
    therefore silently dispersing the TOTAL mass under that name --
    bounds picked to disperse just the dry mass actually dispersed dry
    mass + propellant, quietly shrinking the effective dry-mass spread by
    exactly the propellant amount on every run, with the station-keeping
    controller's own (unaffected, independently-tracked) propellant
    belief silently inconsistent with the result from tick zero. Fixed
    with two small dispersion subclasses
    (`_DryMassPlusPropellantUniformDispersion`/
    `_DryMassPlusPropellantNormalDispersion`) that add the target
    spacecraft's configured propellant back on top of the generated
    dry-mass value before it's written to `hub.mHub`, matching
    `service.py`'s own `initial_mass_kg` computation exactly. Also fixed,
    same audit: `migrations.migrate()`'s `schema_version` type check used
    `isinstance(version, int)`, but `bool` is a subclass of `int` in
    Python, so a malformed `"schema_version": true` silently passed
    through instead of raising the same clear error every other malformed
    `schema_version` value gets.

## What Phase 6 (Mission Sequence architecture) adds -- landed

A GMAT/FreeFlyer-inspired **Resources / Mission Sequence / Output**
organization, requested directly: separate "what exists" (spacecraft,
gravity, ground stations, ... -- everything the schema already had) from
"what happens, in time order" (propagate, maneuver, assign, report,
conditionals) and "what a run produced". Explicitly NOT a port of GMAT's
or FreeFlyer's own object model -- the organizing idea (resources vs. a
time-ordered sequence) is what's borrowed; everywhere Basilisk's own
architecture is a better fit than copying either tool's shape (its native
event mechanism, its continuous feedback controllers, its message/recorder
architecture, its own Monte Carlo framework), this keeps using Basilisk's
own mechanism rather than reshaping it to look like GMAT/FreeFlyer.

This phase is landing in reviewable stages, matching its own plan: data
model first (this section), then an execution engine, then file-format/
GUI-sync work, then the GUI itself -- each stage additive, so every
existing scenario file and every existing test keeps passing unchanged at
every step (confirmed after each stage: the full suite's pass count only
ever grows).

**Data model (`schema/command.py`, `schema/references.py`,
`schema/validation.py`) -- landed:**

* `schema.command.Command`: one envelope dataclass (`kind`, optional
  `label`, `params` dict, `children` for `if`/`while` nesting) covering
  the minimum command set this phase scoped: `propagate` (duration/epoch/
  event-based stop conditions -- events deliberately limited to periapsis/
  apoapsis passage for now, meant to be built on Basilisk's own
  `SimulationBaseClass.EventHandlerClass` rather than a hand-rolled
  polling loop), `maneuver` (impulsive delta-V, inertial/VNB/RTN frame --
  VNB/RTN meant to reuse `engine.orbit_maintenance`'s already-written,
  already-tested `_vnb_basis`/`_rtn_basis` helpers), `assignment`,
  `report`, `if`/`while`, `script_block`. One envelope dataclass rather
  than one Python class per kind, matching the exact shape
  `SensorConfig`/`ActuatorConfig`/`fsw_params` already use in this schema
  for the same reason (very different per-kind shapes, no
  discriminated-union (de)serialization mechanism elsewhere in this
  schema to reuse). Targeting/optimization commands are explicitly out of
  scope for now, per this feature's own scoping decision.
* `Command.validate()` is a COLLECTING validator -- returns every problem
  found in a command (and its `children` subtree) as a list, each with an
  item path, rather than raising on the first one. `Scenario.validate()`
  (unchanged, still raise-fast, exactly as before this phase) now also
  walks `mission_sequence`, folding each command's collected errors into
  one combined message per command -- still raise-fast ACROSS commands,
  preserving that method's existing behavior/contract exactly.
  `schema.validation.validate_all(scenario)` is the genuinely
  fully-collecting entry point requested: every command's every problem,
  plus every dangling spacecraft/ground-station reference across the
  whole sequence, all at once -- stated plainly in its own docstring that
  the RESOURCE side of that same call is still at-most-one-message (since
  it delegates to the unchanged, raise-fast `scenario.validate()`
  rather than retrofitting ~15 existing resource validators into
  collecting ones, which was judged out of proportion to this change).
* `Scenario.mission_sequence: list[Command] = []` -- additive, empty by
  default, so it changes nothing about how any existing scenario file
  loads, validates, or runs; `engine.service.SimulationService.run()`/
  `run_live()` are untouched. Round-trips losslessly through the existing
  JSON format (`Command` is a plain dataclass, so `dataclasses.asdict()`
  -- already how `Scenario.to_dict()` works -- recurses through it with
  no extra code; only the read direction needed a hand-written
  `Command.from_dict()`, matching every other nested dataclass in
  `Scenario.from_dict()`). The existing JSON file format itself now
  reads as GMAT's `BeginMissionSequence` split in miniature -- every
  existing top-level field is "resources", the new `mission_sequence` key
  is the sequence -- without inventing a new text format.
* `schema.references`: `find_spacecraft_references()`/
  `find_ground_station_references()` (an empty list means "safe to
  delete" -- GMAT's own "delete refused, listing every referencing item"
  behavior, which this project's spacecraft/ground-station list widgets
  did not have before this: `_on_remove()` deleted unconditionally, with
  no reference check of any kind, confirmed by reading both before
  writing this) and `rename_spacecraft()`/`rename_ground_station()`
  (FreeFlyer's "rename symbol" behavior -- renames the resource AND
  every reference to it, atomically). Every reference site is hand-listed
  (`phasing_keeping.chief_spacecraft`, Monte Carlo `dispersion.
  spacecraft`, `fsw_params['target_ground_station']`, and every command
  kind/nesting depth that can name a resource) rather than found via
  generic reflection, matching this schema's own established style
  (explicit and auditable over generic) at the cost of needing a new
  entry here whenever a new reference site is added elsewhere.

**Verification:** 62 new tests (`tests/test_command.py`,
`tests/test_references.py`, `tests/test_validation.py`, plus additions to
`tests/test_scenario_schema.py`), all Basilisk-independent (this whole
layer has no Basilisk import) -- model round-trip (including through a
real `save()`/`load_scenario()` file round-trip, and an explicit
command-ordering/reordering check), reference-integrity (find/rename,
including references nested inside `if`/`while` and the dotted-path form
`assignment.target` uses), and collecting-validation (multiple bad
commands and multiple dangling references, all reported at once, not just
the first). Full suite after this stage: 430 passed, 22 skipped (was 366
passed/22 skipped before -- the 22 skips are unrelated, pre-existing
`requires_basilisk` tests; zero regressions, zero new skips, since this
stage adds no Basilisk-dependent code).

**Execution engine (`engine/mission_engine.py`) -- landed:**

* `MissionEngine(scenario, service=None).run() -> (ResultSet, CommandSummary)`
  walks `scenario.mission_sequence` against a real `SimulationService`,
  dispatching each `Command` by `kind`. Every Basilisk call sequence is
  copied from an actually-running official example or this checkout's own
  source, not written from memory (see the module's own docstring for the
  full citation list) -- most notably:
  * `propagate` (duration/epoch): repeated `ConfigureStopTime()`/
    `ExecuteSimulation()` pairs, `ConfigureStopTime()` taking an ABSOLUTE
    cumulative time (not a delta) -- `examples/scenarioOrbitManeuver.py`'s
    own comment on this, and already exercised by this project's own
    `SimulationService.run_live()`/`tests/test_service_run_live.py`.
  * `propagate` (event -- periapsis/apoapsis): Basilisk's native
    `SimBaseClass.createNewEvent(name, eventRate, eventActive,
    conditionFunction=..., terminal=True)`, copied from
    `examples/scenarioDragDeorbit.py`'s own terminal-event block. Detected
    as a sign change in radial velocity (`dot(r, v) / |r|`) rather than
    reconstructing true anomaly every check, capped by a generous
    duration-based safety multiplier so a trajectory that never reaches
    the event raises a clear `MissionEngineError` instead of hanging.
  * `maneuver` (impulsive delta-V, inertial/VNB/RTN): `scObject.dynManager.
    getStateObject(scObject.hub.nameOfHubPosition/nameOfHubVelocity)`
    fetched once, `simHelpers.EigenVector3d2np(velRef.getState())` to read
    the current velocity, plain numpy arithmetic (VNB/RTN via
    `engine.orbit_maintenance`'s already-tested `_vnb_basis`/`_rtn_basis`),
    `velRef.setState(...)` to apply it -- the exact pattern
    `examples/scenarioOrbitManeuver.py` itself uses for its two maneuvers.
* `assignment`/`report`/`if`/`while`/`script_block` have no Basilisk-API
  precedent -- this project's own design, deliberately narrow: `assignment`
  only varies a small, hand-listed whitelist of live controller parameters
  (`thrust_n`/`isp_s` on `station_keeping`/`phasing_keeping`/
  `constant_thrust`), not generic attribute access; `report` snapshots the
  CURRENT value of requested series (GMAT `Report`-command semantics, not
  the whole time history the `ResultSet` already carries) into
  `CommandSummary.reports`; `if`/`while` conditions and `script_block` code
  run against a small, explicit namespace (`t_s`, `spacecraft[name].
  {r_BN_N, v_BN_N, altitude_m, mass_kg}`) -- `script_block` runs full,
  unrestricted Python (a deliberate trust boundary matching GMAT/FreeFlyer's
  own script commands and this checkout's own `examples/` scripts: only run
  a mission file you trust). `while` has a 10,000-iteration safety cap so a
  condition that never becomes false fails fast with a clear error rather
  than hanging.
* Every command failure raises `MissionEngineError` naming the specific
  command's path (e.g. `"mission_sequence[2].children[0] (maneuver): ..."`)
  and kind, never a bare exception from inside Basilisk/`eval`/`exec`.

**Verification:** 23 tests (`tests/test_mission_engine.py`,
`requires_basilisk`-marked like every other `engine.*` test -- this layer
imports `engine.service`, which itself needs Basilisk at import time), and
this is the first Phase 6 stage actually RUN against a real Basilisk
build (by the user, who has a working install this project's own sandbox
doesn't) rather than only written against verified-but-unexecuted call
sequences. All 23 pass now, but only after three real bugs the first
real run surfaced and this project's own "no guessing" discipline caught
by actually checking rather than assuming:

* `TimeSeries` crashed on a genuinely zero-sample recorder: a
  `mission_sequence` with no `propagate` command never calls
  `ExecuteSimulation()`, and Basilisk's own recorder accessor returns a
  bare 1-D array (losing the column count) rather than an `(0, ncols)`
  array when nothing was ever logged. Fixed in `engine/results.py`.
* Chaining each `propagate` command's absolute `ConfigureStopTime()`
  target off `scSim.TotalSim.CurrentNanos` read back after the previous
  command compounds rounding loss across segments whenever a requested
  duration isn't an exact multiple of `dynamics_task_rate_s` -- confirmed
  directly against `sim_model.cpp`: `CurrentNanos` is set to
  `NextTaskTime`, i.e. it snaps DOWN to the last task-grid point at or
  before the actual stop time. Three real chained `propagate` commands
  ended up 20 s short of one equivalent single `propagate`. Fixed by
  tracking the cumulative REQUESTED mission time in a separate counter,
  decoupled from the sim's own grid-snapped clock (`propagate`'s `event`
  stop condition is the one exception: it re-syncs to the actual,
  inherently grid-snapped firing time instead, since there's no
  requested target to track there).
* `propagate`'s `event` stop condition checked `scSim.terminate` after
  `ExecuteSimulation()` to tell whether the event fired, always reading
  `False` and raising a bogus "did not occur" error -- confirmed directly
  against `SimulationBaseClass.py` (and with a live diagnostic against a
  real Basilisk build) that `ExecuteSimulation()` unconditionally resets
  `self.terminate = False` as its own last statement before returning,
  whether the loop broke early on a terminal event or ran to completion,
  so that flag can never answer "did a terminal event fire" after the
  fact. The event mechanism itself was correct the whole time (confirmed
  by the same diagnostic: the sim genuinely stopped at the exact
  periapsis crossing, `CurrentNanos` matching the analytically-predicted
  orbital period to the second). Fixed by checking the fired event's own
  `occurCounter` via `scSim.eventMap[event_name]` instead.

A fourth finding was a wrong test assumption, not an engine bug:
`InitializeSimulation()` alone produces ZERO recorder samples (a
recorder only gets one once `ExecuteSimulation()` has actually ticked),
not one as originally assumed -- `_run_report` now raises a specific
`MissionEngineError` naming which series have no samples yet (a
`report` before any `propagate` has run) instead of a bare `IndexError`.

Test coverage itself: multi-segment `propagate` accumulating rather than
restarting (matches a single equivalent-duration `run()` bit-for-bit),
`epoch`/`event` stop conditions, both maneuver frames (checked against
the LIVE state object directly, not the recorder, since a maneuver alone
doesn't trigger a new `scStateOutMsg` write), `assignment` mutating a
live controller, `report` snapshotting the value AT that mission time
(not the final one), `if`/`while` (including nested, including the
iteration-cap safety net), `script_block` (including exception
wrapping), and clear-error cases for every "names something that doesn't
exist" case.

**File-format/CLI sync (`cli.py`, `engine/results.py`) -- landed:**

The mission-sequence JSON round-trip itself was already complete as of
the data-model stage (`Command` is a plain dataclass, so it falls out of
`Scenario.to_dict()`/`from_dict()` for free -- see that stage's own
notes). What was still missing was a way to actually RUN a
`mission_sequence` outside of a Python script calling `MissionEngine`
directly (the tests, in other words) -- there was no CLI or GUI path to
it at all. Since the GUI doesn't exist yet (Phase 6's last stage), this
stage closes that gap on the CLI side, the same "headless-first" order
the rest of this project has followed:

* `missionstudio run` now dispatches on `scenario.mission_sequence`: a
  non-empty one is executed via `MissionEngine` instead of a single
  `SimulationService.run()` call. An empty one (still the default)
  behaves exactly as before -- zero change for every existing scenario
  file, matching this whole phase's additive design.
* `engine.results.CommandSummary.export_csv()`: a Command Summary needs a
  file-format story too, not just an in-memory dataclass -- writes one
  CSV per run, long format (`report_index, t_s, label, series, component,
  value`) rather than one column per series, since different `report`
  commands can request series with different shapes (a position 3-vector
  alongside a scalar mass, say) and there is no single fixed column set a
  wide table could use across every row. `missionstudio run` writes it
  to `<out-dir>/command_summary.csv` alongside the existing per-series
  CSVs, only when at least one `report` command actually ran.
* `ReportEntry`/`CommandSummary` moved from `engine/mission_engine.py`
  (which imports `engine.service` -> Basilisk at module level) to
  `engine/results.py` (deliberately Basilisk-free, exactly like
  `TimeSeries`/`ResultSet` already are) -- a design-consistency fix
  more than new functionality: these are plain data containers with no
  Basilisk dependency of their own, and belonged with this project's
  other Basilisk-independent, synthetic-data-testable result types.

**Verification:** 3 new tests in `tests/test_results.py` (Basilisk-free,
covers the CSV's long-format shape, nested-directory creation, and the
zero-reports/header-only case). `cli.py`'s actual `run` dispatch logic
itself is not independently unit-tested (same as its pre-existing
`SimulationService`-calling code -- this file's tests only cover argument
parsing and Basilisk-free helper functions, see `tests/test_cli.py`'s own
scope).

**GUI (`gui/mission_sequence_editor.py`, `gui/mission_output_widget.py`,
`gui/run_worker.py`, `gui/main_window.py`, `gui/scenario_editor.py`) --
landed:**

The final Phase 6 stage: a `mission_sequence` is now editable and runnable
end-to-end from the GUI, not just from a scenario JSON file or a script
calling `MissionEngine` directly.

* `gui.mission_sequence_editor.MissionSequenceEditorWidget` -- a new
  "Mission sequence" group box in `ScenarioEditorWidget`, right below
  Ground stations. This is the first `QTreeWidget` used anywhere in
  `gui/` (every other list -- spacecraft, sensors/actuators, ground
  stations -- is flat); `Command` is the first schema type that nests
  (`if`/`while` carry `children`), so a tree is the first of its shape
  this app has needed. Add/Edit/Remove mirror
  `gui.sensor_actuator_editor.SensorActuatorListWidget`'s existing
  shape; Add Child (enabled only when the current selection is an
  `if`/`while`) and Move Up/Move Down are new, for nesting and ordering
  a flat list doesn't need. A tree node's `children` are always taken
  from the tree's own nesting, never from a stored `Command`'s own
  `children` field (which is deliberately cleared on every node --
  see the module's docstring) -- editing a child can never leave a
  parent's copy stale.
* `_CommandEditorDialog` -- modeled directly on
  `gui.sensor_actuator_editor._ItemEditorDialog`'s Kind-combo-plus
  -conditional-fields shape, with one page per `Command` kind (`if`/
  `while` share a page -- both are just a `condition` string). Unlike
  that dialog, this one doesn't hand-check each field: it builds a real
  `schema.command.Command` and calls its own `validate()`, so the
  dialog can never drift out of sync with what `Command.validate()`
  actually requires. `script_block.code` gets a `QPlainTextEdit` in a
  monospace font -- this is "the script editor" from the original
  Resources/Mission/Output request. Spacecraft-name fields
  (`propagate`'s event target, `maneuver`'s target, `assignment`'s
  target) are `QComboBox`es fed from a snapshot list taken when the
  dialog opens, via `MissionSequenceEditorWidget.
  set_spacecraft_names_provider()` -- mirrors
  `gui.spacecraft_editor.SpacecraftListWidget.
  set_central_body_provider()`'s existing zero-argument-callable
  convention. `assignment`'s controller/parameter fields are
  `QComboBox`es built from a small whitelist duplicated from (not
  imported from) `engine.mission_engine._ASSIGNMENT_CONTROLLERS`/
  `_ASSIGNMENT_ATTRIBUTES` -- duplicated because
  `engine.mission_engine` imports `engine.service` -> Basilisk at
  module level, and this dialog has to work with no Basilisk installed;
  kept in sync by hand, same as `_KIND_PARAM_SPECS` already documents
  doing for `engine.fsw`.
* `gui.mission_output_widget.MissionOutputWidget` -- the "debug
  console" from the original request: a new read-only "Mission Output"
  tab in `MainWindow.right_tabs` (between Results and Kernel Status)
  that lists every `report` command's `ReportEntry` in execution order
  once a `mission_sequence` run finishes, plus the total
  `commands_executed` count from its `CommandSummary`.
* `gui.run_worker.RunWorker` now dispatches on
  `scenario.mission_sequence` exactly like `cli.py`'s `cmd_run()`
  already did: a non-empty sequence runs through `MissionEngine`
  instead of `SimulationService.run()`/`run_live()` directly, and
  `finished_ok` now always carries `(ResultSet, Optional[
  CommandSummary])` instead of just a `ResultSet` -- `None` for every
  existing (`mission_sequence`-free) scenario, so nothing about the
  non-mission-sequence path changed. `MissionEngine.run()` has no
  `run_live()` equivalent (no per-command progress callback to drive
  one), so `MainWindow.on_run()` ignores the Live Plot toggle whenever
  `mission_sequence` is non-empty rather than silently hanging a
  progress bar at 0%.
* `MainWindow._on_run_finished()` switches `right_tabs` to Mission
  Output instead of Results when a run produced a `CommandSummary`,
  and clears the Mission Output tab on New/Open/Run, matching how
  Results already behaves.

**Verification:** every new/changed GUI file above has direct
`pytest-qt` coverage in `tests/gui/` (`test_mission_sequence_editor.py`,
`test_mission_output_widget.py`, plus additions to
`test_scenario_editor.py`/`test_main_window.py`). Confirmed against a
real Basilisk build (`pytest tests/ -v`): **501 passed, 8 skipped** --
the 8 skips are exclusively the "Basilisk is not installed" error
-path tests, which correctly skip once Basilisk *is* installed; every
other test in the suite ran for real, including all 23
`test_mission_engine.py` tests and this stage's own GUI tests. One
thing that pass doesn't cover: `test_main_window.py`'s
mission-sequence-dispatch tests monkeypatch `RunWorker.start` to avoid
spinning up a real thread, so no automated test yet drives a genuine
GUI click-through (build a `mission_sequence` in the running app,
click Run, watch the "Mission Output" tab populate from a live
`RunWorker` thread executing `MissionEngine.run()`) -- worth doing
once, since every prior Phase 6 stage turned up real bugs only
reachable that way, but no longer the open question this note used to
flag.

## Launching Vizard from the GUI

A **Launch Vizard** action in the Run menu/toolbar starts the external
Vizard application, added in response to a direct request. Previously
the only Vizard-related GUI surface was the Run menu's **Vizard...**
action -- renamed to **Vizard Configuration...** here to keep the two
apart -- which only configures how the *next simulation run* feeds an
already-running Vizard instance (a playback `.bin` file or a live
stream); nothing anywhere actually started the external application
itself. (An earlier version of this feature added a whole extra
"Vizard" status tab next to Results/Mission Output/Kernel Status --
scrapped after user feedback that a plain menu/toolbar action next to
the existing Vizard Configuration one, not a new persistent tab, was
what was actually wanted.)

* `gui/vizard_launcher.py` -- Basilisk-free (launching an external
  process needs no Basilisk build) module with `find_vizard_executable()`,
  `remember_vizard_executable()`, and `launch_vizard()`. Vizard ships as
  a platform `.zip` the user extracts wherever they like (see
  `docs/source/Vizard/VizardDownload.rst`'s "install in the typical
  Applications folder or Desktop") -- there is no single guaranteed
  install path, so finding it is inherently best-effort: a previously
  remembered path (persisted via `QSettings`, under
  `vizard/executable_path`) is tried first, then a shallow search of a
  handful of common per-OS locations (`/Applications`, Desktop,
  Downloads, `Program Files`, ...), and `None` if neither turns up
  anything. `launch_vizard()` resolves a macOS `.app` bundle to its real
  `Contents/MacOS/` binary before calling `subprocess.Popen` (rather
  than shelling out to `open`, which would hand off and exit
  immediately, losing any way to track whether Vizard is still running)
  and returns the live `Popen` handle.
* `main_window.py` -- a new **Launch Vizard** `QAction`
  (`self.vizard_launch_action`, distinct from the renamed
  `self.vizard_action` "Vizard Configuration..."), wired to
  `on_launch_vizard()`: a no-op while Vizard is already running (checked
  via `Popen.poll() is None` on `self._vizard_process`, the last handle
  `launch_vizard()` returned), otherwise looks the executable up via
  `find_vizard_executable()` and launches it -- falling back to a
  `QFileDialog` browse prompt (remembered via
  `remember_vizard_executable()`, so asked at most once) when it can't
  be found automatically.
* `app.py` -- gained `app.setOrganizationName("AVSLab")`, needed for
  `QSettings()` (used above with no explicit org/app name) to resolve to
  a stable per-platform settings location.

**Verification:** `tests/gui/test_vizard_launcher.py` (path search/
persistence, all real filesystem/`QSettings` I/O redirected into
`tmp_path` -- never touches the developer machine's real Vizard
install or settings), plus `test_main_window.py` additions covering
`on_launch_vizard()`'s launch/no-relaunch-while-running/relaunch-after
-exit/browse-fallback/browse-cancelled/launch-failure paths
(`find_vizard_executable`/`launch_vizard` monkeypatched so nothing
spawns a real process). This sandbox has no real Vizard binary to
launch against, so `launch_vizard()`'s actual `subprocess.Popen` call
itself (as opposed to its argument-construction logic, which the
macOS-bundle-resolution tests in `test_vizard_launcher.py` do cover) is
unverified against the real thing -- worth confirming Vizard actually
opens on a real machine with Vizard installed.

## Second round of GUI feedback

Five pieces of direct feedback from a real run against the actual GUI (a
"Simulation failed" dialog referencing `VizInterface` came with it):

* **Vizard live-stream crash, fixed.** `engine/vizard.py`'s
  `enable_vizard()` used to keep every `_AccessIndicatorBridge` alive by
  attaching them to `viz` as `viz._missionstudio_access_indicator_bridges`.
  `viz` is a SWIG proxy for a C++ `VizInterface`, and SWIG-generated
  proxy classes raise on any attribute they don't already know about --
  confirmed against the reported crash, which failed immediately with
  "You tried to add this variable: ... To this class: <...VizInterface
  ...>" before a single simulation step ran, whenever a scenario used
  the Vizard live-stream option. Fixed by having `enable_vizard()` return
  `access_indicator_bridges` alongside `viz` instead of bolting it onto
  `viz`, and having `SimulationService` retain both as plain attributes
  of itself (an ordinary Python object with no such restriction).
* **Plots now show km/km-s, not raw meters** (`results_widget.py`).
  Length/length-rate series (`units in {"m", "m/s"}` -- position,
  velocity, altitude, slant range, delta-V, ...) are converted for
  display only; a LEO position plot's y-axis used to be in the millions.
  Deliberately narrow -- everything else (accelerometer m/s^2, torque
  N*m, angles, ...) is left alone, since km-scale units would be worse
  there, not better. CSV export (`ResultSet.export_csv()`) is unaffected
  -- it keeps writing the raw SI units `TimeSeries` already holds, since
  a CSV handed to another tool should stay unambiguous.
* **A new X-axis combo** (Elapsed time / Epoch (UTC)) on the Results
  plot. `MainWindow.on_run()` captures `scenario.epoch_utc` before
  starting the run (so it reflects the scenario that was actually run,
  not whatever the editor holds by the time the run finishes) and passes
  it through `_on_run_progress()`/`_on_run_finished()` into
  `ResultsWidget.set_live_result()`. `set_result()`/`set_live_result()`
  both take an optional `epoch_utc` (default `None`), so every existing
  caller/test keeps working unchanged; "Epoch (UTC)" with no epoch
  available (or one that fails to parse) falls back to elapsed time
  rather than raising.
* **The Description box in the Scenario Editor is bigger**
  (`scenario_editor.py`'s `description_edit`, `setFixedHeight(60)` ->
  `220`) -- it needed constant scrolling to read a template's full
  description at the old size.
* **Abort a running simulation, without breaking the tool.** See its own
  section below.

**Verification:** `tests/gui/test_results_widget.py` (km conversion +
Epoch axis, including the "no epoch given"/"unparseable epoch" fallback
paths) and `tests/gui/test_main_window.py` (epoch capture/passthrough).
The Vizard crash fix has no dedicated regression test -- there is no
Basilisk-free way to construct a real `VizInterface` SWIG proxy to
assert against -- but it was confirmed against the exact real run that
originally hit it.

## Abort Simulation

Direct user feedback: "there should also be the option to abort a
running simulation, if needed, without breaking the tool." Basilisk's
`SimBaseClass.ExecuteSimulation()` is a single, blocking C++ call with no
hook to interrupt it mid-flight, and `QThread.terminate()` was
deliberately never considered -- it could leave Basilisk's C++
simulation state mid-mutation, exactly the kind of "breaking the tool"
this was asked to avoid. The design is cooperative cancellation instead,
checked between simulation chunks or mission-sequence commands -- never
a forced kill:

* `engine/service.py` -- a new `SimulationCancelled` exception carrying
  whatever partial `ResultSet` had been produced so far
  (`.partial_result`). `run_live()` gained an optional
  `should_cancel: Optional[Callable[[], bool]] = None` parameter, checked
  once after each chunk's `ExecuteSimulation()` call; when it returns
  `True`, `run_live()` raises `SimulationCancelled` with that chunk's
  results rather than silently discarding them. `should_cancel=None` (the
  default, matching every pre-existing caller) leaves behavior unchanged.
* `engine/mission_engine.py` -- the mission-sequence equivalent:
  `MissionEngineCancelled` (carrying both `.partial_result` and
  `.summary`), and `MissionEngine.__init__` gained the same
  `should_cancel` parameter, checked once per top-level command in
  `_run_commands()` -- which also naturally covers `while`-loop
  iterations, since `_run_while()` re-enters `_run_commands()` once per
  iteration -- AND, since then (see "Abort during a single long
  propagate command, fixed" below), mid-command too: a single
  `propagate` command's own `ExecuteSimulation()` call is chunked via
  `_advance_to()`/the chunked branch of `_run_propagate_event()`, not
  just between top-level commands.
* `gui/run_worker.py` -- `RunWorker` gained `request_cancel()` (sets a
  `threading.Event`, safe to call from the GUI thread while `run()` is
  executing on its own thread) and a new `cancelled` Qt signal
  (`Signal(object, object)`: partial `ResultSet`, optional
  `CommandSummary`). The non-`mission_sequence` path now ALWAYS runs
  through `run_live()` (never the plain, non-chunked `run()`)
  specifically so it's always cancellable regardless of the Live Plot
  toggle -- `self.live` now only controls whether the `progress` signal
  is actually emitted (i.e. whether the plot redraws as the run
  proceeds), not whether the run is chunked at all;
  `run_live()`'s own `_LIVE_DEFAULT_FRAMES` (60) bounds this to a small,
  fixed number of extra `ExecuteSimulation()` calls regardless of run
  length, negligible next to the actual simulated work either way.
* `main_window.py` -- a new **Abort Run** `QAction` (Run menu and
  toolbar, between Run Simulation and Live Plot), disabled except while a
  single (non-Monte-Carlo) run is actually in flight -- `on_run()`
  enables it right after starting `RunWorker`, `_stop_busy()` disables it
  again on any of finished/failed/cancelled. Monte Carlo batches are
  deliberately out of scope: `engine/monte_carlo.py`'s
  `Controller.executeSimulations()` uses a different, single-call
  execution model with no exposed chunking/cancellation hook in this
  checkout, and adding one would be unverifiable against a real Basilisk
  build in this development sandbox anyway. `on_abort_run()` calls
  `RunWorker.request_cancel()` and immediately disables the action (so
  there's nothing to double-click while waiting for the next
  checkpoint -- cancellation is cooperative, not instant); a new
  `_on_run_cancelled()` slot (connected to `RunWorker.cancelled`) shows
  whatever partial results/command summary had been produced, with
  "Run cancelled by user." status-bar messaging instead of "Run
  complete", exactly like a normal finish otherwise.

**Verification:** `tests/test_service_run_live.py` and
`tests/test_mission_engine.py` gained `should_cancel` tests
(`requires_basilisk`, auto-skipped in this development sandbox -- see
the honesty note above); `tests/gui/test_run_worker.py` covers the
dispatch/cancellation plumbing Basilisk-free by faking
`engine.service`/`engine.mission_engine` in `sys.modules` (works
regardless of whether a real Basilisk build is present); and
`tests/gui/test_main_window.py` covers the `abort_action`
enable/disable wiring plus an end-to-end real-`QThread` test proving the
`cancelled` signal is actually connected through to
`_on_run_cancelled()`. All of it (except the `requires_basilisk`-marked
engine-level checkpoint tests) was run and confirmed passing in this
sandbox; the `requires_basilisk` tests were then run for real, on an
actual Basilisk build, which caught one genuine bug:
`_run_command()` wrapped every non-`MissionEngineError` exception a
handler raised into a `MissionEngineError`, including a
`MissionEngineCancelled` bubbling up from several levels down the
command tree (e.g. cancelling mid-`while`-loop, where the cancellation
is raised inside the loop body's own nested `_run_commands()` call,
inside `_run_while()`, inside the enclosing `_run_command()`'s `try`
block) -- masking a clean, user-requested abort as a simulation
failure. Fixed by re-raising `MissionEngineCancelled` unchanged before
the generic `except Exception` clause runs (see its own comment in
`mission_engine.py`): `612 passed, 8 skipped, 1 failed` on that real
build before the fix (only `test_should_cancel_checked_between_while_
loop_iterations` failing), `613 passed, 8 skipped` on the same real
build after it -- the whole Abort Simulation feature, cancellation
inside a `while` loop included, is now confirmed against a real
Basilisk build, not just this sandbox's Basilisk-free suite.

### Abort during a single long propagate command, fixed

More direct user feedback, on the real build: clicking Abort mid-run
showed "Aborting... this takes effect at the next checkpoint, not
instantly" and then simply never finished -- minutes of waiting, no
effect. Root cause: a single `propagate` command's own
`ExecuteSimulation()` call ran straight through to its requested target
in ONE unchunked call, so `should_cancel` (only checked BETWEEN
top-level commands, per `run()`'s own docstring at the time) had no
opportunity to fire at all until that one command finished on its own --
for a mission sequence with one long `propagate` (duration/epoch/event),
that's the entire run.

Fixed the same way `engine.service.run_live()` already fixes it for the
non-mission_sequence path: chunk it.

* `_advance_to()` (new) -- runs the simulation from `self._elapsed_ns`
  to a target time, in one unchunked `ConfigureStopTime()`/
  `ExecuteSimulation()` pair when `should_cancel is None` (unchanged
  behavior, zero extra overhead), or in roughly
  `_PROPAGATE_CANCEL_CHECK_FRAMES` (60, mirroring
  `engine.service._LIVE_DEFAULT_FRAMES`) pieces otherwise, checking
  `should_cancel()` after each one and raising `MissionEngineCancelled`
  if it fires. `_run_propagate`'s `"duration"`/`"epoch"` branches now
  both call it instead of executing straight to their target.
* `_run_propagate_event()`'s safety-capped search (periapsis/apoapsis)
  got the same treatment: chunked when `should_cancel` is set, checking
  both the registered Basilisk event's own `occurCounter` (so a real
  periapsis/apoapsis crossing mid-chunk still stops the search exactly
  as before -- chunking never delays detecting it) and `should_cancel()`
  after each chunk. Its chunk size is deliberately based on the
  scenario's own `duration_days`, not `cap_days` (`duration_days *
  _EVENT_PROPAGATE_SAFETY_MULTIPLIER` -- a rarely-hit upper bound on the
  search, not a meaningful step size): sizing off `cap_days` would make
  each chunk roughly `_EVENT_PROPAGATE_SAFETY_MULTIPLIER` (10x) too
  coarse relative to how soon the event realistically fires in a real
  mission, right back to the same problem.
* `run()`'s own docstring updated to describe the new mid-command
  checkpoint, alongside the existing between-commands one.

**Verification:** two new `tests/test_mission_engine.py` cases
(`test_should_cancel_checked_mid_single_long_propagate_command`,
`test_should_cancel_checked_mid_propagate_event_command`) assert a
cancelled run's partial result is strictly shorter than letting the
same command finish would have produced -- the actual behavior this bug
report was about. The existing
`test_should_cancel_checked_between_while_loop_iterations` and the
renamed `test_should_cancel_stops_before_the_first_command_and_raises_
mission_engine_cancelled` (previously named
"...stops_between_commands..." -- its own duration was short enough
that it used to complete in a single old-style unchunked call, so
"between commands" and "before the first command" were the same thing;
now that a command can itself be chunked, the name says precisely which
checkpoint it exercises) were reworked to keep testing the
between-commands/between-iterations checkpoint specifically, now that a
command can also be interrupted mid-way. **This round has NOT yet been
re-run against a real Basilisk build** -- only this sandbox's
Basilisk-free suite (570 passed, 53 skipped, two more than before for
the two new `requires_basilisk` tests) confirms the plumbing compiles
and the untouched paths still pass; the chunk-timing arithmetic behind
the `while`-loop test's exact `commands_executed == 3` expectation, and
the event test's assumption that its chunk size lands comfortably
inside one ~90-minute orbital period, are worked out by hand in each
test's own docstring/comments, not confirmed by actually running them.

### Vizard live-stream: auto-connect instead of a manual launcher step

Direct user feedback, with a screenshot: running a live-stream scenario
showed Vizard just sitting on its own "Load Data Using One of the
Following" launcher screen doing nothing, while missionStudio itself sat
at 0% progress, elapsed time climbing, with Abort having no effect at
all no matter how long it waited.

Root cause, confirmed against `docs/source/Vizard/vizardAdvanced/
vizardLiveComm.rst` and `vizInterface.cpp` directly: in live-stream mode,
`SimBaseClass.InitializeSimulation()`'s very first step is a **blocking**
ZeroMQ handshake -- Basilisk connects out to `tcp://<vizInterface's
reqComAddress>:<reqPortNumber>` (defaults `0.0.0.0:5556`, i.e.
`localhost:5556` locally -- never overridden anywhere in this checkout)
and sends a PING it waits for Vizard to reply to, before a single
simulation step ever runs. Vizard only replies once its OWN launcher
screen has been told what to connect to (typing the address into
"Socket Address") and "Start Visualization" has actually been clicked --
skip that manual step (as our own "Launch Vizard" button previously
did -- it just started the bare app with no arguments) and that PING
never gets a reply, so `InitializeSimulation()` blocks forever. This is
native C++ with no Python-level hook at all -- not even the Abort
feature's own chunk-boundary checkpoints are reachable yet, since this
happens before the first chunk.

Fixed by never requiring that manual step in the first place: Vizard's
own `-directComm <address>` command-line flag (`docs/source/Vizard/
vizardAdvanced/vizardCommandLine.rst`) makes it connect automatically on
launch, with nothing to type or click.

* `gui/vizard_launcher.py` -- new `DEFAULT_LIVE_STREAM_ADDRESS =
  "tcp://localhost:5556"` (matching vizInterface's own unmodified
  defaults). `launch_vizard()` gained an optional `direct_comm_address`
  parameter, appended as `-directComm <address>` to the launched
  process's arguments when given.
* `main_window.py` -- `on_launch_vizard()` now passes
  `DEFAULT_LIVE_STREAM_ADDRESS` whenever Vizard Configuration is set to
  live-stream (`None`, i.e. no flag at all, otherwise -- a save-file run
  still launches Vizard exactly as before), and returns `True`/`False`
  instead of nothing, so a caller can tell whether Vizard is actually
  confirmed running. `on_run()` calls it FIRST, before starting a
  live-stream run's `RunWorker` at all, refusing to start (with a clear
  explanation, never a silent hang) if Vizard couldn't be confirmed --
  an ordinary (non-live-stream) run never touches Vizard at all, so this
  adds no new behavior there.

**A residual gap, since closed:** the first version of this fix only
covered the case where `on_launch_vizard()` was actually starting a new
Vizard instance -- an ALREADY-running one (e.g. launched earlier in the
same session for a save-file run, or before Vizard Configuration was
ever set to live-stream) was still trusted as-is, matching the
pre-existing "never relaunch while already running" behavior, so the
same hang could still happen one launch later. Closed by tracking which
`-directComm` address (if any) `self._vizard_process` was actually
launched with (`self._vizard_direct_comm_address`): `on_launch_vizard()`
now only trusts an already-running instance if it already matches what
this call needs -- a mismatch (specifically, live-stream needed but the
tracked instance has no live-stream connection) terminates it
(`_terminate_vizard_process()`: `terminate()`, then `kill()` only if it
doesn't exit within a bounded 5 s wait) and relaunches a correct one in
its place. The other direction (a live-stream-ready instance already
running, but a save-file/no-request launch is what's needed now) is
deliberately left alone -- `-directComm` being active doesn't stop
Vizard from also opening a save file. An instance this session never
itself launched (`self._vizard_process` is still `None` -- started by
the user outside missionStudio entirely, or in an earlier session) is
still left completely alone rather than killed -- there is no reliable
way to ask an arbitrary already-running Vizard process "are you actually
connected" from outside it, so a second, correctly-configured instance
is launched alongside it instead of guessing about (or killing) a
process this app doesn't own. That specific case -- an untracked,
already-running, not-actually-connected Vizard instance -- is the one
genuinely irreducible gap left: there is nothing missionStudio can
inspect from outside to detect it.

**Verification:** `tests/gui/test_vizard_launcher.py` gained two new
`launch_vizard()` tests (the flag is appended when given, omitted when
not); `tests/gui/test_main_window.py` gained eight new tests covering
`on_launch_vizard()`'s address selection, the mismatch-relaunch/
matching-instance-kept/untracked-instance-left-alone cases above, and
`on_run()`'s new Vizard-confirmation gate (including that an ordinary
run never calls `on_launch_vizard()` at all). All pass in this sandbox
(580 passed, 53 skipped). Like the Vizard crash fix earlier in this
document, there is no way to exercise a real Vizard connection handshake
without an actual Vizard binary and display, so the `-directComm` flag's
effect on Vizard itself (as opposed to the argument list missionStudio
constructs, and the process-tracking logic around it) is unverified
here -- report back if a live-stream run still doesn't
connect after this.

**One remaining click, made obvious instead of silent** (further direct
user feedback, after the fix above): `-directComm` pre-fills Vizard's
socket address field and pre-selects DirectComm/Live Display, but does
NOT click Vizard's own "Start Visualization" button -- confirmed by
this same user actually running it, contradicting `vizardLiveComm.rst`'s
more optimistic-sounding wording. Checked directly against
`vizardCommandLine.rst` for an alternative: the only documented flag
combination that skips this click entirely is `-batchmode -noDisplay`,
which is headless OpNav mode -- it renders nothing to the screen at all,
which defeats the entire point of a LIVE VISUALIZATION. No flag exists
(documented, at least) that both skips the click and keeps the visible
3D view, so this one click could not be eliminated outright.

Made unmissable instead: `MainWindow.__init__` gained
`self._vizard_live_stream_hint_shown = False`. The first time
`on_launch_vizard()` actually starts a NEW Vizard process with a
`-directComm` address in a given session, it shows a one-time
`QMessageBox.information` explaining exactly this -- that the address is
already filled in, but "Start Visualization" still needs one click in
Vizard's own window before the run can proceed -- rather than leaving
the user to wonder (again) why the run looks stuck. Every launch (not
just the first) also gets an updated status-bar message saying the same
thing more briefly, for when the hint dialog isn't shown again. The
dialog deliberately fires only once per session, not once per
launch/run, so it doesn't turn into a repeated interruption once the
user already knows what to do.

**Verification:** `tests/gui/test_main_window.py` gained
`test_launch_vizard_shows_the_one_click_hint_once_per_session` (fires
exactly once even across repeated `on_launch_vizard()` calls); the four
existing tests that trigger a real live-stream launch had
`QMessageBox.information` mocked so the new dialog doesn't block them.
581 passed, 53 skipped in this sandbox. As with the fix above, there is
no way to confirm the dialog's wording matches what a user actually
needs without a real Vizard binary and display to try it against.

## Three more real-run bugs, caught by the user testing templates

All three were caught by the user actually clicking through the bundled
templates one by one, with screenshots -- not found by this sandbox's
own (Basilisk-free) test suite, which had no way to catch any of them.

**1. Templates '05' and '07' failed to run: missing sun ephemeris.**
`SimulationService.build()` raises a clear `SimulationServiceError` when
any spacecraft has `power`/`station_keeping`/`enable_srp` configured but
`'sun'` isn't in `gravity.third_body_perturbers` (`simpleSolarPanel`/the
eclipse gate/SRP all need a real eclipse shadow factor, which needs a
sun ephemeris) -- exactly the error the user hit on both '05' (formation
flying, `station_keeping` required by `phasing_keeping`) and '07'
(attitude pointing with ADCS hardware, has a `PowerConfig`). Both
templates' own `scripts/_generate_templates.py` builder functions
simply never included `third_body_perturbers=["sun"]` in their
`GravityConfig` -- a real bug in this project's own bundled templates,
not a user configuration mistake. Fixed at the source (the generator
functions, each with a comment explaining why) and regenerated both
JSON files (`python3 scripts/_generate_templates.py`, run from
`missionStudio/`) -- every other template was already correct, so only
these two files changed.

Also promoted to a **schema-level check**: `Scenario.validate()` gained
a mirror of this same engine-layer condition, following the exact
precedent `GravityConfig.validate()` already set for the
`central_body_degree`/`central_body` mismatch (see its own comment) --
without this, `missionstudio validate`/the GUI's live "valid" indicator
(both Basilisk-independent) would keep reporting a clean bill of health
for a scenario guaranteed to fail the moment it's actually run, exactly
as it did here. Now caught immediately in the editor, not after
clicking Run.

**Verification:** a scan of all 9 bundled templates (any spacecraft with
`power`/`station_keeping`/`enable_srp` but no `'sun'` third-body
perturber) confirms only '05'/'07' were affected and both are now
clean. `tests/test_scenario_schema.py` gained
`test_power_station_keeping_or_srp_without_sun_third_body_is_rejected`/
`..._with_sun_third_body_validates`/
`test_no_power_station_keeping_or_srp_does_not_need_sun_third_body`
(parametrized over all three triggering fields), plus fixed seven
existing tests whose own fixtures had exactly this same gap (legitimate
staleness this new check exposed, not false positives -- those fixtures
would already have failed at `SimulationService.build()` if ever run
for real). 588 passed, 53 skipped in this sandbox.

**2. Load Scenario's description text was unreadable.** Screenshot:
near-invisible light-gray-on-white text. Root cause: several widgets'
own inline stylesheets use `"color: palette(mid);"` for muted hint/
description text (`LoadScenarioWidget`'s template description,
`SpacecraftTemplateDialog`'s description, several "how to use this
field" hints across the spacecraft/sensor/mission-sequence editors) --
`QPalette.Mid` was never explicitly set by `gui/theme.py`'s
`apply_theme()`, so it stayed at Qt's own computed default (a subtle
3D-bevel shading tone meant for shadow lines, not body text), which
reads as near-invisible against this theme's light background. Fixed
with a single one-line change in `theme.py` -- `QPalette.Mid` mapped to
the same `text_muted` color the theme already uses for
`PlaceholderText` -- which fixes every `"palette(mid)"` usage across the
whole app at once, not just `LoadScenarioWidget`. Confirmed visually
with an offscreen-rendered screenshot of both `LoadScenarioWidget` and
`SpacecraftTemplateDialog` before considering this done, not just by
reading the CSS.

**Verification:** `tests/gui/test_theme.py` gained
`test_mid_palette_role_is_readable_not_left_at_qt_default`. 589 passed,
53 skipped in this sandbox.

**3. Template '06' crashed with a confusing internal error.**
`'ClassicElements' object has no attribute 'AN'`. Traced directly (not
guessed) to a genuine bug in Basilisk's OWN `src/utilities/
orbitalMotion.py`: `rv2elem()`'s NaN-input guard sets `elements.AN`/
`elements.AP`, but `ClassicElements.__slots__` only defines `Omega`/
`omega` (no `AN`/`AP` at all) -- so instead of returning a clean all-NaN
element set for a non-physical (NaN) position/velocity sample, it
crashes with that `AttributeError`. `engine.service._osculating_elements`
calls `rv2elem()` once per recorded sample (to plot how the orbit's
shape/orientation evolves over the run) -- reaching this crash means the
spacecraft's OWN propagated position/velocity had already gone
non-physical partway through the run, an actual numerical instability
this sandbox has no Basilisk build to reproduce or trace further (inertia
`_INERTIA_MEDIUM` and `mrpFeedback` gains `K=3.5`/`P=30` both look like
reasonable, standard-example-scale values on inspection, not an obvious
mismatch, but that's as far as static inspection alone can go).

Fixed what's actually fixable from here: `_osculating_elements` now
checks each sample for `NaN`/`inf` itself, before ever calling the
buggy `rv2elem()`, and raises a clear, actionable
`SimulationServiceError` naming the sample index and likely causes
(control gains too aggressive for the inertia/rates involved, excessive
actuator torque, too coarse a `dynamics_task_rate_s`) instead of that
confusing `AttributeError` -- turning an inscrutable crash into a
diagnosable one. The Basilisk-side bug itself is not patched here (out
of scope for this checkout's own code); this is a defensive workaround
on the missionStudio side.

**This does NOT fix why template '06' actually diverges** -- only makes
the failure mode legible instead of cryptic. If it still fails after
this, the new error message will say which recorded sample first went
non-physical (and, from `sim_settings.dynamics_task_rate_s`, roughly
what elapsed time that corresponds to) -- that detail would help narrow
down the real cause on a real Basilisk build, which this sandbox cannot
do.

**Verification:** new `tests/test_osculating_elements.py`
(`requires_basilisk`, auto-skipped in this development sandbox --
`engine.service` imports Basilisk at module level) directly exercises
`_osculating_elements` with a synthetic NaN/inf sample, confirming the
clear error fires instead of the `AttributeError`, alongside a
finite-input sanity check. 589 passed, 56 skipped in this sandbox
(three more skipped, matching the three new `requires_basilisk` tests).
**Confirmed for real** on the user's own real Basilisk build, right
after this shipped: re-running '06' produced exactly the new message
("the simulated position/velocity became non-physical (NaN/inf) at
recorded sample 15 of 73...") instead of the old `AttributeError` --
the diagnostic works as designed. The underlying divergence itself is
still open; that sample index/count is the concrete lead needed to
chase it further, next.

## Template '05' crashing with heap corruption, root-caused

Direct follow-up from the "template '06' crashed with a confusing
internal error" entry above: the user then hit template '05' (formation
flying, `station_keeping` + `phasing_keeping`) crashing too -- but with
TWO DIFFERENT native crash signatures on different runs of the exact
same scenario (`basic_string::_M_create`, then `std::bad_alloc`). That
variability is the signature of genuine memory corruption, not a
deterministic bug -- exactly like the very first Vizard crash earlier in
this project (a Python object garbage-collected while Basilisk's C++
side still held a live callback into it).

Root cause, this time: `PhasingKeepingController.UpdateState()` (called
every dynamics tick, directly by Basilisk's C++ scheduler through a SWIG
director override) calls `orbitalMotion.rv2elem()` via its own
`_mean_anomaly()` helper, to compute the chief/follower's current mean
anomaly for the phasing control law. That's the exact same buggy
Basilisk function `engine.service._osculating_elements` was already
fixed to avoid (see above) -- but `_osculating_elements` is ordinary
Python code with an ordinary `try`/`except` around it; `UpdateState()`
is not. A Python exception escaping a SWIG director-overridden virtual
method is undefined behavior, not a clean propagated exception -- which
is exactly consistent with two different native crashes from the same
root cause on different runs.

The state fed into `rv2elem()` there comes straight from
`scStateInMsgA()`/`scStateInMsgB()` with no validity check at all --
either genuinely non-physical (the simulation having already diverged)
or simply not written yet (read before either spacecraft's own dynamics
has published a first sample this run, an ordering question this
function has no control over). Either way, calling `rv2elem()` with it
was never safe.

Fixed in `engine/orbit_maintenance.py`: both `PhasingKeepingController.
UpdateState()` and `StationKeepingController.UpdateState()` (the same
class of risk -- a non-finite or exactly-zero velocity would otherwise
divide-by-zero computing a thrust direction) now check the spacecraft
state for finiteness (and, for station-keeping, non-zero velocity)
*before* doing anything with it. On a non-finite/degenerate tick, both
command zero thrust and log a placeholder (NaN error/altitude, matching
every other tick's log-once-per-call invariant) rather than ever
reaching the buggy call -- there is no safe way to raise from inside a
director callback either, so "degrade gracefully, never crash" is the
only sound option here regardless of why the state went bad.

**This does not, by itself, explain why the state went non-physical (or
unwritten) in the first place** -- same honesty as the '06' entry above.
But it does mean template '05' can no longer crash the whole process
over it: if the underlying cause is "read before write" (an ordering
question), the controller will now simply no-op for a tick or two until
real data arrives; if the underlying cause is a genuine divergence, the
run will still fail, but cleanly -- most likely via
`_osculating_elements`'s own clear `SimulationServiceError` during
result extraction, exactly like '06' now does, rather than a crash with
no useful message at all.

**Verification:** four new tests in `tests/test_orbit_maintenance.py`
(`requires_basilisk`, auto-skipped in this sandbox) construct each
controller directly, write a `SCStatesMsg` with NaN (or, for
station-keeping, zero-velocity) state, call `UpdateState()` directly,
and confirm it returns cleanly with zero commanded thrust instead of
reaching `rv2elem()` -- plus one confirming the guard doesn't change
behavior for the ordinary finite-state path. 590 passed, 60 skipped in
this sandbox (four more skipped, matching the four new tests).

**Confirmed for real** on the user's own Basilisk build: the fix itself
worked first try -- `UpdateState()` returned cleanly with no crash on
every non-finite/degenerate-state test, exactly as designed. Three of
the four new tests still failed, but only on an assertion detail: a
real `ExtForceTorque`'s `extForce_N` reads back as a nested `[[0.0],
[0.0], [0.0]]` column-vector shape, not the flat `[0.0, 0.0, 0.0]` list
these tests assumed -- fixed with a small `_flat()` helper. That same
real run also re-confirmed every other fix from this session still
holds: both sun-ephemeris-validation directions, all four
`should_cancel` checkpoints, `run_live` cancellation, the toolbar split,
and templates '05'/'06'/'07' all loading/validating/round-tripping
cleanly (639 passed, 8 skipped, only the three assertion-shape failures
above, now fixed).

## A toolbar action invisible on one real platform

Direct user report, with a screenshot: the "Launch Vizard" toolbar
button was simply not there -- while confirmed present in the **Run**
menu (built from the exact same `QAction` object as the toolbar button),
ruling out a construction failure. `_build_toolbar()`'s single,
un-movable `QToolBar` held 9 text-beside-icon buttons plus 2 separators
-- wide enough that real-world font/DPI rendering on at least one real
desktop environment ran out of horizontal room before the window itself
did, something this sandbox's own offscreen-Fusion-style screenshots
never reproduced (they consistently rendered narrower). Rather than
chase the platform-specific overflow behavior itself (Qt's overflow
handling for a fixed single-row toolbar is not obviously predictable
across styles/platforms), removed the dependency on window width
entirely: `_build_toolbar()` now builds two shorter, fixed rows (File
ops + Run ops; Vizard + Check Kernels) via `addToolBarBreak()`, each
comfortably narrow enough to never need to overflow at all.

**Verification:** confirmed visually with offscreen screenshots at both
the default window width and a deliberately narrower one (1000px) --
every button fully visible at both. `tests/gui/test_main_window.py`
gained `test_toolbar_actions_are_all_visible`, asserting every one of
this window's actions is present on one of the (now two)
`QToolBar`s and actually visible, not just constructed as a `QAction`
object somewhere. 590 passed, 56 skipped in this sandbox. Not
independently confirmed against the specific real platform/window size
that originally lost the button (this sandbox has no way to reproduce
that environment), but the fix removes the mechanism (window-width
-dependent single-row overflow) entirely rather than patching around a
guessed cause, so it should hold regardless of the exact platform
details.

## Template '05' crash recurred -- added a debug-logging mode

The "root-caused" fix above turned out not to be the whole story: the user
hit the **same** `basic_string::_M_create`/`std::bad_alloc` crash again on
template '05', on a build that already had the `orbit_maintenance.py`
finiteness guards deployed and confirmed working (per that section's own
"Confirmed for real" note). That rules out the guarded `rv2elem()` call
sites as the *only* source -- there is some other path into this crash
that guarding those two call sites didn't cover, and guessing at more
call sites blind, the same way the first fix was found, was not working.

What actually blocked root-causing it further: this app had **no
diagnostic output anywhere**. Every background-thread failure (`RunWorker`,
`MonteCarloWorker`, the kernel-fetch worker) was caught with a bare
`except Exception as exc: self.failed.emit(str(exc))` -- the GUI shows a
one-line message, nothing is logged, and the terminal the user launched
`missionstudio-gui` from prints nothing but Unity's own startup noise. A
native crash inside a SWIG director callback (see above) doesn't even
leave that much -- there is no Python traceback to catch in the first
place. Direct user request: "would be good, if you could add some kind of
debug mode, that outputs everything that happens in the terminal and also
saves it in a log file."

Added `missionstudio/logging_setup.py`: a single `configure_logging()`
entry point, called once as the very first line of both `cli.main()` and
`gui.app.main()` (idempotent -- `cli.main()` dispatching into
`gui.app.main()` for `missionstudio gui` must not double up handlers).
It attaches two handlers to the root logger -- a `FileHandler` at
`~/.missionstudio/logs/missionstudio_<UTC timestamp>.log` (`DEBUG` level,
so nothing is filtered out of the file) and a `StreamHandler` on stderr
(`INFO` level, so the terminal stays readable) -- and installs
`sys.excepthook` so an exception that would otherwise just crash silently
is logged with its full traceback before the process exits. The three
background-worker `except Exception` catch-alls (`run_worker.py` x2,
`kernel_status_widget.py`) now call `logger.exception(...)` before
emitting their `failed` signal, so a worker failure's full traceback lands
in the log file, not just the one-line message the GUI dialog shows.
`main_window.py`'s "Simulation failed"/"Monte Carlo failed" dialogs now
also name the current log file's path directly in the dialog text, so the
next report doesn't depend on the user knowing where to look.

This does not, by itself, fix the template '05' crash -- a crash
originating inside a SWIG director callback can still take the whole
process down before Python-level logging gets a chance to run (the same
reason `orbit_maintenance.py`'s guards can only degrade gracefully, never
raise). But it turns every *other* class of failure -- anything that
raises a normal Python exception anywhere in this app, including on a
background thread -- into something with an actual traceback to read
afterward, and it is the only way forward for the next reproduction: if
the crash again leaves nothing in the log file, that itself narrows it
back down to "inside Basilisk's C++/SWIG layer, not this app's Python
code," which the two conflicting crash signatures already suggested but
didn't confirm.

**Verification:** `tests/test_logging_setup.py` (7 tests, no
Basilisk/Qt dependency, run unconditionally) cover log-file creation,
idempotency, an exception logged via `logger.exception()` landing in the
file with its full traceback, and the `sys.excepthook` install. Three new
`tests/gui/test_main_window.py` tests confirm the failure dialogs mention
the log file's path when logging is configured and omit the hint
otherwise. Running `cli.main()` directly (as `tests/test_cli.py` already
does, dozens of times, without a subprocess) now triggers a real
`configure_logging()` call every time this suite runs -- an autouse
`tests/conftest.py` fixture isolates it per test (resets
`logging_setup`'s internal state, redirects `Path.home()` to a per-test
`tmp_path` so nothing touches this machine's real
`~/.missionstudio/logs`, and restores the root logger's handlers/level
and `sys.excepthook` afterward) so no test leaks a stale `StreamHandler`
bound to a since-closed, pytest-captured `stderr` into any later test.
600 passed, 60 skipped in this sandbox. Not yet confirmed against a real
Basilisk build -- that confirmation depends on the user reproducing the
template '05' crash again and sharing the new log file's contents, which
is the actual blocker on finishing the root-cause fix.

**If you hit this (or any other) crash:** the log file's path is printed
at GUI/CLI startup and is also named directly in any "Simulation
failed"/"Monte Carlo failed" dialog. Check
`~/.missionstudio/logs/missionstudio_<timestamp>.log` (the most recent
one) for a full traceback before reporting a crash -- it will have far
more detail than whatever the dialog or terminal showed on their own.

## Template '05' crash, actually root-caused this time

The logging mode above paid off immediately: the user reproduced the
crash and the new log file's traceback showed something genuinely
different from every earlier assumption in this project's history --

```
RuntimeError: std::bad_alloc
  File ".../missionstudio/engine/service.py", line 1023, in run_live
    self.scSim.ExecuteSimulation()
  File ".../Basilisk/utilities/SimulationBaseClass.py", line 2006, in ExecuteSimulation
    self.TotalSim.StepUntilStop(...)
  File ".../Basilisk/architecture/sim_model.py", line 1524, in StepUntilStop
    return _sim_model.SimModel_StepUntilStop(self, SimStopTime, stopPri)
```

A clean, catchable Python `RuntimeError` -- not a raw native crash with no
Python frame at all. That directly contradicts this project's own earlier
theory (written into `orbit_maintenance.py`'s guard comments): that a
Python exception escaping `UpdateState()` (a SWIG director callback) is
undefined behavior, and that's what produced the two different crash
signatures. Reading Basilisk's actual C++ source
(`src/architecture/system_model/sim_model.cpp`) shows that theory was
wrong -- `SimThreadExecution`'s worker-thread loop wraps every tick in
`catch (...) { threadException = std::current_exception(); }`, and the
parent thread cleanly `std::rethrow_exception`s it, which SWIG surfaces
as an ordinary Python exception. No UB; this project's Basilisk version
has real cross-thread exception safety.

The ACTUAL mechanism, found by then reading
`src/simulation/dynamics/_GeneralModuleFiles/svIntegratorAdaptiveRungeKutta.h`
(the code behind `rkf45`/`rkf78`, the integrators this project's
templates use): once the integrated state goes non-finite (NaN/inf, from
any cause), `computeMaxRelativeError()` returns NaN. The step-acceptance
check `maxRelError <= 1.` is then always false (every comparison against
NaN is false in IEEE 754), so `integrate()`'s `while (time < startingTime
+ desiredTimeStep)` loop never advances `time` and never exits. Worse,
the "shrink the step and retry" fallback that would normally recover from
a rejected step can't either: `std::min`/`std::max` called with a NaN
first argument return that same NaN argument (both are implemented as
`(b < a) ? b : a`, and any `< NaN` comparison is false), so the computed
`newTimeStep` stays NaN forever too. The result is a genuine infinite
C++ loop, re-evaluating the same NaN state and allocating fresh `Eigen`
temporaries every iteration, until the process's heap is exhausted --
`std::bad_alloc` (a clean allocation failure) on one run, heap corruption
(`basic_string::_M_create`, an unrelated allocation tripping over an
already-exhausted/corrupted heap) on another: same root cause, whichever
allocation happens to be the one that finally fails. This also explains
the near-instant crash timing (the whole thing happens inside one C++
call, a tight allocate-and-retry loop with no artificial delay) regardless
of how much simulated time had already completed successfully before it.

**What is NOT the cause, now confirmed:** the `orbit_maintenance.py`
finiteness guards (the earlier fix) were never wrong to add -- a
non-finite spacecraft state was never safe input to `rv2elem()` -- but
they were never going to be *sufficient* either. The state can go
non-finite entirely inside Basilisk's own equations-of-motion/integrator,
strictly between one tick's guarded read and the next, with no Python
-level hook in between to catch it. `orbit_maintenance.py`'s own comments
are corrected to reflect this (and to drop the wrong "UB" claim).

**What this project CAN fix**, since the underlying integrator bug lives
in Basilisk's own C++ (not something this app controls, and not
something a from-source rebuild is practical to depend on here -- see
this README's own "Environment honesty note" on why a from-source build
has historically been avoided): turn the resulting crash into an
immediately actionable message instead of a bare native exception string.
New `engine.service.raise_clear_execution_error()` wraps every
`scSim.ExecuteSimulation()` call in this codebase (`SimulationService.run()`/
`run_live()`, and all three call sites in `MissionEngine._advance_to()`/
`_run_propagate_event()`) in `try`/`except RuntimeError`, re-raising as a
`SimulationServiceError` that explains the actual mechanism above and
points at the concrete things that commonly cause a state to go
non-physical in the first place (a runaway commanded force/torque -- check
station-keeping/phasing-keeping/constant-thrust configuration for a sign
or magnitude error -- or an orbit decaying into the central body).
`SimulationService.run_live()` also now logs progress (`INFO`, sim time
and percent complete) after every chunk, and logs an `ERROR` with exactly
how far the mission clock got before a failure -- so a future crash's log
file will show precisely which portion of the run diverged, rather than
leaving that as a guess.

This still doesn't identify *why* template '05' specifically ends up with
a non-finite state in the first place -- that remains open, and would
need either a reproducible local Basilisk build (not available in this
sandbox) or the user narrowing down which of the two spacecraft's
controllers (or plain two-body dynamics) is responsible from a future,
now-far-more-informative log file. But "Run failed: std::bad_alloc" with
nothing else to go on is no longer where this ends.

**Verification:** `tests/test_service_execution_errors.py` (3 tests) and
one new test in `tests/test_mission_engine.py`
(`test_propagate_translates_execute_simulation_runtime_error`), all
`requires_basilisk` (auto-skipped in this sandbox): construct a real
`SimulationService`/`MissionEngine`, monkeypatch the real, already-built
`scSim.ExecuteSimulation` to raise `RuntimeError("std::bad_alloc")` (an
injected failure -- reproducing the actual integrator bug isn't a
reliable thing to build a fast unit test around), and confirm a
`SimulationServiceError` mentioning "non-physical" is raised with the
original exception preserved as `__cause__`. 600 passed, 64 skipped in
this sandbox (4 more skipped, matching the 4 new tests).

**Confirmed for real** on the user's own Basilisk build: 655 passed, 1
failed, 8 skipped. The one failure was a bug in the new MissionEngine
test, not in the production fix --
`test_propagate_translates_execute_simulation_runtime_error` asserted
that `SimulationServiceError` propagates out of `engine.run()`
unwrapped, but `MissionEngine._run_command()`'s existing generic
`except Exception` handler (the same one that already wraps, say, a
script-block exception -- see
`test_script_block_exception_is_wrapped_in_mission_engine_error`) wraps
ANY non-`MissionEngineError`/`MissionEngineCancelled` exception into a
path-qualified `MissionEngineError` -- correct, existing behavior the
test just modeled wrong. Fixed by asserting `MissionEngineError`
instead (whose message still contains the clear "non-physical"
explanation). `SimulationService.run()`/`run_live()`'s own two tests,
which are not wrapped by anything, passed as written the first time.

## Template '05' crash, narrowed further -- last-known-state diagnostic

The clear-error fix above paid off immediately: the user reproduced the
crash again, and the new error and log showed something genuinely
useful for the first time --

```
run_live: ExecuteSimulation failed at t=10080.0 s of 604800.0 s (1.7% complete)
```

The failure is in the very FIRST live chunk (`run_live`'s default chunk
size for this scenario -- `max(dynamics_task_rate_s, duration_days*86400
/60)` -- works out to 10080 s, about 336 dynamics ticks). 10080 s is
under two orbital periods for this scenario's ~550 km circular orbit
(period ≈ 5740 s) -- so whatever drives the state non-finite happens
almost immediately, not from a slow multi-day drift. That rules out a
large class of otherwise-plausible explanations (e.g. propellant
depletion, a multi-day accumulated phasing error) -- there simply isn't
enough elapsed time for those.

Reasoning through `orbit_maintenance.py`'s actual numbers for this
template by hand (`target_altitude_km=550`, `thrust_n=0.05`,
`target_separation_km=50`, `max_delta_semi_major_axis_km=3.0`) suggests
the commanded maneuvers themselves are tiny (a back-of-envelope
phasing correction here works out to on the order of tens of METERS of
semi-major-axis change, a few cm/s of delta-v) -- nowhere near large
enough on their own to explain a near-instant divergence. One real,
separate finding from this exercise: `PhasingKeepingConfig.
target_separation_km`'s docstring and validation (`schema/scenario.py`)
define it as a distance strictly "ahead of the chief" (validated `> 0`
only, no way to express "behind"), but template '05's own description
and initial conditions (follower's `true_anomaly_deg=-0.5` vs chief's
`0.0`) explicitly set up and describe a TRAILING formation. Worth fixing
as its own follow-up (either allowing a signed value, or documenting
that "ahead"/"behind" is just a label and the schedule is always
interpreted as the magnitude of `mB - mA`), but the hand-computed
maneuver size shows this specific mismatch is not large enough to be
what crashes here.

Without a local Basilisk build to actually step through this, further
narrowing by hand-reasoning about the physics has reached its limit --
what's actually needed is the state at the exact moment it goes
non-finite, which no existing diagnostic captured (the failing tick
itself is never recorded at all -- see `raise_clear_execution_error`'s
own docstring for why). New `SimulationService.log_last_known_state()`,
called right before `raise_clear_execution_error` re-raises at all four
`ExecuteSimulation()` call sites, logs (`ERROR`) the LAST successfully
recorded sample for every spacecraft straight from each handle's own
recorder/controller logs -- position/velocity, and (when configured)
station-keeping's altitude/burn-on/propellant and phasing-keeping's
separation error/state-machine state -- deliberately bypassing
`_extract_results()`/`_osculating_elements()` (which would itself raise
on a non-finite sample) so this works even if the last state is already
bad. This is the closest thing to a debugger breakpoint available
without one: the next crash's log file will show exactly where each
spacecraft was, what each controller was doing, and how far each
propellant tank had been drawn down, one tick before Basilisk's own
stepping failed.

**Verification:** two new tests in `tests/test_service_execution_errors.py`
(`requires_basilisk`, auto-skipped in this sandbox) -- one confirms the
method doesn't raise before any tick has completed (logs "no samples
recorded yet" instead), the other runs a few real dynamics ticks first
and confirms the logged text actually contains `r_BN_N=`/`v_BN_N=` data.
600 passed, 66 skipped in this sandbox (2 more skipped, matching the 2
new tests). Not yet confirmed against a real Basilisk build -- that
confirmation depends on the user reproducing the crash again and sharing
the new log, which will finally show the exact last-good state rather
than just which chunk failed.

## Template '05' crash -- root cause found and fixed at the template level

The last-known-state diagnostic paid off immediately -- the user's next
crash log showed:

```
follower-1: last recorded state before failure -- t=30.000 s, r_BN_N=[...] m, v_BN_N=[...] m/s
follower-1: phasing_keeping last tick -- t=30.000 s, error=-0.0882 deg, state=BURN_OUT, ...
```

The state at t=30 s (the very FIRST dynamics tick) is completely sane --
hand-verified against a from-scratch two-body propagation in plain numpy
(no Basilisk needed) that matched the logged r/v to 6+ significant
digits. The failure happens between t=30 s and t=60 s -- the SECOND
tick, as early as this scenario's finest possible resolution can show.

That ruled out slow drift/depletion explanations and pointed at the
`phasing_keeping` error value itself: -0.0882 degrees, when the actual
along-track separation between these two near-identical orbits (0.5
degrees apart by construction) plus the 50 km/6928 km target works out to
-0.9135 degrees by hand -- a ~10x, suspiciously specific discrepancy.
Root cause, found by reading `orbitalMotion.rv2elem()`'s real algorithm
(`src/utilities/orbitalMotion.py`): this template's two orbits were
defined with `eccentricity=0.0` EXACTLY. `rv2elem()` has a dedicated
branch for a genuinely circular orbit (`e < 1e-11`) that measures the
along-track phase from the ascending node -- numerically stable. But this
scenario's real, propagated eccentricity (perturbed by the sun
third-body gravity this project added earlier to fix a different bug,
and by the phasing controller's own commanded thrust) only needs to
drift a hair above that extremely tight threshold to fall onto a
DIFFERENT branch, which measures the same angle from the eccentricity
vector's direction instead -- numerically meaningless once eccentricity
is that close to zero, since that direction becomes dominated by
floating-point noise rather than physics. Reproducing the real crash's
logged state through that unstable branch by hand gave
argument-of-periapsis values 160 vs 184 degrees apart for two spacecraft
that are physically 0.5 degrees apart -- a ~24 degree spurious
"separation," matching the instability's fingerprint exactly.

**A first attempt at this fix was wrong and has been reverted:**
replacing `PhasingKeepingController`'s call into `rv2elem()` with a
custom, hand-written along-track-angle computation. That is exactly the
kind of change this project does not make -- orbit mechanics goes through
Basilisk, not a parallel implementation of it, however numerically
well-reasoned. The actually-correct fix is at the TEMPLATE level: this
scenario asked for an EXACTLY circular orbit, which is itself an edge
case Basilisk's own `rv2elem()` only handles safely below an extremely
tight, real-perturbation-sensitive eccentricity threshold. Both orbits
now use `eccentricity=0.001` (about 7 km of altitude variation, well
inside `station_keeping`'s 2 km deadband once smoothed over one orbital
period -- see `StationKeepingController.UpdateState()`'s own boxcar
average, which exists for exactly this kind of periodic, non-decay
variation) instead of `0.0` -- large enough to keep `rv2elem()` reliably
on its normal, stable branch for the whole run (comfortably above any
perturbation-induced noise), small enough not to meaningfully change the
scenario's own "near-identical orbits" story. `scripts/_generate_templates.py`
is the source of truth (see that script's own comment on
`build_05_formation_flying_phasing()`'s chief-1 orbit for the full
reasoning); `05_formation_flying_phasing.json` was regenerated from it,
not hand-edited.

**This does not, by itself, prove the crash is fully resolved** -- there
may be a second contributing factor this investigation hasn't isolated.
But it is a definite, real, well-evidenced bug in how this ONE template
was configured (an exactly-circular orbit is a genuine Basilisk edge
case, not something Basilisk itself is wrong about), fixed the way this
project fixes that class of problem: by giving Basilisk's own,
unmodified math a configuration it handles well, not by working around
it.

**Verification:** `tests/test_scenario_templates.py`/
`tests/gui/test_scenario_templates_gui.py`'s existing template
round-trip tests cover `05_formation_flying_phasing.json` structurally
(schema-valid, round-trips through the GUI editor) and pass unchanged --
this is a numeric-value-only change, not a structural one. 600 passed,
66 skipped in this sandbox (matching the count before this fix -- no new
tests needed; the actual regression check is a real Basilisk run of
template '05' no longer crashing, or crashing with a materially
different error/last-known-state, which only the user's own build can
confirm).

## Audit: every other place a degenerate/zero state could reach Basilisk

Direct follow-up request after the template '05' investigation: check the
whole codebase for other places a similar "zero" (or other degenerate)
input could break something, now that one real instance was found. Two
more were found, both in `engine/orbit_maintenance.py`, both existing
gaps in an ALREADY-established defensive pattern (`StationKeepingController.
UpdateState()`'s own guard checks BOTH non-finite AND exactly-zero
velocity before dividing by it) rather than new problems introduced by
anything in this investigation:

1. **`PhasingKeepingController.UpdateState()`** only checked for
   NaN/inf, not for `vA`/`vB` being exactly zero -- `vHatB = vB /
   np.linalg.norm(vB)` a few lines later would divide by zero, and
   `orbitalMotion.rv2elem()` (called just before that, to compute the
   phasing error) also divides by velocity-derived quantities
   internally. Its own existing guard comment on `StationKeepingController`
   even said "Same reasoning as PhasingKeepingController.UpdateState()'s
   own matching guard" -- which was no longer true once written, since
   that guard never actually got the zero-velocity check. Fixed by
   adding it, matching `StationKeepingController`'s exact pattern.

2. **`ConstantFrameThrustController.UpdateState()`** (the `constant_thrust`
   config -- not currently used by any bundled template, but a fully
   supported, documented feature a user can configure) had **no guard at
   all**: neither a finite check nor a zero-velocity one. Its
   `_vnb_basis()`/`_rtn_basis()` helpers (VNB/RTN frame construction)
   divide by `norm(vVec)` (both frames), `norm(rVec)` (RTN), and
   `norm(cross(rVec, vVec))` (both -- the orbit-normal magnitude, zero
   whenever r and v happen to be parallel, e.g. a purely radial
   trajectory, which neither an individual finite check nor a
   zero-velocity check alone would catch). Fixed with a guard covering
   all three degenerate cases, same "command no thrust, hold state"
   pattern as the other two controllers.

Also checked and found NOT to need a fix, with the reasoning for each:

* **`engine.service._osculating_elements()`** (the OTHER
  `orbitalMotion.rv2elem()` call site in this codebase) hits the exact
  same near-circular/near-equatorial classical-elements singularity, but
  its output only feeds plots/CSV export, never a commanded force -- a
  "wrong-looking reported angle" is not a "the simulation crashes"
  problem, and this was already correctly documented as an inherent,
  accepted limitation of osculating classical elements (not something a
  per-sample computation could avoid) rather than a bug, well before this
  audit.
* **`mission_engine.py`'s periapsis/apoapsis event detector**
  (`radial_velocity = dot(r, v) / np.linalg.norm(r)`) divides by
  `norm(r)`, which is only zero if a spacecraft's position has already
  reached the central body's exact center -- a state that requires the
  orbit to have already gone catastrophically non-physical by some OTHER
  cause first, not an independent trigger the way an ordinary near-circular
  or radial-trajectory configuration is.
* **`link_budget.py`'s free-space-path-loss** divides by nothing risky (a
  physical constant, the speed of light); `np.log10(range_m)` would only
  misbehave at `range_m == 0` (spacecraft exactly co-located with a
  ground station -- not a real orbital state), and even then only
  produces a nonsensical reported number, not a crash, for the same
  "reporting-only, not fed back into dynamics" reason as
  `_osculating_elements()`.
* **`engine.constellation`'s Walker-pattern math**
  (`raan_spread/num_planes`, `360/sats_per_plane`, etc.) divides by
  request parameters that `ConstellationRequest.validate()` already
  requires to be positive (see `test_request_validation_rejects_bad_input`)
  before any of this math runs -- pure Python arithmetic, not
  Basilisk-facing, and already schema-guarded.
* **`engine/fsw.py`** (attitude guidance/control wiring) has no custom
  vector-normalization math at all -- it only configures Basilisk's own
  `hillPoint`/`velocityPoint`/`mrpFeedback`/etc. modules directly,
  consistent with this project's convention of never reimplementing
  Basilisk's own math.

Also documented (not a code fix): `PhasingKeepingConfig`'s own docstring
(`schema/scenario.py`) now states the "use a small nonzero eccentricity,
not exactly 0.0" caveat directly, so a user authoring their own
phasing-keeping scenario (not just the bundled template) has a chance to
avoid this landmine before hitting it for real.

**Verification:** 5 new tests in `tests/test_orbit_maintenance.py`
(`requires_basilisk`, auto-skipped in this sandbox) --
`test_phasing_keeping_skips_thrust_on_zero_velocity` (the new
`PhasingKeepingController` guard), and four for
`ConstantFrameThrustController`:
`test_constant_thrust_skips_on_nan_state`,
`test_constant_thrust_skips_on_zero_velocity`,
`test_constant_thrust_skips_on_parallel_r_and_v` (the case neither a
finite check nor a zero-velocity check alone would catch), and
`test_constant_thrust_runs_normally_with_finite_state` (confirms the new
guard doesn't change behavior for the ordinary case). 600 passed, 71
skipped in this sandbox (5 more skipped, matching the 5 new tests). Not
yet confirmed against a real Basilisk build.

## Template '05' crash persists after the eccentricity fix -- isolating the cause

The eccentricity fix's OWN target bug is confirmed fixed: the user's next
crash log shows `phasing_keeping` reporting `error=-0.9125 deg` -- almost
exactly the true physical separation (hand-computed: -0.9135 deg), not
the wildly wrong `-0.0882 deg` from before. But **the crash still
happens, at the exact same point** (t=30 s to t=60 s, the first real
dynamics tick). That rules out the phasing-error noise as the (sole)
trigger -- it was a real, separate, worth-fixing bug, but not the reason
this scenario crashes.

One side effect of the fix, visible in this same log, that hadn't been
exercised before: `station_keeping` is now ACTIVELY BURNING
(`burn_on=True`) at t=30 s, where it previously was not. Both spacecraft
start at `true_anomaly_deg=0` -- with the new `eccentricity=0.001`,
that's PERIAPSIS, the lowest point of the orbit, about 7 km below the
mean/target altitude. `StationKeepingController`'s altitude smoothing
only has ONE sample on the very first tick, so it immediately sees
"6.9 km below deadband" and fires -- a real, if minor, side effect of the
eccentricity fix worth knowing about even independent of the crash
investigation.

That the crash persists with an entirely DIFFERENT controller now doing
the (small, bounded, ordinary) commanded burning is itself informative:
it suggests the trigger may have nothing to do with WHICH
`engine.orbit_maintenance` controller fires, or possibly nothing to do
with `engine.orbit_maintenance` at all. To find out directly rather than
keep guessing from either side, this repository now also includes
`missionstudio/scenarios/diagnostic_05_no_orbit_maintenance.json` -- NOT
a bundled template (it does not appear in the GUI's Load Scenario tab;
open it via Open/Browse, or `missionstudio run
missionstudio/scenarios/diagnostic_05_no_orbit_maintenance.json` from
the CLI). It is otherwise IDENTICAL to `05_formation_flying_phasing.json`
(same two near-circular, 45-degree-inclination, sun-perturbed orbits,
same 7-day/30-second-tick/rkf78 settings) with `station_keeping` and
`phasing_keeping` removed entirely from `follower-1` -- plain two-body
-plus-sun-third-body dynamics for both spacecraft, no custom force
effector active on either one at all.

**If this diagnostic scenario ALSO crashes** around the same t=30-60 s
window, that proves the crash has nothing to do with
`engine.orbit_maintenance` -- something in the core gravity/integrator
setup for two co-located, sun-perturbed, `orbit_only`-mode spacecraft is
the actual trigger, and the investigation moves to `engine.service.build()`
and Basilisk's own dynamics/gravity wiring instead. **If it does NOT
crash**, that rules core dynamics out and points the investigation back
at the force-effector wiring itself -- e.g. `StationKeepingController`'s
own burn, or two controllers sharing one `ExtForceTorque` object.

**Result, confirmed by the user: this diagnostic ran the FULL 7 days with
no crash at all** (`run_live: 100.0% complete`, no error). Conclusive:
the crash is NOT in core gravity/integrator/two-spacecraft setup -- it
requires a force effector actually being active on follower-1. Rules out
an entire class of hypothesis (sun ephemeris timing, task priority
ordering, generic two-spacecraft interaction) and narrows the
investigation specifically to `engine.orbit_maintenance`'s force
-effector wiring or control logic.

## Second diagnostic: isolating which part of orbit_maintenance is responsible

Both real crashes so far had SOME `orbit_maintenance` controller
actively commanding nonzero thrust through follower-1's `ExtForceTorque`
effector at the failing tick (phasing's `BURN_OUT` state in the first
crash, station-keeping's altitude burn in the second) -- but those two
controllers share more than just "a force": the same propellant/mass
-bookkeeping pattern (`engine.propellant_bookkeeping.
apply_propellant_burn`, which writes `scObject.hub.mHub` every tick,
including on non-thrusting ticks), the same `ExtForceTorque` effector
object (phasing shares station-keeping's), and each has its OWN extra
logic on top (station-keeping's altitude-deadband/smoothing/eclipse
gating; phasing's drift-orbit state machine and thruster arbitration).

New `missionstudio/scenarios/diagnostic_05b_constant_thrust_only.json`
(same non-template placement as the first diagnostic) isolates which
part: identical orbits/duration/rate/integrator/gravity, but follower-1
has ONLY `constant_thrust` configured (a small constant 0.05 N prograde
burn -- same magnitude used elsewhere in this template) instead of
`station_keeping`/`phasing_keeping`. `ConstantFrameThrustController` is
about as simple as a force effector in this codebase gets: no state
machine, no altitude smoothing, no thruster arbitration, no eclipse
gating -- just a fixed-direction force and the same shared
mass-bookkeeping write every tick.

**If this ALSO crashes**, the trigger is in the shared force-effector/
mass-bookkeeping mechanism common to all three controllers (most likely
suspect: the every-tick `scObject.hub.mHub` write, possibly interacting
with the RK78 adaptive integrator's own internal substepping in a way
that's fine for `missionAnalysis`'s original, coarser-task-rate version
of this pattern but not for running it on the SAME task as the dynamics
integration itself, which is what `engine.orbit_maintenance`'s own
module docstring already flags as the one deliberate difference from the
ported original). **If it does NOT crash**, the trigger is specifically
in `StationKeepingController`'s or `PhasingKeepingController`'s own extra
logic, not the shared mechanism -- narrowing to the altitude-smoothing/
thruster-arbitration/eclipse-gating code neither shares with
`ConstantFrameThrustController`.

**Result, confirmed by the user: this diagnostic ALSO ran the full 7 days
with no crash.** Rules out the shared mass-bookkeeping mechanism -- the
trigger is specifically in `StationKeepingController`'s and/or
`PhasingKeepingController`'s own extra logic (eclipse-gating,
altitude/error-smoothing history, or the two-controllers-sharing-one
-thruster arbitration), none of which `ConstantFrameThrustController`
has.

## Third diagnostic: station-keeping alone, no sharing with a second controller

One structural difference between the two clean diagnostics and the real
crash stands out: template '05' has TWO controllers
(`StationKeepingController` + `PhasingKeepingController`) sharing ONE
`ExtForceTorque` effector and one propellant tank, with explicit
thruster-arbitration logic (`thrusterHeldByAltCtrl`) deciding which one's
`extForce_N` write wins each tick -- neither of the two clean diagnostics
tested that sharing at all (constant_thrust is the only controller on its
spacecraft). Comparing `build_station_keeping()`/`build_constant_thrust()`
directly shows their `ExtForceTorque` wiring is otherwise structurally
identical (same `addDynamicEffector`/`AddModelToTask` pattern, no
priority difference) -- ruling out a wiring bug as the remaining
explanation.

New `missionstudio/scenarios/diagnostic_05c_station_keeping_only.json`
isolates the sharing question directly: identical to the real template
except `phasing_keeping` is removed from follower-1 entirely --
`station_keeping` alone, with its own eclipse-gating and
altitude-smoothing history intact, but no second controller and no
thruster arbitration.

**If this crashes**, the trigger is in `station_keeping`'s own logic
(eclipse-gating and/or altitude-smoothing), independent of any sharing.
**If it does NOT crash**, that implicates the two-controllers-sharing-one
-effector/arbitration mechanism specifically -- something about
`phasing_keeping` being present and sharing `station_keeping`'s effector,
not either controller's logic in isolation.

**Result, confirmed by the user: `station_keeping` alone crashes, at the
identical point, with identical state.** Conclusive: NOT the
two-controllers-sharing-one-effector mechanism (there's only one
controller here) -- the trigger is specifically in
`StationKeepingController`'s own logic.

## Fourth diagnostic: eclipse machinery present vs. actually read

Comparing the one clean diagnostic (`constant_thrust` alone) against the
one crashing diagnostic (`station_keeping` alone) with everything else
held equal (same thrust magnitude 0.05 N, same VNB-prograde direction,
same mass-bookkeeping write, same fuel-tank message, both start applying
nonzero force on their very first tick): the one remaining code
difference is eclipse-gating.
`StationKeepingController.UpdateState()` reads
`self.eclipseInMsg.isLinked()` / `.shadowFactor` every tick;
`ConstantFrameThrustController` has no eclipse message reader at all --
and because `constant_thrust` alone doesn't trigger
`engine.service.build()`'s `needs_eclipse` condition
(`power`/`station_keeping`/`enable_srp`), that earlier clean diagnostic
never even built the shared `Eclipse()` model in the first place.

New `missionstudio/scenarios/diagnostic_05d_constant_thrust_with_eclipse_model.json`
isolates whether it's the mere PRESENCE of that machinery, or the ACT of
reading it, that matters: `constant_thrust` alone again (no eclipse
message reader, same as the clean diagnostic), but with `enable_srp=True`
added -- this forces `needs_eclipse` true and builds the real shared
`Eclipse()` model/SRP effector, exactly as `station_keeping` does,
WITHOUT `constant_thrust` itself ever reading `eclipseInMsg`.

**If this crashes**, the `Eclipse()`/SRP machinery itself is implicated,
independent of which controller reads it -- something about that model's
construction or its interaction with the integrator. **If it does NOT
crash**, that points specifically at `station_keeping`'s/
`phasing_keeping`'s own act of reading `eclipseInMsg.isLinked()`/
`.shadowFactor` from within their `UpdateState()` callback as the actual
trigger -- an unusual but very specific, actionable finding to chase down
next (e.g. in how `EclipseMsgReader()` behaves when read from a Python
`SysModel` callback versus a C++ one).

**Result, confirmed by the user: this diagnostic ran the full 7 days with
no crash.** Fully exonerates the `Eclipse()`/SRP machinery itself --
narrows the trigger to the ACT of reading `eclipseInMsg` from a custom
Python `UpdateState()` callback, specifically via
`StationKeepingController`'s/`PhasingKeepingController`'s own
`.shadowFactor` read.

## A deprecated-field theory that turned out not to hold on a real build

Reading Basilisk's own C++/SWIG source (not this project's code) turned
up the actual field. `EclipseMsgPayload.shadowFactor`
(`src/architecture/msgPayloadDefC/EclipseMsgPayload.h`) is DEPRECATED in
favor of `illuminationFactor` (same value, same semantics -- confirmed by
Basilisk's own unit test,
`src/simulation/environment/eclipse/_UnitTest/test_eclipse.py`'s
`test_shadow_vs_illumination_alias_and_deprecation_behavior`, with a
removal deadline of 2026-12-31).

**Correction, since an earlier revision of this section named a specific
internal mechanism that turned out to be wrong -- caught by going back
and verifying it directly against Basilisk's generator source rather
than leaving the claim standing on inference:** the generic
`swig_deprecated.i`/`_inject_deprecated_property` machinery (which DOES
re-inject a class-level `property()` on every read, and was this
project's first guess) is NOT what backs `shadowFactor`/
`illuminationFactor`. That field has its own hand-written, one-off
aliasing block, specific to `EclipseMsg` alone among every message type
(`src/architecture/messaging/msgAutoSource/msgInterfacePy.i.in`, the
`if "{type}" == "EclipseMsg":` block): it assigns
`EclipseMsgPayload.illuminationFactor`/`.shadowFactor` as plain
`property()` objects on the class exactly ONCE, at Python import time --
not re-injected per read, per tick, or per instance. So the specific
"repeated class mutation from a hot loop" story in an earlier revision of
this section does not hold up, and no other confirmed mechanism has
replaced it: what Basilisk's own C++/SWIG layer does internally that
makes reading this one deprecated property unsafe from a Python
`SysModel` callback is NOT established here, only that it empirically is
-- proven by elimination, not inferred from a plausible-sounding
mechanism. Four separate diagnostic scenarios agree: `constant_thrust`
(no eclipse reader at all) ran clean; the SRP effector with the SAME
shared `Eclipse()` model present, read only in C++, ran clean;
`station_keeping` alone -- the one thing that reads `.shadowFactor` from
Python every tick -- reliably crashed at the identical point every time.
That is the actual evidence for this fix; the mechanism inside Basilisk
remains an open question, not something this project's investigation
resolved.

**This theory did not survive contact with a real build.** Switching to
`.illuminationFactor` was pushed and the user tried it -- and it failed
immediately with `AttributeError: 'EclipseMsgPayload' object has no
attribute 'illuminationFactor'`. That field does not exist at all on
their installed Basilisk build, which means: their build predates
`illuminationFactor` being added, `shadowFactor` was never deprecated in
their actual runtime (there is no aliasing/deprecation machinery on a
build that doesn't have the new name to alias to), and this project's
`illuminationFactor`/`shadowFactor` deprecation story -- while accurate
for the LATEST Basilisk source tree available for reading in this
environment -- was never the right frame for what is actually installed
on the user's machine. This project does not pin an exact Basilisk
version (see `pyproject.toml`'s own comment on why), so a fix that only
works against one specific source-tree snapshot was never going to be
correct in the first place.

**What this means for the original crash: the root cause is still
open.** The diagnostic sequence that isolated eclipse-reading as the
empirical trigger (`constant_thrust` clean, SRP-with-eclipse-model clean,
`station_keeping` alone reliably crashing) is still valid evidence -- it
ran on the user's real, unchanged Basilisk build throughout, reading
`.shadowFactor` the entire time (the only field that build has). But the
explanation for WHY reading it crashes cannot be "it's deprecated and
unstable," because on this build it isn't deprecated at all -- it's
simply the current, only, ordinary field. Whatever actually makes
reading the eclipse message from a Python `SysModel` callback unsafe on
this specific installed build remains unidentified.

**Fixed for real, scoped correctly this time:** new
`_eclipse_illumination_fraction()` in `engine/orbit_maintenance.py` tries
`.illuminationFactor` first (Basilisk's current documented name, per this
checkout's own source) and falls back to `.shadowFactor` only on
`AttributeError` (i.e. only on a Basilisk build old enough not to have
the new name at all) -- both `StationKeepingController.UpdateState()`
and `PhasingKeepingController.UpdateState()` now go through it. This does
NOT claim to fix the underlying crash (it can't, without knowing the real
mechanism) -- it only makes this one read tolerant of both Basilisk API
generations instead of hard-crashing with an `AttributeError` on an
older build, which is what the previous, now-reverted `.illuminationFactor`
-only version did. Expect the ORIGINAL crash (the one `diagnostic_05c_
station_keeping_only.json` reliably reproduced, reading `.shadowFactor`
either way) to still occur on the next run -- this fixes the regression
this project itself introduced, not the crash the investigation started
with.

**Verification:** two new tests,
`test_eclipse_illumination_fraction_prefers_new_name` and
`test_eclipse_illumination_fraction_falls_back_to_old_name` (the second
one directly modeling the real user's build: a stub payload object with
`shadowFactor` but no `illuminationFactor` attribute at all), in
`tests/test_orbit_maintenance.py` (`requires_basilisk`, auto-skipped in
this sandbox since even constructing the stub payload's consumer needs
the module's Basilisk imports to succeed). 600 passed, 73 skipped in
this sandbox (2 more skipped, matching the 2 new tests).

## The actual root cause, found for real: not eclipse at all

Everything in the sections above -- the deprecated-field theory, the
`illuminationFactor`/`shadowFactor` fallback, "the root cause is still
open" -- was a dead end. Eclipse was never involved in the original
crash. Here is what actually happened, found by continuing the
diagnostic sequence with real repros rather than assuming the eclipse
angle was the only thread left to pull.

**Two more real diagnostics fully exonerated eclipse.** A debug log of
the raw value `StationKeepingController`/`PhasingKeepingController`
read from `EclipseMsgPayload` every tick showed it was always a
completely sane `1.0` (fully sunlit) right up to the crash -- ruling
out a bad/NaN value. A follow-up diagnostic switch that skipped the
eclipse message's `subscribeTo()` call entirely (not just the read --
`isLinked()` stayed `False` the whole run, confirmed by zero
eclipse-related log lines) still crashed identically. Eclipse, the
value it carries, and the act of reading or even subscribing to it,
are conclusively not the trigger.

**A controlled A/B comparison then ruled out `station_keeping`'s own
control logic too.** `diagnostic_05b_constant_thrust_only.json` (clean)
and `diagnostic_05c_station_keeping_only.json` (crashes) use
byte-for-byte identical orbits, and -- because station-keeping's
altitude deadband trips on tick 1 in this configuration -- identical
thrust magnitude, direction, and timing throughout. Both write a
`FuelTankMsgPayload` every tick. Swapping the adaptive `rkf78`
integrator for the fixed-step, non-adaptive `rk2` (which structurally
cannot exhibit "the adaptive step-size search spins forever on a NaN
error estimate," the mechanism this project's own error message
blames) made no difference either -- same crash, same signature. Every
hypothesis this project could test from the Python side was tried and
eliminated.

**The actual break: the headless CLI (`missionstudio.cli run`) ran the
exact same crashing scenario to completion, clean, first try.** Every
single crash report collected across this entire investigation came
from the GUI's `run_live()` path, and every one of them logged
`Basilisk-Vizard connection made` -- something this project had not
isolated as a variable until debugging under `gdb` forced a
Vizard-free headless run. That pointed at Vizard, not station-keeping,
not eclipse, not the integrator.

**Confirmed with a real `gdb catch throw`/`bt`** on a fully isolated
repro: headless CLI, `--vizard-save-file` (no live Vizard connection
needed, just exercises the same `enable_vizard()` build path), station-
keeping only. Full native backtrace:

```
VizInterface::WriteProtobuffer(unsigned long)
  -> google::protobuf::internal::ArenaStringPtr::Set(std::string const&, Arena*)
    -> std::string::_M_create()
      -> throws std::length_error
```

thrown on `vizInterface`'s own background write thread -- not the main
simulation thread, and not anywhere near `orbit_maintenance.py`.

**Root cause:** `engine/vizard.py`'s `enable_vizard()` builds a
`vizInterface.GenericStorage` "Propellant" panel for every spacecraft
with `station_keeping` configured (never for `constant_thrust`, which
is exactly the split every diagnostic above kept finding). Reading
Basilisk's own `vizStructures.h`: `VizSpacecraftData::genericStorageList`/
`genericSensorList` are `std::vector<GenericStorage *>`/
`std::vector<GenericSensor *>` -- raw POINTER vectors.
`vizSupport.enableUnityVisualization()` only stores the pointers it's
handed; it never clones the pointed-to structs. The `panel`/`sensor`
objects `enable_vizard()` built (and their embedded
`FuelTankMsgReader`/`PowerStorageStatusMsgReader`/`DeviceCmdMsgReader`
readers) were local variables, never returned, never retained anywhere
-- garbage-collected the instant `enable_vizard()` returned, while
`VizInterface` kept dangling pointers to them and dereferenced one
every tick from its background thread, eventually reading freed/reused
memory as a corrupt string length.

This is the exact same bug class this same module already found and
fixed once before, for `_AccessIndicatorBridge` (see that section's
own history above the "Live-data panels" docstring in
`engine/vizard.py`) -- right down to the identical
`basic_string::_M_create`/`std::length_error` signature. That earlier
fix's own justification for not extending the same retention to
`GenericStorage`/`GenericSensor` ("their relevant state is copied into
Basilisk's own C++ containers") was an unverified assumption, never
checked against `vizStructures.h`, and it was wrong for these two
specific pointer-vector fields.

**Fixed the same way as the bridge fix:** `enable_vizard()` now also
returns `generic_storage_list`/`generic_sensor_list` alongside
`viz`/`access_indicator_bridges`, and `engine.service.SimulationService`
retains all four (`_viz`/`_viz_access_indicator_bridges`/
`_viz_generic_storage_list`/`_viz_generic_sensor_list`) for the
instance's lifetime instead of just the first two.

**Verification:** `tests/test_vizard.py` (new,
`requires_basilisk`) -- `test_station_keeping_with_vizard_save_file_does_not_crash`
runs `diagnostic_05f_station_keeping_fixed_step_integrator.json` with a
real `VizardRequest(save_file=...)` through `SimulationService.run()`
end to end (this is the actual regression check: it used to raise
`SimulationServiceError` wrapping `std::length_error`/`std::bad_alloc`
within the first couple of ticks, every time); `test_generic_storage_
and_sensor_lists_are_retained_after_build` checks the fix directly --
`service._viz_generic_storage_list` is non-`None` and carries a real
entry after `build()`. Both auto-skip in this sandbox (no Basilisk
build here) but were designed directly from, and match, the real
crash this project's user reproduced and debugged with `gdb` on their
own machine. 600 passed, 75 skipped in this sandbox (2 more than the
count above, matching these 2 new tests). The temporary
`MISSIONSTUDIO_DIAG_SKIP_ECLIPSE_READ`/`_SUBSCRIBE` diagnostic switches
used to isolate eclipse as a non-cause have been removed from
`engine/orbit_maintenance.py` now that the real root cause is fixed.

## RTN separation panels: "Unavailable" readout, and whose offset is it

Two more real bugs/gaps found from a live Vizard screenshot, on the
Radial/Transverse/Normal separation panels a previous round (see
`engine/vizard.py`'s own docstring, "A THIRD round of feedback") had
just replaced the single vague "Separation" scalar with.

**Bug 1: Radial and Normal showed "Unavailable"; Transverse rendered
fine.** All three panels are built identically (same
`vizInterface.GenericStorage` construction, same
`DataStorageStatusMsgReader` wiring) -- the only difference at that
moment was sign: Transverse happened to be positive, Radial and Normal
happened to be negative. `PhasingKeepingController.UpdateState` clamped
`storageLevel` SYMMETRICALLY (`[-storageCapacity, storageCapacity]`),
specifically to preserve "ahead of"/"behind the chief" direction in
Vizard's own native numeric readout. Checked directly against
Basilisk's own field comments -- both `vizStructures.h`'s
(`GenericStorage::currentValue`/`maxValue`, `"current/maximum absolute
value of the storage device"`) and the wire-format
`vizMessage.proto`'s (identical wording) -- `GenericStorage` is
documented as a non-negative gauge, the same kind of quantity as the
battery/propellant/delta-V panels right next to it. A negative
`storageLevel` is out of that contract; Vizard's own client evidently
rejects it outright rather than rendering a broken bar the way an
OVER-capacity value did in an earlier round.

**Later CONFIRMED directly, not just inferred from field comments:**
the `0h3xn4/vizard` Unity project (cloned into this session separately
-- Vizard's client had been assumed closed-source/unavailable to this
project up to that point, which turned out not to be the case) was
checked against this exact question.
`GenericStorageUnitMethods.cs`'s `UpdateCurrentValue()` reads:

```csharp
float value = (float) myMsg.CurrentValue;
...
if (value >= 0) { /* normal bar + "<value> / <maxValue> <units>" */ }
else
{
    hoverText.text = "Unavailable";
    verboseText.text = "Unavailable";   // "Stale" in VR
    verboseText.color = Color.gray;
    measurementRect.GetComponent<Image>().color = Color.gray;
    measurementRect.sizeDelta = new Vector2(0, barHeight);
}
```

A hard `value >= 0` branch, unconditional -- no tolerance for a small
negative number, nothing to do with `maxValue` or color thresholds.
Exactly the mechanism this section's own reasoning (field-comment
wording plus the screenshot's positive/negative split) had inferred,
now confirmed from the actual rendering code rather than circumstantial
evidence.

Fixed in `orbit_maintenance.py`: `_clamp_symmetric` replaced with
`_clamp_magnitude` (`min(abs(value), limit)`) -- `storageLevel` now
publishes MAGNITUDE, not signed direction. A real, honest trade-off,
not a full fix: Vizard's live panels can no longer show "ahead of"/
"behind the chief"; the signed numbers remain available as
`lastRadialKm`/`lastTransverseKm`/`lastNormalKm` on the controller
itself, just not live in Vizard.

**Bug 2 (same round): the panels never said whose offset they were
measuring.** "Radial (R)" on a follower's own storage panel doesn't say
which chief it's relative to. Fixed by threading the chief spacecraft's
own `ModelTag` through as `PhasingKeepingController.chiefName` (wired
by `build_phasing_keeping` from `chief_sc_object.ModelTag`), and a new
`engine.vizard._rtn_panel_label(axis_letter, chief_name, follower_name)`
helper that folds it into the label itself (e.g. `"R vs chief-1"`) --
originally falling back to a generic `"R vs chief"` past a flat,
14-character budget (the longest confirmed NOT to truncate against one
real screenshot).

**Later refined once the Unity source was available (see above):**
that flat 14-character budget turned out to be specific to the
screenshot's own scenario, not a universal constant.
`GenericStoragePanelMethods.cs`'s `InitializePanel()` sets
`panelName = spacecraftName + " Storage"` and only widens the row's bar
(and hence its label's usable width) past a hardcoded 90px default when
`panelName.Length > 16` -- to `panelName.Length * 7` pixels, applied
via `SetBarWidth()` UNIFORMLY to every row in that spacecraft's own
panel. The confirming screenshot's spacecraft ("follower-1", 10
characters) crossed that threshold (123px usable); a SHORTER name (8
characters or fewer, e.g. "sat-1") never does, leaving only 87px --
narrower than what "14 characters" was actually confirmed against. The
prefab (`GenericStoragePanelUnit.prefab`) also confirms the render mode
this matters for: `m_enableAutoSizing: 0`, `m_TextWrappingMode: 1`
(NoWrap), `m_overflowMode: 3` (`TextOverflowModes.Truncate`) -- a hard
per-pixel cutoff.

Fixed: `_usable_label_width_px(follower_name)` computes the real,
per-scenario usable width from Vizard's own formula; no glyph-metrics
table is available for the font in this repo (a built-in TMP font, not
a checked-in asset), so pixel width is converted to a character budget
via a conservative estimate (`_PIXELS_PER_LABEL_CHARACTER_ESTIMATE`,
calibrated against the one confirmed real data point and padded up so
it underestimates rather than overestimates). `_rtn_panel_label` now
has THREE fallback tiers, not two: `"{axis} vs {chief}"` ->
`"{axis} vs chief"` -> the bare axis letter alone (always 1 character,
always fits) -- since on a narrow enough panel even the generic
fallback can exceed the budget.

**Verification:** `tests/test_orbit_maintenance.py`'s two RTN tests
rewritten for magnitude semantics (real Basilisk, both pass -- 27
tests total in that file with the new `chiefName` wiring smoke-tested
separately, not added as a permanent test); `tests/test_vizard_labels.py`
rewritten (8 tests, no Basilisk needed -- these functions have no
Basilisk import, unlike the rest of `engine.vizard`) to cover the
width-aware budget directly, including the narrow-panel/deeper-fallback
case. `chiefName` wiring confirmed end-to-end against real Basilisk
with a standalone script (`build_phasing_keeping()` called directly,
`controller.chiefName == "chief-1"` after); label output for this
project's own `05_formation_flying_phasing` template's actual
spacecraft names confirmed the same way. Both the magnitude fix (bug 1)
and the truncation-width formula (bug 2) are now confirmed directly
against Vizard's own Unity source rather than inferred from a
screenshot or field comments -- only the characters-per-pixel
conversion remains an estimate (no font glyph metrics available).

## Perturbation-model audit: gravity/third-body on every template, atmosphere-model choice, a historical-percentile drag margin

Real user request, in three parts: "why can't I select the atmospheric
drag model, other tools let me choose Jacchia-Roberts or NRLMSISE-00";
"I am missing solar radiation pressure [in Propagation Setup]"; and "I
need all example scenarios to have all perturbations activated ...
spherical harmonics of 10th order, sun and moon third-body
perturbations, 95th percentile/+2sigma atmospheric drag".

**Atmosphere-model choice.** Checked Basilisk's own
`src/simulation/environment/` tree directly (not assumed): it ships
exactly `ExponentialAtmosphere`, `MsisAtmosphere` (NRLMSISE-00), and
`TabularAtmosphere` -- no Jacchia-Roberts model at all, so that specific
option genuinely cannot be offered. New
`SpaceWeatherConfig.atmosphere_model` (`"nrlmsise00"` | `"exponential"`)
lets `engine.service` build either; `"exponential"` is configured via
Basilisk's own `simSetPlanetEnvironment.exponentialAtmosphere()` helper
(the same sea-level Earth constants a real shipped Basilisk example,
`examples/scenarioDragDeorbit.py`, uses for its own exponential-model
deorbit case). Confirmed directly against real Basilisk (a standalone
density-recorder run, not guessed) that this simple model under
-predicts LEO density by many orders of magnitude versus NRLMSISE-00 --
documented plainly as an inherent limitation of the model, not a wiring
bug: pick it for speed/simplicity, never for an accurate drag estimate.
`TabularAtmosphere` (a user-supplied density table) was deliberately
left out -- it would need a new file-upload schema/GUI concept of its
own.

**Conservative ("worst-case") drag margin.** No such concept exists in
Basilisk itself, and this project has no authoritative source for a
specific fixed "worst-case" F10.7/Ap constant to hand-code -- asked the
user how to define it rather than guessing a physical constant; answer:
derive it statistically from REAL historical data. New
`engine.spaceweather.compute_worst_case_activity()`/`generate_worst_case()`
compute the requested percentile (default 95th) of `F10.7_OBS`/`AP_AVG`
across a real historical CelesTrak extract (refuses fewer than 365 days
of real history, and refuses `source="synthetic"` outright -- a
percentile of a fabricated profile is not a real historical "worst
case") and write a CSV holding that value CONSTANT across the whole
scenario (a sustained-worst-case assumption, not a single spike).
`SpaceWeatherConfig.activity_level`/`activity_percentile` expose it;
`PropagationSetupDialog` gained matching combo/spinner controls, grey
-ing out correctly when `atmosphere_model="exponential"` is selected
(no F10.7/Ap dependence at all in that case).

**Solar radiation pressure discoverability.** Already existed as a
per-spacecraft `enable_srp` toggle on `SpacecraftEditorDialog`'s "Orbit
/ mass" tab -- not a missing feature, a UX gap: looking for it
specifically in `PropagationSetupDialog` and not finding it read as
"not supported." Fixed with an explicit pointer `QLabel` in that
dialog's space-weather group (never a docstring the user never sees).

**Every example template audited individually, not blanket-edited** --
`01` (clean two-body Kepler baseline) and `09` (Monte Carlo dispersion
analysis whose own description explains its lesson specifically
requires the ABSENCE of drag/SRP) were deliberately left untouched;
`02`/`03` got gravity-only updates (drag would muddy `02`'s J2 -
precession visual, or is physically negligible at `03`'s GEO altitude);
`04`/`05`/`07`/`08` got the full set (10th-degree gravity, Sun+Moon
third-body, drag, SRP, the conservative margin) since none of their own
stated lessons depend on a clean/unperturbed baseline. `06` got gravity
-only, preserving its explicit role as "the simple version" (`07` being
"the realistic counterpart"). All built through
`scripts/_generate_templates.py` (the existing regeneration source of
truth, updated in place, not hand-edited JSON) -- see that script's own
`_conservative_drag_margin()` helper and each `build_*()` function's
comments for the per-template reasoning.

**Earth-albedo/IR radiation pressure -- investigated, deliberately NOT
added.** A second real user request. Basilisk's `earthRadiationModel`
computes albedo/IR flux, but its own payload doc names
`facetERPDynamicEffector` as the consumer that turns that flux into an
actual orbital force -- and that module doesn't exist anywhere in this
Basilisk build (checked the source tree and the installed package, not
assumed). Adding it for real would mean writing a brand-new,
never-before-exercised force-effector from scratch (the same
`extForceTorque` manual-force-injection pattern this project's own
thrust controllers already use, plus the standard flux/c * area * Cr
formula solar SRP already uses) -- asked the user rather than silently
writing untested physics code under a broader "add perturbations"
instruction; answer: skip it, document the finding (see README's
"Known limitations").

**Verification:** `tests/test_spaceweather.py` grew from 14 to 21 tests
(percentile computation matches `numpy.percentile` directly, short
-history rejection, synthetic-source refusal, the full `resolve()`
conservative-mode path) -- no Basilisk needed, this module has none.
`tests/test_scenario_schema.py` grew by 6 (new field validation/round
-trip). `tests/gui/test_propagation_setup_dialog.py` grew from 10 to 17
(new controls' enable/disable gating, round-trip, the SRP pointer
label's presence). `tests/test_scenario_templates.py` (41 tests)
re-passes unchanged against the regenerated templates. The exponential
-atmosphere wiring itself was confirmed against real Basilisk with a
standalone density-recorder script (bypassing `SimulationService.build()`,
which needs SPICE kernels this sandbox cannot fetch) -- plausible,
positive LEO density recorded end-to-end. 644 passed, 99 skipped in
this sandbox without a Basilisk build; the conservative-margin
templates (`04`/`05`/`07`/`08`) need real network access to CelesTrak
(or a local historical file) to actually RUN, not just validate --
disclosed plainly in each file's own `description` and in this
project's README, not a silent gap.

## "Seamlessly integrate Basilisk and Vizard" -- auto-fetching a pre-built binary

Real user request: merge the Basilisk and Vizard repositories/builds so
neither has to be set up separately. Investigated both repositories
directly (not assumed) before answering: Basilisk builds via CMake +
SWIG + Python; Vizard's OWN repository has no scripted/CLI build path
at all -- only an interactive Unity Editor GUI workflow (install Unity
Hub, install a specific licensed Unity Editor version, open the
project, click through a "Build Profiles" panel per platform; no CI
config, no build scripts exist in that repo). A single build step that
produces both isn't realistic without the user already having Unity
Editor installed and licensed, which this project cannot do on their
behalf. The two are also deliberately separate PROCESSES at runtime --
Vizard plays back a saved `.bin` file with zero Basilisk involvement by
design, not as an artifact of being separate repos.

Asked the user what would actually make this feel seamless; answer: skip
building Vizard from source entirely, auto-fetch AVS's own pre-built
binary instead. `docs/source/Vizard/VizardDownload.rst` (in this
Basilisk checkout) already publishes exactly that -- three fixed,
per-platform `.zip` links a human downloads and unzips manually.

**`gui/vizard_launcher.py`** gained `fetch_vizard()`: downloads the
correct-platform `.zip`, extracts it with an explicit zip-slip guard
(`_safe_extract` -- refuses any entry that would resolve outside the
extraction directory; the URL itself is a hardcoded trusted constant,
not user-supplied, so this is defense in depth, not a response to a
known issue), locates the executable inside (same shallow-search idiom
`find_vizard_executable` already used), and sets the executable bit on
non-Windows platforms (zip extraction doesn't reliably preserve it).
Chunked, cooperatively-cancellable reads (`should_cancel`, checked
between chunks) -- the same pattern `gui.run_worker.RunWorker` already
uses for a running simulation, never a forced thread kill. Raises
`VizardFetchError` on any failure (network, corrupt zip, no executable
found, cancelled) -- one error-reporting path, never a silent partial
install.

**`VizardFetchWorker`** (`QThread`) wraps it for the GUI.
**`MainWindow._locate_or_fetch_vizard`**/**`_fetch_vizard_with_progress`**
wire it into `on_launch_vizard()`'s existing "not found" branch: a
`QMessageBox` now offers "Download Vizard" alongside the original
"Browse...", and the download runs behind a modal, cancellable progress
dialog -- implemented as a NESTED `QEventLoop` (not connecting to the
worker's signals and returning immediately) specifically so
`on_launch_vizard()`'s existing synchronous `bool` return contract
(also relied on by `on_run()`'s live-stream gate) needed no changes.

**Real bug caught while testing this, not a network issue:** the first
version assumed `QEventLoop.quit()` called BEFORE `exec()` would make
the very next `exec()` call return immediately. Confirmed the hard way
(a test using a synchronous fake worker hung indefinitely) that this is
wrong -- Qt's own documented behavior is that `quit()` is a no-op if
the loop isn't running yet. Only matters for a worker that happens to
finish synchronously inside `start()` (never the real, genuinely
-threaded case, where `start()` returns almost instantly, well before
any background work could finish) -- fixed by checking whether the
outcome was already populated before calling `loop.exec()` at all.

**Verification:** `tests/gui/test_vizard_launcher.py` grew by 14 tests
(`fetch_vizard`'s download/extract/error paths, `_safe_extract`'s
zip-slip guard on both a malicious and a normal zip, `VizardFetchWorker`'s
signal wiring) -- network always mocked
(`urllib.request.urlopen` never touches the real
`hanspeterschaub.info`, confirmed blocked by this project's development
sandbox elsewhere, e.g. `engine.kernels`'s own SPICE-kernel fetch using
the same host as a backup URL). `tests/gui/test_main_window.py` grew by
7 (the new `QMessageBox` routing, the progress-dialog flow's success/
failure paths, using a fake `QObject`-based worker rather than a real
`QThread` -- mirrors this file's own existing `RunWorker`-patching
convention). 667 passed, 99 skipped in this sandbox. The real
network fetch itself is unverified end-to-end here (same sandbox
network-policy limitation as CelesTrak/SPICE elsewhere in this
project) -- written directly against `VizardDownload.rst`'s documented
links and Vizard's own documented `.zip` contents; verify on first
real-network use.

## First real-network run of fetch_vizard() -- a real bug, found and fixed

Asked a real user to run `fetch_vizard()` on their own machine, since
this project's own development sandbox can't reach
`hanspeterschaub.info` at all (confirmed via the sandbox's own proxy
status endpoint: an organization egress-policy denial, not a timeout --
every environment available to this session shares the same policy, so
there was no way to test this from here no matter which environment a
new session used).

**Real result:** `HTTPError: 403 Forbidden`, straight from the server,
on the very first `urlopen()` call. Root-caused (not guessed, though the
signature is a well-known one): `urllib.request.urlopen(url, ...)`
called with a bare URL string sends Python's own default `User-Agent`
header (`"Python-urllib/<version>"`), which is routinely blocked by
basic bot-protection on static-file hosts that have no issue with an
ordinary browser downloading the exact same public file by hand --
`VizardDownload.rst` already publishes this exact link for anyone to
click.

**Fixed** in both `gui.vizard_launcher.fetch_vizard()` (the one
actually reported broken) and, proactively, `engine.spaceweather.fetch()`
(the identical bare-`urlopen()` pattern against a different host,
`celestrak.org`, never itself exercised against the real network in
this sandbox either) -- both now send a realistic browser `User-Agent`
via an explicit `urllib.request.Request(url, headers={...})` instead of
a bare URL string. A standard, widely-used workaround for exactly this
kind of blocking, not an attempt to bypass any real access control.

**Verification:** a new regression test in each affected file
(`test_fetch_vizard_sends_a_browser_like_user_agent`,
`test_fetch_sends_a_browser_like_user_agent`) asserts the actual
outgoing `Request` carries a real `User-Agent` header -- neither
existing test suite would have caught this regressing, since their fake
`urlopen()` never inspected what it was called with, only that some
response came back. 669 passed, 99 skipped in this sandbox. The fix
itself has NOT yet been re-confirmed against the real network with a
second real-machine run -- the user's next run should get past the
download step to whatever (if anything) comes after; report back if it
doesn't.

## Second real-network run -- genuine end-to-end success, plus one cosmetic fix

Same user, same real machine, re-ran `fetch_vizard()` after the
User-Agent fix above. **Real result:** the download succeeded, the
`.zip` extracted, and the executable was found --
`Exists: True`, confirmed against the actual binary on disk, not
assumed. This is the first genuine confirmation that `fetch_vizard()`
works end-to-end against the real `hanspeterschaub.info` host, not just
against a mocked one.

The resulting path was one directory deeper than expected though:
`.../vizard/Vizard_Linux/Vizard_Linux/Vizard.x86_64`, a doubled
`Vizard_Linux` segment. Root cause (confirmed from the real `.zip`
the user actually downloaded, not guessed): `extract_dir` was named
after the zip's own filename with `.zip` stripped (`"Vizard_Linux"`),
but AVS's real `Vizard_Linux.zip` *also* wraps its own contents in a
top-level folder of that exact same name -- so extracting it into a
directory of the same name nests it one level deeper than intended.
`_search_one_root()`'s one-level subdirectory search still found the
executable correctly either way, so this was never a functional bug,
only a cosmetically redundant path.

**Fixed** by decoupling `extract_dir` from the zip's filename
entirely -- it is now a fixed `dest_dir / "extracted"` regardless of
what the `.zip` is called, so a real zip's own wrapper folder (of
whatever name) nests exactly once, not twice. Since `extract_dir` no
longer varies per fetch, a second fix rides along: `fetch_vizard()` now
`shutil.rmtree()`s any existing `extract_dir` before extracting, so a
later re-fetch (e.g. after Vizard publishes a new version) can't leave
an older version's files mixed in with the new one's.

**Verification:** two new regression tests in
`tests/gui/test_vizard_launcher.py` --
`test_fetch_vizard_finds_the_executable_inside_a_same_named_wrapper_folder`
builds a `.zip` whose single entry is `"Vizard_Linux/Vizard.x86_64"`
(mirroring the real zip's own layout) and asserts the resulting path is
exactly `extracted/Vizard_Linux/Vizard.x86_64`, one level of nesting,
not two; `test_fetch_vizard_clears_stale_files_from_an_earlier_extraction`
fetches an "old" zip containing an extra file, then a "new" zip without
it, and asserts the stale file does not survive into the second fetch's
result. 671 passed, 99 skipped in this sandbox. `fetch_vizard()` is now
confirmed working end-to-end on real hardware against the real
`hanspeterschaub.info` host, for both the download and the extraction
steps.

## Third real-network round -- the downloaded binary actually launches

Downloading and extracting is one thing; whether the resulting file is
actually executable was still an open question (fetching leaves the
executable bit fix-up, `subprocess.Popen`, and Vizard's own startup
all unexercised against a real download). Asked the same user to clear
their cache (`rm -rf ~/.cache/missionStudio/vizard`, so the fix above
was actually exercised fresh rather than reusing the earlier doubled
-nested extraction) and use the Run menu's "Launch Vizard" action
directly -- on `on_launch_vizard()` -> `_locate_or_fetch_vizard()` ->
the progress dialog -> `launch_vizard()`'s `subprocess.Popen` on the
freshly-extracted binary.

**Real result:** a Vizard window opened. This is the first
confirmation that the full chain -- download, extraction, the
post-extraction executable-bit fix-up
(`os.chmod`), and `subprocess.Popen` actually starting the Unity
player -- works end-to-end on real hardware, not just against mocked
`urlopen`/zip fixtures. `fetch_vizard()` and `launch_vizard()` together
are now confirmed to take a machine with nothing pre-installed all the
way to a running Vizard window with zero manual steps beyond the one
"Download Vizard" click.

Still unconfirmed: the live-stream path specifically (`-directComm`
pre-filling the socket address, clicking "Start Visualization",
spacecraft actually rendering during a run) -- that additionally needs
Basilisk itself installed, which this user's machine does not yet
have.

## First real live-stream run: a genuine label-legibility bug in the RTN panel colors

The user got Basilisk built from source and registered into the venv
missionStudio runs in, then ran a live-stream scenario end-to-end for
the first time -- the full pipeline (Basilisk -> live socket -> Vizard,
downloaded and launched entirely through this project's own auto-fetch
feature from the last few rounds) worked, and the RTN separation
panels (see the "RTN separation panels" section above) showed real,
correctly-labeled numbers. A screenshot of the running panel showed
the next real problem: the "R vs chief-1" row's dark blue fill made its
own label nearly impossible to read.

**Root-caused, not guessed**, by reading Vizard's own
`GenericStoragePanelUnit.prefab` directly (cloned earlier this
session): the on-bar device-name label
(`StorageName`'s `TextMeshProUGUI`) has its font color hardcoded to a
dark gray, `m_fontColor: {r: 0.19607843, g: 0.19607843, b: 0.19607843,
a: 1}` -- Vizard itself never recolors this text to contrast against
whatever fill color a `GenericStorage` message requests. Computing
perceived luminance (`0.2126*R + 0.7152*G + 0.0722*B`, 0-255 scale)
for that gray (~50) against the fill colors this project had been
using: plain `"blue"` is itself only ~18 -- literally *darker* than its
own label text -- and `"magenta"` (~73) isn't much better. Both R and T
happened to read at/near their max value in the screenshot (100/100
km), so their bars were fully saturated-color for their entire width,
with nothing to break up the low-contrast label. `"green"` (~92, used
for N) fares a little better, and wasn't the one flagged, likely
because N's own value was far below its max (0.45/100 km) so most of
its row was still the neutral gray "unfilled" background, not the
saturated fill. The panel's *other* rows (`"cyan"`, `"yellow"`,
`"orange"`, `"lightgreen"`) were never reported as unreadable -- and
indeed all compute to luminance 170-235, comfortably above the label's
own ~50.

**Fixed** by swapping the three RTN fill colors for lighter,
higher-luminance alternatives with the same computed margin as the
panel's already-readable rows, while keeping each visually distinct
from its neighbors: `"blue"` -> `"lightskyblue"` (~194), `"magenta"`
-> `"violet"` (~161), `"green"` -> `"springgreen"` (~192) -- all
`matplotlib`-recognized names accepted by `vizSupport.toRGBA255()`
exactly like the originals, so no new dependency or plumbing. Not
guessed -- computed directly with `matplotlib.colors.to_rgba()` against
the exact hardcoded label-gray value read from the real prefab file.

**Verification:** no existing test pinned the specific color-name
strings (`grep` confirmed), so this is a pure improvement with nothing
to update test-side; the luminance math above is reproducible directly
from Vizard's own checked-in prefab and `vizSupport.toRGBA255()`'s
`matplotlib` color table, not a subjective guess. Full suite still 671
passed, 99 skipped. Not yet re-confirmed visually against a live
Vizard window by the user -- that's the natural next real-machine
check.

## Result plots: titles/axes/legends, mean orbital elements, and a per-category unit policy

Real user feedback on the result plots, all in one request: "they shall
convey more information"; "should all have titles and more descriptive
axes names and legends"; add plots of AVERAGED (not just osculating/
"true") orbital elements, pointing at STK's "Brouwer-Lyd Mean (Short)"
data provider as the reference concept; "delta-V shall always be
displayed in m/s"; "altitudes, semi-major axes shall be displayed in
km"; "state vector elements shall be displayed in meters for position
and m/s for velocity".

**The unit-display part directly reversed an earlier decision.** This
project's own Plotly-migration work (see above) had added one blanket
rule: every series recorded in "m"/"m/s" displays in km/km-s on the
plot. That rule can't satisfy this new request at all -- it's keyed on
the literal unit STRING, but position (km requested: NO, stay meters)
and semi-major axis (km requested: YES) are both recorded in plain
"m"; velocity (stay m/s) and delta-V (stay m/s) are both plain "m/s".
Fixed by replacing that blanket rule with `results_widget._categorize()`,
which keys off what each named series actually *is* (its category:
state vector, orbit element, controller delta-V, ground-station access,
...), each with its own explicit, independently-chosen unit -- not a
per-unit-string rule at all. An unrecognized/future series still falls
back to the OLD blanket rule (`_legacy_display()`), so nothing regresses
silently for a series this registry hasn't been taught about yet.

**Titles/axis names/legends**: every one of the ~30 series categories
`engine.service`/`engine.link_budget` produce (position, velocity, all
6 osculating + 6 new mean orbital elements, attitude, body rate, sun
heading, control torque, reaction wheel speeds, every sensor type,
battery, all three controllers' delta-V/propellant/altitude/state,
ground-station access/slant-range/elevation/azimuth/link-margin) now
gets a real descriptive title (spacecraft name + a human category name,
e.g. "sat-1: Osculating Semi-Major Axis" instead of the bare
"sat-1.orbit_elements.semi_major_axis" dotted key), a y-axis label
combining a plain-English quantity name with its display unit (e.g.
"Semi-major axis [km]"), and legend entries relabeled from raw column
codes where that helps ("x"/"y"/"z" -> "X"/"Y"/"Z", "raw"/"smoothed" ->
"Raw"/"Smoothed (filtered)", "cumulative_delta_v" -> "Delta-V"). Orbit
-element angles (inclination/RAAN/argument of periapsis/true anomaly)
and ground-station elevation/azimuth additionally display in degrees,
not Basilisk's native radians -- matching every angle INPUT field this
app's own Scenario Editor already uses.

**Mean orbital elements**: the user's own reference (STK's "Brouwer-Lyd
Mean (Short)" data provider) describes a Brouwer-Lyddane-family mean
-element theory; rather than write a bespoke implementation of that
(real orbital-mechanics code this project's own standing rule is never
to hand-write/guess), checked what Basilisk itself ships first --
`orbitalMotion.clMeanOscMap()`, a real, already-used-elsewhere-in
-Basilisk first-order-J2 osculating<->mean mapping (Schaub & Junkins,
*Analytical Mechanics of Space Systems*; the exact same tool Basilisk's
own `meanOEFeedback` FSW module uses for closed-loop mean-element
control). Conceptually the same "strip the once-per-orbit J2 wobble off
the true elements" idea the user's own STK reference describes, built
from a tool Basilisk ships and Basilisk's own FSW code already trusts,
not invented here. `engine.service._mean_elements()` calls it per
-sample (sign=-1: osc -> mean) alongside the existing per-sample
osculating-element loop, publishing `.orbit_elements_mean.*` series
only when a real J2 term is actually being modeled (Earth, spherical
-harmonics degree >= 2) -- a point-mass-only central body has no J2
short-period oscillation in its simulated motion to remove, so applying
the map there would inject an artificial correction instead of
stripping out a real one, which `SimulationService`'s own gating
avoids entirely rather than computing something misleading.

Known, inherited (not introduced) limitation, documented directly in
`_mean_elements()`'s own docstring: first-order J2 mean-element theory
has a genuine mathematical singularity at the critical inclination
(~63.4/~116.6 deg) and degrades near 0/180 deg -- the same well-known
caveat STK's own Brouwer-Lyddane-based "Mean" elements carry. A
scenario at/near either inclination can show NaN/spiky mean-element
samples; Plotly leaves a gap for a NaN rather than erroring, so this is
a visible plot artifact, not a crash.

**Verification:** the core math was checked directly against a real
Basilisk build (this development sandbox has one, unlike most of this
project's work, which needed a real user's machine) -- for a real
non-degenerate LEO orbit (a=7000 km, e=0.01, i=45 deg, away from every
singular inclination), osc-vs-mean semi-major axis differs by ~3.7 km
(matching the expected order of magnitude for a J2 short-period term at
this altitude, `J2*(Re/a)^2*a`), and a round-trip through
`clMeanOscMap` with the sign flipped back (mean -> osc) recovers the
original osculating elements to ~1.8 m / ~8e-7 (e) / ~3e-7 rad (i) --
confirming both the math AND that this code calls `clMeanOscMap` with
the correct sign for "osc -> mean" (easy to get backwards, and nothing
else would have caught it). The gravity-setup wiring
(`central_body.radEquator` matching `orbitalMotion.REQ_EARTH*1000`
exactly) was also checked directly. Two new tests in
`tests/test_osculating_elements.py` encode these exact confirmed
numbers as regression tolerances (not guessed bounds). 24 tests in
`tests/gui/test_results_widget.py` cover the new per-category display
policy, including the two inverted-behavior regression guards (position
-in-meters, velocity-in-m/s) and new delta-V/altitude/mean-element
tests. Full suite: 674 passed, 101 skipped. NOT yet run end-to-end
through a full `SimulationService.run()` with live SPICE/network (this
sandbox's network policy denies `naif.jpl.nasa.gov`, the same
limitation noted throughout this project's history) -- the isolated
Basilisk-API-level verification above is real, but the full wiring
through an actual multi-sample run hasn't been watched end-to-end here.

## GUI "reactiveness": toasts, inline validation, and a real data-loss bug found along the way

Real user feedback: "make the GUI more 'reactive'... the user always
knows and understands what they did. visual cues would help... a better
display of settings, setups, parameters and values would help.
currently, everything looks very raw and unfinished." theme.py already
covers the app's visual CHROME (colors/borders/spacing -- an earlier
session's response to similar "looks unfinished" feedback), so this
request was really about something one level down: does the app
visibly react when you DO something?

A survey of the widget layer (spawned as a subagent to keep this out of
the main context, since it only needed to report back concrete
file:line findings, not make any changes) found the app already does
several of these right -- a window-title asterisk for unsaved changes,
a busy progress bar + disabled Run action + working Abort during a run,
QMessageBox.critical for every real error path -- but two patterns
repeated across most of the individual editor dialogs:

1. **No feedback on success**, only on failure. Add/remove/save a
   spacecraft (or sensor, or mission-sequence step) and the only signal
   anything happened is a list silently changing length -- no
   confirmation, no indication of WHICH item just changed.
2. **No live validation**, only a blocking dialog at Save/Run time that
   names the problem but not which of a dialog's many fields caused it.

Built two small, reusable primitives in a new `gui/feedback.py` (no new
dependency -- plain `QLabel`/Qt's own documented dynamic-property QSS
mechanism) rather than a one-off fix per dialog:

* `show_toast(window, message, kind=...)` -- a small, non-blocking,
  auto-dismissing notification anchored to a window's bottom-right
  corner, multiple stacking without overlapping. Not a guess at what
  "better feedback" should look like -- this exact gap was ALREADY
  documented in this app's own code: `MainWindow.on_launch_vizard`'s
  docstring admits a status-bar message is "easy to miss/get
  overwritten by the 'Running...' message that follows moments later"
  and had to be promoted to a one-time blocking dialog just to be
  noticed. A toast is the general-purpose version of that fix.
* `mark_invalid(widget, message)`/`clear_invalid(widget)` -- a red
  border (a new `[state="error"]` QSS rule in theme.py, using Qt's
  documented dynamic-property selector mechanism -- Qt only ships a
  fixed set of built-in pseudo-states like `:hover`/`:focus`, so a
  custom one like this is the officially sanctioned way to add another)
  plus the reason as a tooltip, live as the user types.

Wired into `main_window.py` (a toast on New/Open/Save/Run
complete/Run cancelled) and, as a complete worked example for the
inline-validation half, `spacecraft_editor.py`'s Name field (live,
per-keystroke empty/duplicate-name checking -- the dialog already knows
the other spacecraft names at construction time, no extra plumbing
needed) plus a toast on every Add/Edit/Remove, with the newly added/
edited row auto-selected in the list so it's obvious at a glance which
one just changed.

**A real bug found while wiring this in, not a hypothetical**:
`SpacecraftEditorDialog._on_accept()` called `self.accept()`
unconditionally -- an empty/duplicate name wasn't checked until AFTER
the dialog had already closed, in the caller
(`_on_add`/`_on_edit`/`_on_new_from_template`), which then showed a
`QMessageBox` and returned -- by which point the dialog (and every
other edit the user had just made in it) was already gone and silently
discarded. The exact same duplicate-name mistake this feature was
built to catch inline was ALSO capable of quietly destroying a user's
work. Fixed by checking the name (empty AND duplicate) inside
`_on_accept()` itself, before `accept()`, so the dialog only closes
once the name is actually valid -- the outer checks in
`_on_add`/`_on_edit`/`_on_new_from_template` are now unreachable in
practice but left in place as a harmless second guard.

**A real Qt lifetime bug found by the test suite, not guessed**: the
first version of `show_toast()`'s auto-dismiss timer called
`toast.deleteLater()`. Running the full `main_window` test suite
surfaced `RuntimeError: libshiboken: Internal C++ object (_Toast)
already deleted` on three tests -- a window can legitimately be closed
(destroying its child toast along with it, via Qt's normal parent-child
ownership) BEFORE that toast's own auto-dismiss timer fires, and the
timer's callback still tried to touch the now-dangling wrapper. Fixed
with `shiboken6.isValid()` (the documented way to check whether a
`QObject`'s underlying C++ object is still alive) guarding the dismiss
callback, and switched to `hide()` instead of `deleteLater()`
regardless (avoids a caller -- tests do this -- holding a dangling
reference to whatever `show_toast()` returned).

**Verification:** 13 new tests (`tests/gui/test_feedback.py`: toast
visibility/position/stacking/auto-dismiss/kind-coloring, inline mark/
clear; `tests/gui/test_spacecraft_editor.py`: live inline validation on
the Name field, the accept-blocks-and-keeps-the-dialog-open regression
guard for the data-loss bug above, toast-on-add/remove). Full suite:
687 passed, 101 skipped. All of this is Basilisk-free GUI-layer code,
run and confirmed headless (`QT_QPA_PLATFORM=offscreen`) in this
development sandbox exactly like every other GUI test in this project
-- nothing here needed a real display or a real user's machine to
verify.

## Rolling gui/feedback.py out to every other list-editor dialog

Explicit follow-up request: "roll it out to the other editor dialogs
too" -- the toast/inline-validation primitives above had only been
wired into `spacecraft_editor.py` as a worked example. Rolled out to
every other dialog with the same "Add/Edit/Remove a named/unnamed list
item" shape: `sensor_actuator_editor.py`
(`SensorActuatorListWidget`/`_ItemEditorDialog`), `ground_station_editor.py`
(`GroundStationListWidget`/`GroundStationEditorDialog`),
`mission_sequence_editor.py` (`MissionSequenceEditorWidget` -- no name
-uniqueness concept here, commands aren't named, so toasts only, no
inline validation), and `monte_carlo_editor.py`
(`DispersionListWidget` -- same reasoning, dispersions aren't named
either). Also added a completion toast to
`spacecraft_editor.py`'s two bulk-generate actions (Walker constellation,
phasing formation) that hadn't been covered in the first pass.

**The exact same data-loss bug found and fixed in
`SpacecraftEditorDialog` turned up, unchanged, in both other named-item
dialogs** -- not a coincidence: `sensor_actuator_editor.py`'s
`_ItemEditorDialog` and `ground_station_editor.py`'s
`GroundStationEditorDialog` were both written following
`SpacecraftEditorDialog`'s own shape (their docstrings say so
explicitly -- "mirrors ... SpacecraftListWidget's shape"), so the bug
(`_on_accept()` closing the dialog unconditionally, with the duplicate
-name check only happening afterward, in the now-unreachable-if-wrong
caller) had been copied right along with the pattern it came from.
Fixed identically in both: the dialog now takes the other items' names
at construction, validates the Name field live as the user types
(`textChanged` -> `mark_invalid`/`clear_invalid`), and `_on_accept()`
checks empty/duplicate BEFORE calling `accept()`, so the dialog only
closes once the name is actually valid. The outer checks in each list
widget's `_on_add`/`_on_edit` are now unreachable in practice but left
in place as a harmless second guard, matching the fix already applied
to `SpacecraftEditorDialog`.

**Verification:** every dialog's existing test suite still passes
unchanged (the new pre-check in `_on_accept()` is never exercised by
tests that monkeypatch `.exec()` directly to bypass it, exactly as
already noted for `SpacecraftEditorDialog`'s own tests) plus new tests
mirroring that same file's pattern: live inline-error-on-duplicate,
accept-blocks-and-keeps-the-dialog-open, and toast-shown-on-add/edit/
remove, for each rolled-out widget. Full suite: 695 passed, 101
skipped, including the one `requires_basilisk`-marked phasing-formation
toast test, re-run directly against this sandbox's real Basilisk build
(`/tmp/bsk_venv4`) rather than left unverified.

## "Propagation setup" summary: from three pipe-joined lines to a labeled form

Real user feedback, with a screenshot: the "Propagation setup" group's
read-only summary (`ScenarioEditorWidget._refresh_propagation_summary`)
rendered as three unlabeled, ``" | "``-joined lines in a single QLabel
(``"earth | spherical harmonics (degree 10) | +sun, moon"``, etc.) --
"looks incredibly unfinished, raw and unprofessional and very cluttered
and doesnt help the user understanding what those values stand for".
Checked directly: correct complaint -- this was the ONE settings
summary in the whole app built as free text instead of the labeled
field-name/value rows every other panel already uses
(`spacecraft_editor.py`, `ground_station_editor.py`, and
`PropagationSetupDialog` ITSELF, the exact dialog this summary is
summarizing).

**Fixed** by replacing the single `QLabel` with a `QFormLayout` of
label/value rows, rebuilt on every refresh (row count varies -- the
third-body-perturbers and space-weather rows only appear when
relevant). Every row label is copied VERBATIM from
`PropagationSetupDialog`'s own `form.addRow(...)` calls ("Central
body", "Integrator", "Dynamics task rate [s]", "Duration [days]",
"Atmosphere model", ...) -- the summary and the dialog that edits it
now use identical terminology instead of two different ways of saying
the same thing.

**Verification:** rendered the actual widget headless
(`QT_QPA_PLATFORM=offscreen`, `QGroupBox.grab()` to a PNG) and looked
at it directly rather than trusting the code -- confirmed it now reads
as a clean label/value table instead of the cluttered original. Two
existing tests that asserted against the old single-label `.text()`
were updated (a small `_propagation_summary_text()` test helper
flattens the new form's rows back into one string so the same substring
assertions still work), plus one new test asserting every expected row
label is actually present. Full suite: 696 passed, 101 skipped.

## A visual sweep for "raw panels" elsewhere in the app, and one real bug found by it

Follow-up request: "check the rest of the app for similar raw panels".
Grepped for the same free-text-summary shape across every `gui/*.py`
file, and found nothing else built that way -- the Propagation setup
summary really was the one outlier; every other panel
(`kernel_status_widget.py`'s table, `monte_carlo_editor.py`'s own
`QFormLayout`, every editor dialog) already uses labeled rows.
`mission_output_widget.py`'s plain-text report log was deliberately
left alone -- it's documented as a "debug console" for arbitrary,
variable-shaped report data (series names/array values the user
defines via `report` commands), where a monospace log is the
appropriate format, not a settings dump with a fixed field set.

Grepping isn't the same as looking, so every major screen was also
actually RENDERED headless (`QT_QPA_PLATFORM=offscreen`,
`QWidget.grab()` to a PNG) and inspected as an image, not just read as
code: the full Scenario Editor tab, all 4 tabs of
`SpacecraftEditorDialog`, the main window overview, `VizardDialog`,
`GroundStationEditorDialog`, and `PropagationSetupDialog` itself (not
just its scenario-editor summary). That caught a real bug the grep
alone would have missed entirely: `PropagationSetupDialog`'s
"Atmosphere & drag" `QGroupBox` title rendered as the visibly broken
"Atmosphere _drag" in the actual screenshot -- Qt treats a lone `&` in
a group box title as a mnemonic marker (the same mechanism behind
`"&File"`/`"&Save"` menu shortcuts elsewhere in this app, which are all
correct, intentional uses -- this was the one place a literal `&` was
meant as prose, not a mnemonic). Fixed with `"&&"`, Qt's own documented
escape for a literal ampersand -- confirmed by re-rendering and looking
at the PNG again, not just trusting the source change.

**Verification:** one new regression test
(`test_propagation_setup_dialog.py`) asserts the group's stored title
is the escaped `"Atmosphere && drag"` form, not the single-`&` one --
`QGroupBox.title()` returns Qt's raw stored string, not the rendered/
mnemonic-resolved text, confirmed directly (the first version of this
test asserted the wrong thing and failed against the real widget,
caught before it was ever committed). Full suite: 697 passed, 101
skipped.

## A real user screenshot: "Generate phasing formation" rendered almost entirely off-screen

A real user sent a screenshot of the "Generate phasing formation"
dialog that looked badly broken: every row's own label was missing --
only thin fragments of text were visible hugging the LEFT edge of the
screen ("t holds a target along-track separation from an existing
chief spacecraft...", "pied from here)"), with each input field
stretched to fill the entire visible width.

**Root-caused directly from the fragments themselves**, not guessed:
those fragments are the TAIL ENDS of longer strings -- the visible
"...pied from here)" is the end of the row label "Template spacecraft
(everything else copied from here)", and the long visible sentence
fragment is the middle of this dialog's own top description paragraph.
That only makes sense if the dialog's true left edge sits far off the
left of the screen (a large NEGATIVE x position) -- which happens when
a window manager centers a dialog that's far wider than the screen
(`center_x = (screen_width - dialog_width) / 2`, strongly negative once
`dialog_width` is in the thousands of pixels). Checked
`phasing_formation_dialog.py` directly: its top description `QLabel`
(a full paragraph, matching the visible fragment exactly) had no
`setWordWrap(True)` call -- without it, Qt sizes a `QLabel` to fit its
ENTIRE text on one line, and everything else in the dialog's
`QVBoxLayout` is forced just as wide. Confirmed the mechanism by
actually reproducing it: rendering the dialog at its natural size
(`.show()`, no forced resize -- the earlier "raw panels" sweep's own
blind spot, since every dialog checked there WAS explicitly resized in
the test script, accidentally masking exactly this bug) showed the
same oversized layout.

**The same copy-pasted shape (a `QVBoxLayout` starting with an
unwrapped top description `QLabel`) turned up, with the identical bug,
in four more places** once checked systematically:
`constellation_dialog.py` (`WalkerConstellationDialog`, the sibling
dialog `phasing_formation_dialog.py`'s own docstring says it mirrors),
`vizard_dialog.py`, `spacecraft_template_dialog.py`'s static banner
label, and `spacecraft_editor.py`'s Vizard-model tab description. Fixed
identically in all five: assign the `QLabel` to a variable,
`.setWordWrap(True)`, then add it to the layout -- matching the
word-wrap pattern this codebase already uses correctly elsewhere (e.g.
`sensor_actuator_editor.py`'s hint label,
`propagation_setup_dialog.py`'s own top label, which rendered correctly
in the earlier sweep specifically BECAUSE it already had this call).

**Verification:** re-rendered both `PhasingFormationDialog` and
`WalkerConstellationDialog` at natural size (no forced resize) and
looked at the resulting PNGs -- both now render at a sane size (569x682
and 743x531) with every label fully visible. Five new regression tests
(one per fixed dialog) assert the long description label's
`wordWrap()` is `True`, plus a loose upper bound on the dialog's
`sizeHint().width()` for the two dialogs most likely to regress
visibly. Full suite: 702 passed, 101 skipped.

## Two more real UX bugs, found by continuing the same check

Follow-up request: "check the rest of the app for other UX issues".
Two genuine bugs found, neither a guess:

**Monte Carlo dispersion dialog showed all three value fields at
once, regardless of Kind.** `_DispersionEditorDialog` always displayed
Bounds AND Mean AND Std-deviation, editable, no matter which "Kind"
(uniform/normal/uniform_euler_mrp) was selected -- but
`to_dataclass()` only ever uses the pair matching the current kind,
silently discarding the rest. A user could type a Mean/Std-deviation
value while Kind="uniform" and have it vanish with zero indication
anything was ignored. Fixed by hiding whichever row(s) don't apply to
the selected kind (`_on_kind_changed`, wired to `kind_combo`'s own
signal), so the dialog only shows what will actually be used.

**`PropagationSetupDialog`'s "Atmosphere & drag" description text was
silently cut off mid-sentence**, ending at "...open a" with the rest
of the paragraph missing -- found by rendering the dialog and looking
at the PNG (again), not by reading the source, where the text is
complete. Root-caused precisely by comparing the label's actual
`geometry().height()` (27px) against its own `heightForWidth(520)`
(68px): `QFormLayout.addRow(single_spanning_widget)` did not reserve
this label its full wrapped height, unlike this dialog's OWN top-level
`intro_label` (added via plain `QVBoxLayout.addWidget()`, which has
never had this problem). Fixed by restructuring the group to use a
`QVBoxLayout` for the description label plus a nested `QFormLayout`
for the actual fields, mirroring the already-proven-correct pattern.
Fixing that alone uncovered a SECOND, related bug: the dialog's window
never grew to match its new (taller) `sizeHint()` on first `show()`
(measured directly: window stayed 871x734 while `sizeHint()` said
871x768), clipping the group's own last two rows against its border.
Fixed with an explicit `self.resize(self.sizeHint())` at the end of
`__init__`, after every group is built.

Searched for the same `form.addRow(wrapped_label)` shape (the root
cause of the second bug) everywhere else in `gui/`; one more instance
turned up (`mission_sequence_editor.py`'s "assignment" command page),
but direct measurement showed it was NOT actually clipped (no
`setMaximumWidth` cap and no extra `QGroupBox` nesting meant it
happened to converge correctly on the first layout pass) -- left alone
rather than "fixed" on spec, since it isn't broken.

**Verification, more rigorous than the pattern-matching used to find
the bugs**: wrote a script that renders every dialog in the app (every
`_CommandEditorDialog`/`_ItemEditorDialog`/`_DispersionEditorDialog`
"kind" selection included -- 25 total dialog/state combinations) and
directly compares every word-wrapped `QLabel`'s allocated
`geometry().height()` against its own `heightForWidth()`, rather than
trusting that fixing the two found instances covered everything.
Confirmed clean everywhere, including cycling through every tab of
`SpacecraftEditorDialog` (`QTabWidget` defers layout for hidden tabs,
so checking only the initially-visible one could have missed a real
bug on another tab). Two new regression tests
(`test_dispersion_dialog_hides_fields_not_used_by_the_selected_kind`,
`test_srp_pointer_label_gets_its_full_wrapped_height_not_clipped`)
plus one for the resize fix
(`test_dialog_resizes_to_its_own_sizehint_on_construction`). Full
suite: 705 passed, 101 skipped.

## Results and Mission Output tabs: a searchable series picker, and a real missing export button

Follow-up request: "check for more UX issues in the results and
mission output tabs".

**Results tab's "Series:" picker had no way to search.** A real
scenario (the built-in 6-satellite Walker constellation template, for
one) produces 30-40+ series, all named after the dotted scheme
`engine.service`/`engine.link_budget` use
(`leo-02-03.orbit_elements_mean.inclination`, ...) -- confirmed
directly by building a synthetic multi-spacecraft `ResultSet` and
listing what the combo box actually shows. Scrolling a flat, plain
`QComboBox` that long to find one series is tedious, and the useful
discriminator (spacecraft name, or the category after the first dot)
is usually in the MIDDLE of the name, not the start. Made the combo
editable with a substring-matching (`MatchContains`, not the default
prefix-only `MatchStartsWith`), case-insensitive `QCompleter` bound to
the combo's own model -- confirmed the completer stays correctly in
sync after `set_result()` clears and rebuilds the combo (same model
object throughout, not a stale one), rather than assuming Qt's
`QComboBox.clear()`/`addItem()` mutate the model in place.

**Mission Output tab had no CSV export at all.** Checked
`engine/results.py` directly: `CommandSummary.export_csv()` already
existed, fully implemented and already covered by its own tests at the
engine layer -- but nothing in `mission_output_widget.py` ever called
it. The neighboring Results tab has had an "Export all series to
CSV..." button since the Plotly migration; a user running a
`mission_sequence` with `report` commands had no equivalent way to get
that data out except manually selecting/copying the plain-text debug
log. Added an "Export to CSV..." button mirroring
`ResultsWidget._on_export()`'s exact pattern (a single
`QFileDialog.getSaveFileName`, not `getExistingDirectory` --
`CommandSummary.export_csv()` writes ONE file, unlike
`ResultSet.export_csv()`'s one-file-per-series), disabled until a
summary with at least one report exists (a summary with zero `report`
commands has nothing meaningful to export).

**Verification:** 2 new tests confirm the completer's filter mode/case
-sensitivity and that it survives a `set_result()` rebuild pointing at
the same model object; 4 new tests cover the export button's enabled
-state transitions (no summary / a summary with zero reports / a
summary with reports / after `clear()`) and a genuine round-trip
(writes a real temp-dir CSV, confirms the expected series name appears
in its content). Both tabs re-rendered headless and looked at directly
-- the Results tab's actual Plotly canvas can't be screenshotted in
this sandbox (`QWebEngineView` doesn't rasterize under this sandbox's
software-only GL fallback, a pre-existing, already-documented
limitation -- verified via JS introspection instead, per this file's
own module docstring), but the picker/toolbar row above it, and the
entire Mission Output tab, render and were inspected as images. Full
suite: 710 passed, 101 skipped.

## Kernel Status tab: a table whose own header didn't fit, and an error message that made it worse

Follow-up request: "check the rest of the app for other UX issues".
First checked every other dialog with a "kind"/"pattern" selector for
the same shown-regardless-of-relevance bug class the Monte Carlo
dispersion dialog had -- none found (constellation/phasing-formation
dialogs use every field unconditionally; `spacecraft_editor.py`'s
optional sections are all CHECKABLE `QGroupBox`es, which already
auto-disable their own contents when unchecked, the correct pattern).
Then rendered the tabs/widgets not yet looked at directly: Load
Scenario (clean), and the Kernel Status tab, which had a real, two
-layer bug.

**The table's own column headers didn't fit.** `KernelStatusWidget`'s
4-column table used a blanket `QHeaderView.ResizeMode.Stretch` on every
column -- found by actually populating the table and looking at it:
"Cache last modified (UTC)" (by far the longest header) rendered
truncated on BOTH ends ("ache last modified (UTC"), while "Kernel" sat
in a column much wider than its content needed, since Stretch forces
every column to the exact same width regardless of what's in it. Fixed
by stretching only "Path" (the one column whose content -- real
filesystem paths -- genuinely benefits from claiming the remaining
space) and sizing the other three to their own content
(`ResizeToContents`).

**Fixing that uncovered a second problem**: the "Available" column
embedded the full error message inline (`f"NO: {status.error}"`), so
once its own sizing was fixed to `ResizeToContents`, a single long
error message (e.g. "download failed: connection refused") now forced
THAT column wide instead -- stealing width right back from "Path", the
more important column to keep readable. Fixed by showing just "NO" in
the cell and moving the full error to the item's tooltip (the same
"short status at a glance, detail on demand" pattern `gui.feedback`'s
inline-validation already uses). Added the same tooltip to the "Path"
cell itself while at it: `Stretch`-mode columns can't be interactively
widened by the user the way `Interactive`-mode ones can, so a
genuinely long real path can still end up visually truncated with no
way to fix it except hovering.

**Verification:** rendered the table both empty and populated (with
synthetic `KernelStatus`-shaped data -- duck-typed via
`SimpleNamespace`, since the real dataclass needs a Basilisk import
this sandbox doesn't have) and looked at the PNGs before and after each
fix. 3 new tests: every column's actual `sectionResizeMode()` matches
the intended per-column policy (not just "some column somewhere
stretches"), the unavailable-kernel row's cell text is exactly "NO"
with the real error as its tooltip, and the path cell's tooltip holds
the untruncated path. Full suite: 713 passed, 101 skipped.

## A missing Monte Carlo toast, and a version nowhere in a versioned, packaged app

Follow-up request: "check the rest of the app for other UX issues".
Checked whether Basilisk's own `MonteCarlo.Controller` exposes any
real per-run progress hook, since an earlier survey flagged Monte Carlo
runs as having no progress reporting -- confirmed directly from
Basilisk's own source (`src/utilities/MonteCarlo/Controller.py`,
`src/utilities/simulationProgessBar.py`): its only "progress" is a
`tqdm` terminal bar with no programmatic callback at all, and
`main_window.py`'s own code already documents this exact limitation
honestly (the indeterminate busy bar IS the correct, deliberate choice
here -- not a bug to fix, and not something to fake a fraction for).

Two real, smaller gaps found instead:

* **`_on_monte_carlo_finished`'s all-succeeded branch had no toast**,
  unlike its single-run sibling `_on_run_finished` (added a few rounds
  ago in this same audit). The partial-failure branch already shows a
  `QMessageBox.warning` -- strong enough feedback on its own, same
  reasoning as `_on_run_failed` having no toast alongside its own
  `QMessageBox.critical` -- so only the silent all-succeeded case
  needed one.
* **No way to check the app's own version from inside the app.**
  `missionstudio.__version__` ("1.0.0") already existed, but nothing in
  the GUI ever surfaced it -- no Help menu, no About dialog, no version
  string anywhere, despite this being a packaged desktop app shipping
  `.deb`/Windows installers. A user filing a bug report had no way to
  even state which version they were running without checking
  `pyproject.toml` by hand. Added a `&Help` menu with an "About
  missionStudio" action showing the version plus whether Basilisk is
  actually available in this install (the same
  `importlib.util.find_spec("Basilisk")` check this project's own test
  suite already uses to gate `requires_basilisk` tests).

**Verification:** rendered the menu bar and confirmed "Help" appears
correctly. 3 new tests: the all-succeeded Monte Carlo toast fires and
mentions "Monte Carlo complete", the partial-failure branch does NOT
also show one, and the About dialog's shown text contains both the
real `missionstudio.__version__` string and the word "Basilisk". Full
suite: 716 passed, 101 skipped.

## App icon: from an accidental eye to a satellite, after it was shown to the user first

Explicit request: "create an app icon for the app". One already
existed (a procedurally-drawn `QPainter` icon from an earlier Phase 5
round -- a dark central body inside a thin, inclined orbit ellipse
with a small dot on the ring) -- rather than silently building a
second, competing icon, it was rendered at several sizes and shown to
the user first, who confirmed: keep the concept, but "refine it to
read clearer at small sizes".

**Diagnosed why, rather than guessing at a fix**: at 16-32px (the
sizes this icon is actually seen at most -- window titlebar, taskbar)
it read as a cartoon eye, not an orbit. Tried several parameter-tuning
passes on the SAME structure first (thicker ring stroke, a bigger/
brighter satellite dot) and rendered each one -- they made it read MORE
eye-like, not less (a bigger, lighter dot became an eye's catchlight).
The real problem was structural: "a filled disc centered inside a
surrounding ring" is close to the universal flat-icon glyph for an eye
(pupil + iris) regardless of stroke width or color, so no amount of
tuning on that same silhouette was ever going to fix it.

**Redesigned around a different silhouette instead**: a satellite
glyph (an angular body between two solar-panel wings, plus a thin
antenna at larger sizes) -- confirmed by rendering it at every size
from 256px down to 16px that it stays legible and reads clearly as
spacecraft hardware, with no closed ring-around-a-disc shape left to
be mistaken for an eye. Also a better thematic fit for a
*mission-analysis* tool generally than one specific orbit-and-dot.

**A second real bug found along the way**: rendering the new design
against both a light AND a dark background (not assumed -- many
desktop taskbars are dark) showed the body's original near-black color
nearly disappearing against a dark background. Fixed by making the
body gold instead -- not arbitrary: real satellites commonly use
gold-foil thermal-blanket bodies, so gold-body-next-to-blue-panels is
representationally accurate, not just decorative, and it happens to
have good contrast against both light and dark surfaces.

Fine detail (the antenna; grid lines on the panels/body) is omitted
below its own legibility threshold (found by rendering both and
comparing, same as everything else here) rather than drawn at a
thickness that just anti-aliases into noise at small sizes.

**Verification:** every candidate was rendered and actually looked at
-- individually, side by side across sizes, and against both light and
dark backgrounds -- at every stage of this redesign, not just the
final result. 2 new regression tests: the large-size render includes
the specific gold body color (pinning the part of this redesign a
generic color-count check wouldn't catch regressing), and a 16px
render has meaningfully fewer distinct colors than a 256px one
(confirming the size-gated detail thresholds actually take effect).
Full suite: 718 passed, 101 skipped.

## Taskbar always shows a generic cog icon, never the app icon

**Real user report**, asked right after the icon redesign above: "when
launching the GUI, in the task bar it always shows a cog symbol, why?"
-- not a rendering bug in the icon itself (that was already verified
extensively, see above), so the investigation went into how Linux
desktop shells actually source a running window's taskbar/dock icon.

**Root cause, confirmed by reading how `app.py` launches the window and
comparing it against the packaging/ `.desktop` entries**: most Linux
desktop shells (GNOME Shell, KDE Plasma, and Wayland compositors
generally) do not take a running window's icon from the `QIcon` passed
to Qt's `setWindowIcon()` at all. They match the window to an
*installed* `.desktop` entry -- by "desktop file name" / app-id on
Wayland, or by `WM_CLASS` against that entry's `StartupWMClass=` on
X11 -- and use THAT entry's `Icon=` key. `app.py`'s `main()` never
called `QApplication.setDesktopFileName()`, and neither
`packaging/missionstudio.desktop.in` nor `packaging/deb/.../missionstudio.desktop`
set `StartupWMClass`, so neither matching path could succeed. With no
match, the shell falls back to its own generic "unknown application"
icon, which in Adwaita/Breeze/Yaru-derived icon themes is exactly the
gear/cog glyph reported.

**Fix:** `app.py` now calls `app.setDesktopFileName("missionstudio")`
right after `setApplicationName`/`setOrganizationName`, and both
`.desktop` files gained `StartupWMClass=missionstudio` -- all three
spellings of this identifier now agree with each other and with the
`.desktop` files' own installed basename (`missionstudio.desktop`).
Documented inline in `app.py` that this alone is not sufficient for a
from-source run (`python3 -m missionstudio.gui.app`, or `missionstudio
gui` from a dev checkout): the match still needs a real
`missionstudio.desktop` entry present somewhere in `XDG_DATA_DIRS`,
which currently only `packaging/install.sh` (or the `.deb`) installs,
together with the rendered icon PNG under the `hicolor` icon theme --
so a plain source checkout will keep showing the generic icon
regardless, independent of this fix.

**Verification:** 3 new regression tests in `tests/gui/test_app.py`
(new file): `main()`'s source actually contains the
`setDesktopFileName("missionstudio")` call, both `.desktop` files
actually declare `StartupWMClass=missionstudio`, and the identifier
passed to `setDesktopFileName()` matches the `.desktop` files' own
installed basename (so the three spellings can't silently drift apart
again). Full suite: 722 passed, 101 skipped.

## Basilisk feature audit, and a backlog to close the gaps

**Real user question**: "What other features does basilisk have, that
were not yet integrated in the app?" A background agent inventoried
every capability module under `src/simulation/` and `src/fswAlgorithms/`
in this checkout and the answer, compared directly against what
`engine/service.py`/`engine/fsw.py` actually import, was sobering: this
app wires up 4 of ~8 sensor kinds, 1 of several actuator types, 5 of
~18 attitude-guidance modes, 1 control law, and none of attitude
determination/thermal/onboard-data-handling/communication/optical-nav/
small-body-nav/formation-flying-FSW at all -- sensors feed FSW modules
*truth* directly (`simpleNav`) rather than a real estimated state, and
every maneuver uses an idealized `extForceTorque` rather than a real
thruster. The user's follow-up, verbatim: "Yes please, all of them. But
make them useful end to end, meaning easy setup for user, useful
simulation run and visualization and helpful outputs and results." --
a real multi-week backlog, tracked as 19 prioritized tasks (schema +
engine + GUI + tests + docs per item, not a checkbox), starting with
the highest-value/most-tractable first.

**A significant, re-discovered sandbox constraint**: attempting to
verify the first item (gravity gradient torque, below) against the
real Basilisk build at `/tmp/bsk_venv4` failed -- not from a bug in the
new code, but because `engine.service.SimulationService.build()`
unconditionally needs SPICE kernels (`build_spice_interface()`), and
this sandbox's network egress to `naif.jpl.nasa.gov` and its
`hanspeterschaub.info` backup mirror is blocked by the outbound proxy
policy (confirmed with the proxy's own `recentRelayFailures` log:
`connect_rejected ... gateway answered 403`). Confirmed this is NOT new
or specific to this change by re-running an EXISTING, previously
-documented-as-passing test (`test_service_run_live.py`) here: it fails
with the identical blocked-kernel error. This is, in fact, already
`engine/kernels.py`'s own documented verification status ("the actual
KERNEL DOWNLOAD could not be completed in that same environment") --
not a new discovery, just re-confirmed here because it materially
changes what "verified end-to-end" can mean for the rest of this
backlog: every dynamics-level feature from here on can be verified at
the *API* level (real class/attribute names, confirmed against the
actual compiled Basilisk module and its own shipped unit test's exact
call sequence -- the same "never fabricate a Basilisk API" discipline
`engine/fsw.py` was already built under, before this sandbox had a
Basilisk build at all) but not at the *executed-dynamics* level, in
this sandbox, until kernel network access is available.

### Gravity gradient torque (task 1 of 19)

The first, quickest-to-land item: real torque from the central body's
gravity acting across a spacecraft's own (non-spherical) inertia,
currently missing entirely -- a real, physically meaningful disturbance
for anything coasting without active attitude control, or with a
notably non-uniform inertia tensor. Added
`SpacecraftConfig.enable_gravity_gradient` (default `False`, so every
existing scenario's dynamics are bit-for-bit unchanged), wired to
Basilisk's `GravityGradientEffector` in `engine/service.py` right
alongside the existing drag/SRP effector blocks: `addPlanetName()` on
the central body only (a third-body perturber's gravity-gradient
contribution is smaller by roughly the cube of the distance ratio --
negligible at any real mission distance, so skipped rather than adding
an import per perturber for no measurable effect), then
`addDynamicEffector()` -- it reads the spacecraft's own already
-registered inertia/position/attitude directly, no extra message
wiring needed. Added a matching checkbox next to the existing drag/SRP
toggles in the spacecraft editor's "Orbit / mass" tab (rendered
headless and inspected to confirm placement/round-trip, same discipline
as every other GUI change this project ships).

**Verification:** `GravityGradientEffector`'s constructor,
`addPlanetName()`, and `addDynamicEffector()` call sequence confirmed
directly against this checkout's own
`GravityGradientEffector/_UnitTest/test_gravityGradient.py`, and its
class/method names additionally confirmed to exist on a real built
Basilisk module (`/tmp/bsk_venv4`), not just read from source. Two new
`requires_basilisk` regression tests
(`tests/test_gravity_gradient.py`) are written to actually run the
physics -- an elongated-inertia, uncontrolled (`fsw_mode=None`)
spacecraft's attitude must stay frozen with the flag off and visibly
drift with it on -- but could not be EXECUTED here for the SPICE-kernel
reason above; they will run given kernel network access (a real dev
machine, or CI). GUI checkbox round-trip and rendering confirmed
headless. Full Basilisk-independent suite: 722 passed, 103 skipped (101
-> 103: the two new SPICE-gated tests join the existing
`requires_basilisk` skip bucket in this sandbox, same as every other
test in it).

### Real thruster actuator (task 2 of 19)

`"thruster"` was schema-valid since Phase 2 but `engine.service` hard
-rejected it at run time -- every maneuver/station-keeping/phasing burn
used an idealized `extForceTorque`/direct-mass-bookkeeping model, and a
spacecraft could not use real thruster hardware for attitude control at
all (only reaction wheels). Wired up the real chain from
`examples/scenarioAttitudeFeedback2T_TH.py`: `mrpFeedback` ->
`thrForceMapping` (torque -> per-thruster force) -> `thrFiringSchmitt`
(Schmitt-trigger on-time logic) -> `thrusterDynamicEffector`, with
thrusters built via `simIncludeThruster.thrusterFactory()` (new
`ActuatorConfig.params` keys: `r_B` [m], `tHat_B` [-], `MaxThrust` [N]
required; `thruster_type`, `steadyIsp`, `MinOnTime` optional). A
spacecraft may use `"reaction_wheel"` actuators or `"thruster"`
actuators, not both -- mixing them would need a control-allocation
module (Basilisk's `torqueScheduler`) this app doesn't build, so
`SpacecraftConfig.validate()` now rejects the mix early with a specific
message rather than engine.service silently using only one.

**A real, unrelated bug found and fixed along the way**: the sensor/
actuator editor's vector-param UI (`_ParamSpec`) gave EVERY 3-element
list-valued param -- direction or not -- a "Normalize" button. That's
correct for a direction (`nHat_B`, `gsHat_B`, and now `tHat_B`), but
`r_B` is a thruster's body-frame LOCATION in meters: clicking Normalize
on it would silently rescale a real thruster's mounting point to
exactly 1 meter from the body origin, corrupting the actual geometry.
Magnetometer's `noise_std_tesla` (a per-axis noise std-dev, also not a
direction) turned out to have the exact same latent bug already. Fixed
with a new `_ParamSpec.normalizable` flag (default `True`, so every
existing direction-valued spec is unaffected), set `False` for both
`r_B` and `noise_std_tesla`, and the Normalize button is now only
built when `normalizable` is set.

**Visualization**: `engine.vizard.enable_vizard()` gained
`thr_effectors_by_spacecraft`, so Vizard now draws native thruster
plume effects when a spacecraft's thrusters fire -- this was previously
explicitly documented as "not passed: nothing to visualize" in that
module's own docstring, now genuinely true. `SimulationService.run()`
also reports a new `{name}.thruster_on_time` result series (per
-thruster commanded on-time, seconds) alongside the existing
`{name}.rw_speeds`, with its own plot category ("Thruster On-Times") in
the results viewer.

**Verification**: unlike gravity gradient torque above, this one really
could be run end-to-end in this sandbox -- attitude-only dynamics (no
orbit, no gravity, no SPICE) don't hit the blocked-kernel restriction
at all, so a standalone script driving `engine.fsw`'s new builder
functions directly against a bare `SimulationBaseClass` was written,
run for real against `/tmp/bsk_venv4`'s Basilisk build, and genuinely
worked: an 8-thruster cluster controlling a spacecraft with initial
attitude error `[0.3, 0.2, -0.1]` (MRP) drove it down to
`[0.054, 0.049, -0.007]` in 60 simulated seconds, with real nonzero
per-thruster on-times throughout. Turned into two real, ACTUALLY
-PASSING `requires_basilisk` tests
(`tests/test_thruster_control.py::test_thruster_chain_commands_nonzero_on_times`/
`::test_thruster_chain_reduces_attitude_error`) -- confirmed by running
them through pytest against that same build, not just the standalone
script. Plus 5 new schema-validation tests (required `r_B`/`tHat_B`/
`MaxThrust`, valid-thruster-validates, reaction_wheel+thruster-mix
-rejected) and 2 new GUI tests (thruster kind no longer shows the
"not simulated yet" warning; `r_B`'s vector row has no Normalize button
while `tHat_B`'s keeps one) -- all real, all passing. Full
Basilisk-independent suite: 729 passed, 105 skipped.

### Reaction wheel momentum desaturation (task 3 of 19)

Reaction wheels had no way to shed accumulated momentum at all -- a long
-enough scenario would simply saturate them with no recourse, silently
losing attitude control once that happened. Wired up Basilisk's real
desaturation chain (`thrMomentumManagement` -> `thrForceMapping`,
reused in "momentum-dump mode" via `angErrThresh` set above pi -- the
module's own documented way to make it output an impulse instead of a
torque -- -> `thrMomentumDumping`), firing a spacecraft's `"thruster"`
actuators to bleed off reaction-wheel momentum while those SAME wheels
stay in control of attitude the whole time -- a genuinely different job
from task 2's thruster-as-primary-control path, built as a separate
signal path (`engine.fsw.build_momentum_dumping`) that is never built
for the same spacecraft as `build_thruster_force_mapping`.

New `SpacecraftConfig.momentum_dumping` (`MomentumDumpingConfig`:
`hs_max` [N*m*s] trigger threshold, firing-resolution/cooldown knobs).
Mixing `"reaction_wheel"` and `"thruster"` actuators on one spacecraft
-- previously flatly rejected by task 2's own validation -- is now
allowed in EXACTLY this one case (`SpacecraftConfig.validate()` requires
`momentum_dumping` to be set whenever both kinds are present, and still
rejects the mix otherwise, since mixing them for primary control would
need a control-allocation module this app doesn't build).

**A real, non-obvious Basilisk requirement found by direct
experimentation, not just reading the example's comment**: tried running
`thrMomentumManagement` both with and against a real Basilisk build
(`/tmp/bsk_venv4`) and found that calling its `Reset()` only at t=0 (all
`InitializeSimulation()` itself ever does) means desaturation NEVER
fires for the entire run -- no error, no warning, just silently nothing
-- because `rwSpeedsInMsg` has no real data yet at that exact moment.
Calling `Reset()` again after even ONE real dynamics tick fixes it
completely, and the exact amount of extra time barely matters (confirmed
both 1 s and 10 s delays work identically). `engine.service.SimulationService
.build()` now does this automatically -- primes one dynamics tick,
re-`Reset()`s every desaturation module, then continues to the
scenario's real configured duration via the same documented
"`ConfigureStopTime`/`ExecuteSimulation` resumes, never restarts"
pattern `run_live()` already relied on -- so no scenario author needs to
know this quirk exists.

Added a GUI "Momentum dumping (RW desaturation via thrusters)" group
(threshold + firing-resolution + cooldown fields) next to the spacecraft
editor's other optional propulsion configs.

**Verification**: like task 2, this feature's dynamics (no orbit
propagation needed, just attitude + reaction wheels + thrusters) don't
touch gravity or SPICE at all, so it was run for real against the real
Basilisk build -- confirmed, with the EXACT Reset-timing experiment
above, that a 4-wheel cluster starting pre-saturated (same real
configuration as `examples/scenarioMomentumDumping.py`) genuinely sheds
momentum (initial wheel-speed vector `[418.9, 209.4, 366.5, 0.0]` rad/s
down to `[335.7, 99.0, 296.1, -43.3]` rad/s over 300 s, 3 real
desaturation firings) when primed, and provably does nothing at all when
not. Two new `requires_basilisk` tests in `tests/test_momentum_dumping.py`
ACTUALLY PASS against that build (both the "it works when primed" case
and a pinned regression test for the "does nothing without priming"
case, so a future refactor that accidentally drops the priming step
fails loudly instead of silently). Plus 5 new schema-validation tests
and 3 new GUI round-trip tests, all passing.

### Comprehensive, runnable template scenarios for every new feature

**Real user request**, made explicit after task 2 landed: "for each one
[feature on the 19-item backlog], please create a comprehensive
template/example scenario that can be loaded and ran out of the box."
Added to `scripts/_generate_templates.py` (the existing templates
catalog's own generator -- schema dataclasses + `Scenario.validate()`,
never hand-written JSON, per that script's own docstring) and
regenerated the whole catalog (templates 01-09 picked up two new,
purely-additive fields with their defaults -- `enable_gravity_gradient:
false`, `momentum_dumping: null` -- confirmed via diff that nothing else
in any of them changed):

- **`10_gravity_gradient_torque.json`**: an uncontrolled, elongated
  -inertia spacecraft with `enable_gravity_gradient` set -- its own
  description explains why a spherically-symmetric inertia would make
  the effect disappear entirely, and suggests that exact experiment.
- **`11_thruster_attitude_control.json`**: the thruster counterpart to
  '06'/'07' -- the same `inertial3D` pointing problem, actuated by eight
  real ACS thrusters instead of reaction wheels, using the EXACT
  configuration already confirmed to work in
  `tests/test_thruster_control.py`.
- **`12_reaction_wheel_momentum_dumping.json`**: four pre-saturated
  reaction wheels plus an 8-thruster desaturation cluster, using the
  EXACT configuration already confirmed to work in
  `tests/test_momentum_dumping.py`.

Every new template got the same treatment every existing one already
has: a 200+ character `description` explaining the concept, what to
look at in the results, and what to try changing; a specific regression
test pinning its defining characteristic (`fsw_mode is None` + elongated
inertia for '10', thruster-only actuators for '11', the required
actuator mix for '12'); and a catalog row in both this directory's own
`README.md` and the top-level `README.md`. The GUI's Load Scenario tab
needed no code change at all to pick them up -- it already globs
`scenarios/templates/*.json` dynamically (`gui/load_scenario_widget.py`),
confirmed by rendering it headless and counting 12 listed templates.

**Verification status**: schema-validated and round-trip tested (same
generic parametrized tests every template goes through), and built from
actuator/sensor configurations already confirmed to run correctly
against real Basilisk in isolation (the exact `r_B`/`tHat_B`/`MaxThrust`/
`gsHat_B`/`Omega` values from the passing `test_thruster_control.py`/
`test_momentum_dumping.py` tests above) -- but NOT executed end-to-end
through `SimulationService` in this sandbox: every scenario-level run
needs SPICE kernels (`engine.service.SimulationService.build()` calls
`build_spice_interface()` unconditionally), and this sandbox's network
egress to fetch them is blocked (see task 1's entry above and
`engine/kernels.py`'s own docstring) -- the same pre-existing limitation
already true for all nine original templates, not something new to
these three. Full suite: 755 passed, 107 skipped.

### Magnetic torque rod actuator (task 4 of 19)

The last remaining schema-valid-but-unwired actuator kind. Unlike the
thruster-based desaturation in task 3, this uses a materially different
Basilisk strategy -- `mtbMomentumManagement` -- which continuously
biases each reaction wheel's speed toward a target using whatever
magnetic torque the real geomagnetic field (Basilisk's WMM model) can
produce at the spacecraft's current position, rather than waiting for a
threshold and firing a discrete burst. It sits BETWEEN `rwMotorTorque`
and the RW hardware: it reads the originally-commanded RW motor torque
and republishes a modified one, so `engine.fsw.build_mtb_desaturation`
re-subscribes the RW effector's command input to override
`build_rw_motor_torque`'s own direct subscription (safe: Basilisk
resolves message subscriptions at `InitializeSimulation()`, so the last
`subscribeTo()` call before that wins).

New `SpacecraftConfig.magnetic_momentum_management`
(`MagneticMomentumManagementConfig`: `wheel_speed_biases_rad_s` -- one
target speed per reaction-wheel actuator, in listed order -- and a
`c_gain` control gain), requiring BOTH `"reaction_wheel"` and
`"magnetic_torque_rod"` actuators, mirroring task 3's `momentum_dumping`
requirement structure. New `ActuatorConfig(kind="magnetic_torque_rod")`
params: `gtHat_B` (dipole-axis unit vector) and `max_dipole_a_m2`
(maximum commandable dipole). Unlike `"thruster"`, `"magnetic_torque_rod"`
has NO standalone attitude-control role in this app -- Basilisk ships no
ready-made B-dot-style detumble controller, so a `"magnetic_torque_rod"`
actuator without `magnetic_momentum_management` set is rejected early
with a specific message, rather than silently building a dead actuator.

**A real, independently-found UI bug, fixed opportunistically**: the
"magnetic_torque_rod" entry in `_UNIMPLEMENTED_ACTUATOR_KINDS` (which
used to show "not simulated yet") had to be removed now that it IS
simulated, so the sensor/actuator editor's hint text gained a new
`_CONDITIONAL_ACTUATOR_NOTES` mechanism -- a kind can be fully wired up
but still need an extra note ("needs magnetic_momentum_management set")
beyond its plain param list, which `_UNIMPLEMENTED_ACTUATOR_KINDS`'s
binary "simulated or not" flag couldn't express.

**Verification**: confirmed empirically, not assumed from the shipped
example's comment, that `mtbMomentumManagement` needs NO equivalent of
task 3's "prime one tick, re-Reset()" dance -- it's a continuous
proportional controller, not an event-triggered threshold system.
Running the exact production `engine.fsw` call sequence
(`build_reaction_wheels` + `build_mrp_feedback` + `build_rw_motor_torque`
+ `build_magnetic_field_wmm` + `build_mtb_desaturation`, exactly as
`engine.service` now calls them) against a real Basilisk build drove a
4-wheel cluster from rest to within 0.1-0.5 RPM of commanded targets
(800/600/400/200 RPM) over a 120-minute run, while the attitude
controller simultaneously converged to near-exact inertial pointing
(attitude error ~3e-21). A real test-harness pitfall caught and fixed
along the way: a bypass-SPICE verification needs `magneticFieldWMM` fed
a planet-orientation matrix, and a naive all-zero one (Python's default
for an unpopulated `SpicePlanetStateMsgPayload`) made wheel speeds
converge nowhere near their targets (150-370 RPM off) -- an IDENTITY
orientation matrix (correct for this inertial-only bypass setup) fixed
it completely; `engine.service.SimulationService` always supplies a
real, non-degenerate SPICE-sourced planet message in production, so
this was specific to the test harness, not a bug in the shipped code.
Two new `requires_basilisk` tests in `tests/test_mtb_desaturation.py`
ACTUALLY PASS against that build. Plus 9 new schema-validation tests
and 4 new GUI tests (including the "no longer shows not-simulated-yet,
now explains the real requirement" regression guard), all passing.

**Template**: `13_magnetic_torque_rod_momentum_management.json`, the
direct counterpart to '12' -- same reaction-wheel/attitude-control setup,
magnetic desaturation instead of thruster desaturation, so the two
templates' result plots can be compared side by side (smooth continuous
convergence vs. sharp discrete steps). Full suite: 774 passed, 109
skipped.

### Real sun-heading estimation from CSS hardware (task 5 of 19), and two unrelated crash bugs found along the way

The last sensing-side gap on the 19-item backlog: every `fsw_mode` so far
read `simpleNav`'s noise-free TRUTH sun direction even when a
`coarse_sun_sensor` sensor was configured -- the sensor was cosmetic.
New `engine.fsw.build_css_sun_estimation()` builds a dedicated 8-device
`CoarseSunSensor` cluster (same cube layout as
`examples/BskSim/models/BSK_Dynamics.py`'s own `SetCSSConstellation()`)
feeding Basilisk's `cssWlsEst` weighted-least-squares estimator, and new
`SpacecraftConfig.fsw_params['use_css_estimation']` (validated: requires
at least one `coarse_sun_sensor` sensor) routes that ESTIMATE into
`fsw_mode: sunSafePoint`'s `sunDirectionInMsg` instead of truth -- the
same `cssWlsEst -> sunSafePoint -> mrpFeedback -> reaction wheels` chain
as Basilisk's own `examples/BskSim/scenarios/scenario_AttEclipse.py`
reference. This dedicated CSS cluster is intentionally separate from the
user-visible per-sensor `coarse_sun_sensor` telemetry `attach_sensors()`
already builds, same reasoning as task 4's dedicated TAM: `cssWlsEst`
needs one aggregate `CSSArraySensorMsgPayload` across the whole cluster,
which only Basilisk's `CSSConstellation` container produces.

**A second, genuinely new Basilisk Python-binding lifetime hazard**,
found by careful bisection after a reproducible segfault with no error
message: `CSSConstellation.sensorList` does not take ownership of the
`CoarseSunSensor` Python objects assigned to it, only a reference -- a
function-local `css_devices` list, discarded once the builder function
returned, let Python's garbage collector destroy the underlying C++
objects, leaving a dangling reference that segfaulted Basilisk inside
`InitializeSimulation()`. Same category of bug as this app's own Vizard
wiring (`access_indicator_bridges`/`generic_storage_list`/
`generic_sensor_list` -- "the caller MUST keep ALL FOUR alive"), now the
SECOND time this exact pattern has been found in this codebase --
confirmed reproducibly both ways (segfaults when discarded, works when
kept alive) against a real Basilisk build. Fixed by returning
`css_devices` from `build_css_sun_estimation()` and having
`engine.service.SimulationService` retain it in a new
`self._css_estimation_devices` list for the run's lifetime, mirroring
the Vizard pattern exactly.

**A much bigger, previously-undiscovered finding, chased down while
debugging what first looked like a CSS-specific bug**: closing the loop
end-to-end (CSS estimate -> `sunSafePoint` -> `mrpFeedback` -> idealized
actuation) on a small-sat-scale spacecraft went numerically unstable --
`sigma_BN` reached NaN within seconds, regardless of initial attitude
error size, and regardless of whether the estimate or simpleNav's own
truth drove the loop (ruling out CSS estimation itself as the cause).
Root-caused by direct experimentation, not guesswork: `engine.fsw.
DEFAULT_MRP_GAINS` (`K=3.5`, `P=30.0`) is lifted directly from Basilisk's
own `examples/BskSim` reference (`BSK_Fsw.py`'s `mrpFeedbackRWs`), which
is tuned for THAT example's 900 kg*m^2 spacecraft (`BSK_Dynamics.py`'s
`I_sc`) running its FSW task at `fswRate=0.1`. Applied unscaled to a much
smaller spacecraft (this app's own schema default inertia is
10 kg*m^2) at a coarser `dynamics_task_rate_s`, the resulting discrete
-time control update is wildly over-aggressive for the body's actual
rotational inertia -- idealized (unsaturated) actuation then has nothing
stopping the commanded torque from growing without bound every tick
(confirmed: roughly 2x-29x growth per tick depending on the exact
rate/inertia combination, a textbook discrete-time instability, not a
Basilisk bug). Reaction-wheel actuation's own torque saturation bounds
the damage (no NaN) but still produces a persistent, non-decaying
~30-degree pointing oscillation rather than real convergence -- confirmed
on BOTH the CSS-estimate-driven and truth-driven versions identically,
again ruling out CSS estimation as the cause.

**Two real, independent fixes came out of this**, both general risks for
ANY attitude-controlled spacecraft left on schema/engine defaults, not
specific to this feature:

- Scaling `control_params` (`K`/`P`) by a spacecraft's own inertia
  relative to that 900 kg*m^2 reference (both x `I_new/900`) converges
  cleanly instead -- confirmed directly: this task's own CSS-driven
  closed loop went from a persistent ~30-degree oscillation to a final
  pointing error of 8.5e-7 degrees with scaled gains, everything else
  unchanged. Applied to this task's new template (below) AND retroactively
  to `07_attitude_pointing_with_adcs_hardware.json`'s existing
  `sunSafePoint` + bare-RW setup, which had this exact problem already
  shipped and never actually verified end-to-end.
- For IDEALIZED actuation specifically (no RW/thruster hardware, so no
  torque saturation to bound an over-aggressive control update), the fix
  is a fine enough `dynamics_task_rate_s` instead -- confirmed:
  `06_attitude_pointing_basic.json`'s existing `hillPoint` + idealized
  -actuation setup reliably reached NaN within ~15 task ticks at its
  previously-shipped 1.0s rate; 0.1s (matching the `BSK_Fsw.py` reference
  `fswRate` this gain pair is tuned against) runs the same scenario
  stably for its whole duration. `_osculating_elements()`'s own
  `SimulationServiceError` message in `engine/service.py` already named
  "`dynamics_task_rate_s` too coarse" as a known failure mode for
  exactly this reason -- this is the first time it was actually
  triggered and confirmed, not just anticipated.

**A third, unrelated crash bug found while building a safe reaction
-wheel configuration for this task's own verification**: `rwFactory.
create()` (Basilisk's `simIncludeRW.py`) calls `exit(1)` directly -- not
a raised exception, killing the whole missionStudio process, not just
one run -- when `rw_type="custom"` (this schema's own default) is given
without a positive `u_max`, or without enough information (`Js`, or
`Omega_max`+`maxMomentum` together) to derive the wheel's spin-axis
inertia, or with BOTH `Js` and the `Omega_max`+`maxMomentum` pair at
once (those build a custom wheel's inertia exactly one way, never both).
All three are now schema-validated `ActuatorConfig(kind="reaction_wheel")`
requirements, confirmed against `rwFactory.create()`'s actual source,
with a message that always suggests the fix (set the missing param, or
use a named `rw_type` like `"Honeywell_HR16"` with its own built-in
defaults). Two already-shipped, real places hit variants of this exact
crash and are fixed alongside the schema check: '07's own bare
`gsHat_B`-only reaction wheels (now `"Honeywell_HR16"` + `maxMomentum`),
and `engine.spacecraft_templates.py`'s/`gui.sensor_actuator_editor.py`'s
own "new reaction wheel" default params (which gave `Js` AND
`Omega_max`+`maxMomentum` together -- the mutually-exclusive case).

**Template**: `14_css_sun_heading_estimation.json` -- the same 8-CSS
cluster, `sunSafePoint`, and scaled `control_params` confirmed above,
with `use_css_estimation: true`. New result series
`{name}.sun_heading_body_estimated` (the CSS estimate, alongside the
existing `{name}.sun_heading_body` truth series) lets the two be
compared directly in the GUI's results plots. New
`fsw_params['use_css_estimation']` GUI support in the spacecraft
editor's `sunSafePoint` parameter spec list.

**Verification**: `tests/test_css_estimation.py` (2 new
`requires_basilisk` tests) confirms, against a real Basilisk build, that
the scaled-gain CSS-driven closed loop converges the commanded body axis
to within 1 degree of the true sun direction (no NaN), and that its
final accuracy matches the truth-driven version for this template's
well-conditioned sun-direction/CSS-geometry combination -- the CSS-WLS
estimate's accuracy remains purely geometry-dependent, same as the
already-documented finding from earlier exploration (an under-determined
2-of-8-illuminated case gives large errors, a well-conditioned 4-of-8
case is exact with zero sensor noise; real hardware has exactly this
coverage gap, it is not something to "fix"). Plus 6 new schema
-validation tests for the three new reaction-wheel requirements and the
`use_css_estimation` sensor requirement, and 1 new template regression
test. `InertialUKF` (a full star-tracker + RW UKF attitude filter) is
deliberately OUT of scope for this task -- no clean shipped Basilisk
example to verify it against safely was found; a future task should
revisit it on its own.

### Direct celestial-body pointing (task 6 of 19): closing an already-documented gap

Surveyed every module in `src/fswAlgorithms/attGuidance/` against what
`engine.fsw.build_guidance` already wires up (`inertial3D`, `hillPoint`,
`velocityPoint`, `sunSafePoint`, `locationPointing`) to find the next
real, verifiable guidance gap. The highest-value one turned out to be
one this project had already flagged and explicitly deferred:
`fsw_mode: "locationPointing"`'s `fsw_params["target_body"]` option
(point a body-fixed axis straight at a celestial body, as opposed to
`target_ground_station`'s ground-station targeting) was schema-valid
-- `Scenario.validate()` already enforced the xor between the two
-- but `engine.fsw.build_guidance` hard-raised `FswError` for it,
because `locationPointing.celBodyInMsg` needs an `EphemerisMsg`, and
this checkout only ever produced a SPICE-sourced `SpicePlanetStateMsg`,
never converted.

That conversion turned out to be a single, well-defined Basilisk
module -- `ephemerisConverter.EphemerisConverter` -- confirmed directly
against `examples/scenarioAsteroidArrival.py`'s own
`addSpiceInputMsg()`/`ephemOutMsgs[i]`/`celBodyInMsg.subscribeTo()`
usage (that example points THREE separate `locationPointing` instances
at Earth, an asteroid, and back at Earth again, via exactly this
converter). New `engine.fsw.build_ephemeris_converter()` wraps one
dedicated converter per targeted body (trading a few trivial
pass-through modules for never needing `ephemObject`'s own
call-order index bookkeeping across spacecraft/targets); new
`engine.service.SimulationService` state
(`self._planet_state_out_msgs: Dict[str, msg]`) generalizes the
existing sun-specific `self._sun_state_out_msg` to every SPICE-tracked
body (`gravity.central_body` plus every `gravity.third_body_perturbers`
entry), so `target_body` can name any of them. New schema validation:
`target_body` must actually be one of those names (a real SPICE
ephemeris), with a specific error otherwise.

**A real, independently-found GUI bug, fixed alongside this**: the
spacecraft editor's `locationPointing` FSW-param spec list had
`target_ground_station` hard-marked `required=True` with no
`target_body` entry at all -- editing a spacecraft to use `target_body`
alone would have been rejected by the dialog itself with a "missing
required param" error before ever reaching the (now-correct) schema
validation. Fixed by adding `target_body` as its own spec and teaching
`_fsw_missing_required_keys` the real xor (either key present satisfies
the requirement); a new `_FswParamSpec.fill_on_reset` flag (default
`True`, set `False` only for `target_body`) keeps the "Reset to
template" button from filling BOTH mutually-exclusive keys at once,
which would have otherwise immediately failed `Scenario.validate()`'s
own xor check.

**Verification**: `tests/test_location_pointing_target_body.py` (1 new
`requires_basilisk` test) confirms, against a real Basilisk build, that
`pHat_B` converges onto a stand-in target body's direction (93.9-degree
initial error down to under 1 degree) with NO NaN, using the SAME
`dynamics_task_rate_s=0.1`/`DEFAULT_MRP_GAINS`/idealized-actuation fix
already established for task 5's gain/inertia investigation -- confirmed
to hold for this mode too, not just `hillPoint`/`sunSafePoint`. Plus 2
new schema-validation tests (SPICE-tracking requirement, central-body
-as-target case) and all pre-existing `locationPointing` schema tests
updated for the now-real (not just structural) `target_body`
validation. GUI tests pass unchanged.

**Template**: `15_celestial_body_pointing.json` -- a spacecraft keeping
its +Z axis pointed at the Moon throughout its orbit, the direct
counterpart to '07'/'06's ground-relative and orbit-relative pointing
modes (here the commanded attitude keeps changing as the TARGET itself
moves, not just the spacecraft).

### Lambert transfer planning tool (task 7 of 19): a new Mission Sequence command, not an FSW mode

Unlike every prior item on the 19-item backlog (all attitude/sensor/
actuator features), "Lambert transfer planning" is an ORBIT-planning
tool -- Basilisk's own `lambertPlanner`/`lambertSolver`/
`lambertValidator` FSW module chain (confirmed against
`examples/scenarioLambertSolver.py`'s own usage) solves for the
impulsive delta-V that takes a spacecraft from a given state to a
target position after a given time of flight. The natural integration
point in this app isn't a new `fsw_mode` -- it's a new **Mission
Sequence command**, `lambert_transfer`, alongside the existing
`maneuver` command this project already has (`schema.command.Command`,
`engine.mission_engine.MissionEngine`): where `maneuver` takes an
explicit delta-V, `lambert_transfer` takes a TARGET POSITION and SOLVES
for the delta-V, then applies it the same way.

**A real test-harness pitfall worth documenting (not a module bug)**:
`lambertValidator`'s own convergence check (`failedDvSolutionConvergence`)
compares each tick's delta-V solution against the PREVIOUS tick's,
zero-initialized at `Reset()` -- confirmed directly in
`lambertValidator.cpp` -- so a SINGLE call always reads as
"unconverged" even for a perfectly good, deterministic solution; it
needs at least 2 ticks of IDENTICAL input to actually converge. This is
a real, deliberate noise-robustness feature of the module (meant for a
continuously-running real-time guidance loop sampling noisy navigation
each tick), not a bug -- `_run_lambert_transfer` runs a throwaway,
single-task, 2-tick mini `SimBaseClass` (fed a literal snapshot of the
live spacecraft's current truth state, not the real running sim) for
exactly this reason, then applies the resulting delta-V to the REAL
simulation's velocity state object, same mechanism `_run_maneuver`
already uses (`dynManager.getStateObject(...).setState(...)`).

**Verification, including catching my own test-harness bug**: the
first cross-check attempt (manually propagating the ORIGINAL t=0
orbital state forward by the post-burn velocity) showed a 20,382 km
miss -- which turned out to be my own mistake, not a Lambert-solver
bug: `lambertPlanner` internally propagates the given nav state forward
to the maneuver time itself and reports that propagated state as
`lambertProblemMsgPayload.r1_N` (confirmed directly in its own message
payload comment, "position vector at t0"). Re-deriving the cross-check
from `r1_N`/`lambertSolutionMsgPayload.v1_N` (the actual burn point and
post-burn velocity) instead of the raw initial state gave a miss
distance of 4 MICROmeters -- pure floating-point noise, confirming
Basilisk's own module is exactly correct and the earlier "miss" was a
verification-script bug, not a real one. `tests/test_lambert_transfer.py`
(2 new `requires_basilisk` tests) confirms this against the real
`_run_lambert_transfer` method itself: one applies a transfer and
RK4-propagates the result to confirm sub-meter arrival accuracy, the
other confirms an infeasible transfer (5-second time of flight with a
`min_orbit_radius_m` constraint) raises a clear `MissionEngineError`
naming which `lambertValidator` checks failed, rather than silently
doing nothing.

New `Command(kind="lambert_transfer")` params: `spacecraft`,
`target_position_m` (inertial, central-body-relative), `time_of_flight_s`
(from THIS command's own execution, not a separately-delayed burn --
the burn itself is always immediate, like `maneuver`), `num_revolutions`,
`max_distance_target_m`, `min_orbit_radius_m` (the last two map directly
to `lambertValidator`'s own constraint checks). New GUI support in
`gui/mission_sequence_editor.py` (a dedicated command-editor page,
following the exact same pattern `maneuver`'s page already uses). A
real, independently-found reference-tracking gap fixed alongside this:
`schema/references.py`'s spacecraft-rename/reference-scanning only knew
about `"maneuver"`/`"propagate"`/`"assignment"` command kinds -- without
adding `"lambert_transfer"` there too, renaming a spacecraft would have
silently left any `lambert_transfer` command pointing at the OLD name
(a real dangling reference), and reference validation wouldn't have
caught a `lambert_transfer` targeting a nonexistent spacecraft.

**Template**: `16_lambert_transfer.json` -- the exact configuration
verified above (same orbit, target, and time of flight as
`examples/scenarioLambertSolver.py`'s own scenario), wrapped in a
3-command Mission Sequence (report position, lambert_transfer, coast,
report position again) so the "before" and "after" snapshots in the
GUI's Mission Output tab show the transfer actually landing on
target_position_m.

### Real FuelTank state effector (task 8 of 19): a second, more physical propellant model alongside the existing one

A real codebase audit finding, not a feature request: this project
ALREADY had propellant bookkeeping (`engine.orbit_maintenance`'s
station-keeping/phasing/constant-thrust controllers), but it's a
hand-rolled Python estimate -- explicit-Euler rocket equation, fed back
into `hub.mHub` manually each tick -- and ONLY covers those three
long-duration maintenance burns. The attitude-control/desaturation
thrusters from task 2/3 of this backlog (`"thruster"` actuators via
`thrForceMapping`/`thrMomentumDumping`) have never tracked propellant at
all -- they fire with unlimited "free" fuel. New
`SpacecraftConfig.fuel_tank` (`FuelTankConfig`) closes that gap using
Basilisk's OWN `fuelTank` state effector (`FuelTankModelUniformBurn`),
confirmed against `examples/MultiSatBskSim/modelsMultiSat/
BSK_MultiSatDynamics.py`'s own `SetFuelTank()` -- `fuelTank.
addThrusterSet()` ties the tank directly to a `ThrusterDynamicEffector`,
so it reads the exact same mass-flow rate (`mDot = F / (steadyIsp *
g0)`, confirmed directly in `thrusterDynamicEffector.cpp`) the thruster
hardware already computes for its own force/torque physics, and
depletes `hub.mHub` by exactly that amount. This is a materially more
physical model than the hand-rolled one: a real state effector, not a
Python `UpdateState()` estimate, including the propellant's own
contribution to the hub's center of mass as it depletes
(`tank_position_b_m` -> `setR_TB_B`) -- something a scalar `hub.mHub`
adjustment cannot represent at all. The two propellant models are
unrelated and don't conflict: a spacecraft could in principle use both
(station-keeping's own bookkeeping AND a fuel tank on its ACS
thrusters), each tracking its own, different propellant budget.

New `ActuatorConfig(kind="thruster")` + `fuel_tank` requires at least
one `"thruster"` actuator present (checked by schema, with a specific
error otherwise -- a tank with nothing drawing from it would be
schema-valid in Basilisk itself but almost certainly not what was
intended). Wired into BOTH places this app builds a
`ThrusterDynamicEffector` from `"thruster"` actuators: the primary
-control path (`fsw_mode` + no reaction wheels) and `momentum_dumping`'s
separate desaturation-thruster path -- confirmed these are mutually
exclusive in practice (the existing reaction_wheel+thruster mixing rule
means a spacecraft reaches at most one of the two), so exactly one
`fuelTank` ever gets built per spacecraft regardless of which path fires.

**Verification**: `tests/test_fuel_tank.py` (2 new `requires_basilisk`
tests) confirms, against a real Basilisk build, that a continuously
-firing thruster depletes fuel at the exact rate the rocket equation
predicts (within 1%, over a long-enough run that a real, confirmed
1-task-tick startup transient -- the thruster doesn't start firing until
the tick after `InitializeSimulation()` -- becomes negligible rather
than needing to special-case it), and that a thruster that never fires
at all leaves fuel mass exactly unchanged. New GUI support (a checkable
"Fuel tank" group box in the spacecraft editor, mirroring
`momentum_dumping`'s own pattern) and a new `{name}.fuel_mass_remaining`
result series.

**Template**: `17_fuel_tank_depletion.json` -- '11's exact 8-thruster
attitude-control setup with a 0.5 kg fuel tank added. Confirmed directly
against a real Basilisk build: the attitude converges from its initial
tip within about 100-150 seconds, consuming ~0.185 kg of propellant
during that active correction burn, after which
`{sat-1}.fuel_mass_remaining` goes flat (thrusters stop firing once
converged) -- a clean, real before/during/after depletion curve, not a
hand-picked-to-look-plausible number.

## Full-codebase audit: a comprehensive review and fix pass across every subsystem

A direct request ("do a complete and comprehensive audit and review of
entire code and fix any problems you may encounter"), separate from and
interrupting the 19-item feature backlog above (resumed after this).
Five parallel read-only review passes, one per subsystem
(`schema/`, `engine/service.py`+`engine/fsw.py`, the remaining
`engine/` support modules, `gui/`, and tests+templates+docs), each
briefed on this project's own known bug patterns (Basilisk object
-lifetime hazards, factory `exit(1)` crash risks, task-priority/message
-ordering bugs, control-loop gain/rate instability, a feature wired up
in one place but not another) so the search was productive rather than
generic style nitpicking. Every finding below was independently
re-confirmed by reading the actual flagged source before being fixed --
nothing here was taken on a review pass's word alone -- and, where a
Basilisk build could verify the fix, against a real one (this sandbox
happened to have a working `pip install "bsk[all]"` virtualenv available
from the review pass's own verification work).

### The most severe finding: unscaled default MRP gains are still the out-of-the-box behavior for ANY new scenario

This project already found and fixed (task 5 of 19, above) that
`engine.fsw.DEFAULT_MRP_GAINS` (`K=3.5`, `P=30.0`) is lifted directly
from Basilisk's own `examples/BskSim` reference, tuned for a
900 kg*m^2 spacecraft at a 0.1s FSW rate -- applied unscaled to a much
smaller spacecraft, the resulting discrete-time control update is wildly
over-aggressive and reliably diverges to NaN within seconds. That fix
was applied BY HAND to specific templates (07/14's explicit scaled
`control_params`; 06/15's finer `dynamics_task_rate_s`) -- but never
built into `engine.fsw` itself. Concretely: this schema's own defaults
(`inertia_kg_m2` = 10 kg*m^2 diag, `control_params={}`,
`dynamics_task_rate_s` = 10.0s) are a MORE extreme combination than the
one already confirmed to diverge, so a brand-new spacecraft created in
the GUI with any `fsw_mode` and no actuators (or reaction wheels) and
left on every default reproduces the exact same documented crash, with
zero code-level protection.

**Fixed at the root, not per-template**: `engine.fsw.build_mrp_feedback`
now takes an `inertia_kg_m2` parameter and defaults `K`/`P` to
`_default_mrp_gains_for_inertia(inertia_kg_m2)` -- `DEFAULT_MRP_GAINS`
scaled by the spacecraft's own mean (trace/3) inertia relative to the
900 kg*m^2 reference -- whenever `control_params` doesn't explicitly
override them (an explicit `control_params={"K": ..., "P": ...}` still
wins unchanged, confirmed by `tests/test_location_pointing_target_body
.py`'s own deliberate unscaled-gains case, which continues to omit
`inertia_kg_m2` and so is untouched by this change). All three
`engine.service` call sites (reaction-wheel, thruster, and idealized
-actuation control paths) now pass `sc_config.inertia_kg_m2` through.
This is the exact same `K/P x I_new/900` scaling formula task 5 already
verified by hand for 07/14 (`0.0194`/`0.167` at `I=5` reproduces exactly) --
generalized to every spacecraft automatically rather than needing a
template author to discover and apply it manually.

**Verification, against a real Basilisk build**: direct experimentation
confirmed the UNSCALED reference gains at schema-default inertia (10
kg*m^2) reach NaN within 120 ticks at a 1.0s rate, matching the already
-documented failure mode exactly. The SAME setup with the new scaled
default converges cleanly -- and, more than just "no NaN", converges
cleanly even at the schema's own coarse 10.0s `dynamics_task_rate_s`
default (final attitude error on the order of 1e-9 degrees over a 1200s
run), closing both halves of the original finding (the gain/inertia
mismatch AND the rate-coarseness risk) with one change. Also confirmed
this doesn't regress the two already-shipped thruster-actuated templates
(11/17, `control_params={}`, previously running on unscaled gains) that
a separate review pass flagged as "only verified for ~7% of their own
run duration": re-run over each template's FULL `dynamics_task_rate_s`
=0.5s/864s duration with the new scaled gains, the 8-thruster Schmitt
-trigger chain still fires (61/1729 ticks) and attitude error still
converges (0.374 -> 0.0477), no NaN -- so this fix also closes that
separate, previously-unverified-duration finding as a side effect. New
`tests/test_default_mrp_gain_scaling.py` (3 `requires_basilisk` tests):
confirms the unscaled-gain divergence still reproduces (a sanity check
that the regression test is actually testing something real), confirms
every-schema-default now converges, and confirms an explicit
`control_params` override still reaches the old unscaled behavior
unchanged (by design -- a user who deliberately sets `K`/`P` is opting
out of the automatic scaling).

### `engine.orbit_maintenance`'s delta-V bookkeeping undercounts true mass when a `fuel_tank` coexists

A second, related finding: `StationKeepingController`/
`PhasingKeepingController`/`ConstantFrameThrustController`'s
acceleration/delta-V estimate (`thrustMag / currentMass`) read
`scObject.hub.mHub` for `currentMass` -- which is NOT the spacecraft's
true total mass whenever a `schema.scenario.FuelTankConfig` "fuel_tank"
state effector is ALSO configured on the same spacecraft (e.g. backing
an unrelated "thruster" actuator's attitude-control/momentum-dumping
propellant). Confirmed directly in Basilisk's `fuelTank.cpp`: that
effector tracks its own mass via `effProps.mEff`, which correctly
contributes to the spacecraft's REAL simulated dynamics (Basilisk's own
integrator sums every state effector's mass), but is NEVER added into
`hub.mHub`. So this controller's own acceleration estimate silently
undercounted the true mass, inflating the estimate and ending a burn
early (an achieved-delta-V undershoot) in the controller's OWN
bookkeeping -- while the actual simulated physics stayed correct
throughout, since it never depended on this controller's estimate.

**Fixed** by reading `scObject.scMassOutMsg.read().massSC` -- Basilisk's
own hub+state-effector mass aggregate -- for the acceleration/delta-V
estimate specifically, while the propellant-burn WRITE-BACK (the part
that depletes this controller's OWN tracked propellant) deliberately
keeps reading/writing `hub.mHub` alone: feeding the aggregate into that
write-back would double-count a coexisting fuel tank's mass (once in the
tank's own state, once baked into `hub.mHub`). Confirmed by direct
experimentation that `scMassOutMsg` is fresh and correctly aggregated
every tick regardless of this controller's `AddModelToTask` priority
relative to the spacecraft's (a `SysModel` probe at the controller's own
default priority read `massSC` = 120 = 100 kg hub + 20 kg tank correctly
at every tick, including t=0). New `tests/test_orbit_maintenance_true_mass
.py` (3 `requires_basilisk` tests, built on a real `StationKeepingController`
via `build_station_keeping` with a real `fuelTank.FuelTank()` alongside
it) confirms: the controller's `_cumulativeDv` now matches
`thrust / (hub_mass + tank_mass)` (smaller than, and no longer equal to,
the old buggy hub-only computation); is unchanged for the common
no-fuel-tank case; and that the `hub.mHub` write-back itself does NOT
double-count the tank's mass.

### Three completeness gaps: every other actuator-management feature got matching telemetry/Vizard wiring except two newer ones

- **`engine.vizard` had no live propellant gauge for a real `fuelTank`
  state effector.** `station_keeping_by_spacecraft`'s own hand-rolled
  propellant tracking already got a "Propellant" `GenericStorage` panel
  the moment it shipped, but `schema.scenario.FuelTankConfig` (task 8 of
  19, above) never got an equivalent -- a spacecraft using the newer,
  more physical fuel-tank feature had zero live propellant visibility in
  Vizard. Fixed: new `fuel_tank_by_spacecraft` parameter on
  `engine.vizard.enable_vizard`, wired to a distinctly-labeled "Fuel
  Tank" panel (deliberately different from station-keeping's own
  "Propellant" label -- the two track independent propellant pools and
  can coexist on one spacecraft). `engine.service` now retains the
  `fuelTank.FuelTank()` effector itself on `_SpacecraftHandle` (it
  previously only kept the recorder, not the effector object Vizard
  wiring needs) at both call sites that build one. New
  `tests/test_vizard_fuel_tank_panel.py` (3 `requires_basilisk` tests,
  calling `enable_vizard` directly against a bare `SimulationBaseClass`
  to sidestep this sandbox's SPICE-kernel network block, the same
  bypass pattern `tests/test_thruster_control.py` already uses).
- **`magnetic_momentum_management`'s commanded dipole was invisible to
  the results UI.** `engine.service` built
  `mtb_effector, _ = fsw.build_mtb_desaturation(...)`, discarding the
  second return value (`mtbMomentumManagement` itself) entirely -- so,
  unlike `rw_speeds`/`thruster_on_time`/`fuel_mass_remaining`, there was
  no `{name}.mtb_dipole_commanded` series at all. Fixed: the second
  return value is now kept, its `mtbCmdOutMsg` recorded, and a new
  `{name}.mtb_dipole_commanded` result series (one column per torque
  rod, `A*m^2`) added, with a matching `gui/results_widget.py` display
  spec. New `tests/test_mtb_dipole_result_series.py` confirms
  `mtbCmdOutMsg.mtbDipoleCmds` is real and nonzero over a running
  desaturation loop (not a placeholder that would silently plot as all
  -zero).
- **`load_scenario_widget.py`'s bundled-template loader swallowed every
  exception with zero logging** (`except Exception: continue`, no
  `_logger` at all) -- unlike every sibling `noqa: BLE001` catch
  elsewhere in the GUI (`kernel_status_widget.py`, `run_worker.py`),
  which all log the full traceback before reporting failure. A corrupted
  or future-incompatible bundled template would silently vanish from the
  "Load Scenario" list with no trace anywhere. Fixed: added a module
  logger and a `_logger.exception(...)` call naming the skipped path
  before the `continue`.

### GUI: a reachable dead-end, and three stale default values

- **`orbit_only` mode left three actuator-requiring group boxes
  checkable with no way to satisfy their requirements.** The
  Sensors/Actuators tab (where `reaction_wheel`/`thruster`/
  `magnetic_torque_rod` actuators are added) is already hidden in
  `orbit_only` mode, and `power_group` was already correctly disabled
  for the same reason -- but `momentum_dumping_group`/
  `magnetic_momentum_management_group`/`fuel_tank_group` were not: a
  user could check one, click OK, and hit `Scenario.validate()`'s
  actuator-requirement error with no way to get back into the dialog to
  un-check it (the Sensors/Actuators tab that would let them add the
  required actuator stays hidden). Fixed by applying the exact same
  `setChecked(False)`/`setVisible(False)` pattern `power_group` already
  used, to all three.
- **Three GUI spin-box defaults were hardcoded literals that could
  silently drift from the schema's own defaults**: `bus_idle_power_w`,
  `battery_capacity_wh`, `battery_initial_soc` (power) and
  `tx_antenna_gain_dbi` (RF link) used a bare numeric literal as their
  "nothing configured yet" fallback instead of referencing
  `PowerConfig`/`RFLinkConfig`'s own dataclass default -- meaning a
  spacecraft created via the GUI with that field left unset could
  physically differ from one created by hand-editing JSON with the same
  field omitted, despite both claiming to use "the default". Fixed by
  switching all four to the same `value=config.field if config else
  SchemaClass.field` pattern already used elsewhere in this file (e.g.
  `drag_coeff`).

### Four smaller schema/validation fixes

- **`momentum_dumping` and `magnetic_momentum_management` were never
  actually validated as mutually exclusive**, despite `engine.service`
  building them as two independent `if` blocks (not `elif`) that would
  both try to command the same reaction wheels if both were set --
  confirmed directly in `engine.service`'s source. Fixed with a new
  `Scenario.validate()` check and `tests/test_scenario_schema.py::
  test_momentum_dumping_and_magnetic_momentum_management_are_mutually_exclusive`.
- **No positivity validation on `drag_coeff`/`drag_area_m2`/
  `srp_coeff`/`srp_area_m2`.** These feed straight into Basilisk's
  drag/SRP effectors as a physical coefficient/projected area; neither
  effector rejects a non-positive value itself, so a `<= 0` entry
  (a plausible typo) would silently produce a reversed or zero-magnitude
  force instead of a clear error. Fixed with four new `_require` checks
  (validated unconditionally, not just when `enable_drag`/`enable_srp`
  is set, so toggling either on later can't resurface an
  already-invalid value unnoticed) and 8 new parametrized tests.
- **`validate_all()` could report the same mission-sequence problem
  twice.** `Scenario.validate()` itself validates mission-sequence
  commands/references too (raise-fast, stopping at the first bad one)
  -- so when every resource was already valid, `validate_all()`'s own
  `try`/`except` around `scenario.validate()` caught and appended that
  SAME first-bad-command/dangling-reference message a SECOND time, on
  top of the dedicated collecting loop below it that already reports
  every mission-sequence problem (including that same first one). Fixed
  by recognizing both error-message formats always start with
  `"mission_sequence["` and skipping the `scenario.validate()` exception
  in that case, leaving the dedicated loop as the sole source of
  mission-sequence errors. Two new regression tests in
  `tests/test_validation.py` confirm a bad first command/dangling
  reference is now reported exactly once.
- Stale `README.md` claims corrected to match the app's actual current
  state: "thirteen" -> "seventeen" template scenarios (two places, after
  tasks 6/7/8 of the 19-item backlog each added one since that count was
  last written), test counts updated to the currently-passing 827/116
  (verified by actually running `pytest tests/ -q`), and a stale "not
  yet wired up" parenthetical removed for celestial-body `locationPointing`
  targets/thrusters/magnetic torque rods, all three of which are now
  fully implemented.

### Findings investigated and deliberately NOT changed

Documented here rather than silently dropped, per this project's own
"never sweep a finding under the rug" standard:

- `_run_lambert_transfer` rebuilds a full throwaway mini-sim on every
  call with no caching -- a real perf/scale concern inside a `while`
  loop (up to 10,000 iterations supported), but not a correctness bug,
  and no existing scenario exercises it at a scale where it matters.
- `_run_lambert_transfer`'s `last_failures` dict comprehension could
  raise a bare `IndexError` instead of a clear `MissionEngineError` if
  the mini-sim recorded zero ticks -- unreachable given the fixed
  60s/2-tick mini-sim configuration, so left as a latent inconsistency
  rather than a real risk.
- `kernels.py:build_spice_interface`'s `kernel_dir = statuses[0].path
  .parent` assumes a non-empty `kernels` list -- a bare `IndexError` if
  ever called with an empty one; every actual call site always passes a
  non-empty, schema-validated list, so this is an edge-case-only latent
  risk, not a reachable bug.
- `references.py`'s spacecraft-reference scanning does not look inside
  `if`/`while` `condition` strings or `script_block.code` -- a
  spacecraft referenced ONLY from inside one of those (as opposed to a
  structured `params["spacecraft"]` field) could be renamed or deleted
  without `validate_all()`/the GUI's dangling-reference check catching
  it. Real, but would need a small expression-language decision (how
  much of an arbitrary Python-ish condition string to parse) that is out
  of scope for an audit pass to make unilaterally -- flagged for a
  future, deliberately-scoped task rather than guessed at here.
- `fsw_mode="velocityPoint"` has shipped since early in this project but
  has never been exercised by a template or a `requires_basilisk` test,
  and so never got its own verified gain/rate combination the way every
  other mode did. The new inertia-scaled default gains above (which
  apply to every mode uniformly, not per-mode) substantially reduce the
  risk this represented, but a dedicated template + test is still the
  right way to close this gap fully -- left for a future task rather
  than rushed here.

**Full verification**: `pytest tests/ -q` (no Basilisk) --
8 new passing tests (drag/SRP positivity) and 1 (momentum_dumping/
magnetic_momentum_management mutual exclusion) plus 2 (validate_all
double-report) = 11 new non-Basilisk tests, all passing, zero
regressions. Every new `requires_basilisk` test file above
(`test_default_mrp_gain_scaling.py`, `test_orbit_maintenance_true_mass.py`,
`test_vizard_fuel_tank_panel.py`, `test_mtb_dipole_result_series.py`)
run individually against a real Basilisk build, all passing. Pre
-existing `requires_basilisk` suites re-run to confirm no regressions
from the `build_mrp_feedback`/`orbit_maintenance`/`vizard.enable_vizard`
signature changes: `test_orbit_maintenance.py`, `test_mtb_desaturation.py`,
`test_momentum_dumping.py`, `test_thruster_control.py`,
`test_location_pointing_target_body.py`, `test_css_estimation.py`,
`test_fuel_tank.py` all pass unchanged; `test_vizard.py`'s and
`test_gravity_gradient.py`'s SimulationService-level tests fail in this
sandbox for the same PRE-EXISTING reason documented throughout this
project (the SPICE-kernel network block), confirmed unrelated to this
audit's changes by reproducing the identical failure on `test_vizard.py`
before any of this pass's edits were made.

## Template 18: LEO station-keeping, the direct counterpart to '03's GEO case

A real gap, found by a direct question: '03' demonstrates GEO station
-keeping (Sun/Moon third-body gravity + SRP as the drift driver, a wide
5 km deadband, occasional corrections), but nothing demonstrated the
other, arguably more common real-world case -- a LEO spacecraft actively
compensating CONTINUOUS atmospheric drag decay, which needs a materially
different control regime (tighter deadband, more frequent/smaller
burns). `StationKeepingConfig`/`engine.orbit_maintenance` were always
altitude-agnostic (nothing drag-specific needed adding), so this was a
missing template, not a missing feature.

**Finding the right parameters took real investigation, not guessing**:
Basilisk's `ExponentialAtmosphere` module's own `simSetPlanetEnvironment
.exponentialAtmosphere()` Earth preset (`baseDensity=1.217 kg/m^3`,
`scaleHeight=8500.0 m`) is a single exponential fit tuned near the
surface -- applied unmodified at LEO altitudes (300-450 km) it predicts
a density around 15 orders of magnitude too low (`exp(-400000/8500)`),
producing no meaningful orbital decay at all over weeks. Confirmed
directly: an initial sweep using the stock preset showed exactly zero
station-keeping burns over a 14-30 day run at 300-450 km, regardless of
drag area/mass/deadband. Re-parameterized for verification purposes only
(NOT shipped -- see below) with a realistic ~400 km reference density
(~2.8e-12 kg/m^3, moderate solar activity) and an altitude-appropriate
~60 km scale height, the SAME `engine.orbit_maintenance.
build_station_keeping` + a real `dragDynamicEffector` (built the exact
way `engine.service` wires one, bypassing SPICE the same way
`tests/test_mtb_desaturation.py` already does) produced 2-3 real reboost
burns over 14 days at 400 km with a 1 km deadband and a small (1.5 m^2 /
120 kg) satellite -- a believable, demonstrable multi-burn LEO profile,
confirmed directly against a real Basilisk build before committing to
these numbers.

**What's shipped vs. what's verification-only**: the template itself
uses the SAME `nrlmsise00` conservative-margin atmosphere model '04'/
'05'/'07'/'08' already use (not the reparameterized `ExponentialAtmosphere`
stand-in above, which was a verification tool only) -- consistent with
every other drag-enabled template in this project, and more physically
correct (real density varies with latitude/season/solar activity; a
single exponential fit never will). Like '05', this template's EXACT
decay rate under the real `nrlmsise00` model has not been re-verified
end-to-end in this sandbox (no route to CelesTrak or the NAIF SPICE
kernel host here) -- stated plainly in the template's own `description`,
matching this project's established honesty convention for this exact
situation, rather than silently shipping unverified numbers as if they
were confirmed.

**Template**: `18_leo_station_keeping.json` -- a single 120 kg satellite
at 400 km/51.6 deg, `enable_drag=True`/`enable_srp=False` (isolating
drag as the one dominant perturbation, the same "isolate the lesson"
approach '03' already uses for GEO's SRP/third-body case), `station_keeping`
with a 1 km deadband (vs. '03's 5 km) over the same 14-day window as
'03', for a direct propellant-budget comparison. New
`tests/test_scenario_templates.py::test_leo_station_keeping_template_is_drag_driven_not_srp_driven`
confirms the structural contrast against '03' (drag on/SRP off, a
genuinely-LEO target altitude, a tighter deadband than GEO's). Catalog
entry added to `missionstudio/scenarios/templates/README.md` (which also
had its own stale "Nine ready-to-run scenario files" intro corrected to
eighteen -- it was never updated as templates were added over time), and
every "seventeen"/template-count reference in the top-level `README.md`
updated to eighteen. Full non-Basilisk suite: 844 passed, 126 skipped,
zero regressions (up from 838/126 -- the new template's own 4 parametrized
schema tests + 1 dedicated structural test + its 1 new GUI round-trip
parametrization).

## A guided "Customize..." wizard over three templates' own key parameters

A direct request: let a user "recreate the desired scenario themselves
or even tweak some parameters a little bit" starting from a template,
without first learning the full `ScenarioEditorWidget` form (every field
on every spacecraft/sensor/actuator). The full editor already supported
"open a template, then edit anything, then Save As" -- what was missing
was a FASTER, more approachable path for the common case of wanting to
change a handful of obviously-interesting knobs (the ones each
template's own `description` already calls out under "Try changing:")
without hunting for them across several tabs.

Three explicit design choices, asked of and made by the user rather than
guessed: a TRUE multi-step `QWizard` (one page per decision, not a
single dense form); the wizard hands off an in-memory `Scenario` to the
existing Scenario Editor on Finish (reusing all of its validation/save
machinery, rather than writing a file directly); and a PILOT rollout on
three representative templates first (`'03'` GEO station-keeping --
simple orbit-only; `'18'` LEO station-keeping -- same controller shape
plus a field that touches two dataclass locations at once; `'07'`
attitude+hardware+power -- the most structurally complex single
-spacecraft template) rather than all eighteen at once, to validate the
spec format and the UX before a larger rollout.

New `gui/template_wizard.py`: a declarative `TemplateWizardSpec` (list of
`WizardPageSpec`, each a list of `WizardField` -- label, help text, a
`get(scenario)`/`set(scenario, value)` closure pair, and spin-box
range/decimals/step/suffix), one entry in a `_SPECS` registry per
template filename, and a generic `TemplateCustomizeWizard(QWizard)` that
builds one `QWizardPage` per page spec from whichever template's spec it
was given -- adding a fourth template later is just another registry
entry, no change to the wizard machinery itself. Each spec's fields were
chosen directly from that template's own already-published "Try
changing:" text (`scripts/_generate_templates.py`), not invented fresh:

* `'03'` (2 pages): station-keeping deadband/thrust/isp/propellant
  budget, then simulation duration.
* `'18'` (4 pages): target altitude (the one field that updates BOTH
  `station_keeping.target_altitude_km` and `orbit.semi_major_axis_km`
  together, since the latter is measured from the central body's center
  and the former from its surface -- a wrong value in only one would
  leave the Scenario internally inconsistent), drag area/coefficient,
  the same station-keeping controller knobs as '03', then duration.
* `'07'` (3 pages): reaction-wheel max momentum (applied identically to
  all three wheels, keeping their already-symmetric layout symmetric
  rather than letting the wizard silently create an asymmetric set),
  solar panel area / battery capacity, then duration.

**A real design subtlety, caught before it became a bug**: the wizard
must operate on a COPY of the template's `Scenario`, never the one
`LoadScenarioWidget` loaded from disk, or accepting the wizard would
mutate (and `MainWindow` could then accidentally save over) the original
bundled template file. `TemplateCustomizeWizard.__init__` makes that copy
via `Scenario.from_dict(base_scenario.to_dict())` -- the same round-trip
`tests/test_scenario_templates.py` already trusts -- and `MainWindow
._on_load_scenario_customized` additionally opens the result with
`current_path=None` (refactored out of the existing `open_path()` into a
shared `_open_scenario()` helper), so `on_save()` always routes through
`on_save_as()` for a customized scenario, exactly like File > New
already does, never silently overwriting anything. Confirmed directly:
editing every field across all three templates' wizards, finishing, and
re-loading the original template file afterward shows it completely
unchanged.

New `LoadScenarioWidget.scenario_customized` signal (parallel to the
existing `path_chosen`, but carrying a `Scenario` object instead of a
path, since there is no file yet) and a "Customize..." button next to
"Open Template", enabled only when `template_wizard.get_wizard_spec()`
returns non-`None` for the selected template -- disabled (not hidden,
matching how `open_template_button` already handles "no selection") for
every other template, which still only offers the existing "Open
Template" flow unchanged.

**Verification**: `tests/gui/test_template_wizard.py` (10 new tests)
confirms, for all three registered specs: pages/fields are pre-filled
with the template's own current values; finishing with no edits
reproduces the original scenario byte-for-byte (`to_dict()` equality);
edited values apply correctly and the ORIGINAL `Scenario` object (and
the bundled template file on disk) stay untouched; '18's altitude field
updates both dataclass locations correctly; '07's reaction-wheel field
applies to all three wheels identically. Plus new tests in
`tests/gui/test_load_scenario_widget.py` (button enable/disable per
-template, signal emission on accept/cancel/no-selection) and
`tests/gui/test_main_window.py` (the full hand-off: `_current_path`
stays `None`, unsaved-changes confirmation gates it the same as the
existing template-open path, an invalid customized scenario shows a
clear error instead of crashing). Full suite: 860 passed, 126 skipped,
zero regressions (up from 844/126).

## Two real user-screenshot bugs, found immediately after the wizard shipped

**SpacecraftEditorDialog opened absurdly small.** A real user screenshot
showed the dialog rendering tiny enough that even its own first tab's
"Name"/"Dry mass [kg]" rows were clipped behind scrollbars, with the
window title itself truncated to "Spa...". Root cause: unlike
`propagation_setup_dialog.py` (which already has its own documented fix
for a similar but much milder discrepancy), `SpacecraftEditorDialog` had
NO explicit `resize()` call anywhere -- and simply adding
`self.resize(self.sizeHint())` would not have been enough here either:
every tab is wrapped in its own `QScrollArea` (see `_scrollable()`'s own
docstring for why -- so one busy tab can't force every other tab that
tall), and a `QScrollArea`'s `sizeHint()` is a small, mostly-arbitrary
default, NOT the wrapped content's real size. Confirmed directly: this
dialog's own `sizeHint()` measured 530x416 while its "Orbit / mass" tab
content alone needed 572x789, and the widest tab ("Power / propulsion /
link budget") needed 715. Fixed with an explicit `self.resize(...)`
computed from the widest tab's own content width (so nothing clips
horizontally) and a fixed, generous height (700px -- deliberately NOT
tall enough to fit the busiest tab without scrolling, since that tab
alone wants ~1485px, far taller than most screens; scrolling the busiest
tab independently is `_scrollable()`'s whole intended design, not a
bug). New `tests/gui/test_spacecraft_editor.py::
test_dialog_opens_at_a_usable_size_not_just_a_reasonable_upper_bound` --
the existing `test_dialog_natural_size_stays_reasonable` only guarded
the UPPER bound (catching the dialog blowing back up past ~800px), which
is exactly why this lower-bound regression shipped unnoticed; this new
test closes that gap.

**The Customize wizard buttons were too easy to miss.** Direct user
feedback: "I don't see the wizards. where are they? I wanted something
like what you did for the generate walker constellation, but bespoke
for each template/example scenario." The shipped design (one generic
"Customize..." button next to "Open Template", enabled only once a
template was already selected in the list above) buried the feature
behind a plain, unlabeled secondary button whose behavior depended on
unrelated widget state -- unlike `gui.spacecraft_editor.
SpacecraftListWidget`'s own "Generate Walker constellation.../Generate
phasing formation..." buttons, which are standalone, self-describing,
always-enabled actions. Fixed by replacing the single context-dependent
button with one dedicated "Customize: <template name>..." button per
registered `template_wizard` spec, always visible (not gated on list
selection at all), vertically stacked rather than a row (matching
`SpacecraftListWidget`'s own documented reasoning for why a 5-button row
already didn't reliably fit this app's left pane). `LoadScenarioWidget
.scenario_customized` and the rest of the hand-off to `MainWindow`
(`_on_load_scenario_customized`, `_open_scenario`) are unchanged --
only how a wizard gets STARTED moved. `tests/gui/
test_load_scenario_widget.py` updated for the new per-template buttons
(including a new regression test confirming a Customize click works
regardless of the list's current selection, the exact failure mode of
the earlier design). Full suite: 861 passed, 126 skipped, zero
regressions.

## "Apparently the dialog windows open too small everywhere" -- an app-wide audit

Direct follow-up after the SpacecraftEditorDialog fix above: a second
real user screenshot showed `gui.template_wizard.TemplateCustomizeWizard`
(brand new this session) with the SAME class of bug -- intro text and
help labels cut off mid-sentence -- plus a blanket report that this
might not be isolated to just these two dialogs. Audited every
`QDialog`/`QWizard` subclass in `gui/` (11 total) rather than only
reacting to the two already reported.

**Root cause, confirmed for each one individually, not assumed**:
`propagation_setup_dialog.py` already had its own documented, measured
fix for this exact bug class (`self.resize(self.sizeHint())`, with a
comment noting Qt sized that window smaller than its own sizeHint() on
first `show()` on a real desktop -- 871x734 vs. 871x768). Of the 11
dialog/wizard classes, only 3 had picked up that same fix
(`PropagationSetupDialog`, the just-fixed `SpacecraftEditorDialog`, and
`SpacecraftTemplateDialog`'s own fixed `520x320`) -- the other 8 had NO
explicit sizing at all, silently relying on Qt's default first-show
behavior, exactly the behavior `propagation_setup_dialog.py` already
proved unreliable on a real desktop. Rendering all 11 through this
project's own offscreen Qt test backend did NOT reproduce the user's
screenshot (every dialog measured `size() == sizeHint()` there) --
confirming this is a genuine, platform-dependent Qt layout-convergence
gap that can only be caught by explicitly forcing the size, never by
trusting headless/offscreen rendering alone to rule a dialog safe.

**Fixed by applying the same explicit resize to every dialog that was
missing it**: `WalkerConstellationDialog`, `GroundStationEditorDialog`,
`_CommandEditorDialog` (mission sequence), `_DispersionEditorDialog`
(Monte Carlo), `PhasingFormationDialog`, `_ItemEditorDialog`
(sensor/actuator), and `VizardDialog` each now call
`self.resize(self.sizeHint())` at the end of `__init__`, identical to
`propagation_setup_dialog.py`'s own proven fix -- for
`PhasingFormationDialog` specifically, this closes a REAL, independently
-measured 56px shortfall (497x545 vs. its own 497x601 sizeHint()), not
just a defensive guess.

**`TemplateCustomizeWizard` needed a different fix, not just the same
one-liner**: confirmed directly that `QWizard.sizeHint()` does NOT
reflect its own pages' content at all -- it measured a flat 500x360
regardless of which of the three registered specs ('03'/'07'/'18') was
given, while the busiest actual page ("Station-keeping controller",
shared by '03' and '18') needs 367x326 just for its own fields, before
QWizard's own title/intro banner and Back/Next/Cancel row are added on
top. `self.resize(self.sizeHint())` alone would therefore have done
nothing here. Fixed by computing the explicit target size from the
widest/tallest `_WizardFieldPage` across the WHOLE wizard (not just
whichever page is shown first) plus fixed padding for QWizard's own
chrome -- confirmed by rendering every page of all three specs at the
new size and checking none of them clip. Sizing from every page (not
just the current one) also means paging through Back/Next never
triggers an awkward mid-flow resize.

**Verification**: one new `test_dialog_resizes_to_its_own_sizehint_on
_construction`-style regression test per fixed dialog (matching
`propagation_setup_dialog.py`'s own existing test for the same bug
class), plus a dedicated `test_wizard_is_sized_to_fit_its_own_busiest
_page_not_a_flat_default` for the wizard's different fix, parametrized
across all three registered specs. Full suite: 871 passed, 126 skipped,
zero regressions.

## Customize wizards for the remaining fifteen templates

Direct follow-up, once the 3-template pilot (see above) was confirmed
working: "looking good, please create them for all the others now."
Every bundled template ('01' through '18') now has a registered
`gui.template_wizard.TemplateWizardSpec` -- the wizard MACHINERY needed
no changes at all (confirmed by the pilot's own design goal), this was
purely 15 new spec entries plus a handful of new small get/set helper
functions for shapes the pilot hadn't needed yet.

**Fields, chosen the same way the pilot's three were**: each spec's
fields come from that template's own already-published "Try changing:"
text wherever it maps to a safe scalar edit. A few templates' literal
text doesn't -- '04's Walker constellation text calls out
total_satellites/num_planes, which the text ITSELF says must be
regenerated via the GUI/CLI, not hand-edited (so the wizard instead
exposes altitude/inclination, applied uniformly across every generated
satellite -- a real Walker constellation shares both by construction);
'06'/'11'/'15's text calls out swapping `fsw_mode` to a different string
(a structurally different `fsw_params` set, not a spin-box edit -- the
wizard instead exposes each one's initial attitude tip, a safe,
meaningful "how far off-target does it start" knob that's always
present regardless of fsw_mode). Two things are NEVER exposed in any
spec, even where a template's own text mentions them: `fsw_mode` itself,
and `dynamics_task_rate_s` (several templates' own comments document a
real, confirmed NaN-divergence risk from setting this too coarse -- see
this file's own "MRP gain scaling" entry above).

**A real, independently-found precision bug, caught by this task's own
comprehensive round-trip tests (new: every spec, not just the pilot's
three, checked for an EXACT no-op round-trip and for still validating
after a one-step nudge to every field)**: '18's own altitude field
(carried over unchanged from the pilot) silently drifted
`orbit.semi_major_axis_km` by ~137 m on EVERY `accept()`, even with zero
user edits -- its setter recomputed `semi_major_axis_km = altitude +
_EARTH_RADIUS_KM` using a fixed module constant, but '18's own
`scripts/_generate_templates.py` builder was written with a simpler,
rounder "6378.0" Earth radius, not that constant's more precise value.
Two more of the same CLASS of bug surfaced in the new specs: '04's
Walker altitude field (its OWN setter used the same fixed-constant
pattern, now additionally confirmed to be Basilisk's real
`earth.radEquator`, 6378.1366 km -- but at this field's original
`decimals=1`, the display rounding alone was enough to lose the ~0.4 m
remainder) and '13's wheel-speed-bias RPM fields (a separately
-precomputed reciprocal constant for the reverse rad/s<->RPM conversion
left a few-ULP floating-point discrepancy after one round trip).

Fixed three different ways, matched to each root cause: '18's setter now
derives the radius offset from the scenario's OWN current
(pre-mutation) `semi_major_axis_km`/`target_altitude_km` rather than
applying a fixed constant, so it exactly preserves whatever offset a
template was actually built with, regardless of convention; '04's
Altitude field's `decimals` went from 1 to 4 (now the display itself
doesn't truncate away precision `_EARTH_RADIUS_KM`, corrected to
Basilisk's real `6378.1366`, no longer needs to lose); '13's RPM
conversion now divides/multiplies by the exact SAME constant
`scripts/_generate_templates.py` itself uses (`_RPM_TO_RAD_S =
math.pi / 30.0`), confirmed directly to make the round trip bit-exact
rather than just visually close. All three were real bugs that would
have shipped invisibly (the drift is far too small to notice in the UI,
but a module whose own module docstring explicitly promises "the
original template file is never touched" should not silently nudge a
DERIVED scenario's values on a true no-op either) -- found specifically
because the broader rollout's own test sweep checked EVERY spec for an
exact round trip, not just the three the pilot had already covered.

**Verification**: `tests/gui/test_template_wizard.py`'s two
template-count-agnostic parametrized tests (pre-fill correctness, sizing
-- already written for the pilot) now run against all eighteen
specs automatically (parametrized from the real bundled-template
directory listing, not a hand-maintained list), plus two brand new
parametrized tests across all eighteen: an exact (`to_dict()`
-equality) no-edit round-trip, and a "nudge every field by one step,
still validates" sweep -- the two tests that actually caught the three
precision bugs above. Full suite: 938 passed, 126 skipped, zero
regressions (up from 871/126).

---

## Load Scenario tab: real screenshot caught overlapping/garbled text on resize/maximize

A user reported the main window "doesn't allow to maximize and breaks
and freezes and crashes" when just resizing/maximizing it -- no
simulation running. A headless, offscreen `.show()` /
`.showMaximized()` / `.showNormal()` reproduction of `MainWindow` and
several dialogs raised no exception (same limitation this file's own
earlier dialog-sizing bugs already ran into -- the offscreen Qt platform
plugin's virtual framebuffer essentially always has "enough" room, so it
cannot reproduce a bug that only shows up when a real window's available
space is actually smaller than a widget's natural content). A follow-up
real-desktop screenshot (not offscreen) made the bug concrete: visibly
overlapping, garbled text in the Load Scenario tab, right at the
boundary between the bottom of the 18-item template list and the
description label below it.

**Root cause**: `LoadScenarioWidget` (the "Load Scenario" tab) builds
its entire body -- an intro label, the template `QListWidget` (grown
from 9 to 18 rows over this file's own earlier entries), the
description label, the Open/Browse button row, and now one always
-visible standalone "Customize: \<template name\>..." button per
template (18 of them, from the `template_wizard` rollout earlier in this
file) -- straight onto its own single top-level `QVBoxLayout`, with no
`QScrollArea` anywhere. It's embedded directly as a tab page inside
`MainWindow`'s `self.left_tabs` (`QTabWidget`), itself inside a
user-resizable `QSplitter`. This tab's natural content height grew
substantially across this file's own history (9 rows -> 18 rows, plus 18
new buttons with no scroll area) until it could exceed what a real,
non-maximized window -- or even a maximized one on a modest display --
actually has room for. When the real window (or just the splitter's left
pane) is resized/maximized to less height than this tab needs, the
`QVBoxLayout` has to compress something, and `QLabel` does **not** clip
its own wrapped text to its allocated rect -- squeezed below the height
its wrapped text needs, it simply paints the overflow past its own
boundary, over whatever widget sits next to it in the layout. That's
exactly what the screenshot showed: `description_label`'s (and the
list's) painted content overlapping across their shared boundary. This
is a real rendering bug, not a cosmetic one -- it's the same failure
mode `scenario_editor.ScenarioEditorWidget`'s own top-level
`QScrollArea` and `spacecraft_editor.py`'s per-tab `_scrollable()`
helper were already built to prevent elsewhere in this app (see each
module's own comments); `LoadScenarioWidget` was the one tab-page-sized
widget in the GUI that still lacked it, and the two things that grew its
content well past "always fits" (18 template rows, 18 customize buttons)
were both added after those other widgets had already needed the fix.

**Fix**: wrapped `LoadScenarioWidget`'s entire body in its own internal
`QScrollArea` (`setWidgetResizable(True)`, zero-margin outer layout),
exactly matching `ScenarioEditorWidget`'s own existing pattern -- the
widget's public API (`list_widget`, `description_label`,
`open_template_button`, the "Customize: ..." buttons, etc.) is
unaffected, since a `QScrollArea` only changes *where* a widget's
geometry comes from, not its identity or its own children. A
`QScrollArea` never squeezes its inner widget below its own size hint:
when there's enough room it sizes the content to the viewport as before,
and when there isn't, it scrolls instead of letting the layout compress
a child below what it needs -- which removes the overlap mechanism
entirely, rather than just tuning the specific numbers (e.g. the list's
own `_size_list_to_contents()` fixed-height computation) that happened
to trigger it this time.

**Verification**: offscreen `.show()` alone can't prove a real-desktop
rendering bug is gone (same caveat as always in this file), but the
mechanism itself is directly testable: resizing the widget to 500x150
(far shorter than its real natural content height) and comparing
`description_label.geometry().height()` against
`description_label.heightForWidth(...)` after a few `processEvents()`
calls -- the same verification approach
`test_propagation_setup_dialog.test_srp_pointer_label_gets_its_full_wrapped_height_not_clipped`
already used to catch a real instance of this exact QLabel-overflow
failure mode elsewhere in this app -- confirms the label's allocated
height now always matches what it needs, never less. A rendered,
squeezed-window screenshot taken directly from this fix (offscreen, but
still an actual pixel render, not just a geometry assertion) shows the
template list scrolling cleanly within its own bounds instead of
overlapping the content below it. Two new regression tests added to
`tests/gui/test_load_scenario_widget.py`: one structural (a
`QScrollArea` wraps the content, `description_label` lives inside it),
one behavioral (the squeeze-and-measure check above). Full suite: 940
passed, 126 skipped, zero regressions (up from 938/126).

---

## Version 1.1.0 released

Cut a new release on top of everything accumulated since 1.0.0 was
tagged (`54545db6c`, which shipped with nine templates and no
`template_wizard.py` at all): the four new actuator/effector
capabilities (gravity gradient, thruster attitude control, momentum
dumping, magnetic torque rods) and their templates (10-13), the two new
attitude-guidance capabilities (CSS sun-heading estimation, celestial
-body pointing) and their templates (14-15), the `lambert_transfer`
Mission Sequence command and its template (16), the real `FuelTank`
effector and its template (17), the LEO station-keeping template (18),
the "Customize: ..." wizard's full rollout to all eighteen templates,
`engine.fsw`'s automatic MRP-gain-vs-inertia scaling, the GUI dialog
-sizing audit (`SpacecraftEditorDialog`, every `TemplateCustomizeWizard`
spec, `LoadScenarioWidget`'s `QScrollArea` fix), and this session's own
README accuracy pass plus the new `USER_MANUAL.md`.

Confirmed no breaking change before cutting the version: `schema.scenario.
CURRENT_SCHEMA_VERSION` is still `1`, unchanged since 1.0.0 -- every new
field across all of the above is purely additive with a sensible
default (`schema/migrations.py`'s own docstring: additive fields need no
migration), so every scenario file valid under 1.0.0 stays valid,
byte-identical, under 1.1.0. This is therefore a MINOR version bump
under semver (new backward-compatible functionality, no breaking
changes), not a MAJOR one, despite the size of the feature list above.

Version bumped `1.0.0` -> `1.1.0` in `pyproject.toml`,
`missionstudio/__init__.py`, and `packaging/windows/missionstudio.iss`'s
`MyAppVersion` (the `.deb` build reads `missionstudio.__version__`
directly -- `packaging/deb/DEBIAN/control.in` has no version string to
touch). `packaging/build_deb.sh` was re-run in this development sandbox
to confirm the packaging mechanics still work end-to-end at the new
version: `dpkg-deb --build` succeeds and produces a valid
`missionstudio_1.1.0_all.deb`. The full real-Basilisk install/test pass
(venv creation, `bsk[all]` from PyPI, a real `printBuildInfo()`, hundreds
of tests passing from the installed copy) was NOT independently re-run
against this specific 1.1.0 artifact -- it was run once, at 1.0.0,
against install logic that is unchanged since (see `packaging/README.md`'s
"1.1.0 release note" for the same caveat in context). Full suite: 940
passed, 126 skipped, same as immediately before this release (no tests
added or removed by the version bump itself).

---

## Version 2.0.0: renamed to SpaceMissionStudio, missionAnalysis removed

Two changes landed together, each its own commit/PR, then released as
one version bump.

**Removed `missionAnalysis`**, a standalone, one-off constellation
mission-design case study that predates this project (its own README
said it was never run end-to-end in this development sandbox). Checked
thoroughly before removing: not imported anywhere, no `sys.path`
reference, nothing in the build system, CI, docs toctree, or packaging
-- the only references anywhere else in the repo were prose provenance
comments in `engine/*.py`/`schema/scenario.py` ("ported directly from
`../missionAnalysis`'s X"), left as historical design-rationale notes,
not functional dependencies. This project has since absorbed and
generalized essentially everything missionAnalysis did -- constellation
generation, station-keeping/phasing controllers, power budget,
link-margin estimate, Vizard comm-ring visualization -- with a real
schema, GUI, and test suite, and far more capability than the one fixed
case study ever covered. Confirmed with the full test suite unchanged
after deletion (940 passed, 126 skipped) -- proof nothing actually
depended on it. Also dropped the now-stale `missionAnalysis/*` entries
from `.gitignore`.

**Renamed "missionStudio" to "SpaceMissionStudio"** (short form "SMS"),
requested directly, with one explicit constraint: "SMS" collides hard
with Short Message Service, so it was scoped to prose only -- never the
CLI command, package name, or any identifier. A full technical rename,
not just branding, since that's what was asked for:

* Directory: `missionStudio/` -> `SpaceMissionStudio/` (via `git mv`,
  history preserved).
* Python package/import name: `missionstudio` -> `spacemissionstudio`.
* CLI command, PyPI/`.deb` package name: same substitution.
* Windows installer: `MyAppName`/`MyAppPublisher`/install
  directory/Start Menu group/output filename all updated, plus the
  `AppId` GUID regenerated (`D9A6194C-1034-4A25-946A-689B2B13E86D`, was
  `B96F3E9D-6C0B-4C61-9C1E-8B9E3E5B6F7A`) -- that field's own comment
  says not to reuse a GUID for a different application identity, and
  this genuinely is one (no end user has ever installed the old build
  via this installer, which has still never run on a real Windows
  machine).
* Desktop entry (`packaging/spacemissionstudio.desktop.in` and the
  packaged `.desktop`): `Name=`/`Exec=`/`Icon=`/`StartupWMClass=`
  updated, files renamed.
* Every in-app GUI string -- confirmed with a real headless render
  (window title read `SpaceMissionStudio -- untitled`, the About dialog
  and Load Scenario tab intro text both read "SpaceMissionStudio", all
  eighteen templates still loaded), not just grep.

**A real gap found mid-rename, not anticipated going in**: a blind
two-rule sed (`missionstudio` -> `spacemissionstudio`,
`missionStudio` -> `SpaceMissionStudio`) missed two more case variants
genuinely present in the codebase -- `Missionstudio` (PowerShell's own
PascalCase-of-a-lowercase-string convention for parameter names, e.g.
`$MissionstudioWheel` in `install.ps1`) and `MISSIONSTUDIO` (an
env-var-style all-caps pair, `MISSIONSTUDIO_DIAG_SKIP_ECLIPSE_READ/
_SUBSCRIBE`, embedded in one template's own `description` field, plus
`MISSIONSTUDIO_SETUP_ERROR` in `bootstrap_env.ps1`). Found by an
exhaustive case-variant inventory (`grep -ohE "[Mm]ission[Ss]tudio"`)
before declaring the rename done, not assumed complete after the first
pass -- two more targeted sed rules closed both gaps, confirmed by a
final occurrence-count cross-check (every remaining lowercase
`missionstudio` substring is part of `spacemissionstudio`, every
`missionStudio` is part of `SpaceMissionStudio`, with zero exceptions
outside two deliberately-preserved historical references).

Also found: a stale, untracked `build/`/`*.egg-info` directory pair
sitting in the working tree from an earlier local install, still
containing a copy of the OLD package under the old name. Not tracked by
git (so not part of any diff), but real stray content that would have
caused confusion on the next local build -- deleted outright; both
regenerate correctly under the new name on reinstall.

**Deliberately NOT touched**: this file's own body, for the same reason
stated in its own opening section -- an honest record of what was
actually true when each entry was written, not a current reference. One
note near the top (read it first) explains the rename and asks the
reader to mentally substitute the new name below that point.

**Verification**: full test suite unchanged through both changes (940
passed, 126 skipped) -- re-run after `missionAnalysis` removal, then
again after a real `pip uninstall missionstudio` + `pip install -e
".[dev,gui]"` reinstall under the new package name. The new
`spacemissionstudio` CLI command confirmed working and the old
`missionstudio` command confirmed gone. `packaging/build_deb.sh` re-run
and produces a valid `spacemissionstudio_2.0.0_all.deb`.

**Version bumped** `1.1.0` -> `2.0.0` -- a MAJOR bump under semver, the
first in this project's history, because this is the first genuinely
breaking change: every scenario file/template/capability from 1.1.0
carries over completely unchanged, but anyone's own code importing
`missionstudio` or invoking the `missionstudio` CLI command breaks and
needs updating to `spacemissionstudio`. `CURRENT_SCHEMA_VERSION` stays
`1` -- the scenario file format itself has no breaking change, only the
package/CLI identity does. Bumped in `pyproject.toml`,
`spacemissionstudio/__init__.py`, and
`packaging/windows/spacemissionstudio.iss`'s `MyAppVersion` (the `.deb`
reads `spacemissionstudio.__version__` directly, no change needed
there).

A published GitHub Release, "missionStudio v1.1.0" (tag `v1.1.0`), had
already gone out pointing at the commit immediately after the 1.1.0
version bump -- before this rename and the `missionAnalysis` removal
landed. Rather than move that tag out from under an already-published
release (a published release's tag shouldn't move retroactively), this
version bump gets its own fresh tag/release instead, so `v1.1.0` stays
an honest, immutable snapshot of exactly what it was when published.


---

## Template 19: automatic Sun-pointing / ground-station-pointing comms link, with live power + RF telemetry

Direct request: a spacecraft that Sun-points its solar panels by default, automatically
re-points its antenna at a ground station whenever it's actually, geometrically in
contact (never a manually-specified time window), physically slews between the two
rather than snapping, and drives a real, live-updating power budget and RF link-margin
estimate throughout -- plus a GUI view to watch all of that while a run is in progress.

**The core mechanism (`schema.scenario.CommsPointingConfig`, `engine.fsw.build_comms_pointing`)**:
a small, module-private `sysModel.SysModel` subclass (`_CommsPointingArbitrator`) that each tick
reads the spacecraft's REAL `groundLocation.GroundLocation` access state
(`AccessMsgPayload.hasAccess` -- the same real elevation-mask access analysis this project's
ground-station features already use) and forwards whichever of two already-built guidance
chains -- an ordinary `sunSafePoint` chain (Sun-pointing) and an ordinary `locationPointing`
chain targeting the configured ground station -- is currently "active" onto its own output
`AttGuidMsg`, which feeds the spacecraft's one shared `mrpFeedback` control loop. Only the
attitude REFERENCE switches; nothing here ever touches the spacecraft's own integrated attitude
STATE, so the existing closed-loop controller simply starts tracking a new target the next
tick -- this is what makes the Sun-pointing <-> ground-station-pointing transition a genuinely
physically-simulated slew (confirmed, not just asserted: `tests/test_comms_pointing.py`'s own
continuity check) rather than an instantaneous attitude jump, with zero new dynamics code
needed. An optional `comms_power_w` drives a `simplePowerSink` live, gated the same way, for a
downlink transmitter's stand-in power draw. Built from two patterns already proven elsewhere in
this codebase rather than a single official Basilisk example (there isn't one for this exact
orchestration): the real `examples/scenarioAttitudePointingPy.py`'s `PythonMRPPD` class for the
general "custom Python `SysModel`, construct-then-`.write()` a message" mechanics, and
`engine.orbit_maintenance`'s own controllers (`StationKeepingController` et al.) for the
Python-list-telemetry-log convention. Wired into `engine.service.SimulationService.build()` as
its own branch (sibling to the existing `fsw_mode` branch, since `Scenario.validate()` makes the
two mutually exclusive -- `comms_pointing` fully owns attitude control when set), with the
arbitrator/`mrpFeedback`/actuation itself built in a deferred second pass once every spacecraft's
`accessOutMsg` exists -- the same "defer to a second pass" pattern `phasing_keeping` already
established, not a new one. Only idealized-torque actuation is wired for a `comms_pointing`
spacecraft in this round (matching `fsw_mode`'s own "no actuators configured" path); real
reaction-wheel actuation for this mode is a reasonable follow-on, not built here, and this
project's own templates simply don't configure actuators on a `comms_pointing` spacecraft yet.

**RF link budget enhancement (`engine.link_budget`)**: `RFLinkConfig` gained one new optional
field, `antenna_beamwidth_deg` (`None` by default -- every existing scenario's exact prior
behavior, zero pointing-loss term, is unchanged). When set together with `comms_pointing`, the
spacecraft's own ACTUALLY-achieved antenna pointing error (the arbitrator's own
`pointingErrorDegLog`, derived from Basilisk's own already-computed `sigma_BR` via the exact
MRP-to-rotation-angle relation `theta = 4*atan(|sigma|)` -- no new geometry computed by hand)
feeds a standard parabolic/Gaussian-main-lobe pointing-loss approximation,
`12*(pointing_error_deg/antenna_beamwidth_deg)^2` dB (clamped at 30 dB -- the approximation is
only meaningful within a few beamwidths of boresight), into a new `link_budget_breakdown()`
function that exposes every intermediate stage (EIRP, FSPL, pointing loss, received power, N0,
C/N0, Eb/N0, margin) as its own dataclass, not just the final margin number `link_margin_db()`
(now a thin wrapper over it) always returned. `link_margin_series()` -- the function
`engine.service`'s `_extract_results()` actually calls -- now additionally gates on the
spacecraft's own `{sc}.comms_pointing.active_mode` series (when present) alongside the
pre-existing `has_access` gate, and feeds its `{sc}.comms_pointing.pointing_error_deg` series
through per-sample: real geometric access alone no longer implies a defined margin -- right at
a transition, `has_access` can already be true while the still-large pointing error legitimately
produces a poor or negative margin, making "geometric visibility vs. actual RF link
availability" a real, inspectable distinction rather than an asserted one. A spacecraft with no
`comms_pointing` configured has neither series recorded, so this is exactly equivalent to the
pre-existing, always-perfect-pointing margin for every template that predates this feature.

**A real, more physically-complete alternative was found and deliberately NOT used**:
`src/simulation/communication/{simpleAntenna,linkBudget}/` -- real, compiled Basilisk modules
(copyright 2025, NTNU) computing a true 2D-Gaussian-beam antenna pattern, real pointing loss
from actual 3D antenna/spacecraft/ground geometry, FSPL, and ITU-R P.676 atmospheric
attenuation. Not used here: no example scenario anywhere in this checkout exercises either
module (confirmed via `grep`), so there is no reference usage to confirm the wiring against --
unlike every other Basilisk module this project uses, which was checked against a real example's
own usage first. Betting this feature on an unexampled, unverified-in-this-project module, with
no Basilisk build available in this sandbox to test it directly, was judged the wrong risk
trade; the existing, already-proven, Basilisk-free `engine.link_budget.py` was extended instead.
A real future upgrade path, documented in template '19's own `description` too.

**New template, '19 - Sun-pointing spacecraft with automatic ground-station comms link'**: one
small-sat-class spacecraft (idealized actuation, `_INERTIA_MEDIUM`, the exact
`dynamics_task_rate_s=0.1` combination '06' already confirmed stable for that actuation/inertia
pair), a near-polar 550 km orbit, one ground station ("boulder-gs"), `power`/`rf_link`
(S-band, `antenna_beamwidth_deg=30`)/`comms_pointing` all set. 0.5-day duration (not longer):
idealized actuation's confirmed-stable rate is fine, but genuinely large-angle Sun-pointing
<-> ground-station-pointing slews over a much longer run than '06's own short convergence demo
were not independently re-confirmed against a real Basilisk build in this sandbox (MRP
feedback's own commanded torque stays naturally bounded regardless of angle size, which is why
this is believed low-risk, not because it was re-verified here) -- the template's own
`description`, and `scripts/_generate_templates.py`'s own comment on this function, say so
plainly. Regenerated through the project's own `scripts/_generate_templates.py` (its own source
of truth), not hand-written JSON; a registered `gui.template_wizard.TemplateWizardSpec` (ground
-station minimum elevation, antenna beamwidth, comms transmitter power, duration) follows the
same rollout this project already completed for every other template -- '01' through '19' now
all have one. `scenarios/templates/README.md`'s own catalog and `README.md`'s template
count/Capabilities/repository-layout sections updated to match; '19 is explicitly called out as
the one exception to this project's own "templates are deliberately minimal and isolated"
convention, since it deliberately integrates several concepts at once.

**Live telemetry (`gui.mission_dashboard_widget.MissionDashboardWidget`, a new "Mission
Dashboard" tab)**: needed NO new live-data plumbing at all -- `_extract_results()` was already
confirmed (see this file's own Mission Sequence/results-widget entries) to run on every
`run_live()` progress chunk, so any new series this feature adds was already "live" the moment
it existed. The only real new work was a widget to display it, following `ResultsWidget`'s own
`set_result()`/`set_live_result()` calling convention exactly so `gui/main_window.py` could wire
it in with one more call alongside each existing `results_widget` call. Shows four grouped
panels (Operating state / Attitude / Power / RF link) with plain `QLabel` readouts, colored
status badges (a small `_badge_style()` helper over `theme.py`'s own `PALETTE`, the same
"reuse this project's existing themed colors" precedent `feedback.py`'s toast/inline-validation
helpers already set), and a battery-SOC `QProgressBar`. A genuinely useful reuse, not just
display plumbing: rather than recording a dozen more RF-breakdown series from the engine side,
the dashboard instead calls `engine.link_budget.link_budget_breakdown()` itself, live, from the
already-recorded range/pointing-error samples plus the run's own `Scenario` (passed through
alongside the `ResultSet`, the same optional-auxiliary-argument pattern `ResultsWidget` already
uses for `epoch_utc`) -- the exact same pure-Python function the engine itself uses, so the
dashboard's numbers can never drift out of sync with what a post-hoc analysis would compute.
Single-spacecraft scope (the first spacecraft found carrying a `comms_pointing` series),
matching `gui.template_wizard`'s own already-documented `_sc()` precedent for the same
simplification.

**Verification**: as with every Basilisk-dependent feature in this project, nothing above could
be run end-to-end here (no Basilisk build in this sandbox) -- built directly against real,
already-read Basilisk source (message payload structs, module headers, the same confirmed
`examples/scenarioAttitudePointingPy.py`/`engine.orbit_maintenance` patterns cited above) rather
than assumed. What WAS run here: the full Basilisk-free test suite (schema validation and
round-trip, the new `link_budget` pointing-loss/gating math against hand-computed values, and
the new dashboard widget against synthetic `ResultSet`/`Scenario` data, headless via
`pytest-qt`) plus `tests/test_comms_pointing.py`, a new `requires_basilisk`-marked test
isolating the arbitrator's own mode-switching/power-gating/attitude-continuity behavior (it
collects correctly and skips cleanly here, same as this project's entire existing
Basilisk-dependent suite always has in this sandbox -- it will only genuinely run once a real
build is available). Full suite: 976 passed, 130 skipped, zero regressions (up from 940/126, this
file's own last-recorded figure, in the "Version 2.0.0" entry above).

---

## Comprehensive audit of the comms_pointing feature (template 19) and a full README pass

Direct request: "update all readme's, do a complete and comprehensive audit and review of
everything, and fix any problem that may be detected." Run as four parallel, independent audits
(`schema/`, `engine/`, `gui/`, and a fact-checking pass over every README/HISTORY.md claim against
the actual repository state) rather than one linear read-through -- each one reported concrete,
verifiable findings (file:line, concrete failure scenario, suggested fix), not style preferences.
Five real bugs were found and fixed; one more was investigated, understood, and DELIBERATELY left
unchanged because the "fix" was worse than the bug. Every fix below got its own new regression test.

**Real bugs, fixed:**

1. **`Scenario.validate()`'s `needs_sun` check omitted `comms_pointing`**
   (`schema/scenario.py`). The existing check already catches `power`/`station_keeping`/
   `enable_srp` needing a real sun ephemeris (`gravity.third_body_perturbers`) -- but
   `comms_pointing`'s own internal `sunSafePoint` chain needs exactly the same thing
   (`engine.fsw.build_simple_nav`'s `vehSunPntBdy` field is only populated when "sun" is
   SPICE-tracked) and was simply never added to the `any(...)` predicate. A `comms_pointing`
   scenario with no `power`/third-body sun validated cleanly and then silently Sun-pointed on a
   zero/garbage heading the moment it was actually run -- the exact failure mode this check
   exists to catch, just missing one case. Fixed by adding `comms_pointing` to the predicate;
   covered by a new `"comms_pointing"` case added to the existing parametrized
   `test_power_station_keeping_or_srp_{with,without}_sun_third_body_*` tests.
2. **`schema/references.py` never tracked `comms_pointing.target_ground_station`**. This
   module's whole job is backing "refuse delete if referenced" and "rename updates every
   reference atomically" for the GUI -- but `find_ground_station_references`/
   `rename_ground_station` only ever knew about `fsw_params['target_ground_station']`, never
   `comms_pointing`'s own reference to the same resource kind. A user could delete a ground
   station out from under a `comms_pointing` spacecraft with no warning, or rename one and leave
   `comms_pointing.target_ground_station` pointing at a name that no longer exists -- precisely
   the two guarantees this module's own docstring promises, both silently broken for this one
   field. Fixed by adding a `comms_pointing` case to both functions, mirroring the existing
   `fsw_params` handling exactly; two new tests (`test_comms_pointing_target_is_found`,
   `test_rename_ground_station_updates_comms_pointing_reference`).
3. **`engine.link_budget.link_margin_series` computed a margin for the WRONG ground station in
   a multi-ground-station scenario.** A `comms_pointing` spacecraft has exactly one antenna,
   committed to `comms_pointing.target_ground_station` -- but `link_margin_series` had no notion
   of which station that was, so `_extract_results()`'s own loop over every `ground_stations`
   entry would compute a plausible-looking, entirely fabricated margin for ANY station with
   `has_access=1` while the spacecraft was actively comms-pointing (gated on `active_mode`
   alone), using a pointing error that was really measured against the ACTUAL target, not that
   station. Fixed by threading a new `comms_pointing_target_ground_station` parameter through
   `link_margin_series()` (from `engine.service`'s own call site): when it's set and doesn't
   match the ground station being evaluated, the margin is now always `NaN` for that pair --
   there is no real link to a station the single antenna was never pointed at, geometric access
   notwithstanding. Two new tests confirm both the NaN case and that the real target's own
   gating is unaffected.
4. **`gui.mission_dashboard_widget`'s RF link panel ignored `active_mode` entirely** -- it
   computed and showed a full link-budget breakdown (EIRP, FSPL, C/N0, Eb/N0, a concrete margin
   number) gated on `has_access` alone, the exact same gap `engine.link_budget.
   link_margin_series()` itself had already been fixed to avoid (see its own docstring,
   "geometric visibility vs. actual RF link availability"). Concretely: with the Mode badge
   reading "Sun-pointing" (i.e. the antenna isn't pointed at the ground station AT ALL), the RF
   panel right next to it could still show "Link OK" with a specific margin in dB -- a fabricated
   number directly contradicting the badge beside it. Fixed by threading `is_comms_mode` into
   `_refresh_rf_link()` and adding it to the gating condition; when access exists but the mode
   hasn't switched yet, the badge now reads "Not yet comms-pointing" instead of either a fake
   breakdown or the equally-wrong "No access" (access DOES exist in that case -- pointing just
   hasn't caught up). New regression test:
   `test_real_access_without_mode_switch_shows_no_link_breakdown`.
5. **The same dashboard's `_find_ground_station` could silently pick the wrong station** for
   the RF panel in a multi-ground-station scenario (same root issue as #3, GUI side) -- it just
   returned the first `{gs}.access_to_{sc}.has_access` series found, with no preference for the
   spacecraft's own actual `comms_pointing.target_ground_station`. Fixed to prefer the
   configured target when a `Scenario` is available (and to return no station, rather than a
   wrong one, if that pairing wasn't actually recorded), falling back to the old "first found"
   behavior only when no `Scenario`/target is known.

**Investigated, NOT fixed -- the audit's own case for leaving something alone:**
`engine.fsw.build_comms_pointing`'s arbitrator is added to its task at the default (lowest)
priority, while `engine.service`'s own `comms_power_sink` (the thing the arbitrator drives) is
added at priority 50 (matching the panel/bus_sink convention, intentionally higher than
battery's 40 so the battery reads THIS tick's fresh power values). Since the sink runs before
the arbitrator within a tick, the battery's recorded comms-power draw lags the mode-switch
telemetry by one dynamics tick -- real, but negligible at this app's `dynamics_task_rate_s`
scale (seconds) against comms passes lasting minutes. The first attempted fix (raising the
arbitrator's own priority above 50) was checked by hand against Basilisk's own task-priority
semantics (confirmed in `sys_model_task.cpp`: higher priority runs first within a tick) and
found to introduce a WORSE bug: the arbitrator would then run before the two guidance chains it
reads from, feeding it one-tick-stale guidance every single tick instead of a one-tick-stale
power reading only on the power side. No single priority value satisfies both orderings given
the existing power-layer (40-100) vs. FSW-layer (-1) priority split this app already uses
throughout -- fixing this for real would mean restructuring that split, unverifiable without a
real Basilisk build. Reverted, and documented in `build_comms_pointing`'s own comment so the
tradeoff is visible to the next person who looks at this, rather than silently "fixed" with an
unverified change.

**README/docs pass**, verified against the actual repository rather than assumed: `README.md`'s
test-count claims (two places said 940, actual was 976 before these fixes' own +7 tests, now
983), its "Repository layout" tree (missing `mission_dashboard_widget.py`, `logging_setup.py`,
`tests/test_comms_pointing.py`, `tests/test_propellant_bookkeeping.py`,
`tests/gui/test_mission_dashboard_widget.py`, `tests/gui/test_feedback.py`, the six
`diagnostic_05*.json` files, `USER_MANUAL.md`, `docs/images/`, and four `packaging/` scripts that
exist but weren't listed), and its complete lack of any mention of the "Mission Dashboard" tab
anywhere (added to both "Running the GUI" and the "GUI & CLI" capability paragraph).
`scenarios/templates/README.md` still said "eighteen" templates in two places (now nineteen).
`packaging/README.md`'s own real, historical `.deb` build example showed `_1.0.0_` (true to what
was actually run at the time, left as a historical record per this file's own convention, but
annotated so it isn't mistaken for what `build_deb.sh` produces today, `_2.0.0_`). This file's
own immediately-preceding entry claimed "(up from 949/126)" -- a real number from an intermediate
point in that session's own work, but one this file never actually recorded anywhere, making it
unverifiable from the file's own text; corrected to reference this file's own last RECORDED
figure (940/126, the "Version 2.0.0" entry) instead, matching every other entry's own convention.

**Verification**: full suite re-run after every fix above, not just at the end --
`python3 -m pytest tests/ -q` -- 983 passed, 130 skipped, zero regressions (up from 976/130,
this file's own immediately-preceding entry). A headless `MainWindow` smoke test confirmed
template 19 still loads/round-trips through the Scenario Editor and the Mission Dashboard tab
still renders after all of the above. `scripts/_generate_templates.py` re-run and produced
byte-identical template JSON files (confirms none of the schema/engine fixes above touch
anything a template's own construction depends on).

---

## Results tab: "Save plot as PNG..." button

Direct request: "would be great to also have a button to save the plots as png images in a
desired location." Plotly's own modebar already has a built-in camera/download-as-png icon
(`config={"displaylogo": False}` in `results_widget.py` leaves it in), but inside an embedded
`QWebEngineView` that triggers Chromium's own download machinery, which this app never wires up
(`QWebEngineProfile.downloadRequested`) -- confirmed directly that clicking it does nothing
observable here, not assumed. A new "Save plot as PNG..." button next to the existing "Export
all series to CSV..." button fixes this with a proper native Save As dialog and a real file on
disk at the chosen path.

**Design**: renders the chart to a PNG CLIENT-SIDE via the SAME `plotly.js` already loaded on
the page (`Plotly.toImage()`), rather than pulling in a server-side renderer (the `kaleido`
package) this project doesn't otherwise depend on -- the same "no unnecessary dependency" choice
this module's own docstring already makes for `plotly.js` itself. `scale: 2` asks for a
higher-than-screen-resolution render at the chart's own current on-screen size.

**A real bug, caught before it shipped, not after**: the first implementation assumed
`QWebEnginePage.runJavaScript()` awaits a top-level returned `Promise` automatically (this is
genuinely true for some Qt WebEngine versions/configurations, which is presumably where that
assumption came from) and just returned `Plotly.toImage(...)`'s own Promise directly as the
script. Confirmed directly, NOT assumed, against this project's actual PySide6 6.11.2: it does
NOT await it -- the callback receives an empty string every single time, which looks exactly
like a render failure (both show up as "no valid PNG data") but isn't one. Caught by the
project's own "verify before committing" discipline: a quick isolated diagnostic script
(`new Promise((resolve) => resolve(42))` through the exact same `runJavaScript()` call) showed
the empty-string result BEFORE the feature's own real test was trusted, rather than assuming a
hanging/failing test meant the feature itself was broken. Fixed by polling a page-global
variable instead (`Plotly.toImage(...).then(url => { window.X = url; })`, then a `QTimer`
checking `window.X` every 100ms) -- confirmed directly to work (a 106 KB real PNG, resolved in
~200ms in practice). A second, related quirk found the same way: a bare JS `null`/`undefined`
also bridges back as an empty string here, not Python `None` as plain code might assume -- the
poll uses an explicit sentinel string (`"__spacemissionstudio_png_pending__"`) to tell "still
rendering" apart from a real (possibly falsy) result, rather than relying on that bridging.

**A second real race, also caught by actually running the test, not just writing it**: the
button's own enabled state is set synchronously inside `_redraw()`, right after kicking off
`QWebEngineView.setHtml()` -- but `setHtml()` itself loads and executes the page (including
`plotly.js` and the `Plotly.newPlot()` call that defines `window.Plotly`) ASYNCHRONOUSLY. An
ordinary human click is far slower than that load and never notices, but this project's own new
test for the feature -- calling `_on_save_plot_png()` immediately after `set_result()`, with no
wait -- hit it directly: `js: Uncaught ReferenceError: Plotly is not defined`. Fixed two ways:
the test now waits for a real `loadFinished` signal before clicking (`qtbot.waitSignal`,
matching realistic usage and making the test deterministic rather than racy), AND the production
kickoff script itself gained a short, near-zero-cost-in-the-common-case retry loop (up to 40
attempts, 50ms apart) that waits for `window.Plotly`/the chart element to exist before rendering
-- real defense-in-depth for the narrow case of an automated/very-fast click actually beating
the page load, not just a test-only workaround.

**Verification**: `tests/gui/test_results_widget.py` gained 5 new tests (a real end-to-end PNG
render with real PNG magic-byte verification, the `.png` extension auto-append, the no-result
no-op, and the cancelled-dialog no-op) -- all confirmed against the REAL offscreen
`QWebEngineView`/`plotly.js` pipeline in this sandbox, not mocked JS. One environment quirk
noted, not a regression from this feature: running `tests/gui/test_results_widget.py` ALONE
segfaults at Python interpreter teardown ("Release of profile requested but WebEnginePage still
not deleted") -- confirmed this already happens on the pre-existing 26 tests in that file with
zero changes from this feature, and that the full `tests/gui/` suite (517 passed, 2 skipped) and
the full `tests/` suite both exit cleanly (code 0) -- an isolated-single-file-run artifact of
this sandbox's Qt WebEngine teardown, not something seen running the suite normally. Full suite:
987 passed, 130 skipped, zero regressions (up from 983/130, the previous entry's own figure).

## Closed-off/offline policy: removing every runtime network call

**Real user requirement**: "the app must be completely closed off and offline, only exception is
the installation process." Before this change, SpaceMissionStudio had three runtime code paths
that could reach the network, none of them gated behind an opt-in flag -- this entry audits and
closes all three, plus a real gap discovered along the way.

**1. SPICE/gravity-harmonics/magnetic-field support data (`engine.kernels`)**. Basilisk's own
`supportDataTools.dataFetcher` (`pooch`-backed) fetches a file over the network the first time
`get_path()` is called for it and the local repo copy/cache doesn't already have it -- this was
previously left to happen lazily, on whatever run first needed a given file. A real pre-existing
gap found while auditing this: `DEFAULT_KERNELS` (what `ensure_kernels`/`require_kernels`
defaulted to) covered only the SPICE kernels (`naif0012.tls`, `de430.bsp`, `de-403-masses.tpc`,
`pck00010.tpc`) -- `DataFile.LocalGravData.GGM03S` (10th-degree spherical-harmonics gravity) and
`DataFile.MagneticFieldData.WMM` (the magnetometer model) were NOT pre-fetched by anything, so a
scenario using gravity harmonics or a magnetometer could still trigger an unreported runtime
fetch even before this directive. Fixed in two parts: `engine/kernels.py` now defines
`ALL_SUPPORT_DATA_FILES = DEFAULT_KERNELS + (GGM03S, WMM)` and both `ensure_kernels`/
`require_kernels` default to it instead of `DEFAULT_KERNELS`; and all four packaging installers
(`packaging/install.sh`, `packaging/install.ps1`, `packaging/deb/DEBIAN/postinst`,
`packaging/windows/bootstrap_env.ps1`) now call `engine.kernels.require_kernels()` once, right
after SpaceMissionStudio itself is installed into the venv (ordering matters: a first attempt in
`postinst` placed this call right after the Basilisk install step but BEFORE
spacemissionstudio's own install, which would have failed with `ModuleNotFoundError` -- caught by
re-reading the script's full line order before considering the edit done, and fixed by moving the
block after the spacemissionstudio wheel install). `install.sh`/`install.ps1` treat a failed
pre-fetch as non-fatal (a missing Basilisk wheel there is already optional); `postinst`/
`bootstrap_env.ps1` treat it as FATAL, since both of those always install a real Basilisk --
matching how each script already treats its own Basilisk/spacemissionstudio install steps. See
`packaging/README.md`'s own "Closed-off/offline policy" section for the per-script detail.
`build_spice_interface()`'s own `kernels` parameter default is UNCHANGED (`DEFAULT_KERNELS`) --
it's SPICE-specific by construction, not the general-purpose default this change touches.

**2. Space weather (`engine.spaceweather`)**. This module used to fetch live F10.7/Ap data from
CelesTrak as its DEFAULT `source` (`"celestrak"`), with a fallback chain to `local_file` then
`synthetic` if the fetch failed or didn't cover the scenario's date range. All of that -- the
`fetch()` function, `CELESTRAK_URLS`, the `urllib.request`/`urllib.error` imports, the
fetch-then-fallback chain in `resolve()`, and the `"celestrak"` branch in
`_resolve_conservative()` -- has been REMOVED entirely, not just defaulted away from. `source` is
now `"local_file"` or `"synthetic"` (the new default) only; anything else, including
`"celestrak"`, raises `SpaceWeatherError` as an unknown source. The `activity_level="conservative"`
worst-case-percentile margin (computed from REAL historical F10.7/Ap data -- never the synthetic
generator, which is fabricated) is now `local_file`-only for the same reason: there is no more
automatic way to obtain that real historical data inside the app. A real, deliberate honesty
check was run before accepting this trade-off: could a real historical CSV just be bundled with
the app instead, to preserve the conservative-margin feature's full value without ANY runtime
fetch? A direct `curl` against `celestrak.org` from this sandbox confirmed it is genuinely
blocked (403) and no stale cached copy exists anywhere in this checkout to fall back on -- so
rather than fabricate or guess a "real historical" file, the honest choice was to reduce this
specific capability and say so plainly, not paper over it.

**Ripple effects, all fixed**: `tests/test_spaceweather.py` had its CelesTrak-specific tests
(`test_resolve_celestrak_falls_back_when_unreachable_or_insufficient`,
`test_fetch_sends_a_browser_like_user_agent`) replaced with
`test_resolve_celestrak_source_is_rejected_as_unknown` and `test_module_has_no_fetch_function`
(asserts `spaceweather.fetch`/`spaceweather.urllib` don't even exist any more). The five bundled
templates that defaulted to `_conservative_drag_margin()` (`scripts/_generate_templates.py`: 04
Walker constellation, 05 formation-flying phasing, 07 ADCS hardware, 08 mission-sequence orbit
raise, 18 LEO station-keeping) now use `activity_level="nominal", source="synthetic"` instead of
`source="celestrak", activity_level="conservative"` -- each template's own `description` field was
rewritten to explain the change and how to restore the real-historical-data margin (set
`space_weather.source="local_file"`, `activity_level="conservative"`, `local_file_path=<your own
downloaded CelesTrak CSV>` in the Scenario Editor). All 19 templates were regenerated via
`scripts/_generate_templates.py` -- every one of them had `"source": "celestrak"` serialized into
its JSON (the OLD schema default), which would otherwise have failed `Scenario.validate()`'s
source-whitelist check the moment this schema change landed. The six hand-maintained
`diagnostic_05*.json` fixtures and `two_body_validation.json` (not produced by
`_generate_templates.py`) had the same stale `"source": "celestrak"` fixed by hand (a plain
`"source": "synthetic"` substitution -- these files set no other space-weather fields, so no
further changes were needed) and re-validated via `load_scenario()` + `.validate()`.
`gui/propagation_setup_dialog.py`'s `space_weather_source_combo` dropped the `"celestrak"` entry
(now just `["synthetic", "local_file"]`), and its tooltips/docstring were reworded to match.

**3. Vizard auto-download (`gui.vizard_launcher`, `gui.main_window`)**. `fetch_vizard()` (plus its
`VizardFetchError`, `_DOWNLOAD_URLS` table pointing at `hanspeterschaub.info`, zip-slip-guarded
extraction, and `VizardFetchWorker` QThread wrapper) and the "Download Vizard" button that drove
it from `MainWindow.on_launch_vizard()`'s "Vizard not found" dialog have been removed entirely.
Vizard is a separate, user-installed Unity application, not something this app's own install step
can pre-fetch the way `engine.kernels` does for SPICE/support data (there's no single guaranteed
install location, and the installers above only run once, at install time, not whenever Vizard
happens to be missing). The "Vizard not found" dialog now offers only its original **Browse...**
option; `docs/source/Vizard/VizardDownload.rst`'s published links are still there for a human to
follow manually, same as before this feature ever existed. `tests/gui/test_vizard_launcher.py`
lost its entire "fetch_vizard()" test section (previously unverifiable end-to-end in this sandbox
anyway, per that module's own docstring -- `hanspeterschaub.info` was blocked here); the path
-lookup/persistence/process-launch tests it opened with are unaffected and still pass.
`tests/gui/test_main_window.py` lost its `_FakeVizardFetchWorker` class and the two
`_fetch_vizard_with_progress` tests it supported; `_locate_or_fetch_vizard` was renamed to
`_locate_vizard` throughout (it no longer offers a download branch, so the old name was no longer
accurate) and its remaining browse/cancel/dismiss tests updated to match the single-button dialog.

**Re-verified**: a project-wide re-grep for `import urllib`/`import requests`/`import socket`/
`import ftplib`/`urlopen(` across `spacemissionstudio/` (excluding `build/`) turned up zero
matches after this change -- the ONLY `http://`/`https://` literal left anywhere in the package is
a docstring pointer in `engine/spaceweather.py` telling a USER where to manually download a
CelesTrak CSV themselves, never code that fetches it.

**Verification**: full suite re-run after every change above, not just at the end.
`tests/test_spaceweather.py`: 22 passed. `tests/test_scenario_templates.py`: 90 passed (all 19
regenerated templates round-trip and validate). The six diagnostic fixtures +
`two_body_validation.json` re-validated individually via `load_scenario()`/`.validate()` after the
hand-edit. `tests/gui/test_propagation_setup_dialog.py`: 20 passed. `tests/gui/
test_vizard_launcher.py`: 11 passed (down from its pre-change count, entirely from removing the
fetch-only tests, zero regressions in what remains). `tests/gui/test_main_window.py`: 75 passed.
Full suite with `QT_QPA_PLATFORM=offscreen`: 968 passed, 130 skipped, zero regressions (the drop
from 987 to 968 passed is entirely the removed fetch_vizard/VizardFetchWorker/CelesTrak-fallback
tests described above, not a loss of coverage on anything that still exists).

## Relaxing the offline policy: a consent-gated startup fetch/update prompt

**Real user follow-up, immediately after the previous entry's fully-offline change**: "A one time
fetch during each startup of the app is also allowed, to store everything that is needed locally
so it can be used later again. But the user always should be asked if they want to fetch/update."
This doesn't undo the previous entry's core principle (SpaceMissionStudio never fetches anything
*silently*) -- it adds one specific, narrow exception: a consent prompt, shown once each GUI
startup, that CAN fetch real data if the user explicitly agrees, every single time.

**New: `gui/startup_fetch_dialog.py`**. `StartupFetchDialog` -- two independent checkboxes (both
checked by default), "Fetch now"/"Skip" buttons, never auto-accepting. `maybe_run_startup_fetch()`
shows it, and only on "Fetch now" (with at least one item still checked) runs
`StartupFetchWorker` -- a background `QThread` (same cooperative pattern as
`gui.kernel_status_widget`'s `_KernelFetchWorker`) that calls `engine.kernels.ensure_kernels()`
and/or `engine.spaceweather.fetch(dataset="SW-All", force=True)` for whichever item(s) were
checked -- behind a progress dialog, then shows a one-line-per-item summary. Clicking "Skip",
dismissing the dialog, or unchecking both items touches no network at all, identical to before
this file existed. Wired into `gui.main_window.MainWindow` via a new `prompt_startup_fetch: bool =
True` constructor parameter and `QTimer.singleShot(0, ...)` (fires once the window has actually
rendered, not before) -- `tests/gui/test_main_window.py`'s own `window` fixture passes
`prompt_startup_fetch=False` so none of its 75+ tests hang on an unanswered modal dialog.

**`engine/spaceweather.py`: `fetch()`/`CELESTRAK_URLS`/`cached_fetch_path()` restored, deliberately
NOT wired back into `resolve()`**. The previous entry deleted `fetch()` entirely on the theory that
CelesTrak access was gone for good; this entry restores it verbatim (same CelesTrak URLs,
User-Agent fix, cache-hit-unless-`force`-set behavior) as a plain utility function, callable only
by `gui.startup_fetch_dialog`'s consent-gated worker. Deliberately did NOT re-add `"celestrak"` as
a valid `SpaceWeatherConfig.source` value: that would let a scenario's own config silently trigger
a network fetch the moment it's RUN, which is not what was asked for ("during startup", not
"during a run") and would reintroduce exactly the implicit-fetch behavior the previous entry
removed. `resolve()` itself is unchanged -- still only `"local_file"`/`"synthetic"`, still never
touches the network -- and a new `test_resolve_never_calls_fetch` test (monkeypatches `sw.fetch`
to raise `AssertionError` if called, then exercises both valid sources) makes that a guarded
invariant, not just a comment. New `cached_fetch_path()` is a pure, no-network existence check
(not a second fetch path) that lets GUI code offer an already-fetched CSV without re-downloading.

**`gui/vizard_launcher.py`/`gui/main_window.py`: `fetch_vizard()`/`VizardFetchWorker`/"Download
Vizard" restored verbatim** from before the previous entry removed them. Unlike the space-weather
fetch, this one was never wired to the startup prompt at all -- it's reached only via an explicit
click on the "Download Vizard" button in the "Vizard not found" dialog (Run menu's Launch Vizard),
which already satisfies "always ask first" on its own; cramming an unrelated external application
into a startup checklist nobody asked to see every single time would be nagging, not a convenience
for a capability most sessions never need. `_locate_vizard` (renamed back from the previous
entry's rename) offers both "Download Vizard" and "Browse..." again; `_fetch_vizard_with_progress`
(the blocking-`QEventLoop`-behind-a-progress-dialog pattern) is back too.

**A real, deliberate design decision**: a successful startup space-weather fetch produces an
ordinary local CSV -- fetching it is worthless if nothing then uses it. `gui/
propagation_setup_dialog.py`'s Local file field now pre-fills with `engine.spaceweather
.cached_fetch_path()`'s result when the scenario doesn't already have its own `local_file_path`
set (never overriding an explicit one) -- a pure, no-network read of whether a previous fetch left
a file on disk, not a second trigger for anything.

**Verification**: `tests/test_spaceweather.py` gained `test_resolve_never_calls_fetch` plus 7 new
`fetch()`/`cached_fetch_path()` tests (download+cache, cache-hit-without-force,
force-redownloads, unknown dataset, network failure, and the two `cached_fetch_path` cases) -- all
mocking `urllib.request.urlopen`, same convention as the restored `tests/gui/
test_vizard_launcher.py` fetch tests (27 tests, reconstructed to cover the same ground as before:
download+extract+find, User-Agent header, executable-bit, network/corrupt-zip/no-executable/
cancellation/size-cap/zip-slip failures, progress callback, same-named-wrapper-folder and
stale-extraction-clearing behavior, plus the `VizardFetchWorker` thread wrapper's three signals).
`tests/gui/test_main_window.py` gained back its Download-Vizard-button and
`_fetch_vizard_with_progress` tests (77 passed total). New `tests/gui/test_startup_fetch_dialog.py`
(11 tests: dialog defaults/selection, Skip/both-unchecked no-ops, a successful/failed summary, and
the worker's own `_fetch_kernels`/`_fetch_space_weather` methods -- the missing-Basilisk case
exercised for real, this sandbox genuinely having none, same as `test_kernel_status_widget.py`'s
own equivalent test). `tests/gui/test_propagation_setup_dialog.py` gained 3 tests for the new
pre-fill behavior (fills when empty and a cache exists, never overrides an explicit path, stays
empty with nothing cached). Full suite: 1007 passed, 130 skipped, zero regressions.

## Comprehensive audit of the two offline-policy entries above

Real user request: "a complete and comprehensive audit and review of everything." Ran this
project's own `/code-review --level max` against the full `origin/develop...HEAD` diff (49 files,
the two entries above). Three findings came back; all investigated, one deliberately not
actioned, two were real bugs, fixed and regression-tested.

**1. CRITICAL, fixed: no schema migration for the removed `"celestrak"` source.** The first entry
above removed `"celestrak"` as a valid `SpaceWeatherConfig.source` value -- but `"celestrak"` was
also the OLD (v1) schema default, so essentially every scenario file ever saved by a previous
version of this tool has it. With no migration, `CURRENT_SCHEMA_VERSION` still at 1, every such
file would fail `Scenario.validate()` the moment anyone tried to open it again -- a real backward
-compatibility break this project's own `migrations.py` docstring explicitly warns against ("a
change... that would break older files... requires a migration"). Fixed properly: bumped
`CURRENT_SCHEMA_VERSION` to 2, added `migrations._migrate_1_to_2()` (rewrites
`space_weather.source == "celestrak"` to `"synthetic"`, and downgrades `activity_level` from
`"conservative"` to `"nominal"` when it was paired with the old `"celestrak"` source, since
`"conservative"` is now `"local_file"`-only and migrating only `source` would otherwise still
leave a file that loads fine but fails at RUN time with no schema-level warning). Regenerated all
19 bundled templates (bumps each to `schema_version: 2`, a clean 1-line diff per file) and bumped
the 7 hand-maintained diagnostic/`two_body_validation.json` fixtures the same way, by hand -- not
produced by the generator. New `tests/test_migrations.py` (9 tests: version bump, both
celestrak-rewrite cases, both pass-through cases, the no-space-weather-block edge case, two real
`load_scenario()` end-to-end regression tests, and the "no migration registered" error path).
Fixed `test_saved_file_is_plain_readable_json`'s hardcoded `== 1` assertion to use
`CURRENT_SCHEMA_VERSION` instead, so it won't go stale at the next version bump either.

**2. REAL bug, fixed: an orphaned QTimer could spam duplicate "Plot saved" dialogs forever.**
Confirmed by reasoning through the exact sequence (then verified by literally reverting the fix
and watching a new regression test fail): `gui.results_widget.ResultsWidget._redraw()` -- called
repeatedly by `set_live_result()` while a run streams in -- unconditionally re-enabled
`save_png_button` even while an earlier "Save plot as PNG..." click's async poll
(`self._png_poll_state`, a `QTimer` polling a page-global JS variable for `Plotly.toImage()`'s
result) was still in flight. A second click during that window started a SECOND, independent
`QTimer`/poll while overwriting the ONE shared `self._png_poll_state` the two polls both read --
orphaning the first `QTimer` (nothing held a reference to stop it specifically; `state["timer"]`
only ever pointed at whichever poll started MOST recently). That orphaned timer never got told to
stop, so it kept firing every 100ms indefinitely, each time re-reading the (by-then-resolved,
unchanging) JS result variable and re-triggering `_on_plot_png_rendered()` -- a duplicate file
write plus a duplicate "Plot saved" `QMessageBox.information()` dialog, forever, long after the
user thought they were done. Fixed three ways: (a) `_on_save_plot_png()` gained an explicit
re-entrancy guard (`if self._png_poll_state is not None: return`), matching
`gui.kernel_status_widget.KernelStatusWidget.refresh()`'s own established convention; (b)
`_redraw()` no longer force-enables the button while a poll is in flight; (c) `_poll_plot_png()`
now resets `self._png_poll_state = None` on EVERY completion path (success, render error, AND the
timeout path, which never did this before either), so the guard in (a) can't become permanent and
block all future saves. **Verified the regression test actually catches the bug**: reverted fix
(a) alone, watched `test_redraw_does_not_reenable_save_button_while_a_png_poll_is_in_flight` fail
with a real assertion error, restored the fix, watched it pass again -- not just "added a test
that happens to pass." Two more new tests cover the re-entrancy guard itself and that
`self._png_poll_state` correctly resets to allow a later, legitimate save.

**3. Investigated, NOT fixed -- a release-note-snippet process question with a clear answer.** The
review flagged that this PR's validation/packaging changes should, per `AGENTS.md` rule 7 and
`docs/source/Support/bskReleaseNotesSnippets/README.md`'s literal text, get a snippet file.
Checked the actual precedent first: `git log --diff-filter=A -- docs/source/Support/
bskReleaseNotesSnippets/` across this repo's ENTIRE history shows every snippet ever added was for
a real upstream Basilisk core-engine PR (real AVSLab/basilisk issue numbers like `#282`/`#1592`)
-- zero SpaceMissionStudio commits, across dozens of PRs over this project's whole history, have
ever added one. SpaceMissionStudio is a self-contained sub-application that already maintains its
own changelog discipline (`HISTORY.md`, kept current with every change, including both entries
this audit covers) -- adding a snippet here would be inconsistent with every prior PR's own
established practice, not a gap this one PR introduced. Left alone.

**A second, related hardening pass, found while re-reading the new feature's own worker code** (not
from the code-review findings above, but the same kind of "what happens on an unexpected failure"
question #2 raised): `gui.startup_fetch_dialog.maybe_run_startup_fetch()` blocks inside a
`QEventLoop` behind a progress dialog with deliberately NO cancel button, waiting for
`StartupFetchWorker.finished_all` to fire. `_fetch_kernels()`/`_fetch_space_weather()` only caught
their OWN specific expected failure types -- anything else (e.g. `engine.spaceweather.fetch()`'s
own `tmp.write_bytes()`/`tmp.replace()`/`cache_dir.mkdir()` steps, which were NOT wrapped in the
network try/except at all, raising a raw `OSError` on a full or read-only disk) would propagate
uncaught out of the `QThread`'s `run()`, `finished_all` would never fire, and that `QEventLoop`
would hang FOREVER with no way for the user to dismiss it. Fixed two layers deep: `run()` itself
now wraps both helper calls in a broad `except Exception`, matching
`gui.kernel_status_widget._KernelFetchWorker`'s own established "this signal must always fire"
convention, so `finished_all` is a genuine guarantee rather than something that merely held for
the failure modes anticipated so far; and `engine.spaceweather.fetch()` now wraps its
`mkdir()`/`write_bytes()`/`replace()` calls in their own `try`/`except OSError`, converting to the
same `SpaceWeatherError` every other failure in that function already reports (a full/read-only
disk is just as much a "this fetch did not succeed" case as a network failure). **Verified the new
`test_worker_run_always_emits_even_if_a_helper_raises_unexpectedly` test actually catches this**:
reverted the `run()` fix, watched the test hit pytest-qt's own `TimeoutError` waiting on a signal
that never came (the real hang, reproduced, not simulated), restored the fix, watched it pass.
Two new `engine.spaceweather.fetch()` tests cover the disk-write and cache-dir-creation failure
paths directly; two more on the GUI side cover `StartupFetchWorker.run()`'s own guarantee and
`maybe_run_startup_fetch()`'s summary message for this new "error" outcome key.

**Verification**: full suite re-run after every fix above, not just at the end.
`tests/test_migrations.py`: 9 passed (new file). `tests/test_scenario_schema.py`: all passed with
the corrected assertion. All 26 bundled/hand-maintained scenario files re-validated individually
at `schema_version: 2` via `load_scenario()`/`.validate()` after the hand-edits.
`tests/gui/test_results_widget.py`: 33 passed (30 + 3 new). `tests/test_spaceweather.py`: 31
passed (29 + 2 new). `tests/gui/test_startup_fetch_dialog.py`: 13 passed (11 + 2 new). Full suite
with `QT_QPA_PLATFORM=offscreen`: 1023 passed, 130 skipped, zero regressions (up from 1007/130).

## Real user-reported crash: ground station + Vizard both enabled

**Real user report** (a traceback from their own machine, where a real Basilisk build and real
cached SPICE kernels both exist -- something this development sandbox has never had): every run
with a ground station AND Vizard output configured crashed inside
`engine.vizard.enable_vizard()`'s ground-station loop:

```
TypeError: only 0-dimensional arrays can be converted to Python scalars
SystemError: <built-in function LocationPbMsg_gHat_P_set> returned a result with an exception set
```

**Root cause, confirmed directly against a real Basilisk build, not reasoned about in the
abstract**: this development sandbox doesn't have cached SPICE kernels either (naif.jpl.nasa.gov
is blocked here, same already-documented gap as always), but it DOES have a real Basilisk install
in a throwaway venv (`/tmp/bsk_venv4`, used earlier this session to verify the offline-policy
PNG/startup-fetch work) -- `pip install -e .` into it and reproducing the EXACT reported traceback
took one Python one-liner, not a guess:
`groundLocation.GroundLocation.r_LP_P_Init` (a real Basilisk `Eigen::Vector3d`) is exposed to
Python as a NESTED `[[x], [y], [z]]` list, confirmed directly, never a flat `[x, y, z]` one.
`enable_vizard()`'s ground-station loop passed it to `vizSupport.addLocation()` via a plain
`list(gs.r_LP_P_Init)` call, which leaves that nesting untouched. `addLocation()` itself tolerates
the nested `r_GP_P` shape fine (its own setter apparently squeezes it) -- but since this call
never passes its own `gHat_P`, `addLocation()` computes one internally as `r_GP_P /
np.linalg.norm(r_GP_P)`; fed the STILL-nested `r_GP_P`, that division produces a genuinely
(3, 1)-shaped numpy array instead of a flat (3,) one, and THAT shape is what breaks `gHat_P`'s own
setter, which tries to convert each of the 3 "rows" to a scalar and chokes on each being itself a
1-element sub-array (`TypeError: only 0-dimensional arrays can be converted to Python scalars`,
surfacing through SWIG's generic exception-forwarding as the `SystemError` above).

**The fix**: `simHelpers.EigenVector3d2list()` instead of bare `list()` -- the exact conversion
every real Basilisk example that passes a `GroundLocation`'s own `r_LP_P_Init` to `addLocation()`
already uses (`examples/scenarioAttLocPoint.py`, `examples/scenarioGroundDownlink.py`,
`examples/scenarioGroundLocationImaging.py`, `examples/scenarioSpacecraftLocation.py`,
`examples/scenarioStripImaging.py` -- confirmed by grepping every real `addLocation` call site in
this checkout's own `examples/`, not just one). A project-wide re-grep for the same `list(...)`
-on-a-Basilisk-vector pattern elsewhere in `engine/` turned up nothing else at risk.

**Verified end-to-end against the real Basilisk build, both directions**: confirmed the OLD code
(via `git stash`) reproduces the user's EXACT traceback (same `SystemError`, same inner
`TypeError`, same shape -- `array([[-0.20...], [-0.74...], [0.64...]])`, a genuine (3, 1)); then
confirmed the fix resolves it. New `tests/test_vizard.py::test_enable_vizard_with_a_ground_station_
does_not_crash` calls `engine.vizard.enable_vizard()` directly against a real
`groundLocation.GroundLocation`/`vizInterface.VizInterface` pair, deliberately NOT through
`SimulationService.build()` (which would need the SPICE kernels this sandbox still can't fetch --
a real, separate, already-documented gap this bug has nothing to do with) -- the ground-station/
Vizard wiring needs no SPICE at all, so this test genuinely runs and passes against the real
Basilisk build in `/tmp/bsk_venv4`, not just a reasoned-through fix. Reverted the fix one more
time with this new test in place and watched it fail with the identical traceback, then restored
it and watched it pass -- the same "prove the regression test actually catches the bug" discipline
as the two fixes in the entry above.

**Verification**: `tests/test_vizard.py` (3 tests, one new): the 2 pre-existing SPICE-dependent
tests fail in THIS sandbox with exactly the already-documented, unrelated `KernelError` (SPICE
kernels can't be fetched here) -- raised inside `service.build()` well BEFORE it ever reaches the
ground-station/Vizard code this fix touches, so not a regression this change could have caused;
the new ground-station test, which needs no SPICE at all, passes cleanly against the real
Basilisk build. Full non-Basilisk suite with `QT_QPA_PLATFORM=offscreen`: 1023 passed, 131 skipped
(+1 for the new Basilisk-marked test, correctly skipped in the main sandbox venv that has no
Basilisk at all), zero regressions.

---

## Templates: Sun-synchronous (10:30 LTAN) orbits and a Berlin ground station

**Direct user request**, part of a 5-item feedback list after a real run on their own machine:
"All example/template scenarios shall be, where it makes sense, SSO (10:30 AM) orbits and
baseline groundstation shall be in Berlin, Germany, wherever applicable."

**Derived, not guessed, and verified against two independent references.** Two new helpers in
`scripts/_generate_templates.py`:

* `sun_synchronous_inclination_deg(semi_major_axis_km, eccentricity=0.0)` solves the standard
  first-order J2 secular RAAN-rate equation (Vallado, *Fundamentals of Astrodynamics and
  Applications*: `dRAAN/dt = -1.5 * n * J2 * (Req/p)^2 * cos(i)`, `n = sqrt(mu/a^3)`,
  `p = a*(1-e^2)`) for the inclination whose nodal regression exactly matches the Sun's own mean
  motion (360 deg / tropical year) -- the defining property of a Sun-synchronous orbit. `J2`,
  `Req`, and `mu` were read directly off a real installed Basilisk build (`/tmp/bsk_venv4`:
  `orbitalMotion.J2_EARTH = 0.001082616`, `gravBodyFactory().createEarth().radEquator =
  6378136.6` m, `.mu = 398600436000000.0` m^3/s^2), not assumed. Verified against this project's
  own pre-existing, independently hand-picked reference value: evaluates to 97.40 deg at a
  6878.1366 km semi-major axis (500 km circular altitude), matching
  `engine.spacecraft_templates._placeholder_orbit()`'s own `inclination_deg=97.4  # sun
  -synchronous at ~500 km` comment exactly.
* `raan_for_ltan_deg(epoch_utc, ltan_hour=10.5)` computes the RAAN that places the ascending node
  at the requested local time of ascending node (LTAN), via the standard relation
  `RAAN = RA_sun + 15 deg/hr * (LTAN - 12h)`, using the Astronomical Almanac's own "low precision
  formula for the Sun" (accurate to about 0.01 deg through 2050) for the Sun's real right
  ascension at the scenario's epoch. Verified against known Sun RA values at the equinoxes/
  solstices (0h at the vernal equinox, ~90 deg at the summer solstice, ~180 deg at the autumnal
  equinox) before being trusted in any template. Default LTAN is 10:30 (the user's own stated
  value); both helpers round to 2 decimal places -- real orbit-insertion dispersion and the
  first-order J2-only model both dwarf anything past that precision, and it keeps every value
  exactly representable by the Customize wizard's existing 2-decimal spin boxes (a round-trip
  test with the full, unrounded value caught this: `test_every_spec_round_trips_with_no_edits`
  failed on template 01 with `97.03 != 97.0296092274072` until the rounding was added at the
  source).
* `_berlin_ground_station(**overrides)` returns a `GroundStationConfig` for Berlin, Germany
  (city-center reference: Alexanderplatz, 52.5200 N, 13.4050 E, ~34 m above the WGS84 ellipsoid),
  the new baseline ground station for every template that has one.

**Applied to every template where it makes sense, and deliberately NOT to the rest** -- each
exclusion has its own reason, not a blanket skip:

* **Changed** (11 of 19): `01` (two-body circular orbit), `05` (formation flying/phasing, both
  spacecraft), `06`/`07` (attitude pointing, basic and with ADCS hardware), `08` (mission
  sequence/orbit raise), `09` (Monte Carlo dispersion), `10` (gravity-gradient torque), `12`
  (RW momentum dumping), `15` (celestial body pointing), `18` (LEO station-keeping), and `19`
  (Sun-pointing + comms link, which also gets the ground-station rename: `boulder-gs` ->
  `berlin-gs` throughout its description text, `gui/template_wizard.py`'s matching wizard-page
  intro text, and `scenarios/templates/README.md`'s catalog row).
* **Not changed, each for a template-specific physical/pedagogical reason**: `02` (elliptical
  orbit) and `03` (GEO station-keeping) are about perturbation/stationkeeping effects that have
  nothing to do with LTAN and GEO can't be Sun-synchronous at all; `04` (Walker constellation)
  is about relative-phasing geometry, not absolute LTAN; `11` (thruster attitude control) and
  `17` (fuel tank depletion) are deliberately kept as the two exceptions to the separate "never
  use thrusters for attitude control" item in the same feedback list -- their entire teaching
  purpose IS thruster-based ADCS, confirmed with the user before proceeding; `13` (magnetic
  torque rod) and `14` (CSS Sun-heading estimation) depend on their current orbit/attitude
  geometry for their own specific demonstration (geomagnetic field direction, Sun-vector
  estimation geometry) in ways re-deriving the orbit risked silently breaking; `16` (Lambert
  transfer) is a two-point boundary-value transfer problem, not an operational orbit.

**Verification**: all 19 regenerated templates reload and `Scenario.validate()` cleanly; full
non-Basilisk suite with `QT_QPA_PLATFORM=offscreen`: 1026 passed, 131 skipped, zero regressions
(including `tests/gui/test_template_wizard.py`'s own prefill/round-trip tests, parametrized over
every template, which is what caught the rounding issue above before it shipped).

---

## Mission Dashboard telemetry, also in Vizard

**Direct user request**, item 3 of the same 5-item feedback list as the two entries above: "the
mission panel live stream shall also be in the vizard live visualization, not only in the GUI
itself" -- referring to `gui.mission_dashboard_widget.MissionDashboardWidget`, template 19's
live readout of a `comms_pointing` spacecraft's operating mode, pointing error, and RF link
status (battery/power was already covered: the existing, generic "Battery" `GenericStorage`
panel fires for any spacecraft with `PowerConfig` set, independent of `comms_pointing`).

**What was added, all sourced directly from `engine.fsw.build_comms_pointing`'s own arbitrator
-- no second computation, no new bridge `SysModel`** (unlike ground-station access, which needed
one because `groundLocation.GroundLocation` itself has no "mode" concept; this arbitrator
already IS the live source of all three states, for its own reasons, every tick):

* `_CommsPointingArbitrator` (`engine/fsw.py`) now also publishes `modeCmdOutMsg`
  (`DeviceCmdMsgPayload`, the same 0/2 convention the pre-existing ground-station-access
  `GenericSensor` bridge already uses) and `pointingErrorOutMsg` (`DataStorageStatusMsgPayload`,
  `storageLevel`/`storageCapacity` = `theta_deg`/180 deg) every tick, from the exact same
  `hasAccess`/`sigma_BR` values it already reads to do the mode switch itself -- no new geometry,
  no re-derivation.
* A third message, `linkStatusCmdOutMsg`, needed a real link-margin number to gate on. Rather
  than re-implement that math, the arbitrator now optionally takes the spacecraft's own
  `schema.scenario.RFLinkConfig` and the target ground station's `GroundStationConfig` (wired
  from `engine.service.py`'s own comms_pointing pass, which already has both in scope) and calls
  `engine.link_budget.link_margin_db` -- the SAME pure-Python function
  `gui.mission_dashboard_widget` and `engine.link_budget.link_margin_series` already use for
  their own numbers, with the SAME gating (real access AND actually comms-pointing, never
  geometric visibility alone) -- so Vizard's badge and the GUI's detailed dB breakdown can never
  silently disagree about whether the link is "up". `engine/fsw.py` picking up a `from . import
  link_budget` (a plain Python import, no new Basilisk dependency: `link_budget.py` has never
  had one) was the only new coupling needed.
* `engine.vizard.enable_vizard()` gained a `comms_pointing_by_spacecraft` parameter (same shape
  as the existing `battery_by_spacecraft`/`station_keeping_by_spacecraft` dicts) and, per
  spacecraft with one, builds a "Pointing Error" `GenericStorage` bar plus "Mode"/"Link status"
  `GenericSensor` badges, reading straight off the three messages above.
* **Deliberately a colored status badge for link status, not a numeric margin bar**: a real
  margin can be negative (a degraded link is exactly the state worth seeing), and
  `GenericStorage` has no non-negative-only workaround that doesn't lose the sign -- see this
  file's own "Real bug found from a real running Vizard screenshot, FOURTH round" entry above for
  why that was already tried and reverted once for the RTN separation panels, and `README.md`'s
  own "Scoped but not yet built" note (now updated) for why a live NUMERIC link-margin gauge
  stays a known, deliberate gap. Pointing error, by contrast, is a plain non-negative angle by
  construction (`theta_deg = 4*atan(|sigma_BR|)`, always >= 0) and so gets an ordinary
  `GenericStorage` bar with no such risk.

**Verified directly against a real Basilisk build** (`/tmp/bsk_venv4`, this checkout installed
editable into it), not just reasoned through: four new tests in `tests/test_comms_pointing.py`
confirm `modeCmdOutMsg` mirrors `modeLog` in the 0/2 convention, `pointingErrorOutMsg` matches
`pointingErrorDegLog` exactly with `storageCapacity` always 180, `linkStatusCmdOutMsg` stays "no
link" when no `rf_link`/ground-station config is given (matching
`gui.mission_dashboard_widget`'s own fallback), and -- using a real close-range/far-range pair
independently confirmed via `engine.link_budget.link_margin_db` itself to close/not-close the
link -- that the badge tracks the real margin's sign exactly, including staying "no link" during
real access that hasn't yet become actual comms-pointing. One new test in `tests/test_vizard.py`
exercises `enable_vizard()`'s new `comms_pointing_by_spacecraft` wiring directly (the same
SPICE-free, bare-`SimulationBaseClass` pattern this file's own ground-station-access test uses)
and confirms all three new panels actually land in the lists handed to
`vizSupport.enableUnityVisualization()`. All pass against the real build; the pre-existing,
unrelated `nodePowerOut`/SPICE-kernel-network failures already documented elsewhere in this file
are unchanged by this work (confirmed identical via `git stash` before/after). Full non-Basilisk
suite: 1026 passed, 136 skipped (+5 for the new `requires_basilisk` tests, correctly skipped
here), zero regressions.

---

## GUI beginner-friendliness pass: tooltips explaining every setting's real-world effect

**Direct user request**, item 5 of the same 5-item feedback list as the three entries above: "The
GUI shall be more user friendly. Particularly for beginners, they shall be guided through each
step and get explanations of everything... They have to know what outcomes their actions have.
They need to understand what they are doing in each step."

**Audit first, not a blind sweep**: grepped every `gui/*.py` file for existing `setToolTip`
coverage before touching anything. Several files already had the explanatory discipline this
request asks for -- `gui/load_scenario_widget.py`'s template picker (an intro label, a live
description of the selected template, a "Customize wizard" tooltip), `gui/sensor_actuator_editor.py`'s
per-kind `_hint_text()` (every sensor/actuator kind's required/optional params, with units, shown
live as a label), `gui/spacecraft_editor.py`'s FSW-mode/control-gains hint labels, and
`gui/results_widget.py`'s series/x-axis pickers -- left alone rather than padded with redundant
tooltips. The real gaps were the dense, numeric-field-heavy editors with little or no explanatory
text at all: `gui/orbit_ic_widget.py` (zero tooltips -- every orbital element was a bare label +
unit, no explanation of what it means or what changing it does), and `gui/spacecraft_editor.py`'s
power/station-keeping/constant-thrust/phasing-keeping/momentum-management/fuel-tank/RF-link
groups, `gui/propagation_setup_dialog.py`'s gravity/integrator/space-weather fields, and
`gui/ground_station_editor.py`/`gui/monte_carlo_editor.py`/`gui/mission_sequence_editor.py`'s own
fields (2-4 tooltips each in files with dozens of controls).

**What was added**: a `setToolTip()` on every numeric field, combo box, and checkable group box
in those files that didn't already have one -- not a generic "set this value" placeholder, but
the real physical/behavioral meaning and, per the user's own explicit ask, the OUTCOME of
changing it (e.g. the inclination field doesn't just say "tilt of the orbit" -- it says what
0/90/~97-98 deg each physically mean; the "Enable atmospheric drag" checkbox says it's the
dominant force shrinking a LEO orbit and that nothing happens below ~800-1000 km; the station
-keeping deadband field explains the frequency/size trade-off of narrowing or widening it). Every
explanation was checked against this project's own `schema/scenario.py` docstrings (already the
authoritative, unit-annotated source for what each field does) rather than written from memory,
and against the actual engine behavior for anything non-obvious (e.g. `main_window.py`'s "Run
Simulation" tooltip naming the Scenario tab's validity indicator was checked against
`scenario_editor.py`'s real `validation_label` placement, not assumed).

**A real interaction bug caught before it shipped**: `propagation_setup_dialog.py`'s
`enable_harmonics_check` already had its OWN dynamically-set tooltip (`_on_central_body_changed`
overwrites it with an Earth-only-restriction note or clears it to `""` depending on the selected
central body). Adding a static explanatory tooltip at construction time would have been silently
wiped out the moment `_on_central_body_changed(gravity.central_body)` ran at the end of
`_build_gravity_group()` -- caught by re-reading the method after writing the tooltip, not by a
test (none exercise tooltip text). Fixed by moving the explanation INTO `_on_central_body_changed`
itself as the Earth-body branch's own tooltip, so the two pieces of tooltip logic compose instead
of one clobbering the other -- verified directly with a headless `QApplication` smoke test that
switches the central body away from and back to Earth and reads `.toolTip()` both times.

**Files touched**: `orbit_ic_widget.py` (every field, full coverage), `scenario_editor.py`
(epoch, propagation-setup button), `spacecraft_editor.py` (every group box and essentially every
field across all its tabs -- by far the largest, since it has the most dense, unexplained numeric
fields of any editor in the app), `sensor_actuator_editor.py` (the Kind combo -- the per-kind
param hints were already thorough), `ground_station_editor.py` (every field), `propagation_setup_dialog.py`
(gravity, integrator, atmosphere/space-weather), `mission_sequence_editor.py` (command Kind, stop
condition, event kind, delta-V), `monte_carlo_editor.py` (dispersion quantity/kind/bounds/mean/std,
the Monte Carlo enable/run-count checkboxes), and `main_window.py` (every File/Run menu action's
tooltip rewritten to state its actual outcome, not just repeat its keyboard shortcut; three
actions -- Save As, Quit, About -- had no tooltip at all before this).

**Verification**: full non-Basilisk suite (`QT_QPA_PLATFORM=offscreen`): 1026 passed, 136
skipped, zero regressions. A headless `QApplication` smoke test additionally constructed
`MainWindow`, `SpacecraftEditorDialog` (toggling every checkable group on), `GroundStationEditorDialog`,
and `PropagationSetupDialog` (including the central-body-switch tooltip-composition check above)
to confirm every new tooltip-bearing code path actually runs with no error, not just that it
parses.

**Honestly scoped, not exhaustive**: this pass covers the editors with the heaviest concentration
of unexplained numeric/combo fields -- it does not touch every remaining widget in every GUI
file (e.g. `constellation_dialog.py`, `phasing_formation_dialog.py`, `vizard_dialog.py`,
`vizard_launcher.py`, `startup_fetch_dialog.py` still have their pre-existing, lighter tooltip
coverage). A natural follow-on, not required to call this item done: those dialogs are smaller
and already somewhat less dense with unexplained fields than the ones addressed here.

---

## Real user screenshot: picking a series via the completer popup still didn't redraw the plot

**Direct user report, with a screenshot**: after the earlier "live plot series switching unresponsive" fix (see that entry above -- it addressed a webview-reload race during a FAST live run), the user showed a case that fix did NOT cover: typing into `series_combo` to filter, then picking a suggestion, left the OLD plot ("Inertial Position") on screen while the text box plainly showed a different, valid series name (`berlin-gs.access_to_leo-comms-1.has_access`) already typed in full.

**Root cause, found by re-reading `series_combo`'s own wiring, not reasoned about in the abstract**: `_redraw()` was connected to exactly one signal, `series_combo.currentIndexChanged`. That signal is what a PLAIN dropdown-arrow click reliably fires. `series_combo` is `setEditable(True)` with its own `QCompleter` (needed for a 30-40+-series scenario, see this widget's own module docstring) -- and a completer-driven pick (click a popup suggestion, or type a full name and press Enter) does not reliably drive that same `currentIndexChanged` path in this Qt configuration, a known-inconsistent area of `QComboBox`+`QCompleter` interaction generally, not unique to this app. The combo's displayed TEXT updates either way (which is why the screenshot showed the right name in the box) -- only the actual redraw was silently skipped.

**The fix**: two more explicit hooks in `results_widget.py`, both funneling through a new `_on_series_text_committed(text)` method that explicitly syncs `series_combo`'s real selected index to the committed text (via `findText`/`setCurrentIndex`) before calling `_redraw()` directly -- never relying on a signal cascade that turned out not to be reliable:
* `completer.activated` -- fires the instant a popup suggestion is picked, by click or Enter-within-the-popup.
* `series_combo.lineEdit().editingFinished` -- catches the other real path: typing an exact, already-complete name and pressing Enter with no popup open.

Both are harmless to fire alongside the pre-existing `currentIndexChanged` (`_redraw()` is idempotent -- rebuilding the same figure twice costs a little work, never a bug) rather than trying to determine which single signal is "the" correct one across Qt versions.

**Verified with two new tests** in `tests/gui/test_results_widget.py`, each simulating the REAL interaction path rather than calling internal methods directly: `test_selecting_a_series_via_the_completer_popup_redraws_the_plot` emits `completer.activated` the way Qt does when a popup suggestion is chosen; `test_typing_an_exact_series_name_and_pressing_enter_redraws_the_plot` sets the line edit's text and sends a real `Qt.Key_Return` via `qtbot.keyClick`. Both assert the plot's own y-axis title actually changes (confirming a real rebuild happened, not just that the combo's displayed text changed) -- deliberately NOT using `series_combo.setCurrentIndex()` directly, which is the pre-existing, already-passing `test_user_series_change_is_never_throttled_during_a_live_run`'s own subject (the plain dropdown-arrow path, which was never broken). Full suite: 1028 passed, 136 skipped, zero regressions.

---

## Robustness: a live-display failure must never crash or permanently wedge the GUI

**Direct user feedback**, with a screenshot: running a second simulation after a previous one finished left the Results tab stuck on its empty "Run a simulation to see results here" placeholder for the ENTIRE new run (status bar and the elapsed-time progress bar both showed it genuinely running, Vizard was visibly animating normally), with no error shown anywhere. Stated principle behind the report: "the app really should be robust and resilient and not crash whenever something unusual happens or if the user does stupid things."

**Honesty note on root cause**: this sandbox has no cached SPICE kernels and no real display, and `engine.service.SimulationService.build()` unconditionally needs a SPICE interface for every scenario (confirmed by reading that method directly, not assumed) -- so the exact failing scenario from the report could not be reproduced end-to-end here, the same already-documented gap this project's own SPICE-dependent features have always carried. A thorough code-level audit of every per-scenario state handoff in `main_window.py` (`on_new`/`open_path`/`_open_scenario` all already correctly clear `results_widget`/`mission_dashboard_widget`/`mission_output_widget` on a scenario swap) found no definitive single root cause for THAT exact symptom. Rather than guess at one unprovable fix, this entry hardens the actual failure MODE the report's own stated principle describes -- a GUI update failure anywhere in the live-result path going completely unhandled and unrecoverable -- which is real, verified by new tests below, and valuable regardless of what specifically triggered the report.

**Two real, independently-confirmed gaps, both fixed**:

1. **`MainWindow.on_run()` only cleared the previous run's results when the NEW run was starting in live-plot mode** (`if live: self.results_widget.set_result(None); ...`). A non-live run (Live Plot toggled off, or a scenario with a `mission_sequence`, which `RunWorker` never live-chunks -- see that module's own docstring) skipped this entirely, leaving WHATEVER the previous run produced on screen for the full duration of the new one -- genuinely indistinguishable from "this run's results are already in, and wrong" rather than "no results yet." Fixed: the clear now always runs, unconditionally, before a run starts.
2. **No GUI-thread exception handling anywhere in the live-result chain.** `_on_run_progress` (called on every single live chunk), `_on_run_finished`, and `_on_run_cancelled` all called straight into `results_widget`/`mission_dashboard_widget` with no `try`/`except` at all. Basilisk's own `RunWorker.run()` was ALREADY defensive (a blanket `except Exception` reporting via its own `failed` signal, per that module's own docstring) -- but nothing on the RECEIVING, GUI-thread side was. If any one of these GUI calls ever raised for ANY reason (a genuinely unexpected one included -- exactly the "something unusual happens" case the report names), the exception would propagate back out through Qt's own signal dispatch with no handler: for `_on_run_progress`, specifically, since the same scenario/data keeps producing the same failure on every subsequent chunk, this deterministically means EVERY later chunk silently fails the same way for the rest of the run -- exactly the "Results tab stuck empty while the run keeps going in the background" symptom the screenshot shows, whatever the original trigger actually was. Worse, for a handler ordered with its state-restoring work (`_stop_busy()`, which re-enables Run/clears the busy indicator) AFTER the part that could fail, a mid-handler exception could leave the app in "busy" forever -- unable to start another run at all without restarting the whole process, the single worst form of "a lot of things break."

**The fix**: `_on_run_progress`/`_on_run_finished`/`_on_run_cancelled`/`_on_monte_carlo_finished` now each wrap their own result-display work in `try`/`except Exception`, logging the full traceback (`_logger.exception`, matching `RunWorker`'s own "full traceback to the log file" discipline) and surfacing a non-fatal warning dialog -- never a silent swallow. `_on_run_progress`'s own dialog is shown at most ONCE per run (`self._progress_error_shown`, reset at the start of every `on_run()`) rather than popping up on every single chunk, since the whole point is that a live run can call it dozens of times. Every terminal handler (`_on_run_finished`/`_on_run_cancelled`/`_on_monte_carlo_finished`) now calls `_stop_busy()` BEFORE the part of the handler that could fail, not after -- so a display-side bug can never again leave Run/Abort permanently disabled; the simulation's own real outcome (it DID finish, or DID get cancelled) is never hidden behind a GUI bug in showing it.

**Verified with six new tests** in `tests/gui/test_main_window.py`: `test_run_progress_exception_is_caught_not_propagated`/`test_run_finished_exception_still_stops_busy_indicator`/`test_run_cancelled_exception_still_stops_busy_indicator` each monkeypatch `results_widget.set_live_result` to raise and confirm the handler itself does not raise AND (for the two terminal ones) that the busy indicator genuinely stops and `run_action` is re-enabled -- the exact "stuck forever" failure mode described above, reproduced and confirmed fixed. `test_run_progress_exception_dialog_shown_only_once_per_run` confirms five failing chunks produce exactly one dialog, and that a fresh run's own reset re-arms it. `test_on_run_clears_previous_results_even_when_not_live` reproduces gap #1 directly: sets a stale result, starts a non-live run, confirms `series_combo` is empty immediately rather than still showing the stale run. Full suite: 1033 passed, 136 skipped, zero regressions.

---

## Real bug confirmed numerically: phasing-keeping correction can diverge instead of converge, from a nonzero radial placement offset

**Direct user report, with two screenshots**: "in the phasing keeping wizard I selected a desired along-track separation to be maintained of 1000km. why is it crossing this value much more beyond in the simulation?" -- one screenshot showed the along-track separation at ~1567/2000 km (the Vizard panel's own capacity, 2x the 1000 km target) partway through a run, the other showed BOTH radial and transverse pinned at their 2000/2000 km panel capacity later in the same run. A companion report in the same message ("These RTN values seem like complete nonsense to me") is the same underlying bug, not a separate one -- see below.

**Root cause, found with a real numerical diagnostic, not just reasoned about**: the formation wizard (`gui/phasing_formation_dialog.py`) lets a user set a nonzero Radial (R) offset alongside the Along-track (T) target -- `engine/formation.py`'s own docstring already documented that this makes T "somewhat short" of its target at epoch, due to `orbitalMotion.rv2elem()`'s known near-circular decomposition ambiguity when a radial Hill-frame offset is layered on via `hill2rv`. A fresh 31-day two-body sim built directly against this project's real `/tmp/bsk_venv4` Basilisk install (chief + follower, `build_station_keeping` + `build_phasing_keeping`, a 1000 km along-track target with a 50 km radial offset -- a realistic, not extreme, wizard input) showed this is far worse than "somewhat short": the follower's real orbital elements come out corrupted enough (semi-major axis off by ~206 km, eccentricity off by more than 20x) that `PhasingKeepingController`'s own mean-anomaly-based error metric reads **-7.92 deg at epoch when the true geometric error is actually +8.27 deg** -- backwards, not just imprecise. The controller burns confidently in the WRONG direction, and the real along-track separation oscillates between roughly +6900 km and -6900 km (vs. the 1000 km target) over the 31-day run while radial separation grows to over -13,800 km and 54% of the formation's propellant budget is consumed chasing a correction that never converges -- exactly the two screenshots' numbers, and exactly why the RTN panel looked like "nonsense": those numbers are the real, correctly-computed geometry (verified independently via `orbitalMotion.rv2hill`, the same function the wizard itself uses to place a follower in the first place) reporting a genuinely broken physical state, not a display bug.

**What was NOT done, and why**: the obvious "real" fix -- a Clohessy-Wiltshire-consistent radial-offset velocity correction (`rho_prime_h[1] = -2*n*R` instead of zero) so the placement itself doesn't secularly drift -- was built and tested numerically against the same diagnostic. It measurably improved the corrupted semi-major-axis/eccentricity, but shifted the error into the follower's argument of periapsis instead (a ~170 deg mean-anomaly error), which is worse for this controller's specific error metric, not better. This exact code area (the RTN telemetry panels feeding off this same controller) has already been through four separate rounds of real-user-screenshot-driven fixes earlier in this project (see this file's own entries above) -- betting a placement-math rewrite on one afternoon's numerical testing, in an area with that history, was judged too risky to ship with confidence. `engine/formation.py`'s docstring and the wizard's own radial/along-track tooltips (`gui/phasing_formation_dialog.py`) were instead rewritten to state the REAL severity (divergence, not just imprecision) rather than leave the original, now-known-to-undersell, "somewhat short... the controller will still correct it" wording in place.

**The fix actually shipped: a divergence guard in `PhasingKeepingController`.** Rather than fix the placement math, the controller now recognizes when its own corrections aren't working and stops trying, instead of burning propellant into an unbounded spiral forever:
* Each full correction cycle (`BURN_RESTORE -> IDLE`) is checked against the SAME tolerance band the `IDLE` state itself uses to decide whether a correction is even needed -- if the error is still outside that band after a full correction supposedly fixed it, the cycle counts as non-convergent.
* The first attempt tried was comparing a cycle's ending error against its own starting error (literally "did this get better") -- numerically this was fooled by the diverging case's own oscillation: the error metric alternates between two phase-locked values on successive cycles (observed directly: -36 deg, then +162 deg, then -36 deg, ...), which looks "better" every other cycle and never accumulates a non-convergence count. Comparing against the fixed tolerance band instead of the previous cycle's error avoids that trap entirely.
* After `_MAX_NON_CONVERGENT_CYCLES` (2) consecutive non-convergent cycles, `suspendedDueToNonConvergence` is set `True` and no further automatic corrections are triggered from `IDLE`, logged once via `_LOGGER.warning` with the before/after error for diagnosis. A fresh schedule target (the mission's own `target_separation_km` list ticking over to a new entry, e.g. a scripted reconfiguration) is treated as a genuinely new situation and clears the suspension for a clean new attempt.
* `suspendedDueToNonConvergence` is a real, public (non-underscore) attribute -- inspectable and testable now, not yet wired into a live Vizard panel (a reasonable follow-on, not done here).

**Verified directly against the real Basilisk build**, both before and after: the SAME 31-day diagnostic that reproduced the user's screenshots shows the guard triggering at ~1.7 days (after exactly 2 non-convergent cycles) and cutting propellant consumption from 54% of the 5 kg budget (97.6 m/s of delta-V) down to under 2% (3.6 m/s) -- the correction attempts for the rest of the 31-day run that would otherwise have kept chasing the oscillation are skipped entirely. A second diagnostic run with R=0 (the well-conditioned case this controller already handles correctly) confirms the guard never falsely triggers there: `suspendedDueToNonConvergence` stays `False` for the full 31 days, with delta-V usage an order of magnitude smaller still (0.04 m/s) than even the guarded divergent case. Three new tests in `tests/test_orbit_maintenance.py` (`test_phasing_keeping_divergence_guard_suspends_after_non_convergent_cycles`, `test_phasing_keeping_suspends_further_burns_once_guard_trips`, `test_phasing_keeping_new_schedule_target_clears_the_suspension`) exercise the guard directly and fast via hand-crafted, frozen (always-non-convergent-by-construction) state messages rather than a slow full simulation -- the full-sim confirmation above lived in a throwaway scratch script, not in the committed suite. All 26 tests in that file pass against the real Basilisk build (`/tmp/bsk_venv4`), with zero regressions in the 23 pre-existing ones.

**Known, honestly-stated limitation**: this is a safety net, not a fix for the underlying placement-math decoupling -- a follower placed with a large radial/cross-track offset will still start from a badly mis-estimated error and still burn propellant on 1-2 non-convergent cycles before the guard engages (3.6 m/s / ~2% of budget in the diagnostic above, not zero). The wizard's tooltips now say this plainly. A real fix would need to either correct `engine.formation.generate_phasing_follower`'s placement math to not corrupt the follower's orbital elements in the first place, or give `PhasingKeepingController` a geometric (Hill-frame, `rv2hill`-based) error metric instead of the current mean-anomaly-difference one -- both are real, scoped follow-on work, not attempted here given the CW-fix side effect found above and the time available to verify either confidently against this codebase's own documented history of subtle bugs in this exact area.

---

## Real bug found directly from Vizard's own Unity source: GenericSensor mode 0 is hardwired to "invisible", not "the 0th color"

**Direct user report**: "why is scenario 19 not showing any RF link related panels in vizard (as I requested)?" -- referring to the "Mode"/"Link status" `GenericSensor` badges added for `schema.scenario.CommsPointingConfig` spacecraft (see the "Surface Mission Dashboard telemetry" entry above).

**Investigation, not guesswork**: the engine-level wiring (`engine.fsw.build_comms_pointing`, `engine.vizard.enable_vizard`'s `comms_pointing_by_spacecraft` handling, `engine.service.build()`'s deferred comms_pointing pass) was re-read end to end and found correct -- `tests/test_vizard.py::test_enable_vizard_with_comms_pointing_builds_the_three_new_panels` already confirms, against a real Basilisk build, that all three panels land in the lists handed to `vizSupport.enableUnityVisualization()`. A from-scratch orbital-mechanics check (template 19's real orbit: a=6928 km, i=97.59 deg, vs. `berlin-gs`'s real lat/lon/min-elevation) confirmed the scenario's own geometry genuinely produces two real access windows (~7 minutes each, up to 32 deg elevation) within its 12-hour duration -- not a badly-parameterized template with no access at all.

That left the Unity rendering side -- this module's own docstring had already flagged the `GenericSensor`/`DeviceCmdMsgPayload` composition as "NOT yet... confirmed against a real running Vizard instance", unlike the `GenericStorage` panels. With no running Vizard available in this sandbox either, the next honest option (matching this project's own established technique -- see the RTN-panel `storageLevel` clamping bug earlier in this file, confirmed directly against `GenericStorageUnitMethods.cs`) was to read Vizard's actual Unity source (`0h3xn4/vizard`) rather than keep guessing from the C++ header's field comment the code was originally written against.

**The real finding, in `GenericSensorHUDMethods.cs`**: `vizStructures.h`'s own comment ("Modes 0 and 1 will use the 0th color, Mode 2 will use the color indexed to 1") describes an OLDER or different semantic than what this Unity build actually does. The real `FixedUpdate()`/`getModeColor()` logic is hardwired so that **mode 0 always fades the indicator's colored "scoop" to fully hidden, regardless of what color is configured for it** -- `getModeColor()` is never even called when the commanded mode is 0; that branch goes straight to a 20-frame fade-to-invisible instead. Modes 1 and 2 are the only two values that actually map to the two user-supplied colors (`modeColors[1]`/`modeColors[2]` -- `modeColors[0]` is an internal, hardcoded default color the Unity code never lets a caller's own color list override). Every one of this project's `GenericSensor` badges -- the pre-existing ground-station-access indicator AND the new Mode/Link-status badges -- used exactly the `{0, 2}` convention the C++ comment suggested, which means the "off" state (no access / Sun-pointing / no link) was invisible for essentially the entire run, not shown in some default/off color. Template 19's comms-pointing badges spend ~99% of a 12-hour run in that "off" state (two ~7-minute access windows out of 12 hours) -- so a user watching Vizard would see nothing there almost all the time, exactly matching "not showing any RF link related panels."

**The fix**: both the access-indicator bridge (`engine.vizard.enable_vizard`'s `_AccessIndicatorBridge`) and the comms-pointing arbitrator (`engine.fsw._CommsPointingArbitrator`'s `modeCmdOutMsg`/`linkStatusCmdOutMsg`) now command `1` for "off" and `2` for "on" -- never `0`. This is a pure relabeling with no change to the colors themselves (the first configured color, previously unreachable at mode 0, now shows correctly at mode 1), so both states render as a persistently visible, distinctly colored badge for the whole run instead of one of them being a permanent no-op. This incidentally fixes the SAME latent bug in the pre-existing ground-station-access indicator, which the module's own docstring had already flagged as unconfirmed against a real Vizard instance -- it had never actually been visually verified working, and this finding shows it very likely wasn't.

**A second, unrelated real bug found while investigating** (same area, same real-Basilisk-build verification pass): `tests/test_comms_pointing.py::test_comms_power_sink_only_draws_power_while_comms_mode_is_active` read the recorded power-sink message's field as `nodePowerOut` -- but the real, installed `PowerNodeUsageMsgPayload` names that field `netPower` (confirmed directly: `dir(messaging.PowerNodeUsageMsgPayload())`). This is a test-only bug (the production code only ever sets the SimplePowerSink module's own `nodePowerOut` *property*, a different and valid name, never reads this message field back) -- this specific test had apparently never actually been run against a real Basilisk build before now, despite task #46 marking the comms_pointing test suite "complete." Fixed by reading `netPower` instead.

**Verified directly against the real Basilisk build** (`/tmp/bsk_venv4`): all 8 tests in `tests/test_comms_pointing.py` pass (one updated, `test_mode_cmd_out_msg_mirrors_mode_log_in_the_0_2_vizard_convention` renamed to `..._1_2_...` and its assertions updated for the new convention; three more tests' hardcoded `== 0`/`== 0` checks updated to `== 1`, matching the new "no link"/"off" command value), and 10 of 12 tests in `tests/test_vizard.py` pass (the remaining 2 failures are the pre-existing, already-documented SPICE-kernel-network gap in this sandbox, confirmed unrelated: they fail identically before and after this change). No GUI/exported-data series are affected -- `{sc}.comms_pointing.active_mode`'s own 0/1 convention (what `gui.mission_dashboard_widget` and the CSV export read) is a completely separate Python telemetry log, untouched by this fix, which only changes the integer written into Vizard's own `DeviceCmdMsgPayload`.

**Honestly-stated limitation**: this fix is verified by direct source inspection and the existing unit-test suite, not by an actual running Vizard instance (no Unity runtime is available in this sandbox, the same gap this project has carried throughout). It is the most concrete, evidence-based explanation found for the report, and corrects a semantic mismatch now confirmed from Vizard's own real source code -- but, per this project's own documentation discipline, is flagged here as not visually re-confirmed end-to-end.

---

## Real bug, root-caused from Vizard's own Unity source: a running Vizard instance has no way to reset itself between runs

**Direct user report**: "when running a new simulation after a previous simulation finished, vizard should completely refresh so it actually displays only stuff from the current simulation, and not the previous one."

**Root cause, confirmed directly from Vizard's own Unity source** (`0h3xn4/vizard`, same technique used for the other two Vizard investigations this round): `MessageList.cs`'s `AddLiveMessage()` just keeps appending every new message to an ever-growing dictionary, under an ever-incrementing `timestepsTotal` index, for the ENTIRE lifetime of the Unity process -- there is no code path anywhere that clears this between separate client connections. `ScenarioSceneManager.cs`'s `Awake()` -- which actually builds the scene's spacecraft/celestial-body/ground-station GameObjects -- runs exactly ONCE, driven by `MessageList.FirstMessage` (also captured exactly once, the very first message this process ever receives, cached via a `firstMessageAdded` flag that's never reset while the Main Scene is running). The one method that does reset this state, `MessageList.ResetFirstMessage()`, is only ever called from `StartUpScreenManager.cs` -- Vizard's own pre-scene launcher screen -- never while the Main Scene is live and streaming. In short: **a running Vizard instance cannot be reset short of actually restarting the process**; reconnecting a new simulation to the SAME running instance just feeds new data into the first simulation's own scene, appended after its data in the same continuous timeline.

This directly explains the report: `gui/main_window.py`'s `on_launch_vizard()` deliberately REUSES an already-running, correctly-configured Vizard process across runs (`self._vizard_process is not None and self._vizard_process.poll() is None` -> "Vizard is already running", return without relaunching) -- a deliberate choice from an earlier round, made specifically to avoid forcing the user to re-click Vizard's "Start Visualization" button on every single run. That convenience is exactly what was defeating the user's expectation of a clean scene per run, since (per the finding above) there is no way for a reused instance to ever actually be clean.

**The fix**: `on_run()` now always terminates a self-launched `self._vizard_process` (one `on_launch_vizard()` itself started earlier -- never a process this session didn't launch, same "not this app's process to kill" boundary `on_launch_vizard()` already respects) immediately before calling `on_launch_vizard()` for a live-stream run, forcing a fresh relaunch every time rather than reusing a matching instance. `on_launch_vizard()` itself is unchanged -- its own "reuse if matching" behavior still applies exactly as before when invoked directly from the "Launch Vizard" menu action, which is a different use case (the user explicitly wants a persistent Vizard window to leave open, not "about to start a run"). The real UX cost -- one more "Start Visualization" click needed in Vizard's own window before each run, since there is no documented command-line flag to skip that while still showing the live view (already true before this change, see `on_launch_vizard()`'s own docstring) -- is an unavoidable, honestly-documented price of actually fulfilling what was asked: a real fresh scene has no cheaper substitute given Vizard's own real architecture.

**Verified** with a new test, `test_run_always_relaunches_vizard_fresh_for_a_live_stream_run` (`tests/gui/test_main_window.py`): drives `on_run()` twice with a live-stream request and a fake, already-"running" Vizard process, and confirms the second call terminates the first process and launches a genuinely different one, rather than reusing it. All 82 tests in that file (plus the pre-existing Vizard-launch tests covering the menu-action's own, unchanged "reuse if matching" behavior) pass headlessly against a real `QApplication`.

**Known, honestly-stated limitation**: an EXTERNALLY-started Vizard instance (the user launched it manually, outside this app, or in an earlier session before this one tracked it) is still left alone -- this app has no reliable way to tell an arbitrary running Vizard process "are you connected to a previous run", and killing a process it didn't start is not this app's call to make (the same boundary `on_launch_vizard()` already drew). A user who manually keeps reusing such an instance across runs will still see stale data; the fix only covers Vizard instances this app itself launches, which is the common case ("Run" with live-stream enabled, no manual Vizard management).

---

## Real, sourced device catalog: "select from the space industry" alongside the existing custom editor

**Direct user feedback**: "the user should be able to either create their own sensor/actuator or select from a range of commonly used devices from the space industry. They must be ITAR free and available in europe." A follow-up mid-task refined the ask further: swap the catalog's thruster entry for ENPULSION's larger MICRO R3 (not the CubeSat-class Nano), and size the whole catalog for "a spacecraft between 200 to 500 kg wet mass" rather than CubeSat-class hardware.

**New module, `engine/device_catalog.py`** (no Basilisk/PySide import, fully unit-testable with no sandbox dependency): one `DeviceCatalogEntry` per `schema.scenario.SensorConfig`/`ActuatorConfig` kind this project supports, each a REAL, currently-sold, European-manufactured device:

| Kind | Device | Manufacturer | Country |
|---|---|---|---|
| `star_tracker` | ASTRO APS | Jena-Optronik | Germany |
| `imu` | ARIETIS-NS (gyro) | InnaLabs | Ireland |
| `coarse_sun_sensor` | SS200 | Hyperion Technologies | Netherlands |
| `magnetometer` | MM200 | Hyperion Technologies | Netherlands |
| `reaction_wheel` | RSI 04-33-60A | Collins Aerospace (Teldix) | Germany |
| `thruster` | MICRO R3 | ENPULSION | Austria |
| `magnetic_torque_rod` | MTQ800 | AAC Clyde Space | Sweden/UK |

**Honesty discipline, checked against this project's own established standard elsewhere** (e.g. `engine.formation`'s R/N-placement docstring, `engine.link_budget`'s pointing-loss approximation): every entry's numbers were pulled from that manufacturer's own real, publicly reachable datasheet/catalog page (`source_url`, cited on every entry -- nothing invented), via live web search rather than recalled from training data, specifically to avoid presenting a plausible-looking but unverified number as a real spec. Where a datasheet's own unit/statistic didn't map directly onto this schema's field (e.g. a star tracker's two different boresight/cross-boresight accuracy numbers against this schema's single isotropic `noise_arcsec`; a gyroscope's angular-random-walk noise DENSITY against Basilisk's own discrete per-tick `gyro_noise_rad_s`; a magnetometer's noise spectral density against a per-sample standard deviation; a reaction wheel's spin-axis inertia, never directly published, DERIVED from the vendor's own published momentum storage divided by max speed), the catalog entry's `notes` field states the exact approximation/derivation and the arithmetic behind it -- never silently presented as if it were the vendor's own direct figure. Exactly one optional field (the IMU's `accel_noise_m_s2`) was left unset rather than guessed, because no specific InnaLabs accelerometer datasheet number could be confirmed in the time available.

**`itar_free_note` is phrased at the confidence level the source material actually supports**: InnaLabs' and Hyperion's own public materials explicitly state "ITAR free" for the relevant product lines, quoted as such; for entries where no such explicit claim was found (Jena-Optronik, ISISPACE-class reasoning, Collins Aerospace, AAC Clyde Space), the note states only the plain, verifiable fact (country of manufacture, and for Collins Aerospace specifically, the caveat that its PARENT company is US-headquartered even though this exact wheel is built in Heidelberg, Germany) with an explicit "verify the current export-control classification with the manufacturer for your own procurement" caveat. This project makes no independent legal export-control determination for anyone's own hardware/mission, and nothing in this catalog should be read as one.

**Mass-class fit, addressing the follow-up refinement**: a 1-3U CubeSat-class reaction wheel/magnetorquer/thruster would be badly undersized for a 200-500 kg microsatellite bus's real control-torque/dipole/thrust-authority budget, so those three ACTUATOR entries specifically were chosen from manufacturers' own mid-size product lines (the RSI family spans 30-7,000 kg per Collins Aerospace's own materials; the MTQ800 is stated for 50-200 kg, a closer though not perfect fit noted honestly in its own entry; the MICRO R3, per the user's explicit request, over ENPULSION's smaller milli-kg-class Nano). The four SENSOR entries (star tracker, IMU, sun sensor, magnetometer) were deliberately left as originally researched and explained as such in each entry's own description: a pointing/attitude sensor's mass, power, and accuracy genuinely don't scale with bus size the way an actuator's torque/thrust authority does, so a part marketed for CubeSats is not actually an engineering mismatch on a larger bus.

**GUI wiring, `gui/sensor_actuator_editor.py`'s `_ItemEditorDialog`**: a new "Catalog" row (a combo box of real devices for the currently selected Kind, plus an "Apply device preset" button and an info label showing the selected device's description/source/export-control note/any approximation notes) sits between the existing per-kind hint text and the vector-row/params-JSON editor. Selecting a catalog entry only PREVIEWS it (the info label updates; nothing in the actual sensor/actuator changes yet) -- exactly mirroring the existing "Reset to template" button's own "nothing changes until an explicit action" rule, so browsing the catalog can never accidentally clobber an in-progress custom edit. Clicking "Apply device preset" fills the SAME vector spin boxes and params JSON box "Reset to template" already fills, just with a real device's numbers instead of a generic example -- the result stays exactly as freely editable afterward as any hand-built sensor/actuator, never a separate locked mode. The section hides itself entirely (not an error) for a kind with no catalog entry, and resets to the "custom (no preset)" placeholder whenever Kind changes, since a different kind's catalog entries are a different list.

**Verified**: a new `tests/test_device_catalog.py` (9 tests, no Basilisk/GUI dependency beyond an import-skippable PySide6 check for two of them) confirms every entry's kind is schema-recognized, every entry has real sourcing metadata (manufacturer/product/country/a real `https://` source URL/an export-control note), every entry satisfies `gui.sensor_actuator_editor`'s own required-key list for its kind (so "Apply device preset" can never itself produce an invalid sensor/actuator), every params key it sets is one that module actually recognizes for that kind (catching a typo'd/stale key), and every kind this project supports has at least one entry. Six new tests in `tests/gui/test_sensor_actuator_editor.py` drive the actual dialog: the catalog row shows/hides correctly, selecting an entry previews without mutating fields, applying one fills real device params, the result stays freely hand-editable afterward (overwriting one field keeps the rest of the preset), and the combo resets to "custom" on a Kind change. Full suite: 1040 passed, 11 skipped (`-m "not requires_basilisk"`), zero regressions; the two newly added Basilisk-adjacent-but-actually-Basilisk-free test files also pass directly against the real Basilisk venv used throughout this session.

---

## Device-interface realism: faults, saturation, and encoder quantization for sensors; friction/dispersion for actuators (already there, undiscoverable)

Continuing the same round of feedback as the device catalog above: "device-interface realism (faults/saturation/encoders)" was picked as the next backlog item to build.

**Investigated before building anything**: rather than invent new physics, read the real, already-compiled Basilisk sensor modules this project already wires up (`StarTracker`, `ImuSensor`, `CoarseSunSensor`, `Magnetometer`) directly in a real Python session against this project's own Basilisk venv. All four already expose real, native bias/saturation/fault/quantization fields this project's `engine.fsw.attach_sensors()` was simply never setting: `ImuSensor.senRotBias`/`senTransBias` (fixed bias), `senRotMax`/`senTransMax` (saturation), `setLSBs()` (encoder/ADC quantization -- the "encoders" the feedback asked for, by name); `CoarseSunSensor`/`Magnetometer`'s `senBias`/`maxOutput`/`minOutput` (bias/saturation) plus a real, named fault-state enum each (`CSSFaultState_t`: stuck-at-current/stuck-at-max/stuck-at-random/random-noise; `MagFaultState_t`: stuck-at-current/stuck-at-value/spiking, applied per AXIS since a real single-axis sensor-element failure doesn't take out the other two); `StarTracker.walkBounds` (a long-run random-walk bound on its existing noise). Separately, `simIncludeRW.rwFactory().create()`/`simIncludeThruster.thrusterFactory().create()` already accept real friction (`useRWfriction`/`fCoulomb`/`fStatic`/`cViscous`/`betaStatic`) and thrust-dispersion (`thrusterMagDisp`) kwargs -- and this app's own `engine.fsw._coerce_rw_kwargs()`/`_coerce_thruster_kwargs()` were ALREADY passing those straight through (even already present in the defensive `_RW_FLOAT_KWARGS`/`_THRUSTER_FLOAT_KWARGS` float-coercion lists) -- they were fully wired and usable today, just never surfaced in `gui.sensor_actuator_editor`'s per-kind hint text, so nobody without reading this project's own source code would ever discover they existed.

**What was built**: `engine/fsw.py`'s `attach_sensors()` now sets each of those real fields from new, optional `SensorConfig.params` keys (schema's own `params` dict stays a fully open dict, so no schema migration was needed) -- `bias_walk_bound_arcsec` (star tracker); `gyro_bias_rad_s`/`accel_bias_m_s2`/`gyro_saturation_rad_s`/`accel_saturation_m_s2`/`gyro_lsb_rad_s`/`accel_lsb_m_s2` (IMU); `bias`/`saturation_max`/`saturation_min`/`fault_mode`/`fault_noise_std` (coarse sun sensor); `bias_tesla`/`saturation_tesla`/`fault_mode`/`fault_axis`/`stuck_value_tesla`/`spike_probability`/`spike_amount` (magnetometer). `gui/sensor_actuator_editor.py`'s `_KIND_PARAM_SPECS` gained matching entries for discovery (hint text, vector rows where applicable, "Reset to template" inclusion) -- plus, for `reaction_wheel`/`thruster`, entries for the ALREADY-working `useRWfriction`/`fCoulomb`/`fStatic`/`cViscous`/`betaStatic`/`thrusterMagDisp` kwargs, so this round's only actual code change for those two kinds was making them discoverable.

**A real bug caught by this round's own tests, not shipped**: the first version of the `coarse_sun_sensor` fault wiring mapped `fault_mode="none"` to `coarseSunSensor.CSSFAULT_OFF` -- reasonable-looking given the name, and WRONG: reading `coarseSunSensor.h`'s own enum comment directly ("CSS measurement is set to 0 for all future time") shows `CSSFAULT_OFF` is itself one of the FAULT states (a "sensor permanently dead" fault), not "no fault" -- the real nominal/unfaulted value is a separate, differently-named enum member, `NOMINAL`, which doesn't contain the substring "FAULT" and was therefore missed on a first `dir()`-based enumeration of the module's fault constants. This made EVERY `coarse_sun_sensor` built through the new code read a permanent 0 regardless of real sun geometry -- caught immediately by `test_css_baseline_reads_near_full_illumination` actually checking the sensor's real observable output (not just that the field got set without crashing), before this was ever committed. Fixed by mapping `"none"` to `coarseSunSensor.NOMINAL` instead. Also confirmed directly against `coarseSunSensor.cpp`'s own `UpdateState()` ordering that `"stuck_max"` forces the PRE-saturation value to a literal `1.0`, which this schema's own `saturation_max` (if set lower) still clips afterward -- documented precisely in `engine.fsw`'s own comment rather than the looser "freezes at maxOutput" phrasing an untested first draft used.

**Verified directly against the real Basilisk build** (`/tmp/bsk_venv4`), via real observable sensor OUTPUT, not just "the setter ran": a new `tests/test_device_realism.py` (14 tests) builds each sensor directly against a bare `SimulationBaseClass` (same pattern as `tests/test_css_estimation.py`/`tests/test_mtb_desaturation.py`) and confirms, from the actual recorded output message: a CSS bias adds exactly to the true cosine-law reading; `saturation_max` really clips it; `fault_mode="stuck_max"` combined with a tiny `saturation_max` reads exactly that saturation value regardless of an enormous bias; an unrecognized `fault_mode` raises a clear `FswError` (both CSS and magnetometer); a magnetometer bias adds exactly per-axis to a REAL WMM-computed field (same real-Earth-field setup as `test_mtb_desaturation.py`); magnetometer saturation clips every axis symmetrically; a magnetometer `fault_mode="stuck_value"` on one `fault_axis` freezes exactly that axis while leaving the other two untouched; an IMU gyro/accelerometer bias adds exactly to the true rate/specific-force (the latter checked against a true value of exactly 0, since this bare sim has no gravity/forces -- a clean, nothing-else-to-subtract-out baseline); IMU gyro saturation clips; and a coarse `gyro_lsb_rad_s` genuinely quantizes a true rate that is NOT itself a multiple of that step onto one that is. The star tracker's `bias_walk_bound_arcsec` gets a lighter-touch test (confirms it's really set and the sensor still runs/produces finite output) since its effect is a stochastic long-run bound, not something one deterministic tick can demonstrate -- a statistical long-run confirmation is flagged as a reasonable, not-yet-done follow-on. Full suite: all pre-existing Basilisk-dependent tests this round touched (`test_css_estimation.py`, `test_mtb_desaturation.py`, `test_orbit_maintenance.py`, `test_fuel_tank.py`, `test_thruster_control.py`, `test_momentum_dumping.py`) still pass, plus the full non-Basilisk suite (1040 passed, 11 skipped), zero regressions.

---

## Comprehensive audit round: six parallel read-only reviewers, five real fixes, one claimed finding rejected

User request, ahead of starting the thermal-simulation backlog item: "do a complete and comprehensive audit and review of everything and fix any problems you might detect." Six independent, read-only review agents were run in parallel, each scoped to a different part of the codebase (`schema/`+`cli.py`; `engine/` core; `engine/` support modules; `gui/` core; `gui/` support modules; a final consolidation pass), each briefed on this project's own historical bug patterns so it wouldn't re-flag issues already fixed in earlier rounds. Several things the audits checked came back clean and are worth recording as confirmed-correct rather than silently dropped: the Vizard `GenericSensor` `{1, 2}` panel-index convention is consistent everywhere it's used; the Vizard object-retention fix from an earlier round is still correctly wired; `on_run()`'s Vizard-relaunch logic (see the entry above) has no missed call site; the device-catalog picker's `normalizable` flags are all correct; no newly-added `SysModel` has a dangling-reference risk; `device_catalog.py`'s seven entries all match `engine.fsw`'s actual params keys exactly; there are no dead/orphaned tests; all 19 bundled templates remain schema-valid.

**Fix 1 -- `engine/fsw.py`: an out-of-range magnetometer `fault_axis` silently did the wrong thing instead of raising.** `attach_sensors()` validated `fault_mode` but not `fault_axis` before using it to index a plain 3-element Python list (`stuckValue`/`spikeProbability`/`spikeAmount`) and then calling `Magnetometer.setFaultState(axis, state)`. An axis `>= 3` raised a bare, unhelpful `IndexError` on the list indexing -- unlike every other bad-input path in this function, which raises a specific `FswError`. A NEGATIVE axis was worse: Python's own negative-indexing silently wrote the WRONG axis (e.g. `-1` writes axis 2, not "axis -1"), while confirmed directly against `magnetometer.cpp` (`if (axis >= 0 && axis < 3) {...}`, no `else`/error branch), Basilisk's own `setFaultState()` just silently no-ops for a negative axis -- so the fault would look "configured" in the saved scenario but never actually fire on any axis. Fixed by validating `fault_axis in (0, 1, 2)` up front, same as every other input in this function. New test: `test_magnetometer_out_of_range_fault_axis_raises_fsw_error_not_indexerror` (`tests/test_device_realism.py`, `requires_basilisk`) -- 15/15 passing against the real build.

**Fix 2 -- `schema/scenario.py`: a magnetometer sensor or `magnetic_momentum_management` on a non-Earth body validated cleanly, then failed much later at Run Simulation time.** `engine.fsw.attach_sensors()` already raises an `FswError` the moment a `"magnetometer"` sensor is configured with `gravity.central_body != "earth"` (Basilisk's WMM magnetic-field model is Earth-only), and `engine.service.SimulationService.build()` raises the analogous error for `magnetic_momentum_management` -- but both are engine-layer checks that only run once a scenario is actually simulated. `MagneticMomentumManagementConfig`'s own docstring already pointed at this exact gap as "deferred to the engine layer", explicitly flagged as something this schema's own precedent (the `needs_sun` cross-reference checks for power/station-keeping/SRP/comms-pointing) should have closed the same way. Mirrored both checks into `Scenario.validate()`, right after the existing `needs_sun` block, and updated `MagneticMomentumManagementConfig`'s docstring to match. Three new tests in `tests/test_scenario_schema.py` (185 passed); confirmed none of the 19 bundled templates regress (`test_scenario_templates.py`, 90 passed).

**Fix 3 -- `schema/references.py`: `report` commands weren't tracked by the reference-integrity system at all.** `report.params["series"]` entries are dotted, spacecraft-name-prefixed strings (`"sat-1.position_N"`), structurally identical to how `assignment.params["target"]` is already parsed -- but `_command_references()`/`_rename_in_commands()` had no `"report"` case, so a report command referencing a spacecraft didn't block that spacecraft's deletion (silently leaving a dangling series name instead of refusing, which is this module's whole stated purpose) and wasn't rewritten on rename. Added a `report` branch to both functions, parsing each `series` entry's leading dotted segment the same way `assignment` already does (a report can reference several spacecraft at once, one per series entry, unlike the single-spacecraft `assignment`/`maneuver` cases, so this one loops with an index). Updated the module's own docstring, which previously described `assignment` as the sole dotted-string exception. New tests in `tests/test_references.py`: `test_report_series_reference_is_found`, `test_report_series_reference_to_other_spacecraft_is_not_found` (24/24 passing).

**Fix 4 -- claimed, investigated, and rejected: stale non-vector sensor/actuator params surviving a Kind switch.** An earlier audit pass flagged `gui/sensor_actuator_editor.py`'s `_ItemEditorDialog.to_dataclass()` for stripping only vector-shaped keys belonging to the newly-selected Kind, never non-vector keys left over from a PREVIOUS Kind. On inspection this is not a bug: `tests/gui/test_sensor_actuator_editor.py::test_switching_kind_does_not_clobber_params_until_reset_clicked` already asserts, by name, that an arbitrary hand-typed key (`{"hand_typed": true}`) must survive a Kind switch verbatim, and the module's own docstring states the params box is a deliberately open dict (so new Basilisk kwargs this project hasn't yet surfaced in `_KIND_PARAM_SPECS` can still be set by hand) that only the explicit "Reset to template" button is allowed to clobber. Stripping unknown non-vector keys on every Kind switch would silence that test and contradict the documented design. No change made; recorded here so this claim isn't silently re-raised by a future audit without this context.

**Fix 5 -- `engine/orbit_maintenance.py`: `PhasingKeepingController`'s divergence guard could be reset by a schedule change mid-maneuver, handing a genuinely non-converging correction an unearned extra chance.** The guard's reset block (`suspendedDueToNonConvergence`/`_consecutiveNonConvergentCycles` cleared whenever the scheduled target separation changes, so a scripted reconfiguration gets a clean new attempt even after a previous target was given up on) ran unconditionally on every tick, gated only on the schedule value itself having changed -- not on `self.state`. The guard's own cycle-outcome judgment only happens once, at the `BURN_RESTORE -> IDLE` transition; if the schedule happened to tick over to a new entry while a cycle was still mid-maneuver (`BURN_OUT`/`DRIFT`/`BURN_RESTORE`), the reset fired before that cycle's own outcome was ever judged, wiping out the accumulated non-convergence count from every PRIOR cycle for a coincidence of timing, not an actual improvement -- letting a diverging correction keep burning propellant for longer than the guard is supposed to allow. Fixed by gating the reset to `self.state == self.IDLE` (the only state that actually reads `suspendedDueToNonConvergence` to decide whether to start a new correction): a schedule change mid-maneuver is no longer lost, it's simply evaluated once the controller is actually back in `IDLE`, against whatever the schedule's current value is at that point -- same outcome, no premature reset. New test, `test_phasing_keeping_schedule_tick_mid_maneuver_does_not_reset_the_guard` (`tests/test_orbit_maintenance.py`, `requires_basilisk`): drives the guard to one cycle short of tripping, forces a mid-maneuver state, ticks the schedule over, confirms the count survives intact, then finishes the cycle and confirms the guard still trips exactly on schedule. 27/27 passing against the real build.

**Smaller items, also fixed this round:**
- `gui/feedback.py`: `mark_invalid()`/`clear_invalid()` used to unconditionally overwrite/blank a widget's tooltip rather than saving/restoring whatever was there first -- currently unreachable (no call site sets a static tooltip before validation runs) but a latent trap for any future field with its own tooltip. Now stashes the pre-existing tooltip in a dynamic property and restores it. Two new tests in `tests/gui/test_feedback.py` (10/10 passing).
- `gui/main_window.py`: `_terminate_vizard_process()`'s docstring claimed waiting for the process to exit frees "the port it may have bound" -- factually wrong, per `docs/source/Vizard/vizardAdvanced/vizardLiveComm.rst`: `launch_vizard()` only ever starts the external Vizard GUI as a CLIENT that dials OUT to Basilisk's own `vizInterface` (the engine side, which is what actually binds the port). Comment-only fix, no functional change.
- `engine/link_budget.py`: `link_margin_series()` indexed `pointing_error_series`/`active_mode_series`/`range_series`/`access_series` by the same loop index with no length check -- currently safe (every recorder in this app shares one time grid today) but silently exploitable by a future independently-decimated recorder. Added a defensive `ResultsError` check, mirroring `TimeSeries.__post_init__`'s own existing guard for the identical failure shape.
- `README.md`: added six files missing from the "Repository layout" tree (`gui/startup_fetch_dialog.py` and five test files that existed but were never listed).

**Full suite**: 1056 passed, 155 skipped (`-m "not requires_basilisk"`, this sandbox's no-Basilisk default); the `requires_basilisk`-marked subset was re-run against the real Basilisk build (`/tmp/bsk_venv4`) used throughout this project, zero regressions.

---

## Thermal simulation: a "thermal" sensor kind and an optional reaction-wheel motor-thermal model

Next backlog item, picked up directly after the audit round above.

**Investigated before building anything**: Basilisk ships two real, already-compiled thermal modules this project had never used -- `sensorThermal.SensorThermal` (flat-plate radiative absorption/emission + an optional internal power draw, a real `TemperatureMsgPayload` output) and `motorThermal.MotorThermal` (a reaction wheel's own motor inefficiency/friction heat vs. ambient dissipation). A third, `tempMeasurement.TempMeasurement`, adds the same bias/noise/fault layer this project's other device-interface-realism sensors already have, chained onto either temperature source. Two real, shipped Basilisk example scenarios confirm the exact wiring: `examples/scenarioSensorThermal.py` (`sunInMsg`/`stateInMsg`/optional `sunEclipseInMsg`, confirmed optional directly against `sensorThermal.cpp`'s own `readMessages()` -- `illuminationFactor` just stays its constructor default of 1.0, "always fully lit", if left unconnected) and `examples/scenarioTempMeasurementAttitude.py` (`motorThermal.rwStateInMsg.subscribeTo(rwStateEffector.rwOutMsgs[item])` -- confirmed this is the PER-WHEEL message array, indexed by wheel-creation order, not the combined `rwSpeedOutMsg` this project's own `build_reaction_wheels` already uses elsewhere; and the real `tempMeasurement`/`TempFaultState_t` wiring).

**What was built**:
- `schema/scenario.py`: a new `"thermal"` entry in `SUPPORTED_SENSOR_KINDS` -- unlike every other sensor kind (each a real, distinct physical device), this models the temperature of ANY flat-plate component, so it's documented as the deliberate exception to "every kind maps to one real device" (see `test_device_catalog.py`'s matching exemption below). Required params (`nHat_B`, `area_m2`, `absorptivity`, `emissivity`) are schema-validated up front: confirmed directly against `sensorThermal.cpp`'s own `Reset()` that each has no safe default and hard-exits the whole process via `bskLogger.bskError` if left unset (the constructor deliberately sets them to `-1`). A matching `motor_thermal_*` params group on `"reaction_wheel"` actuators is validated the same way, as an all-or-nothing group: `motorThermal.cpp`'s own `Reset()` hard-exits on an unset `currentTemperature`/`ambientThermalResistance`/`motorHeatCapacity`, AND on `efficiency` outside the OPEN interval (0, 1) -- its own constructor default (`1.0`) is itself one of the rejected values, so motor-thermal fields are now all required together the instant any one is set, exactly mirroring this schema's existing `rw_type="custom"` defenses against the same class of hard-crash.
- `engine/fsw.py`: `attach_sensors()` gained a `"thermal"` branch (`sensorThermal.SensorThermal`, optionally chained into `tempMeasurement.TempMeasurement` for `measurement_bias_c`/`measurement_noise_std_c`/`measurement_walk_bound_c`/`measurement_fault_mode` -- `"none"`/`"stuck_current"`/`"stuck_value"`/`"spiking"`, the same naming convention `magnetometer`'s own fault_mode already uses; `TEMP_FAULT_BIASED`/`TEMP_FAULT_GAUSS_MARKOV` are real enum members but confirmed, directly against `tempMeasurement.cpp`'s own `applySensorErrors()`, to have no distinct effect beyond the always-applied bias/noise above, so they're deliberately not exposed). A new `build_reaction_wheel_motor_thermal()` builds one `MotorThermal` per wheel that actually sets the `motor_thermal_*` group (most have none), indexed into `rwOutMsgs` by the SAME `actuator_configs` order `build_reaction_wheels()` was just called with -- not `actuator.name`, which `rwOutMsgs` knows nothing about.
- `engine/service.py`: the shared eclipse-model build was moved earlier in the per-spacecraft loop (was previously built only after sensors were attached) so a `"thermal"` sensor's own `sunEclipseInMsg` can be given this spacecraft's real eclipse state instead of always reading "fully lit" -- a pure reordering, since `sunEclipseInMsg` is optional and every pre-existing power/station_keeping/enable_srp use of the eclipse message is unaffected. `needs_eclipse`'s own top-level gate (and the SPICE-sun precondition error it raises) was extended to include a `"thermal"` sensor. A new `rw_motor_thermal_recorders` dict on `_SpacecraftHandle` records whichever wheels actually got a motor-thermal model; `_extract_results()` gained matching series for both the `"thermal"` sensor kind (`{sc}.sensor.{name}.temperature`) and motor-thermal wheels (`{sc}.actuator.{name}.motor_temperature`).
- `gui/sensor_actuator_editor.py`: a `"thermal"` entry in `_KIND_PARAM_SPECS` (hint text, `nHat_B`'s own vector row, "Reset to template" inclusion -- the same in-dialog discovery every other sensor kind already gets), plus `motor_thermal_*` entries added to the existing `"reaction_wheel"` spec list.
- `gui/template_wizard.py`: a registered `TemplateWizardSpec` for the new template (below), keeping this project's own "every bundled template has a wizard" invariant intact (`test_every_bundled_template_has_a_registered_spec` would otherwise fail the moment a new template file existed without one).
- New template, `20_thermal_simulation.json`: `07`'s own full ADCS hardware suite (star tracker/IMU/CSS/three reaction wheels/power budget) plus a `"thermal"` sensor sharing the CSS's sun-facing normal (so it genuinely tracks real sunlight/eclipse cycles) and a motor-thermal model on exactly ONE of the three wheels (`rw-2`/`rw-3` deliberately have none, demonstrating this is per-wheel opt-in). `sim_settings.duration_days=0.3` at this orbit's ~100-minute period covers roughly 4 full orbits -- several complete heating/cooling cycles.

**A real numerical-stability gap caught by this round's own tests, not shipped**: the first draft of `tests/test_thermal_simulation.py` used a deliberately "simplified" thermal mass (`mass_kg=1.0`, `specific_heat_j_kg_k=1.0`, i.e. a 1 J/K heat capacity) to make the arithmetic easy to hand-check -- and that is numerically unstable: `sensorThermal`'s own explicit-Euler integration, at a 1 Hz task rate, pushed the temperature to `-8.8e+182` within 5 ticks once Q_in (~1366 W for a 1 m^2, fully-absorptive plate) massively overwhelms such a tiny heat capacity. Caught immediately by the test's own sanity assertion (`final_temp > 0.0` failing on an absurd negative exponential), before this was ever treated as a real result -- fixed by using the SAME realistic physical parameters `examples/scenarioSensorThermal.py` itself uses (`mass_kg=2.0`, `specific_heat_j_kg_k=890.0`, aluminum), which integrate cleanly. This is a real constraint of the module's own numerical method, not a bug in this project's code -- documented directly in the test file's own comment so a future test (or template) doesn't reintroduce it. A second, smaller gap: `simIncludeRW.rwFactory()`'s `"Honeywell_HR16"` named type hard-exits (`exit(1)`, not a catchable error) unless `maxMomentum` is also given -- already true of every other named-RW-type test in this suite, but newly hit here since this test module built its own reaction wheels from scratch; fixed by adding `maxMomentum=100.0` everywhere this test module builds a `Honeywell_HR16` wheel.

**Verified directly against the real Basilisk build** (`/tmp/bsk_venv4`): a new `tests/test_thermal_simulation.py` (13 tests) builds both modules directly against a bare `SimulationBaseClass` (same pattern as `tests/test_device_realism.py`/`tests/test_momentum_dumping.py`) and confirms, from real recorded output: a sun-facing `"thermal"` sensor heats up over several ticks and a sun-averted one does not (matching `examples/scenarioSensorThermal.py`'s own documented behavior); a real `EclipseMsgPayload` with `illuminationFactor=0` measurably reduces heating relative to no eclipse message at all; `power_draw_w` adds heat even with zero solar view; `measurement_bias_c`/`measurement_fault_mode="stuck_value"`/`"spiking"` (with `spike_probability=1.0` for determinism) each transform the true reading exactly as expected; `attach_sensors` raises a specific `FswError` for a `"thermal"` sensor with no sun ephemeris; `build_reaction_wheel_motor_thermal` returns nothing for a wheel with no thermal params, wires the CORRECT wheel index when only one of several wheels has them (not an off-by-one), reproduces `motorThermal.cpp`'s own exact closed-form Euler step for an idle (zero heat-generation) wheel cooling toward ambient, and shows a friction-enabled wheel ending up measurably warmer than an otherwise-identical frictionless one. Schema-level tests in `tests/test_scenario_schema.py` (9 new, 194 total) cover every validation path with no Basilisk needed. Full suite: 1074 passed, 2 skipped (`-m "not requires_basilisk"`), zero regressions; every one of the (now twenty) bundled templates, including the new one, round-trips through both the schema (`test_scenario_templates.py`) and the GUI editor/wizard (`test_scenario_templates_gui.py`/`test_template_wizard.py`).

---

## Design-philosophy audit + roadmap, and its first implementation step: run provenance

A direct request to review this app against an instrument-design philosophy (trust/correctness, GUI/script parity, time-as-first-class, analytical visualization, object model, progressive disclosure, expert efficiency, analysis workflow, long-run feedback, interoperability, reporting, config management, reliability, documentation, extensibility, modern directions). Phase 1 (`docs/ux_audit.md`) audited each principle with file:line evidence and ranked the top three places a result could be silently wrong: no run provenance, no active conservation/drift diagnostic beyond crash-translation, and units enforced only by naming convention. Phase 2 (`docs/ux_roadmap.md`) ranked every finding by (impact on trust) x effort into Quick wins/Medium/Strategic, with five flagged decisions (units enforcement, report format, plugin architecture, targeting/optimization, dark-mode-vs-palette) each given a recommendation. Both are read-only design documents, no code changed in that round.

**Phase 3, step 1 (Quick win Q1) -- run provenance on every result**, the highest-impact/lowest-effort finding: a `ResultSet` previously carried no record of what produced it, so two runs made months apart (possibly after a Basilisk/SpaceMissionStudio upgrade silently changed a module default) were indistinguishable after the fact.

**What was built**: a new, Basilisk-free `RunProvenance` dataclass (`engine/results.py`) -- `spacemissionstudio_version`, `basilisk_version`, `run_started_utc` (ISO 8601), `integrator`/`dynamics_task_rate_s` (from `sim_settings`), and a static `rng_seed_note` recording that every sensor/fault/noise model used Basilisk's own default `SysModel` `RNGSeed` (confirmed directly against `architecture/_GeneralModuleFiles/sys_model.h`'s `0x1badcad1` default) unless a Monte Carlo batch dispersed it -- `engine.monte_carlo` bypasses `ResultSet` entirely (it archives through `Basilisk.utilities.MonteCarlo.RetentionPolicy` instead), so this field is only ever populated for an ordinary `run()`/`run_live()` result, never a Monte Carlo one. `ResultSet` gained an optional `provenance` field (`None` for any hand-built/synthetic result, e.g. in a test). `SimulationService.build()` now captures a UTC timestamp the moment it starts (the one point every call path -- `run()`, `run_live()`, `MissionEngine.run()` -- reaches immediately before `ExecuteSimulation()`); `_extract_results()` populates `provenance` from that timestamp plus `Basilisk.__version__` and `spacemissionstudio.__version__`. `ResultSet.export_csv()` writes a `provenance.json` sidecar alongside the existing per-series CSVs -- a SEPARATE file, not an extra header/row injected into the existing CSV format, so nothing already parsing those CSVs is affected. `cli.py`'s `cmd_run` picks this up automatically (it already iterates `export_csv()`'s returned paths). `gui/results_widget.py` shows a one-line, tooltip-backed summary ("SpaceMissionStudio 2.0.0 - Basilisk 2.12.0 - rkf78 @ 10 s - run started ...") above the plot, blank when `provenance` is `None`.

**Verified**: `Basilisk.__version__` confirmed to actually exist and read `"2.12.0"` directly against this project's own real venv (`/tmp/bsk_venv4`) before relying on it -- not assumed. New tests in `tests/test_results.py` (provenance defaults to `None`; `export_csv` writes no sidecar without it; writes a byte-exact JSON sidecar with it; still writes the sidecar when a `ResultSet` has provenance but zero series, confirming `export_csv` doesn't skip its own `mkdir` in that edge case) and `tests/gui/test_results_widget.py` (label blank/populated/cleared correctly, tooltip carries the RNG note). Full non-Basilisk suite: 1081 passed, 2 skipped, zero regressions. The `service.py`/`cli.py` wiring that actually populates `provenance` end-to-end needs a full `SimulationService.build()` run, which needs SPICE kernels -- this sandbox's one standing, already-documented limitation (network access to NAIF is blocked here; see this file's own "Environment honesty note" at the top) -- so that specific path is verified by direct inspection (`Basilisk.__version__`/`spacemissionstudio.__version__` import and attribute-access confirmed against the real venv) rather than an end-to-end run, same honesty standard as every other Basilisk-dependent feature in this file that hit the identical limitation.

---

## Phase 3 step 2 (Medium M1): a post-run conservation/drift diagnostic

The audit's #2-ranked trust gap: the only numerical-health signal this app had was translating a hard Basilisk integrator crash (NaN/inf) into a clear error (`engine/service.py`'s `raise_clear_execution_error`) -- a FINITE but wrong result (a too-coarse timestep silently drifting, not crashing) shipped with no flag at all. This session's own thermal-sensor bug earlier (`-8.8e+182` from an unrealistic heat capacity) was exactly this failure shape, caught only because a test happened to assert a sign.

**What was built**: a new, Basilisk-free `conservation_drift_warnings(name, mu, r_m, v_m, energy_tol=0.01, momentum_tol=0.01)` (`engine/results.py`) -- computes specific orbital energy (`v^2/2 - mu/r`) and orbital angular-momentum magnitude (`|r x v|`) from a recorded position/velocity time history, both EXACTLY conserved for true two-body motion, and returns a human-readable warning for either one if it drifts more than a generous, deliberately coarse 1% from its own first-sample value -- loose enough to catch a genuine blowup (orders of magnitude) without grading an integrator's own fine-grained truncation error. `ResultSet` gained a `warnings: List[str]` field (always empty for a hand-built result; informational only, never raised as an exception, never blocks a run). A new, equally conservative gate, `engine.service._is_two_body_only(scenario, sc_config)`, decides per-spacecraft whether this check is even MEANINGFUL: `False` (check skipped entirely) the moment `gravity.central_body_degree != 0`, `third_body_perturbers` is non-empty, `scenario.mission_sequence` is non-empty (a `maneuver`/`lambert_transfer` command's own deliberate, instantaneous delta-V is a real "jump" this check cannot distinguish from a bug, so the whole scenario is excluded rather than trying to prove no command targets this specific spacecraft), or this spacecraft has `enable_drag`/`enable_srp`/`station_keeping`/`constant_thrust`/`phasing_keeping`/`comms_pointing`/`fuel_tank`/`momentum_dumping` set or a `"thruster"` actuator -- every one of those is a REAL, legitimate translational-force/delta-V source, so a drift under any of them is expected physics, not a numerical-health signal. A `"reaction_wheel"`/`"magnetic_torque_rod"` actuator does NOT disqualify the check (pure torque, no net force on the center of mass). `SimulationService._extract_results()` calls this gate once per spacecraft (reusing the position/velocity arrays it already reads for the `.position_N`/`.velocity_N` series -- no new Basilisk calls) and extends `result.warnings` when it applies and trips. `cli.py`'s `cmd_run` prints each warning to stderr without affecting the exit code; `gui/results_widget.py` shows them in a hidden-when-empty banner above the plot, reusing this app's one existing "needs attention" color (`PALETTE["danger"]`, the same color `gui/feedback.py`'s error toasts already use) rather than inventing a second semantic color -- updated on every `set_live_result()` call (not just the first, and not throttled like the webview redraw), since a drift can only become detectable after enough samples have accumulated.

**Verified**: new tests in `tests/test_results.py` -- an exact (to floating-point precision) analytically-generated circular two-body orbit produces zero warnings; an orbit with deliberately injected velocity-magnitude growth (simulating exactly the silent-blowup failure shape this exists to catch) trips both the energy and momentum checks; a too-small sample count returns no warnings rather than crashing; a custom, tighter tolerance catches a drift the default 1% tolerance correctly lets through. A new `tests/test_conservation_check.py` (10 tests, `requires_basilisk` -- importing `engine.service` at all needs a Basilisk install, even though `_is_two_body_only` itself calls no Basilisk API) exercises every disqualifying condition individually against real `Scenario`/`SpacecraftConfig` objects, run against the real build (`/tmp/bsk_venv4`): 10/10 passing, confirming reaction wheels don't false-positive-disqualify the check while every real perturbation/thrust source does. `tests/gui/test_results_widget.py` covers the banner showing/hiding correctly. Full non-Basilisk suite: 1086 passed, 2 skipped, zero regressions (one single-run QtWebEngine-teardown flake reproduced once across this whole session's many GUI-test runs, not reproducible on a second run, consistent with a known headless-QtWebEngine flakiness pattern rather than a code regression). A broader sweep of real-build tests this change's `_extract_results()` edit could plausibly affect (`test_device_realism.py`, `test_css_estimation.py`, `test_mtb_desaturation.py`, `test_momentum_dumping.py`, `test_thruster_control.py`, `test_fuel_tank.py`, `test_orbit_maintenance.py`, `test_thermal_simulation.py`, `test_formation.py`, `test_lambert_transfer.py`, plus the new `test_conservation_check.py`): 92/92 passing.

---

## Phase 3 step 3 (Quick win Q3): generous plausibility bounds on the highest-risk numeric fields

A smaller, lower-effort step toward the audit's #3-ranked trust gap ("units enforced only by naming convention") -- not the full type-level unit system that finding's own "decision needed" in `docs/ux_roadmap.md` deferred (new dependency, large regression surface), but a cheap, purely additive mitigation: several fields where a plausible-but-wrong magnitude (a units mixup -- cm^2 for m^2, grams for kilograms, mW for W) would previously validate cleanly and run silently, since the only existing check was a bare `> 0`.

**What was built**: a generous (10-1000x realistic) upper bound added alongside each field's existing sign check in `schema/scenario.py` -- `PowerConfig.panel_area_m2` (<= 2000 m^2, vs. the ISS's own ~2500 m^2 of combined arrays), `PowerConfig.battery_capacity_wh` (<= 1e6 Wh), `RFLinkConfig.tx_power_w` (<= 1e4 W, real spacecraft downlinks are typically under 100 W), `SpacecraftConfig.dry_mass_kg` (<= 1e6 kg, well above the ISS's ~4.2e5 kg, the largest crewed structure ever assembled), `SpacecraftConfig.drag_area_m2`/`srp_area_m2` (<= 1e4 each), and the `"thermal"` sensor's `area_m2` (<= 1000) and optional `mass_kg` (<= 1e4, only checked when actually set -- it stays genuinely optional). Each message explicitly names the likely unit mixup, mirroring this schema's own established "specific, actionable message" style. Deliberately NOT extended to orbital-distance fields (`semi_major_axis_km` and similar): those are central-body-dependent (a heliocentric or Jupiter-orbit scenario can legitimately need a semi-major axis in the hundreds of millions of km, where an Earth-orbit scenario needs thousands), so a single universal bound would either be too loose to catch anything or would reject a real scenario -- correctly scoped as part of the deferred full-unit-system work instead, not a quick-win candidate.

**Verified**: nine new tests in `tests/test_scenario_schema.py` (one "too large -> rejected" case per field, plus a "mass_kg unset -> still validates" case confirming the bound doesn't make an optional field required) -- 203/203 passing. Critically, `tests/test_scenario_templates.py` (every one of the twenty bundled templates, round-tripped through `Scenario.validate()`) passes completely UNMODIFIED, confirming none of these new ceilings are anywhere close to tripping on a real, shipped scenario. Full non-Basilisk suite: 1095 passed, 2 skipped, zero regressions. `tests/test_device_catalog.py`/`tests/gui/test_scenario_templates_gui.py`/`tests/gui/test_template_wizard.py` (which build sensors/actuators from real catalog/template params against these same fields) also pass unmodified.

---

## Phase 3 step 4 (Quick win Q2): a search/filter box on the Mission Output tab

The audit's own §7/§9 finding: `gui/mission_output_widget.py`'s report-command text log had no way to search/filter it -- the neighboring Results tab already had a searchable series combo, but this tab was a plain, unfiltered `QPlainTextEdit`.

**What was built**: a `QLineEdit` filter row above the text log (`filter_edit`, placeholder "Filter by label, series name, or value..."), matching on the FULL text of each report block (its `[i] t = ... (label)` header plus every one of its series/value lines), case-insensitively -- so a search can hit a label, a series name, OR a value, not just one of those. A matching report's entire block is shown (never a bare value line with its header stripped, which would lose the context of which report/time it belongs to); when the filter is non-empty, a `"(N of M report(s) match '...')"` line makes the match count visible. The filter is deliberately VIEW-only: `_on_export()` always exports every report regardless of the active filter (mirrors this app's own Results tab, where a displayed series's own filtering is cosmetic and never silently narrows what CSV export writes) -- the export button's tooltip says so explicitly. `clear()` (called between runs) also clears the filter box, so a stale filter from a previous run's output can't silently hide a new run's results.

**Verified**: seven new tests in `tests/gui/test_mission_output_widget.py` -- filtering hides non-matching reports and shows the match count; a search term matches a series name/value, not just a label; clearing the filter text restores the full list; the filter is case-insensitive and still applies correctly to a freshly-set summary; the export button's tooltip mentions the filter; and, the one test most worth having, export still writes every report (including one the active filter is currently hiding) to CSV. 13/13 passing in that file; full non-Basilisk suite: 1102 passed, 2 skipped, zero regressions.

---

## Phase 3 step 5 (Medium M2): SVG export alongside PNG for the Results plot

The roadmap's M2 item: `gui/results_widget.py` already had a "Save plot as PNG..." button, but a PNG is a raster -- dropping one into a paper or report and then scaling it up (or printing it) goes blurry. A vector export has no such ceiling.

**What was built**: a new "Save plot as SVG..." button next to the existing PNG one, sharing its entire dialog/kickoff/poll machinery rather than duplicating it -- `_on_save_plot_png()` gained an `fmt: str = "png"` parameter (every existing zero-argument call site, including every existing test, keeps behaving exactly as before); `_on_save_plot_svg()` is a one-line wrapper calling it with `fmt="svg"`. The in-page JS kickoff now asks Plotly for `{format: fmt, scale: 2}` instead of a hardcoded `'png'`; `_png_poll_state` carries the requested `fmt` through `_poll_plot_png()` to `_on_plot_png_rendered(data_url, path, fmt)`, which decodes PNG and SVG differently because Plotly's own JS encodes them differently -- confirmed directly against the installed `plotly.min.js` bundle's own `encodeSVG` function (`"data:image/svg+xml," + encodeURIComponent(svgText)`), NOT assumed: unlike the PNG path's `data:image/png;base64,...` (decoded with `base64.b64decode`), the SVG data URL is plain percent-encoded TEXT with no base64 anywhere, decoded with `urllib.parse.unquote(...)` and written with `Path.write_text(..., encoding="utf-8")`. Every place the existing code toggled `save_png_button`'s enabled state (the redraw path's re-entrancy guard, the click handler's own disable-on-click, both completion paths of the poll) now toggles the new `save_svg_button` in lockstep, since both buttons share the same `_png_poll_state`/page-global JS result variable -- a concurrent click on either one while the other's poll is in flight would orphan the first poll's `QTimer` exactly as a second PNG click already could before that guard existed (see this file's own PNG-save re-entrancy bugfix entries earlier in this project).

**Verified**: five new tests in `tests/gui/test_results_widget.py`, mirroring the existing PNG suite's own structure -- an end-to-end real-plotly.js render producing a real `<svg>...</svg>` text file (not mocked JS, not a PNG magic-bytes check but the SVG equivalent: the file actually starts with `<svg` and contains a closing `</svg>` tag); the `.svg` extension is appended when missing; a no-result click is a no-op; a click on either save button while the OTHER button's poll is in flight is also a no-op (the shared-guard case specific to having two buttons now); and `_redraw()` during a live update does not re-enable `save_svg_button` while a poll is in flight, mirroring the existing PNG regression guard. 46/46 passing in that file (41 previous + 5 new); full non-Basilisk suite: 1107 passed, 2 skipped, zero regressions. This module imports no Basilisk (same Basilisk-free design as the rest of `gui/results_widget.py`), so no real-build verification was needed or applicable here.

---

## Phase 3 step 6 (Medium M3): validated the colorblind-safe plot palette, and fixed a stale audit claim

Starting this roadmap item ("define a validated categorical palette... apply it as Plotly's colorway") turned up that its own premise was already out of date: `gui/results_widget.py`'s `_SERIES_COLORS` -- a fixed, deliberately chosen 8-hue list already applied via `_SERIES_COLORS[i % len(_SERIES_COLORS)]` to every multi-series plot's line colors -- was added in the matplotlib->Plotly migration on 2026-09-30 (confirmed via `git log -S`), five days BEFORE this session's own Phase 1 audit (`docs/ux_audit.md`, written 2026-10-05) incorrectly listed "no deliberately colorblind-safe categorical palette... rely on Plotly's default color cycle" as Missing. The plots never used Plotly's default cycle in the first place.

**What was actually done**: the genuinely missing piece -- the palette's own comment CLAIMED it "clears the >= 8 [CVD Delta E] target in both light and dark mode" but that claim had never actually been run through the `dataviz` skill's validator against THIS app's own chart surface. Running `scripts/validate_palette.js` for real: light mode (`--surface "#FFFFFF"`, this module's actual `_SURFACE` constant) PASSES every check (worst-adjacent CVD Delta E 9.1 protan / 5.8 tritan, worst-pair normal-vision Delta E 19.6, one WARN on contrast-vs-surface that this app's own existing "legend always shown for >1 column" behavior already satisfies as the required relief). Dark mode, which the old comment claimed also passed, in fact FAILS the lightness-band check on 4 of the 8 hues when actually run -- moot for THIS app specifically, since `gui/theme.py` has no dark theme to validate against at all (confirmed, `docs/ux_audit.md`'s own §4 "Missing" item), but the old comment's unverified claim was simply wrong and is corrected. `docs/ux_audit.md` and `docs/ux_roadmap.md` both gained a correction note documenting this (pre-existing palette, pre-existing PNG export now also resolved by M2) rather than silently leaving the stale "Missing" language in a document whose whole purpose is an accurate trust audit.

**Verified**: a new `test_series_colors_palette_is_8_distinct_valid_hex_colors` (`tests/gui/test_results_widget.py`) -- deliberately NOT a `node`-subprocess test (this Python project has no other Node.js dependency in its own test/build pipeline, and one specific color-contrast assertion doesn't justify adding one; the roadmap's own M3 item explicitly offered "a one-time check documented in a comment" as the alternative, used here) -- guards the shape that matters going forward (8 distinct, valid hex strings) so a future accidental edit can't silently corrupt the list without the validator being re-run by hand. Full non-Basilisk suite: 1108 passed, 2 skipped, zero regressions.

---

## Phase 3 step 7 (Medium M4): autosave / crash recovery for scenario edits

The audit's own §13 gap: this app's existing unsaved-changes protection (`_confirm_discard_unsaved`'s prompt on New/Open/close) only ever fires on a CLEAN exit path -- anything that took the process down before that point (a Basilisk crash, a segfault, a killed process) lost whatever was being edited entirely, with nothing left behind to recover.

**What was built**: a new, deliberately Qt-free `gui/autosave.py` -- `write_recovery_file(scenario, original_path)`/`clear_recovery_file()`/`read_recovery_file() -> Optional[RecoveryInfo]`, operating on one FIXED recovery slot (`~/.spacemissionstudio/autosave/recovery.json`, matching `logging_setup.py`'s own per-user directory convention) rather than one-per-scenario, since this app only ever edits a single scenario at a time (one `MainWindow`, no MDI). The envelope written is `{original_path, saved_at_utc, scenario: scenario.to_dict()}`; reading it back runs the SAME `migrations.migrate()` -> `Scenario.from_dict()` -> `.validate()` pipeline `schema.load_scenario()` uses for a real file, so a recovery file is always restorable exactly the same way a normal saved one is -- and anything that fails that pipeline (missing/corrupt/hand-edited/an invalid embedded scenario) is treated as "nothing to offer," never a crash of this feature on top of the very crash it exists to help recover from. Writing and clearing are both best-effort: an `OSError` is logged and swallowed, never raised into the caller, so a full disk or a permissions problem can't interrupt the user's actual work or spam an error dialog on a 30-second timer they never directly triggered.

`gui/main_window.py` wires this in with two new pieces: a `QTimer` (`_AUTOSAVE_INTERVAL_MS = 30_000`, started unconditionally in `__init__`) whose `_on_autosave_tick()` no-ops unless the editor is dirty, and SILENTLY skips a tick where `ScenarioEditorWidget.to_scenario()` currently raises `ScenarioValidationError` (a transiently-invalid mid-edit state, e.g. a blank required field) rather than surfacing anything -- the next tick simply tries again once the edit settles. `_mark_clean()` -- the one chokepoint every Save/New/Open/discard already funnels through -- now also calls `clear_recovery_file()`, so a recovery file only ever exists while there's genuinely something unsaved to recover; this closes the roadmap's own flagged risk ("stale recovery files prompting forever would be worse than not having the feature") by construction rather than by a separate cleanup pass. On the NEXT launch, a new `_check_autosave_recovery()` (fired via `QTimer.singleShot(0, ...)`, same pattern the existing startup kernel-fetch consent dialog already uses, so the window is visible before the modal appears) offers to restore it (`QMessageBox` with `Open`/`Discard` buttons -- there's no literal "Restore" standard button in Qt, and the dialog's own text names what's being restored). Accepting loads the recovered `Scenario` into the editor and sets `self._current_path` to the recovery's `original_path` (which may be `None`, for a scenario that had never been saved) -- but marks the window DIRTY, not clean: the recovered content is exactly the UNSAVED state from right before the crash, so it genuinely still needs an explicit Save before it's safe on disk again. Declining clears the recovery file immediately (same as an explicit discard elsewhere in this app) rather than prompting again every subsequent launch. A new `check_autosave_recovery: bool = True` constructor parameter mirrors the already-established `prompt_startup_fetch` opt-out convention for headless/test construction.

**Verified**: a new `tests/test_autosave.py` (11 tests, no `QApplication` needed, isolated to a `tmp_path` recovery location via an autouse fixture that monkeypatches the module's own path constants -- this module must never touch a real developer's or user's actual home directory from an automated test run) -- write-then-read round-trips both the scenario and the original path (including `None`); clearing removes the file and is a no-op when nothing is there; a missing, corrupt-JSON, non-dict, or structurally-malformed (missing the `"scenario"` key) recovery file, and one whose embedded scenario itself fails `validate()` (e.g. a hand-edited negative mass), all return `None` rather than raising; a write or clear failure (`OSError`/`PermissionError` from the underlying filesystem call) is swallowed, not propagated. Eight new `tests/gui/test_main_window.py` tests (added to a new file-wide autouse fixture giving every existing test in that file the same `tmp_path` isolation, since this file's own `window` fixture constructs a real `MainWindow`) cover the tick no-op/write/skip-while-invalid cases, that both Save and a discard-confirmed New clear the recovery file, that the startup check with nothing pending is a no-op, and both the accept (restores + marks dirty + preserves `original_path`) and decline (clears the file, leaves the editor untouched) paths of the restore prompt. All ~90 pre-existing `tests/gui/test_main_window.py` tests pass completely UNMODIFIED except the one `window` fixture, which needed exactly one new keyword (`check_autosave_recovery=False`) alongside its existing `prompt_startup_fetch=False` -- confirming the new always-running timer genuinely doesn't interfere with anything already tested. Full non-Basilisk suite: 1127 passed, 2 skipped, zero regressions.

---

## Phase 3 step 8 (Medium M5): a combined ground-station access timeline view

The audit's §3 Gantt gap, scoped down per the roadmap's own call: rather than a general-purpose linked-timeline framework (Strategic-tier scope), one more chart inside the existing Results tab -- "most of the value of 'see access windows at a glance' comes from one more chart, not a new interaction model."

**What was built**: a new "View:" combo (`gui/results_widget.py`) next to the existing per-series dropdown, with two options: "Single series" (the existing, unchanged behavior, still the default) and "Ground station access timeline." The timeline view combines EVERY `{gs}.access_to_{sc}.has_access` series already in the result into one Gantt-style chart -- one categorical y-axis row per station/spacecraft pair, each contiguous access window drawn as a thick (`width=16`) two-point `go.Scatter` line segment rather than `go.Bar(orientation="h")`: a plain two-point line needs no base/width unit-matching against the x-axis (numeric elapsed-time or, if it ever needed to, a datetime axis), where a horizontal bar's would. A pair with NO access window at all over the whole run still gets an invisible placeholder trace so it still appears as its own labeled row rather than silently vanishing from the chart -- a real, deliberate corner case, not an oversight (a scenario could easily have one ground station that a given spacecraft's orbit never actually passes over). A result with no access-pair series at all (no `ground_stations` configured) shows an explanatory empty-state annotation instead of a blank chart. The x-axis is DELIBERATELY always elapsed time, ignoring the existing `x_axis_combo` -- a horizontal line's two endpoints work identically whether the x-axis is numeric or datetime, but committing to one simpler axis type avoided ever having to reconcile "epoch mode" with the per-row category axis, and the timeline's whole value (seeing every pass at a glance) doesn't need UTC timestamps the main single-series view doesn't lose. Switching views disables `series_combo` (inert in the timeline view) and the PNG/SVG save buttons' default filename becomes `access_timeline.png`/`.svg`. `_parse_access_pair()` was factored out of the pre-existing `_access_pair_display()` so both now agree, via one shared function, on exactly which series count as "an access-pair series."

**Explicitly NOT built**, matching the roadmap's own hedge ("clicking a bar COULD set the x-axis range on the main plot"): the click-to-jump interaction linking a clicked bar back to the main plot. This app has no JS<->Python click bridge (`QWebChannel`) anywhere yet -- the existing PNG/SVG export flow only ever reads a page-global JS variable back via polling, never reacts to a click -- and building one for this single interaction would be a far bigger lift than the timeline chart itself; the roadmap's own rationale already named the chart alone as the cheaper, sufficient scope.

**Verified**: 8 new tests in `tests/gui/test_results_widget.py` -- the view combo defaults to "Single series"; switching disables/re-enables `series_combo` correctly; the combined chart produces the right trace count per pair (including the always-present no-access placeholder row for a pair with zero windows); the no-access-series-at-all case shows the empty-state annotation; the x-axis stays elapsed time even when `x_axis_combo` is explicitly set to Epoch; switching back to "Single series" restores the exact previous series selection and plot; the PNG save dialog's default filename becomes `access_timeline.png` in that view; and a real end-to-end check that the generated HTML actually loads in the offscreen `QWebEngineView` without error (catches a figure that builds fine as a Python object but would be malformed Plotly JSON, which the other, Python-object-level assertions can't). All 47 pre-existing tests in that file pass completely UNMODIFIED. Full non-Basilisk suite: 1134 passed, 2 skipped, zero regressions.

This completes every item in the user-approved Phase 3 sequence (Q1 -> M1 -> Q3 -> Q2 -> M2/M3 -> M4 -> M5). Everything remaining in `docs/ux_roadmap.md` is Strategic-tier and explicitly gated on a decision from the user before starting, per that document's own Decisions section.

---

## Real UI regression fix: Results tab's top row was squeezing the Series combo to unreadable fragments

Caught directly from a real screenshot of the running app (template 19), not a test: the Series combo (`gui/results_widget.py`) was showing only a few garbled characters (e.g. ",powerS") of whatever series was selected, instead of its real name (e.g. "leo-comms-1.battery_net_power"). Root cause: every control on the Results tab's top row -- the View/Series/X-axis combos AND all three action buttons (Export, Save PNG, Save SVG) -- shared one `QHBoxLayout`. Adding the "View" combo (roadmap item M5) and the "Save plot as SVG..." button (roadmap item M2) earlier this session, on top of what was already a fairly full row, pushed total width demand past what the Results panel (never full window width -- it shares a splitter with the Scenario Editor) actually has. Qt's layout resolved that overflow by shrinking `series_combo` (the one widget with `stretch=1`, i.e. the one actually meant to use leftover space) down toward its minimum size rather than shrinking anything else -- which is exactly backwards from what a user needs, since that's the ONE control whose content (a real series name, sometimes 40+ characters long) is the least tolerant of truncation.

**Fix**: split the row into two -- "what am I looking at" (View/Series/X-axis combos) stays on its own row with nothing else competing for its space, and "do something with it" (Export/Save PNG/Save SVG buttons) moved to a new row below. `series_combo` also gained an explicit `setMinimumWidth(220)` as a second, independent safety margin, so even a genuinely narrow window can't squeeze it back down to unreadable -- the row before this fix had no floor on it at all, which is the same underlying gap that let this regression happen invisibly (every automated test constructs the widget off-screen or at a generous default size, so none of them would ever have caught a real window's width pressure).

**Verified**: all 55 `tests/gui/test_results_widget.py` tests pass unmodified (purely a layout change -- no widget was removed or renamed, so nothing the existing tests reference moved). Additionally confirmed VISUALLY, not just via passing tests: rendered the real widget off-screen at both an 820px and a 600px panel width (matching the proportions in the reported screenshot) and grabbed a screenshot of each -- the full series name now displays correctly at both widths, with the three action buttons clearly separated onto their own row beneath. Full non-Basilisk suite: 1135 passed, 2 skipped (one single-run QtWebEngine-teardown crash reproduced once, same known flake pattern already documented elsewhere in this file -- confirmed non-reproducible on an immediate re-run, clean 1135/2).

---

## Real UI bug fix: a huge blank gap above the Results plot, pushing the actual chart off-screen

Caught from a second real screenshot of the running app (template 05, formation flying): a large blank area sat between the provenance/button rows and the actual Plotly chart, with the chart itself continuing well past the bottom of the visible window (a scrollbar was needed to see any of it).

**Root cause, confirmed by directly inspecting live Qt widget geometry (not guessed at)**: `provenance_label` and `web_view` both default to `QSizePolicy.Preferred` vertically with a stretch factor of 0 -- `gui/results_widget.py`'s `QVBoxLayout` had no explicit stretch factors anywhere to break that tie. Qt's layout engine resolved the resulting ambiguity by handing almost ALL of the column's leftover vertical space to the one-line `provenance_label` (confirmed directly: its allocated geometry was 386px tall at a 950px window height, for a label whose own `sizeHint()` is 14px) while `web_view` stayed pinned at its generic, content-independent default `sizeHint()` of 640x480 -- exactly backwards from the obviously-intended behavior (the label should stay compact; the chart should fill whatever room is left).

**Fix**: `provenance_label` and `warnings_label` both get an explicit `QSizePolicy(Preferred, Fixed)` (pinning them to their own natural height regardless of surplus space), and `web_view` is now added with `layout.addWidget(self.web_view, stretch=1)` -- the standard, deterministic Qt mechanism for "this widget gets all the leftover space," rather than relying on size-policy tie-breaking that turned out not to behave as expected here.

**Verified**: reproduced the exact bug first -- rendered the real widget off-screen at a 1210x950 window (matching the reported screenshot's proportions) with real provenance text set and inspected `provenance_label.geometry()` directly: `QRect(11, 67, 1188, 386)`, confirming the 386px overgrowth non-anecdotally before writing any fix. After the fix, the same inspection shows `web_view.geometry()` = `QRect(11, 87, 1188, 852)` -- claiming the correct leftover space -- and a fresh screenshot shows the chart filling the window immediately below the button row, with zero blank gap. `tests/gui/test_results_widget.py`: 55/55 passing unmodified. Full non-Basilisk suite: 1135 passed, 2 skipped, zero regressions.

---

## Real bug fix: StationKeepingController cold-start altitude-smoothing bias corrupts phasing-keeping

A user, watching a real run of `05_formation_flying_phasing.json` live in Vizard, flagged that the "R vs chief-1"/"T vs chief-1" `GenericStorage` panels were both pinned at their 100 km ceiling partway through a 7-day run -- not just the previously-investigated along-track-overshoot issue (see this file's earlier "phasing-keeping along-track separation overshoots target badly" entry), but now the RADIAL separation too, which this controller never actively manages and should stay near zero for two near-identical coplanar orbits.

**Root cause, found by reproducing the template with REAL Basilisk dynamics** (point-mass Earth gravity, both the default fixed-step integrator and the production `rkf78` -- confirmed identical results either way, ruling out integrator truncation error as a factor) and instrumenting `PhasingKeepingController`'s own `lastRadialKm`/`lastTransverseKm`/`errorDegLog` directly: the along-track separation diverged monotonically from -60 km to -595 km over 7 days (more than 10x the 50 km target, in the WRONG direction) while the controller sat frozen in its DRIFT state for the entire run, having fired exactly one, correctly-computed 0.057 m/s correction burn that should have been converging the error, not growing it.

Tracing the discrepancy down to the actual semi-major-axis history (not just the controller's own interpretation of it) found the true cause: NOT a sign error in phasing-keeping's own control law (confirmed correct by hand-deriving the deltaA/burn-direction chain and by independently confirming the applied burn direction against Basilisk's real dynamics), but a cold-start bug in the CO-LOCATED `StationKeepingController`, which shares the same thruster. `StationKeepingController.UpdateState()`'s "orbit-period boxcar smoothing" (`_altHistory`, meant to "reject short-period altitude oscillation and only respond to secular decay") starts EMPTY on every `Reset()` -- so at the very first tick, the smoothed altitude is averaged over exactly ONE sample: the raw osculating altitude at whatever point in the orbit the spacecraft happens to start. The template places both spacecraft AT PERIGEE (`true_anomaly_deg: 0`/`-0.5`), where the osculating altitude is genuinely, normally below the orbit's mean -- nothing secular is wrong at all. With only one sample in the averaging window, that single low perigee reading alone was enough to trip `burnOn = True` immediately, and the controller then burned continuously for roughly half an orbital period (confirmed: exactly 96 ticks x 30s = 2880s, matching the window's own fill time) before the smoothing average caught up -- injecting a real, unintended ~540 m semi-major-axis change into the follower's orbit purely as a filter-startup artifact. `PhasingKeepingController` has no way to distinguish that perturbation from a genuine orbital anomaly, and its own correctly-sized correction burn was overwhelmed by it from that point on.

**Fix** (`engine/orbit_maintenance.py`, `StationKeepingController`): a new burn may only START once the altitude-history window actually holds a FULL orbital period of real samples (tracked via a new `_historyStartT`, set once on the first tick after `Reset()` -- NOT measured against the oldest entry still in the pruned window, which structurally can never itself reach the window length and would make the guard permanently unsatisfiable; this exact mistake was caught and fixed during this same session, before it shipped, by the regression tests below). The symmetric burn-STOP condition is left untouched -- it only matters once a burn has legitimately started, by which point the window is always full. This delays reacting to a genuinely real altitude deficiency at simulation start by at most one orbital period, which is consistent with, not a new tradeoff against, this controller's own stated purpose of responding only to secular decay (which by definition unfolds over many orbits anyway).

**Verified**: re-running the same real-dynamics 7-day reproduction with the fix applied: ZERO spurious station-keeping burns (`skBurnOn` never true), max radial separation drops from 26.1 km to 0.37 km, and the along-track separation now converges smoothly and monotonically from -60 km toward the 50 km target (reaching -20 km by day 7, correctly trending toward target instead of diverging away from it) -- the controller's own `errDeg` metric shrinks monotonically too, matching. Two new regression tests in `tests/test_orbit_maintenance.py` (`test_station_keeping_cold_start_does_not_spuriously_burn_on_one_low_sample`, confirming a single below-deadband sample no longer trips `burnOn`; `test_station_keeping_cold_start_guard_only_gates_the_start_not_the_stop`, confirming an already-in-progress burn still exits immediately and isn't delayed by this fix) plus an existing test (`test_station_keeping_publishes_delta_v_message_after_update`) updated to run a full settle phase first, since its old "burns on the very first tick" premise is exactly the bug this fixes. Three mass-bookkeeping tests in `tests/test_orbit_maintenance_true_mass.py` needed a matching update (a settle phase before the measured tick, plus real point-mass gravity attached -- their spacecraft previously coasted ungoverned with no gravity at all, harmless for a single-tick test but not for a multi-thousand-second settle phase) -- all three pass with real per-tick dv/mass deltas isolated via before/after snapshots rather than the old single-tick cumulative values. Full `tests/test_orbit_maintenance.py` (29/29) and `tests/test_orbit_maintenance_true_mass.py` (3/3) pass; a broader sweep (`pytest -k "station_keeping or orbit_maintenance or formation or phasing"`, 144 tests) shows exactly two pre-existing failures, both confirmed (via `git stash`) to fail identically without this fix -- this sandbox's standing, already-documented SPICE/no-network limitation, unrelated to this change. Full non-Basilisk suite: 1135 passed, 2 skipped, zero regressions.

---

## Two real bugs found from the first genuine full-suite run on a real (non-sandbox) dev machine

The user ran the full suite for real for the first time this session, on their own machine with a real Basilisk install, real SPICE kernels, and a real, persistent filesystem -- none of which this project's own development sandbox has ever had. Result: 1301 passed, 11 skipped, 3 failed. Two of the three failures were real, previously-undetectable-in-this-sandbox bugs (the third was this session's own, already-known, already-documented SPICE/no-network sandbox gap re-surfacing under a different test name -- not investigated further here).

**Bug 1 -- `gui/propagation_setup_dialog.py`'s "cached startup fetch" prefill read the REAL filesystem cache, un-isolated, in every test built on the plain `dialog` fixture.** `PropagationSetupDialog.__init__` calls `engine.spaceweather.cached_fetch_path()` directly to decide whether to pre-fill its local-file field -- correct production behavior, and already correctly tested with its own `monkeypatch` in the three tests that specifically exercise it. But the SHARED `dialog`/`_dialog()` fixture used by most of this file's other tests never isolated that same call, so every one of them (e.g. `test_defaults_round_trip`, which asserts a pristine `SpaceWeatherConfig()` round-trips with `local_file_path=None`) was silently depending on whatever happened to be in `~/.cache/SpaceMissionStudio/spaceweather/` on whatever machine ran the tests. This sandbox's own ephemeral container never had anything cached there, so the gap was invisible here; the user's real, persistent dev machine had genuinely already run the startup-fetch flow before, populating that cache for real -- exactly the scenario this test suite should have been resilient to from the start.

**Fix**: a new file-wide `autouse=True` fixture in `tests/gui/test_propagation_setup_dialog.py` defaults `cached_fetch_path` to "no cache" (`None`) for every test, closing the isolation gap at its root rather than patching each affected test individually; the three tests that deliberately exercise the real prefill behavior keep their own explicit overrides, which simply take precedence per pytest's usual fixture-then-test-body ordering.

**Bug 2 -- `tests/test_gravity_gradient.py` used a physically-impossible inertia tensor that a NEWER Basilisk build now correctly rejects.** The test picked `diag(5, 10, 20) kg*m^2` to get an "elongated," non-spherical inertia for a nonzero gravity-gradient torque -- but no rigid body can actually have those three principal moments: the triangle inequality requires the largest to be no more than the sum of the other two, and `5 + 10 = 15 < 20`. The Basilisk 2.12.0 build this project was built and verified against never checked this at runtime, so the mistake shipped unnoticed; the user's newer Basilisk build has since added `HubEffector::validateConfiguration()` (confirmed directly by reading `src/architecture/utilities/avsEigenSupport.cpp`'s `eigenIsValidInertiaMatrix()` in this monorepo's own Basilisk source tree -- symmetric, at-most-one-zero-eigenvalue, and exactly this triangle-inequality check), which now correctly rejects it during `InitializeSimulation()` with a cryptic C++ message naming `IHubPntBc_B`, not the actual problem.

**Fix**: changed the test's inertia to `diag(5, 8, 10)` -- still clearly non-spherical (the real requirement the comment above it already documented) while comfortably satisfying the triangle inequality (`5 + 8 = 13 > 10`). Also added a genuinely new, scoped validity check to `schema.scenario.SpacecraftConfig.validate()` itself: for a DIAGONAL `inertia_kg_m2` (confirmed, by sweeping every bundled template/scenario JSON file, to be the only shape this project's own content ever uses), the diagonal entries -- which ARE the principal moments directly for a diagonal matrix, no eigendecomposition needed -- must be positive and satisfy the same triangle inequality, with a message that actually names the violated values instead of a generic Basilisk C++ string. A fully general (off-diagonal-populated) inertia tensor is deliberately left unchecked here (this schema module has no numpy dependency by design -- see its own "standalone, no Basilisk needed" docstring) and still reaches Basilisk's own runtime check unvalidated, just without this earlier message.

**Verified**: `tests/gui/test_propagation_setup_dialog.py`: 23/23 passing (unaffected in this sandbox, since nothing was ever cached here either way -- the fix is about determinism on OTHER machines, confirmed by inspecting the fixture's own isolation, not by a before/after sandbox comparison this sandbox can't produce). Four new tests in `tests/test_scenario_schema.py` for the new triangle-inequality check: rejects the exact `diag(5, 10, 20)` mistake with a message naming "triangle inequality"; rejects a non-positive diagonal entry; accepts the corrected `diag(5, 8, 10)`; and confirms a non-diagonal tensor is deliberately left unchecked (scoped as documented, not silently over-reaching). `tests/test_scenario_schema.py` (207/207) and `tests/test_scenario_templates.py` (every bundled template, unmodified) both pass, confirming the new check doesn't false-positive on anything this project already ships. `tests/test_gravity_gradient.py` itself could not be re-run in this sandbox (needs SPICE/network, this sandbox's own standing, already-documented limitation) -- the fix is grounded in reading Basilisk's own real C++ validation source directly, not assumed. Full non-Basilisk suite: 1139 passed, 2 skipped, zero regressions.

---

## Comprehensive audit: phasing-keeping still broken under real J2 dynamics -- two more real bugs, found and fixed, after this session got genuine Basilisk access

A later screenshot (different numeric values than the earlier cold-start-fix investigation, so a fresh run) STILL showed `05_formation_flying_phasing.json`'s "R vs chief-1"/"T vs chief-1" Vizard panels pinned at their 100 km ceiling. The user asked for a complete audit of what was going wrong, with a quick primer on real-world phasing-keeping practice first.

**Industry practice, briefly.** Real along-track/phasing control for formation-flying and co-located constellations (GPS, Iridium-class LEO formations, co-located GEO pairs) is built on a small set of standard ideas this controller already follows in spirit: (1) phase/separation is tracked via a drift-and-correct cycle -- raise or lower the semi-major axis slightly for a bounded window to accumulate the needed mean-motion offset, then restore it, rather than continuously thrusting; (2) the tracked phase quantity and any altitude deadband are evaluated on MEAN, not raw osculating, elements/altitude, specifically to avoid reacting to short-period (once-per-orbit) oscillation that isn't real secular drift; (3) for near-circular orbits specifically, mission designers use non-singular ("equinoctial") orbital elements rather than classical (semi-major axis, eccentricity, inclination, RAAN, argument of periapsis, mean anomaly) ones, because classical elements have a well-known mathematical singularity as eccentricity -> 0 (where "the direction to periapsis" stops being meaningful) and near i -> 0; (4) any deadband is sized with real margin over the orbit's own natural, non-decaying short-period variation (eccentricity- and J2-driven), not picked as tight as the mission's propellant budget allows. This audit found this project's own controller violating (2)/(3)/(4) in ways invisible in this sandbox until a real Basilisk build with real J2 gravity became available to test against (see below) -- (1) was already correct.

**This sandbox finally has a real Basilisk build to test against.** Earlier entries in this file repeatedly documented "could not verify here, no Basilisk install" as a standing limitation; that changed mid-audit (`pip download bsk` succeeded through this session's proxy, and a prior session had already built a working venv) -- real SPICE kernel hosts (`naif.jpl.nasa.gov`, its `hanspeterschaub.info` backup) remain unreachable (re-confirmed directly: a live fetch attempt gets a proxy 403 from both), so Sun/Moon third-body gravity specifically still could not be exercised, but Earth's own spherical-harmonics gravity field (`GGM03S`, bundled locally, no network needed) now could be, for the first time, against this template's exact real orbital elements.

**Bug 1 -- `PhasingKeepingController`'s phase-error metric is numerically singular for a near-circular orbit, and this template's own orbit is near-circular (`e = 0.001`) on purpose.** The control law measured along-track phase from the difference of each spacecraft's osculating MEAN ANOMALY (`orbitalMotion.rv2elem` -> `f2E` -> `E2M`), which decomposes eccentricity, argument of periapsis, and true anomaly individually. Reproduced directly, against a real Basilisk build with real (degree >= 2) spherical-harmonics Earth gravity active on this template's exact elements: the osculating eccentricity vector's own real, physical J2 short-period oscillation is, by itself, enough to carry this near-circular orbit's `e` through numerically-zero every single orbit -- confirmed by instrumentation, `e` dipped to ~7.5e-5 and the recovered argument of periapsis swung by ~180 deg within three 30 s ticks, while the REAL geometric along-track separation (`orbitalMotion.rv2hill`) barely moved at all over that same interval. The resulting mean-anomaly-difference "error" read as large as several THOUSAND km of spurious phase error within a handful of ticks, which the controller (faithfully, correctly given its input) acted on as real -- computing a wildly wrong `deltaA`/burn direction from it and actually perturbing the real orbit.

**Fix** (`engine/orbit_maintenance.py`, `PhasingKeepingController`): replaced the osculating-mean-anomaly difference with a new `_argument_of_latitude(rVec, vVec)` -- the angle `u = omega + f`, computed DIRECTLY from each spacecraft's instantaneous position/velocity via the ascending-node/orbit-normal geometry, never decomposing eccentricity/argument-of-periapsis/true-anomaly individually. This is exactly the quantity non-singular/equinoctial element theory is built around retaining for this reason, and it is numerically well-behaved all the way through `e -> 0` (confirmed: re-running the exact same real-J2 reproduction with the fix, the along-track error is smooth and stable to within ~0.5 km across the same interval that used to show thousand-km spikes). The one real approximation this introduces -- a true, not mean, argument of latitude, carrying an uncorrected equation-of-center bias of order `2*e` radians -- is utterly negligible for the near-circular (well under ~0.05) orbits this controller targets; a rigorous equinoctial-element reformulation (correct at any eccentricity) is a real, documented follow-on, not implemented here. Undefined, in the same well-known way classical RAAN is, only for an exactly equatorial orbit (`i == 0`) -- falls back to the inertial +X axis as an arbitrary but fixed reference in that case, which loses no accuracy for this controller's own use (only the difference `uB - uA` is ever used, and both spacecraft always share the same orbital plane).

**Bug 2 -- this template's own `station_keeping.deadband_km` (2 km) had no margin over this orbit's real, natural, non-decaying altitude variation.** Tracing WHY the fixed phase-error metric was STILL drifting under the full control loop (not just the one function) found a second, independent problem: the co-located `StationKeepingController` (which `phasing_keeping` always shares a thruster with) fired a real, continuous ~7-hour reboost burn, confirmed via direct instrumentation of its own burn log, purely from boxcar-averaging raw osculating altitude over one orbital period and comparing it against an absolute 550 km target with only a 2 km deadband. Measured directly: for this exact orbit (`a` = 6928 km, `e` = 0.001) under real J2 gravity, the time-average of raw altitude over ANY integer number of orbital periods (tested 1 through 10 -- ruling out an averaging-window-length artifact) converges to a STABLE ~545 km, not 550 km -- a genuine ~5 km secular offset between this orbit's initializing semi-major axis and its own true time-averaged radius under real J2, on top of which J2's short-period term adds further swing. A 2 km deadband has no margin over either, so the controller was doing exactly what it was configured to do: reacting to ordinary orbital mechanics, not real secular (e.g. drag) decay. (A tempting alternative fix -- average the osculating semi-major axis, or use Basilisk's own `orbitalMotion.clMeanOscMap` Brouwer mean-element mapping instead of raw altitude -- was tried and rejected: SMA's own short-period swing at this geometry is LARGER than altitude's (~19 km peak-to-peak, confirmed), and `clMeanOscMap` depends on the same individually-decomposed eccentricity/argument-of-periapsis internals Bug 1 just found to be singular at this exact eccentricity.)

**Fix**: widened `05_formation_flying_phasing.json`'s own `station_keeping.deadband_km` from 2.0 to 15.0 (`scripts/_generate_templates.py`, regenerated) -- comfortably covering this orbit's real natural swing while still catching genuine drag decay (this template's own `enable_drag=True`) well before it could matter, matching the industry practice above (size the deadband with margin over natural short-period variation, not as tight as the budget allows). The template's own `description` and the `orbit=`/`station_keeping=` comments in the generator were corrected in place -- the old comment's claim that 7 km of eccentricity-driven swing was "well inside" a 2 km deadband was itself simply wrong, never actually checked against real J2 dynamics until this audit.

**Verified**: both fixes confirmed together, end-to-end, against the real Basilisk build on this template's exact elements (degree-2 Earth gravity -- Sun/Moon third-body remains genuinely unverified, see above): zero station-keeping burns over 7 simulated days (previously one real ~7-hour burn), and the along-track error converges smoothly and monotonically from its real -110 km starting value toward the +50 km target (reaching -71 km by day 7, consistent with the 21-day correction window design) instead of diverging past -5000 km. Four new unit tests in `tests/test_orbit_maintenance.py` for `_argument_of_latitude` directly (matches true anomaly/`rv2elem` for a well-conditioned orbit; stays exactly continuous as `e` is swept through zero where the classical decomposition is undefined; matches hand-computed equatorial reference cases) plus one new guard test (`test_phasing_keeping_skips_thrust_on_parallel_r_and_v`, the same `cross(r, v) == 0` degenerate case `ConstantFrameThrustController` already guards against, newly needed since `_argument_of_latitude` divides by the orbit-normal magnitude). A new `tests/test_orbit_maintenance_j2_regression.py` (2 tests) runs the FULL control loop end-to-end against real degree-2 spherical-harmonics gravity via the same bare-`SimulationBaseClass`-plus-builder-functions pattern `tests/test_gravity_gradient.py` already established (bypassing `engine.service`'s own SPICE requirement, which real `central_body_degree > 0` always triggers there) -- a standing regression guard for both bugs together, not just the one function. `tests/test_orbit_maintenance.py` (33/33, up from 29) and the new file (2/2) both pass against a real Basilisk 2.12.0 build.

**The user then ran the full suite for real**, on their own machine (real Basilisk, real SPICE, Python 3.14.4): 1314 passed, 11 skipped, 0 failed -- up from the prior real-machine baseline of 1301/11/3 (see "Two real bugs found from the first genuine full-suite run" above), confirming both this entry's fixes and that earlier entry's fixes are ALL still green together, including the two new `_argument_of_latitude` unit tests and both `test_orbit_maintenance_j2_regression.py` integration tests, for real, with genuine SPICE access this sandbox still doesn't have.

**A follow-up real screenshot (with both fixes above already applied) then asked whether the along-track separation "drifting toward the chief" down to ~20 km at t=7 days was a THIRD bug.** Re-run directly against the real Basilisk build, same real J2 gravity, extended to 25 simulated days: it is not a bug -- `hillT_km` (the real geometric along-track separation) grows smoothly and monotonically from -60.4 km at t=0 to +49.1 km by t=20 days and HOLDS there (48-49 km, `IDLE` state, zero further station-keeping burns) for the rest of the run; at t=7.0 days specifically it reads -21.1 km, matching the user's screenshot's `|T| = 20.66 km` (the Vizard panel shows magnitude only, see `_clamp_magnitude`'s own docstring) to within 2%. The real explanation: `follower-1` actually starts ~60 km BEHIND `chief-1` (`true_anomaly_deg=-0.5`), not ahead, and `phasing_keeping.correction_window_days=21` deliberately spreads that catch-up over 21 days, not instantly -- the shortest, most fuel-efficient path from "60 km behind" to "50 km ahead" necessarily passes close by the chief partway through (confirmed: ~0.9 km minimum separation at day ~11, entirely in-track -- radial/cross-track both stay under 0.3 km throughout, a controlled same-track catch-up, not a collision course across orbit planes). The REAL bug this surfaced: this template's own `sim_settings.duration_days` (7.0) was shorter than its own `phasing_keeping.correction_window_days` (21.0), so the template's DEFAULT run never actually let a user see the maneuver finish -- only the alarming-looking close-approach partway through, directly contradicting the template's own description ("the along-track separation should stay near target_separation_km"). A separate, smaller documentation bug was also caught while fixing this: the description claimed the follower holds station BEHIND the chief, when `target_separation_km`'s own sign convention (`PhasingKeepingController`'s docstring: always a positive, "B leads A" distance) actually settles it AHEAD.

**Fix**: widened `05_formation_flying_phasing.json`'s own `sim_settings.duration_days` from 7.0 to 24.0 -- 3 days of margin past the 21-day correction window so a default run shows the maneuver actually settle and hold at the target, not just the close-approach partway through. Rewrote the template's `description` to explain the close-approach as expected/safe up front (so a user isn't alarmed watching it happen live in Vizard) and fixed the "behind"/"ahead" wording. `scripts/_generate_templates.py`'s own `duration_days=` now carries a comment explaining why, regenerated into the JSON.

**Verified**: re-ran the extended (25-day) reproduction above directly against the real Basilisk build (degree-2 Earth gravity) to confirm the fix's premise before shipping it, not just asserted it; `tests/test_scenario_templates.py`, `tests/test_orbit_maintenance.py`, `tests/test_orbit_maintenance_j2_regression.py`, and `tests/gui/test_scenario_templates_gui.py` (149 tests total, none of them duration-coupled) all still pass against the real Basilisk build after the change.

## Real requirement correction: template 05 was built as a one-time realignment, not the fixed-distance formation-keeping the user actually asked for

The previous entry's fix made the default run "work" in the narrow sense of not showing an alarming close-approach unexplained, but a direct user correction made clear the underlying design was still wrong: "my requirement was... that the follower is maintaining certain distance to the chief, and not that it is basically alternating between trailing behind the chief and leading ahead of the chief. It has to be maintaining this fixed distance with a certain margin of error." The user also flagged that `chief-1` ran no `station_keeping` of its own at all, which "definitely should not be the case" since the chief also needs to hold its own altitude.

**Root cause.** `follower-1` was placed at `true_anomaly_deg=-0.5`, ~60 km BEHIND `chief-1`, while `phasing_keeping.target_separation_km=[50.0]` targets 50 km AHEAD (a positive, "B leads A" distance -- `PhasingKeepingController`'s own docstring). The default run therefore demonstrated a one-time ~110 km realignment maneuver (passing close by the chief on the way, per the previous entry), not steady-state formation-keeping -- the exact behavior the user said they did not want. This also directly contradicted `engine/formation.py`'s own stated design intent for this two-spacecraft shape ("the two-satellite 'chief holds station, follower holds formation' case"): the chief was never actually given that station-keeping role in this template.

**The correct pattern already existed, unused by this template.** `engine.formation.generate_phasing_follower()` (the "Generate phasing formation..." GUI generator) has always placed a NEW follower EXACTLY on its target separation from the chief, by shifting the follower's own mean anomaly by the along-track arc length corresponding to the target separation: `along_track_rad = target_separation_km * 1000 / chief_sma_m`. This template's hand-authored JSON had simply never been updated to match that same, already-correct design -- it wasn't a controller bug, just a stale scenario.

**Fix** (`scripts/_generate_templates.py`, `build_05_formation_flying_phasing()`): changed `follower-1`'s orbit from `true_anomaly_deg=-0.5` to `anomaly_type="mean", mean_anomaly_deg=0.413509` -- computed via the same arc-length relation above (`50000 m / 6928000 m = 0.0072171 rad = 0.413509 deg`), exploiting that `chief-1` sits at `true_anomaly_deg=0.0`, where true and mean anomaly are identically equal for ANY eccentricity (both are exactly 0 at periapsis), so no Kepler's-equation solve was needed to get the exact value. Added a matching `station_keeping=StationKeepingConfig(target_altitude_km=550.0, deadband_km=15.0, thrust_n=0.05, isp_s=1500.0, propellant_kg=5.0)` to `chief-1` (identical hardware to `follower-1`'s own, already-present station-keeping -- a realistic "sister satellite" pair, not a special case). Rewrote the template's `description` to describe formation-KEEPING from the start, not a transition, and added an "Audit history" paragraph to its own text documenting this and the prior two fixes for future readers.

**Verified** directly against a real Basilisk build (degree-2 Earth gravity, same bare-`SimulationBaseClass`-plus-builder-functions pattern as the regression tests above): over a 24-day run, `hillT_km` starts at 50.05 km and drifts only within about +/-3.5 km of target from real J2/differential-drag perturbations, with neither spacecraft's `station_keeping` needing to fire even once -- steady-state holding, never a transition, never passing the chief. `tests/test_scenario_templates.py` and the full non-Basilisk suite stay green after the change.

## Long-term-simulation feedback, and a real Basilisk platform limit found while acting on it

Having fixed template 05 to show correct steady-state formation-keeping, the user pointed out the 24-day run itself wasn't interesting: "for phasing keeping, short term simulations are not really interesting. its the long term simulations, that give much more insight into this type of mission, particularly the phasing keeping deltaV and the behaviour of the RTN separation between both satellites. but not limited to them of course." This was a fair complaint against the fix just shipped -- a direct re-run confirmed the 24-day duration produces ZERO station-keeping or phasing-keeping burns and essentially zero delta-V, because the formation never drifts far enough to cross `phasing_keeping`'s own 10% tolerance band in that short a window. Pedagogically correct ("it just holds") but not demonstrative of what the controller actually does under real drift.

**Investigating longer durations surfaced a real, previously-unknown Basilisk platform limit**, not a SpaceMissionStudio bug: Basilisk's own `nanoToSec()` (C++, `src/architecture/utilities/macroDefinitions.h`) converts simulated nanoseconds to a `double` and can only exactly represent integers up to `2**53` (`DBL_MANT_DIG`) -- `9007199254740992` ns, ~104.25 days. Past that limit it `fprintf`s a stderr error on EVERY call (apparently made many times per simulation tick) and returns `NaN`, which poisons every downstream time-dependent computation for the rest of the run. Confirmed directly: a 180-day test run hit this cliff and became severely, visibly degraded -- across 500,000+ repeated stderr error lines, simulated time barely progressed past ~104.25 days at all (advancing only ~5.84 more simulated days despite running far longer in real time). This is a real, hard ceiling on any duration this app -- or any Basilisk-based tool -- can safely request, independent of anything SpaceMissionStudio's own schema previously checked (`SimSettings.validate()` had no upper bound on `duration_days` at all before this fix).

**A 90-day run was verified to stay safely clear of that cliff while finally showing the long-term dynamics the user asked for.** Re-run against the real Basilisk build (degree-2 Earth gravity, chief-1 now also holding its own station-keeping per the fix above): the along-track separation drifts naturally between roughly 45 km and 50 km, crossing `phasing_keeping`'s 10% tolerance band TWICE over the run (around day 35 and again around day 70), each crossing firing a real along-track correction burn and accumulating about 0.015 m/s of delta-V by day 90 -- `Max |T - 50km| over run: 5.0997 km`, `Total follower-1 PK dv: 0.01481 m/s`, ending `IDLE` with `suspendedDueToNonConvergence: False`. Exactly the "drift, then correct" behavior `phasing_keeping` exists to demonstrate, invisible at 24 days.

**Fix, two parts.** (1) `scripts/_generate_templates.py`: changed `05_formation_flying_phasing.json`'s `sim_settings.duration_days` from 24.0 to 90.0, regenerated, and rewrote the template's description/comments to explain the new long-term drift-and-correct behavior instead of the old (shorter-duration) "it just holds, no corrections" framing. (2) `schema/scenario.py`: added a real upper bound to `SimSettings.validate()` -- `duration_days <= 100.0`, with an error message naming `nanoToSec()`'s `2**53`-ns/~104.25-day limit directly -- so this failure mode can never be silently hit by ANY scenario built through the GUI or hand-authored, bundled template or otherwise, not just this one. 100.0 days keeps real margin under the actual ~104.25-day cliff rather than sitting right on it.

**Verified**: regenerated all 20 bundled templates and confirmed via `git diff` that only `05_formation_flying_phasing.json` changed (the new validation ceiling is far above every other template's own duration); two new tests in `tests/test_scenario_schema.py` (`test_duration_days_at_the_100_day_cap_validates`, `test_duration_days_beyond_the_basilisk_nanotosec_limit_rejected`) guard the new ceiling directly; the full non-Basilisk suite (`pytest tests/ -q --ignore=tests/gui`: 550 passed, 184 skipped) and `tests/test_scenario_schema.py`/`tests/test_scenario_templates.py` together (303 passed) both stay green.

## Full audit: the app was "a black box" -- six real GUI-vs-template fidelity gaps found and closed, plus a new live "Explain" recipe layer

A real user raised a core product complaint directly: the bundled example templates demonstrate real fidelity, but a user cannot reproduce that same fidelity by building a bespoke scenario from scratch through the app's own GUI -- some of what makes the templates work is either missing from the GUI entirely, or trapped in the dev-only generator script and never wired into the shipped package at all. Confirmed via a full field-by-field audit (every schema dataclass, every GUI editor, every helper in `scripts/_generate_templates.py`, cross-referenced against all 20 bundled templates) that this was real, and worse than a missing-feature gap in two places -- an active, silent DATA-LOSS bug.

**Gap 1/2 (the real bugs): `CommsPointingConfig` and `RFLinkConfig.antenna_beamwidth_deg` had NO editor anywhere in `spacecraft_editor.py`.** Opening a spacecraft that already had either set (e.g. template 19's "leo-comms-1") in the ordinary Spacecraft "Edit..." dialog and clicking OK with ZERO edits permanently deleted them, because `SpacecraftEditorDialog.to_dataclass()` always rebuilds a fresh `SpacecraftConfig(...)` from widget state alone, and no widget existed for either field. **Fix**: added a `comms_pointing_group` to the Attitude control (FSW) tab -- a `target_ground_station` combo (populated via a new `set_ground_station_names_provider()`, plumbed down from `ScenarioEditorWidget` the same way `central_body`/`simulation_mode` already flow to this dialog; same stale-reference-preserved-not-silently-swapped fallback as `pk_chief_combo`'s own precedent), `antenna_boresight_b`/`sun_pointing_axis_b` (a "use default" checkbox gating the latter, since it has a real semantic `None` default) xyz rows, and a `comms_power_w` spin box -- plus an `antenna_beamwidth_deg` optional field on the existing RF link group. Force-cleared to `None` in `simulation_mode="orbit_only"` the same way `fsw_mode`/`power` already are. **Verified**: a new end-to-end regression test loads the REAL bundled template 19, opens "leo-comms-1" in this dialog with zero edits, and confirms both fields survive `to_dataclass()` unchanged -- the exact bug scenario, not just a dataclass-level round-trip check -- plus 15 more unit tests for the new widgets. `tests/gui/test_spacecraft_editor.py` went from 70 to 82 passing tests.

**Gap 3: `sun_synchronous_inclination_deg()`/`raan_for_ltan_deg()` existed ONLY as private helpers inside the dev-only `scripts/_generate_templates.py`**, never importable by the running app -- affecting orbit reproducibility for 12 of the 20 bundled templates (every SSO-orbit one). **Fix**: moved both (verbatim, same docstrings/verified reference values) into a new Basilisk-free `engine/orbit_design.py`; the generator script now imports them instead of defining its own copy (one shared implementation, zero drift risk). Added "Compute Sun-sync inclination for this altitude"/"Compute RAAN for LTAN..." buttons to `orbit_ic_widget.py`'s classical-elements page (a new `set_epoch_provider()`, plumbed the same way, supplies the epoch the RAAN computation needs) -- buttons, not auto-apply, matching this app's "compute a sane starting point, let the user keep tweaking" convention elsewhere. **Verified**: regenerating all 20 templates after the move produces a diff in exactly ONE file (`01_two_body_circular_orbit.json`'s own description text, updated to point at the new importable location) -- confirmed a pure refactor otherwise; a new `tests/test_orbit_design.py` (8 tests) turns this module's own docstring reference-value claims (97.40 deg at 6878.1366 km; the three real Sun-right-ascension reference points at the equinoxes/solstice) into real pytest asserts, previously only "verified directly" in prose.

**Gap 4/5 (lower severity -- a workaround already existed for each): `PhasingFormationRequest.station_keeping_target_altitude_km`/`.eclipse_sunlit_threshold` missing from `phasing_formation_dialog.py`; `SpaceWeatherConfig.cache_dir` missing from `propagation_setup_dialog.py`'s `to_space_weather()`.** Fixed: a "derive from chief's own altitude" checkbox (default-checked, matching that field's own `None`="derive" semantics) plus an `eclipse_sunlit_threshold` spin box in the phasing-formation dialog; a plain optional `cache_dir` line edit (blank keeps the `None` default) in the propagation setup dialog. Both are real gaps, but neither was a data-loss bug the way gaps 1/2 were -- editing an already-generated spacecraft's `station_keeping`/propagation-setup blocks directly already worked.

**Gap 6: no "how do I build this myself" layer at all -- only the 20 bundled templates' own hand-written `description` text, which a from-scratch scenario never has.** Asked the user directly whether, beyond raw field exposure, a "recipe/explain" layer was also wanted -- confirmed yes. Went through two further rounds of direct user correction on HOW to present it: an initial prose-paragraph design was rejected ("what users don't like are endlessly long prose... keep the app clean and clear"); the terse-bullet-point redesign that followed was ALSO rejected ("isn't there a visually and graphically better way to convey information? users don't like these raw text bullet points either") before landing on the stat-tile/badge/table shape actually built, informed directly by the `dataviz` skill's own form guidance ("a handful of headline numbers -> a KPI row of stat tiles," "more than ~7 same-shape items -> a table").

**Built**: `engine/scenario_explainer.py` (Basilisk-free, same independently-testable precedent as `engine/constellation.py`) -- `explain(scenario) -> ScenarioExplanation` (`StatTile`/`Badge`/`SpacecraftFactRow`/`ExplanationSection` dataclasses), NEVER raises (called on every keystroke, often against a mid-edit/invalid scenario), builds each stat tile/section/table row CONDITIONALLY so a trivial from-scratch scenario renders a short tile row and maybe one badge, not a wall of empty sections. SSO detection reuses Gap 3's own `engine.orbit_design.sun_synchronous_inclination_deg()` directly -- zero duplicated math. Every string stays short by construction (a dedicated test enforces a 90-char ceiling on every `StatTile.value`/`Badge.label` across all 20 real bundled templates, a permanent regression guard against this quietly regrowing into prose or a bullet wall later). Extracted `mission_dashboard_widget.py`'s own `_badge_style()`/color-tuple helper into a new, shared `gui/badges.py` (added one new semantic color, `PALETTE["warning"]`, alongside the existing danger/success/accent/muted set) so both widgets draw from the exact same visual language rather than inventing a second one -- `mission_dashboard_widget.py` now imports from `badges.py` instead of defining its own copy, zero behavior change there (its own 11 tests still pass unchanged). New `gui/scenario_explainer_widget.py` renders the structured output as a KPI stat-tile row, per-section colored badge rows, and (for 2+ spacecraft) a `QTableWidget` comparison -- never prose, never a bullet-point wall -- inside its own `QScrollArea` so it never forces the window taller. Wired into `main_window.py` as a new "Explain" tab, driven by the ALREADY-EXISTING `ScenarioEditorWidget.changed` signal (zero new plumbing for the common edit case) plus explicit calls at every other state-reset point that doesn't itself emit `changed` (`on_new`, `open_path`/`_on_load_scenario_customized`'s shared `_open_scenario()` tail, and the autosave-recovery-restore path) -- found directly by testing each one, not assumed. Does NOT touch or replace `scenario_editor.py`'s own free-text `description` box -- different pane, different job (that one is hand-written narrative/pedagogical prose for the 20 bundled templates specifically; this is a terse, ALWAYS-CURRENT fact summary for any scenario).

Added short, same-style glossary entries to `USER_MANUAL.md` Section 12 for the terms this feature newly references but the glossary didn't yet define (Sun-synchronous orbit, spherical-harmonics gravity, third-body perturbation, phasing/along-track separation) -- a badge/note that needs a definition points at that section by name rather than inlining the explanation. Also fixed that same manual's own stale "Three tabs on the right" claim (it was already wrong before this work -- Mission Dashboard had no mention at all) while touching the adjacent text for the new Explain tab.

**Verified**: `tests/test_scenario_explainer.py` (49 tests) -- a trivial one-spacecraft scenario produces a short `stat_tiles` row and no `spacecraft_table`; a template-05-shaped chief/follower pair produces a 2-row `spacecraft_table`, a "Formation / orbit maintenance" section badge, and a note specifically flagging a spacecraft with `phasing_keeping` but no `station_keeping`; SSO detection fires at 97.40 deg/6878 km and doesn't at 51.6 deg/same altitude; degree-10 + Sun/Moon gravity shows up as a tile; `explain()` doesn't raise on any of the 20 real bundled templates nor a zero-spacecraft scenario; every rendered string stays short, checked against all 20 real templates, not just synthetic cases. `tests/gui/test_scenario_explainer_widget.py` (5 pytest-qt tests) covers `set_scenario(None)`/rich/trivial/switching-between-scenarios. Four new `tests/gui/test_main_window.py` tests confirm the Explain tab actually exists and genuinely refreshes on startup, on edit, on an invalidating edit (shows the placeholder, not stale content), and on File > New -- the real wiring, not just the widget in isolation. Full suite: 1226 passed, 186 skipped (Basilisk-requiring, this sandbox's standing limitation), one pre-existing unrelated Qt test-ordering flake (confirmed to pass standalone) deselected -- up from 1140 before this whole six-fix audit began.

## Explain tab, round two: a real formation-geometry diagram, not just badges

The stat-tile/badge/table design above landed the SHAPE a real user had converged on through two earlier, explicitly rejected drafts (prose, then plain bullet points), but the very next piece of direct feedback on it was clear: "it already looks quite good but it still lacks a certain professionality and a certain depth of information." Badges alone name a mechanism ("Phasing-keeping") without showing what it actually does -- the along-track separation drifting inside a hysteresis control band is exactly the kind of thing a picture conveys and a badge cannot.

**Built**: `engine.scenario_explainer.FormationDiagram`, a new small dataclass (`chief_name`, `follower_name`, `target_separation_km`, `tolerance_fraction`, `restore_tolerance_fraction`) plus `ScenarioExplanation.formation_diagrams: List[FormationDiagram]`, one entry per spacecraft with `phasing_keeping` configured -- `target_separation_km` takes the FIRST entry of a (possibly multi-step) separation schedule, i.e. the current/initial target. Deliberately holds only fields already fixed at scenario-design time (no live telemetry -- that stays `mission_dashboard_widget.py`'s own job, which needs an actual run to mean anything).

**New `gui/formation_diagram_widget.py`** (`FormationDiagramWidget`) draws it procedurally with `QPainter` -- same precedent as `icons.py`'s own app-icon glyph, no new bitmap/SVG asset or dependency to keep in sync with the theme. Not real-distance-scaled (the separation always fills the available width): a chief marker and a follower marker on a labeled along-track baseline with a direction arrowhead, and -- the actual "depth of information" the feedback asked for -- TWO concentric, translucent bands centered on the follower's target position: a wider warning-colored band for the trigger tolerance (where a correction STARTS) and a narrower, nested success-colored band for the restore tolerance (where a correction STOPS) -- literally the deadband/hysteresis control law this controller runs, not just two separate numbers in a table cell. Collapses to zero height when there's no diagram to show (`set_diagram(None)`), matching `ScenarioExplainerWidget`'s own "clear, don't just hide" idiom.

Wired into `gui/scenario_explainer_widget.py`: one `FormationDiagramWidget` per `formation_diagrams` entry, placed directly inside the "Formation / orbit maintenance" section (right below its badges/notes) -- the diagram sits next to the badge that names the mechanism it depicts, not in some separate, disconnected part of the tab.

**Verified**: rendered directly (grabbed to PNG, visually inspected) both against synthetic data at several separation/tolerance scales and against the REAL bundled template 05 (90-day phasing-keeping demo) -- the diagram correctly reflects that template's real 50 km target, 10%/2% trigger/restore tolerances, and renders legibly alongside its stat tiles, badges, and the existing spacecraft comparison table. New `tests/gui/test_formation_diagram_widget.py` (5 tests): zero-height with no diagram, real height once one is set, collapses back to zero on clear, `paintEvent` doesn't raise across a deliberately wide range of separation/tolerance combinations (including the edge case where the restore band would be wider than a naive implementation might clip), accepts an initial diagram via the constructor. Three new `tests/test_scenario_explainer.py` tests cover the extraction logic directly (correct fields for a template-05-shaped pair; the first-entry-of-a-schedule rule for a multi-step separation list; no diagram without `phasing_keeping`). Three new `tests/gui/test_scenario_explainer_widget.py` tests confirm the widget is actually instantiated for a rich (chief/follower) scenario, absent for a trivial one, and correctly removed when switching from rich back to trivial (a real `deleteLater()`-timing bug was caught and fixed here: `QObject.findChildren()` still sees a widget until the NEXT event-loop pass actually runs its deferred deletion, so the test needed a `qtbot.wait(10)` after the switch -- the same reason `ScenarioExplainerWidget._render()`'s own clear-and-repopulate pattern works correctly in the app itself, where the event loop keeps running). Full suite: 1236 passed, 186 skipped, same one pre-existing unrelated flake deselected -- up from 1226.

## Full code + GUI audit: stale code removed, real bugs fixed, every dialog visually reviewed

A request for a complete audit of the whole codebase and GUI, covering stale code, GUI elements with no remaining purpose, visual polish, and any real bugs. Static analysis (ruff/pyflakes/vulture) came first, then every main-window state and every dialog was rendered offscreen and inspected. Then came a mechanical open-then-OK round trip of every editor dialog over all 20 bundled templates, a schema probe with invalid values, a CLI-vs-GUI parity check, and a loop of the GUI suite to chase an intermittent crash.

**Real bugs found and fixed**

* **Opening an editor and clicking OK changed the data.** A plain `QDoubleSpinBox` rounds every value to its *display* decimals as soon as the value is set. So with zero edits, the spacecraft dialog rewrote template 13's 0.00667 kg*m^2 inertia as 0.007 (a 5% change), its 2-hour duration (0.08333 d) as 0.0833, a 7078.1366 km semi-major axis as 7078.137, and more.
  * The fix is a new `gui/widgets.py` `PreciseDoubleSpinBox`. It stores 10 decimals, treats `setDecimals()` as the *minimum* shown, and so always displays what will actually be saved. It always uses `.` as the decimal point (a typed `,` is also accepted), matching every other number the app prints, instead of switching to `,` under e.g. a German locale. It replaces all 17 spin-box constructions across the GUI.
  * The same class of bug existed in two comma-separated list fields (`target_separation_km`, `wheel_speed_biases_rad_s`), which were formatted with `{:g}` (6 significant digits). These now use `exact_number_text()`.
  * New regression test: `test_opening_then_okaying_every_editor_leaves_template_values_unchanged`, parametrized over every template and every spacecraft/sensor/actuator/propagation/ground-station/dispersion dialog.
* **Intermittent whole-process abort: "QThread: Destroyed while thread is still running".** Workers emit their terminal signal from inside `run()`, so the thread can still be returning when that signal's slot runs. Dropping the last reference to it at that point aborts the process.
  * In the app, `on_run()`/`on_run_monte_carlo()` replaced `self._run_worker`/`self._mc_worker` unconditionally. They now call `_join_finished_worker()` first.
  * In the tests, this is the long-standing "pre-existing flake" that earlier entries deselected: looping `test_run_worker.py` alone aborted 8 runs in 25. Three tests returned right after the `failed` signal, so the worker was garbage-collected mid-return. A new autouse fixture in `tests/gui/conftest.py` now joins every QThread a test started, and the affected tests wait on their worker explicitly. After the fix: 0 aborts in 25 loops of every QThread-using test file, and 5 of 5 full GUI-suite runs clean.
* **Locale-dependent SPICE epoch strings.** `QApplication` calls `setlocale(LC_ALL, "")` on Linux, which made `strftime("%b")` locale-dependent. Under a German locale, any epoch in March, May, October, or December produced e.g. `2030 MÄR 01`, which SPICE rejects. `engine/time_system.py` now uses a fixed English month table.
* **Zero or non-finite direction vectors passed validation.** Only the length of these vectors was checked: `comms_pointing.antenna_boresight_b`, `comms_pointing.sun_pointing_axis_b`, `power.panel_normal_b`, `constant_thrust.direction`, CSS/thermal `nHat_B`, RW `gsHat_B`, and MTB `gtHat_B`. A `[0, 0, 0]` or NaN axis only failed mid-run, as a NaN attitude target. The new shared check `_is_direction_vector()` requires three finite components and non-zero length.
* **Template 05's Customize wizard said the opposite of the truth.** It told the user `follower-1` holds station *behind* `chief-1`. `target_separation_km` is a "follower leads chief" distance, so it now says *ahead*.
* **CLI/GUI parity gap.** `generate-phasing-formation` had no `--eclipse-sunlit-threshold`, though `PhasingFormationRequest` and the GUI dialog both support it. A new test asserts that every `PhasingFormationRequest` field is reachable from the CLI.
* `SimulationService.log_last_known_state()`'s docstring promised "never raises", but its station-keeping/phasing controller log reads were unguarded. They are now guarded too.

**Stale code removed**

* The five unused `diagnostic_05*.json` debug scenarios, which shipped in every wheel. The one still used by a test moved to `tests/data/vizard_station_keeping_crash_regression.json`.
* `time_system.py`'s dead, never-called SPICE helpers (`utc_to_et`, `et_to_utc_iso`, `EpochTimes`, `epoch_times`, `build_epoch_msg`) were removed. The module is now Basilisk-free and its tests run everywhere.
* Unused imports across `gui/` and the tests.

**GUI cleanup**

* **Combo boxes and spin boxes had no arrows at all.** Styling the `::drop-down`/`::up-button` subcontrols makes Qt stop drawing the native arrow, so every dropdown looked like a plain text field. The fix ships SVG chevrons, plus themed check-mark and radio indicators, in `gui/assets/` (added to `package-data`, and verified in a built wheel). `test_theme.py` checks that every referenced asset exists and that the SVG colours match `PALETTE`.
* **Grey bands in group boxes.** The theme's base `QWidget` background rule painted a grey band behind every checkbox row and stacked-widget page inside a white group box, and across the Explain tab's sections. Those widgets are now transparent.
* **Load Scenario tab.** It had 20 full-width "Customize: <whole title>..." buttons below the list, which forced a ~690 px minimum width and a horizontal scrollbar at the default window size. They are replaced by a compact **Customize...** button on each row. The buttons sit above the list, and the list fits its rows.
* **Toolbar.** The platform's mixed stock pixmaps (colour folder/floppy bitmaps, a ▶▶ glyph, no icon at all for Live Plot) are replaced with one consistent SVG line-icon set (`icons.toolbar_icon()`). A checked toolbar action, like Live Plot, now looks different from an unchecked one.
* **Propagation setup.** The content is now in a scroll area sized to the screen. On an 800 px screen, the window manager had clamped the dialog and squashed the "Atmosphere & drag" rows until their text was cut off. Over-long field labels were shortened, taking the dialog from 905 to 671 px wide.
* **Phasing formation dialog.** A flat 20-row form (830 px tall) is now five titled groups (Spacecraft, Initial offset, Propulsion, Station-keeping, Phasing-keeping) in two columns, 594 px tall.
* **Sensor/actuator editor.** The reaction-wheel help was a 16-bullet wall that made the dialog 896 px tall. It is now a recessed reference panel capped at 150 px, with warnings first. An empty catalog-info label that left a 40 px gap is now hidden.
* **Spacecraft editor.**
  * The tab bar was clipped, because it was measured before the stylesheet's bold tab font was applied.
  * The Attitude control tab now puts the Comms pointing group directly under FSW mode, with a hint that changes with context, and the JSON boxes are height-capped.
  * Tab labels are shortened.
* **Smaller fixes.**
  * Disabled primary buttons no longer look enabled.
  * Explain-tab stat tiles no longer draw nested borders.
  * The formation diagram's trigger band is no longer clipped at the widget edge.
  * The Scenario Editor button rows no longer overflow the left pane.
  * The wizard's Finish button no longer renders clipped ("Finisl"): bold is now reserved for `[primary="true"]`, not the dynamic `:default` state.
  * Long scenario names no longer open scrolled to their end.
  * The Vizard dialog's camera placeholder is no longer truncated.
  * The spacecraft-template list's horizontal scrollbar is gone.
  * The Mission Dashboard empty state is centred.
  * Validation-label colours now come from `PALETTE`.

**Docs**

* `USER_MANUAL.md`'s three screenshots were regenerated from the current GUI (they showed the old Load Scenario design and 18 templates).
* The manual's, README's, and templates README's Customize instructions now describe the per-row button.
* The README file layout now lists every module and test file (several were missing).
* The test counts and the Basilisk-independence list were corrected; `time_system.py` is now Basilisk-free.

**Verified**: full suite 1298 passed, 183 skipped (Basilisk-dependent), with nothing deselected (up from 1252 passed at the start of this audit). `scripts/_generate_templates.py` still regenerates all 20 templates byte-identically. A wheel built from a clean tree contains the SVG assets and no diagnostic scenarios. Every dialog and main-window state was re-rendered after the fixes and inspected.

## Real failure analysis: a 90-day formation run where the follower lapped the chief

A real user re-ran template 05 for 90 days and reported it "full of errors". They sent the run's log, both spacecraft's `position_N` CSVs, and the follower's `phasing_keeping.separation_error`/`state` CSVs.

**What the data showed.** The run completed. Its only real warning came at day 46: the phasing controller "did not reduce its own tracking error (179.987 deg -> -2.006 deg)" and suspended itself. Rebuilding the true along-track separation from the two position files showed:
* The follower started 50 km ahead, exactly as placed.
* It then fell behind at ~780 km/day and lapped the chief.
* It crossed through ±180° at day 28, crossed 0° at day 46, and kept lapping to day 90.

**Root cause, confirmed by reproducing it exactly with Basilisk 2.12.0 (the user's version) and real J2/degree-10 gravity.**
* **The scenario had been edited.** The error at t = 0 was −0.4127°, which is the true 0.4143° separation minus a 0.827° target, i.e. a 100 km target, not 50 km. The follower's station-keeping fired at t = 0.0667 d, the first tick with a full smoothing window, and stopped at a smoothed altitude of exactly 550.000 km. That means a deadband under ~5.1 km, not the template's 15 km.
* **Independent station-keeping broke the formation.** The orbit's natural mean altitude is ~545 km, because template 05's a = 6928 km is osculating at the starting point (~6916 km mean). So the follower's 550 km target made it reboost alone to ~5.25 km above the chief, an along-track drift of ~6.2°/day, while the chief never reboosted.
* **The phasing controller couldn't undo it.** Its burns were open-loop: its restore burn only replayed its own Δv backwards. It never measured the actual relative semi-major axis, so it could never remove a mismatch something else had created.
* **A ±180° wrap counted as "target reached".** At day 28 the "overshoot" check, a bare sign comparison, fired on the error wrapping from −180° to +180°.
* **The log file reached 116 MB.** Three controllers each DEBUG-logged their eclipse reading every 30 s tick.

**Fixes** (`engine/orbit_maintenance.py`):
* **Formation-follower station-keeping.** `build_phasing_keeping` switches the follower's controller into a mode where it mirrors the chief's station-keeping burns, rather than reboosting toward its own absolute target. It reboosts on its own only if it falls more than `deadband_km` below the chief's smoothed altitude, as a safety floor. The service passes in the chief's controller.
* **Closed-loop relative SMA.** Every phasing burn is now sized from the *measured* one-orbit mean of (a_follower − a_chief), which is steady to ~0.1 m under J2 against ±135 m instantaneous. The measurement is trusted only after a full orbit with no thrust. The restore burn nulls the measured mismatch. A disturbed drift gets re-steered to its planned offset, and an idle mismatch is trimmed out even while suspended. The trim tolerance is 25 m, or 1.5× one thruster tick's semi-major-axis change if that's larger, so a strong thruster can't ping-pong. The value is exported as a new result series, `<follower>.phasing_keeping.relative_semi_major_axis`.
* **Wrap-safe zero crossing** (`_crossed_zero`).
* **Eclipse logging only on sunlit/eclipse transitions.**
* **Docs:** schema `PhasingKeepingConfig`, the spacecraft editor's phasing tooltip, and template 05's description (regenerated) now explain the relative station-keeping.

**Verified with real Basilisk dynamics over 90 days** (direct-builder harness: degree-10 gravity, no SPICE/eclipse, since the sandbox can't fetch SPICE kernels):

| configuration | before | after |
|---|---|---|
| the user's configuration: placed 50 km ahead, 100 km target, 2 km follower deadband | laps the chief | closes to 98 km by day 15 and holds 91–98 km, no stray reboost, not suspended |
| both spacecraft with a 2 km deadband, so the chief reboosts at t = 0.07 d | — | follower mirrors it, 286/286 burn ticks; separation holds 45–50 km |
| stock template 05 | — | bit-identical to the old code (same 0.1143 m/s, same four correction cycles) |
| the user's configuration with a 0.5 N thruster (~260 m of SMA per tick) | — | converges in ~10 days, holds 89–98 km, three cycles, no ping-pong |

New `tests/test_formation_keeping_regression.py` covers:
* the user's configuration;
* the mirrored chief reboost;
* the follower burn logic;
* the wrap cases;
* the tick-quantum trim tolerance.

All orbit-maintenance/formation tests pass under Basilisk.

**Follow-up: partial-tick thrust** (requested by the user after the fix above). One 30 s tick of the template's 0.05 N thruster moves the semi-major axis ~26 m, while a typical correction needs ~2 m. So every phasing correction overshot about tenfold: the separation sawed against the bottom of its tolerance band and propellant was wasted.
* Each burn tick's thrust is now capped to exactly the Δv the burn still needs (`remaining_dv * mass / dt`). The very first tick (dt = 0) waits one tick instead of firing uncounted thrust.
* With burns exact, the tick-quantum trim tolerance from the fix above is no longer needed: a plain 25 m.

**Verified over 90 days** (same harness):

| configuration | phasing Δv before → after | separation after |
|---|---|---|
| stock template 05 | 0.114 → 0.0027 m/s | 45.4–52.2 km, one correction (day 28) |
| the user's configuration | 0.057 → 0.018 m/s | closes over the designed ~21-day correction window, holds 94.8–98.7 km |
| the user's configuration with a 0.5 N thruster | identical to 0.05 N | — |
| mirrored chief reboost | 0.086 → 0.0023 m/s | 45.0–49.5 km |

A single correction now lands on its planned relative SMA (−16.7 m planned, −16.1 m measured). New tests cover burn accuracy and thrust-independence. Template 05's description now quotes these re-verified numbers in place of the old degree-2 ones (two corrections, ~0.015 m/s).

## Finite-burn realism: thruster minimum on-time, and eccentricity-neutral burns

The user asked whether finite burns had been considered. Burns already were finite: the thrust is applied as a continuous force over many 30 s ticks, never as an impulse. Two real effects were missing, though, and the user asked for both.

**1. Thruster minimum on-time / minimum impulse bit.** A real thruster can't fire for an arbitrarily short time. The partial-tick fix above made a 2 m correction a sub-second firing, which no real 50 mN thruster can do.
* New `StationKeepingConfig.min_on_time_s` (default 0 = the old ideal thruster). The minimum impulse bit is `thrust_n * min_on_time_s`.
* New `ThrusterOnTimeModel` in `engine/orbit_maintenance.py`. A firing, once started, runs for at least the minimum on-time, even across several ticks and even after the controller that asked for it stops. A burn needing less than one minimum firing is rounded up to it when it needs at least half of one, and skipped otherwise.
* The phasing controller plans with it. A planned phasing correction smaller than one impulse bit is rounded up to one bit (a slightly faster correction). A *trim* finer than one bit is flown as an exact pair: (one bit + Δv), then one bit back. Any extra Δv a rounded-up firing delivers is counted.
* The station-keeping and phasing controllers of one spacecraft share ONE model instance, because they drive one physical thruster.
* **Real bug caught in verification, fixed before commit.** A firing belonged to no one, and station-keeping (which runs first each tick) continued any firing still in progress. It therefore took 30 s of every multi-tick phasing firing each tick: it logged those ticks as its own burns and debited their propellant a second time, while phasing's force overwrote its own on the shared effector. Every phasing firing was cut to half its on-time, and the follower's station-keeping logged 692 burn ticks against the chief's 205 in a 90-day mirrored-reboost run. This also hit default settings for any phasing burn longer than one tick. Now each firing records which controller started it, and only that controller continues it. Phasing also yields the thruster while a station-keeping firing is still committed after `burnOn` drops. The burn-accuracy regression test gained a 120 s minimum-on-time case (a 4-tick firing) that fails without the fix.

**2. Eccentricity-neutral burns.** Tangential thrust at argument of latitude u changes the eccentricity vector by about (2Δv/v)(cos u, sin u). A burn spread evenly over whole orbits cancels out. But eclipse gating removes the same arc from every orbit, so a multi-orbit reboost builds up a one-sided eccentricity change.
* Measured with Basilisk (degree-2 gravity, a real `eclipse` module fed static Sun/Earth messages, compared against an unthrusted twin): a ~5 km reboost changed e by 4.9e-4 and a 15 km reboost by 1.1e-3. Template 05's own e is 0.001.
* New `StationKeepingConfig.eccentricity_neutral_burns` (default off). With it on, the model tracks the maneuver's accumulated eccentricity-vector change. A new firing only starts if it keeps that change within one orbit's natural excursion of continuous thrust, a circle of diameter 4·accel/(v·n). Firings are capped at `max(min_on_time_s, dt)` so the gate is re-checked often. The thruster simply waits for the balancing side of the orbit.
* Results: the ~5 km reboost's Δe fell from 4.9e-4 to 2.3e-4, which is the one-orbit bound. The 15 km reboost's Δe fell from 1.1e-3 to 2.1e-4, at the cost of spreading the burn over 0.71 d instead of 0.35 d. Δa per unit Δv is unchanged, since Gauss's equation for a doesn't depend on where tangential thrust is applied.

**Why Basilisk's `thrusterDynamicEffector` was NOT used.** Its thrusters are fixed in the body frame, so an along-track burn would need the spacecraft to point along its velocity. An orbit-only scenario has no attitude control at all. The model keeps the ideal inertial force but gives it real firing constraints. A firing shorter than a tick is applied as its average force over that tick, which delivers the same impulse.

**Wiring.** Schema validation (`min_on_time_s` must be finite and in [0, 86400] s). The Spacecraft editor's station-keeping group, the Phasing Formation dialog's propulsion group, and the CLI (`--min-on-time-s`, `--eccentricity-neutral-burns`) all expose both fields. Old scenario files without them load with the defaults, and the defaults reproduce the previous behaviour bit-for-bit.

**Three more real bugs, found by the 90-day verification runs and fixed.** One run had both deadbands at 2 km (so the chief reboosts), a 300 s minimum on-time and eccentricity-neutral burns. It used 33.6 m/s over 115 phasing cycles. A per-tick diagnosis showed:
* **The follower overshot after the chief's reboost.** The follower carried its *mirrored* reboost on as if it were a safety-floor burn, until its one-orbit smoothed altitude caught up with the chief's. That average lags a burn, so the follower overshot by ~730 m of semi-major axis. A mirrored burn now ends with the chief's.
* **A coarse thruster ran a correction every day.** A trim finer than one impulse bit was rounded to whole firings. That left up to half a bit (~130 m of semi-major axis, ~18 km/day of drift), so a full correction ran every day. Such a trim is now flown as an exact pair of opposite firings, but only when neither skipping it nor rounding it to one firing lands within the 25 m tolerance. (Splitting every sub-bit trim doubled the stock formation's cost, because a typical restore needs just under one bit.)
* **Eccentricity-neutral splitting left too-short pieces.** It could leave a remainder shorter than one minimum firing. It no longer does.

**Verified over 90 days with Basilisk:** degree-2 gravity, a real `eclipse` module with a static Sun, a 50 mN thruster and 105 kg spacecraft. "300 s" means a 300 s minimum on-time with eccentricity-neutral burns.

| configuration | thruster | phasing Δv | separation, last 30 days | corrections |
|---|---|---|---|---|
| the user's case (100 km target, placed 50 km, deadbands 2/15 km) | ideal | 0.017 m/s | 104–109 km | the initial one |
| same | 1 s on-time + e-neutral | 0.017 m/s (identical) | 104–109 km | the initial one |
| same | 300 s | 0.29 m/s (1.43 before the fixes) | 90–94 km | the initial one |
| stock 50 km formation (deadbands 15/15 km) | 300 s | 0.29 m/s (0.86 before) | 49.9–51.2 km | 1 (day 35) |
| chief reboosting (deadbands 2/2 km) | ideal | 0.014 m/s; station-keeping 276/275 burn ticks | 46.2–47.9 km | none |
| same | 300 s | 0.59 m/s (33.6 at worst before); 205/204 burn ticks | 45.8–47.0 km | 1 |

No run suspended. A 300 s firing of 50 mN is ~260 m of semi-major axis, so a coarse thruster costs real Δv: it is roughly one impulse bit (0.14 m/s) per firing the formation needs. A realistic on-time for this thruster class (well under one 30 s tick) costs nothing. Template 05 keeps both settings off, so its published numbers are unchanged. New unit tests cover firing ownership, the mirror end, the exact pair, the no-split cases and the chunking rule.

## Real bug from a user's full test run: opening Propagation Setup wrote their cache path into the scenario

The user's first complete `pytest` run on their own machine: 1479 passed, 11 skipped, 20 failed. All 20 failures were the template round-trip test (open every editor on every template, click OK, nothing may change), and all at `space_weather.local_file_path: None -> '/home/<user>/.cache/SpaceMissionStudio/spaceweather/SW-All.csv'`.
* **Real dialog bug.** The Propagation Setup dialog pre-filled "Local CSV file" with the most recently startup-fetched CelesTrak CSV for *every* scenario. Merely opening it on a `synthetic`-source scenario and clicking OK wrote the user's absolute cache path into the scenario, which marked it modified and leaked that path into any file they saved and shared. The cached file is now suggested only when the source is, or is switched to, `local_file`.
* **Why the sandbox never saw it.** The sandbox has no cache file. An earlier fix had isolated only that dialog's own test file from the real cache, which hid the dialog bug instead of fixing it. The real cache was also reachable from any test: `spaceweather.DEFAULT_CACHE_DIR` is computed from `Path.home()` at import time, often during collection, before `conftest`'s `Path.home` patch. `tests/conftest.py` now redirects it for every test.
* Reproduced with a populated fake home directory: the old code gives 21 failures (the 20, plus the new regression test), the fixed code none.

## Real performance bug from a user's 30-day run log: live runs slowed down quadratically

The user's 30-day template 05 run log was clean: no warnings, no errors, no phasing suspension, and 435 KB against the 116 MB of the earlier 90-day run, so the eclipse-logging fix works. But the run slowed down as it went. Each 1.7% progress step (half a simulated day) took ~3 s at the start and ~22 s at the end, 11 minutes in total.
* **Cause.** `run_live` extracts the results 60 times per run to feed the live plots. Each extraction recomputed every recorded sample's osculating and mean orbital elements: a Python loop of `rv2elem` / `clMeanOscMap` calls, measured at 9.6 s + 3.2 s per spacecraft for a 30-day, 30 s-step history. The work per step grew with simulated time, so the total grew with the square of the duration. A 90-day run would have spent over an hour on it.
* **Fix.** `SimulationService._orbit_elements` caches each spacecraft's elements and computes only samples not computed before. Both mappings are pointwise, so the result is identical (asserted bit-for-bit against one full pass). The NaN guard's message still reports the recorded sample index.
* **Measured.** For the user's run's pattern (60 updates, 2 spacecraft, 30 days), element extraction drops from ~13 minutes to 27 s here.

## Phasing was too slow: correction window default 21 -> 3 days

The user's next 30-day run (their 100 km configuration, follower placed 50 km ahead) behaved correctly: it closed steadily to ~97 km, then held 97–98 km for 0.018 m/s, with no station-keeping burns. But they found it "very slow": reaching the target took ~22 days. That's by design rather than a bug. Every correction is planned to take `correction_window_days`, which defaulted to 21 days, so the drift rate was only ~2.2 km/day. A correction's Δv scales roughly as 1 / window.

Verified with Basilisk (eclipse harness, the user's configuration, 30 days):

| window | target reached | phasing Δv | separation afterwards |
|---|---|---|---|
| 21 days | day ~21.6 | 0.017 m/s | 94–99 km |
| 5 days | day ~5 | 0.077 m/s | 95–98 km |
| 3 days | day ~3 | 0.13 m/s | 98–102 km |
| 1 day | day ~1 | 0.38 m/s | 97–100 km |

No overshoot, cycling or suspension in any case. The default is now **3 days** in the schema, the phasing-formation generator and its dialog, the spacecraft editor and the CLI, and a new test keeps them in agreement. The editor's tooltip states the Δv trade-off.

Over 90 days, stock template 05 still fires its one drift correction (day ~28 in the degree-10 no-eclipse harness, ~35 with eclipses). That correction now finishes in ~2.4 days instead of ~2 weeks, with the separation held at 45–52 km, for 0.014 m/s instead of 0.003 m/s. The chief-reboost case is unchanged (one trim, 0.014 m/s, burns 276/275). The template's description now quotes these numbers. Old scenario files that set the window explicitly keep their value; only files that omit it pick up the new default.

## Device catalog from the user's supplier database (+31 devices), and an editor precision bug

The user supplied a supplier database: a market survey of 609 products for 100–500 kg LEO/SSO satellites, dated 07 Oct 2026, with ITAR status, heritage, sources and an audit column. They asked for every applicable sensor and actuator to be considered. 165 rows are ADCS, GNSS or propulsion products.

**Inclusion rule** (the database's own criteria, applied mechanically). A product is added to `engine/device_catalog.py` only if all five hold:
1. It maps to a kind the app simulates (star tracker, IMU, sun sensor, magnetometer, reaction wheel, magnetorquer, thruster).
2. It has flight heritage; "Development – monitor" rows are excluded.
3. The database doesn't flag it "Check / export risk".
4. The database gives the numbers its kind needs.
5. The database doesn't call it too small or oversized for 100–500 kg.

That gives 31 new entries:
* 8 star trackers;
* 1 IMU;
* 3 sun sensors;
* 2 magnetometers;
* 2 reaction wheels;
* 3 magnetorquers;
* 12 thrusters.

Every entry cites the database's own source link, and every datasheet-to-parameter conversion is stated in the entry's notes. The conversions follow the existing entries:
* noise is converted to 1-sigma, using the worse axis or range end;
* angular random walk is converted to per-tick noise for a 1 s tick;
* sun-sensor angle × sin 45° gives the cosine-law noise;
* wheel inertia is momentum / top speed, with 6,000 RPM assumed where the speed isn't published.

Two new fields, `heritage` and `procurement_status`, are shown in the editor's catalog preview. The seven original entries were updated from the database:
* **Teldix RSI 04-33-60A:** the database flags it "Check / export risk" (US parent); it is kept for existing scenarios, with the flag in its note.
* **SS200 and MTQ800:** the database's audit found no ITAR-free statement on the vendor pages the old notes relied on.

**Not added**, with reasons:
* **No matching simulation model:** CMGs, Earth/horizon sensors, GNSS receivers and integrated ADCS units.
* **Missing numbers:** for example Sodern Auriga, Exail Astrix NS and Astrofein wheels, which have no torque or accuracy figures in the database.
* **Flagged "Check / export risk":** for example Honeywell, LITEF and Safran PPS.
* **Development status:** for example ASPINA and SITAEL HT100.
* **Sizing called out by the database:** for example SteamJet, ThrustMe NPT30 and CubeSat-class wheels.

**Real bug found while verifying.** Applying each preset through the real editor (a new test does this for all 38 entries, then validates the resulting spacecraft) showed that the existing MM200 magnetometer's 1.18e-9 T noise came back as 1.2e-9 T. `gui/widgets.PreciseDoubleSpinBox`, used in 18 places, kept values to 10 decimal places, so anything finer was silently rounded on open + OK. It now keeps values exactly (40-decimal internal storage, shortest-exact display text), with a parametrized round-trip test.

## The template "Customize" wizards were very incomplete: every setting is now reachable

The user found the wizards "very incomplete": template 05's offered no correction window and nothing for the chief, and they asked for an audit of all of them. A measured audit nudged each wizard field and recorded which scenario settings moved. Every wizard reached only 5–20% of its template's numeric and on/off settings, for example 6 of 71 for template 05 and 2 of 56 for template 17.

**Fix.**
* **Generated sections.** A new `gui/wizard_settings.py` builds sections for every remaining setting from the scenario itself, grouped by spacecraft and component: orbit; mass, drag & radiation pressure; attitude; station-keeping; phasing keeping; sensors & actuators; power; and so on. It then adds ground stations, the mission sequence, Monte Carlo and environment & simulation. Because the sections come from the scenario, nothing can be left out.
* **Labels and units.** These come from a curated table. Sensor and actuator parameters use the device editor's own descriptions, with a sub-heading per device, and vectors are shown on one row.
* **What isn't offered.** Text settings (names, epoch, mode names) need the full editor. Vizard model offset, rotation and scale are only offered when a model is set.
* **No duplicates.** The curated "key settings" pages stay first, and the generated sections leave out anything they already offer.
* **Two-pane dialog.** The wizard is now a dialog with a section list and a filter box (typing "correction" jumps to the correction window), instead of a 16-step Next/Next/Next flow. Only fields the user actually changed are written back.
* **Tests.** New tests check that every template's wizard offers 100% of its settings with nothing twice, that template 05's wizard sets the correction window and the chief's orbit and station-keeping, and that the filter works. The existing round-trip tests (no edits reproduce the template exactly) pass for all 20 templates.
* **Layout fix found while checking.** Each field reserved width for its ±1e15 range, and a 9-element inertia row made the dialog 3,454 px wide. Fields now have a modest minimum width, and the inertia tensor shows as three rows.

**The other wizards, audited the same way.**
* **Phasing Formation generator** (Spacecraft list → "Generate phasing formation…"): every request field was already in the dialog, but nothing could be set on the chief. The follower's station-keeping mirrors the chief's reboosts, so the chief's own station-keeping is part of the formation's design. A new "Chief station-keeping" section is prefilled from the selected chief, with defaults when it has none and the target altitude taken from its orbit. Unchecking it removes the chief's station-keeping. The follower's groups are now labelled as the follower's, and the intro is one line instead of a paragraph.
* **Walker Constellation generator:** every request field was already in the dialog. It gains a "Sun-synchronous" button that sets the inclination for the entered altitude and eccentricity (Earth only), as the orbit editor already had.
* **Spacecraft Template dialog:** a preset picker that opens the full editor, so there was nothing to add.

## The Load tab's template description was "just awful UI/UX"

The user's screenshot showed the Load tab's description panel for template 05: about 7,200 characters of grey prose, including the template's development audit history, class and docstring references, and verification notes. It sat below the 20-row template list, so it was only visible after scrolling the whole tab.

* **All 20 descriptions rewritten** (new `scripts/_template_descriptions.py`, used by the generator). Each is a one- or two-sentence summary followed by short "What to look at" and "Try changing" bullets, plus a "Note" or "Limitations" bullet where it matters. They now run 470–1,000 characters each, down from up to 7,200. Development history stays in this file and the generator's code comments.
* **Two wrong series names fixed** in the rewrite: template 19 pointed to `power.battery_soc` (the real series is `battery_charge`), and template 20 to `sensor.therm-1.temperature` (it is `sensor.therm-1`).
* **The Load tab** now has a title-and-description card below the list, split by a draggable divider, each scrolling on its own, and visible as soon as a template is selected. Descriptions are rendered as rich text, with bold headings and bullet lists. The intro and hint are one line each, and the hint now says that Customize changes any setting.
* **Tests** keep descriptions short and structured: under 1,400 characters, summary under 300, bullets under 200, with no development-history wording. They also check the rich-text rendering, including escaping, and that the card is visible without scrolling the tab.

**Follow-up: "a lot of unused empty space".** Showing one section at a time left a one-field section ("Reaction wheels" in template 07) as a nearly empty dialog with an 800 px wide field. The Customize dialog now shows every section as a compact card on one scrolling page. The left list is a table of contents: click to jump, and it follows the scroll. Fields have a fixed, readable width; a curated field's help text sits to its right instead of in a narrow column underneath; and card titles no longer repeat the spacecraft name that heads their group.

## Sensor/actuator and attitude-control editors: forms instead of bullet lists over JSON

The user sent four screenshots:
* The Edit sensor/actuator dialog was "cramped": a bullet-list parameter reference squeezed into a small scroll box, above a JSON box.
* The selected device's information was "raw text … unclear, confusing, all over the place and not professional". The IMU with the ARIETIS-NS preset was a second example.
* The spacecraft editor's Attitude control tab had the same pattern: bullet lists of keys above two raw JSON boxes.

**A shared parameter form.** New `gui/param_form.py` (`ParamForm`) turns a list of parameter specs into labelled rows:
* **Labels.** Each row has a short name. The unit is in the field (`rad/s`, `N*m`, …) and the full description is in the tooltip.
* **Optional parameters.** Each has a checkbox. Unticked means the key is left out and Basilisk's default applies.
* **Field types.** On/off values are checkboxes, and named options (fault modes) are drop-downs. A 3-component vector gets x/y/z boxes on their own line, with Normalize only for directions.
* **Other keys.** Any key the specs don't know stays editable in a collapsed "Advanced: other parameters (JSON)" box. It opens automatically when such keys are present, so nothing is lost on open + OK.
* **Labels for every parameter.** Each sensor/actuator parameter got an explicit short label (for example "Bias random-walk bound" instead of "Long-run random-walk BOUND on the noise above").

**Sensor/actuator dialog.**
* **Layout.** Kind and Name at the top, a note banner only when the kind has a note, the device picker and card on the left, and the parameter form on the right. Required and optional parameters are grouped.
* **Device card.** It is now structured rich text: name and country, the summary, a labelled table (Heritage, Procurement in its status colour, Export control, Source link), and "How the values were set" in small print.
* **Defaults.** A new item starts with the required parameters at a working example and the optional ones at Basilisk's defaults. Switching Kind away and back keeps edits, and Reset to template restores the defaults.
* **No toast over the buttons.** The "Applied … values" toast covered the OK button and has been removed, since the form visibly changes.

**Attitude control tab.**
* **Mode description.** A one-line description of the selected mode replaces the key list.
* **Pointing parameters.** A form, hidden when no mode is selected. locationPointing's "Point at ground station" lists the scenario's stations, and it is mutually exclusive with "Point at celestial body". The mode's values are kept when switching modes away and back.
* **Control gains.** A form in which unticked gains use the defaults.
* **Comms pointing.** The group has shorter labels, collapses to its title while unticked, and shows its unit in the field.

**New catalog device: VECTRONIC Aerospace VRW-D-6.** Added from the user's datasheet (A4, 25 Apr 2024):
* **Values.** 6.0 N*m*s, ±6,000 RPM, 50 mN*m (90 mN*m variant noted), and rotor inertia 9.56e-3 kg*m^2.
* **Status.** Built in Berlin; the datasheet has no ITAR statement, so the entry is "RFI - confirm ITAR in writing".
* **Basilisk check.** Basilisk's `rwFactory` builds it with H_max = 6.007 N*m*s, matching the datasheet's 6.0 N*m*s. A full simulation was not possible in this container because the SPICE kernels are not cached and there is no network.

**Tests.** New tests cover:
* the device card's structure;
* units in fields and optional-parameter checkboxes;
* the attitude tab's form (station list, exclusive targets, no bullets, JSON collapsed);
* round-tripping existing fsw/control params, including unknown keys;
* mode switching that keeps edits.

The tests that assumed JSON boxes now use the form. The catalog test applies and validates all 39 entries through the dialog.

## Typed lists replaced: wheel biases, separation stages, report series

A follow-up check of every other editor found no more bullets-over-JSON boxes. It did find three fields where you had to know a hidden structure to type them; the user asked for all three to be fixed.

**Wheel speed biases** (magnetic momentum management):
* **Before.** A comma-separated list matched to the reaction wheels by position, with nothing showing which number belonged to which wheel.
* **Now.** One labelled `rad/s` box per wheel, named after the wheel, in the actuator-list order the engine uses.
* **Kept in step.** Adding or removing a wheel on the Sensors/actuators tab adds or removes its row (new wheels start at 0).
* **No wheels.** The group says so, and OK explains that a reaction wheel is needed.
* **Shared widget.** This uses the new `gui/number_list.NumberListEditor`.

**Target separation** (phasing keeping):
* **Before.** A comma-separated km list.
* **Now.** Numbered stages ("Stage 1", "Stage 2", …), each a km box with Remove, plus "Add stage"; the last stage can't be removed. It uses the same widget.

**Report command series** (mission sequence):
* **Before.** Typed one per line from memory, where a single typo stopped the run.
* **Now.** A checkable list of the series this scenario will produce, with a filter and "Clear selection". Nothing ticked still means "every series".
* **Unknown names.** A saved name the scenario doesn't produce is kept, so open + OK changes nothing, but it is shown in red with "(not produced by this scenario)".
* **Where the list comes from.** A new Basilisk-free `engine/series_names.expected_series_names()` mirrors the engine's own rules for which series exist.
  * **Checked against a real run.** For template 05 it matches the user's own exported results exactly (40 series).
  * **Basilisk check.** A new `requires_basilisk` test compares it with a shortened real run of every template. It could not run here, because the SPICE kernels aren't cached in this container.
* **Half-edited scenarios.** The scenario editor feeds the list from an unvalidated draft, so it works mid-edit.

**Tests.**
* Per-wheel rows follow the actuator list, including the no-wheel case.
* Separation stages add and remove, and never go below one.
* The report list ticks, filters and clears, and keeps and flags an unknown series.
* The series prediction is checked for templates 05, 07 and 19, plus the real-run comparison above.
* The tests that typed comma lists now use the new widgets.
