# SpaceMissionStudio coding standard

Document: SMS-CS, issue 1 (draft), 2026-10-08. Remediation R10.

Addresses ECSS-Q-ST-80C 6.3.4.1a-6.3.4.8a (coding standards, their tools,
code evaluation) and ECSS-E-ST-40C 5.5.3.1a, 5.8.3.5a/b/f (coding, code
verification, coverage, robustness).

**Status:** written by the supplier. Not yet reviewed with the customer.
That review (Q-ST-80C 6.3.4.4a) and agreement of the thresholds in rules C-7
and C-10 are human action H09.

## 1 Scope and basis

- **Scope:** the Python code of SpaceMissionStudio:
  - `spacemissionstudio/`
  - `tests/`
  - `scripts/`
  - `compliance/tools/`
- **Out of scope:** Basilisk. It is reused software (ECSS-Q-ST-80C 6.2.7).
  It is used unmodified at the version pinned in
  `spacemissionstudio/dependencies.py`, and this standard does not apply to
  it.
- **Basis:**
  - PEP 8;
  - the Basilisk coding guidelines
    (`docs/source/Support/Developer/CodingGuidlines.rst`, "Python Exceptions"
    and the frame/attitude notation);
  - the repository rules in `AGENTS.md`.
- **Where they differ, this document governs the tool's code.** Rule C-2
  records the one difference.

## 2 Rules

Each rule names how it is checked:

- **ruff:** automatic, `[tool.ruff]` in `pyproject.toml`, run in CI.
- **review:** the code review of H06.
- **test:** the test suite in CI.

| # | Rule | Checked by |
|---|---|---|
| C-1 | **Language.** Python >= 3.9 (`requires-python`). No low-level language is used (Q-ST-80C 6.3.4.5a). C/C++ exists only inside Basilisk, which is reused, not developed here. | review |
| C-2 | **Layout.** PEP 8. Lines are at most 120 characters in new or changed code (E501 is not enforced on existing lines). Imports are grouped stdlib / third party / local. Exception: binary operators have spaces as PEP 8 recommends; Basilisk's "no spaces around math operators" exception is not adopted. | ruff E4, E7, E9, W; review |
| C-3 | **Naming.** `snake_case` for functions, variables and modules; `CapWords` for classes. Names of Basilisk objects and message fields keep Basilisk's spelling. A physical quantity's name ends in its unit (`_m`, `_km`, `_s`, `_deg`, `_rad`, `_kg`, `_n`, `_w_m2`, `_km3_s2`). A vector carries its frame as in `engine/frames.py` (`r_BN_N`, `sigma_BN`, `dcm_PN`). No single-letter names except loop indices and established symbols (`r`, `v`, `t`, `mu`). | review |
| C-4 | **Units on literals.** Every numeric literal with physical meaning has a unit comment, e.g. `1361.0  # [W/m^2]` (`AGENTS.md` rule 1). SI is used internally. Conversion happens only at the boundaries (GUI, CCSDS km, files). | review |
| C-5 | **Comments and docstrings.** Every module, public class and public function has a reStructuredText docstring saying what it does, with units and frames. A module that implements a standard cites the clause, e.g. "CCSDS 502.0-B-3 7.4", "ECSS-E-ST-10-09C 5.4.6a". A comment says *why*, not what. New files carry the ISC copyright header with the current year. | review |
| C-6 | **Errors.** No bare `except:`. An exception is caught only to add context or to recover, and the user-facing message names the field or file at fault. A handler that recovers logs at WARNING or above, or returns the problem to the caller (e.g. `Issue`, `warnings` lists). No `assert` for input checking in shipped code. | ruff E722, B; review |
| C-7 | **Complexity.** McCabe cyclomatic complexity <= 15 for new or rewritten functions (ruff C901, measured by `compliance/tools/metrics.py`). Existing functions above 15 are listed in `compliance/metrics.md`. Each is split when it is next changed materially, or its size is justified in a comment (e.g. a GUI form constructor). | metrics.py; review |
| C-8 | **Static analysis.** Zero ruff findings for the rule set in `pyproject.toml` (pyflakes F, pycodestyle E4/E7/E9/W, bugbear B; B007 and B023 ignored for the reasons given there). A `# noqa` names the rule and states the reason on the same line. | ruff in CI |
| C-9 | **Tests.** Every new function has a unit test. Every test has a docstring stating what it checks. Tests check boundary values (n-1, n, n+1) and each error path the code defines (E-ST-40C 5.5.3.2c). A test that verifies a requirement carries `@pytest.mark.requirement("<standard> <ID>")` (traceability, `compliance/tools/build_traceability.py`). A test that needs Basilisk is marked `requires_basilisk`. Tests never download data themselves (the fetch functions are mocked); Basilisk's own data files are fetched by Basilisk's data fetcher when absent. | test; build_traceability.py |
| C-10 | **Coverage.** Statement coverage of `spacemissionstudio` >= 90 % and branch coverage reported, measured by pytest-cov in CI (E-ST-40C 5.8.3.5b-c). For category C, Table 5-1 of E-ST-40C leaves the figure "TBA", so 90 % is the supplier's proposal (H09). Code not reached by tests (GUI error dialogs, download failures) is justified by inspection (5.8.3.5d). | CI; metrics.py |
| C-11 | **Security.** See the rule list after this table. | review; ruff S (from R15) |
| C-12 | **Dependencies.** Basilisk is pinned (`QUALIFIED_BASILISK_VERSION`) and checked at start-up. Other dependencies have lower bounds in `pyproject.toml`, and their versions are recorded in each run's `provenance.json`. A new dependency needs an entry in the reused-software list (H07). | test (test_dependencies.py) |
| C-13 | **Basilisk.** The Basilisk framework is never modified, patched or monkey-patched. Only its public Python API is used. A Basilisk shortcoming is corrected outside Basilisk (e.g. R06 thermal scaling) and is documented where it is corrected. | review |
| C-14 | **Numerics.** Floating-point results are compared with stated tolerances, never with `==`, except for values that are exactly representable or copied. Time is handled as described in `engine/time_system.py` (UTC in, TDB seconds since the epoch inside). | review; test |
| C-15 | **Configuration control.** All code is in git. Work is done on a branch. A commit message names the requirement IDs or remediation items it addresses. A change merges only with CI green (Q-ST-80C 6.3.4.8a). | CI; review |

### C-11 security rules

1. No `eval`, `exec` or `pickle` of data that comes from outside the code.
   The two existing uses are recorded for the R15 security analysis:
   - the `if`/`while` conditions use `eval` with empty builtins;
   - `script_block` uses `exec`.
2. Files are parsed as JSON, CSV or CCSDS KVN, and validated before use.
3. Network access happens only through the consented fetch functions:
   - `spaceweather.fetch`
   - `earth_orientation.fetch`
   - the Vizard download

   Each uses HTTPS with a timeout. Nothing is downloaded at import or run
   time.
4. `subprocess` is called only with argument lists, never with
   `shell=True`.
5. Paths from the user are opened, never executed.
6. No credentials are stored in the code.

## 3 Tools

These tools are identified for Q-ST-80C 6.3.4.3a and 6.3.4.6a:

| Tool | Purpose | Where |
|---|---|---|
| ruff >= 0.6 | Lint and static analysis (C-2, C-6, C-8), complexity (C-7) | `pyproject.toml`, CI |
| pytest, pytest-qt, pytest-xdist | Unit and integration tests (C-9) | `tests/`, CI |
| pytest-cov (coverage.py) | Statement and branch coverage (C-10) | CI |
| `compliance/tools/metrics.py` | Size, complexity, fault-density proxy, coverage, failures (Q-ST-80C 7.1.5a) | CI artifact `compliance/metrics.md` |
| `compliance/tools/build_traceability.py` | Requirement-to-test traceability (C-9) | CI artifact `compliance/traceability_matrix.csv` |

## 4 Code evaluation

Code is evaluated while it is written (Q-ST-80C 6.3.4.6b). The CI workflow
`.github/workflows/spacemissionstudio.yml` runs on every push and pull request
that touches `SpaceMissionStudio/`, so the programmer gets feedback on each
change. It runs:

1. ruff;
2. the tests with coverage;
3. the metrics, traceability, ICS and compliance-matrix builds.

The synthesis of the results and the corrective actions taken goes into the
software product assurance report (Q-ST-80C 6.3.4.7a). That report is part
of Phase 4, and its approval is H02.

## 5 Status of the existing code

The figures are from the date of this issue:

- ruff: rule set C-8 passes with zero findings.
- Coverage:
  - statement coverage: see `compliance/metrics.md`;
  - Phase 1 baseline: 91 % of 15,720 statements.
- Complexity: 19 functions are above 15 (`compliance/metrics.md`). None are
  refactored by this issue. Refactoring them would change verified code
  without a requirement asking for it, and is left to rule C-7's "when next
  changed".
- Rule C-4 (units on literals) and rule C-5 (docstrings) are applied to new
  code. The existing code was not re-checked line by line, and that check is
  part of the review in H06.
