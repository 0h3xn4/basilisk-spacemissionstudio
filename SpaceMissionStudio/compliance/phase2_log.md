# Phase 2 implementation log

One row per remediation item of `gap_analysis.md` section 9, in the order
done. "Suite" is the full test suite on the commit (baseline: 2055 passed,
11 skipped, 0 failed; new tests add to "passed").

| Item | Requirements | Change | Verification | Suite |
|---|---|---|---|---|
| R05 | E-ST-10-09C 5.4.6a | `engine/geodesy.py` (WGS-84; sphere for other bodies); `fsw.build_ground_location` uses `specifyLocationPCPF`; recorded elevation/azimuth converted to geodetic; pass prediction uses the WGS-84 site and normal; GUI/schema labels | `tests/test_geodesy.py` (published WGS-84 constants, round trip, independent elevation/azimuth, Basilisk site); template 19 full Basilisk run: passes 10.4-18.2 min (61.6 deg) and 106.8-111.8 min (16.1 deg) | 2068 passed, 11 skipped, 0 failed |

## Result differences against the baseline

* R05: ground-station geometry changes by design. Template 19's predicted
  second pass now lasts 5 min instead of 4 min and its first-pass peak
  rounds to 60 deg instead of 61 deg; three test expectations
  (`test_scenario_checks`, `test_scenario_explainer`, `test_record_interval`)
  were updated to the new values, which the full Basilisk run confirms.
  Basilisk's own `has_access` flag keeps its geocentric horizon (about 2 s
  difference at the 10 deg boundary in that run).
