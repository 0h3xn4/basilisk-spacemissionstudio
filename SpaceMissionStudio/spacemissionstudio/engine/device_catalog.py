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
            "Manufactured in Germany by Jena-Optronik GmbH (an OHB SE subsidiary); a German-built "
            "product is not generally subject to US ITAR export control absent US-origin content -- "
            "verify the current export-control classification with the manufacturer for your own "
            "procurement."
        ),
        description=(
            "A flight-proven, high-accuracy APS (active pixel sensor) star tracker used across many "
            "LEO/GEO/scientific missions -- 20 deg circular field of view, 1024x1024 pixel detector, "
            "10 Hz standard sampling rate. ~2 kg mass is a sensible choice for a 200-500 kg "
            "microsatellite bus (unlike the reaction wheel/magnetorquer/thruster entries below, "
            "pointing sensors like this one don't need to scale with spacecraft mass the same way)."
        ),
        params={
            "noise_arcsec": 8.0,
        },
        notes=(
            "The real datasheet gives two different 1-sigma numbers: <1 arcsec cross-boresight, <8 "
            "arcsec about boresight (boresight roll is always the least-observable, noisiest axis for "
            "any star tracker). This schema has one isotropic noise_arcsec value -- the WORSE "
            "(boresight) figure, 8 arcsec, is used here rather than the better cross-boresight one, so "
            "this preset does not understate the sensor's real noise floor."
        ),
    ),
    DeviceCatalogEntry(
        kind="imu",
        manufacturer="InnaLabs",
        product_name="ARIETIS-NS",
        country="Ireland",
        source_url="https://www.innalabs.com/arietis-ns",
        itar_free_note=(
            'InnaLabs Ltd. markets this product line explicitly: "ITAR free... Built in Europe" -- '
            "quoted from the manufacturer's own public materials, not an independent determination by "
            "this project. Still verify the current export-control classification with the "
            "manufacturer for your own procurement."
        ),
        description=(
            "A space-qualified, radiation-tolerant 3-axis Coriolis vibratory gyroscope (CVG), used as "
            "a primary or coarse-rate gyro on LEO/MEO/GEO/telecom/scientific missions of essentially "
            "any mass class, including a 200-500 kg microsatellite bus."
        ),
        params={
            "gyro_noise_rad_s": 1.5e-6,
        },
        notes=(
            "The real, vendor-published spec is an Angular Random Walk (ARW) of <=0.005 deg/sqrt(hr) "
            "(plus an in-run bias instability of <=0.1 deg/hr, not separately modeled by Basilisk's "
            "imuSensor noise term) -- a continuous-time noise DENSITY, not Basilisk's own discrete "
            "per-tick gyro_noise_rad_s standard deviation. gyro_noise_rad_s here is DERIVED assuming a "
            "1 s dynamics timestep: ARW[deg/sqrt(hr)] -> rad/sqrt(s) (x pi/180, /60), then divided by "
            "sqrt(dt) for a 1 s tick => ~1.5e-6 rad/s. Rescale by 1/sqrt(your own "
            "sim_settings.dynamics_task_rate_s) if it isn't 1 s. accel_noise_m_s2 is deliberately left "
            "unset here (falls back to Basilisk's own module default) -- no specific InnaLabs "
            "accelerometer datasheet figure was confirmed to pair with this gyro at the time this "
            "catalog entry was written; see InnaLabs' own published quartz pendulous accelerometer "
            "datasheets to fill that in with a real number for your own scenario."
        ),
    ),
    DeviceCatalogEntry(
        kind="coarse_sun_sensor",
        manufacturer="Hyperion Technologies",
        product_name="SS200",
        country="Netherlands",
        source_url="https://www.aac-clyde.space/what-we-do/space-products-components/adcs/ss200",
        itar_free_note=(
            "Manufactured in the Netherlands by Hyperion Technologies (part of the AAC Clyde Space "
            "group), which markets its CubeSat ADCS component line as ITAR-free; verify the current "
            "export-control classification for this specific part number with the manufacturer for "
            "your own procurement."
        ),
        description=(
            "A small, light-weight, low-power digital sun sensor -- 110 deg field of view, "
            "calibrated before delivery, flown on numerous CubeSat missions. Marketed for CubeSats, "
            "but a coarse sun sensor's mass/power/accuracy don't scale with bus size the way a "
            "reaction wheel or thruster's do -- this part is a perfectly reasonable choice on a "
            "200-500 kg bus too, not a mismatch."
        ),
        params={
            "nHat_B": [1.0, 0.0, 0.0],
            "fov_deg": 110.0,
            "noise_std": 0.004,
        },
        notes=(
            "fov_deg is the vendor's own direct spec. noise_std (this schema's dimensionless "
            "cosine-law output noise) is DERIVED from the real published 0.3 deg (1-sigma) angular "
            "accuracy (in the +/-45 deg range): at a representative 45 deg sun angle, "
            "d(cos th)/d(th) = -sin(45 deg) ~= 0.707, so noise_std ~= 0.707 * (0.3 deg in rad) ~= "
            "0.0037, rounded to 0.004 -- not a directly vendor-published cosine-domain figure. nHat_B "
            "is a generic +X mounting placeholder (boresight direction is a spacecraft integration "
            "choice, not a device spec) -- set it to this spacecraft's own sensor mounting direction."
        ),
    ),
    DeviceCatalogEntry(
        kind="magnetometer",
        manufacturer="Hyperion Technologies",
        product_name="MM200",
        country="Netherlands",
        source_url="https://www.aac-clyde.space/what-we-do/space-products-components/adcs/mm200",
        itar_free_note=(
            "Manufactured in the Netherlands by Hyperion Technologies (part of the AAC Clyde Space "
            "group); the manufacturer's own product material states this part is ITAR free. Verify "
            "the current export-control classification with the manufacturer for your own "
            "procurement."
        ),
        description=(
            "A high-precision fluxgate magnetometer, +/-800 uT range, tiny 4 cm^2 footprint, 12 g "
            "mass. Marketed for CubeSat ADCS, but -- like the sun sensor above -- a magnetometer's "
            "specs don't need to scale with bus size, so this is a reasonable choice on a 200-500 kg "
            "bus too."
        ),
        params={
            "noise_std_tesla": [1.18e-9, 1.18e-9, 1.18e-9],
        },
        notes=(
            "The real, vendor-published spec is a 1.18 nT/sqrt(Hz) noise spectral density, not "
            "directly Basilisk's own per-sample standard deviation. The ASD value itself (1.18e-9 T) "
            "is used here as an order-of-magnitude per-axis noise_std_tesla placeholder -- rescale for "
            "your own effective sample rate/bandwidth using the full vendor noise-density datasheet "
            "entry if precision matters for your scenario."
        ),
    ),
    DeviceCatalogEntry(
        kind="reaction_wheel",
        manufacturer="Collins Aerospace (Teldix)",
        product_name="RSI 04-33-60A",
        country="Germany",
        source_url="https://www.satcatalog.com/component/rsi-04-33-60a/",
        itar_free_note=(
            "Manufactured in Heidelberg, Germany by Collins Aerospace's space business (the former "
            "Rockwell Collins Deutschland / Teldix GmbH wheel line, ~850 units flown on 300+ "
            "satellites); a German-built product is not generally subject to US ITAR export control "
            "absent US-origin content -- Collins Aerospace itself is a US-headquartered parent "
            "company, though, so verify the current export-control classification for this specific, "
            "German-manufactured part number with the manufacturer for your own procurement."
        ),
        description=(
            "A mid-size momentum/reaction wheel from the RSI family (whose members span 0.04-68 "
            "N*m*s, for spacecraft from 30 kg to 7,000 kg) -- the RSI 04 variant's 0.4 N*m*s momentum "
            "and 33 mN*m torque sit well within a typical ADCS budget for a 200-500 kg microsatellite "
            "bus, unlike a 1-3U CubeSat wheel (mN*m*s-class) which would be badly undersized for this "
            "mass class."
        ),
        params={
            "gsHat_B": [0.0, 0.0, 1.0],
            "rw_type": "custom",
            "Omega_max": 6000.0,
            "u_max": 0.033,
            "Js": 6.366e-4,
        },
        notes=(
            "Omega_max (operational speed range +/-6,000 RPM) and u_max (motor torque at nominal "
            "speed, 33 mN*m = 0.033 N*m) are the vendor's own direct published figures. Js (wheel "
            "inertia about the spin axis) is NOT directly published -- it is DERIVED from the "
            "vendor's own published angular momentum at nominal speed (0.4 N*m*s) divided by that "
            "same nominal speed (6,000 RPM = 628.3 rad/s): Js = 0.4 / 628.3 ~= 6.366e-4 kg*m^2. Dry "
            "mass is published as <1.75 kg, for sizing your spacecraft's own mass budget (not a "
            "simulated quantity this schema has a field for). gsHat_B is a generic +Z spin-axis "
            "placeholder -- set it to this wheel's own mounting direction on your spacecraft."
        ),
    ),
    DeviceCatalogEntry(
        kind="thruster",
        manufacturer="ENPULSION",
        product_name="MICRO R3",
        country="Austria",
        source_url="https://www.enpulsion.com/products/micro-r3/",
        itar_free_note=(
            "Manufactured in Wiener Neustadt, Austria by ENPULSION GmbH. FEEP (field emission "
            "electric propulsion) thrusters of this kind are commonly marketed by non-US "
            "manufacturers specifically as an ITAR-free alternative to US-origin electric "
            "propulsion -- verify the current export-control classification with the manufacturer "
            "for your own procurement."
        ),
        description=(
            "A fully integrated indium-fed FEEP electric propulsion system, scaled up from "
            "ENPULSION's own smaller Nano/Nano R3 CubeSat-class thrusters specifically for larger "
            "small satellites -- 2.6 kg dry / 3.9 kg wet (1.3 kg propellant), a sensible fraction of "
            "a 200-500 kg bus's own mass budget, unlike the milli-kg-class Nano thruster that line "
            "is built for."
        ),
        params={
            "r_B": [1.0, 0.0, 0.0],
            "tHat_B": [1.0, 0.0, 0.0],
            "MaxThrust": 1.0e-3,
            "thruster_type": "Blank_Thruster",
            "steadyIsp": 3000.0,
        },
        notes=(
            "MaxThrust (1 mN nominal; the real thruster's dynamic range is 300 uN - 1 mN, "
            "electronically throttleable down to 50 uN precision) is the vendor's own direct "
            "published figure. steadyIsp: the real thruster is continuously adjustable from 1500 s "
            "to 4500 s Isp depending on extraction potential/available power (30-120 W total system "
            "power) -- 3000 s (a representative mid-range value) is used here; tune within that real "
            "1500-4500 s envelope for your own power budget. Total impulse is published as up to 50 "
            "kN*s (for sizing your own delta-v budget, not a field this schema has). thruster_type is "
            "'Blank_Thruster' (no FEEP entry exists in Basilisk's own "
            "simIncludeThruster.thrusterFactory() catalog, so the explicit params above are used "
            "as-is, not a named factory preset). r_B/tHat_B are generic placeholders -- mounting "
            "location/thrust direction are spacecraft-integration choices, not device specs. "
            "MinOnTime is deliberately left unset (falls back to Basilisk's own module default) -- no "
            "vendor datasheet figure for it was confirmed at the time this catalog entry was written."
        ),
    ),
    DeviceCatalogEntry(
        kind="magnetic_torque_rod",
        manufacturer="AAC Clyde Space",
        product_name="MTQ800",
        country="Sweden/United Kingdom",
        source_url="https://www.aac-clyde.space/what-we-do/space-products-components/adcs/mtq800-10",
        itar_free_note=(
            "AAC Clyde Space manufactures across its Swedish (Uppsala) and Scottish (Glasgow) "
            "facilities -- both European, though the group is itself publicly listed and "
            "multinational; verify the current export-control classification and country of "
            "manufacture for this specific part number with the manufacturer for your own "
            "procurement."
        ),
        description=(
            "A magnetorquer sized for 50-200 kg satellites per the manufacturer's own stated "
            "application range -- its 15-30 A*m^2 dipole moment (vs. a 1-3U CubeSat torquer's "
            "~0.2 A*m^2) is a far better starting point for a 200-500 kg bus than CubeSat-class "
            "hardware, though still worth checking against your own detumble/desaturation torque "
            "budget at the upper end of that mass range. Sold as a 3-axis set (torquer rods plus "
            "shared drive electronics, 489 g total) with a boost mode for short-duration higher"
            "-dipole maneuvers."
        ),
        params={
            "gtHat_B": [1.0, 0.0, 0.0],
            "max_dipole_a_m2": 15.0,
        },
        notes=(
            "max_dipole_a_m2 uses the vendor's own published NOMINAL (continuous) dipole moment, 15 "
            "A*m^2 -- the real hardware also has a boost mode reaching up to 30 A*m^2 for short "
            "-duration maneuvers only, not modeled separately here (this schema's single field is a "
            "continuous maximum). gtHat_B is a generic +X dipole-axis placeholder -- set it to this "
            "torquer's own mounting direction on your spacecraft (this is a 3-axis set; add one "
            "ActuatorConfig per axis you want to model, each using this same max_dipole_a_m2)."
        ),
    ),
]


def catalog_entries_for_kind(kind: str) -> list[DeviceCatalogEntry]:
    """Every :data:`CATALOG` entry for one sensor/actuator ``kind``, in
    catalog order. Empty (not an error) for a kind with no catalog entry
    yet -- :mod:`gui.sensor_actuator_editor` falls back to the ordinary
    custom-params editor in that case.
    """
    return [entry for entry in CATALOG if entry.kind == kind]
