# SpaceMissionStudio: Coordinate Systems Document (CSD)

DRD: ECSS-E-ST-10-09C Annex A
Document: SMS-CSD, issue 1 (draft), 2026-10-08. Remediation R14.

**Status:** draft, not reviewed (H01).

The frame definitions are those of `spacemissionstudio/engine/frames.py`.
That module writes them into every run's `provenance.json`, so a result
carries the definitions it was computed with. This document restates them
and adds the time scales, the parameterisations and the transformation
chains. If the two ever differ, the code is what ran, and this document is
wrong.

## 1 Introduction (A.2.1<1>)

This document defines the coordinate systems, transformations, units and
time scales that SpaceMissionStudio uses, as required by ECSS-E-ST-10-09C
for the tool's inputs, results and exchanged data.

It was prepared during the ECSS/CCSDS audit (remediation R02 implemented
the frame and time layer; R14 wrote this document). It applies to version
2.0.0 of the tool.

## 2 Applicable and reference documents (A.2.1<2>)

| Ref. | Document |
|---|---|
| AD1 | ECSS-E-ST-10-09C, Reference coordinate systems |
| AD2 | CCSDS 502.0-B-3, Orbit Data Messages (frame and time-system values) |
| RD1 | `spacemissionstudio/engine/frames.py`, `engine/time_system.py`, `engine/geodesy.py`, `engine/earth_orientation.py`, `engine/tle.py` |
| RD2 | NIMA TR8350.2, WGS-84 |
| RD3 | NAIF SPICE documentation: frames (J2000, ITRF93, IAU_EARTH), PCK and LSK kernels |
| RD4 | SOFA/ERFA library documentation (time scales, IAU 1976/1980 precession and nutation) |
| RD5 | Vallado, Crawford, Hujsak, Kelso: *Revisiting Spacetrack Report #3*, AIAA 2006-6753 (TEME) |
| RD6 | Basilisk 2.12.0 documentation: `hillFrame`, MRP conventions |
| RD7 | `compliance/phase3_log.md`: validation V-01 (time), V-02 (Earth frame), findings F-01, F-05, F-06 |

## 3 Conventions, notation and naming (A.2.1<3>)

**International conventions:**
- The inertial frame is EME2000 as realised by SPICE (J2000).
- The Earth-fixed frame is ITRF93 as realised by NAIF's IERS-based PCKs;
  without them it is the IAU_EARTH rotation model.
- Geodetic coordinates use WGS-84 (RD2).
- TLE states are in TEME (RD5).
- CCSDS values are as in AD2: `REF_FRAME` EME2000 or TEME;
  `TIME_SYSTEM` UTC.

**Naming and notation (Basilisk's convention, RD6):**
- Each coordinate system has a descriptive name and a one-letter
  mnemonic: N, P, B, H, L. TEME is the exception.
- A vector names its points and its frame. In `r_BN_N`, the position of
  point B relative to point N is expressed in N components.
- A direction cosine matrix `dcm_XY` takes Y components to X components:
  `v_X = dcm_XY v_Y`. The transformation is named "Y -> X".
- An attitude is a modified Rodrigues parameter set `sigma_XY`, the
  rotation from Y to X.
- All frames and rotations are right-handed. No left-handed rotation
  convention is used (AD1 5.4.8e).
- Attitudes are MRPs. The tool's inputs, results and exchanged data
  contain no quaternions, so a quaternion convention (AD1 5.4.8g) is not
  needed.

**Transfer of coordinate data:**
- In results, every series carries its frame mnemonic in
  `provenance.json` (`series_frames`), and the frame definitions and named
  transformations alongside (`frames`, `transformations`).
- In CCSDS messages, frame and time system are stated in the message's
  `REF_FRAME` and `TIME_SYSTEM` keywords.
- In scenario files, inputs carry their frame in the field name or in the
  orbit type: `cartesian` is N, `tle` is TEME.

## 4 Units (A.2.1<4>)

| Quantity | Inside the engine and in results | In scenario inputs and the GUI |
|---|---|---|
| Length | m | km, where the field name says `_km` |
| Time | s | s, days (`_days`) |
| Angle | rad | deg (`_deg`) |
| Velocity | m/s | km/s (`_km_s`) |
| Mass, force, torque | kg, N, N·m | same |
| CCSDS messages | km, km/s, deg (AD2) | – |

The unit of every result series is in its CSV header (ICD-03). The unit of
every scenario field is in `ICD_scenario_fields.md`.

## 5 Time standards (A.2.1<5>)

| Scale | Use | Relationship |
|---|---|---|
| UTC | The scenario epoch (`epoch_utc`, ISO 8601); every calendar date shown; CCSDS epochs | – |
| TAI | Intermediate | TAI = UTC + ΔAT. ΔAT is the leap-second count: 37 s since 2017-01-01, the last leap second in both ERFA's table and `naif0012.tls`. Later leap seconds are not modelled. |
| TT | Intermediate | TT = TAI + 32.184 s |
| TDB | The simulation's time variable; SPICE ephemeris time (ET) | TDB = TT + (TDB − TT). The periodic term, below 1.7 ms, comes from ERFA `dtdb` at the geocentre. |
| UT1 | Earth rotation only | Contained in the Earth PCK (ITRF93); not used directly |

**Implementation:**
- The conversions use ERFA (`engine/time_system.py`), cross-checked
  against SPICE (`tests/test_time_system.py`).
- Each result's `time_s` is **TDB seconds since the scenario epoch**.
  `engine.time_system.elapsed_to_utc` converts it to UTC.
- Validation V-01 compared the tool with GMAT (RD7): TAI to 0.15 µs, TT to
  0.11 µs, TDB to 34 µs.
- GMAT evaluates the gravity field's time argument in TAI, the tool in TDB
  (finding F-05): about 0.1 m per day in LEO.

## 6 Overview of the coordinate systems (A.2.1<6>)

| Type (AD1 list) | Used | Frame |
|---|---|---|
| Inertial | yes | N: EME2000 (SPICE J2000), central-body centred |
| Orbital | yes | H: Hill frame of a spacecraft (radial, along-track, orbit normal) |
| Launcher | no | – |
| Satellite-fixed | yes | B: spacecraft body frame. Sensor and actuator axes are given in B. |
| Body-fixed rotating (planet) | yes | P: Earth-fixed (ITRF93, or IAU_EARTH without EOP files); IAU body-fixed frames for other central bodies |
| Topocentric | yes | L: ground-station frame (South-East-Zenith, WGS-84 geodetic horizon) |
| Test facility | no | – |
| Simulator | no separate frame | The simulation works in N, P, B, H and L |
| Processing or product | yes | TEME: SGP4 output, for TLE input only. Converted to N at the scenario epoch. |

**Theory between the systems:**
- **N → P (Earth), with EOP files:** the NAIF ITRF93 model: IAU 1976
  precession, IAU 1980 nutation with IERS corrections, true sidereal time
  from UT1, and polar motion.
- **N → P (Earth), without EOP files:** the IAU_EARTH rotation model of
  `pck00010.tpc`, which has no polar motion, no UT1 and no nutation. This
  gives about 160 m per day of position error at degree 20 in LEO (F-06),
  and the run warns about it.
- **N → P, other bodies:** the IAU rotation models.
- **TEME → N:** IAU 1976/1980 precession and nutation at the TLE's
  propagated epoch (equation of the equinoxes as in RD5).
- **SPICE J2000 and ICRF/GCRF:** taken as the same frame. The frame bias is
  about 23 mas, about 0.8 m in LEO. A CCSDS message in ICRF or GCRF is read
  as EME2000, with a note (decision D7).

## 7 Parameterisations (A.2.1<7>)

**Within a coordinate system:**

| Parameterisation | Frames | Definition |
|---|---|---|
| Cartesian position and velocity | N, P, B, H, L | Components along the frame's axes |
| Classical (osculating) orbital elements: a, e, i, Ω, ω, true or mean anomaly | N | Keplerian elements of the state with the central body's GM (Earth 398600.436 km³/s², D-07). Mean anomaly is converted by Kepler's equation. |
| TLE (SGP4 mean elements) | TEME | As in RD5; propagated by SGP4 to the scenario epoch |
| Geodetic latitude, longitude, altitude | P (Earth) | WGS-84: a = 6378137.0 m, 1/f = 298.257223563 (RD2). For other bodies, a sphere of the body's equatorial radius. |
| Azimuth, elevation | L | Elevation above the geodetic horizon; azimuth from North towards East |
| Along-track, radial, cross-track offsets | H | Relative position of a follower in the chief's Hill frame (formation design) |
| Geodetic proxy position | P | The position at the same geodetic latitude and altitude on the sphere the atmosphere model uses (finding F-07, `engine/geodesy.atmosphere_proxy_position`) |

**Within a transformation:**

| Parameterisation | Used for |
|---|---|
| Direction cosine matrix `dcm_XY` | N → P (from SPICE `pxform`), P → L, TEME → N |
| MRP `sigma_XY`, shadow set where \|σ\| > 1 | N → B (the attitude Basilisk integrates); guidance attitudes |
| Angular rate `omega_XY_X` (rad/s) | B relative to N, in B |

## 8 Transformation chains (A.2.1<8>)

**Top level:**

```
              TEME --(IAU 1976/1980, at the epoch; TLE input only)--+
                                                                    v
   DE430 ephemerides (Sun, Moon, planets) -----------------------> N  (EME2000 / SPICE J2000, TDB)
                                                                    |
              +---------------------------+-------------------------+
              |                           |                         |
              v                           v                         v
   P (ITRF93 or IAU_EARTH)        B (body; MRP sigma_BN)     H (Hill; from r_BN_N, v_BN_N)
              |
              v
   L (ground station; geodetic lat/lon, WGS-84)
```

**Constraints and measurements:**
- A ground station's L is fixed in P.
- Access is the elevation of the spacecraft in L above the station's mask.
- Simulated sensors measure in B: star tracker, coarse sun sensors,
  magnetometer, IMU.
- The gravity field acts in P.
- Drag uses the velocity relative to the atmosphere, which co-rotates
  with P.

**Lower-level chains:**

1. **Gravity in one step.**
   - N → P at the middle of the integration step, from the SPICE
     orientation shifted by −h/2 and re-orthonormalised
     (`engine/planet_rotation.py`, F-01).
   - The field is evaluated in P, and the acceleration is rotated back to
     N.
2. **Atmosphere.**
   - The position r_BN_N is rotated by N → P (SPICE) to give the geodetic
     latitude and altitude (WGS-84).
   - These give the proxy position on Basilisk's sphere, P → N
     (`engine/geodetic_atmosphere.py`, F-07).
   - The density at the proxy position is the density at the true
     geodetic point.
3. **Ground access.**
   - The site's geodetic coordinates give the site position in P, and
     `dcm_LP` gives the L axes.
   - The spacecraft position is rotated N → P, then transformed into L.
   - Elevation and azimuth are computed in L.
4. **TLE input.**
   - SGP4 gives the state in TEME at the scenario epoch, which is
     rotated TEME → N.
   - The result is the initial state in N.
5. **CCSDS export.**
   - The OEM or OPM state is taken in N (EME2000).
   - Epochs are converted TDB → UTC.

**Each system:**
- Every system above is drawn in the top-level chain.
- The axes of each are defined in section 9.

## 9 Detailed description of the coordinate systems (A.2.1<9>)

| Mnemonic | Name | Origin | Axes | Epoch and time scale | Realisation | Parent and transformation | Source |
|---|---|---|---|---|---|---|---|
| N | Inertial (EME2000 / SPICE J2000) | Central body's centre of mass | Earth mean equator and equinox of J2000 | J2000.0 = 2000-01-01T12:00:00 TT; ephemerides and propagation in TDB | SPICE with DE430 | Root of the chain | RD3 |
| P | Central body–fixed | Central body's centre of mass | Earth: ITRF93 (with EOP files) or IAU_EARTH; z along the rotation pole, x towards the prime meridian. Other bodies: IAU body-fixed. | Time dependent; TDB | SPICE PCK (`engine/earth_orientation.py` for Earth) | N; `dcm_PN` from SPICE `pxform(J2000, P, ET)` each step | RD3 |
| B | Spacecraft body | Spacecraft body point B (Basilisk hub frame origin) | Fixed to the structure, as given by `inertia_kg_m2` and the device axes | – | Basilisk spacecraft state | N; MRP `sigma_BN`, integrated by Basilisk | RD6 |
| H | Hill (orbit) | Spacecraft | x radial out, z along the orbit normal, y completing the triad (along-track) | Instantaneous | Basilisk `hillFrame` convention | N; `dcm_HN` from r_BN_N and v_BN_N | RD6 |
| L | Topocentric (ground station) | Ground-station site, WGS-84 geodetic | South-East-Zenith; geodetic horizon | Fixed in P | `engine/geodesy.py` | P; `dcm_LP` from the site's geodetic latitude and longitude | RD2 |
| TEME | True equator, mean equinox of date | Earth's centre of mass | SGP4 output frame | Of the TLE's propagated epoch; UTC | `engine/tle.py` | Converted to N: Pᵀ Nᵀ R3(−Eq) at the scenario epoch | RD5 |

The parameterisations of each system and each transformation are those of
section 7.
