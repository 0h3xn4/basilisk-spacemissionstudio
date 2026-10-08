# Whole-tool review log

Findings of the whole-tool review that followed the human actions
(`PROGRESS.md`). Numbering continues the findings of `phase3_log.md`.

## Findings

| # | Finding | Effect | Action |
|---|---|---|---|
| F-09 | `engine/spaceweather.py` wrote the resolved space-weather file in place after an `exists()` check. Parallel processes resolving the same window (altitude trade workers, Monte Carlo runs) could read another's half-written file; a write that died left a short file in the cache for good. Found by the Windows CI job (400 km altitude trade: 1.45 kg against 7.26 kg on Linux); reproduced on Linux (2 of 5 trials of 8 processes read a short file, down to 512 of 3674 lines). | Wrong solar activity, so wrong drag, lifetimes and budgets, in parallel runs, without an error (Basilisk only warns "Failed to retrieve a state") | Fixed: temporary file and `os.replace`; a cached file with the wrong line count is rewritten. 0 of 5 trials after the fix. Tests in `tests/test_spaceweather.py`. Parallel results computed before the fix are to be re-run (SRelD K-11; dependability analysis FM-04). |

## Checked, not a defect

- The one-day reference run warned that NOAA's monthly F10.7 forecast is
  used before MSFC's prediction starts. That is the designed order (real
  data only), covered by
  `tests/test_spaceweather.py::test_noaa_fills_only_the_months_before_msfc_starts`.
