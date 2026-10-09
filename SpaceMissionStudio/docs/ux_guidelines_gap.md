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
| No background network use | Partly | No telemetry, update or licence checks; plotly.js is loaded from the installed package (`results_widget.py`, local file URL); every download is behind a button or the startup prompt. No automated test runs with the network disabled | Add a test that blocks every socket (and a CI job under `unshare -n` on Linux) and runs start-up, a template run and every export | S |
| Downloads only with consent, naming source, files and size; integrity; show changes; rollback | Partly | Earth orientation: consent, size (~36 MB), SHA-256 manifest, `previous/` rollback (`engine/earth_orientation.py`). Space weather (`spaceweather.fetch`) and Vizard (`fetch_vizard`): no checksum, no kept previous version, no change summary; the prompt names sizes only for Earth orientation | One download module for all three: source, files and size in the prompt; checksum (published where the source has one, else recorded); keep the previous version; a short "what changed" (dates covered, versions) | M |
| Reference data by download or file import; version, date and source shown | Partly | Earth orientation: download, import, rollback (CLI `earth-orientation`); space weather: a local file can be chosen. Leap seconds come from the bundled SPICE LSK; gravity coefficients from Basilisk. The Kernel Status tab lists SPICE kernels, not the space-weather or MSFC files | A "Data" panel listing every reference file in use: name, version, dates covered, source, SHA-256, installed date, with import and rollback | M |
| Everything bundled (fonts, icons, scripts, docs) | Partly | Icons, plotly.js, templates and data are bundled; fonts are the system's (no IBM Plex); the user manual is not reachable from the app | Bundle IBM Plex (SIL OFL) if Carbon is adopted; open the bundled manual from Help | S |
| Vizard local only, streaming bound to the local machine | Partly | The tool connects only to `tcp://localhost:5556`; it opens no port. Which interface Vizard itself listens on is not known (SRelD K-05) | Check Vizard's listener on each platform and document it; nothing in the tool to change | S |
| Help and examples built in | Partly | 21 templates, tooltips, the Explain tab; Help has only "About" | Help menu: user manual (bundled HTML or Markdown viewer), keyboard shortcuts, template catalogue | S |
| No AI features; deterministic, traceable warnings | Met | No AI features; warnings come from fixed rules (`scenario_checks.py`, schema validation) | Name the rule in each warning's tooltip | S |

## Foundation

| Guideline | Status | Evidence | Proposed work | Effort |
|---|---|---|---|---|
| IBM Carbon design system | Not met | Own theme (`gui/theme.py`, `PALETTE`), Fusion style | Carbon tokens (colour, type scale, spacing) in `theme.py`, Carbon-style tables, notifications and form fields as Qt styles; IBM Plex bundled. Qt cannot use Carbon's web components, so this is Carbon's look and rules, rebuilt in Qt | L |
| Undo and a command palette | Not met | No undo stack; no palette (roadmap S3) | `QUndoStack` over scenario edits (each dialog OK is one command); Ctrl+K palette over menu actions, templates, spacecraft and series | M (palette), L (undo) |
| Provenance on every output | Partly | Results carry tool and Basilisk versions, integrator, step, seeds (`RunProvenance`, `provenance.json` beside CSV exports, a line under the plot). Not recorded: input file and its hash, the settings, the reference data files used. Not on PNG/SVG plots, OEM/OPM exports (beyond the creator line), budgets, lifetimes or Monte Carlo archives | Extend `RunProvenance` with the input file hash, the full settings and the data files (name, version, SHA-256); write it into every export (CSV header, OEM `COMMENT`s, plot caption and metadata, budget and lifetime reports) | M |
| Error messages pointing to the field, saying how to fix | Partly | Validation messages name the path (`spacecraft[0].orbit...`); dialogs mark the field red (`feedback.mark_invalid`); messages do not always say how to fix it | Map each validation path to its widget so the error focuses it; add the fix to every message | M |
| Templates as empty states | Met | The start page lists the templates (`load_scenario_widget.py`) | - | - |

## Mission analysis features

| Guideline | Status | Evidence | Proposed work | Effort |
|---|---|---|---|---|
| One shared time cursor across views | Not met | Plots, the dashboard and the access timeline each have their own time axis | A time-cursor model in the main window; the plots, access timeline, dashboard and output tables follow it and set it by click or drag | L |
| Tight Vizard integration, jump Vizard to a time | Partly | Live streaming and save files work; the tool starts Vizard with the right file or address (`vizard_launcher.py`). Vizard's documented interface (`-loadFile`, `-directComm`, `vizardCommandLine.rst`) has no way for another program to set its playback time | Within what Vizard allows: start playback of the last run's file from the Results tab. A time link needs a Vizard interface that does not exist (to raise with the Vizard developers) | S (open file) |
| Frame, epoch and time scale beside every input | Partly | Orbit inputs show "EME2000 (SPICE J2000) ... (UTC)" and the TLE path "TEME (SGP4) -> EME2000"; the epoch field says UTC. Ground stations give WGS-84 only in tooltips; the Cartesian position tooltip says "J2000-ish"; other vector inputs (target vectors, thrust frames) state their frame only in tooltips | Correct the "J2000-ish" tooltip; a visible frame tag on every position and vector input | S |
| Non-blocking propagation, partial results, cancel, cached results | Met | Runs in a worker thread with progress, live partial plots and Abort; changing a plot does not rerun | - | - |
| Events as a timeline with a sortable, exportable table | Partly | Ground-station access timeline (roadmap M5); eclipses and manoeuvres are not on it; no event table | One event model (passes, eclipses, burns, mode changes) as a Gantt timeline over a sortable table with CSV export | M |
| Run comparison | Not met | The launch-delay sweep and altitude trade compare budgets, not runs | Keep finished runs in the session; overlay a series from several runs; a diff of their inputs | M-L |
| Plausibility checks while typing | Partly | Bounds on risky numeric fields; warnings for TLE age, gravity truncation, recording interval, passes (`scenario_checks.py`); a run outside the space-weather data is refused at run time | Add perigee below the surface, inconsistent element sets, and epoch outside the installed Earth orientation and space-weather data, shown while editing | S |
| Model transparency panel | Partly | The Explain tab lists gravity degree, third bodies, drag and SRP; Kernel Status lists SPICE kernels; runs report the space-weather data used in their warnings | One models-and-data panel: active models with their parameters, and every data file with version, dates and source, warning when out of date | M |
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
