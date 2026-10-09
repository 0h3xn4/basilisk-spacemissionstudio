# UX/UI guidelines: where the tool stands (2026-10-09)

Each guideline of "UX/UI Guidelines for SpaceMissionStudio" (2026-10-08)
against the tool as it is on branch `compliance/ecss-ccsds-audit`. It
builds on `ux_audit.md` and `ux_roadmap.md`: of the roadmap, Q1-Q3,
M1-M5 and S5 (CCSDS OEM) are done; S1 (unit typing), S2 (HTML report),
S3 (command palette, undo) and S4 (generic trade runner) are not.

Status: **met**, **partly**, **not met**. Effort: S (under a day),
M (1-3 days), L (more).

## Offline and closed operation

| Guideline | Status | Evidence | Proposed work | Effort |
|---|---|---|---|---|
| No background network use | Met (2026-10-09) | `tests/test_offline.py` blocks every lookup and connection through validate, export, a run with its exports and GUI start-up; CI repeats it with no network interface. It found Basilisk's import-time request to github.com (contained, review_log F-16) and downloads of missing support data during runs (removed, F-17) | - | - |
| Downloads only with consent, naming source, files and size; integrity; show changes; rollback | Met (2026-10-09) | Every download starts from the Data tab or the startup prompt, after naming source, files and size (default No). Support data: Basilisk's registry checksums where it has them; space weather: parsed before it replaces anything, SHA-256 recorded, previous file kept; Earth orientation: SHA-256 manifest, previous files kept. The Data tab says what changed and offers Roll back. Vizard's download (an executable) has no published checksum (security analysis S-05) | Vizard download through the same prompt | S |
| Reference data by download or file import; version, date and source shown | Met (2026-10-09) | The Data tab lists every file with source, dates covered, SHA-256 and install time, flags missing and out-of-date files, imports space-weather and Earth orientation files and rolls them back | - | - |
| Everything bundled (fonts, icons, scripts, docs) | Partly | Icons, plotly.js, templates and data are bundled; fonts are the system's (no IBM Plex); the user manual is not reachable from the app | Bundle IBM Plex (SIL OFL) if Carbon is adopted; open the bundled manual from Help | S |
| Vizard local only, streaming bound to the local machine | Partly | The tool connects only to `tcp://localhost:5556`; it opens no port. Which interface Vizard itself listens on is not known (SRelD K-05) | Check Vizard's listener on each platform and document it; nothing in the tool to change | S |
| Help and examples built in | Met (2026-10-09) | 21 templates, tooltips, the Explain tab; Help > User Manual (F1) shows the bundled manual offline, Help > Keyboard Shortcuts | Template catalogue in Help (optional) | S |
| No AI features; deterministic, traceable warnings | Met | No AI features; warnings come from fixed rules (`scenario_checks.py`, schema validation) | Name the rule in each warning's tooltip | S |

## Foundation

| Guideline | Status | Evidence | Proposed work | Effort |
|---|---|---|---|---|
| IBM Carbon design system | Not met | Own theme (`gui/theme.py`, `PALETTE`), Fusion style | Carbon tokens (colour, type scale, spacing) in `theme.py`, Carbon-style tables, notifications and form fields as Qt styles; IBM Plex bundled. Qt cannot use Carbon's web components, so this is Carbon's look and rules, rebuilt in Qt | L |
| Undo and a command palette | Not met | No undo stack; no palette (roadmap S3) | `QUndoStack` over scenario edits (each dialog OK is one command); Ctrl+K palette over menu actions, templates, spacecraft and series | M (palette), L (undo) |
| Provenance on every output | Met (2026-10-09) | Runs record tool, Basilisk and dependency versions, the scenario's SHA-256, integrator, step, seeds and every reference data file with its SHA-256 (`RunProvenance`). Written into: CSV export (`provenance.json`), PNG (text chunk) and SVG (`<metadata>`) plots, OEM header `COMMENT`s, OPM/OMM exports, the Mission Output CSV and Monte Carlo archives (`.provenance.json` beside them), the budget copy | The input file's path is not recorded (its hash is) | S |
| Error messages pointing to the field, saying how to fix | Partly | Validation messages name the path (`spacecraft[0].orbit...`); dialogs mark the field red (`feedback.mark_invalid`); messages do not always say how to fix it | Map each validation path to its widget so the error focuses it; add the fix to every message | M |
| Templates as empty states | Met | The start page lists the templates (`load_scenario_widget.py`) | - | - |

## Mission analysis features

| Guideline | Status | Evidence | Proposed work | Effort |
|---|---|---|---|---|
| One shared time cursor across views | Met (2026-10-09) | One `TimeCursor` in the main window (`gui/time_cursor.py`). The Results plots and the access timeline draw it and set it by a click; the Events timeline draws it and sets it by click or drag; the Mission Dashboard shows the values at the cursor; Mission Output marks the last report before it and sets it from a report header; the status bar shows its time (`tests/gui/test_results_cursor.py`, `test_event_timeline_widget.py`, and the dashboard and output tests) | Vizard cannot follow it (row below) | - |
| Tight Vizard integration, jump Vizard to a time | Partly | Live streaming and save files work; the tool starts Vizard with the right file or address (`vizard_launcher.py`). Vizard's documented interface (`-loadFile`, `-directComm`, `vizardCommandLine.rst`) has no way for another program to set its playback time | Within what Vizard allows: start playback of the last run's file from the Results tab. A time link needs a Vizard interface that does not exist (to raise with the Vizard developers) | S (open file) |
| Frame, epoch and time scale beside every input | Met (2026-10-09) | Orbit pages show their frame row; vector inputs name their frame in the visible label (body frame B, EME2000, WGS-84); the epoch field says UTC (`tests/gui/test_frame_tags.py`) | - | - |
| Non-blocking propagation, partial results, cancel, cached results | Met | Runs in a worker thread with progress, live partial plots and Abort; changing a plot does not rerun | - | - |
| Events as a timeline with a sortable, exportable table | Met (2026-10-09) | One event model (`engine/events.py`): passes, eclipses (every spacecraft's illumination is now recorded when the Sun is tracked), station-keeping, GEO and phasing burns with their delta-V, thruster firings, comms and phasing mode changes. The Events tab draws them as a Gantt timeline over a sortable table with kind filters and CSV export (with provenance); `spacemissionstudio run` writes the same `events.csv` | Events are only those a run records; an event still going at the end of the run ends there | - |
| Run comparison | Not met | The launch-delay sweep and altitude trade compare budgets, not runs | Keep finished runs in the session; overlay a series from several runs; a diff of their inputs | M-L |
| Plausibility checks while typing | Met (2026-10-09) | The scenario editor shows, under its validation line: perigee below the surface or below 120 km, a Cartesian state inside Earth or escaping, a drag run outside the space-weather data, missing or out-of-span Earth orientation files (`scenario_checks.plausibility_warnings`) | More rules as they are found | S |
| Model transparency panel | Partly | Data files: the Data tab (source, dates, checksum, out-of-date warning). Active models: the Explain tab (gravity degree, third bodies, drag, SRP); runs name the space-weather data in their warnings | Active models with their parameters beside the files, in one place | S |
| Scenario as text and GUI | Met | Scenarios are JSON files the GUI and the CLI both read and write | - | - |

## Decisions needed

1. **Carbon:** restyle the whole GUI to Carbon's tokens and components
   (rebuilt in Qt, IBM Plex bundled), or keep the current theme and take
   only Carbon's rules (spacing, type scale, notification patterns)?
2. **Order:** proposed first are the items that are small and close
   firm guidelines: the offline test, the plausibility checks, the
   frame-label fix, Help with the manual, and provenance on every output.
   Then the data panel with consented, checked downloads; then the event
   timeline and the shared time cursor; then run comparison, undo and the
   command palette.
3. **Vizard time link:** accept that Vizard cannot be driven to a time
   (only opened on a run's file), or raise it with the Vizard developers?

## Decisions (2026-10-09, the owner)

1. **Carbon:** full restyle. Carbon's colour, type and spacing tokens
   across the GUI, Carbon-style tables, notifications and form fields,
   rebuilt in Qt; IBM Plex bundled (SIL Open Font Licence).
2. **Order:** small and firm first: (1) the offline test, plausibility
   checks while typing, frame tags, Help with the manual, provenance on
   every output; (2) the data panel with consented, checked downloads;
   (3) the event timeline and the shared time cursor; (4) run comparison,
   undo, the command palette. The Carbon restyle runs alongside.
3. **Vizard time link:** not possible with Vizard's interface. The
   Results tab opens Vizard on the last run's file; the missing time
   interface is added to the upstream reports (H10).
