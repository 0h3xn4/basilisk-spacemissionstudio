# Whole-tool review log

Findings of the whole-tool review that followed the human actions
(`PROGRESS.md`). Numbering continues the findings of `phase3_log.md`.

## Findings

| # | Finding | Effect | Action |
|---|---|---|---|
| F-09 | `engine/spaceweather.py` wrote the resolved space-weather file in place after an `exists()` check. Parallel processes resolving the same window (altitude trade workers, Monte Carlo runs) could read another's half-written file; a write that died left a short file in the cache for good. Found by the Windows CI job (400 km altitude trade: 1.45 kg against 7.26 kg on Linux); reproduced on Linux (2 of 5 trials of 8 processes read a short file, down to 512 of 3674 lines). | Wrong solar activity, so wrong drag, lifetimes and budgets, in parallel runs, without an error (Basilisk only warns "Failed to retrieve a state") | Fixed: temporary file and `os.replace`; a cached file with the wrong line count is rewritten. 0 of 5 trials after the fix. Tests in `tests/test_spaceweather.py`. Parallel results computed before the fix are to be re-run (SRelD K-11; dependability analysis FM-04). |

| F-10 | `propagate` with `stop_condition: event` (periapsis, apoapsis) started on that apsis: the radial velocity there is zero up to rounding (+2.3e-13 m/s on Linux for the test orbit). When the rounding made it negative, as on Windows, the first steps already "crossed" the apsis and the run stopped after one step instead of one orbit. Found by the Windows CI job (`test_should_cancel_checked_mid_propagate_event_command`: did not raise); reproduced on Linux by starting 1e-9 deg before the apsis (1.0 s instead of 5829 s). | The same scenario gave a different mission timeline per platform | Fixed in `engine/mission_engine.py`: a first sample within 1e-6 m/s of zero counts as on the apsis, which then does not count. Test: `test_propagate_to_an_apsis_from_that_apsis_flies_a_whole_orbit` (six start points, both apsides). |
| F-11 | Template wizard cards could not shrink: hint labels never wrapped and form rows never wrapped, so wider fonts (the Windows CI measured cards about 1.5 times as wide; also high DPI and large-font settings) forced sideways scrolling. | Usability on Windows and with large fonts | Fixed in `gui/template_wizard.py`: hints wrap and long rows put the field under its label, only when the row does not fit. Unchanged at the normal font size. Test: `test_wizard_fits_without_sideways_scrolling_with_large_fonts` (1.5 times the font). |

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

## Checked, not a defect

- The one-day reference run warned that NOAA's monthly F10.7 forecast is
  used before MSFC's prediction starts. That is the designed order (real
  data only), covered by
  `tests/test_spaceweather.py::test_noaa_fills_only_the_months_before_msfc_starts`.
