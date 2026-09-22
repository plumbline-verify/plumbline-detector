# plumbline-detector

A static, offline, artifact-only detector that answers one question about a
repository snapshot: **is this codebase's verification evidence real, or does
it only look real?**

It reads a directory (for example, an unpacked data-room zip) and writes one
versioned JSON record. It does not use the network, the GitHub API, CI
history, or git. It never executes the code it analyzes.

Read [LIMITATIONS.md](LIMITATIONS.md) before relying on any result.

## Install

Requires Python 3.11 or newer. One runtime dependency (PyYAML).

```sh
python -m venv .venv
.venv/bin/pip install .            # or: pip install -e '.[test]' for development
```

## Usage

```sh
plumbline-detect PATH                 # JSON record to stdout
plumbline-detect PATH -o record.json  # to a file
```

Options:

| Option | Effect |
|---|---|
| `--required-check NAME` | A required status check known from outside the snapshot (repeatable). Branch protection normally lives in repository settings, not in the repository; if the data room supplies it, pass it here. |
| `--gate-file FILE` | A GitHub ruleset JSON export supplied with the snapshot (repeatable). |
| `--label TEXT` | A label for the repository. Only its SHA-256 is recorded. |
| `--commit-sha SHA` | The commit, when known but absent from the snapshot (for example a zip without `.git`). |
| `--timestamp ISO` | A timestamp to record. `SOURCE_DATE_EPOCH` is honored too. |
| `--now` | Record the wall-clock time. The output is then no longer reproducible. |

Exit status is 0 when a record was produced (whatever the verdicts), 2 on
usage errors.

Run the detector's own tests:

```sh
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest
.venv/bin/python tools/check_us_spelling.py   # US spelling in prose (needs hunspell en_US + en_GB)
```

## Verdicts

Every check returns exactly one of:

- **FAIL**: at least one finding, each with file and line.
- **UNKNOWN**: there was nothing in scope to examine, or something in scope
  could not be read, parsed, or recognized. The unrecognized locations are
  listed under `unknowns`.
- **PASS**: there was input in scope, all of it was examined, and nothing was
  found.

Precedence is FAIL > UNKNOWN > PASS. A read failure, parse failure, size-limit
skip, or unrecognized construct can never produce PASS.

## Output record

The record is described by [`schema/record.schema.json`](schema/record.schema.json).
Top-level fields:

| Field | Content |
|---|---|
| `schema_version` | Version of the record format **and** check semantics. Any change to a check bumps it (enforced by `tests/test_versioning.py`). |
| `tool` | Name and package version. |
| `provenance` | `ruleset_fingerprint` (SHA-256 over the source of every module that defines check semantics), `operator_set` (check IDs run), `config` and `config_hash`, `environment` (Python and PyYAML versions; the Python grammar accepted depends on the interpreter), `commit_sha` and how it was obtained, `timestamp` and its source. |
| `repo` | `content_id`: SHA-256 over sorted (path, file SHA-256) pairs, so the same content always has the same identifier wherever it is unpacked. `label_sha256` if a label was given. |
| `inventory` | Per-language file counts and non-blank LOC, primary language, Python test-file count, workflow count, unread files with reasons, excluded directory and symlink counts, Python test-data files. |
| `summary` | Count of PASS / FAIL / UNKNOWN. |
| `checks` | One entry per check: `id`, `verdict`, `reason`, `findings`, `unknowns`, `stats`, and for gate checks `basis`. |

**Determinism.** Two runs over identical input, options, and environment
produce byte-identical output. Nothing time- or location-dependent enters the
record unless `--now` is passed. Collections are sorted and JSON keys are
sorted.

**Versioning.** `src/plumbline_detector/fingerprint.json` maps each schema
version to the ruleset fingerprint. If check code changes without a version
bump, the test suite fails. Existing entries are never edited; a change means
a new version and a new entry (`tools/update_fingerprint.py` prints the
current fingerprint).

**Privacy.** The record contains relative paths, line numbers, and
detector-generated messages. Messages quote short fragments of the analyzed
code where they are the finding: test, class and job names, `if:`
expressions, required-check names, and special-cased literal values. The
record contains no author or commit metadata beyond the commit SHA, and no
absolute paths. The analyzed repository's name appears only if the operator
puts it in `--label`, and then only hashed. Treat a record of confidential
code as confidential.

## What is analyzed

- **GitHub Actions**: `.github/workflows/*.yml|yaml` (top level only, as
  GitHub reads them). Gate declarations: `.github/settings.yml` (the Settings
  app format), `.github/rulesets/*.json` and `.github/*ruleset*.json` (GitHub
  ruleset exports), plus operator input.
- **Python**: every `.py` file, parsed with the running interpreter's `ast`.
  *Test paths* are `test_*.py`, `*_test.py`, `conftest.py`, `tests.py`, and any
  `.py` under a directory named `tests` or `test`. *Test data* are `.py` files
  under `fixtures/`, `resources/`, `testdata/`, `test_data/`,
  `example_scripts/` or `snapshots/` whose directory is not a package and
  whose name is not collectable by pytest; they are counted, not analyzed.
  Everything else is *implementation*.
- Excluded directories (installed third-party code, caches): `.git`,
  `node_modules`, `.venv`, `venv`, `.tox`, `.nox`, `__pycache__`,
  `site-packages`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.eggs`.
  Symlinks are never followed. Files over 4 MiB are not read and are recorded
  as unread.

JavaScript/TypeScript, Java and C# are inventoried (files, LOC) but not
analyzed in this version.

## The checks

### Gate topology (GitHub Actions)

GitHub documents that a job skipped by a conditional reports its status as
Success, and branch protection accepts success, skipped and neutral alike for
a required check. A skipped *job* therefore satisfies a required check. The
gate checks find the places where that, or something like it, lets unverified
code merge.

Several gate checks need to know which checks are required. That set comes
from the snapshot or the operator (`basis: "declared"`). If none is declared,
aggregator jobs (summary jobs that `needs:` others) are treated as the
required set (`basis: "inferred"`). If there is neither, the check is UNKNOWN.

| ID | Detects | Failure it prevents |
|---|---|---|
| `GT-SKIP-SATISFIES` | A job that produces a required check and has a job-level `if:` that can be false on a pull-request run. Allowlisted non-skipping forms: `always()`, `!cancelled()`, `true`, `success() \|\| failure()`, and conjunctions of those with conditions that are always true on a pull request (`github.ref != 'refs/heads/…'`, `github.event_name != 'push'` and similar). Every other expression is treated as skippable. | A required check that goes green without running because a label, an actor, a path filter, or a merge-queue event made its condition false. |
| `GT-CONTINUE-ON-ERROR` | `continue-on-error` that is `true` or an expression, on a step that runs tests or on a job that runs tests. Values other than `true`, `false`, or `${{ … }}` are UNKNOWN. | Test failures that leave the job (step level) or the workflow run and its dependents (job level) green. |
| `GT-AGGREGATOR-PERMISSIVE` | An aggregator job (has `needs:`, runs no tests, and has an aggregator-style name or only trivial steps) that either (a) lacks an always-run `if:`, so it is skipped and reports Success when a dependency fails, or (b) runs always but never checks the result of some or all of its needs. Recognized verifications: `re-actors/alls-green` given `toJSON(needs)`; a step that reads `needs.<job>.result` and can exit non-zero; a step that consumes `toJSON(needs)` and can `exit 1`. | An "all checks passed" job that is green when checks failed. |
| `GT-NO-PROPAGATION` | A test-running job in a pull-request-triggered workflow whose failure cannot reach a required check: it is not required itself, and no chain of always-running, result-verifying dependents connects it to one. With an inferred required set the locations are reported as UNKNOWN, not FAIL, because the job might be required directly in settings. | Test jobs whose red X is advisory: the merge button never sees them. |
| `GT-NO-GATE` | Workflows exist but nothing in the snapshot or operator input declares a required status check, or a declared branch protection lists no required checks. | Treating the presence of CI as evidence that CI gates merges. |

### Evidence-channel tampering (Python)

These target the documented ways that code, or an agent writing it, makes a
test suite report success without verifying anything: Anthropic's
production-RL reward-hacking findings (AlwaysEqual, `sys.exit(0)` before
asserts, a `conftest.py` patching `TestReport.from_item_and_call`) and the
ImpossibleBench strategies (arXiv 2510.20270: overriding `__eq__`,
special-casing test inputs, among others).

| ID | Detects | Failure it prevents |
|---|---|---|
| `EC-EXIT-BEFORE-ASSERT` | In test code: `sys.exit`, `exit`, `quit`, `os._exit`, `raise SystemExit`, `pytest.exit(returncode=0)` with a success status. Not reported: under `if __name__ == "__main__":`, inside `pytest.raises(SystemExit)` / `assertRaises(SystemExit)`, or with a non-zero literal status. A non-literal status is UNKNOWN. | A process that exits 0 before its assertions run, which a runner or CI reads as success. |
| `EC-EQUALITY-OVERRIDE` | Anywhere: an `__eq__`/`__ne__` (method, lambda, class attribute, attribute assignment, `setattr`) whose result does not read the other operand, such as `return True`. In test code only, any other `__eq__` is UNKNOWN (a comparison helper whose soundness cannot be judged). A value-object `__eq__` in implementation code that reads the other operand is **not** reported. | An object that equals everything, so every `assert result == expected` passes. |
| `EC-RUNNER-PATCHED` | In test code: patching reporting machinery (`TestReport`, `CallInfo`, `call_and_report`, unittest `TestResult`, `AssertionError` …) by assignment, `setattr`, `monkeypatch`, or `mock.patch`; writing outcome attributes (`outcome`, `longrepr`, `excinfo`, `exitstatus`, `wasxfail` …) inside reporting hooks; `force_result` in reporting hooks; `pytest_pyfunc_call`/`pytest_runtest_call` returning without calling the test; `TestResult` subclasses that drop failures; `wasSuccessful()` returning a constant. Other attribute writes inside reporting hooks, and any `pytest_report_teststatus` implementation, are UNKNOWN. The same constructs in pytest plugins outside test paths are UNKNOWN. Not reported: the documented `setattr(item, "rep_" + rep.when, rep)` pattern. | A test suite that reports failures as passes. |
| `EC-NO-ASSERTION` | A test function (pytest or unittest; not `conftest.py`, not fixtures, not `skip`ped) with no recognized assertion. Recognized: `assert`; calls whose name starts with `assert`; `pytest.raises`/`warns`/`deprecated_call`, `assertRaises…`/`assertWarns…`/`assertLogs`; `pytest.fail`/`self.fail`; `raise AssertionError`; pytester `fnmatch_lines`-family and pexpect `expect`; and calls to functions defined in test paths that themselves (transitively) assert. | A test that passes whenever the code does not crash, so it cannot detect a wrong answer. |
| `EC-MOCK-ONLY` | A test that creates or injects mocks, asserts, and loads no name other than those mocks, values derived only from them, builtins and mock/pytest library names. Not reported: tests that call real code with a mock and then assert on the mock. | A green test that never reaches the code under test (`m.return_value = 3; assert m() == 3`). |
| `EC-SPECIAL-CASED` | (a) In implementation code: `if <parameter> == <literal>: return <literal>` in a function that also has a general return path, where the input literal is non-trivial, occurs in test files, and occurs nowhere else outside test files (not in other code, not in docs). (b) Implementation code that reads `PYTEST_CURRENT_TEST`, `PYTEST_VERSION`, `sys._called_from_test`, or checks for `pytest`/`unittest` in `sys.modules`. Test infrastructure (files importing pytest, pytest plugins, noxfile, setup.py) is excluded from (b). | Code that returns the expected answer for the test's input only, or behaves differently under test than in production. |
| `EC-ASSERTION-NONSTANDARD` | Assertions that cannot fail or cannot run: `assert <truthy constant>`, `assert (x, "msg")`, `assert x is x`, `assert … or True`, `assertTrue(a, <non-string constant>)`, `assert m.called_once_with(…)` (auto-created Mock attribute), bare `m.assert_called_once` without a call, an assertion inside `try` whose handler swallows `AssertionError`/`Exception`, and an assertion after a bare call inside a `pytest.raises`/`assertRaises` block. `assert x == x` is **not** reported (it invokes `__eq__` and can fail). This is an operational definition; it does not reproduce the taxonomy of any cited study. | Assertions that look like verification but verify nothing. |

## Layout

```
src/plumbline_detector/   detector (snapshot reader, GHA and Python models, checks, record)
schema/                   JSON Schema for the record
fixtures/                 miniature repositories: known-good, known-bad, discrimination, malformed
tests/                    test suite (fixture expectations, determinism, schema, versioning)
tools/                    development aids (fingerprint, spelling, summaries)
docs/ACCEPTANCE.md        Phase A acceptance runs against real public repositories
LIMITATIONS.md            what this detector cannot see
```

## License

Apache-2.0 (to be applied at publication).
