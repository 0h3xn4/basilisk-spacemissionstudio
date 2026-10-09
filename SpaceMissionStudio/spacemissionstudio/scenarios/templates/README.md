# Template missions

Twenty-five ready-to-run scenario files, for learning the tool and the
orbital mechanics it simulates, and as starting points for your own
missions (copy one, edit it, save it under a new name):

* **01-18 and 21** each demonstrate one concept in isolation.
* **19 and 20** deliberately integrate several.
* **22-25** are starting points: 22 and 23 to build your own mission
  from, 24 and 25 to compare with 05 and 09 using the newer formation
  law and Monte Carlo dispersions.

**New here?** Run 01, then 22, then follow the learning path at the end
of this file. To start your own mission, open 22 or 23 and Save As.

Every file is a complete, independently valid `Scenario` (built through
`schema.scenario`'s own dataclasses and `Scenario.validate()`, not
hand-written JSON -- see `scripts/_generate_templates.py` in this
repository, the source of truth these were generated from) with an
extensive `description` field explaining what it teaches, what to look at
after running it, and what to try changing. Read that field (open the
`.json` file directly, or look at the Description box at the top of the
GUI's scenario form after opening one) before diving into the raw numbers.

Templates with drag (04, 05, 07, 08, 18, 21) use a drag coefficient of
3.0, ESA AD10's value for operations (Sec. 5.2); the End of Life tab
and `spacemissionstudio lifetime` use its end-of-life 2.2 by default.

## Opening a template

```bash
# GUI: File -> Open..., then browse to one of these files, or:
python3 -m spacemissionstudio.gui.app

# CLI (needs a real Basilisk build):
spacemissionstudio run spacemissionstudio/scenarios/templates/01_two_body_circular_orbit.json --out-dir out

# Just check it's schema-valid, no Basilisk needed:
spacemissionstudio validate spacemissionstudio/scenarios/templates/01_two_body_circular_orbit.json
```

Once opened in the GUI, **Save As...** under a new name/location before
editing if you want to keep the original template intact for next time.

Every template also has its own **Customize...** button on its row of
the GUI's Load Scenario list: one dialog with all of that template's
settings, pre-filled, its key ones (usually those under "Try changing:")
first, with a section list and a filter. **Open in editor** applies the
changes in the Scenario Editor; the template file itself is never
touched. The key settings of each template are defined in
`gui/template_wizard.py`.

## Catalog

Roughly progressive order -- each one builds on ideas from the ones
before it, but none of them depend on running an earlier one first.

| # | File | Teaches |
|---|------|---------|
| 01 | `01_two_body_circular_orbit.json` | The basics: a single circular orbit, point-mass Earth, no perturbations, no attitude (`simulation_mode: orbit_only`). Kepler's third law. Deliberately kept perturbation-free (see '09' too) -- the clean baseline the others contrast against. |
| 02 | `02_elliptical_orbit_with_perturbations.json` | An eccentric (GTO-like) orbit with Earth oblateness (J2 and higher-order terms, via 10th-degree spherical harmonics) and Sun/Moon third-body gravity switched on -- nodal regression, apsidal rotation, why a fine `dynamics_task_rate_s` matters once `central_body_degree > 0`. Drag deliberately left off so the J2/third-body precession lesson stays visually clean. |
| 03 | `03_geo_station_keeping.json` | A 500 kg satellite in the 10 E GEO slot under 10th-degree gravity, Sun/Moon and SRP, held by `geo_station_keeping` (`engine.geo_station_keeping`): east-west burns keep its day-averaged longitude within +/-0.05 deg, north-south burns at the nodes keep its inclination under 0.05 deg. Longitude and inclination are measured in Earth's own rotating frame (SPICE `J20002Pfix`), and the spacecraft starts in Earth's TRUE equator (`engine.orbit_design.geostationary_elements_deg`) -- i = 0 in J2000 is already 0.17 deg inclined to it by 2030. Confirmed in a real 45-day Basilisk run: east-west burns (0.05-0.1 m/s) at days 13, 20, 32, 41; north-south burns (~2 m/s, ~1150 s at 1 N) at days 16 and 30, each from 0.051 to ~0.013 deg; 4.4 m/s and 1.1 kg in all (~36 m/s per year). The daily eccentricity wobble (+/-0.01 deg here) is not controlled. |
| 04 | `04_walker_constellation.json` | A 6-satellite, 2-plane Walker delta constellation, generated programmatically via `engine.constellation.generate_walker_constellation()` -- the same code path the GUI's "Generate Walker constellation..." dialog and the `generate-constellation` CLI subcommand use. Full perturbation set (10th-degree gravity, Sun/Moon, drag, SRP) on every satellite -- 700 km is genuinely drag-relevant; drag uses the real space weather shipped with the app (2030: NASA MSFC's 50th-percentile prediction; the 95th gives an ESA AD10 operations budget). |
| 05 | `05_formation_flying_phasing.json` | Two spacecraft, the follower holding a fixed in-track separation 50 km ahead of the chief (`phasing_keeping`, always paired with its own `station_keeping` -- see that config's own docstring for why) -- a basic formation-flying/proximity-operations control model. Full perturbation set on both spacecraft identically, same real space-weather data as '04'. |
| 06 | `06_attitude_pointing_basic.json` | Attitude pointing as a pure concept: `fsw_mode: hillPoint` (nadir pointing) with no sensors/actuators configured, so control torque is applied through an idealized effector rather than modeled hardware. Watch the attitude error converge. Gravity harmonics/third-body added for realism; drag/SRP deliberately left off -- '06' stays the simple version, '07' is the realistic one. `dynamics_task_rate_s` is deliberately 0.1 (not the schema default of 10, nor this template's own earlier 1.0) -- confirmed directly against a real Basilisk build that the earlier, coarser rate drove the idealized-actuation control loop numerically unstable (`sigma_BN` reached NaN) with this template's inertia; see HISTORY.md. |
| 07 | `07_attitude_pointing_with_adcs_hardware.json` | The same pointing problem as '06', but with a realistic hardware suite: star tracker, IMU, coarse sun sensor, three 6 N*m*s reaction wheels (VRW-D-6 class), and a solar-array/battery power budget, on a 150 kg, 0.8 x 0.8 x 1.0 m microsatellite. Full perturbation set (drag/SRP included) to match its own "realistic counterpart" role, same real space-weather data as '04'/'05'. The sun sensor sits on the +Z face that Sun-safe pointing turns to the Sun. |
| 08 | `08_mission_sequence_orbit_raise.json` | The Mission Sequence layer: a time-ordered command list (coast, snapshot, impulsive prograde burn, coast, snapshot) instead of one flat propagate-to-duration run -- edit it as a tree in the GUI's "Mission sequence" panel. The building block for a full two-burn Hohmann transfer (see the file's own description for how to extend it into one). Full perturbation set at 400 km (drag/SRP included, same real space-weather data as '04'/'05'/'07') -- doesn't undermine this template's own lesson, unlike '01'/'09'. |
| 09 | `09_monte_carlo_dispersion_analysis.json` | Uncertainty quantification: the same orbit as '01', run as a 20-case Monte Carlo batch with `dry_mass_kg` independently redrawn per run from a normal distribution. Deliberately kept perturbation-free, same as '01' -- the file's own `description` explains why (mass doesn't affect pure two-body trajectories at all; only drag/SRP/maneuvers would show mass sensitivity). |
| 10 | `10_gravity_gradient_torque.json` | An uncontrolled (`fsw_mode: null`), elongated 500 kg spacecraft (1 x 1 x 2 m bus) with `enable_gravity_gradient` set -- Basilisk's real `GravityGradientEffector`, a disturbance torque with no GUI/schema path to model at all until this feature. With zero initial body rate, attitude normally stays frozen for the whole run; here it visibly drifts instead, purely from gravity acting across the spacecraft's own non-uniform mass distribution. |
| 11 | `11_thruster_attitude_control.json` | The thruster counterpart to '06'/'07': the same `inertial3D` pointing problem, but actuated by eight real 1 N ACS thrusters on the corners of a 300 kg, 1.2 x 1.2 x 1.5 m bus (`thrForceMapping` -> `thrFiringSchmitt` -> `thrusterDynamicEffector`) instead of reaction wheels or an idealized effector -- real hardware, real on-times, real Vizard thruster plumes. |
| 12 | `12_reaction_wheel_momentum_dumping.json` | A 500 kg spacecraft's four 12 N*m*s reaction wheels (Honeywell HR12) under normal attitude control, started already heavily spun up -- `MomentumDumpingConfig` fires a separate cluster of eight 1 N thrusters (`thrMomentumManagement` -> `thrForceMapping` -> `thrMomentumDumping`) to bleed the excess momentum off while the wheels stay in control the whole time. Watch `{sat-1}.rw_speeds` drop in discrete steps as each desaturation burn fires (confirmed in Basilisk: three dumps, at 2, 103 and 204 s, take the stored momentum from 13.8 to 9.4 N*m*s, below the 9.6 N*m*s threshold). |
| 13 | `13_magnetic_torque_rod_momentum_management.json` | The alternative to '12', on a 150 kg microsatellite: four 15 A*m^2 magnetic torque rods continuously bias the same four reaction wheels toward target speeds using the real geomagnetic field (`MagneticMomentumManagementConfig` -> `mtbMomentumManagement`), rather than firing discrete thruster bursts. Watch `{sat-1}.rw_speeds` climb smoothly from zero toward 800/600/400/200 RPM instead of '12''s sharp steps -- same problem, a structurally different real Basilisk solution (confirmed in Basilisk: within 0.5 RPM of every target after 104 min). |
| 14 | `14_css_sun_heading_estimation.json` | Real sun-direction ESTIMATION, not truth: eight `coarse_sun_sensor` devices feed a dedicated `cssWlsEst` weighted-least-squares estimator, and `fsw_params['use_css_estimation']` routes that ESTIMATE (rather than `simpleNav`'s noise-free truth) into `fsw_mode: sunSafePoint` -- the same architecture as Basilisk's own `examples/BskSim/scenarios/scenario_AttEclipse.py` reference. Flown on '07''s 150 kg microsatellite with the same inertia-scaled default gains. Watch `{sat-1}.sun_heading_body_estimated` settle onto the real sun direction as the estimate itself stabilizes. |
| 15 | `15_celestial_body_pointing.json` | `fsw_mode: locationPointing`'s OTHER target option: `fsw_params['target_body']` points a body-fixed axis straight at a celestial body (here, the Moon) instead of a ground station, built via `engine.fsw.build_ephemeris_converter` (`SpicePlanetStateMsg` -> `EphemerisMsg` -> `locationPointing.celBodyInMsg`), the same converter + guidance pairing Basilisk's own `examples/scenarioAsteroidArrival.py` uses. `target_body` must name `gravity.central_body` or a `gravity.third_body_perturbers` entry. Unlike '06'/'07's fixed-relative-to-orbit targets, the commanded attitude here keeps changing as the target body moves along its own orbit. |
| 16 | `16_lambert_transfer.json` | A new Mission Sequence command kind, the counterpart to '08's `maneuver`: `lambert_transfer` solves for WHATEVER delta-V takes the spacecraft from its current state to a target position after a given time of flight (rather than you specifying the delta-V directly), via Basilisk's own `lambertPlanner` -> `lambertSolver` -> `lambertValidator` chain (`engine.mission_engine.MissionEngine._run_lambert_transfer`), then applies it immediately. Like Basilisk's own `examples/scenarioLambertSolver.py` (whose orbit, target and time of flight it uses), it first coasts a quarter orbit (2490 s) to the burn point: burning at t = 0 dips the path below Earth's surface, which `min_orbit_radius_m` rejects. Confirmed end to end in a real Basilisk run: both reports fire, and the spacecraft arrives about 1.6 m from `target_position_m` (tolerance 500 m). |
| 17 | `17_fuel_tank_depletion.json` | The exact '11' thruster-attitude-control setup, with a real `FuelTankConfig` added: Basilisk's own `fuelTank` state effector (`engine.fsw.build_fuel_tank`) now tracks real propellant depletion as the thrusters fire, reading the same mass-flow rate each thruster already computes for its own physics -- unlike this app's older hand-rolled station-keeping/phasing/constant-thrust propellant bookkeeping, this is Basilisk's own effector doing the real physics. Confirmed in a real Basilisk run on the 300 kg bus: ~0.3 g of the 0.5 kg starting load is consumed while the attitude settles (within 0.03 in about 3 minutes); after that only occasional short pulses fire. |
| 18 | `18_leo_station_keeping.json` | The direct LEO counterpart to '03': a 400 km satellite correcting atmospheric-drag-driven altitude decay with the same `station_keeping` deadband controller, instead of '03's GEO-scale Sun/Moon/SRP drift. A tight 1 km deadband and continuous drag mean repeated corrections; '03' instead holds a GEO slot's longitude and inclination. `enable_srp` deliberately off, same "isolate the one dominant perturbation" approach as '03'. Same real space-weather data as '04'/'05'/'07'/'08'; its exact nrlmsise00 decay rate has not been re-verified in this sandbox (no CelesTrak/SPICE route here) -- the station_keeping/drag parameters were instead tuned against a bypass-SPICE build with a realistically-reparameterized atmosphere model (2-3 real reboost burns over 14 days). |
| 19 | `19_sun_pointing_comms_link.json` | An integrated spacecraft: `comms_pointing` automatically switches attitude between Sun-pointing (normal operation, maximizing `power` generation) and ground-station-pointing, driven entirely by real `groundLocation.GroundLocation` access to `berlin-gs` -- never a manually-specified time window -- with a genuine, physically-slewed transition (only the attitude REFERENCE switches; the spacecraft's own integrated state is never reset). `rf_link` (extended with an `antenna_beamwidth_deg`-driven pointing-loss term) computes a live link margin gated on BOTH real access AND the spacecraft having actually switched into comms-pointing mode, so it can show a real, physically meaningful "geometrically visible but not yet actually linked" period right at each transition. The run starts at 08:30 UTC so Berlin is about to pass under the 10:30-LTAN orbit: a high (~60 deg) pass ~10-18 min in and a low (~15 deg) one ~107-112 min in, inside a 2 h 15 min run (a Sun-synchronous orbit crosses Berlin's latitude only near 09:50 and 23:10 local time, so the old midnight-UTC start put the first pass ~8 h in). The one template that layers ground station + RF link + comms-pointing + power onto a single spacecraft -- see the file's own `description` for the full cross-subsystem story, including a documented, deliberately-not-yet-used upgrade path to Basilisk's own native `simpleAntenna`/`linkBudget` modules. |
| 20 | `20_thermal_simulation.json` | Adds Basilisk's real thermal modules on top of '07's own ADCS hardware suite: a `"thermal"` sensor (`sensorThermal.SensorThermal`) on the Sun-facing +Z panel models an externally-mounted component heating in sunlight and cooling in eclipse -- real radiative absorption/emission plus an optional internal power draw, with its own `measurement_*` noise/bias/fault layer (`tempMeasurement.TempMeasurement`), the same device-interface-realism shape as every other sensor kind. `rw-1` separately carries an OPTIONAL per-wheel motor-thermal model (`motorThermal.MotorThermal`, the `motor_thermal_*` params) -- motor inefficiency/friction heat vs. ambient dissipation, independent of whether any `"thermal"` sensor exists at all; `rw-2`/`rw-3` deliberately have none set. Watch `{sat-1}.sensor.therm-1.temperature` track several full sunlight/eclipse cycles and `{sat-1}.actuator.rw-1.motor_temperature` rise above its 20 C ambient (its starting temperature) as the wheel works -- only ~0.05 C in a real Basilisk run: one gentle slew does little work. |
| 21 | `21_disturbance_torques.json` | Attitude-dependent drag and solar radiation pressure from a facet model (`SpacecraftConfig.facets`, Basilisk's `facetDragDynamicEffector`/`facetSRPDynamicEffector`): two copies of one 300 kg Sun-pointing spacecraft, built as a box plus a 2.5 m^2 array on a boom 1.5 m off to +Y, so the array's pressure torques the spacecraft. `rods-off` has only wheels; `rods-on` adds 30 A*m^2 torque rods with magnetic momentum management. Confirmed in a real Basilisk run (`tests/test_template_claims.py`): rods-off stores ~1.7 N*m*s by the end of the day (January 2030, MSFC's 50th-percentile prediction, Cd 3.0), rods-on stays under ~20 RPM; both stay Sun-pointed. Sunlit SRP torque matches the hand estimate (2.24e-5 N*m, `tests/test_facets.py`). |
| 22 | `22_starter_first_leo_satellite.json` | **Starter.** The smallest scenario that is still realistic: one 150 kg satellite in a 550 km Sun-synchronous orbit (10:30 LTAN), degree-10 gravity, Sun and Moon, drag from the real space weather shipped with the app (Cd 3.0), solar pressure, and the Berlin ground station. Orbit only, so a day runs in seconds. Confirmed in a real Basilisk run (`tests/test_template_claims.py`): four Berlin passes in the day, the first 10.5-18 min in, 15 eclipses of ~35 min, and the mean orbit plane turning ~1.0 deg/day (Sun-synchronous: 0.986). Over 30 days drag lowers the mean semi-major axis ~0.1 km here, ~1.8 km at 400 km. Its description says what to change first to make it your own. |
| 23 | `23_starter_complete_small_satellite.json` | **Starter.** A complete small satellite: the GUI's "Microsatellite (150 kg)" preset (`engine.spacecraft_templates`: star tracker, IMU, sun sensor, three wheels unloaded by torque rods, facets with Cd 3.0, a 1 m^2 array and 300 Wh battery) in Sun-safe pointing, plus a 5 W S-band downlink (`rf_link`) to Berlin, on 22's orbit. Its Mission Sequence propagates until the first Berlin pass starts (`pass_start`), reports, propagates until it ends (`pass_end`), reports, and coasts another hour. Confirmed in a real Basilisk run (`tests/test_template_claims.py`): reports at 10.4 and 18.2 min, link margin 11 dB at the 10 deg edge and 21 dB at the 62 deg peak, wheels up to ~310 RPM in the turn to the Sun and back under 1 RPM by the end, ~35 Wh drawn in the 35 min eclipse. |
| 24 | `24_formation_mean_element_control.json` | Template 05 with one change: follower-1's `phasing_keeping.control_law` is `mean_oe`, Basilisk's `meanOEFeedback` (continuous feedback on the mean orbital elements, through the follower's own 50 mN station-keeping thruster), for 14 days instead of 90. `tests/test_scenario_templates.py` checks that nothing else differs, so the two compare directly. Confirmed in a real Basilisk run: the separation error stays within 65 m (17 m RMS) after the first day, against 5 km for 05's drift-orbit law; 0.46 m/s in 14 days (0.20 of it in the first day), against 0.014 m/s for 05's 90 days. Requests stay under 4 mN and are not fired in eclipse (37% of the run); outside eclipse almost all are fired. |
| 25 | `25_monte_carlo_orbit_and_drag_dispersions.json` | Template 09's idea with the newer dispersions: 20 runs of a 150 kg satellite at 400 km for 3 days, each starting on a slightly different orbit (`orbit_elements`, 1-sigma: 1 km in semi-major axis, 0.02 deg in inclination, 0.1 deg in true anomaly) with a drag coefficient drawn between 2.2 and 3.0 (`drag_coeff`). Measured in a real 20-run batch: the runs start ~10 km apart along track (1-sigma) and spread ~150 km per day (447 km after 3 days), almost all from the semi-major-axis spread (a 1 km lower orbit gains ~9 km per orbit); drag alone separates them by only ~10 km in 3 days. The GUI saves the batch to a folder but does not plot it; `examples/monte_carlo_spread.py` reads it back. |

## A learning path

| Step | Templates | What you learn |
|---|---|---|
| 1. Orbits | 01, 02, 22 | An ideal orbit; what Earth's shape, the Sun and the Moon do to it; a realistic satellite with drag and a ground station |
| 2. Keeping an orbit | 18, 03, 17 | Station keeping against drag (LEO) and drift (GEO); how propellant runs down |
| 3. Pointing | 06, 07, 15, 14 | Attitude control, ideal and with real hardware; pointing at the Moon; finding the Sun with sun sensors |
| 4. Disturbances and momentum | 10, 21, 12, 13, 11 | Gravity-gradient and surface torques; unloading wheels with thrusters or torque rods; thrusters for pointing |
| 5. Missions in steps | 08, 16, 23 | Mission Sequences: burns, a Lambert transfer, stopping on a ground pass |
| 6. Several spacecraft | 04, 05, 24 | A Walker constellation; a formation held by two different control laws |
| 7. Whole systems | 19, 20, 23 | Power, radio link and thermal working together |
| 8. Uncertainty | 09, 25 | Monte Carlo batches: mass, orbit insertion, drag |

## Using one as a starting point for your own mission

**22** and **23** are made for this: 22 has the environment every LEO
mission needs and nothing else, 23 is a whole small-satellite mission.
Open one, **Save As...** under your own name, and change it a step at a
time, running after each (the User Manual's section 6, "Building your own
scenario, step by step", walks through it).

Templates '01' through '18' are deliberately minimal and self-contained --
no ground stations, no RF links, no Monte Carlo batches layered on top of
an attitude scenario, etc. -- so each idea is easy to see in isolation.
'19' and '20' are the exceptions: '19' is the integrated demonstration
showing what combining several of these concepts looks like (ground
station + RF link + comms-pointing + power, on one spacecraft), and '20'
layers both a thermal sensor AND an optional per-wheel motor-thermal model
onto '07's own full ADCS hardware suite. A real mission scenario will
usually combine several of these concepts this way (e.g. a comms-relay
constellation might start from '04' and add '07''s ADCS hardware plus a
ground station and RF link to each satellite, matching what
`gui/ground_station_editor.py`/`RFLinkConfig` add, or '19's own
`comms_pointing` for automatic antenna pointing, or '20's own `"thermal"`
sensor/`motor_thermal_*` params for thermal telemetry). Copying the
closest template and layering in the next concept from this list is
generally easier than starting from a blank scenario.
