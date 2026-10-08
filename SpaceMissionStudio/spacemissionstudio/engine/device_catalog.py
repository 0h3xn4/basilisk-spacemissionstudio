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

r"""A small catalog of REAL, commercially available, European-manufactured
small-satellite sensors/actuators, for :mod:`gui.sensor_actuator_editor`'s
"Select from catalog" picker -- direct user feedback: "the user should be
able to either create their own sensor/actuator or select from a range of
commonly used devices from the space industry. They must be ITAR free and
available in europe."

This module has NO Basilisk/PySide import and is fully unit-testable here
with no sandbox dependency -- it only produces plain
``schema.scenario.SensorConfig``/``ActuatorConfig``-shaped ``params`` dicts
(the exact same open dict shape ``gui.sensor_actuator_editor``'s own
"Reset to template" button already fills), via :func:`catalog_entries_for_kind`
and :data:`CATALOG`. Selecting an entry is a PRESET, never a lock-in: every
field it fills is the same ordinary spin box/JSON text the custom editor
already exposes, so a user can select one as a starting point and then
freely edit any value, exactly like "Reset to template" already works
today -- this module adds WHERE the template's numbers come from, not a
new editing mode.

**Honesty discipline for every entry below** (checked against this
project's own established documentation standard elsewhere in this
codebase -- see e.g. ``engine.formation``'s R/N-placement docstring, or
``engine.link_budget``'s pointing-loss approximation):

* Every entry cites a real manufacturer, product name, country of
  manufacture, and at least one real, publicly reachable datasheet/catalog
  URL (``source_url``) -- nothing here is invented.
* A field is filled with the manufacturer's own published number WHENEVER
  that number's units match this schema's field directly (e.g. a
  magnetorquer's published "maximum dipole moment [A*m^2]" -> this
  schema's own ``max_dipole_a_m2`` -- no conversion needed).
* Where the real datasheet's own quantity uses different units/statistics
  than this schema's field expects (e.g. a star tracker's angular accuracy
  vs. this schema's isotropic ``noise_arcsec``, or a gyroscope's angular
  random walk [deg/root-hr] vs. Basilisk's own discrete per-tick
  ``gyro_noise_rad_s``), the value here is an EXPLICITLY LABELED
  approximation or a value DERIVED from two other real published numbers
  (shown in ``notes``, with the arithmetic/assumption stated) -- never a
  number presented as if it were the vendor's own direct figure. Where no
  real number could be found/verified for an OPTIONAL field, that field is
  simply left out (falls back to Basilisk's own module default) rather
  than guessed.
* ``itar_free_note`` is phrased per-entry at the confidence level the
  source material actually supports: a manufacturer's own explicit public
  "ITAR-free" claim is quoted as such; where no such explicit claim was
  found but the manufacturer is clearly a non-US entity manufacturing in
  Europe, the note says only that plainly (country of manufacture), with
  an explicit "verify the current export-control classification with the
  manufacturer for your own procurement" caveat -- this project makes no
  independent legal determination of export-control status for anyone's
  specific hardware/mission, and nothing here should be read as one.
* "Europe" is read geographically (as the user's own request put it), not
  strictly "EU member state" -- Ireland/Germany/Netherlands/Austria below
  are all EU; none here happen to be European-but-non-EU, but that
  wouldn't disqualify an entry either.

**Supplier-database entries.** A real user's supplier database ("Complete
market research: subsystems for 100 - 500 kg satellites, LEO/SSO, 5 - 7
years", dated 07 Oct 2026; ITAR-free mandatory, TRL >= 7 for its main
lists) supplied the second block of entries below, and updated the export
-control notes of the first block. A product from it is included only if
(1) it maps to a kind this app can simulate, (2) it has flight heritage
(the database's "Development - monitor" rows are excluded), (3) the
database does not flag it "Check / export risk", (4) the database gives
the numbers its kind needs, and (5) the database does not call it too
small or oversized for 100 - 500 kg. ``procurement_status`` quotes the
database's own status. Its values are as stated by the cited source;
"Secondary" sources (directories, press) must be verified before use.

Mirrors ``gui.sensor_actuator_editor._KIND_PARAM_SPECS``'s own kind/key
shape exactly -- :func:`validate_catalog_against_param_specs` (used by this
project's own test suite) checks that every entry's ``params`` satisfies
every required key for its ``kind``, so this catalog can never drift out of
sync with that module's own required-field list.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeviceCatalogEntry:
    kind: str  # one of schema.scenario.SUPPORTED_SENSOR_KINDS/SUPPORTED_ACTUATOR_KINDS
    manufacturer: str
    product_name: str
    country: str  # country of manufacture
    source_url: str
    itar_free_note: str
    description: str  # one or two sentences: what this real device is, flight heritage/market segment
    params: dict = field(default_factory=dict)
    notes: str = ""  # any approximation/derivation made converting a real datasheet number into this schema's units
    heritage: str = ""  # flight heritage / TRL, as stated by the source
    # Procurement status from the user's supplier database (see this
    # module's docstring), e.g. "RFI priority (ITAR-free stated)".
    procurement_status: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.manufacturer} {self.product_name} ({self.country})"


CATALOG: list[DeviceCatalogEntry] = [
    DeviceCatalogEntry(
        kind="star_tracker",
        manufacturer="Jena-Optronik",
        product_name="ASTRO APS",
        country="Germany",
        source_url="https://www.jena-optronik.de/products/star-sensors/astro-aps.html",
        itar_free_note=(
            (
            'Built in Germany by Jena-Optronik (OHB group). No ITAR statement found; verify the '
            'export classification with the manufacturer.'
        )
        ),
        description=(
            (
            'High-accuracy APS star tracker: 20 deg field of view, 1024 x 1024 detector, 10 Hz, about '
            '2 kg.'
        )
        ),
        params={
            "noise_arcsec": 8.0,
        },
        notes=(
            (
            'The datasheet gives <1 arcsec (1-sigma) across the boresight and <8 arcsec about it. The '
            'form has one isotropic value, so the worse figure, 8 arcsec, is used.'
        )
        ),
        heritage="Flight-proven (e.g. Alphasat), per the supplier database.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="imu",
        manufacturer="InnaLabs",
        product_name="ARIETIS-NS",
        country="Ireland",
        source_url="https://www.innalabs.com/arietis-ns",
        itar_free_note=(
            (
            'InnaLabs states "ITAR free... Built in Europe" (manufacturer\'s own claim). Verify the '
            'export classification with the manufacturer.'
        )
        ),
        description=(
            (
            'Radiation-tolerant 3-axis Coriolis vibratory gyroscope for LEO to GEO missions of any '
            'size.'
        )
        ),
        params={
            "gyro_noise_rad_s": 1.5e-6,
        },
        notes=(
            (
            'The datasheet gives an angular random walk of <=0.005 deg/sqrt(h), a noise density. Gyro '
            'noise is per time step, so it is converted for a 1 s step: about 1.5e-6 rad/s. For '
            'another step dt, multiply by 1/sqrt(dt). Bias instability (<=0.1 deg/h) is not modelled. '
            'Accelerometer noise is left at the default: no matching figure was found.'
        )
        ),
        heritage="InnaLabs gyros flying since 2016 (>2.5 M h on 19 satellites); ARIETIS-NS flown on CO3D (2025).",
        procurement_status="RFI priority (ITAR-free stated)",
    ),
    DeviceCatalogEntry(
        kind="coarse_sun_sensor",
        manufacturer="Hyperion Technologies",
        product_name="SS200",
        country="Netherlands",
        source_url="https://www.aac-clyde.space/what-we-do/space-products-components/adcs/ss200",
        itar_free_note=(
            (
            'Built in the Netherlands by Hyperion Technologies (AAC Clyde Space). Only a '
            'company-level ITAR-free claim was found, not one for this product; get written '
            'confirmation.'
        )        ),
        description=(
            (
            'Small, low-power digital sun sensor: 110 deg field of view, calibrated before delivery. '
            "Sun sensors don't scale with bus size, so it also suits a 200-500 kg bus."
        )
        ),
        params={
            "nHat_B": [1.0, 0.0, 0.0],
            "fov_deg": 110.0,
            "noise_std": 0.004,
        },
        notes=(
            (
            'Field of view is the datasheet value. Output noise is derived from the 0.3 deg (1-sigma) '
            'accuracy at a 45 deg sun angle: 0.707 x 0.3 deg in rad = 0.0037, rounded to 0.004. The '
            'boresight direction is a placeholder: set your own mounting.'
        )
        ),
        heritage="TRL 9, flying since 2018.",
        procurement_status="RFI - confirm ITAR in writing",
    ),
    DeviceCatalogEntry(
        kind="magnetometer",
        manufacturer="Hyperion Technologies",
        product_name="MM200",
        country="Netherlands",
        source_url="https://www.aac-clyde.space/what-we-do/space-products-components/adcs/mm200",
        itar_free_note=(
            (
            'Built in the Netherlands by Hyperion Technologies (AAC Clyde Space), which states it is '
            'ITAR free. Verify the export classification with the manufacturer.'
        )
        ),
        description=(
            (
            "Fluxgate magnetometer: +/-800 uT range, 4 cm^2 footprint, 12 g. Magnetometers don't "
            'scale with bus size, so it also suits a 200-500 kg bus.'
        )
        ),
        params={
            "noise_std_tesla": [1.18e-9, 1.18e-9, 1.18e-9],
        },
        notes=(
            (
            'The datasheet gives 1.18 nT/sqrt(Hz), a noise density. The same number is used as a '
            'per-sample noise placeholder; rescale for your sample rate if precision matters.'
        )
        ),
        heritage="CubeSat flight heritage per the manufacturer.",
        procurement_status="Not in the supplier database",
    ),
    DeviceCatalogEntry(
        kind="reaction_wheel",
        manufacturer="Collins Aerospace (Teldix)",
        product_name="RSI 04-33-60A",
        country="Germany",
        source_url="https://www.satcatalog.com/component/rsi-04-33-60a/",
        itar_free_note=(
            (
            'Built in Heidelberg, Germany, but the parent company (Collins Aerospace) is US-based. '
            "The supplier database flags it 'Check / export risk'; it is kept for existing scenarios."
        )        ),
        description=(
            (
            'Mid-size reaction wheel from the RSI family (0.04 to 68 N*m*s): 0.4 N*m*s and 33 mN*m, '
            'suited to a 200-500 kg bus. Dry mass <1.75 kg.'
        )
        ),
        params={
            "gsHat_B": [0.0, 0.0, 1.0],
            "rw_type": "custom",
            "Omega_max": 6000.0,
            "u_max": 0.033,
            "Js": 6.366e-4,
        },
        notes=(
            (
            'Max wheel speed (6,000 RPM) and max torque (33 mN*m) are datasheet values. Rotor inertia '
            'is derived: 0.4 N*m*s / 628.3 rad/s = 6.366e-4 kg*m^2. The spin axis is a placeholder: '
            'set your own mounting.'
        )
        ),
        heritage="RSI family: ~850 units on 300+ satellites.",
        procurement_status="Check / export risk",
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="ENPULSION",
        product_name="MICRO R3",
        country="Austria",
        source_url="https://www.enpulsion.com/products/micro-r3/",
        itar_free_note=(
            (
            'Built in Wiener Neustadt, Austria by ENPULSION. No ITAR statement found. The supplier '
            'database notes it is sized for 10-200 kg; a 200-500 kg bus needs a cluster.'
        )        ),
        description=(
            (
            'Integrated indium FEEP electric thruster for larger small satellites: 2.6 kg dry, 3.9 kg '
            'wet (1.3 kg propellant).'
        )
        ),
        params={
            "r_B": [1.0, 0.0, 0.0],
            "tHat_B": [1.0, 0.0, 0.0],
            "MaxThrust": 1.0e-3,
            "thruster_type": "Blank_Thruster",
            "steadyIsp": 3000.0,
        },
        notes=(
            (
            'Max thrust 1 mN is the datasheet value (range 300 uN to 1 mN). Specific impulse is '
            'adjustable from 1,500 to 4,500 s with power (30-120 W); 3,000 s is used. Total impulse '
            'is up to 50 kN*s. Basilisk has no FEEP preset, so a blank thruster model with these '
            'values is used. Location and direction are placeholders. Minimum on-time is left at the '
            'default: no figure was found.'
        )
        ),
        heritage="TRL 9 per the manufacturer; >280 FEEP units in orbit (family).",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="magnetic_torque_rod",
        manufacturer="AAC Clyde Space",
        product_name="MTQ800",
        country="Sweden/United Kingdom",
        source_url="https://www.aac-clyde.space/what-we-do/space-products-components/adcs/mtq800-10",
        itar_free_note=(
            (
            'Built by AAC Clyde Space in Sweden and Scotland. No ITAR-free statement was found for '
            'this product; get written confirmation.'
        )        ),
        description=(
            (
            'Magnetorquer set for 50-200 kg satellites: 15 A*m^2 continuous, 30 A*m^2 boost, 489 g '
            'for three rods and electronics. Check the torque budget at the top of the 200-500 kg '
            'range.'
        )
        ),
        params={
            "gtHat_B": [1.0, 0.0, 0.0],
            "max_dipole_a_m2": 15.0,
        },
        notes=(
            (
            'Max dipole is the 15 A*m^2 continuous value; the 30 A*m^2 boost mode is not modelled. '
            'The dipole axis is a placeholder. The set has three rods: add one actuator per axis, '
            'each with this value.'
        )
        ),
        heritage="TRL 9, in flight since 2020.",
        procurement_status="RFI - confirm ITAR in writing",
    ),
    # -- From the user's supplier database (07 Oct 2026) -- see this
    # module's docstring for the inclusion rule. Values are as that
    # database states them; "Secondary" sources need verifying.

    # Star trackers. noise_arcsec is a 1-sigma figure; a 3-sigma or 2-sigma
    # spec is divided down, and where only a range or two axes are given the
    # WORSE figure is used (as for ASTRO APS above).
    DeviceCatalogEntry(
        kind="star_tracker",
        manufacturer="AAC Hyperion",
        product_name="ST200",
        country="Netherlands",
        source_url="https://www.aac-clyde.space/what-we-do/space-products-components/adcs/st200",
        itar_free_note=(
            "AAC advertises ITAR-free products in general; the supplier database's audit found no "
            "statement on the ST200 product page -- confirm in writing with the manufacturer."
        ),
        description="A very small (42 g, 0.7 W) star tracker, 30 arcsec (3-sigma).",
        params={"noise_arcsec": 10.0},
        notes="noise_arcsec = 30 arcsec (3-sigma) / 3. Source level: primary (vendor).",
        heritage="TRL 9, flown since 2015.",
        procurement_status="RFI - confirm ITAR in writing",
    ),
    DeviceCatalogEntry(
        kind="star_tracker",
        manufacturer="Berlin Space Technologies",
        product_name="ST400",
        country="Germany",
        source_url="https://www.berlin-space-tech.com/st400/",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description=(
            "Microsatellite star tracker co-developed with AAC Hyperion (sold by AAC as ST400-T): "
            "5 Hz, 350 g with baffle, 5-year LEO life, 11 krad."
        ),
        params={"noise_arcsec": 10.0},
        notes=(
            "The vendor quotes 5 arcsec; AAC quotes 10 arcsec (pitch/yaw) for the same unit. The worse "
            "figure is used. Source level: primary (vendor)."
        ),
        heritage="Space heritage since 2015.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="star_tracker",
        manufacturer="Terma",
        product_name="T1",
        country="Denmark",
        source_url="https://www.satnow.com/products/star-trackers/terma/37-1195-t1-star-tracker",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="APS (1024 x 1024) star tracker, 20 deg FOV, 10 Hz; optical head 313 g, electronics 450 g.",
        params={"noise_arcsec": 10.0},
        notes="noise_arcsec = the published 10 arcsec (statistic not stated). Source level: secondary (directory).",
        heritage="Heritage per directory.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="star_tracker",
        manufacturer="Vectronic Aerospace",
        product_name="VST-41M",
        country="Germany",
        source_url="https://www.vectronic-aerospace.com/star-trackers/",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="Rad-hard CMOS star tracker for LEO/GEO/interplanetary: 4 Hz, 0.7-0.9 kg, 2.5 W, 20 krad.",
        params={"noise_arcsec": 9.0},
        notes="noise_arcsec = 18 arcsec (2-sigma, cross-axis) / 2. Source level: primary (vendor).",
        heritage="Space heritage per directory.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="star_tracker",
        manufacturer="arcsec",
        product_name="Sagitta",
        country="Belgium",
        source_url="https://satsearch.co/products/arcsec-sagitta-star-tracker",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="Compact star tracker, 270 g, ~1.3 W; ~4 months lead time.",
        params={"noise_arcsec": 10.0},
        notes="noise_arcsec = the worse end of the published 2-10 arcsec (1-sigma). Source level: secondary.",
        heritage="Heritage since 2020 (two ESA IOD CubeSats).",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="star_tracker",
        manufacturer="arcsec",
        product_name="Twinkle",
        country="Belgium",
        source_url="https://www.satnow.com/products/star-trackers/arcsec/37-1184-twinkle-star-tracker",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="Miniature star tracker (35 g, 1 W), 10 Hz, 10.6 deg FOV, for CubeSats and larger satellites.",
        params={"noise_arcsec": 30.0},
        notes=(
            "Published 3 arcsec cross-boresight, 30 arcsec about boresight; the worse (boresight) "
            "figure is used. Source level: secondary (directory)."
        ),
        heritage="Heritage per directory.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="star_tracker",
        manufacturer="DTU Space",
        product_name="micro-ASC",
        country="Denmark",
        source_url="https://www.eoportal.org/satellite-missions/formosat-5",
        itar_free_note="Danish public university supplier; no ITAR/EAR statement found (supplier database).",
        description="Multi-head star tracker (1-4 camera heads on one processing unit), radiation tolerant.",
        params={"noise_arcsec": 2.0},
        notes="noise_arcsec = the published <2 arcsec pointing accuracy. Source level: secondary (eoPortal).",
        heritage="TRL 9: FORMOSAT-5 (~525 kg, 2017), Flying Laptop (2017); >70 spacecraft since 2008.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="star_tracker",
        manufacturer="Antrix",
        product_name="Mark-3 Star Sensor (M3SS)",
        country="India",
        source_url="https://www.satnow.com/products/star-trackers/antrix-corporation-limited/37-1183-mark-3-star-sensor-m3ss-",
        itar_free_note=(
            "No ITAR/US-content statement found; Indian export licensing (SCOMET/DGFT) likely applies "
            "(supplier database) -- verify with the supplier."
        ),
        description="GEO/LEO star sensor: 8 Hz, 1024x1024 CMOS; 6.25 kg (head 2.0 kg + processor 4.25 kg), 14-24 W.",
        params={"noise_arcsec": 40.0},
        notes="noise_arcsec = the worse end of the published 10-40 arcsec. Source level: secondary (directory).",
        heritage="Space heritage per directory.",
        procurement_status="Candidate - ITAR status unknown",
    ),

    # Gyros / IMUs. gyro_noise_rad_s follows the ARIETIS-NS conversion above:
    # angular random walk [deg/sqrt(h)] -> rad/sqrt(s), for a 1 s tick.
    DeviceCatalogEntry(
        kind="imu",
        manufacturer="Safran Sensonor",
        product_name="STIM300",
        country="Norway",
        source_url="https://safran-navigation-timing.com/product/stim300/",
        itar_free_note="ITAR-free per Safran Sensonor (product-level statement, confirmed by the supplier database).",
        description=(
            "COTS MEMS IMU, radiation characterised, used in space for a decade but not space-qualified "
            "(the STIM377H is the space-grade variant)."
        ),
        params={"gyro_noise_rad_s": 4.4e-5, "gyro_saturation_rad_s": 6.98},
        notes=(
            "gyro_noise_rad_s from the published ARW 0.15 deg/sqrt(h): 0.15 * pi/180 / 60 = 4.4e-5 "
            "rad/sqrt(s), for a 1 s tick (rescale by 1/sqrt(dt)). gyro_saturation_rad_s = +/-400 deg/s. "
            "Bias instability 0.3 deg/h is not modeled. Source level: primary (vendor)."
        ),
        heritage="Used in the space segment for a decade (COTS).",
        procurement_status="RFI priority (ITAR-free stated)",
    ),

    # Sun sensors. noise_std uses the SS200 conversion above: 1-sigma angle
    # x sin(45 deg) in the cosine-law output.
    DeviceCatalogEntry(
        kind="coarse_sun_sensor",
        manufacturer="Solar MEMS",
        product_name="nanoSSOC-D60",
        country="Spain",
        source_url="https://www.cubesatshop.com/product/nanossoc-d60-digital-sun-sensor/",
        itar_free_note="ITAR-free per the manufacturer (directory-only statement per the supplier database's audit).",
        description="Digital two-axis sun sensor, +/-60 deg FOV, <0.5 deg (3-sigma); 5-6 weeks lead time.",
        params={"nHat_B": [1.0, 0.0, 0.0], "fov_deg": 120.0, "noise_std": 0.002},
        notes=(
            "fov_deg = 2 x 60 deg. noise_std = sin(45 deg) x (0.5/3 deg in rad) = 0.0021. nHat_B is a "
            "mounting placeholder. Source level: secondary (directory)."
        ),
        heritage="TRL 9, since 2016, >1,000 units delivered.",
        procurement_status="RFI priority (ITAR-free stated)",
    ),
    DeviceCatalogEntry(
        kind="coarse_sun_sensor",
        manufacturer="Jena-Optronik",
        product_name="Fine Sun Sensor",
        country="Germany",
        source_url="https://www.satnow.com/news/details/668-jena-optronik-introduces-new-sun-sensor-for-earth-observation-and-science-satellites",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="Analogue, redundant (main + redundant channel) fine sun sensor, <650 g, >13-year lifetime.",
        params={"nHat_B": [1.0, 0.0, 0.0], "fov_deg": 128.0, "noise_std": 0.0006},
        notes=(
            "fov_deg = the published 128 deg. noise_std = sin(45 deg) x (0.15/3 deg in rad) = 0.0006. "
            "Source level: secondary (directory)."
        ),
        heritage="Space-qualified; GSTB-V2, Radarsat-2, COSMO-SkyMed.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="coarse_sun_sensor",
        manufacturer="Tensor Tech",
        product_name="FSS-15M",
        country="Taiwan",
        source_url="https://satsearch.co/products/tensortech-fss-15-fine-sun-sensor",
        itar_free_note="'ITAR-free, no export control required' per satsearch (directory-only, per the supplier database).",
        description="Fine sun sensor, 0.2 deg (1-sigma), RS485; 3-6 weeks lead time.",
        params={"nHat_B": [1.0, 0.0, 0.0], "noise_std": 0.0025},
        notes=(
            "noise_std = sin(45 deg) x (0.2 deg in rad) = 0.0025. FOV not published: fov_deg is left "
            "at the default. Variant naming differs between directories. Source level: secondary."
        ),
        heritage="TRL 9, heritage since 2022.",
        procurement_status="RFI priority (ITAR-free stated)",
    ),

    # Magnetometers. These publish a 1 deg direction accuracy, not a noise
    # density: noise_std_tesla is DERIVED as tan(1 deg) x ~45,000 nT (a
    # typical LEO field) ~= 800 nT per axis -- an order-of-magnitude figure.
    DeviceCatalogEntry(
        kind="magnetometer",
        manufacturer="ZARM Technik",
        product_name="FGM-A-75",
        country="Germany",
        source_url="https://www.nasa.gov/wp-content/uploads/2024/02/5.soa-gnc-2023-final.pdf",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="High-reliability analogue 3-axis fluxgate, 0.33 kg, 0.75 W.",
        params={"noise_std_tesla": [8.0e-7, 8.0e-7, 8.0e-7], "saturation_tesla": 7.5e-5},
        notes=(
            "saturation_tesla = the published +/-75,000 nT range. noise_std_tesla derived from the 1 deg "
            "accuracy (see the comment above this group). Source level: secondary (NASA SoA report)."
        ),
        heritage="TRL 9 per the NASA small-spacecraft state-of-the-art report.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="magnetometer",
        manufacturer="NewSpace Systems",
        product_name="NMRM-Bn25o485",
        country="South Africa",
        source_url="https://www.nasa.gov/wp-content/uploads/2024/02/5.soa-gnc-2023-final.pdf",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="Small digital magnetometer, 0.085 kg, 0.75 W.",
        params={"noise_std_tesla": [8.0e-7, 8.0e-7, 8.0e-7]},
        notes=(
            "noise_std_tesla derived from the 1 deg accuracy (see the comment above this group); range "
            "not published. Source level: secondary (NASA SoA report)."
        ),
        heritage="TRL 7-9 per the NASA small-spacecraft state-of-the-art report.",
        procurement_status="Candidate - ITAR status unknown",
    ),

    # Reaction wheels. Js = published momentum / Omega_max; where the top
    # speed isn't published, 6,000 RPM is ASSUMED, which keeps the published
    # momentum capacity exact (only the wheel speed is then nominal).
    DeviceCatalogEntry(
        kind="reaction_wheel",
        manufacturer="Dragonfly Aerospace",
        product_name="RW-1Nms",
        country="South Africa",
        source_url="https://dragonflyaerospace.com/components/rw-1nms/",
        itar_free_note="ITAR-free per Dragonfly Aerospace (product-level statement, confirmed by the supplier database).",
        description="1.0 N*m*s reaction wheel, 1.0 kg, CAN/RS485, >20 krad, ABEC 7 bearings; 108 W peak.",
        params={"gsHat_B": [0.0, 0.0, 1.0], "rw_type": "custom", "Omega_max": 6000.0, "u_max": 0.039,
                "Js": 1.592e-3},
        notes=(
            "u_max = the published +/-39 mN*m (a v2 offers +/-74 mN*m). Top speed not published: "
            "Omega_max 6,000 RPM assumed, Js = 1.0 / 628.3 = 1.592e-3 kg*m^2. Source level: primary (vendor)."
        ),
        heritage="TRL 9 per the manufacturer (no missions listed).",
        procurement_status="RFI priority (ITAR-free stated)",
    ),
    DeviceCatalogEntry(
        kind="reaction_wheel",
        manufacturer="Microsat Systems Canada",
        product_name="MicroWheel 1000",
        country="Canada",
        source_url="https://satnow.com/products/reaction-wheels/microsat-systems-canada-inc/38-1203-microwheel-1000",
        itar_free_note=(
            "No ITAR statement found; the supplier database could not reach the vendor's website -- "
            "confirm the company is active and its export classification."
        ),
        description="1.1 N*m*s microsatellite wheel, 30 mN*m, 1.44 kg, <50 W peak, >7-year life.",
        params={"gsHat_B": [0.0, 0.0, 1.0], "rw_type": "custom", "Omega_max": 6000.0, "u_max": 0.030,
                "Js": 1.751e-3},
        notes=(
            "u_max = the published 30 mN*m. Top speed not published for this model: Omega_max 6,000 RPM "
            "assumed, Js = 1.1 / 628.3 = 1.751e-3 kg*m^2. Source level: secondary (eoPortal/directory)."
        ),
        heritage="TRL 9: four MicroWheel 1000 on PROBA-2 (2009).",
        procurement_status="Candidate - ITAR status unknown",
    ),
    # From the manufacturer's datasheet the user supplied ("VRW-D-6
    # Reaction Wheel", A4, 25 Apr 2024).
    DeviceCatalogEntry(
        kind="reaction_wheel",
        manufacturer="VECTRONIC Aerospace",
        product_name="VRW-D-6",
        country="Germany",
        source_url="https://www.vectronic-aerospace.com",
        itar_free_note=(
            "Designed and built in Berlin, Germany. The datasheet makes no ITAR statement -- "
            "verify the export classification with the manufacturer for your own procurement."
        ),
        description=(
            "6.0 N*m*s reaction wheel for small and medium satellites: +/-6,000 RPM, +/-50 mN*m "
            "(90 mN*m variant), 3.0 kg, 200 x 200 x 67 mm, RS422/RS485 and CAN, 45,000+ h design life."
        ),
        params={"gsHat_B": [0.0, 0.0, 1.0], "rw_type": "custom", "Omega_max": 6000.0, "u_max": 0.050,
                "Js": 9.56e-3},
        notes=(
            (
            'All values are from the datasheet: 6,000 RPM, 50 mN*m (use 0.090 N*m for the high-torque '
            'variant) and rotor inertia 9.56e-3 kg*m^2, which gives the stated 6.0 N*m*s. Power: <1.4 '
            'W idle, <14 W at full speed, <110 W at full speed and torque.'
        )
        ),
        heritage="VRW series: over 100 years of combined in-orbit operation (manufacturer).",
        procurement_status="RFI - confirm ITAR in writing",
    ),

    # Magnetorquers.
    DeviceCatalogEntry(
        kind="magnetic_torque_rod",
        manufacturer="Space Inventor",
        product_name="MT-6-P4",
        country="Denmark",
        source_url="https://satsearch.co/products/space-inventor-mt-2-p4",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description=(
            "Magnetorquer with integrated controller and redundant windings, 300 mm x 17 mm, 300 mW, "
            "redundant CAN (CSP 2.0)."
        ),
        params={"gtHat_B": [1.0, 0.0, 0.0], "max_dipole_a_m2": 6.0},
        notes="max_dipole_a_m2 = the published 6 A*m^2. gtHat_B is a mounting placeholder. Source level: secondary.",
        heritage="TRL 9 per directory.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="magnetic_torque_rod",
        manufacturer="Space Inventor",
        product_name="MT-2-P4",
        country="Denmark",
        source_url="https://satsearch.co/products/space-inventor-mt-2-p4",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="Smaller variant of the MT-6-P4: 200 mm, 375 g, 250 mW.",
        params={"gtHat_B": [1.0, 0.0, 0.0], "max_dipole_a_m2": 2.0},
        notes="max_dipole_a_m2 = the published 2 A*m^2. Source level: secondary (directory).",
        heritage="TRL 9 per directory.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="magnetic_torque_rod",
        manufacturer="Strasspace",
        product_name="Micro Magnetic Torque Rod",
        country="France",
        source_url="https://satnow.com/products/magnetorquers/strasspace/41-1231-micro-magnetic-torque-rods",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="Torque rods for nano- and microsatellites, 5-15 A*m^2, 0.75-3.5 W, 250 x 60 x 30 mm.",
        params={"gtHat_B": [1.0, 0.0, 0.0], "max_dipole_a_m2": 15.0},
        notes="max_dipole_a_m2 = the top of the published 5-15 A*m^2 range. Source level: secondary (directory).",
        heritage="Space heritage per directory.",
        procurement_status="Candidate - ITAR status unknown",
    ),

    # Thrusters. MaxThrust/steadyIsp are the published figures; where Isp is
    # not published, steadyIsp is left unset (Basilisk default), which only
    # affects propellant use. r_B/tHat_B are mounting placeholders.
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="Dawn Aerospace",
        product_name="B20",
        country="Netherlands/New Zealand",
        source_url="https://www.dawnaerospace.com/thrusters",
        itar_free_note="'All our systems are ITAR-free' per Dawn Aerospace (confirmed by the supplier database).",
        description=(
            "Nitrous oxide / propene bipropellant thruster, spark ignition, self-pressurising, >11,000 "
            "restarts; SatDrive systems for 30 kg to >500 kg."
        ),
        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 18.0,
                "thruster_type": "Blank_Thruster"},
        notes="MaxThrust = the top of the published 6.5-18 N (pressure dependent). Isp not published. Source level: primary.",
        heritage="In orbit since Jan 2021 (D-Orbit ION); >160 B1/B20 launched.",
        procurement_status="RFI priority (ITAR-free stated)",
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="Liftero",
        product_name="BOOSTER M1",
        country="Poland",
        source_url="https://liftero.com/booster",
        itar_free_note="'Our propulsion systems are ITAR-free' per Liftero (confirmed by the supplier database).",
        description="N2O / ethane bipropellant system (up to 14 thrusters) for 30-500 kg; 6-9 months lead time.",
        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 1.0,
                "thruster_type": "Blank_Thruster", "steadyIsp": 290.0},
        notes=(
            "Thrusters span 0.54-30.5 N (M1/M5/M20); MaxThrust 1 N is the M1 class (verify the exact "
            "figure). steadyIsp = the vendor's '>290 s'. Source level: primary (vendor)."
        ),
        heritage="Flown on a SpaceX rideshare (March 2025).",
        procurement_status="RFI priority (ITAR-free stated)",
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="Arkadia Space",
        product_name="TRITON 5 N",
        country="Spain",
        source_url="https://arkadiaspace.com/arkadia-space-demonstrates-full-in-orbit-capabilities-of-its-green-propulsion-system-based-on-hydrogen-peroxide/",
        itar_free_note=(
            "The vendor calls its propellants ITAR-free; the supplier-level ITAR-free claim comes from a "
            "customer (Reflex Aerospace) -- confirm in writing."
        ),
        description="Hydrogen-peroxide monopropellant thruster (DARK system); thrusters/tanks in <6 months.",
        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 5.0,
                "thruster_type": "Blank_Thruster"},
        notes="MaxThrust = the published 5 N. Isp not published. Source level: primary (vendor).",
        heritage="DARK flown on D-Orbit ION (Transporter-13, March 2025); TRL 8-9 per Arkadia.",
        procurement_status="RFI - confirm ITAR in writing",
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="Nammo",
        product_name="MHT-1N",
        country="United Kingdom",
        source_url="https://www.nammo.com/products/space/space-propulsion-thrusters-and-engines/mht-1n/",
        itar_free_note="Made by Nammo (UK) Ltd, Westcott; Norwegian parent. No ITAR statement found (supplier database).",
        description="Hydrazine monopropellant thruster, <0.45 kg, >42 kg throughput demonstrated.",
        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 1.38,
                "thruster_type": "Blank_Thruster", "steadyIsp": 228.0},
        notes="MaxThrust = 1.38 N at 24 bara; steadyIsp = 228 s. Source level: primary (vendor).",
        heritage="First flight on Telesat LEO-1 (Jan 2018); in ESA qualification for NeoSat.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="Nammo",
        product_name="SVT01 cold gas thruster",
        country="United Kingdom",
        source_url="https://www.nammo.com/products/space/space-propulsion-thrusters-and-engines/cold-gas-thruster/",
        itar_free_note="Made by Nammo Cheltenham (UK). No ITAR statement found (supplier database).",
        description="Cold gas thruster, 60 g, <5 ms response, 1.5 M cycles; >15 years in production.",
        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 0.1,
                "thruster_type": "Blank_Thruster", "steadyIsp": 72.0},
        notes="MaxThrust = the top of the published 10-100 mN; steadyIsp = 72 s with GN2 (47 s CF4, 30 s GXe). Source level: primary.",
        heritage="CryoSat 1 & 2, TanDEM-X, Swarm, GRACE-FO, Electra.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="AST Advanced Space Technologies",
        product_name="Cold Gas Thruster (CGT)",
        country="Germany",
        source_url="https://satcatalog.com/component/cgt",
        itar_free_note="German company, no US parent identified; no ITAR statement found (supplier database).",
        description="Precision cold gas thruster, 43 g dry, >1e9 actuations; thrust linear with inlet pressure.",
        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 0.042,
                "thruster_type": "Blank_Thruster", "steadyIsp": 69.0, "MinOnTime": 0.0026},
        notes=(
            "MaxThrust = 42 mN; steadyIsp = the published '>69 s'. MinOnTime = impulse bit / thrust = "
            "110 uN*s / 42 mN = 2.6 ms. Source level: secondary (SatCatalog)."
        ),
        heritage="Flight heritage (qualified on FORMOSAT-5 per SatCatalog); in production.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="ArianeGroup",
        product_name="1 N hydrazine thruster",
        country="Germany",
        source_url="https://space-propulsion.com/spacecraft-propulsion/hydrazine-thrusters/1n-hydrazine-thruster.html",
        itar_free_note=(
            "No ITAR statement; the valve supplier is not identified, and ArianeGroup's 10 N thruster "
            "uses a US valve option -- confirm the valve origin (supplier database)."
        ),
        description="Monopropellant hydrazine thruster, 290 g incl. valve, redundant catalyst-bed heaters.",
        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 1.1,
                "thruster_type": "Blank_Thruster", "steadyIsp": 220.0},
        notes="MaxThrust = the top of the published 0.32-1.1 N; steadyIsp = the nominal 220 s (200-223 s). Source level: primary.",
        heritage=">500 units in space; Globalstar, Jason, Sentinel, COSMO-SkyMed (TRL 9).",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="Rafael",
        product_name="1 N hydrazine thruster",
        country="Israel",
        source_url="https://blog.satsearch.co/2023-05-05-chemical-propulsion-systems-for-satellites",
        itar_free_note=(
            "'Free of any ITAR restrictions' per satsearch only (supplier database); Israeli defence "
            "prime -- confirm export licensing in writing."
        ),
        description="Hydrazine monopropellant thruster (a 5 N version also exists).",
        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 1.0,
                "thruster_type": "Blank_Thruster"},
        notes="MaxThrust = 1 N. Isp not published. Source level: secondary (directory).",
        heritage="Flight heritage; qualified for the OFEQ programme per directory.",
        procurement_status="RFI priority (ITAR-free stated)",
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="IHI Aerospace",
        product_name="BT-6",
        country="Japan",
        source_url="https://www.ihi.co.jp/ia/en/products/space/satprop/index.html",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="Bipropellant thruster (hydrazine/NTO or MMH/MON-3); >400 bipropellant thrusters delivered.",
        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 21.5,
                "thruster_type": "Blank_Thruster"},
        notes="MaxThrust = the published 21.5 N. Isp not published. Source level: primary (vendor).",
        heritage="Listed as flight proven.",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="Exotrail",
        product_name="ExoMG micro",
        country="France",
        source_url="https://cdn.exotrail.com/img/Small_Sat_08-2020/5efb4caf37835_ExoMG.pdf",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="Hall-effect thruster for 10-250 kg, 150 W; a cluster version reaches 35 mN at 800 W.",
        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 0.007,
                "thruster_type": "Blank_Thruster"},
        notes="MaxThrust = the published 7 mN. Isp not published. Source level: primary (vendor).",
        heritage="Qualified; first flight system delivered 2019, CubeSat in-orbit demo (Nov 2020).",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="SETS",
        product_name="SPS-25",
        country="Ukraine",
        source_url="https://sets.space/sps25/",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="Hall-thruster system (ST-25, xenon feed, PPU) for up to 500 kg; 120-275 W, up to 75 kN*s.",
        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 0.014,
                "thruster_type": "Blank_Thruster"},
        notes="MaxThrust = the published 'up to 14 mN'. Isp not published. Source level: primary (vendor).",
        heritage="In-orbit test on EOS SAT-1 (2023).",
        procurement_status="Candidate - ITAR status unknown",
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="T4i",
        product_name="REGULUS-50",
        country="Italy",
        source_url="https://www.satnow.com/products/thrusters/t4i-technology-for-propulsion-and-innovation/36-1178-regulus-50",
        itar_free_note="No ITAR statement found (supplier database); verify with the manufacturer.",
        description="Iodine RF plasma thruster, 30-60 W, 2.5 kg; for drag compensation, VLEO, phasing, deorbit.",
        params={"r_B": [1.0, 0.0, 0.0], "tHat_B": [1.0, 0.0, 0.0], "MaxThrust": 6.5e-4,
                "thruster_type": "Blank_Thruster", "steadyIsp": 650.0},
        notes="MaxThrust = the top of the published 0.25-0.65 mN; steadyIsp = 'up to 650 s'. Source level: secondary.",
        heritage="In-orbit validation on UniSat-7 (2021); listed as space-qualified.",
        procurement_status="Candidate - ITAR status unknown",
    ),
]


def catalog_entries_for_kind(kind: str) -> list[DeviceCatalogEntry]:
    """Every :data:`CATALOG` entry for one sensor/actuator ``kind``, in
    catalog order. Empty (not an error) for a kind with no catalog entry
    yet -- :mod:`gui.sensor_actuator_editor` falls back to the ordinary
    custom-params editor in that case.
    """
    return [entry for entry in CATALOG if entry.kind == kind]
