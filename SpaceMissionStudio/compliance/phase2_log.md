# Phase 2 implementation log

One row per remediation item of `gap_analysis.md` section 9, in the order
done. "Suite" is the full test suite on the commit (baseline: 2055 passed,
11 skipped, 0 failed; new tests add to "passed").

| Item | Requirements | Change | Verification | Suite |
|---|---|---|---|---|
| R05 | E-ST-10-09C 5.4.6a | `engine/geodesy.py` (WGS-84; sphere for other bodies); `fsw.build_ground_location` uses `specifyLocationPCPF`; recorded elevation/azimuth converted to geodetic; pass prediction uses the WGS-84 site and normal; GUI/schema labels | `tests/test_geodesy.py` (published WGS-84 constants, round trip, independent elevation/azimuth, Basilisk site); template 19 full Basilisk run: passes 10.4-18.2 min (61.6 deg) and 106.8-111.8 min (16.1 deg) | 2068 passed, 11 skipped, 0 failed |
| R03 | E-ST-10-09C 5.3.1b, 5.3.1c; CCSDS 502.0-B-3 4.2.4.9 | `engine/tle.py`: TLE checks, SGP4 to the scenario epoch, TEME of date -> EME2000 (IAU 1976/1980 via ERFA); service, lifetime, pass prediction and plausibility warnings use it; GUI shows the TLE epoch and age; new runtime dependencies `sgp4`, `pyerfa` | `tests/test_tle.py`: Vallado TEME->J2000 example to 0.1 m, SPICE IAU-1976/1980 dynamic frame to 1e-13 rad, propagation to the scenario epoch, malformed TLEs, SGP4 failure, warnings; GUI test | 2082 passed, 11 skipped, 0 failed |
| R01 | Q-ST-80C 6.2.4, 6.2.7 (and input to 5.5, H07) | `spacemissionstudio/dependencies.py` (qualified Basilisk 2.12.0, check, dependency versions, data-file records); installers pin `bsk[all]==2.12.0`; GUI status bar and CLI `run` warn on another version; `provenance.json` gains qualification, dependency versions, scenario SHA-256 and data files | `tests/test_dependencies.py` (check, installer pins = qualified version, file records, real run's provenance) | 2089 passed, 11 skipped, 0 failed |
| R06 | E-ST-10-04C 4.2.1b, 4.2.2a, 4.2.2d, 6.2.1a, 6.3 | `engine/environment_models.py` (TSI 1361 W/m^2 with 1/r^2, Earth-Sun distance, sensorThermal input correction, Kaula truncation estimate); thermal sensors use the corrected inputs; warning for drag around a point-mass Earth; Explain-tab note when truncation exceeds SRP; schema caps the gravity degree at 180 (GGM03S); GUI 70 x 70 guidance; 4.2.2d -> deviation D-07 (TN36 unreachable) | `tests/test_environment_models.py`: Table 6-2 aphelion/perihelion, DE430 distance to 2e-4 AU, Basilisk 2.12 sensorThermal constants measured, corrected sensorThermal equilibrium = standard equilibrium to 0.01 K, truncation estimate, checks, degree cap | 2097 passed, 11 skipped, 0 failed |

## Result differences against the baseline

* R05: ground-station geometry changes by design. Template 19's predicted
  second pass now lasts 5 min instead of 4 min and its first-pass peak
  rounds to 60 deg instead of 61 deg; three test expectations
  (`test_scenario_checks`, `test_scenario_explainer`, `test_record_interval`)
  were updated to the new values, which the full Basilisk run confirms.
  Basilisk's own `has_access` flag keeps its geocentric horizon (about 2 s
  difference at the 10 deg boundary in that run).
* R03: no existing test or template uses a TLE orbit, so no existing
  result changed. A TLE scenario whose epoch differs from the TLE epoch now
  starts where SGP4 puts the satellite at the scenario epoch (before: where
  it was at the TLE epoch).
* Phase 1 correction: Basilisk 2.12's `satTle2elem` does run SGP4 and
  rotate TEME (into GCRF); Phase 1 had said it did neither. Corrected in
  `gap_analysis.md` (section 3, B1) and the matrix.
* R01: `provenance.json` has five more keys; `test_results.py`'s exact-keys
  expectation was extended. No simulation result changed.
* R06: thermal-sensor temperatures change by design. Sunlit equilibrium
  rises by (1361/r^2 / 5.670374e-8 over 1366 / 5.76051e-8)^(1/4): +0.3 %
  at 1 AU (about +0.9 K at 300 K), between -0.6 % (aphelion) and +1.2 %
  (perihelion) through the year. No existing test asserted a temperature
  tightly enough to change. Gravity: no template is warned; five templates
  (04, 05, 07, 08, 21) now carry the Explain-tab 4.2.1b note.
