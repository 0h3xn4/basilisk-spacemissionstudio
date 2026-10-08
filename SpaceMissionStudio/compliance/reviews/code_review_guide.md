# Independent code review guide (H06)

For a reviewer who did not write the code. Prepared 2026-10-08 (decision 12).

**Why:**
- The code, its tests and the audit were produced by one supplier, an AI
  coding assistant.
- External references check the results: GMAT, IERS and SOFA (`docs/SVR.md`).
  Nobody independent has read the code.
- ECSS-Q-ST-80C 6.2.6 and 5.1.3.2a, and ECSS-E-ST-40C 5.8.3.5a, ask for it.

**Scope:** the modules where a defect gives a plausible but wrong number,
plus the security-relevant ones. That is about 5,300 of the package's
29,000 lines, in priority order below. Everything else (the GUI, plotting,
templates) is lower risk and out of scope for a first review.

## How to review

1. **Set up:** `pip install "bsk==2.12.0"`; `pip install -e ".[dev,gui]"`.
   The tests run with `QT_QPA_PLATFORM=offscreen pytest tests -n auto`.
2. **For each file,** read it beside its tests (column "Tests").
   - Check the items in "What to check".
   - Run the file's tests, then try to break the code with a case the tests
     miss.
3. **Record each finding** in `findings.md`, with the template at the end of
   this guide. Severity:
   - **major:** a wrong result or a security hole;
   - **minor:** misleading or fragile, but correct today;
   - **note:** style or clarity.
4. **Independence:** don't let the supplier explain the code before you form
   your view. Read the code and its documents first.

**Reference material:**
- `docs/SDD.md`, `docs/CSD.md` (frames, time, units);
- `phase3_log.md` (findings F-01 to F-08);
- `docs/security_analysis.md`;
- `docs/dependability_safety_analysis.md`.

## Files, in priority order

| # | File | Lines | Tests | What to check | Known risk points |
|---|---|---|---|---|---|
| 1 | `engine/propellant_budget.py` | 772 | `tests/test_propellant_budget.py` | Each budget line against ESA AD10 (EOP-FM/2024-07-177 v3.0; not in the repository): injection, collision avoidance, clearance, graveyard, uncontrolled re-entry disposal. The rocket equation (`propellant_for`): mass, Isp, g0. Thruster efficiency. Margins. Units (m/s, kg). | The drag make-up is an orbit-averaged estimate, about 5 % below full runs (HISTORY.md). Drag figures published before F-07 are out of date (SRelD K-01). Date arithmetic in `_years_later` (leap years). Parallel jobs in `altitude_trade`. |
| 2 | `engine/lifetime.py` | 591 | `tests/test_lifetime.py` | Mean orbit from the osculating state. Density averaged around the orbit ring (`ring_states`, `RING_POINTS`). The re-entry threshold (perigee 120 km) and the 100 km stop. The 5- and 25-year rule checks. The deorbit burn (vis-viva). | Density must use geodetic altitude (F-07). Validated against one full decay run only (3 %). The exponential atmosphere is flagged as too thin. |
| 3 | `engine/planet_rotation.py` | 104 | `tests/test_planet_rotation.py` | The SPICE payload is copied, never modified. The sign and size of the −h/2 orientation shift. The orthonormalisation `1.5M − 0.5 M Mᵀ M`. Task priority 450, between SPICE (500) and gravity. | Works around Basilisk defect F-01 from outside Basilisk; a wrong sign doubles the error instead of removing it (V-04 checks it). |
| 4 | `engine/geodetic_atmosphere.py`, `engine/geodesy.py` | 85 + 171 | `tests/test_geodesy.py` | The proxy position has the true geodetic latitude and altitude on Basilisk's sphere. The WGS-84 constants. Convergence of `pcpf_to_geodetic`. The elevation and azimuth convention (South-East-Zenith; azimuth from North to East). | Workaround for F-07; residual 1.6 % in the drag validation, unexplained. |
| 5 | `engine/time_system.py`, `engine/frames.py` | 184 + 103 | `tests/test_time_system.py`, `tests/test_frames.py` | UTC → TAI → TT → TDB, and back (`elapsed_to_utc`). UTC offsets in epochs. The frame labels of result series (`series_frames` infers frames from names). | No leap seconds after 2017 are modelled (dependability analysis FM-03). `series_frames` is a naming heuristic: a new series name can get the wrong frame label. |
| 6 | `engine/earth_orientation.py` | 277 | `tests/test_earth_orientation.py` | The precedence of the two NAIF files. Last-datum parsing. Manifest and rollback. The DAF/PCK header check. Network access only in `fetch`. | Without the files the frame is IAU_EARTH (F-06); the warning must appear. |
| 7 | `engine/spaceweather.py` | 668 | `tests/test_spaceweather.py` | The order observed → CelesTrak forecast → NASA MSFC prediction at the chosen percentile. Column parsing of CSV and legacy text. Refusal outside the data. No network access in `resolve`. | **Only real data may be used: never synthetic** (user rule). A silent fallback to made-up values would be a major finding. |
| 8 | `engine/tle.py` | 156 | `tests/test_tle.py` | TLE checks (checksums, lengths). SGP4 errors. TEME → EME2000 (IAU 1976/1980). The epoch-age warning. | – |
| 9 | `engine/ccsds_odm.py` | 911 | `tests/test_ccsds_odm.py`, `tests/validation/test_v06_ccsds_oem.py` | Units in messages (km, km/s). The epoch and time-system conversion (TDB → UTC). The stated GM (398600.436, D-07). Coverage of the 502.0-B-3 rules. | GMAT reads only version 1.0 and Lagrange OEMs (F-08). |
| 10 | `schema/command.py` (the condition evaluator), `engine/mission_engine.py` (script consent) | 449 + 855 | `tests/test_command.py`, `tests/test_mission_engine.py`, `tests/test_cli.py`, `tests/gui/test_main_window.py` | **Security.** Can any allowed expression reach a Python object? Think about subscripts on numpy arrays, slices, comparisons that call `__eq__` on user values, and huge numbers. Is `script_block` refused before anything runs without consent, on every path (CLI, GUI, other callers of `MissionEngine`)? | Security analysis S-01, S-02, S-12 (resource use in conditions). |

## Findings template

Copy this into `compliance/reviews/findings.md`:

```markdown
# Code review findings

Reviewer: <name>, <affiliation/role>. Date: <YYYY-MM-DD>. Commit reviewed: <hash>.

| # | File:line | Severity | Finding | Evidence (test, case, reasoning) | Proposed fix |
|---|---|---|---|---|---|
| CR-01 | | major / minor / note | | | |

Files reviewed completely: <list>. Files reviewed in part: <list, with what was skipped>.
Statement: I did not write this code and was not directed by its author during the review.
```

## After the review

- Each finding gets a fix and a test (the supplier), or a recorded reason
  for no fix (the reviewer agrees).
- H06 closes when the files of this guide are reviewed and the major
  findings are closed.
- `compliance/audit/` then reflects the review.
