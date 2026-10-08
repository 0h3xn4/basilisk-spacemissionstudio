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
| D-07 | ECSS-E-ST-10-04C 4.2.2d | Planetary GM values are Basilisk's: Earth 398600.436 km^3/s^2 (BODY399_GM of de-403-masses.tpc, also Basilisk's MU_EARTH), the other bodies from the same file; not checked against IERS TN36. The GGM03S field's coefficients are normalised with 398600.4415 km^3/s^2 (its file header), so with spherical harmonics the two differ by 1.4e-8. | IERS TN36 was not supplied and iers.org could not be reached (2026-10-08). Effect measured in Phase 3 (validation V-04): 1.4e-8 in GM moves a 400 km orbit about 18 m along-track per day for the same initial state; the difference to TN36 is unknown until TN36 is supplied (H08). An earlier draft of this row gave the Earth value as 398600.4415; that was wrong and is corrected here. | D4 |

| D-08 | ECSS-E-ST-40C 5.2.5a, 5.3.3, 5.3.4, 5.3.5, 5.4.2.4a, 5.4.4a, 5.5.2.10a, 5.6.3.4a, 5.6.4.4a, 5.7.3, 5.11.5 (the review requirements of H01) | No reviews (SRR, PDR, CDR, TRR, QR, AR) are held. The documents in `docs/` stay drafts, accepted by no review. | The user's decision for this single-person tool (2026-10-08, decision 7). The reviews' purpose, an independent check of requirements, design and results, is not replaced: the requirements stay open, and the independent code review (H06) is a separate item. A reviewer may be named later. | User, 2026-10-08 |
| D-09 | ECSS-Q-ST-80C 5.1.5 (training plan, training records, security training) and 5.7 (process assessment and improvement) | No training plan or records are kept, and no process assessment is made. | The user's decision for this single-person tool (2026-10-08, decision 8). | User, 2026-10-08 |
| D-10 | ECSS-E-ST-40C 5.11.2a, 5.11.2b (software security management plan) | No security management plan is written. The security analysis (`docs/security_analysis.md`) and its treatments stand without one. | The user's decision at security assurance level low (D8; 2026-10-08, decision 8). The security manager (5.11.2c) is not waived: the role is open (H02). | User, 2026-10-08 |
| D-11 | ECSS-E-ST-40C 5.2 (customer requirements: SSS, IRD, installation, acceptance and validation requirements), 5.6.4 (validation against the requirements baseline), 5.8.3.1a, Annexes B and C; ECSS-Q-ST-80C 6.3.1 | No customer requirements baseline exists. The SRS, derived from the tool as built, is the only specification; validation is against it (5.6.3) only. | The user's decision (2026-10-08, decision 9): the user is customer and supplier of this tool. | User, 2026-10-08 |
| D-12 | ECSS-E-ST-40C 5.9 (operation support), ECSS-Q-ST-80C 5.3 (risk management, critical-item control), the change board of configuration control | No formal operation support, risk process or change board. The user approves changes and CI gates them; technical risks are logged as findings; support is best effort. | The user's decision for this single-person tool (2026-10-08, decision 11). | User, 2026-10-08 |
| D-13 | ECSS-E-ST-40C 5.7.2.1b (secure delivery), signing part | Releases are tagged and checksummed but not signed. | The user's decision (2026-10-08, decision 11): checksums cover accidental corruption; no signing key is kept. | User, 2026-10-08 |

The other process items not executed (deviation candidate D-08 of
`gap_analysis.md`) are human actions in `human_actions.md`; the reviews,
training, process assessment, the security management plan, the customer
baseline, the formal change board, risk process and operation support, and
release signing have been waived so far. Waiving any other item is the customer's
decision.

## Signature

| Role | Name | Date | Decision |
|---|---|---|---|
| Responsible engineer / customer | | | |
