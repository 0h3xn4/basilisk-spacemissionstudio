# SpaceMissionStudio — Design-Philosophy Audit (Phase 1: read-only)

Scope: `SpaceMissionStudio/` (the PySide6 GUI + CLI + Basilisk-backed
simulation engine), audited against the instrument design philosophy in
the brief. No code changed. File:line citations are to this repo's
current `claude/awesome-knuth-2vlhqu` branch.

Note on scope per your follow-up: this project is explicitly
closed-off/offline by design already (`README.md`'s "Closed-off/offline
policy", `engine/spaceweather.py`'s module docstring) — no network calls
at runtime, only at install time and explicit, user-initiated data
fetches (SPICE kernels, Vizard binary). Principle 16 is evaluated with
that as the fixed constraint, not a gap: web frontend / cloud batch /
hosted-AI items are out of scope by design, not missing features.

Legend: **Done** / **Partial** / **Missing** / **N/A**.

---

## Top risks ranked (where a result could be silently wrong or unverifiable)

1. **No run provenance captured with results.** `engine/results.py`'s
   `ResultSet` (line 102) has no field for Basilisk version,
   SpaceMissionStudio version, RNG seed, or a hash/copy of the input
   scenario. A CSV exported via `TimeSeries.to_csv` (`results.py` ~88-97)
   carries units in its header but nothing about what produced the
   numbers. Two runs made a year apart, after a Basilisk upgrade changed
   a module default, are indistinguishable after the fact. This is the
   single biggest gap against principle 1's core "trust" requirement.
2. **No independent conservation/drift diagnostic.** `engine/service.py`
   does translate a Basilisk integrator NaN/inf crash into a specific,
   actionable error (`service.py:230-256`, `:348-372`) — a real strength,
   not absent — but that only fires on a hard blowup. There is no
   periodic energy/angular-momentum drift check, step-size-adequacy
   check, or convergence diagnostic run on an otherwise "successful"
   result. A slow, non-crashing integration error currently ships
   silently. (This session's own thermal-sensor bug — an unrealistic
   heat capacity driving `sensorThermal`'s explicit-Euler integration to
   `-8.8e+182` — was caught only because a *test* happened to assert
   `> 0`; nothing in the shipped product would catch the equivalent in a
   user's own scenario.)
3. **Units are a naming convention, not a checked type.** Every field is
   consistently unit-suffixed (`area_m2`, `gyro_noise_rad_s`,
   `panel_area_m2` — e.g. `schema/scenario.py:250-255`) and that
   discipline is real and valuable, but there is no `pint`/`astropy.units`
   (or equivalent) enforcement anywhere in the repo (confirmed by grep —
   no hits). Most numeric fields are validated only for sign/range where
   a *physical* constraint exists (e.g. `absorptivity` in `(0, 1]`,
   `schema/scenario.py`'s thermal-sensor checks added this session); a
   plain magnitude mistake (an area off by 1000x, a mass typed in grams)
   passes validation and runs silently.

Everything else below is lower-severity (missing capability or rough
edge, not a silent-wrong-answer risk).

---

## 1. Trust and correctness — **Partial**

**Done:**
- No hidden epoch/frame assumption that isn't documented and enforced:
  `engine/fsw.py`'s own docstring (lines ~79-95) explicitly calls out the
  `hillPoint`/`velocityPoint` central-body-relative-frame assumption and
  exactly which `engine/service.py` setting (`spice_object.zeroBase`)
  makes it true — a real bug this project hit and then documented at the
  point of risk, not swept under the rug.
- Validation gives specific, actionable messages, never a bare exception
  — `ScenarioValidationError`/`FswError`/`SimulationServiceError`
  throughout `schema/scenario.py`, `engine/fsw.py`, `engine/service.py`.
  `schema/validation.py`'s `validate_all()` collects every mission
  -sequence problem with an item path in one pass, not just the first.
- Determinism by default: every Basilisk noise/fault module in this app
  keeps `SysModel`'s own fixed default `RNGSeed` (`0x1badcad1`) unless a
  Monte Carlo batch explicitly disperses seeds
  (`engine/monte_carlo.py:343`, `setShouldDisperseSeeds(True)`) — the
  same scenario always reproduces the same single run.
- Reasonable, hard-crash-avoidance validation: e.g. `reaction_wheel`
  `rw_type="custom"` missing `u_max`/inertia is caught in schema
  (`schema/scenario.py` ~830-875) specifically because the underlying
  `rwFactory.create()` would otherwise call `exit(1)` on the whole
  process — a real, previously-hit failure mode, now defended against.

**Partial / Missing:**
- No run provenance (see Top Risks #1).
- No active conservation/drift/convergence diagnostics (see Top Risks
  #2) beyond crash-translation.
- Units are convention, not type-enforced (see Top Risks #3).
- Uncertainty/fidelity is only as good as Monte Carlo dispersions
  (`DISPERSION_QUANTITIES = ("dry_mass_kg", "attitude_sigma_bn")`,
  `schema/scenario.py:116`) — a narrow set; there's no fidelity
  indicator in results (e.g. "idealized actuation" vs "real hardware"
  shown next to a plot), only in each template's prose `description`.

---

## 2. GUI/script parity — **Done**

- `cli.py` is a full headless surface, not a GUI shim: `validate`, `run`
  (headless, CSV export), `monte-carlo`, `kernels-status`,
  `spaceweather-resolve`, `generate-constellation`,
  `generate-phasing-formation`, `gui` (`cli.py:416-520`,
  `build_parser()`). Every one of these is also reachable from the GUI.
- `engine.service.SimulationService` is a plain, importable, scriptable
  class — not GUI-coupled.
- Scenario files are plain, diffable JSON, with `CURRENT_SCHEMA_VERSION`
  (`schema/scenario.py:66`) and a real migration registry
  (`schema/migrations.py`) already exercised across a real breaking
  change (v1→v2, HISTORY.md).

No gap found here worth flagging.

---

## 3. Time as first-class — **Partial**

**Done:**
- A single, consistent time base: `engine/time_system.py` is the one
  source of truth for UTC/TAI/TT/ET conversions, used everywhere.
- Scenario vs. wall-clock vs. compute-time distinction exists in
  practice: `sim_settings.duration_days` (scenario time) vs. real
  progress/cancel during a run (`gui/run_worker.py`, Abort Simulation).
- An epoch-vs-elapsed-time x-axis toggle exists in the results plot
  (`gui/results_widget.py`, per `HISTORY.md`'s Phase-era entry and this
  session's own task list item #12).

**Missing:**
- No event/access Gantt view. Ground-station access
  (`has_access`/`slant_range`/`elevation`/`azimuth`) is recorded as
  ordinary time series and plotted as a line, not as a click-to-jump
  access-window Gantt chart (`gui/results_widget.py` — confirmed only a
  single combo-box-selected line plot, no Gantt widget anywhere in
  `gui/`).
- No synchronized/linked timeline across multiple views: the results
  widget shows exactly one series at a time via `series_combo`
  (`gui/results_widget.py:481-527`), not multiple panels sharing a time
  cursor.

---

## 4. Analytical visualization — **Partial**

**Done:**
- A deliberate, limited, consistent visual system
  (`gui/theme.py`'s own docstring: "a small, deliberately limited
  palette... reused... never a second accent color introduced for a
  single widget").
- Plotly-based plots (`QWebEngineView`) give real interactivity
  (zoom/pan/hover) for free, plus a PNG export path
  (`gui/results_widget.py:538-866`, `save_png_button`).
- CSV export always carries units in the header
  (`engine/results.py`'s `TimeSeries.to_csv`).

**Missing:**
- Single theme only — no dark-mode toggle (`theme.py` defines one fixed
  QSS/QPalette, applied once at startup; no mode switch anywhere in
  `gui/`).
- No deliberately colorblind-safe categorical palette: multi-series
  plots (3-axis vectors, `wheel_0..wheel_N`, `thruster_0..thruster_N`)
  rely on Plotly's default color cycle, not a chosen, verified-safe set.
- Export is PNG-only, not vector (no SVG/PDF), so "publication-quality"
  export is raster-at-whatever-resolution, not scalable.
- No linked/multi-panel views (see §3) — a real limit on "high data
  density" for cross-subsystem analysis (e.g. watching attitude error
  and RW speed together currently means switching the one dropdown back
  and forth).

---

## 5. Object model — **Done**

- Visible hierarchy + property inspector: `gui/spacecraft_editor.py`
  (tabbed: orbit, sensors/actuators, FSW, power/propulsion/link budget),
  `gui/sensor_actuator_editor.py`'s per-kind dialog with live hint text
  and a vector-row editor for direction fields.
- Reusable component library: `engine/spacecraft_templates.py` (3 bus
  templates) and `engine/device_catalog.py` (7 real, sourced,
  manufacturer-specific sensor/actuator presets with citations).
- Dependency visibility is a genuine strength, not just present:
  `schema/references.py` refuses to delete a spacecraft/ground station
  still referenced elsewhere, listing every referencing item by path,
  and rewrites every reference atomically on rename — closer to a real
  CAD-style dependency graph than most tools in this space offer.

No gap found here worth flagging.

---

## 6. Progressive disclosure — **Done**

- Good defaults everywhere (every `_ParamSpec`/dataclass field has a
  sane default or a worked "Reset to template" example,
  `gui/sensor_actuator_editor.py`).
- Full control one level deeper: the open `params` dict + raw-JSON box
  is a deliberate, documented design choice precisely so a new Basilisk
  kwarg never needs a schema migration (`sensor_actuator_editor.py`'s
  module docstring).
- Wizards are never the only path: `gui/template_wizard.py`'s own
  docstring states the "Customize..." wizard is a curated subset, and
  "Open Template" (the full editor) is always available alongside it.

No gap found here worth flagging.

---

## 7. Expert efficiency — **Missing**

- Keyboard shortcuts exist only for the standard File/Run actions
  (`gui/main_window.py:224-276`: New/Open/Save/Save As/Quit via
  `QKeySequence.StandardKey`, Run via a hardcoded `"Ctrl+R"`). No
  command palette, no global search across scenario objects, no macro
  recording/playback, no customizable/savable layouts (confirmed by grep
  — no `QShortcut`/palette/macro hits beyond those menu actions).
- `gui/mission_output_widget.py` has no filter/search box over its own
  output (`MissionOutputWidget`, confirmed — only a CSV export button).

This is a real, consistent gap against the brief's "expert efficiency"
principle, though it's also the area where GMAT/STK-caliber tooling sets
an unusually high bar — treat as a capability roadmap item, not a defect.

---

## 8. Analysis workflow — **Partial**

**Done:**
- Monte Carlo batch analysis is real, not simulated:
  `engine/monte_carlo.py` bridges `Basilisk.utilities.MonteCarlo`, with
  `dispersions` (dry mass, attitude) and an archived-results directory
  (`cli.py cmd_monte_carlo`).
- Long operations don't block: `gui/run_worker.py` runs
  `SimulationService`/Monte Carlo on a background `QThread`; **Abort
  Simulation** cooperatively cancels between chunks, keeping partial
  results (confirmed via this session's own task history, item #13, and
  `main_window.py`'s run/cancel wiring).

**Missing:**
- No native parameter sweep / trade-study runner (beyond Monte Carlo's
  random dispersions) — no "run this scenario across a grid of
  altitude×inclination" feature.
- No targeting/optimization: `schema/command.py`'s own docstring
  (lines 59-61) explicitly states GMAT's `Target`/`Vary`/`Optimize`
  equivalents are "explicitly NOT included... future work."
- No run snapshotting/diffing (compare two results side by side) and no
  undo/redo for scenario edits — the GUI tracks dirty state and prompts
  on unsaved-changes close, but there's no edit-history stack (confirmed
  by grep — no `QUndoStack`/undo hits anywhere in `gui/`).
- No caching/incremental recompute:
  `engine/service.py:485-489`'s own docstring says a `SimulationService`
  is "not designed to be reset and rebuilt" — every run rebuilds gravity,
  spacecraft, sensors, etc. from scratch, by design. Reasonable given
  Basilisk's own architecture, but it rules out "tweak one parameter,
  rerun fast" without a full rebuild.

---

## 9. Long-run feedback — **Done**

- Progress + cancel + partial results: `run_live()`'s chunked streaming
  (`engine/service.py`) feeds the GUI's live-updating plot
  (`_on_run_progress`, `gui/main_window.py`); Abort Simulation keeps
  whatever was produced.
- Structured, persistent logging: `gui/logging_setup.py` — built
  specifically from a real user complaint ("would be good if you could
  add some kind of debug mode... saves it in a log file"), so a crash
  leaves more than one bare traceback line.
- Actionable errors are a consistent strength throughout — nearly every
  `_require()`/raised error in this codebase names the specific field,
  the specific wrong value, and what to do about it (spot-checked across
  `schema/scenario.py`, `engine/fsw.py`, `engine/service.py` all
  session).

**Partial:** logs are file-backed but not surfaced as a searchable,
object-linked panel in the GUI itself (see §7's note on
`mission_output_widget.py` having no filter box) — you can read the log
file, but the GUI doesn't let you jump from a log line to the object it
concerns.

---

## 10. Interoperability — **Missing**

- No CCSDS OEM/OPM/AEM import or export.
- TLE is accepted as an orbit *input* (`OrbitIC(type="tle", ...)`,
  `schema/scenario.py`) but there's no OMM/TLE *export* of a propagated
  result.
- SPICE is used internally for kernels (`engine/kernels.py`) but not
  exposed as a general interchange format for user data.
- No CZML export for Cesium-style web visualization (Vizard, a separate
  external application, is this project's 3D-viz path instead — a
  reasonable substitute, but not CZML/web-portable).
- Export is CSV only (`TimeSeries.to_csv`); no HDF5, no direct
  MATLAB `.mat`, no Excel writer (confirmed by grep — no `h5py`,
  `scipy.io`, `openpyxl` anywhere in the dependency tree or code).

This is the most consistently "Missing" section — reasonable for a
single-developer-scope tool, but worth flagging since the brief
specifically names these formats.

---

## 11. Reporting — **Partial**

- The Mission Sequence `report` command + `gui/mission_output_widget.py`
  (`CommandSummary`/`ReportEntry`, CSV export) is a real, working
  "generate structured output from a run" path, and CSV exports do carry
  units (§4).
- **Missing:** no template-driven, regenerate-from-inputs formatted
  report (HTML/PDF) with embedded run metadata — confirmed absent (no
  `jinja`/`weasyprint`/`ReportLab` anywhere in the repo).

---

## 12. Config management — **Done** (with one caveat)

- Scenario files are self-contained, human-readable JSON with a version
  field and a real migration path (§2).
- **Caveat, shared with Top Risk #1:** "self-contained" currently means
  self-contained for re-*editing*, not for re-*verifying a past result*
  — the scenario file alone doesn't carry what version of this app or
  Basilisk last ran it.
- Containerizable: no Dockerfile exists (confirmed by grep), but the
  project does ship real, working installers (`.deb`, a plain wheel,
  a Windows Inno Setup installer, `packaging/`) — a deliberate choice
  documented throughout `packaging/README.md`, not an oversight. Treat
  "containerizable" as **N/A by current distribution strategy** rather
  than a gap, unless Docker specifically becomes a stated goal.

---

## 13. Reliability — **Partial**

**Done:**
- No UI freezes during compute: background `QThread` execution
  (`gui/run_worker.py`), confirmed throughout this session's own test
  suite (`tests/gui/test_run_worker.py`).
- Backward compatibility is actively maintained, not just claimed: the
  v1→v2 schema migration is real and tested
  (`schema/migrations.py`, `tests/test_migrations.py`).
- Crash diagnosability: `logging_setup.py` (§9).

**Missing:**
- No autosave / crash recovery for in-progress scenario edits (confirmed
  by grep — no autosave/session-restore hits anywhere). A crash mid-edit
  loses unsaved work; the GUI only prompts "unsaved changes" on a normal
  close, which doesn't help after an actual crash.

---

## 14. Documentation — **Done**

- In-context help is pervasive and specific, not generic: every
  `_ParamSpec`/`WizardField` carries real physical help text with units
  (`gui/sensor_actuator_editor.py`, `gui/template_wizard.py`), and every
  bundled template's `description` field explains what it teaches, what
  to look at, and what to try changing (`scripts/_generate_templates.py`,
  all 20 templates).
- Runnable examples: the 20 bundled templates are real, validated,
  round-tripped `Scenario` objects, not static prose.
- `HISTORY.md` is an unusually thorough theory/validation log (every
  real bug, every Basilisk-API confirmation, cited against actual
  Basilisk source/examples) and `USER_MANUAL.md` covers the GUI
  end-to-end walkthrough.

No gap found here worth flagging — this is a genuine strength, arguably
above the bar the brief sets.

---

## 15. Extensibility — **Missing**

- Sensor/actuator "kinds" are a closed, hardcoded tuple
  (`SUPPORTED_SENSOR_KINDS`/`SUPPORTED_ACTUATOR_KINDS`,
  `schema/scenario.py:103-104`), not a registry a third party can extend
  without editing this repo.
- No plugin architecture, entry-point mechanism, or documented extension
  API anywhere (confirmed by grep — no `entry_points`/plugin hits).

Reasonable for current scope (single-developer, closed-off tool), but a
real gap if third-party extension is ever a goal.

---

## 16. Modern directions — **N/A by design** (per your note)

- Web frontend / cloud batch: explicitly out of scope — this project is
  closed-off/offline by design (`README.md`'s "Closed-off/offline
  policy"; network access only at install time or an explicit,
  user-initiated fetch such as SPICE kernels or the Vizard binary,
  `engine/spaceweather.py`'s docstring, `gui/startup_fetch_dialog.py`).
  Nothing here should be read as a gap.
- Jupyter: no notebook integration, but `engine.service.SimulationService`
  is already a plain importable Python object (§2), so nothing
  architecturally blocks a user from driving it from a notebook today —
  just no bundled example of doing so.
- AI assistance producing inspectable/editable artifacts: N/A — not a
  stated goal for this tool, and would need to run fully offline to fit
  the project's own architecture.

---

## Summary

**Strongest areas:** progressive disclosure (§6), the object/reference
model (§5), scenario versioning and GUI/CLI parity (§2, §12),
documentation and in-context help (§14), and error-message quality
throughout (§1, §9). These are not just "present" — they're
unusually carefully done for a tool this size, with real bugs found and
fixed along the way rather than asserted away.

**Weakest areas, in order of what matters most to the brief's thesis:**
run provenance and active numerical-health diagnostics (§1, both touch
"can I trust this specific result"), expert-efficiency tooling (§7),
interoperability (§10), and extensibility (§15).

Ready for Phase 2 (roadmap) on your go-ahead.
