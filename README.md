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
| `--format json\|sarif\|markdown` | `json` (default) is the versioned record. `sarif` is SARIF 2.1.0 for code-scanning tools (GitHub code scanning, IDEs): findings at level `error`, UNKNOWN locations at level `note`. `markdown` is a human-readable report for a data room or an audit memo. Both are pure renderings of the record. |

Compare two records of the same repository (for example the base and head of
a pull request):

```sh
plumbline-diff base.json head.json   # prints + new, - resolved, ~ verdict changes; exit 1 if anything is new
```

Findings are matched by `id`, a hash of check, file and message that does not
change when lines shift. This gates a pull request on *regressions* without
requiring an existing codebase to be clean first.

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
| `checks[].measured_precision` | The check's most recent held-out precision measurement (docs/PRECISION_STUDY.md): round, schema it was measured on, whether that is the exact check code now running (`same_ruleset`), sample size, true positives, precision and 95% Wilson interval; `null` if the check has never produced a finding in a study round. The source file's hash is in `provenance.measurements_sha256`. |
| `checks[].grade` | How far to trust the check's findings, derived from `measured_precision`: `verdict` (at least 20 labeled findings, precision ≥ 90%, 95% lower bound ≥ 80%), `advisory` (at least 10, precision ≥ 70%), `experimental` (anything else, including unmeasured). SARIF result levels follow it (`error`, `warning`, `note`). Each study round recalibrates it; the verdict itself is unaffected. |
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
  `.py` under a directory named `tests`, `test` or `_tests`. *Test data* are `.py` files
  under `fixtures/`, `resources/`, `testdata/`, `test_data/`,
  `example_scripts/` or `snapshots/` whose directory is not a package and
  whose name is not collectable by pytest; they are counted, not analyzed.
  Everything else is *implementation*.
- Excluded directories (installed third-party code, caches): `.git`,
  `node_modules`, `.venv`, `venv`, `.tox`, `.nox`, `__pycache__`,
  `site-packages`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.eggs`.
  Symlinks are never followed. Files over 4 MiB are not read and are recorded
  as unread.

### Which tests actually run

When there is evidence that pytest is the runner (a pytest configuration, a
pytest invocation, a `conftest.py`, or test files importing pytest), the
detector models pytest collection and selection statically:

- **Configuration** is located and parsed as pytest does: `pytest.toml`,
  `.pytest.toml`, `pytest.ini`, `.pytest.ini`, `pyproject.toml`
  (`[tool.pytest]` or `[tool.pytest.ini_options]`), `tox.ini` (`[pytest]`),
  `setup.cfg` (`[tool:pytest]`), first directory upward that has one. It reads
  `addopts`, `testpaths`, `norecursedirs`, `python_files`, `python_classes`,
  `python_functions`, and applies `-o`/`--override-ini` overrides of those.
- **Invocations** are read from GitHub Actions `run:` steps (with
  `working-directory`, `defaults.run.working-directory`, `cd`, and a literal
  `PYTEST_ADDOPTS`), tox configuration (`tox.ini` `commands` with
  `changedir` and substitutions; `tox.toml` and `[tool.tox]` in
  `pyproject.toml`), `noxfile.py` `session.run`, Makefile recipes, `*.sh` scripts and
  extensionless scripts with a `sh`/`bash` shebang, and the `run:`/`command:`
  input of actions that run a given command (CodSpeed, retry wrappers).
  `python -m pytest` is recognized with interpreter flags (`python -Im`,
  `python -bb -m`) and under `coverage run [options] -m`. An unresolved value of an option that does not affect selection
  (`--basetemp={env_tmp_dir}`, `--cov=$PKG`) does not make an invocation
  unresolvable. With none found, a plain `pytest` at each configuration root is
  assumed.
- `-k`, `-m` (last one wins, as in pytest), `--deselect`, `--ignore`,
  `--ignore-glob`, positional paths and node IDs, `--pyargs`, and
  `collect_ignore`/`collect_ignore_glob` in `conftest.py` are applied.

**Test code and test data.** With a resolved invocation, a file under a test
directory is test code only if pytest collects it, it is a `conftest.py`
pytest would load, or test code imports it (directly, transitively, or via
`pytest_plugins`). Anything else there whose name does not look like a test
module (a linter's functional inputs, documentation roots, example projects)
is test data: counted in `inventory.python_test_data_files`, not analyzed. A
file that does look like a test module stays test code even when nothing
collects it, so a test hidden by `collect_ignore` is still reported.

A test counts as run if **any** invocation collects and selects it and it is
not unconditionally skipped, so the model errs toward "runs". Tests the model
says never run are reported by `EC-TESTS-NOT-RUN` and excluded from
`EC-NO-ASSERTION` and `EC-MOCK-ONLY`; files that the configuration collects
are treated as test code whatever their name.

**Out-of-scope trees.** A test file none of whose tests any resolved
invocation's collection scope reaches (`testpaths`, `norecursedirs`,
command-line paths), and which lies in a different top-level directory from
every collected test file (`example/`, `examples/`, `bench/` beside
`tests/`), is not judged by `EC-EXIT-BEFORE-ASSERT`, `EC-NO-ASSERTION`,
`EC-MOCK-ONLY` or `EC-ASSERTION-NONSTANDARD`. Its tests still appear under
`EC-TESTS-NOT-RUN` as UNKNOWN. A file beside collected tests in the same
top-level directory stays judged, so an invocation the model missed cannot
hide a whole suite.

- **JavaScript / TypeScript**: parsed with tree-sitter (TypeScript grammar for
  `.ts/.mts/.cts`, TSX for `.tsx`, JavaScript with JSX for `.js/.jsx/.mjs/.cjs`).
  A test file follows a test naming convention (`*.test.*`, `*.spec.*`,
  `*.cy.*`, `__tests__/`, `test/`, `tests/`) and declares at least one test
  case (`it`, `test`, `specify`, with `.skip/.only/.todo/.each` and
  `xit/fit/xdescribe/fdescribe`). A test call must have a title, and a local
  function that happens to be named `test` or `it` is not a test primitive.
  Frameworks are read from `package.json` (jest, vitest, mocha, chai, ava,
  jasmine, playwright, cypress). Files named like test utilities
  (`test-utils`, `testing`, `setupTests` …) are read only as sources of
  asserting helpers.

Java and C# are inventoried (files, LOC) but not analyzed in this version.

## The checks

### Gate topology (GitHub Actions)

GitHub documents that a job skipped by a conditional reports its status as
Success, and branch protection accepts success, skipped and neutral alike for
a required check. A skipped *job* therefore satisfies a required check. The
gate checks find the places where that, or something like it, lets unverified
code merge.

Several gate checks need to know which checks are required. That set comes
from the snapshot or the operator (`basis: "declared"`). If none is declared,
aggregator jobs (summary jobs that `needs:` others; not release, deploy or
publish jobs, not jobs whose `if:` is false on every pull request, and not
jobs in workflows whose `pull_request` trigger lists only activity types
that deliver no new code, such as `labeled`) are
treated as the required set (`basis: "inferred"`). If there is neither, the
check is UNKNOWN.

| ID | Detects | Failure it prevents |
|---|---|---|
| `GT-SKIP-SATISFIES` | A job that produces a required check and has a job-level `if:` that can be false on a pull-request run. Allowlisted non-skipping forms: `always()`, `!cancelled()`, `true`, `success() \|\| failure()`, and conjunctions of those with conditions that are always true on a pull request (`github.ref != 'refs/heads/…'`, `github.event_name != 'push'` and similar). Every other expression is treated as skippable. | A required check that goes green without running because a label, an actor, a path filter, or a merge-queue event made its condition false. |
| `GT-CONTINUE-ON-ERROR` | `continue-on-error` on a step that runs tests or on a job that runs tests, when it is `true`, or when it is an expression that some leg of the job's static matrix makes true (the expression is evaluated for every leg; the finding names how many). An expression that cannot be evaluated (other contexts, a dynamic matrix) is UNKNOWN; one that no leg makes true is not reported. | Test failures that leave the job (step level) or the workflow run and its dependents (job level) green. |
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
| `EC-EXIT-BEFORE-ASSERT` | `sys.exit`, `exit`, `quit`, `os._exit`, `raise SystemExit`, `pytest.exit(returncode=0)` with a success status, where the runner executes it for a test: module level of a test file, test functions, fixtures, pytest hooks, test-class lifecycle methods. The same in helpers, test doubles or nested functions is UNKNOWN (whether a test reaches it uncaught is not evaluated). Not reported: under `if __name__ == "__main__":`, inside `pytest.raises(SystemExit)` / `assertRaises(SystemExit)`, inside a `try` that catches `SystemExit`/`BaseException`, or with a non-zero literal status. A non-literal status is UNKNOWN. | A process that exits 0 before its assertions run, which a runner or CI reads as success. |
| `EC-EQUALITY-OVERRIDE` | Anywhere: an `__eq__`/`__ne__` (method, lambda, class attribute, attribute assignment, `setattr`) that never reads the other operand and whose every return is the same literal, such as `return True`. One that ignores the other operand but computes its result (state, a call) is UNKNOWN. In test code, any other `__eq__` is UNKNOWN (a comparison helper whose soundness cannot be judged). A constant `__eq__`/`__ne__` on an abstract class (one declaring an `@abstractmethod`) is UNKNOWN: its instances are its subclasses', which may override it. A value-object `__eq__` in implementation code that reads the other operand is **not** reported. | An object that equals everything, so every `assert result == expected` passes. |
| `EC-RUNNER-PATCHED` | In test code: patching reporting machinery (`TestReport`, `CallInfo`, `call_and_report`, unittest `TestResult`, `AssertionError` …) by assignment, `setattr`, `monkeypatch`, or `mock.patch`; writing outcome attributes (`outcome`, `longrepr`, `excinfo`, `exitstatus`, `wasxfail` …) inside reporting hooks; `force_result` in reporting hooks; `pytest_pyfunc_call`/`pytest_runtest_call` returning without calling the test; `TestResult` subclasses that drop failures; `wasSuccessful()` returning a constant. Other attribute writes inside reporting hooks, and any `pytest_report_teststatus` implementation, are UNKNOWN. The same constructs in pytest plugins outside test paths are UNKNOWN. Not reported: the documented `setattr(item, "rep_" + rep.when, rep)` pattern. | A test suite that reports failures as passes. |
| `EC-TESTS-NOT-RUN` | A test that no invocation found ever runs. FAIL: unconditionally skipped (`@pytest.mark.skip`, `skipif(True)`, `xfail(run=False)`, `unittest.skip`, module-level skip, a skip as the test's first statement), or deselected (`-k`, `-m`, `--deselect`) or ignored (`--ignore`, `--ignore-glob`, `collect_ignore`) in every invocation. UNKNOWN: outside collection scope (`norecursedirs`, `testpaths`, `python_files`, command-line paths), which is often test data; `-k` on parametrized tests; unresolvable invocations; collection hooks; conditional `collect_ignore`. See "Which tests actually run" below. | A test suite that looks large and green while part of it never executes. |
| `EC-NO-ASSERTION` | A test function that runs (pytest or unittest; not `conftest.py`, not fixtures, not `skip`ped, not excluded by the collection model) with no recognized assertion. Recognized: `assert`; calls whose name starts with `assert`; `pytest.raises`/`warns`/`deprecated_call`/`RaisesGroup`/`RaisesExc`, `assertRaises…`/`assertWarns…`/`assertLogs`; `pytest.fail`/`self.fail`; `raise AssertionError`; pytester `fnmatch_lines`-family and pexpect `expect`; zope.interface `verifyClass`/`verifyObject`; WebTest request methods with a `status=` expectation (`app.get(url, status=403)` raises on mismatch); `eq_`/`ne_`/`is_`-style comparison functions imported from a `testing` or `nose` package; a decorator that asserts; a fixture whose body (or returned closure) asserts, called by the test; and calls (bare or via `self.`/`cls.`) to functions, `functools.partial` aliases, or callable classes (`__call__`) that themselves (transitively) assert, defined in test paths, in test-support modules (`testing/`, `test_utils/`, `assertions.py` …), or named `test*` anywhere. A test whose only assertions sit inside a code string it executes elsewhere is UNKNOWN. Benchmarks (tests taking the pytest-benchmark/CodSpeed `benchmark` fixture or marked `@pytest.mark.benchmark`) measure speed, not correctness, and are counted in `stats.benchmarks_excluded` instead. | A test that passes whenever the code does not crash, so it cannot detect a wrong answer. |
| `EC-MOCK-ONLY` | A test that creates or injects mocks, asserts, and loads no name other than those mocks, values derived only from them, builtins and mock/pytest library names. Not reported: tests that call real code with a mock and then assert on the mock. | A green test that never reaches the code under test (`m.return_value = 3; assert m() == 3`). |
| `EC-SPECIAL-CASED` | (a) In implementation code: `if <parameter> == <literal>: return <literal>` in a function that also has a general return path, where the input literal is non-trivial, occurs in test files, and occurs nowhere else outside test files (not in other code, not in docs). (b) Implementation code that reads `PYTEST_CURRENT_TEST` or `PYTEST_VERSION` from the environment (`os.environ.get`, `os.getenv`, `os.environ[...]`, `in os.environ`), reads `sys._called_from_test` (attribute, `hasattr`, `getattr`), or checks for `pytest`/`unittest` in `sys.modules`. The same strings merely present in code (a linter's pattern table) do not count. Test infrastructure (files importing pytest, pytest plugins, noxfile, setup.py) is excluded from (b). | Code that returns the expected answer for the test's input only, or behaves differently under test than in production. |
| `EC-ASSERTION-NONSTANDARD` | Assertions that cannot fail or cannot run: `assert <truthy constant>`, `assert (x, "msg")`, `assert x is x` with `x` a plain name, `assert … or True`, `assertTrue(a, <non-string constant>)`, `assert m.called_once_with(…)` (auto-created Mock attribute), bare `m.assert_called_once` without a call, an assertion inside `try` whose handler catches `AssertionError`/`Exception` and does nothing (only `pass`/`continue`/`break`) with no failing `else:`, and an assertion after a bare call inside a `pytest.raises`/`assertRaises` block with no explicit `raise` after it. Not reported: `x == x` and `x.attr is x.attr` (both can fail: `__eq__`, property caching). This is an operational definition; it does not reproduce the taxonomy of any cited study. | Assertions that look like verification but verify nothing. |

## Measuring the detector

`tools/seeded_eval.py` scores the detector against an external corpus of
tamper variants and benign look-alikes (a directory per variant plus a
`manifest.json` naming each variant's target check and kind). It reports, per
check, how many tamper variants were detected, abstained on (UNKNOWN), or
missed, and how many benign variants raised a false alarm, both in isolation
and overlaid onto real host repositories. The corpus must come from someone
who has not read this code; a corpus written by the detector's author
measures only the author's imagination.

```sh
python tools/seeded_eval.py --corpus CORPUS_DIR --host path/to/host-repo --out results.json
```

### Evidence channel (JavaScript / TypeScript)

These carry a `-JS` suffix; their precision is measured separately.

| ID | Detects | Failure it prevents |
|---|---|---|
| `EC-EXIT-BEFORE-ASSERT-JS` | `process.exit()` / `process.exit(0)` in a test file. A non-literal status is UNKNOWN. | The runner ends with success before the remaining assertions run. |
| `EC-RUNNER-PATCHED-JS` | `expect.extend` matchers whose every returned `pass` is literal `true`; assignments to `expect`, `it`, `test`, `describe`, `assert` or their `global`/`globalThis` properties. | Failures reported as passes. |
| `EC-TESTS-NOT-RUN-JS` | `.skip`, `xit`, `xdescribe` (and tests inside them), `.todo`, tests with a title and no body (a call that produces the body, `it(title, wrap(fn))`, and an ava macro `test(title, macro, …args)` are bodies), and a committed `.only`/`fit`/`fdescribe` that excludes the other tests in the file under jest or mocha. Not reported for vitest-only projects (vitest fails CI runs on `.only`). `.only` with no identifiable framework is UNKNOWN. Conditional skips (`skipIf`, `runIf`, ternaries) are not evaluated. | Tests that count as evidence and never execute. |
| `EC-NO-ASSERTION-JS` | A test case with no assertion the detector can see. Recognized: `expect`/`assert`/`should` chains; node:test and ava `t.*` assertions; `sinon.assert`; supertest-style `.expect(...)`; testing-library `getBy*`/`findBy*` queries and cypress `cy.contains`/`.should` (they throw); a `throw`; node:test `t.assert.*`; `@matteo.collina/tspl` plans (`plan.equal`, with `const plan = tspl(t, …)`); an assertion method passed to a checker (`check(assert.equal, a, b)`); any call whose name starts with `assert` or `expect` followed by a capital (`assertEqual<A, B>(true)`, `util.assertNever(x)`); calls to asserting helpers (functions, `.bind` aliases, ava `test.macro` macros, and asserting functions passed as arguments) defined in test files or test-utility files. In files vitest type-checks (`*.test-d.*`, or a vitest/vite config with `typecheck: { enabled: true }`, or a package script running `vitest --typecheck`), `// @ts-expect-error` and `satisfies` count as assertions. A test body produced by a call (`it(title, withSetup(async () => {…}))`) is analyzed through the function it wraps; with no inline function it is UNKNOWN, as is a test whose body is a function reference defined elsewhere. | A test that passes whenever the code does not throw. |
| `EC-ASSERTION-NONSTANDARD-JS` | `expect(x);` with no matcher; a jest/vitest matcher referenced but not called (`expect(x).toBeTruthy;`; chai's property assertions are real and not reported); `expect(<literal>)` against a literal that makes a pure matcher always pass (`expect(true).toBe(true)`; literals that differ always fail and are not reported); `assert(<truthy literal>)` when `assert` is not a local function; `.resolves`/`.rejects` assertions neither awaited nor returned (an element of an awaited `Promise.all([...])` counts as awaited). | Assertions that look like verification but verify nothing, or may not run. |

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
