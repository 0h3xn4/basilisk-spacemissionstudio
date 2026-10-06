# SpaceMissionStudio — Design-Philosophy Roadmap (Phase 2)

Ranked by (impact on trust/correctness) × effort, per `docs/ux_audit.md`.
Nothing here is implemented yet — Phase 3 starts only after you approve
specific items below. Effort buckets: **Quick** (<0.5 day), **Medium**
(1-3 days), **Strategic** (bigger, or gated on a decision).

---

## Decisions needed before Phase 3 (my recommendation marked →)

1. **Units: full type-enforced units vs. incremental bounds checks?**
   Full `pint`/`astropy.units` adoption would touch nearly every field
   in `schema/scenario.py` and every consumer in `engine/`, is a new
   dependency, and carries real regression risk for a convention that
   currently works (consistent `_km`/`_rad_s` suffixes). → **Recommend
   incremental bounds/plausibility checks now (Quick win M1 below),
   defer full unit-typing as an optional Strategic item** — only revisit
   if a real unit-confusion bug actually occurs in practice.
2. **Reporting format: HTML or PDF?** PDF needs a new dependency with
   system-library requirements (`weasyprint` needs Cairo/Pango;
   `reportlab` is pure-Python but more code to lay out a report by
   hand) — either complicates the existing `.deb`/wheel/Windows
   installer story (`packaging/`). → **Recommend a template-driven HTML
   export first** (`jinja2`, pure-Python, no system libs, opens in any
   browser, still "regenerate from inputs"); treat PDF as optional later
   if actually needed.
3. **Plugin architecture: real third-party extensibility, or just make
   the internal kind-list easier to extend?** This is a closed-off,
   single-maintainer tool today. → **Recommend skipping a real plugin
   API for now** — low near-term benefit for the effort/risk; the
   existing `_KIND_PARAM_SPECS`-style dict pattern is already cheap to
   extend internally. Revisit if external contributors become a goal.
4. **Targeting/optimization (GMAT `Vary`/`Target`/`Optimize`
   equivalents):** `schema/command.py` already documents this as
   deliberately deferred. → **Recommend keeping it deferred** — a
   differential-corrector/targeter is a significant, physics
   -correctness-sensitive feature that deserves its own dedicated
   design pass, not a line item squeezed into this roadmap.
5. **Dark-mode toggle vs. colorblind-safe palette first?** Both are
   under §4 of the audit, but a real light/dark *toggle* is a theme
   -architecture change (`gui/theme.py` currently applies one fixed
   QSS/QPalette at startup); a colorblind-safe categorical palette for
   multi-series plots is smaller and matters more for "trust" (can you
   tell the series apart correctly). → **Recommend the palette pass
   first (Medium, below); treat a dark/light toggle as a separate,
   lower-priority item.**

If you'd rather decide differently on any of these, say so and I'll
replan that item's bucket/approach accordingly.

---

## Quick wins (<0.5 day each)

### Q1. Run provenance on every result (fixes audit Top Risk #1)
- **Rationale:** highest-impact, lowest-effort item in the whole audit —
  makes every result traceable to what produced it.
- **What:** add a `RunProvenance` (or similar) record to
  `engine/results.py`'s `ResultSet` — SpaceMissionStudio version
  (`spacemissionstudio.__version__`), Basilisk version (`Basilisk
  .__version__` if exposed, else the import's own version string),
  wall-clock run timestamp, integrator + `dynamics_task_rate_s` from
  `sim_settings`, and (when Monte Carlo is off) confirmation that the
  default `RNGSeed` was used. Populate it once in
  `SimulationService._extract_results()`. Include it in
  `TimeSeries.to_csv`'s export (a leading metadata block or a sidecar
  `.json`) and show it in the GUI's Results tab header.
- **Files:** `engine/results.py` (new field + `to_csv`),
  `engine/service.py` (`_extract_results`), `gui/results_widget.py`
  (display), `cli.py` (`cmd_run`'s CSV export path).
- **Regression risk:** low — purely additive; existing `TimeSeries`
  consumers (tests, CSV readers) are unaffected if the metadata is a
  separate block/file rather than a new required column.
- **Tests:** `tests/test_results.py` (provenance populated correctly,
  CSV sidecar written); a GUI test confirming the header renders.

### Q2. Mission Output search/filter box
- **Rationale:** closes the "logs not searchable" gap noted in §9 for
  the one output panel that already exists; trivial to add.
- **What:** a `QLineEdit` filter above `MissionOutputWidget`'s table,
  filtering visible rows by text (command label, series name, value).
- **Files:** `gui/mission_output_widget.py`.
- **Regression risk:** very low — additive UI, no change to the
  underlying `CommandSummary`/`ReportEntry` data.
- **Tests:** `tests/gui/test_mission_output_widget.py` — filter hides/
  shows rows correctly, clearing restores the full list.

### Q3. Extend plausibility bounds on the highest-risk numeric fields
- **Rationale:** partial, low-cost mitigation of Top Risk #3 (unit/
  magnitude typos) without the full units-library decision in #1 above.
- **What:** audit `schema/scenario.py` for fields with only a sign
  check (`> 0`) where a physically-implausible-but-positive value is a
  likely typo (e.g. `area_m2` > ~1000, `dry_mass_kg` > ~50000,
  `panel_area_m2` > ~100) and add a generous (not falsely-restrictive)
  upper-bound `_require` with a message suggesting the likely unit
  mixup, mirroring the existing `(0, 1]` absorptivity/emissivity style
  added this session.
- **Files:** `schema/scenario.py` only.
- **Regression risk:** low-medium — a bound set too tight could reject
  a legitimate large scenario (e.g. a big constellation bus). Pick
  generous bounds (10-100x realistic) and test against all 20 bundled
  templates to confirm none trip it.
- **Tests:** new cases in `tests/test_scenario_schema.py`; confirm
  `tests/test_scenario_templates.py` still passes unmodified.

---

## Medium (1-3 days each)

### M1. Post-run conservation/drift sanity check (fixes audit Top Risk #2)
- **Rationale:** the only current numerical-health signal is a hard
  crash translation (`engine/service.py:230-256`); this adds a cheap,
  independent check that a *finite but wrong* result doesn't ship
  silently.
- **What:** in `_extract_results()`, for each spacecraft with a
  two-body-dominated orbit (central-body point-mass or low-degree
  gravity, no significant thrust during the window), compute specific
  orbital energy and angular-momentum magnitude from the recorded
  `r_BN_N`/`v_BN_N` series (pure Python/NumPy, no Basilisk changes) and
  check their drift against a configurable relative tolerance (e.g.
  1e-6 relative, loosened automatically when drag/SRP/thrust are
  active). Surface a `ResultSet`-level warning list (not an exception —
  this is a diagnostic, not a new failure mode) shown in the GUI Results
  tab and printed by `cli.py run`.
- **Files:** `engine/results.py` (new `warnings: List[str]` field on
  `ResultSet`), `engine/service.py` (`_extract_results`), `cli.py`
  (`cmd_run`), `gui/results_widget.py` (warning banner).
- **Regression risk:** medium — must not false-positive on every
  perturbed/thrust/drag scenario (most of the 20 templates). Gate the
  check to only fire when it's actually meaningful (two-body or
  near-two-body windows), and default to "informational, never blocks a
  run."
- **Tests:** new `tests/test_conservation_check.py` — a clean two-body
  propagation shows no warning; a synthetic series with injected drift
  does; every bundled template still runs with no *unexpected* warning
  (`requires_basilisk`, run against the real build).

### M2. Vector (SVG) export alongside PNG
- **Rationale:** closes the "publication-quality export" gap (§4) —
  Plotly already supports `toImage({format: 'svg'})`, so this reuses
  the existing save-PNG machinery almost unchanged.
- **What:** add a format argument to `results_widget.py`'s existing
  `_on_save_png`/JS-poll flow (`_SAVE_PNG_*` constants), offer "Save
  plot as PNG/SVG..." with a file-type chooser.
- **Files:** `gui/results_widget.py` only.
- **Regression risk:** low — the existing PNG path is unchanged; SVG is
  an additive branch reusing the same poll/timeout logic.
- **Tests:** extend `tests/gui/test_results_widget.py`'s existing PNG
  -save tests with an SVG-format case.

### M3. Colorblind-safe categorical palette for multi-series plots — **DONE**
- **Rationale:** closes part of §4.
- **Correction while starting this item:** the premise ("currently
  relies on Plotly's default color cycle... isn't verified
  colorblind-safe") was already stale — `gui/results_widget.py`'s fixed
  8-hue `_SERIES_COLORS` was added back in the matplotlib→Plotly
  migration (2026-09-30), predating the audit that flagged it as
  missing (2026-10-05); see `docs/ux_audit.md`'s own "Correction
  (post-audit)" note under §4. What this item actually did: ran the
  `dataviz` skill's `scripts/validate_palette.js` against that EXACT
  palette and this app's real chart surface (`_SURFACE = "#FFFFFF"`)
  for the first time — confirmed PASS on every check in light mode (the
  only mode this app has; no dark theme exists to validate against,
  per §4's "Missing" item, correctly left N/A rather than assumed) —
  and corrected the palette's own comment, which had wrongly claimed an
  unverified "passes in both light and dark mode" (dark in fact FAILS
  the lightness-band check on 4 of 8 hues when actually run).
- **Files:** `gui/results_widget.py` (comment only — the palette and
  its application via `_SERIES_COLORS[i % len(...)]` needed no code
  change), `docs/ux_audit.md`, `docs/ux_roadmap.md` (this entry).
- **Regression risk:** none — doc/comment-only change; the actual
  colors applied to every plot are unchanged.
- **Tests:** deliberately NOT a `node`-dependent test-suite call to the
  validator — this project has no other Node.js dependency anywhere in
  its own test/build pipeline, and adding one for a single
  color-contrast assertion isn't worth a new runtime dependency a real
  install wouldn't otherwise need (ground rule: "no new dependencies
  without justification"). Used the roadmap's own explicitly-offered
  alternative instead: a one-time check, with its exact numbers
  documented in `_SERIES_COLORS`'s own comment (reproducible by anyone
  with Node installed, not just asserted); a plain-Python regression
  test (`tests/gui/test_results_widget.py`) guards the shape that
  matters going forward (8 distinct, valid hex colors) so a future
  accidental edit to the list can't silently shrink or corrupt it
  without the validator being re-run by hand.

### M4. Autosave / crash recovery for scenario edits — **DONE**
- **Rationale:** closes §13's one real gap — today a crash mid-edit
  loses unsaved work; only a clean close prompts to save.
- **What was built:** a new, Qt-free `gui/autosave.py` (`write_recovery_file`/
  `clear_recovery_file`/`read_recovery_file`, a single fixed recovery
  slot under `~/.spacemissionstudio/autosave/recovery.json`, matching
  `logging_setup.py`'s own per-user directory convention) plus a
  `QTimer` in `gui/main_window.py` that calls
  `write_recovery_file(scenario, self._current_path)` every 30s
  (`_AUTOSAVE_INTERVAL_MS`) while the editor is dirty AND the in-memory
  scenario currently validates (an incomplete mid-edit is skipped that
  tick, tried again next tick, same tolerance a real Save already
  has). `_mark_clean()` — the one chokepoint every Save/New/Open/
  discard already funnels through — calls `clear_recovery_file()`, so
  a recovery file only ever exists while there's genuinely something
  unsaved to recover. On the NEXT launch, `_check_autosave_recovery()`
  (fired via `QTimer.singleShot(0, ...)`, same pattern as the existing
  startup kernel-fetch prompt) offers to restore it; accepting loads it
  into the editor and marks the window DIRTY (not clean — the
  recovered content is exactly the unsaved state from before the
  crash, so it still needs an explicit Save); declining clears the
  recovery file immediately rather than prompting again next launch.
- **Files:** `gui/autosave.py` (new), `gui/main_window.py` (timer,
  `_on_autosave_tick`, `_check_autosave_recovery`, a new
  `check_autosave_recovery` constructor flag mirroring the existing
  `prompt_startup_fetch` one), `tests/test_autosave.py` (new),
  `tests/gui/test_main_window.py`.
- **Regression risk:** low in practice — every one of the ~90
  pre-existing `MainWindow` tests passed completely unmodified (only
  the one `window` fixture needed `check_autosave_recovery=False`
  added alongside its existing `prompt_startup_fetch=False`, the same
  opt-out convention already established); the autosave timer runs
  unconditionally but no-ops whenever the editor isn't dirty.
- **Tests:** `tests/test_autosave.py` (11 tests, Qt-free, isolated to a
  `tmp_path` recovery location — round-trip, missing/corrupt/malformed
  files, a write/clear failure being swallowed not raised) plus 8 new
  `tests/gui/test_main_window.py` tests (tick writes while dirty/no-ops
  while clean/skips silently on a transiently-invalid scenario; Save
  and discard-via-New each clear the recovery file; the startup check
  with no file present is a no-op; accepting restores into the editor
  and marks it dirty with the original path preserved; declining clears
  the file and leaves the editor untouched) — all isolated to a
  `tmp_path`-backed recovery location via a new autouse fixture, never
  touching a real home directory from the test suite.

### M5. Lightweight ground-station access timeline
- **Rationale:** a scoped, cheap step toward §3's Gantt gap without
  building a general-purpose linked-timeline framework (that's
  Strategic, below) — most of the value of "see access windows at a
  glance" comes from one more chart, not a new interaction model.
- **What:** a new, small results view that renders
  `{gs}.access_to_{sc}.has_access` as a horizontal bar/step plot per
  ground-station/spacecraft pair (still Plotly, still inside the
  existing results panel — a "view" choice alongside the current
  per-series dropdown, not a new widget framework). Clicking a bar could
  set the x-axis range on the main plot (a small, scoped version of
  "click-to-jump," not full view-linking).
- **Files:** `gui/results_widget.py` (new view mode).
- **Regression risk:** low-medium — purely additive view; must not
  change the existing single-series view's behavior.
- **Tests:** extend `tests/gui/test_results_widget.py` with the new view
  mode against a synthetic `ResultSet` containing access series.

---

## Strategic (bigger scope, or gated on a decision above)

### S1. Full unit-type enforcement (gated on Decision 1)
`pint` (or hand-rolled dimensional wrapper) across `schema/scenario.py`
and every `engine/` consumer. Large surface, new dependency, real
regression risk to hundreds of call sites. Only pursue if a real unit
-confusion incident occurs, or if you want it regardless of near-term
payoff — tell me and I'll scope it properly rather than estimate blind.

### S2. Template-driven HTML report (gated on Decision 2)
A `jinja2` template rendering a run's key series/plots/provenance
(once Q1 lands) to a standalone HTML file — "regenerate from inputs,"
not a static export. Needs its own design pass (what goes in a report,
which plots, how much is configurable) before estimating file-by-file.

### S3. Expert-efficiency suite: command palette, global search, macros, undo/redo
Each of these is its own multi-day feature (a `QUndoStack`-based edit
history touches every editor dialog in `gui/`; a command palette needs
a registry of every action in `main_window.py` plus every dialog's
actions; global search needs an index over scenario objects). Recommend
picking ONE to start with if this is a priority — my suggestion would
be **undo/redo** first (highest safety value: recovering from a bad
edit), **command palette** second (highest discoverability value).

### S4. Native parameter sweep / trade-study runner
A grid/sweep executor over `Scenario` fields (distinct from Monte
Carlo's random dispersions), plus run snapshot/diff to compare sweep
points. Builds on `engine/monte_carlo.py`'s existing batch-execution
pattern but needs its own sweep-specification schema and a comparison
UI — a real multi-day design, not a small addition.

### S5. Interoperability: CCSDS OEM export
Of the formats in §10, OEM (state-vector time history) is the most
standard and highest-reuse (readable by GMAT, STK, and most other
tools) — recommend starting here alone if/when this becomes a
priority, rather than all of OEM/OPM/AEM/HDF5/MATLAB at once.

### S6. Targeting/optimization (gated on Decision 4) — not recommended now
See Decision 4 above.

### S7. Plugin architecture (gated on Decision 3) — not recommended now
See Decision 3 above.

---

## Suggested order if you approve broadly

Q1 → M1 → Q3 → Q2 → M2/M3 (can run in parallel, both touch
`results_widget.py` but in different functions) → M4 → M5. Everything
under Strategic waits for an explicit decision per item above.
