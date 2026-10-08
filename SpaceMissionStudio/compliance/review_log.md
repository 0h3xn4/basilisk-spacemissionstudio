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
