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
| F-05 | The tool integrates geocentric motion in TDB seconds (Basilisk's simulation time is the SPICE ET offset); GMAT integrates in TAI seconds. | 13 us per day apart for this epoch: about 0.1 m along-track per day at 7.7 km/s. The tool and GMAT agree to 0.004 m at the same elapsed integration time. | Recorded, not corrected (Basilisk has one time variable; the effect is far below the other model errors). V-04 checks both the implementation (same elapsed time) and the user-visible result (same UTC, with this allowance). |
| F-06 | Without the IERS-based Earth orientation files the tool uses IAU_EARTH (1.5 mrad from ITRF in 2026). | A degree-20 field in a 400 km orbit is 160 m from GMAT after one day (0.2 m with the files). | The run warning now says so when a gravity field is used without the files. |
| F-07 | Basilisk 2.12's atmosphere models compute altitude and latitude on a sphere (`PCI2LLA` with the equatorial radius only); NRLMSISE-00 takes geodetic altitude and latitude. | At latitude phi the altitude is about 21 km sin^2(phi) too low. 400 km, 52.5 deg orbit: one-day decay 478 m against GMAT's 436 m (+10 %); GMAT on a sphere gives 486 m. | Fixed in the tool without modifying Basilisk: `engine/geodetic_atmosphere.py` gives the atmosphere model a proxy position with the WGS-84 geodetic altitude and latitude (same longitude); the drag force and wind use the real state; the lifetime evaluator applies the same conversion. After: 429 m against GMAT's 436 m (-1.6 %); position difference 0.78 km of a 32 km drag displacement. The remaining 1.6 % is not explained: GMAT already uses observed (not 1 AU-adjusted) F10.7 (tested with a copy of its file); differences in the Ap handling are possible but unconfirmed. Reporting F-07 to the Basilisk developers is part of H10. |

## V-01 and V-02 results

| Case | Reference | Result | Tolerance |
|---|---|---|---|
| V-01 TAI-UTC at 11 epochs 1980-2030, both sides of the 1999 and 2017 leap seconds | GMAT R2026a (its own leap-second table) | 0.15 us | 2 us |
| V-01 TT-TAI | GMAT | 0.11 us | 2 us |
| V-01 TDB-TT | GMAT: its two-term series (0.001657 sin M + 0.00001385 sin 2M; GMAT matches it to 1 us) | 34 us, the series' truncation | 50 us (**revised from 20 us**, which assumed GMAT used a full series) |
| V-01 TDB-TT series | SOFA's regression value for iauDtdb (t_sofa_c.c), quoted from memory and confirmed by ERFA reproducing it to 3.5e-18 s | 1e-15 s | 1e-15 s |
| V-02 Earth frame, 882 epochs 1990-2026-03 | ERFA IAU 2006/2000A + IERS 20 C04 (excerpt `tests/data/validation/eopc04_excerpt.txt`) | max 0.43 m, median 0.13 m at the surface | 1 m |
| V-02 Vallado ITRF/GCRF example, 2004-04-06 | published vectors (ERFA reproduces them to 1 cm) | 0.37 m | 1 m |

## V-04 results (tool at its 10 s default step against GMAT R2026a)

`tests/validation/test_v04_propagation.py`; tolerances fixed in `tests/validation/validation_cases.py` before the comparison, except where noted.

| Case | Arc | Implementation difference | Same-UTC difference | Tolerance | Result |
|---|---|---|---|---|---|
| two-body, 400 km circular, 52.5 deg | 1 day | 0.004 m | 0.103 m (allowance 0.102 m, F-05) | 0.05 m | met |
| GGM03S 20 x 20, same orbit (ITRF93 files) | 1 day | 0.116 m | 0.184 m | 1 m | met |
| Sun + Moon (DE430), GEO | 7 days | 0.009 m | 0.380 m | 1 m | met |
| as above + cannonball SRP with eclipses | 7 days | 1.135 m | 0.768 m | 10 m | met |
| NRLMSISE-00 drag, observed 2024 indices, 400 km | 1 day | 0.78 km | 0.78 km | 1.6 km (5 % of the 32 km drag displacement) | met after F-07; **the first tolerance, an absolute 500 m chosen without analysis, was not met and was revised** |

Two set-up errors of the validation itself were found and corrected before these results: GMAT takes the central body's GM from its gravity file even at degree 0 (its default JGM-2 gives 398600.4415), so every GMAT case now uses the converted file with the tool's GM; and the first LEO initial state was not circular (perigee at 31 km), which made the drag case meaningless.

## Result differences against the Phase 2 suite

* F-01 changes every propagated result slightly (more accurately). The
  full suite after the correction: 2193 passed, 11 skipped, 0 failed
  (5 new tests); one template claim
  test (03, GEO) needed its docstring's burn days updated (east-west
  12.5, 21.4, 31.1, 36.9 instead of 13, 20, 32, 41; north-south 16.4 and
  30.4); its assertions (box +/-0.05 deg, 3 east-west and 2 north-south
  burns in 32 days) hold unchanged.

* F-07 lowers NRLMSISE-00 density wherever the latitude is not zero, so
  every drag result changes: template 18's spacecraft from 300 km now
  re-enters after 34.0 days in Basilisk (25.4 before; the lifetime
  estimate still agrees, 34.35 vs 34.04 days, +0.9 %), and from its 400 km
  in March 2031 instead of during 2030. Three test expectations
  (`test_lifetime.py` twice, `test_cli.py`) were updated to these values;
  no template claim changed.

## Open

* The drag case's remaining 1.6 % difference from GMAT (see F-07).
* V-01 time scales, V-05 ground-station passes and V-06 CCSDS OEM
  interchange with GMAT are planned.
