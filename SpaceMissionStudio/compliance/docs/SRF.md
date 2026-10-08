# SpaceMissionStudio: Software Reuse File (SRF)

DRD: ECSS-E-ST-40C Annex N
Document: SMS-SRF, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft, written by the supplier.
- The decisions in section 6 are the user's (decision D5: qualify
  Basilisk 2.12.0, pin it and check it at start-up).
- Acceptance of the reused software, its licences and its export status
  is a human action (H07).
- Where this file says "not assessed", the information was not available
  to the audit. That is a gap, not a finding that the item is absent.

## 1 Introduction (N.2.1<1>)

SpaceMissionStudio is built on existing software, Basilisk above all.
ECSS-E-ST-40C 5.4.3.7a and ECSS-Q-ST-80C 6.2.7 require reused software to
be analysed and documented. This SRF does that for every software item the
tool reuses, and for the reused data, so that the customer can decide
whether the reuse is acceptable for a category C tool.

## 2 Applicable and reference documents (N.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | ECSS-E-ST-40C Rev.1, 5.4.3.7 and Annex N |
| AD2 | ECSS-Q-ST-80C Rev.2, 6.2.7 (reuse of existing software) |
| RD1 | `spacemissionstudio/dependencies.py`: the qualified Basilisk version and the start-up check |
| RD2 | `compliance/phase3_log.md`: validation V-01 to V-08, findings F-01 to F-08 |
| RD3 | `compliance/deviations.md`: D-02 to D-07 (gaps in the reused models) |
| RD4 | Basilisk documentation, `https://avslab.github.io/basilisk/`; source `https://github.com/AVSLab/basilisk` |
| RD5 | PyPI release records of each package (section 9) |

## 3 Terms, definitions and abbreviated terms (N.2.1<3>)

| Term | Meaning |
|---|---|
| Reused software | Software not developed for this tool and used unmodified: Basilisk, the Python packages of section 4 |
| Workaround | Code in the tool that corrects a reused item's behaviour from outside, without modifying it |
| PyPI | The Python Package Index, from which the reused packages are installed |

## 4 Presentation of the software intended for reuse (N.2.1<4>)

This section gives, for each reused item, the information of
N.2.1<4>b: the software items, the Basilisk modules used, the reused data
and the conditions of use.

### Software items

| Item | Main features used | Developer | Version | Licence | Language | Execution environment |
|---|---|---|---|---|---|---|
| **Basilisk** (PyPI `bsk`) | Simulation framework: process, task and message architecture; the dynamics, environment, sensor, actuator and FSW modules listed below; `vizSupport` | AVS Lab, University of Colorado Boulder | 2.12.0 (pinned; checked at start-up) | ISC | C, C++ with SWIG Python bindings; Python utilities | Linux, Windows, macOS; Python ≥ 3.9 (abi3 wheels) |
| numpy | Arrays and linear algebra | NumPy developers | ≥ 1.24.4 (2.4.6 tested) | BSD-3-Clause (with 0BSD, MIT, Zlib, CC0 parts) | Python, C | Python |
| sgp4 | SGP4/SDP4 propagation of TLEs | Brandon Rhodes, after Vallado et al. | ≥ 2.20 (2.25 tested) | MIT | Python, C++ | Python |
| pyerfa | ERFA (SOFA-derived) time scales and precession and nutation | Astropy project | ≥ 2.0.1 (2.0.1.5 tested) | BSD-3-Clause | Python, C | Python |
| PySide6 | Qt 6 GUI, including Qt WebEngine for the plots | The Qt Company | ≥ 6.6 (6.11.2 tested) | LGPL-3.0-only, GPL-2.0-only or GPL-3.0 | C++, Python bindings | Python; a display |
| plotly | Interactive plots | Plotly, Inc. | ≥ 5.0 (7.1.0 tested) | MIT | Python, JavaScript | Python; Qt WebEngine |
| Basilisk's own dependencies | Installed with `bsk`: bokeh, colorama, matplotlib, pandas, pillow, pooch, protobuf, requests, tqdm. The tool does not import them directly. | various | as resolved by pip | open-source licences, not reviewed one by one | – | – |
| Vizard (optional) | 3-D visualisation of runs | AVS Lab | as downloaded by the user | AVS Lab's Vizard licence (not reviewed) | Unity application | Separate process |

### Basilisk modules used

The tool uses these Basilisk modules (from its imports):

| Package | Modules |
|---|---|
| `architecture` | `messaging`, `sysModel` |
| `simulation` | `spacecraft`, `svIntegrators`, `GravityGradientEffector`, `dragDynamicEffector`, `facetDragDynamicEffector`, `facetSRPDynamicEffector`, `radiationPressure`, `extForceTorque`, `thrusterDynamicEffector`, `reactionWheelStateEffector`, `MtbEffector`, `fuelTank`, `msisAtmosphere`, `exponentialAtmosphere`, `zeroWindModel`, `spaceWeatherData`, `magneticFieldWMM`, `eclipse`, `ephemerisConverter`, `groundLocation`, `simpleNav`, `starTracker`, `imuSensor`, `coarseSunSensor`, `magnetometer`, `sensorThermal`, `motorThermal`, `tempMeasurement`, `simpleSolarPanel`, `simpleBattery`, `simplePowerSink`, `vizInterface` |
| `fswAlgorithms` | `inertial3D`, `hillPoint`, `velocityPoint`, `sunSafePoint`, `locationPointing`, `attTrackingError`, `mrpFeedback`, `rwMotorTorque`, `cssWlsEst`, `tamComm`, `mtbMomentumManagement`, `thrForceMapping`, `thrFiringSchmitt`, `thrMomentumManagement`, `thrMomentumDumping`, `lambertPlanner`, `lambertSolver`, `lambertValidator` |
| `utilities` | `SimulationBaseClass`, `macros`, `orbitalMotion`, `simIncludeGravBody` (gravity bodies and the SPICE interface), `simIncludeRW`, `simIncludeThruster`, `simSetPlanetEnvironment`, `simHelpers`, `vizSupport`, the Monte Carlo `Controller` and dispersions, `DataFile`, `get_path` |

### Reused data

These data files are reused through Basilisk or by the tool:

| Data | Source | Used for |
|---|---|---|
| DE430 ephemerides, `naif0012.tls`, `pck00010.tpc`, `de-403-masses.tpc` | NAIF, via Basilisk's data fetcher | Planet positions, time, rotation models, GM values (D-07) |
| GGM03S gravity field | University of Texas CSR, shipped with Basilisk | Spherical harmonics |
| NRLMSISE-00 | US Naval Research Laboratory, implemented in Basilisk | Atmospheric density |
| WMM2025 coefficients | NOAA NCEI and BGS, shipped with Basilisk | Magnetic field (D-04) |
| IERS-based Earth PCKs | NAIF, downloaded only on the user's consent | ITRF93 Earth orientation |
| Space weather | CelesTrak SW-All (bundled); NASA MSFC solar-activity predictions (bundled) | Real solar and geomagnetic activity (D-01) |

### Further information

- **Industrial property and exportability:** every item is open source and
  published. No item has been classified for export control by the
  audit; classification is part of H07.
- **Warranty and maintenance:** all items are provided "as is" without
  warranty (their licences). Maintenance is by the developers' public
  projects.
- **Installation and training:** installed with pip from PyPI (and by the
  tool's installers, SRS-DEL-01). No training is provided.
- **Problem reporting:** through each project's public issue tracker; for
  Basilisk, GitHub issues of AVSLab/basilisk.

## 5 Compatibility of existing software with project requirements (N.2.1<5>)

**Requirements implemented through reuse:**
- Orbit and attitude dynamics, integration and gravity (SRS-F-03), with
  the planet orientation corrected by the tool (SRS-F-04).
- Atmosphere, SRP and magnetic field (SRS-F-03).
- Sensors, actuators and FSW (SRS-F-09).
- Ground-station access geometry (SRS-F-08).
- Lambert solution (SRS-F-11).
- Vizard (SRS-F-16).
- Time scales (pyerfa; SRS-F-07).
- SGP4 (sgp4; SRS-F-02).
- The GUI (PySide6, plotly; SRS-F-15).

**Availability and quality status of the information (Basilisk):**

| Information (N.2.1<5>b) | Status for Basilisk 2.12.0 |
|---|---|
| 1 Software requirements documentation | No ECSS SRS. Each module's documentation (RD4) states its purpose, inputs, outputs, assumptions and limitations. |
| 2 Architectural and detailed design documentation | Architecture and module documentation online (RD4), generated from the source with Doxygen and Sphinx; no ECSS SDD |
| 3 Traceability between system requirements, software requirements, design and code | None published |
| 4 Software requirements, design and code | The code is public (RD4) |
| 5 Unit tests documentation and coverage | Each module has unit tests in the source repository (pytest). The wheel ships only some of them (`utilities/tests`). The NRLMSISE-00 and WMM2025 tests were run against the pinned release (V-07). Coverage not assessed. |
| 6 Integration tests documentation and coverage | Scenario tests in the source repository; coverage not assessed |
| 7 Validation documentation and coverage | The validation of the models the tool uses was done by the tool, against GMAT R2026a, IERS and SOFA (RD2, V-01 to V-08). Basilisk's own validation publications were not assessed. |
| 8 Verification reports | Not published as such |
| 9 Problem reports | GitHub issues; not reviewed for the modules used |
| 10 Configuration and operating history | Release history on GitHub and PyPI; the tool uses one release (section 9) |

**Quality level against the project's requirements (category C):**
- The models the tool's results depend on were validated by the tool
  itself (RD2). The results meet the SRS performance requirements
  SRS-P-01 to SRS-P-08 for the configurations tested.
- Validation found two Basilisk accuracy defects. The tool corrects both
  from outside (section 8):
  - **F-01:** Basilisk extrapolates the Earth's orientation linearly
    across an integration step.
  - **F-07:** the atmosphere models use spherical altitude and latitude.
- Validation also found these behaviours, which are documented and
  accepted:
  - **F-03:** the field's GM and radius are the body's, not the file's.
  - **F-05:** the time argument is TDB.
  - **F-06:** IAU_EARTH is used without EOP files.
- Gaps in the reused models are deviations D-02 to D-06 (RD3): no
  thermospheric wind, no tides, WMM instead of IGRF, no external magnetic
  field, a 0 K thermal sink.
- **Not covered:** without ECSS documentation, traceability or coverage
  figures, Basilisk does not on its own meet the ECSS-Q-ST-80C 6.2.7
  expectations for reused software of category C. The tool's validation
  compensates for this only for the functions validated. The modules not
  exercised by V-01 to V-08 (for example the thermal and power models,
  the FSW algorithms) rest on Basilisk's own testing. Whether that is
  acceptable is the customer's decision (H07).
- **The other packages:** they are mature, widely used open-source
  libraries. For sgp4 and pyerfa the tool checks them against published
  test values (`tests/test_tle.py`: Vallado's TEME example;
  `tests/test_time_system.py`: SPICE). Their quality documentation was not
  assessed.

## 6 Software reuse analysis conclusion (N.2.1<6>)

| Item | Decision | Estimated level of reuse | Basis |
|---|---|---|---|
| Basilisk 2.12.0 | Reuse, unmodified, pinned and checked at start-up (decision D5) | The whole simulation core: dynamics, environment, sensors, actuators, FSW. The tool adds configuration, two workarounds, analyses, data handling and the user interface. | Rebuilding an equivalent framework is not feasible for the tool; validation shows the results meet the SRS once F-01 and F-07 are corrected |
| numpy, sgp4, pyerfa | Reuse, unmodified | Complete libraries, called through their public APIs | Reference implementations (SGP4, SOFA); checked against published values |
| PySide6, plotly | Reuse, unmodified | User interface only; no effect on numerical results | Standard GUI toolkit; results are produced by the engine without them (CLI) |
| Vizard | Optional reuse | Visualisation only | Not needed for any result |

**Method:** the level of reuse was estimated from the tool's imports (the
module list of section 4) and the requirement allocation of the SDD
(`SDD_components.md`). It is a qualitative estimate; no size-based measure
was made.

## 7 Detailed results of evaluation (N.2.1<7>)

The detailed evaluation of the Basilisk models the tool depends on is the
validation in RD2:

| Case | Reused models | Result |
|---|---|---|
| V-01 time scales | pyerfa (ERFA); Basilisk SPICE interface | TAI 0.15 µs, TT 0.11 µs, TDB 34 µs against GMAT |
| V-02 Earth orientation | SPICE ITRF93 PCK | 0.425 m at the surface against IERS 20 C04 |
| V-04 propagation | `spacecraft`, `svIntegrators`, gravity, SPICE, `msisAtmosphere`, `radiationPressure` | Two-body 0.004 m/day; 20 × 20 field 0.116 m/day (after F-01); third body 0.009 m in 7 days; SRP 1.135 m in 7 days; drag 0.78 km of 32 km (after F-07) |
| V-05 passes | `groundLocation` geometry (tool's geodetic elevation) | 0.081 s against GMAT |
| V-06 CCSDS OEM | – (the tool's own code) | 8.4 mm GMAT reading the tool's OEM |
| V-07 | `msisAtmosphere`, `magneticFieldWMM`: Basilisk's own unit tests, run unchanged against the pinned release | 294 passed |
| V-08 | sgp4 2.25: the package's tests, including Vallado's verification set | 49 passed |

The findings F-01 to F-08 and their analyses are in RD2.

## 8 Corrective actions (N.2.1<8>)

| Action | For | Implementation | Result |
|---|---|---|---|
| Mid-step planet orientation | F-01 | `engine/planet_rotation.py`: a SysModel (priority 450) giving the gravity model the orientation at the middle of each step, from a copy of the SPICE message. Basilisk is not modified. | 20 × 20 field error against GMAT reduced to 0.116 m/day (V-04) |
| Geodetic proxy position for the atmosphere | F-07 | `engine/geodetic_atmosphere.py`: a SysModel (priority 395) giving the atmosphere a position whose spherical altitude and latitude equal the true geodetic ones | Drag displacement difference against GMAT 0.78 km of 32 km (V-04); the remaining 1.6 % is unexplained (`phase3_log.md`) |
| Version pin and start-up check | Configuration of the reused baseline | `dependencies.py`: `QUALIFIED_BASILISK_VERSION = "2.12.0"`; warning on any other version; `basilisk_qualified` in every provenance | `tests/test_dependencies.py` |
| Warning without EOP files | F-06 | `engine/service.py` warns: ~160 m/day at degree 20 | `tests/test_frames.py::test_a_gravity_field_without_iers_data_warns_of_its_accuracy` |
| OEM version 1.0 and Lagrange for GMAT | F-08 | `--oem-interpolation lagrange`; GMAT reads only v1.0 OEMs | V-06 |
| Report upstream | F-01, F-07 | **Not done: human action H10.** The workarounds are removed once a qualified Basilisk release fixes the defects (SRS-M-02). | – |

## 9 Configuration status (N.2.1<9>)

**Reused baseline:**
- **Basilisk:** `bsk==2.12.0` from PyPI. Uploaded 2026-09-21.
  - SHA-256 of the published files (RD5):
    - `bsk-2.12.0-cp39-abi3-manylinux_2_28_x86_64.whl`:
      `f74936868949d58754dc7ef46e5c5fde05c33259c980ff1abd8ea9c1330816e2`
      (the file the audit tested);
    - `bsk-2.12.0-cp39-abi3-win_amd64.whl`:
      `4e1d27a830e11a24e6ba5eab49ef63382de135e5fbbadf37ee6ef2a3236615cd`;
    - `bsk-2.12.0-cp39-abi3-manylinux_2_28_aarch64.whl`:
      `370ab731d4c44066290adc84708d53748e18cb08b331bb2d09b7f5d1f3c8bf8e`;
    - `bsk-2.12.0-cp39-abi3-macosx_11_0_arm64.whl`:
      `b45f85e1f01f74c367b662a05b4bd7125f03006ddedb83fcb97e3da1d222418f`;
    - `bsk-2.12.0.tar.gz`:
      `d152f7177cfabcc780d63eaa5b316c70f821c98b781b670a8ec6ecccf9466bf1`.
  - The tool and CI install the release, not the Basilisk source tree
    of the repository that contains the tool (`../src`). That tree is a
    fork of Basilisk's development branch.
  - Only that tree's unit tests are used, in V-07, where two of them run
    against the release.
- **The other packages:** lower bounds in `pyproject.toml`. The versions
  tested are in section 4. Every run records the versions actually used
  in `provenance.json` (`dependency_versions`).
- **Data:**
  - Each data file a run uses is recorded with its size and SHA-256 in
    the provenance (`data_files`).
  - The Earth PCKs have a manifest with their source and SHA-256.
- **Open items:**
  - The other packages are pinned by lower bound only. A lock file with
    exact versions and hashes for releases is proposed in the SCMP
    description (`SDP.md`).
  - Its adoption is a human decision (H05).
