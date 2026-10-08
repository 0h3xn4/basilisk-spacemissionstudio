#
#  ISC License
#
#  Copyright (c) 2026, Autonomous Vehicle Systems Lab, University of Colorado at Boulder
#
#  Permission to use, copy, modify, and/or distribute this software for any
#  purpose with or without fee is hereby granted, provided that the above
#  copyright notice and this permission notice appear in all copies.
#
#  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
#  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
#  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
#  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
#  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
#  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
#  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#
"""Phase 1 assessments: ECSS-E-ST-10-09C, ECSS-E-ST-10-04C, CCSDS 502.0-B-3.

Each rule: (standard, match, status, evidence, gap, fix, effort, near_basilisk,
remediation). ``match`` is a requirement ID, or an ID prefix ending in ``*``;
the most specific match wins (see ``tools/build_matrix.py``). Evidence paths
are relative to ``SpaceMissionStudio/``. "B2.12" is the installed Basilisk
2.12.0 the tool runs on; "src" is this repository's Basilisk 2.13.0b0 source.
Statuses: C, P, N, NA, H (see ``build_matrix.STATUS``).
"""

# Shared findings, referenced by several rules ----------------------------------

_NO_CSD = "No Coordinate Systems Document (CSD) exists; frame and time conventions are spread over code docstrings."
_CSD_FIX = "Write the CSD (Annex A DRD) from the frame/time inventory in gap_analysis.md section 3.1."
_FRAMES_IN_CODE = ("engine/service.py (spice_object.zeroBase = central body; Basilisk state names r_BN_N, "
                   "sigma_BN); engine/kernels.py (naif0012, de430, pck00010)")
_TIME_GAP = ("Epoch stored as UTC (schema Scenario.epoch_utc); Basilisk/SPICE run in TDB (ET) from naif0012; "
             "results are tagged in elapsed seconds; the GUI Epoch axis adds them to the UTC epoch "
             "(gui/results_widget.py), and spaceWeatherData/MSIS count days from the UTC epoch. The "
             "UTC/TAI/TT/TDB relationship is implicit (inside SPICE) and documented nowhere.")

TECHNICAL_RULES = [
    # ======================= ECSS-E-ST-10-09C ===================================
    ("E-ST-10-09C", "5.2.1a", "H", "-", "No responsibility for coordinate-system definition is assigned.",
     "Name the person responsible for the tool's coordinate systems (CSD owner).", "S", "no", "H02"),
    ("E-ST-10-09C", "5.2.2*", "N", "-", _NO_CSD, _CSD_FIX + " Put it under configuration control (git).",
     "M", "no", "R14"),
    ("E-ST-10-09C", "5.2.2c", "H", "-", "Project-phase milestones (phase A/B) belong to the using project.",
     "Each project using the tool references the tool CSD from its own CSD.", "S", "no", "H01"),
    ("E-ST-10-09C", "5.2.2d", "H", "-", "Configuration control at phase B is a project action.",
     "Baseline the CSD with the tool release (git tag) and record it in the project CM.", "S", "no", "H05"),
    ("E-ST-10-09C", "5.2.2e", "H", "-", "Re-examination at each phase is a project/process action.",
     "Add a CSD review item to each tool release checklist.", "S", "no", "H01"),
    ("E-ST-10-09C", "5.2.3*", "P", _FRAMES_IN_CODE,
     "Elements needing frames (spacecraft B, inertial N, planet-fixed, Hill/orbit, sensor and actuator "
     "axes, facets, ground-station topocentric) are defined in code but not identified in one place, and "
     "no transformation chain is drawn.",
     "Frame inventory and transformation tree in the CSD (gap_analysis.md 3.1).", "M", "yes (documents Basilisk frames)",
     "R02,R14"),
    ("E-ST-10-09C", "5.3.1a", "N", "-", _NO_CSD, "List the conventions applied (IERS 2010, IAU 2006/2000A where "
     "used, SPICE J2000=ICRF alignment, WGS-84) in the CSD.", "S", "no", "R14"),
    ("E-ST-10-09C", "5.3.1b", "C", "R03 (Phase 2): engine/tle.py checks the TLE (length, line numbers, catalogue "
     "number, checksums), propagates it with SGP4 to the scenario epoch and rotates TEME of date -> EME2000 "
     "(IAU 1976 precession, IAU 1980 nutation, equation of the equinoxes without kinematic terms, via ERFA); "
     "engine/service.py uses it for TLE spacecraft; scenario_checks warns when the TLE is > 3 d from the "
     "scenario epoch; the GUI shows the TLE epoch and age. ISO 8601 epochs with a UTC offset are converted to "
     "UTC (engine/time_system.py, engine/tle.py). Tests: tests/test_tle.py (Vallado TEME->J2000 example, "
     "SPICE IAU-1976/1980 frame to 1e-13 rad, propagation to the scenario epoch, malformed TLEs, warnings), "
     "tests/gui/test_orbit_ic_widget.py.",
     "Phase 1 misdescribed Basilisk 2.12 (corrected in gap_analysis.md section 3): it does run SGP4 and rotate "
     "TEME, but only at the TLE epoch and into GCRF; the tool no longer calls it. Other external conventions "
     "the tool reads (CelesTrak space weather, MSFC tables) carry no frame; R09 adds CCSDS ODM.",
     "-", "M", "yes (replaces the call to a Basilisk utility; Basilisk unchanged)", "R03"),
    ("E-ST-10-09C", "5.3.1c", "P", "engine/tle.py module docstring specifies the TLE conversion (steps, models, "
     "frames, time scales); engine/time_system.py the UTC-offset conversion.",
     "Specified in code documentation; the CSD (R14) has to carry it.",
     "Copy the conversion specification into the CSD.", "S", "no", "R03,R14"),
    ("E-ST-10-09C", "5.3.2*", "P", "Basilisk naming convention used throughout (r_BN_N, sigma_BN, dcm_BN; "
     "series names engine/series_names.py)",
     "A consistent naming/notation exists (Basilisk's) but is not specified as the tool's convention; "
     "outputs name frames only by suffix (_N, _B).",
     "Specify naming, mnemonics, notation and sign conventions in the CSD; add frame metadata to outputs.",
     "S", "yes (adopts Basilisk notation)", "R02,R14"),
    ("E-ST-10-09C", "5.3.2b", "P", "docstrings and USER_MANUAL.md",
     "The inertial frame is called 'inertial'/'N' (SPICE J2000) and the Earth-fixed frame is IAU_EARTH; no "
     "recognised name is misused, but the docs do not state which is meant.",
     "Use the exact names (SPICE J2000/ICRF-aligned, IAU_EARTH) in docs and output metadata.", "S", "no", "R02"),
    ("E-ST-10-09C", "5.3.3*", "N", "-", "No frame figures exist.", "Frame figures in the CSD.", "M", "no", "R14"),
    ("E-ST-10-09C", "5.4.1a", "P", _FRAMES_IN_CODE, "Origins are set in code (N: central body via "
     "zeroBase; B: spacecraft centre of mass per Basilisk) but not specified in a document or in outputs.",
     "Specify origins in the CSD and in output metadata.", "S", "yes", "R02,R14"),
    ("E-ST-10-09C", "5.4.1b", "P", _FRAMES_IN_CODE, "Derivation of origins from reference points is implicit.",
     "Document in the CSD.", "S", "yes", "R14"),
    ("E-ST-10-09C", "5.4.1c", "P", _FRAMES_IN_CODE, "Derivation of axes from reference directions is implicit "
     "(SPICE frame definitions, Basilisk guidance frames).", "Document in the CSD.", "S", "yes", "R14"),
    ("E-ST-10-09C", "5.4.1d", "C", "SPICE frames and Basilisk DCM/MRP algebra are orthonormal by construction; "
     "tests/test_osculating_elements.py, tests/test_two_body_validation.py exercise them",
     "-", "Record the evidence in the CSD.", "S", "yes", "R14"),
    ("E-ST-10-09C", "5.4.1e", "C", "All frames right-handed (SPICE, Basilisk B/N/Hill; facet normals in B)",
     "-", "State it in the CSD.", "S", "yes", "R14"),
    ("E-ST-10-09C", "5.4.1f", "C", "No left-handed frame is imported (inputs: classical elements, cartesian "
     "J2000 state, TLE)", "-", "-", "S", "no", ""),
    ("E-ST-10-09C", "5.4.1g", "NA", "No left-handed frame exists", "-", "-", "S", "no", ""),
    ("E-ST-10-09C", "5.4.1h", "P", "engine/kernels.py: SPICE J2000 (epoch J2000.0)",
     "The inertial frame's epoch is fixed by SPICE (J2000) but stated neither in docs nor in outputs.",
     "Frame metadata on every state vector (frame name, epoch, origin).", "S", "yes", "R02"),
    ("E-ST-10-09C", "5.4.2a", "N", _FRAMES_IN_CODE, _TIME_GAP,
     "Time-system layer: every time tag carries its scale; document TDB as the propagation scale.", "M",
     "yes (wraps SPICE/Basilisk time)", "R02"),
    ("E-ST-10-09C", "5.4.2b", "C", "position_N series (engine/results.py, CSV export)", "-", "-", "S", "no", ""),
    ("E-ST-10-09C", "5.4.3a", "P", "engine/results.py TimeSeries.units",
     "Most series carry units in their CSV column names; dimensionless quantities are not marked "
     "consistently ([-] in some, nothing in others).", "Mark dimensionless series explicitly; check all series.",
     "S", "no", "R02"),
    ("E-ST-10-09C", "5.4.3b", "P", "engine/results.py TimeSeries.units; schema field names carry units "
     "(_km, _deg, _s)", "Angles and some derived series lack units in exports.",
     "Unit audit of every series and schema field; add missing units.", "S", "no", "R02"),
    ("E-ST-10-09C", "5.4.4a", "P", "CSV header time_s", "The time unit (s) is given, but not its scale or origin.",
     "Time column states scale and epoch (e.g. 'TDB seconds since <epoch>' or UTC ISO time tags).", "S", "yes",
     "R02"),
    ("E-ST-10-09C", "5.4.4b", "N", "-", _TIME_GAP + " Leap seconds: naif0012 (last leap second 2017-01-01); a "
     "later leap second would need a newer LSK and nothing checks LSK validity. lifetime.py uses its own "
     "GMST with UT1 = UTC.",
     "Time-system layer with explicit UTC/TAI/TT/TDB conversions (SPICE-backed), LSK validity check, "
     "documented relationships in the CSD; validate against SOFA/IERS reference values.", "M",
     "yes (wraps SPICE time)", "R02,R13"),
    ("E-ST-10-09C", "5.4.5a", "P", "SpacecraftConfig facets/sensors/actuators defined in B",
     "B is the Basilisk body frame (origin at the spacecraft point B); its relation to a material structure is "
     "not defined (the tool has no structural model).",
     "Document B as an analysis frame and how a project maps it to its mechanical frame.", "S", "yes", "R14"),
    ("E-ST-10-09C", "5.4.5b", "NA", "-", "AIT physical points/targets: not in the scope of an analysis tool.",
     "-", "S", "no", ""),
    ("E-ST-10-09C", "5.4.5c", "NA", "-", "As 5.4.5b.", "-", "S", "no", ""),
    ("E-ST-10-09C", "5.4.5d", "NA", "-", "As 5.4.5b.", "-", "S", "no", ""),
    ("E-ST-10-09C", "5.4.5e", "NA", "-", "Launcher interface frame: no launcher modelling.", "-", "S", "no", ""),
    ("E-ST-10-09C", "5.4.5f", "NA", "-", "Spacecraft/adapter/launcher mechanical frames: no launcher modelling.",
     "-", "S", "no", ""),
    ("E-ST-10-09C", "5.4.6a", "C", "R05 (Phase 2): engine/geodesy.py defines the reference surface (WGS-84 "
     "a = 6378137.0 m, 1/f = 298.257223563; sphere of the simulation radius for other bodies), longitude east "
     "positive from the body-fixed prime meridian, North Pole = +z of the body-fixed frame; engine/fsw.py places "
     "groundLocation with specifyLocationPCPF at the WGS-84 position; recorded elevation/azimuth are geodetic; "
     "GUI and schema label the coordinates. Tests: tests/test_geodesy.py (published WGS-84 constants, round "
     "trip, independent elevation/azimuth, Basilisk site position), tests/test_scenario_checks.py (template 19 "
     "passes vs full Basilisk run).",
     "Residual (Basilisk 2.12, B2): groundLocation's has_access flag uses the geocentric horizon, so a pass "
     "boundary can differ from the geodetic minimum-elevation crossing by up to ~0.19 deg (about 2 s in the "
     "template 19 check). The prime meridian is IAU_EARTH until R04. The CSD (R14) restates the definitions.",
     "-", "S", "yes (Basilisk's public API only)", "R05"),
    ("E-ST-10-09C", "5.4.7*", "P", "schema OrbitIC (classical elements, cartesian, TLE); results orbit_elements_* "
     "series (osculating via rv2elem, mean via clMeanOscMap)",
     "Parameterisations exist and are documented in docstrings, not mathematically in a CSD.",
     "Specify them in the CSD (element sets, mean-element theory, singularities).", "S", "yes", "R14"),
    ("E-ST-10-09C", "5.4.8*", "P", "Basilisk MRP attitude (sigma_BN), DCMs; Euler 3-2-1 inputs in schema",
     "Rotation conventions are Basilisk's (MRPs with shadow-set switching, DCMs); not specified in a CSD.",
     "Specify rotation decomposition, MRP/quaternion definitions and order in the CSD.", "S",
     "yes (documents Basilisk conventions)", "R14"),
    ("E-ST-10-09C", "5.4.8h", "P", "Basilisk outputs MRPs, not quaternions",
     "No error quaternion is output; if quaternions are added (e.g. CCSDS AEM/OEM extensions) the positive "
     "scalar convention applies.", "Keep in mind for any quaternion output.", "S", "no", "R02"),
    ("E-ST-10-09C", "5.4.9*", "N", "-", "Transformations are not defined verbally, mathematically and graphically; "
     "time dependence (planet rotation from pck00010) and interpolation (SPICE) are undocumented.",
     "CSD transformation definitions; frame layer documents time dependence.", "M", "yes", "R02,R14"),
    ("E-ST-10-09C", "5.4.9f", "P", "SPICE double precision; Basilisk DCMs",
     "Numerical precision adequate in double precision, but the IAU_EARTH (pck00010) Earth orientation omits "
     "nutation details and polar motion; precision vs users' needs not stated.",
     "Use the IERS-based high-precision Earth orientation (ITRF93 binary PCK) and state precision.", "M", "yes",
     "R04"),
    ("E-ST-10-09C", "A.*", "N", "-", "The CSD does not exist.", _CSD_FIX, "M", "no", "R14"),

    # ======================= ECSS-E-ST-10-04C ===================================
    ("E-ST-10-04C", "4.2.1a", "C", "engine/service.py (gravity bodies: central body point mass or GGM03S "
     "spherical harmonics, optional Sun/Moon/planets from DE430); tests/test_two_body_validation.py, "
     "tests/test_gravity_gradient.py", "-", "-", "S", "yes", ""),
    ("E-ST-10-04C", "4.2.1b", "P", "R06 (Phase 2): engine/environment_models.py gravity_truncation_acceleration "
     "(Kaula's rule, actual J2) and srp_acceleration; scenario_checks warns when drag is modelled around a "
     "point-mass Earth and the Explain tab notes when the field's truncation leaves out more than SRP, with "
     "the degree that matches it; tests/test_environment_models.py",
     "Relating truncation to the orbit/attitude accuracy REQUIREMENTS stays the analyst's task (the tool has "
     "no accuracy requirement input); drag is only compared for the point-mass case. Five bundled templates "
     "(04, 05, 07, 08, 21) use degree 2-10 with SRP on and get the note.",
     "Decide whether the templates move to the matching degree (slower runs).", "S", "no", "R06"),
    ("E-ST-10-04C", "4.2.1c", "P", "engine/kernels.py pck00010 (IAU_EARTH)",
     "High-degree gravity is evaluated in IAU_EARTH, a lower-accuracy Earth orientation than the IERS one.",
     "Earth orientation from IERS data (R04).", "M", "yes", "R04"),
    ("E-ST-10-04C", "4.2.2a", "P", "engine/kernels.py LocalGravData.GGM03S (GRACE-based, static, ICGEM, degree "
     "180); R06: schema caps the degree at 180, the GUI tooltip states the 70 x 70 requirement",
     "GGM03S satisfies items 1-4 as a model; the degree is the user's choice and templates use 0-10, below the "
     "70 x 70 the requirement asks for.",
     "Use degree >= 70 for compliant analyses (performance cost); template decision as 4.2.1b.", "S",
     "yes", "R06"),
    ("E-ST-10-04C", "4.2.2b", "N", "-",
     "No tides (Basilisk has no tide model) and no IERS Earth orientation parameters (IAU_EARTH from pck00010).",
     "EOP via the IERS-based high-precision Earth PCK (R04); tides: deviation (D-03) or tool-side model.", "L",
     "yes (Basilisk lacks tides)", "R04,D-03"),
    ("E-ST-10-04C", "4.2.2c", "C", "engine/kernels.py DEFAULT_KERNELS: de430.bsp (planets and Moon, DE/LE-430)",
     "-", "-", "S", "yes", ""),
    ("E-ST-10-04C", "4.2.2d", "N", "B2.12 astroConstants (MU_EARTH 398600.436 km^3/s^2 ...), "
     "simIncludeGravBody; de-403-masses.tpc",
     "Planetary GM values are Basilisk's/DE-403's, not the IERS 2010 (TN36) standards. D4: IERS TN36 was not "
     "supplied and could not be fetched (iers.org and iers-conventions.obspm.fr blocked, 2026-10-08), so "
     "deviation D-07 applies.",
     "Human action: supply IERS TN36 Table 1.1; then set gravBody.mu from it (public attribute).", "S",
     "yes (configures Basilisk objects)", "D-07"),
    ("E-ST-10-04C", "5.2.1a", "N", "engine/fsw.py build_magnetic_field_wmm (Basilisk magneticFieldWMM, "
     "WMM2025)", "WMM is used, not IGRF-12. IGRF-12 (2015) only predicts to 2020; for 2025+ epochs its use "
     "is questionable.",
     "Decision D2: tool-side IGRF (current generation) model, or deviation keeping WMM2025.", "M",
     "yes (Basilisk has no IGRF)", "R08,D-04"),
    ("E-ST-10-04C", "5.2.1b", "NA", "-", "No environment model in use carries its own geomagnetic field.", "-",
     "S", "no", ""),
    ("E-ST-10-04C", "5.2.1.1a", "N", "engine/fsw.py (WMM2025)", "As 5.2.1a.", "As 5.2.1a.", "M", "yes",
     "R08,D-04"),
    ("E-ST-10-04C", "5.2.2a", "N", "-", "No external (magnetospheric) field model; Basilisk has none.",
     "Deviation (D-05): internal field dominates at LEO for torque-rod/magnetometer analysis.", "L", "yes",
     "D-05"),
    ("E-ST-10-04C", "5.3a", "P", "WMM2025 (higher fidelity than a dipole)", "Recommendation to use IGRF not "
     "followed (see 5.2.1a).", "As 5.2.1a.", "S", "yes", "R08"),
    ("E-ST-10-04C", "5.3b", "NA", "-", "Permission (may).", "-", "S", "no", ""),
    ("E-ST-10-04C", "6.2.1a", "C", "Table 6-2 values: B2.12 solarFlux 1361.0 W/m^2 at 1 AU with 1/r^2 (SRP, "
     "facet SRP, solar panels); R06: engine/environment_models.py TSI 1361 W/m^2, Earth-Sun distance, and "
     "sensor_thermal_inputs, which corrects Basilisk sensorThermal's fixed 1366 W/m^2 and sigma 5.76051e-8 "
     "(both measured on 2.12) through its public inputs; tests/test_environment_models.py (Table 6-2 "
     "perihelion/aphelion values, DE430 distance, Basilisk equilibrium = standard equilibrium to 0.01 K)",
     "The thermal sensor's flux is set at the scenario epoch's Sun distance; over a multi-month run the real "
     "flux changes by up to 3.4 % (1316-1407 W/m^2) while the sensor keeps the epoch value.", "-", "S",
     "yes (configures Basilisk inputs; Basilisk unchanged)", "R06"),
    ("E-ST-10-04C", "6.2.1b", "NA", "-", "No spectral solar modelling (total irradiance only).", "-", "S", "no", ""),
    ("E-ST-10-04C", "6.2.1c", "N", "src sensorThermal.cpp radiates to 0 K", "No 3 K space sink in the "
     "thermal sensor model.", "Deviation D-06 (effect ~ (3/T)^4, negligible) or tool-side correction.", "S",
     "yes", "D-06"),
    ("E-ST-10-04C", "6.2.2a", "N", "engine/spaceweather.py (CelesTrak observed, then NASA MSFC prediction "
     "per ESA AD10 Sec. 5.9)",
     "Daily/81-day F10.7 come from the observed record and MSFC's prediction, not Table A-1. S10.7/M10.7 are "
     "not used (NRLMSISE-00 takes F10.7 and Ap only).",
     "Decision D1: add an ECSS-E-ST-10-04C reference-activity option, or deviation citing AD10.", "M", "no",
     "R07,D-01"),
    ("E-ST-10-04C", "6.2.2b", "N", "engine/spaceweather.py", "No fixed-index option with the Table 6-3 values "
     "(the historical-percentile mode was removed, schema v4).", "Decision D1 (Table 6-3 low/moderate/high).",
     "S", "no", "R07,D-01"),
    ("E-ST-10-04C", "6.2.2c", "N", "-", "No Table 6-4 ap storm profile.", "Decision D1.", "S", "no", "R07,D-01"),
    ("E-ST-10-04C", "6.2.2d", "N", "-", "As 6.2.2b/c.", "Decision D1.", "S", "no", "R07,D-01"),
    ("E-ST-10-04C", "6.2.3a", "NA", "-", "Permission (may).", "-", "S", "no", ""),
    ("E-ST-10-04C", "6.2.3b", "C", "engine/spaceweather.py: activity values are used as read, no margin added",
     "-", "-", "S", "no", ""),
    ("E-ST-10-04C", "6.2.3c", "N", "engine/spaceweather.py", "Future index sequences come from MSFC (AD10), not "
     "Table A-1.", "Decision D1.", "M", "no", "R07,D-01"),
    ("E-ST-10-04C", "6.3*", "N", "-", "Tables 6-2 to 6-4 are data for 6.2.1/6.2.2: TSI 1361 W/m^2 is used "
     "(SRP); Tables 6-3/6-4 are not available in the tool.", "See 6.2.1a, 6.2.2b-d.", "S", "no", "R07"),
    ("E-ST-10-04C", "6.3 (ECSS-E-ST-10-04_0760115)", "C", "As 6.2.1a: 1361 W/m^2 at 1 AU, 1/r^2 scaling "
     "(1316/1407 W/m^2 at aphelion/perihelion, tested).", "Thermal sensor: epoch distance only (see 6.2.1a).",
     "-", "S", "yes", "R06"),
    ("E-ST-10-04C", "7.2.1.1a", "C", "engine/service.py msisAtmosphere (Basilisk NRLMSISE-00), default "
     "atmosphere_model; tests/test_lifetime.py (density matches the simulation's)",
     "The exponential model can also be chosen; the tool warns that it is far too thin above ~150 km.",
     "Keep NRLMSISE-00 the default; mark exponential as non-compliant in the UI.", "S", "yes", ""),
    ("E-ST-10-04C", "7.2.1.1b", "NA", "-", "Permission (may); JB2008 not used.", "-", "S", "no", ""),
    ("E-ST-10-04C", "7.2.1.2a", "C", "No JB-2006/JB-2008 model in the tool", "-", "-", "S", "no", ""),
    ("E-ST-10-04C", "7.2.1.2b", "N", "engine/spaceweather.py", "No worst-case short-period mode with Table 6-3 "
     "high values (the conservative case is MSFC 95th percentile per AD10).", "Decision D1.", "S", "no",
     "R07,D-01"),
    ("E-ST-10-04C", "7.2.1.2c", "N", "engine/spaceweather.py", "Analyses longer than a week use observed and "
     "MSFC-predicted daily values, not Table 6-3 long-term constants.", "Decision D1.", "S", "no", "R07,D-01"),
    ("E-ST-10-04C", "7.2.1.2d", "N", "engine/spaceweather.py", "Uses MSFC, not Table A-1.", "Decision D1.", "M",
     "no", "R07,D-01"),
    ("E-ST-10-04C", "7.2.1.2e", "C", "engine/spaceweather.py: observed days are the record; MSFC months use the "
     "same smoothed value for the day and the 81-day mean", "No artificial mixing of high daily with low or "
     "moderate long-term values.", "-", "S", "no", ""),
    ("E-ST-10-04C", "7.2.2a", "N", "engine/service.py zeroWindModel (B2.12)", "No HWM07 winds; Basilisk only "
     "has a zero-wind model (co-rotating atmosphere).", "Deviation D-02, or a tool-side HWM wind model.", "L",
     "yes (Basilisk lacks HWM)", "D-02"),
    ("E-ST-10-04C", "7.2.2b", "NA", "-", "No wind model in use (see 7.2.2a).", "-", "S", "no", "D-02"),
    ("E-ST-10-04C", "7.2.2c", "NA", "-", "Permission (may).", "-", "S", "no", ""),
    ("E-ST-10-04C", "7.2.3a", "NA", "engine/service.py: drag refused for non-Earth central bodies",
     "Mars atmosphere not modelled; drag is Earth-only and refused elsewhere.", "-", "S", "no", ""),
    ("E-ST-10-04C", "A.2 (ECSS-E-ST-10-04_0760121)", "N", "-", "Table A-1 (solar cycle 23 indices) is not "
     "available in the tool.", "Decision D1.", "S", "no", "R07,D-01"),

    # ======================= CCSDS 502.0-B-3 =====================================
    ("CCSDS-502.0-B-3", "CCSDS-502.0-B-3 *", "N", "No ODM code anywhere (grep for OPM/OMM/OEM/CCSDS: none)",
     "Orbit Data Messages are neither read nor written.",
     "ODM module: OPM/OMM/OEM KVN read/write, XML (NDM/XML schemas from SANA needed), validation of "
     "incoming files, covariance, frame/time keywords via the frame/time layer.", "L",
     "no (uses the tool's frame/time layer)", "R09"),
    ("CCSDS-502.0-B-3", "ICS-*", "N", "No ODM code", "ICS item not supported (no ODM implementation).",
     "Implement with the ODM module and complete the ICS (Annex A) per item.", "L", "no", "R09"),
    ("CCSDS-502.0-B-3", "CCSDS-502.0-B-3 1.5.2.1", "NA", "-", "Conventions of the standard itself.", "-", "S",
     "no", ""),
    ("CCSDS-502.0-B-3", "CCSDS-502.0-B-3 3.1.6", "H", "-", "File naming to be agreed between exchange partners.",
     "Record the agreement in the ICD (Annex I items).", "S", "no", "H03"),
    ("CCSDS-502.0-B-3", "CCSDS-502.0-B-3 3.1.7", "H", "-", "Exchange method to be agreed between partners.",
     "Record in the ICD.", "S", "no", "H03"),
    ("CCSDS-502.0-B-3", "CCSDS-502.0-B-3 4.1.6", "H", "-", "OMM file naming to be agreed between partners.",
     "Record in the ICD.", "S", "no", "H03"),
    ("CCSDS-502.0-B-3", "CCSDS-502.0-B-3 4.1.7", "H", "-", "OMM exchange method to be agreed.", "Record in the ICD.",
     "S", "no", "H03"),
    ("CCSDS-502.0-B-3", "CCSDS-502.0-B-3 5.1.4", "H", "-", "OEM file naming to be agreed between partners.",
     "Record in the ICD.", "S", "no", "H03"),
    ("CCSDS-502.0-B-3", "CCSDS-502.0-B-3 5.1.5", "H", "-", "OEM exchange method to be agreed.", "Record in the ICD.",
     "S", "no", "H03"),
    ("CCSDS-502.0-B-3", "CCSDS-502.0-B-3 4.2.4.9", "P", "R03: engine/tle.py treats TLEs as TEME of date (the "
     "preferred option) and uses TEME only to read them.",
     "The ICD (H03) has to state the TEME interpretation; no OMM is read or written yet.",
     "OMM import/export with MEAN_ELEMENT_THEORY = SGP4, REF_FRAME = TEME (R09).", "M", "yes", "R03,R09"),
]
