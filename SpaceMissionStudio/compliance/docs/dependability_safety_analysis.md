# SpaceMissionStudio: Software Dependability and Safety Analysis

Document: SMS-SDSA, issue 1 (draft for approval), 2026-10-08. Human action H04.

**Status:** drafted by the supplier for the user's approval (decision 10,
2026-10-08).
- No DRD for this analysis appears in the supplied documents. Its contents
  follow ECSS-Q-ST-80C 6.2.2 and 6.2.3.
- The standards that define the severity of system functions,
  ECSS-Q-ST-30 and ECSS-Q-ST-40, were not supplied (decision 3, H12). The
  classification below therefore rests on the user's judgement, not on a
  system-level analysis.

## 1 Classification

**Category: C** (decision 1; signed off by the user, decision 10).

**Rationale** (ECSS-Q-ST-80C Table D-1, as far as it can be applied
without ECSS-Q-ST-30/40):
- SpaceMissionStudio is a ground mission-analysis tool. It commands no
  spacecraft and takes no part in operations.
- Its results feed mission design: orbits, propellant budgets, lifetime
  and disposal, passes and link margins.
- **Worst credible failure:** a plausible but wrong result that leads a
  mission design astray, for example a propellant budget that is too small,
  or a re-entry date that is too late.
- **Compensating provisions:** for any decision that matters, results are
  normally checked by other means (other tools, reviews, margins such as
  AD10's). That would place the tool in category C, or in D if its
  functions are judged category IV. The user chose C.

**Consequence:** ECSS-Q-ST-80C 3.2.8 defines critical software as software
of category A, B or C. **The whole tool is therefore critical software**,
and 6.2.3 applies to all of it (section 4). No component is classified
lower: the tool is not partitioned into components of different
categories.

## 2 Method

**Method:** a functional failure-mode and effects analysis at the level of
the SRS functions (ECSS-Q-ST-80C 6.2.2.3a).

For each failure mode, the analysis lists:
- its effect on the user's results;
- how it would be detected;
- the safeguards that exist, with their evidence;
- the residual risk.

There is no system-level analysis to start from (6.2.2.2a), and the
methods have not been agreed with a customer (6.2.2.3b): the user is
customer and supplier.

## 3 Failure modes

| # | Failure mode | Effect | Safeguards in place (evidence) | Residual |
|---|---|---|---|---|
| FM-01 | Orbit propagation silently wrong (a model or integration defect, here or in Basilisk) | Wrong positions, passes, budgets, lifetimes | Validation against GMAT, IERS and SOFA, V-01 to V-08 (SVR). Two Basilisk defects found and corrected (F-01, F-07). Basilisk pinned and checked at start-up. Energy and momentum drift warnings for point-mass runs (`results.conservation_drift_warnings`). Full regression suite in CI. | Configurations outside the validation cases (attitude, power, thermal, mission sequences) rest on tests, not external references; the 1.6 % drag residual is unexplained |
| FM-02 | Earth orientation inaccurate (no IERS files) | Gravity-field and ground-station errors, about 160 m/day | Warning in the run (F-06; `tests/test_frames.py`); frames and data files recorded in the provenance | The user ignores the warning |
| FM-03 | Time scale wrong (a leap second after `naif0012.tls`/ERFA's table) | Epochs 1 s off after the new leap second | ERFA and SPICE cross-checked (V-01); the SMP has the maintenance step | No warning when a run passes a leap second unknown to the tables |
| FM-04 | Space-weather data wrong, missing or out of date | Wrong drag: lifetimes and budgets | Real data only (bundled CelesTrak and MSFC). A run outside the data is refused, naming the day. Coverage and format checks. SHA-256 in the provenance. MSFC percentile chosen by the user. | Forecast uncertainty is inherent; the user picks the percentile |
| FM-05 | Wrong input: units, frame, epoch or element type confused | Wrong scenario, correct-looking results | Units in every field label and name; validation naming the field; plausibility warnings (`engine/scenario_checks.py`: passes, recording, TLE age > 3 days, gravity fidelity); the Explain tab | Values that are valid but not what the user meant |
| FM-06 | Model used outside its validity (an atmosphere too thin, a gravity degree too low) | Biased results | Gravity-fidelity warnings; the exponential atmosphere flagged as too thin for lifetime (`tests/test_lifetime.py`); D-02 to D-06 document missing models | Validity limits not covered by a warning |
| FM-07 | Estimate bias in the analyses (lifetime, budget) | Lifetime or delta-V off by a few percent | Lifetime checked against a full decay run, 3 % (V-L). The budget estimate is checked against 5-year runs (about −5 %, stated in its notes). AD10 margins. | Figures published before F-07 are out of date (K-01) |
| FM-08 | Wrong Basilisk version installed | Results not covered by the validation | Start-up check and warning; `basilisk_qualified` in every provenance | The user ignores the warning |
| FM-09 | Run fails midway (re-entry, a numerical failure, a crash) | Partial results; lost work | A failed run ends with a message and keeps the results so far (SRS-RE-01). Re-entry is detected and stops the run. Autosave of edits. GUI runs are contained in a worker thread; parallel Monte Carlo runs in separate processes. | – |
| FM-10 | Exported orbit data misread by another tool | Wrong data in the partner's tool | Written to CCSDS 502.0-B-3 and checked against it; GM stated; interoperability with GMAT tested (V-06, F-08) | Partners whose readers deviate from the standard |
| FM-11 | A scenario file runs code (script block, condition) | Anything the user's rights allow | Consent required; conditions use a whitelist evaluator (security analysis S-01, S-02) | The user consents without reading |
| FM-12 | A long run is split into segments wrongly | Discontinuities at segment boundaries | State carried between segments; tested (`tests/test_long_run.py`) | – |

## 4 Measures for critical software (ECSS-Q-ST-80C 6.2.3)

| Clause | Measure | Status |
|---|---|---|
| 6.2.3.2a: define, justify and apply measures | The safeguards of section 3. External validation for accuracy, provenance for traceability of every result, warnings for known limits. Justification: the main hazard is a plausible wrong result, so the measures aim at detecting wrong results, not at fault tolerance. | Applied |
| 6.2.3.3a: verify the measures | Each safeguard has a test or a validation case (column "Safeguards"); verified by the suite (SVR 4.6) | Verified by the supplier only (no independent verification, H06) |
| 6.2.3.4a: regression testing after platform or tool changes | The full suite runs in CI on every change. A new Basilisk version requires requalification, with the suite and the validation (SMP 8). Dependency versions are recorded per run. | Applied; changes of Python, Qt or OS versions are covered by CI only for the CI's versions |
| 6.2.3.5a: analyse the need for more V&V after platform changes | Part of the requalification step (SMP 8) | Procedure defined; not yet exercised |
| 6.2.3.6a: remove identified unreachable code | No systematic unreachable-code analysis has been done. The uncovered branches (18.3 %, `metrics.md`) are the candidate list. A few duplicate-name checks are known to be unreachable in practice; they are kept as defensive checks (Q-ST-80C 3.2.9, note). | **Open: analyse the uncovered branches** |
| 6.2.3.8a: validation on non-instrumented code | The validation cases ran without coverage instrumentation in the Phase 4 run (2239 passed). CI runs them with coverage. | Applied in the local run; CI's run is instrumented |

## 5 Reporting and updates (6.2.2.5a, 6.2.2.6a)

- The status of these measures is reported in the SPAMR (on request,
  decision 8).
- This analysis is updated when:
  - a function is added;
  - a safeguard changes;
  - a validation finding appears;
  - Basilisk is requalified.

## 6 Open items

- **Unreachable-code analysis** of the uncovered branches (6.2.3.6a).
- **Warning for leap seconds** missing from the tables (FM-03): a
  candidate improvement.
- **Independent verification** of the measures (H06).
