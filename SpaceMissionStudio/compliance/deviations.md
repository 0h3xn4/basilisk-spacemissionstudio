# Deviations

Requirements the tool does not meet by decision, with the reason. A
deviation becomes effective only when the customer / responsible engineer
accepts it (ECSS tailoring authority); the user's decisions of 2026-10-08
(D1-D4, `PROGRESS.md`) select these deviations, the **signature** below is a
human action (H08 in `human_actions.md`).

Status: **selected by the user 2026-10-08; justification drafted; awaiting
signature.** Figures marked *(to confirm)* were not checked against a
supplied document and must be confirmed by the signatory.

| # | Requirement(s) | Deviation | Justification | Decision |
|---|---|---|---|---|
| D-01 | ECSS-E-ST-10-04C 6.2.2a-d, 6.2.3c, 7.2.1.2b-d (via R07) | Solar and geomagnetic activity are taken from observed indices (CelesTrak SW-All, bundled) and NASA MSFC predictions at the 95th or 50th percentile, as ESA AD10 (EOP-FM/2024-07-177 v3.0) Sec. 5.9 prescribes, instead of the reference values of Tables 6-3, 6-4 and A-1. | The project's applicable guideline AD10 requires MSFC percentile predictions; Tables 6-3/6-4 are rounded reference values of solar cycle 23 and Table A-1 is cycle 23 itself. The user requires real data and the AD10 approach for drag ("conservative" = MSFC 95th percentile). | D1 (a) |
| D-02 | ECSS-E-ST-10-04C 7.2.2a | No thermospheric wind model: the atmosphere co-rotates with the Earth. | Basilisk 2.12 has no wind model (B7). Thermospheric winds change the relative velocity by some 100 m/s against ~7.5 km/s, a drag effect of a few percent *(to confirm)*, below the drag-coefficient uncertainty used for budgets (AD10 margins). | D3 |
| D-03 | ECSS-E-ST-10-04C 4.2.2b (tides part) | No solid-Earth or ocean tides. | Basilisk 2.12 has no tide model (B4). Tidal accelerations in LEO are of order 1e-7 m/s^2 *(to confirm, e.g. Montenbruck & Gill, Satellite Orbits, Fig. 3.1)*, well below drag for the tool's mission-analysis use. Earth orientation itself is IERS-based (R04). | D3 |
| D-04 | ECSS-E-ST-10-04C 5.2.1a, 5.2.1.1a, 5.3a (via R08) | The internal geomagnetic field is WMM2025 (Basilisk magneticFieldWMM), not IGRF-12. | IGRF-12 (2015) predicts only to 2020, so for the tool's 2025+ epochs it is extrapolated; WMM2025 is a current main-field model. Basilisk 2.12 has no IGRF (B5). | D2 (a) |
| D-05 | ECSS-E-ST-10-04C 5.2.2a | No external (magnetospheric) field model. | The internal field dominates in LEO for magnetometer and torque-rod sizing; Basilisk has no external model (B6). | D3 |
| D-06 | ECSS-E-ST-10-04C 6.2.1c | The Basilisk sensorThermal model radiates to a 0 K sink, not 3 K. | (3 K / T)^4 is about 1e-8 of the radiated power at 300 K. The module's solar constant and Stefan-Boltzmann value are corrected by R06. | D3 |
| D-07 | ECSS-E-ST-10-04C 4.2.2d | Planetary GM values are Basilisk's (Earth 398600.4415 km^3/s^2 from GGM03S; others from de-403-masses.tpc), not checked against IERS TN36. | IERS TN36 was not supplied and iers.org could not be reached (2026-10-08). Expected relative differences are of order 1e-9 to 1e-8 *(to confirm against TN36)*. Supplying TN36 (H08) allows the values to be set. | D4 |

Deviation candidate D-08 of `gap_analysis.md` (process items not executed)
is not a deviation the tool can take: each such item is a human action in
`human_actions.md`; whether to waive any of them is the customer's decision.

## Signature

| Role | Name | Date | Decision |
|---|---|---|---|
| Responsible engineer / customer | | | |
