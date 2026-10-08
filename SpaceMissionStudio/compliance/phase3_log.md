# Phase 3 validation log (R13)

Validation of the tool against independent references (ECSS-E-ST-40C 5.6;
ECSS-Q-ST-80C 7.1.7a; ECSS-E-ST-10-09C 5.4.4b). Case definitions:
`tests/validation/validation_cases.py`. GMAT reference generator:
`compliance/validation/make_gmat_references.py`.

## References used

| Reference | Source | Status |
|---|---|---|
| GMAT R2026a (console, Ubuntu build of 2026-03-30) | sourceforge.net/projects/gmat, `gmat-ubuntu-x64-R2026a.tar.gz`, SHA-256 fe124b4a606b2e3b704a6fbb1c37b87598d5df0d18cb661c304b5f60074a7754 | downloaded 2026-10-08; not installed in the repository |
| IERS EOP 20 C04 (as shipped with GMAT, `eopc04_08.62-now`, SHA-256 52c95d68...ed3) | IERS via GMAT | observed values to 2026-03-17, predictions after |
| CelesTrak space weather (`SpaceWeather-All-v1.2.txt`, shipped with GMAT) | CelesTrak via GMAT | for the drag case |
| Vallado's ITRF/GCRF example of 2004-04-06 07:51:28.386009 UTC | literature (Vallado, Fundamentals of Astrodynamics and Applications) | values reproduced independently with ERFA (IAU 2006/2000A and the example's EOP) to 8 mm before use |
| SOFA, IERS web services, CelesTrak, JPL SSD | - | not reachable from this environment (2026-10-08) |

## Findings so far

| # | Finding | Effect | Action |
|---|---|---|---|
| F-01 | Basilisk 2.12 extrapolates the planet orientation linearly inside each dynamics step (`dcm_PfixN + dcm_PfixN_dot * dt`, `GravBodyData::computeGravityInertial`). The result is not a rotation; every gravity evaluation, point mass included, is stretched by about (omega dt)^2 / 2. | Two-body 400 km orbit, 1 day, against Kepler: 18.8 m at 1 s step, 148 m at the 10 s default, 1.2 km at 30 s. Degree 10 at 10 s: 66 m from a 0.25 s run. | Fixed in the tool without modifying Basilisk: `engine/planet_rotation.py` gives the gravity bodies a copy of the SPICE message with the mid-step orientation and zero rate. After: two-body < 1 mm/day at 10 s, < 1 mm at 30 s; degree 10 at 10 s within 2 cm of 0.25 s (`tests/test_planet_rotation.py`). Ground stations, attitude guidance and the atmosphere keep SPICE's own message (tested). The earlier explanation in `service.py` and in the two-body scenario (Euler-stepped central-body position) was wrong and is replaced. Reporting it to the Basilisk developers is human action H10. |
| F-02 | The Earth GM the propagation uses is 398600.436 km^3/s^2 (BODY399_GM of de-403-masses.tpc), not GGM03S's 398600.4415 as deviation D-07 and `ccsds_odm.EARTH_GM_KM3_S2` said (errors made in Phase 2). | 1.4e-8 in GM: about 18 m along-track per day at 400 km for the same initial state; exported OPMs stated a GM that was not the one used. | D-07 corrected; `EARTH_GM_KM3_S2` = 398600.436 with a test that it equals the simulation's GM. Choosing the GM remains decision D4 (TN36 not supplied). |
| F-03 | Basilisk's `SphericalHarmonicsGravityModel::initializeParameters` replaces the field file's GM and reference radius (398600.4415 km^3/s^2, 6378136.3 m for GGM03S) with the body's (398600.436, 6378136.6 m). | Coefficients applied with a radius 3e-7 too large: about 1e-7 relative on J2 (centimetres per day in LEO). | Recorded; not corrected (below the other errors); GMAT is given the same effective values so the comparison isolates implementation differences. |
| F-04 | V-02: the tool's Earth-fixed frame (SPICE ITRF93 from the installed NAIF PCKs) against ERFA IAU 2006/2000A with IERS 20 C04 (polar motion, UT1-UTC), 882 epochs 1990 to 2026-03. | Largest difference 0.43 m at the Earth's surface (14 mas), median 0.13 m. | Within the 1 m tolerance. |

## Result differences against the Phase 2 suite

* F-01 changes every propagated result slightly (more accurately). The
  full suite after the correction: 2193 passed, 11 skipped, 0 failed
  (5 new tests); one template claim
  test (03, GEO) needed its docstring's burn days updated (east-west
  12.5, 21.4, 31.1, 36.9 instead of 13, 20, 32, 41; north-south 16.4 and
  30.4); its assertions (box +/-0.05 deg, 3 east-west and 2 north-south
  burns in 32 days) hold unchanged.

## Open

* GMAT references generated for `twobody_leo`, `ggm03s_20_leo`,
  `third_body_geo`, `srp_geo`; `drag_leo` did not finish (GMAT did not
  return within 30 min) and is under investigation. The comparison tests
  (`tests/validation/`) are not written yet.
* V-01 time scales, V-05 ground-station passes and V-06 CCSDS OEM
  interchange with GMAT are planned.
