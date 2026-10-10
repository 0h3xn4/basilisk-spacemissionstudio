# Whole-tool review log

Findings of the whole-tool review that followed the human actions
(`PROGRESS.md`). Numbering continues the findings of `phase3_log.md`.

## Findings

| # | Finding | Effect | Action |
|---|---|---|---|
| F-09 | `engine/spaceweather.py` wrote the resolved space-weather file in place after an `exists()` check. Parallel processes resolving the same window (altitude trade workers, Monte Carlo runs) could read another's half-written file; a write that died left a short file in the cache for good. Found by the Windows CI job (400 km altitude trade: 1.45 kg against 7.26 kg on Linux); reproduced on Linux (2 of 5 trials of 8 processes read a short file, down to 512 of 3674 lines). | Wrong solar activity, so wrong drag, lifetimes and budgets, in parallel runs, without an error (Basilisk only warns "Failed to retrieve a state") | Fixed: temporary file and `os.replace`; a cached file with the wrong line count is rewritten. 0 of 5 trials after the fix. Tests in `tests/test_spaceweather.py`. Parallel results computed before the fix are to be re-run (SRelD K-11; dependability analysis FM-04). |
| F-10 | `propagate` with `stop_condition: event` (periapsis, apoapsis) started on that apsis: the radial velocity there is zero up to rounding (+2.3e-13 m/s on Linux for the test orbit). When the rounding made it negative, as on Windows, the first steps already "crossed" the apsis and the run stopped after one step instead of one orbit. Found by the Windows CI job (`test_should_cancel_checked_mid_propagate_event_command`: did not raise); reproduced on Linux by starting 1e-9 deg before the apsis (1.0 s instead of 5829 s). | The same scenario gave a different mission timeline per platform | Fixed in `engine/mission_engine.py`: a first sample within 1e-6 m/s of zero counts as on the apsis, which then does not count. Test: `test_propagate_to_an_apsis_from_that_apsis_flies_a_whole_orbit` (six start points, both apsides). |
| F-11 | Template wizard cards could not shrink: hint labels never wrapped and form rows never wrapped, so wider fonts (the Windows CI measured cards about 1.5 times as wide; also high DPI and large-font settings) forced sideways scrolling. | Usability on Windows and with large fonts | Fixed in `gui/template_wizard.py`: hints wrap and long rows put the field under its label, only when the row does not fit. Unchanged at the normal font size. Test: `test_wizard_fits_without_sideways_scrolling_with_large_fonts` (1.5 times the font). |
| F-12 | The plot export (PNG, SVG) polled the page every 100 ms with asynchronous `runJavaScript()` queries without waiting for the answers. A tick after the poll had finished read the cleared state (the `'NoneType' object is not subscriptable` tracebacks of SRelD K-08), and with several queries in flight each answer could finish the save again (a second file write and dialog). | Spurious tracebacks; possible duplicate saves on slow machines | Fixed in `gui/results_widget.py`: one query at a time, ticks without a poll and answers to a finished poll ignored. Tests: `test_a_poll_tick_after_the_poll_finished_is_ignored`, `test_only_one_poll_query_is_in_flight_and_late_answers_are_ignored` (both fail without the fix). K-08 closed. |
| F-13 | Unreachable code (ECSS-Q-ST-80C 3.2.34: "code that cannot be executed due to design or coding error"), found by the unexecuted-code analysis (`unreached_code.md`): six functions nothing calls (`Ellipsoid.describe`, `SpaceWeatherData.kinds_between`, `BudgetWidget.compute_sweep` and `compute_trade`, `sensor_actuator_editor._template_params`, the template wizard's `content_size_hint`; found with vulture 2.16 and a search for every caller, signal hookup and dynamic lookup), and an `except MissionEngineError: raise` clause in `MissionEngine._evaluate_condition` that nothing in its `try` body can trigger (a leftover of the `eval()` era) | None at run time; dead code to maintain and review | Removed (6.2.3.6a). Re-verification: the full suite after the six removals (2259 passed, 11 skipped) and the mission-engine and condition tests after the handler (66 passed). No re-validation needed: no reachable path changed. |
| F-14 | Constant-frame thrust (`constant_thrust`) is reachable from the GUI and the schema, but no test ran it in a simulation: no template uses it and the unit tests stopped at the schema | A user-visible feature without verification | Test added: `tests/test_constant_thrust_run.py` (prograde thrust against the rocket equation, 0.1 %, and Gauss's equation for the semi-major axis, 2 %; orbit-normal thrust turns the plane and leaves the semi-major axis alone). Both pass. |
| F-15 | The suite's coverage measurement is blind to code Basilisk runs: Basilisk calls the tool's Python `SysModel` callbacks (`UpdateState`, `Reset`, and what they call) from its own native thread, which coverage's default tracer does not see. Confirmed: in a 0.02-day run the planet-orientation and geodetic-atmosphere callbacks ran 177 and 58 times off Python's main thread, while coverage reported them as never executed. Python 3.12's `sys.monitoring` (`COVERAGE_CORE=sysmon`) sees them | The qualified (Python 3.11) coverage figures understate what runs: 1586 statements unexecuted on 3.11 against 1065 on 3.12 with sysmon (93.3 % statement coverage); every function is entered on 3.12. The 90 % and 80 % gates are met on 3.11 even so. Branch coverage on 3.12 is not available (sysmon measures branches from Python 3.14) | The unexecuted-code analysis uses the 3.12 sysmon measurement (`tools/unreached_code.py` docstring). The CI gates stay on the qualified 3.11 measurement, which errs low. |
| F-16 | Every simulation contacted github.com. Basilisk 2.12.0's `dataFetcher` sends `requests.head("https://github.com/AVSLab/basilisk/releases/tag/<version>", timeout=1)` when imported, and every run imports it (through `simIncludeGravBody` and the tool's `engine/kernels.py`). Found by the offline test of the UX/UI guidelines: in a full `spacemissionstudio run` with every socket call recorded, the one attempt was a lookup of `github.com:443` from that import; the tool's own code made none | Breaks SRS-S-01 ("no network access unless the user starts it") and the guideline "no background network use"; reveals to GitHub that the tool runs. Runs still worked offline: the request fails within its 1 s timeout | Contained without changing Basilisk (decision of 2026-10-09): `spacemissionstudio/_offline.py` adds an import hook that, while that one module is first executed, points the HTTP(S) proxy settings at a closed local port and clears `NO_PROXY`; the request fails on this computer, with no name lookup; the user's settings are restored. Tests: `tests/test_offline.py` (a fresh interpreter importing Basilisk through the tool makes no lookup or connection to another computer; the settings are restored). CI runs the offline tests in a network namespace with no interfaces. To be reported upstream (H10). |
| F-17 | A run with a support-data file missing from Basilisk's cache downloaded it: `kernels.build_spice_interface`, the gravity field and the magnetic-field model called Basilisk's `get_path`, which fetches what is not cached, with the user's network settings and without asking. Only the installers and the explicit fetch actions were meant to download | Breaks SRS-S-01 when the cache is incomplete (a deleted or partial cache, a new data file) | Fixed: runs use `kernels.cached_path`/`require_cached`, which only read the cache, check the registry checksum where Basilisk gives one, and otherwise stop with a `KernelError` saying where to fetch the file. Downloads stay in the startup prompt (after consent), the Kernel Status tab, `spacemissionstudio kernels-status` and the installers. Tests: a run with an empty cache stops with that error and no network attempt; a cached file with a wrong checksum is refused. |
| F-18 | The unexecuted-code analysis of 2026-10-09 (F-13 to F-15) no longer described the code: about 6600 statements were added since (15947 then, 22587 now), and it still listed `gui/kernel_status_widget.py`, removed since. Re-measured on 2026-10-10 (commit 660912587, Python 3.12 with `sys.monitoring`, 2717 passed, 10 skipped): 1462 of 22587 statements are not executed (93.5 % statement coverage) and every function is entered. Reviewed: the 189 handler and guard statements in code added since 2026-10-09 (93 handlers, 96 guards), and a dead-code search (vulture 2.16, confidence 60; every reported function and method searched for callers in the package, tests, scripts, examples and installers) | None at run time; the analysis was out of date | No unreachable code found (Q-ST-80C 3.2.34). The handlers are file, operating-system, socket and external-program errors (SIL, export, data files) that a user or the program can cause. The guards are checks on files, SIL frames and user input, display cases for series no test plots, and defensive checks behind validation or Basilisk's run order (for example `mean_oe` without J2, which the schema already refuses, and the flight-software capture's run-order checks). Every function vulture reports is called (by the installers, tests or examples); every variable it reports is a dataclass field. Not reviewed in this refresh: the 919 `branch` statements (conditions the tests do not set up). Report: `unreached_code.md`, which now records when and on what it was measured. |

## Test defects found by the platform jobs (not tool defects)

- `test_download_url_for_platform_covers_all_three` "restored" `sys.platform`
  from itself and left it at "linux" for the rest of the worker process;
  on macOS that broke `sysconfig` in an unrelated test (`test_ccsds_odm`).
- The Vizard download tests built a Linux archive but the code looked for
  the executable name of the real platform; the exec-bit test read a POSIX
  bit on Windows.
- `test_path_cell_carries_the_full_path_as_a_tooltip` expected `/` on Windows.
- Three width tests had pixel limits measured at the Linux CI's font; they
  are now in average character widths (the same limits on Linux).
- `test_an_accepted_download_runs_and_reports_what_changed` (the Data tab,
  UX step 2) waited for `QThread.finished` after starting a worker whose
  stub task ends at once, so the signal could come first (CI run 51,
  Linux). It now waits for the buttons the result slot enables again.
- Observed, not a tool defect: run on their own in this sandbox, the test
  files that open a Results plot (`QWebEngineView`) end in a segmentation
  fault after every test has passed, while Qt WebEngine shuts down
  ("Release of profile requested but WebEnginePage still not deleted").
  It happens on `5c2805085` too, before the event, cursor and comparison
  work, and not in the parallel suite runs that CI uses.
- macOS: the plot tests ran Qt WebEngine on the offscreen plugin, which does
  not work there (page loads never finished, a worker crashed); the macOS
  job now uses Qt's cocoa plugin.
- CI run 23: the first plot page sometimes took over 10 s to load on the
  Windows and macOS runners (four test workers), each time in a different
  test; the page-load wait is now 30 s. The wizard test allowed for its
  1100 px cap but not for a narrower screen (the macOS runner's is 1024 px).
  The one-line hint check measured the label, whose height is pinned to the
  spin box beside it, instead of the text.
- F-09's fix on Windows (CI run 26): `os.replace` is refused while another
  process has the target open. That process wrote the same window, so a
  complete file there is now kept and the new copy dropped; an incomplete
  one is retried, then reported. Tests:
  `test_a_refused_replace_keeps_the_complete_file_another_process_wrote`,
  `test_a_refused_replace_of_an_incomplete_file_is_reported`.
- The hint check now states the rule exactly: one line wherever the text
  fits, wrapping (at most two lines) only where it does not (Windows CI).
- CI run 27 (macOS, push run; the pull-request run of the same commit was
  green): in one test worker two plot pages never finished loading, even
  with 30 s. The plot tests had never shown the widget; hidden, its web
  view can stall on Qt's cocoa platform (the likely cause, not proven).
  The results-widget test fixture now shows the widget and waits until it
  is exposed, as it is in the app.
- Reviewing F-12's one-query-at-a-time rule: an answer that never arrived
  would have stalled the save; the poll now asks again after a second.

## Checked, not a defect

- The one-day reference run warned that NOAA's monthly F10.7 forecast is
  used before MSFC's prediction starts. That is the designed order (real
  data only), covered by
  `tests/test_spaceweather.py::test_noaa_fills_only_the_months_before_msfc_starts`.
- Python 3.12 deprecates `datetime.utcnow()`, used in
  `engine/ccsds_odm.py` (the OEM creation date) and
  `gui/startup_fetch_dialog.py`. Warnings only, and the tool is qualified
  on Python 3.11; to be replaced with `datetime.now(timezone.utc)` before
  a Python version that removes it is qualified.
