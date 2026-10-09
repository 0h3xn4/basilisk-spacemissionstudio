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

"""User-facing descriptions of the bundled templates, keyed by template
number.

A real user called the old ones "just awful UI/UX": up to 7,000
characters of prose, mixing in development audit history, class names and
verification notes. Each is now a short summary plus "What to look at" /
"Try changing" bullets (and "Note" or "Limitations" where it matters),
written for someone using the app. Development history lives in
HISTORY.md and the generator's own comments, not here.

Format, rendered by ``gui.load_scenario_widget``: paragraphs separated by
a blank line; a paragraph whose first line ends with ":" is a heading,
and lines starting with "- " are bullets.
"""

DESCRIPTIONS = {
    "01": """\
A single spacecraft in a circular low-Earth orbit around a point-mass Earth: no perturbations and no \
attitude. The "hello world" of orbital mechanics. (The inclination is a Sun-synchronous one, but without \
Earth's oblateness the orbit plane does not actually turn to follow the Sun.)

What to look at:
- sat-1.position_N traces a perfect circle.
- The period matches Kepler's third law: about 92.6 minutes, so one day is ~15.5 orbits.

Try changing:
- Semi-major axis: higher means a slower orbit and a longer period.
- Inclination: watch the ground track change in Vizard.
- Eccentricity: see template 02 for an elliptical orbit.""",

    "02": """\
An eccentric (e = 0.7), transfer-like orbit with Earth's oblateness (degree-10 gravity) and Sun and Moon \
gravity. Drag is off, so the gravity effects stand out.

What to look at:
- sat-1.orbit_elements_mean.arg_periapsis and .raan: Earth's oblateness turns the perigee about \
+0.5 deg/day and the orbit plane about -0.3 deg/day (small next to the orbit itself in position_N).
- sat-1.velocity_N: much faster at periapsis than at apoapsis.

Try changing:
- Spherical-harmonics degree 0, for the unperturbed orbit.
- Only the Moon, or only the Sun, as third body, to isolate each effect.

Note:
- Keep the 1 s time step: a coarser step adds error to the harmonics gravity.""",

    "03": """\
A 500 kg geostationary satellite in the 10 deg E slot, kept there the way real GEO satellites are: \
east-west burns hold its longitude within +/-0.05 deg, north-south burns keep its inclination under \
0.05 deg. Sun and Moon gravity, solar radiation pressure and Earth's gravity field all push it out.

What to look at:
- geo-sat-1.geo_station_keeping.longitude: the one-day fit drifts across the box on a parabola, and a \
small along-track burn (0.05-0.1 m/s) turns it back at each edge -- 4 in 45 days.
- geo-sat-1.geo_station_keeping.inclination: Sun and Moon tilt the orbit ~0.0025 deg/day; at 0.05 deg a \
~2 m/s burn at a node takes it back to ~0.013 deg -- 2 in 45 days.
- geo-sat-1.geo_station_keeping.delta_v: north-south dominates, ~35 m/s per year in all.

Try changing:
- Target longitude: near 75 E or 255 E (the stable points) east-west burns become rare; near 165 E or \
345 E they come often.
- The box sizes: halving the longitude box roughly halves the time between east-west burns.

Limitations:
- The box holds the day-averaged longitude. The daily wobble from eccentricity (radiation pressure grows \
it, to ~+/-0.01 deg here and ~+/-0.03 deg after 3 months) is not controlled.""",

    "04": """\
A 6-satellite Walker delta constellation (2 planes of 3, phasing factor 1) at 700 km and 53 deg, with full \
perturbations: degree-10 gravity, Sun and Moon, drag and radiation pressure.

What to look at:
- Ground tracks in Vizard, or each satellite's position_N.
- The planes are 180 deg apart in RAAN; satellites are evenly spaced in a plane, offset between planes by \
the phasing factor.

Try changing:
- Satellite count, planes or phasing factor: regenerate with Spacecraft > Generate Walker constellation.

Note:
- Drag uses real space weather; 2030 is NASA MSFC's 50th-percentile prediction. For an ESA AD10 \
operations budget, set Solar activity to Conservative (MSFC 95th) in Propagation setup.
- Cd 3.0: AD10's operations value.""",

    "05": """\
Two spacecraft in Sun-synchronous orbits, with follower-1 holding 50 km ahead of chief-1 for 90 days. The \
chief holds its altitude; the follower mirrors the chief's reboosts and fires small along-track burns when \
the separation drifts out of tolerance.

What to look at:
- follower-1.phasing_keeping.separation_error and .relative_semi_major_axis.
- The separation drifts slowly and reaches the edge of its 10% band around day 20; one correction turns \
it round within a day, never more than 0.2 km outside.
- It then stays within 45-54 km, for ~0.014 m/s in all.

Try changing:
- Target separation (a list of values steps through a schedule).
- Correction window: shorter is faster but costs more delta-V (roughly 1 / window).
- Tolerance: tighter triggers corrections sooner.
- follower-1's starting mean anomaly, to begin off target.
- Duration: under ~20 days no correction fires; the maximum is 100 days.""",

    "06": """\
A spacecraft pointing at nadir, starting tipped away from it with a small body rate. There are no sensors \
or actuators: the control torque is applied ideally, so this shows only the pointing concept. Template 07 \
adds real hardware.

What to look at:
- Vizard's attitude view: the spacecraft swings onto nadir and holds it.

Try changing:
- Pointing mode: velocityPoint (along the velocity) or inertial3D (fixed in space).
- The initial attitude tip.""",

    "07": """\
The realistic counterpart to 06, on a 150 kg microsatellite: a star tracker, IMU and coarse sun sensor, \
three 6 N*m*s reaction wheels, and a solar array with a battery. Sun-safe pointing, with full perturbations.

What to look at:
- sat-1.rw_speeds as the wheels absorb the pointing manoeuvre.
- sat-1.battery_charge and sat-1.battery_net_power: charging to full in sunlight, then draining at the \
12 W bus load in eclipse.

Try changing:
- Reaction wheel limits, or pick real devices from the sensor/actuator catalog.
- Pointing mode locationPointing at a ground station (add a station first).""",

    "08": """\
Introduces the Mission Sequence: coast, take a snapshot, burn +50 m/s prograde, coast, take another \
snapshot -- instead of one plain propagation.

What to look at:
- The Mission Output tab: the snapshots before and after the burn.
- The orbit turns into an ellipse: apoapsis raised opposite the burn, periapsis unchanged.

Try changing:
- Burn size (bigger raises apoapsis more) or sign (negative lowers it).
- Add a second burn half an orbit later to circularize: a Hohmann transfer.""",

    "09": """\
Template 01's circular orbit as a 20-run Monte Carlo batch: each run's dry mass is drawn from a normal \
distribution, 500 kg +/- 25 kg.

What to look at:
- Run it with Run Monte Carlo...: the Monte Carlo tab shows every run and their spread.
- Mass barely matters here: with no drag, radiation pressure or burns, mass doesn't change the trajectory.

Try changing:
- Number of runs, or the standard deviation.
- Turn on drag or radiation pressure to make mass matter.
- Add an initial-attitude dispersion (needs full-attitude simulation).""",

    "10": """\
No attitude control, an elongated 500 kg bus (1 x 1 x 2 m: Ixx = Iyy = 208, Izz = 83 kg*m^2) and \
gravity-gradient torque on. Without the torque the spacecraft would stay at its initial attitude; with it, it slowly turns.

What to look at:
- Vizard's attitude view: the spacecraft drifts away from its starting orientation.
- sat-1.attitude_sigma_BN: moving away from zero, its starting value.

Try changing:
- Inertia: make all three values equal and the torque vanishes.
- Altitude: the torque falls off as 1/r^3.
- Add inertial3D pointing with reaction wheels (see 07) to cancel it.""",

    "11": """\
Attitude control with eight 1 N thrusters on the corners of a 300 kg bus, instead of reaction wheels, \
pointing at a fixed inertial attitude from an initial tip.

What to look at:
- sat-1.thruster_on_time: which thrusters fire, and for how long.
- sat-1.attitude_sigma_BN: from the initial tip to within a few degrees in about 2 minutes, then a small \
limit cycle as the thrusters pulse.
- Thruster plumes in Vizard.

Try changing:
- Thrust per thruster: weaker ones take longer to settle.
- The layout: fewer than 6 well-placed thrusters can't produce torque about every axis.""",

    "12": """\
A 500 kg spacecraft whose four 12 N*m*s reaction wheels start heavily spun up. Eight 1 N thrusters dump \
the excess momentum whenever it passes 9.6 N*m*s, while the wheels stay in control of the attitude.

What to look at:
- sat-1.rw_speeds dropping in sharp steps, one per dump (three in the first 4 minutes).
- sat-1.thruster_on_time: when the dump thrusters fire.

Try changing:
- Dump threshold: lower dumps sooner and more often.
- Initial wheel speeds.
- Remove momentum dumping: the wheel speeds never come down.""",

    "13": """\
The alternative to 12, on a 150 kg microsatellite: four 15 A*m^2 magnetic torque rods and Earth's \
magnetic field continuously steer four reaction wheels toward target speeds (800, 600, 400 and 200 RPM) while the wheels point the spacecraft.

What to look at:
- sat-1.rw_speeds settling smoothly near the targets over ~2 hours (within ~0.5 RPM), not in steps.

Try changing:
- Wheel speed biases: the target speeds.
- Gain: larger reacts faster but can overshoot.
- Inclination: a near-equatorial orbit sees a weaker field and converges more slowly.""",

    "14": """\
Sun-safe pointing driven by an estimated Sun direction: eight coarse sun sensors feed a weighted \
least-squares estimator, instead of using the true direction.

What to look at:
- sat-1.sun_heading_body_estimated settling near [0, 0, 1] as the +Z axis turns to the Sun.
- Accuracy depends on how many sensors are lit, as on real hardware.

Try changing:
- The sensors' field of view: narrower means fewer lit sensors and a worse estimate.
- Turn off "Estimate Sun heading from coarse sun sensors" to compare with the true direction.""",

    "15": """\
The spacecraft's +Z axis stays pointed at the Moon for the whole run, about three-quarters of an orbit \
(locationPointing with a celestial target).

What to look at:
- Vizard's attitude view: the commanded attitude keeps changing as both the spacecraft and the Moon move.

Try changing:
- Target body: the Sun, a farther and slower target.
- The pointing axis, to aim a different face.""",

    "16": """\
A Mission Sequence step that solves for the burn: lambert_transfer finds the delta-V that reaches a target \
position after a set time of flight, then applies it.

What to look at:
- The Mission Output tab: after the time of flight, the position sits at the target [-6578000, 0, 0] m, \
within about 2 m (the solver accepts up to 500 m).

Try changing:
- Target position or time of flight (too short a time is rejected with a clear error).
- Coast to burn point: shorten it to 10 s and the path dips below Earth's surface, so the minimum \
orbit radius check rejects it.""",

    "17": """\
Template 11's eight-thruster attitude control with a real fuel tank: propellant runs down as the \
thrusters fire, and the centre of mass shifts with it.

What to look at:
- sat-1.fuel_mass_remaining with sat-1.thruster_on_time: about 0.3 g of the 0.5 kg drains while the \
attitude settles; after ~3 minutes only occasional short pulses fire and it barely moves.

Try changing:
- Propellant below ~0.0003 kg, to run dry mid-manoeuvre.
- Thruster specific impulse: lower uses more propellant for the same correction.""",

    "18": """\
The LEO counterpart to 03: a 400 km satellite holding its altitude against atmospheric drag with a 1 km \
deadband. Radiation pressure is off, to isolate drag.

What to look at:
- leo-sat-1.station_keeping.altitude and .propellant_remaining: each reboost, and the propellant it costs over \
14 days; compare 03, which holds a GEO slot's longitude and inclination instead.

Try changing:
- Orbit altitude: lower decays much faster (try 350 or 300 km).
- Drag area or coefficient.
- Deadband.

Note:
- Drag uses real space weather; 2030 is NASA MSFC's 50th-percentile prediction.
- Cd 3.0: ESA AD10's operations value. The Budget tab's Launch delays repeats the budget for launches \
up to 5 years late.""",

    "19": """\
leo-comms-1 points its solar panel at the Sun, and slews its antenna to the Berlin ground station whenever \
the station is in view, then back. Power and the radio link follow what actually happens.

The run starts at 08:30 UTC, just before Berlin passes under the orbit: a high pass (about 60 deg) \
around 10-18 min in, and a low one (about 15 deg) one orbit later, around 107-112 min in.

What to look at, across each pass:
- berlin-gs.access_to_leo-comms-1.has_access: the passes themselves.
- leo-comms-1.comms_pointing.active_mode: 1 during the pass.
- leo-comms-1.comms_pointing.pointing_error_deg: large at the switch, then settling.
- leo-comms-1.battery_charge: dips while transmitting.
- berlin-gs.access_to_leo-comms-1.link_margin_db: poor during the slew, healthy once pointed, worse at low \
elevation, empty outside passes.

Try changing:
- The station's minimum elevation.
- Antenna beamwidth: narrower makes pointing error matter more.
- Comms power, or the duration (Berlin's next passes come about 13 h later, around 23:00 local time).

Limitations:
- The link budget uses a simplified antenna pattern, not Basilisk's antenna and link-budget modules.""",

    "20": """\
Template 07's hardware with thermal models: a thermal sensor on the Sun-facing +Z panel heats in sunlight \
and cools in eclipse, and reaction wheel rw-1 carries a motor-thermal model.

What to look at:
- sat-1.sensor.therm-1 (temperature) rising in sunlight and falling in each eclipse.
- sat-1.actuator.rw-1.motor_temperature: it rises only ~0.05 C above its 20 C ambient. The motor heats \
from wheel power and friction, and this gentle slew uses little of either.

Try changing:
- therm-1's facing direction, area, absorptivity, emissivity, mass or specific heat (more heat capacity \
responds more slowly).
- rw-1's motor efficiency (closer to 1 means less heat; 1 itself is rejected) -- it only shows on a wheel \
that works hard.

Limitations:
- The thermal sensor's power draw is constant (no on/off duty cycle yet).""",

    "21": """\
Two copies of one 300 kg Sun-pointing spacecraft, each built from flat plates (facets): its box and a \
2.5 m^2 solar array on a boom 1.5 m off to +Y. Sunlight and drag push on that array off-centre, a small \
steady torque. rods-off has only reaction wheels; rods-on also has torque rods.

What to look at:
- rods-off.rw_speeds: after the first turn to the Sun, the wheels soak up the torque all day -- about \
1.7 N*m*s stored by the end, rw-x near -815 RPM.
- rods-on.rw_speeds: the torque rods hand that momentum to Earth's magnetic field; the wheels stay under \
~20 RPM.
- rods-on.mtb_dipole_commanded: the rods working against the torque.

Try changing:
- The array's centre of pressure (rods-off: surface facets): back to y = 0 and the torque disappears.
- Its area or reflection coefficients: torque scales with both.
- Altitude: lower adds drag torque on the array.

Limitations:
- Facets are fixed to the body: the array does not rotate to track the Sun.""",

    "22": """\
Start here for your own mission: one 150 kg satellite in a 550 km Sun-synchronous orbit with the \
environment every LEO mission needs -- detailed gravity, Sun and Moon, drag from real space weather and \
solar pressure -- and the Berlin ground station. No attitude, so a day runs in seconds.

What to look at:
- The Events tab: four Berlin passes (the first 10-18 min in) and 15 eclipses of about 35 min.
- my-sat.orbit_elements_mean.raan: the orbit plane turns about 1 deg a day, in step with the Sun.
- The Explain tab: everything this scenario switches on, in one view.

Make it your own (Save As first):
- Spacecraft > Edit: your mass, drag area and orbit (a TLE works too).
- Ground stations: add yours.
- Propagation setup: the duration and solar activity.

Try changing:
- Altitude 400 km and 30 days: drag lowers the mean semi-major axis ~1.8 km (at 550 km only ~0.1 km).
- Spacecraft > New from template, for a satellite with hardware (see 23).""",

    "23": """\
A complete small-satellite mission to copy and edit: the 150 kg microsatellite preset (star tracker, IMU, \
sun sensor, wheels unloaded by torque rods, solar array, battery) in Sun-safe pointing, with a radio link \
to Berlin.

A Mission Sequence stops at the start and end of the first pass (about 10 and 18 min in), reports both, \
then coasts on for an hour.

What to look at:
- The Mission Output tab: the two reports.
- berlin-gs.access_to_smallsat-1.link_margin_db: 11 dB at the 10 deg edge of the pass, 21 dB at its peak.
- smallsat-1.rw_speeds: up to ~300 RPM while turning to the Sun, then the torque rods bring them back \
near zero.
- smallsat-1.battery_charge: full in sunlight, about 35 Wh used in the 35 min eclipse.

Try changing:
- Pointing mode locationPointing at berlin-gs, to aim at the station.
- The transmitter power or data rate (Power/propulsion tab).
- Add a station-keeping thruster (template 18 shows how).""",

    "24": """\
Template 05's formation, held by Basilisk's mean-element feedback (meanOEFeedback) instead of the \
drift-orbit controller: continuous small burns on all six mean orbital elements. Same spacecraft, orbits \
and thruster, so you can compare the two runs.

What to look at:
- follower-1.phasing_keeping.separation_error: within ~0.0005 deg (65 m) after the first day, against \
kilometres in 05.
- follower-1.phasing_keeping.force: requests of a few mN; applied drops to 0 in each eclipse, when nothing fires.
- follower-1.phasing_keeping.delta_v: about 0.46 m/s in 14 days, against 0.014 m/s for 05's 90 days.

Try changing:
- Control law back to Drift orbit, or Hill-frame PD (needs a closer formation, about 1 km).
- Mean-element gain: higher holds tighter and spends more.
- Target separation: start off target and watch it close the gap within a day.

Note:
- The law needs Earth gravity of degree 2 or more (J2).""",

    "25": """\
A 20-run Monte Carlo batch with the uncertainty a real launch leaves: each run starts on a slightly \
different orbit (1-sigma: 1 km in semi-major axis, 0.02 deg in inclination, 0.1 deg along track) and flies \
with a drag coefficient between 2.2 and 3.0. Three days at 400 km, with real space weather.

What to look at:
- Run it with Run Monte Carlo...: the Monte Carlo tab opens on the runs' spread.
- The runs start ~10 km apart along track (1-sigma) and spread ~150 km a day: a lower orbit is faster.
- The Runs table: sort by semi-major axis to see the lowest orbits pull ahead.
- Drag alone (spreads set to 0) separates them by only ~10 km in three days.

Try changing:
- Number of runs, for smoother statistics.
- The element spreads, for a better or worse launcher.
- Add a dry-mass dispersion: with drag on, mass matters (compare template 09).""",
    "26": """\
An Earth-observation microsatellite and its data: a camera (80 kbit/s, orbit average) and housekeeping \
write into a 3 Gbit onboard memory, and an S-band patch antenna on the nadir face sends it to Berlin at \
5 Mbit/s whenever the link closes. Two days, pointing at nadir.

Berlin sees the satellite in two groups of passes a day, 9 to 11 h apart. Between them the camera fills \
the memory, and what no longer fits is lost.

What to look at:
- eo-sat.data_handling.stored: filling between passes, emptying in them, full in the long gaps.
- eo-sat.data_handling.data_lost: 0.9 Gbit of the 14.5 Gbit generated; the memory is first full 12 h in.
- berlin-gs.access_to_eo-sat.link_margin_db: 16 dB at the best pass, 3.7 dB at the 10 deg edge, where \
Berlin is 65 deg off the patch's boresight (.antenna_off_boresight).
- The Events tab: each downlink and how much it sent.

Try changing:
- Memory capacity 8 Gbit (Data handling, Power/propulsion tab): nothing is lost.
- Add a ground station on Svalbard (78.23 N, 15.39 E): everything generated is downlinked.
- Data rate 10 Mbit/s: the edge margin falls to 0.6 dB.
- Antenna pattern: a gain table from your patch's datasheet. The cos^n model is broader than most real \
patches.""",
    "27": """\
A 300 kg satellite whose cells sit on two deployed wings, 2.4 x 1.0 m and 8 kg each, one on each side. Each \
wing is a panel on a spring-damper hinge, so it flexes and its motion acts back on the attitude. The \
satellite starts 71 deg off the Sun and turns to it with its wheels. 2.4 hours.

The wings' first mode is assumed: 0.2 Hz with the hub held fixed, and 0.5% damping. Use your array's \
measured or analysed value.

What to look at:
- flex-sat.solar_array.wing-1.deflection: 0.07 deg as the wheels start the turn, ringing at 0.26 Hz. \
Free of the hub's mass, the wing rings faster than its hub-fixed 0.2 Hz.
- The ringing is below 0.001 deg within 4.3 min: the attitude control damps it through the hub.
- flex-sat.sun_heading_body: within 0.1 deg of the Sun after 7.1 min, the same as with the wings rigid.
- flex-sat.solar_array.wing-1.power: up to 980 W per wing in sunlight, 0 in each eclipse (the first from 23 to 58 min).

Try changing:
- First mode 0.05 Hz (Flexible solar arrays, Orbit / mass tab): the wings swing 0.94 deg and ring at \
0.065 Hz, and the pointing still settles as before.
- Damping 5%: the ringing dies only slightly sooner, since the control already damps most of it.
- Recording interval 5 s: the Explain tab warns that the samples are too far apart to show the flexing.

Note:
- Flexible arrays need the rkf45 or rkf78 integrator.""",
}
