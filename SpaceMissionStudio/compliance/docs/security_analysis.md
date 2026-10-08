# SpaceMissionStudio: Software Security Analysis

Document: SMS-SSA, issue 1 (draft), 2026-10-08. Remediation R15.

**Status:** draft, by the supplier; not reviewed.

**Structure:** no DRD for a software security analysis report appears in
the supplied documents. The structure follows what
ECSS-E-ST-40C 5.11.3 and 5.11.4 and ECSS-Q-ST-80C 6.2.9 ask the analysis to
contain:
- assets and components with their sensitivity (5.11.3l);
- vulnerabilities and the risks mapped to them (5.11.3i);
- risk treatment measures (5.11.4a);
- the status of their implementation and verification (Q-ST-80C 6.2.9.5).

**Security assurance level:** low (decision D8).

**Human actions:**
- a security manager (E-ST-40C 5.11.2c): not named, the roles are open
  (H02). The security management plan (5.11.2a) is waived (decision 8,
  deviation D-10);
- the review of this analysis at SRR, PDR, CDR, QR and AR (5.11.5): H01.

## 1 Scope and method

- **Product:** the `spacemissionstudio` package and its installers, at
  this commit.
- **Basilisk and the third-party packages:** treated as reused software
  (SRF). They are covered for how the tool uses them, not audited
  internally.
- **Method:**
  1. Identify the inputs that cross a trust boundary.
  2. Find every place the code executes, deserialises, downloads,
     extracts or listens.
  3. Assess each place.
  4. Run a static security analysis: ruff's flake8-bandit rules (S) over
     the package.
  5. Treat what can be treated in the code, and test the treatment.
  6. Record what remains as a residual risk.
- **Higher-level analysis:** none exists (5.11.3c/d). The analysis rests
  on the security requirements of the SRS, SRS-S-01 to SRS-S-03.

## 2 Context and assets

The tool is a desktop program run by one user on their own computer. It has
no server, no accounts and no stored credentials. It is offline by design:
it accesses the network only when the user asks.

| Asset | Why it matters |
|---|---|
| The user's computer and files | A scenario that runs code acts with the user's rights |
| The correctness of results | Results feed mission design (budgets, lifetime); tampered data gives wrong numbers |
| Downloaded data and programs (space weather, Earth PCKs, Vizard) | Data of wrong provenance gives wrong results; a tampered program runs with the user's rights |
| The installed software | A tampered package or dependency runs with the user's rights |

**Inputs crossing a trust boundary:** scenario files from other people,
CCSDS and TLE files, space-weather files, downloads, the Vizard socket, and
packages from PyPI.

**Sensitivity of the components (5.11.3l):**

| Class | Components |
|---|---|
| High: they execute, or decide whether to execute, content from a file | `engine/mission_engine` (`script_block`, conditions), `schema/command` (condition evaluator), `cli` and `gui/main_window` (consent) |
| Medium: they parse files or downloads, or open network connections | `engine/spaceweather`, `engine/earth_orientation`, `gui/vizard_launcher`, `engine/vizard`, `engine/ccsds_odm`, `engine/tle`, `schema/scenario`, `schema/migrations` |
| Low | Everything else |

## 3 Vulnerabilities, risks and treatment

| # | Vulnerability | Risk (likelihood, effect) | Treatment | Status | Evidence |
|---|---|---|---|---|---|
| S-01 | **`script_block` runs the scenario file's Python with the user's rights** (`exec` with real builtins). A shared or downloaded scenario could run code without the user noticing, because pressing Run was enough. | Medium likelihood (scenarios are shared), high effect | A run refuses to start a sequence containing a `script_block` without the user's explicit consent (SRS-S-03). In the engine, `MissionEngine(allow_scripts=False)` is the default and raises `ScriptsNotAllowedError` before building anything. In the CLI, `run` needs `--allow-scripts`; without it the exit code is 1 and the message names each block. `validate` notes the blocks. In the GUI, Run shows the code of every block and asks; the default is No. Consent is never stored in the scenario file, so a file cannot consent for itself. | Implemented, tested | `tests/test_mission_engine.py::test_script_block_does_not_run_without_consent`; `tests/test_cli.py::test_run_refuses_script_blocks_without_allow_scripts`, `test_run_with_allow_scripts_runs_them`, `test_validate_notes_script_blocks`; `tests/gui/test_main_window.py::test_script_blocks_run_only_after_the_user_confirms`, `test_script_block_confirmation_shows_the_code_and_defaults_to_no` |
| S-02 | **`if`/`while` conditions ran through `eval()`** with empty builtins. This is not a sandbox: attribute access (`().__class__.__base__.__subclasses__()`) reaches any loaded class, and from there file and process access. Before this change, a condition ran with no consent at all. | Medium, high | Conditions are now evaluated by a small interpreter over a whitelist of expression nodes (`schema.command.evaluate_condition`). It allows names from the context, numbers, strings, subscripts, arithmetic, comparisons, `and`/`or`/`not` and conditional expressions. It refuses attribute access, calls, lambdas and comprehensions. Exponents are capped. Validation reports a disallowed condition at the field, before the run. | Implemented, tested | `tests/test_command.py::test_conditions_evaluate_like_python`, `test_conditions_cannot_reach_beyond_their_values`, `test_condition_errors_name_the_problem`, `test_validation_reports_a_condition_outside_the_allowed_set`; `tests/test_mission_engine.py::test_condition_cannot_reach_python_objects` |
| S-03 | **Scenario JSON parsing.** Scenarios are plain JSON (`json.loads`), never pickled; unknown fields are refused. | Low | None needed. | – | `tests/test_scenario_schema.py::test_load_scenario_rejects_an_unknown_field_naming_it` |
| S-04 | **Monte Carlo archives** are written by Basilisk's `Controller` as gzipped pickles. Loading a pickle runs code. | Low: the tool writes archives but never loads them. A user who loads someone else's archive with Basilisk's own tools is outside the tool. | None in the tool. The SUM tells users to load only their own archives. | Documented | `grep` shows no load path in `spacemissionstudio/` (this analysis) |
| S-05 | **The Vizard download is an executable.** It comes from AVS's server over HTTPS. No checksum is published to verify it against. | Low (HTTPS, a fixed URL, only on the user's click), high effect if the server were compromised | Download only on consent, from a constant https URL. Bounded size. Zip-slip guard on extraction. The tool now records the download: `download.json` with URL, size, SHA-256 and time, and the status line shows the hash so the user can compare it. | Partly treated: a hash can be recorded but not verified | `tests/gui/test_vizard_launcher.py::test_fetch_vizard_records_the_download_with_its_sha256`, `test_fetch_vizard_rejects_a_response_over_the_size_cap`; the zip-slip guard tests |
| S-06 | **Vizard live stream:** Basilisk's `vizInterface` binds its ZMQ sockets on 0.0.0.0, ports 5556 and 5570, so other machines on the network can connect while a live run streams. | Low (only during a live run; the data is the simulation's), low to medium | Proposed: set `reqComAddress` and `pubComAddress` to 127.0.0.1 through Basilisk's public attributes. **Not done:** it cannot be verified with a real Vizard in this environment, and an unverified change could break live streaming. The SUM advises a firewall. | Open: H11 | – |
| S-07 | **Integrity of the tool's own releases.** No checksums were published. | Low, high | The build scripts now write `SHA256SUMS` (wheel, sdist) and `<deb>.sha256`. Signing the releases is a human decision (H05). | Implemented for checksums | `packaging/build_wheel.sh` run in this audit (SHA256SUMS produced) |
| S-08 | **Dependency supply chain.** Installers run `pip install "bsk[all]==2.12.0"` and the tool's dependencies, from PyPI over HTTPS, without hash checking. Lower-bound pins (`pyproject.toml`) let other versions in. | Low, high | The Basilisk version is pinned and checked at start-up. The versions used are recorded in every run's provenance. Proposed: a lock file with hashes (`--require-hashes`) for releases (SDP, SCMP). | Partly treated | `dependencies.py`, `tests/test_dependencies.py` |
| S-09 | **Data downloads:** CelesTrak space weather and NAIF Earth PCKs. | Low, medium (wrong results) | Only on the user's request. Constant https URLs. Bounded size. Format and coverage checks (DAF/PCK header; the space-weather parser and coverage check). SHA-256 recorded in the manifest and in each run's provenance. | Implemented | `tests/test_spaceweather.py`, `tests/test_earth_orientation.py` |
| S-10 | **File parsers** (CCSDS KVN, TLE, space-weather CSV and text) read local files the user chooses. | Low (no code execution; Python's memory safety), low (a refused file) | Line-based parsing with explicit errors; no `eval`; no deserialisation of objects. | – | `tests/test_ccsds_odm.py`, `tests/test_tle.py` |
| S-11 | **Subprocess:** the tool starts Vizard (`subprocess.Popen` with an argument list, no shell). | Low | No shell. The executable is the one the user chose or downloaded (S-05). | – | ruff S603 reviewed (noqa with reason) |
| S-12 | **Denial of service by a crafted scenario:** a `while` that never ends, a huge expression or a huge duration. | Low, low (the user's own session) | `while` stops after a fixed iteration cap; exponents are capped; durations are bounded by validation; every run is cancellable. Very large string or number products are still possible in a condition. | Mostly treated | `tests/test_mission_engine.py::test_while_loop_exceeding_iteration_cap_raises_clear_error` |

## 4 Static security analysis

**Rule set:** ruff's flake8-bandit rules (S) over `spacemissionstudio/`.

**Before treatment, 13 findings:**

| Rule | Where | Disposition |
|---|---|---|
| S102 `exec` | `engine/mission_engine.py` (`script_block`) | By design, behind consent (S-01); noqa with reason |
| S307 `eval` | `engine/mission_engine.py` (conditions) | **Removed:** replaced by the whitelist evaluator (S-02) |
| S310 URL open (×6) | `earth_orientation`, `spaceweather`, `vizard_launcher` | Constant https URLs; noqa with reason |
| S603 subprocess | `gui/vizard_launcher.py` | Argument list, no shell (S-11); noqa |
| S110, S112 try-except-pass/continue (×3) | `engine/scenario_checks.py`, `engine/vizard.py` | Deliberate: the Explain tab must survive a half-edited scenario; noqa with reason |
| S101 assert | `gui/mission_dashboard_widget.py` | Type narrowing only; noqa |

**After treatment:** no findings. The S rules are now part of the lint
configuration (`pyproject.toml`), so CI fails on any new finding. Tests,
scripts and the compliance tools are excluded (asserts and trusted local
input).

## 5 Architecture: residual vulnerabilities (E-ST-40C 5.4.3.2b)

The architecture (SDD 4.1) has no network service. Code from a file
executes in exactly one place: `script_block`, behind consent. There is one
listening socket, Vizard's, during live runs only (S-06).

**Residual vulnerabilities after treatment:**
- S-05: the Vizard download is not verifiable.
- S-06: the live-stream sockets bind to all interfaces.
- S-08: dependencies are not pinned by hash.
- S-12: residual resource use in conditions.
- The consent for S-01 relies on the user reading the code.

## 6 Delivery and installation (E-ST-40C 5.7.2.1b, 5.7.2.3b)

- **Delivery:** release checksums (S-07). Signing is H05.
- **Installation:** installers create a private virtual environment,
  install from PyPI over HTTPS (S-08), and offer to pre-fetch the data
  files. No step runs with more rights than the installer needs. The
  Debian package runs as root via apt, as every system package does.

## 7 Updating this analysis

Review it:
- at each release;
- when a new input, download, parser or execution path is added;
- after a reported security problem (5.11.3k, 5.11.5.6).

The S lint rules in CI catch new instances of the patterns in section 4.
