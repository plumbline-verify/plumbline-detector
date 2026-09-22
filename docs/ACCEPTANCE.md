# Phase A acceptance record

Detector schema 1.1.0 (thirteen checks). Environment: CPython 3.13, PyYAML 6.0.3. Schema 1.0.0 was the first handoff; 1.1.0 added EC-TESTS-NOT-RUN and the pytest collection model (section at the end).

## Criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Every Python and GitHub Actions check passes on a known-good fixture, fires on a known-bad fixture, and returns UNKNOWN on absent or unparseable input. | `tests/test_fixtures.py`: a table of fixture → check → expected verdict and exact finding count, with PASS and FAIL cases for every check (a meta-test fails if a check lacks either); `test_empty_directory_is_unknown` (all checks); `test_gt_absent_workflows_unknown`; `test_malformed_workflow_never_passes` over six malformed workflow shapes (syntax error, duplicate key, merge key, wrong shape, non-UTF-8, empty file); `test_ec_unparseable_test_file_unknown`; `test_ec_no_tests_unknown`; `test_unread_file_blocks_pass`. |
| 2 | EC-EQUALITY-OVERRIDE discrimination: a value-object `__eq__` does not fire. | `fixtures/py/eq-good` (a `Money` value object with a field-comparing `__eq__`/`__ne__` in `pkg/`) is PASS with both definitions examined; `fixtures/py/eq-bad-impl` (an always-true `__eq__` in `pkg/`) is FAIL. `test_equality_discrimination_value_object_outside_tests`. |
| 3 | Two runs over identical input give byte-identical output. | `test_two_runs_byte_identical`, `test_location_independent` (same content at a different path gives the same record). Also checked on all seven real repositories below: two CLI runs each, compared with `cmp`, all identical. |
| 4 | Schema versioned and documented; any check change bumps the version. | `schema/record.schema.json` (validated in `test_record_validates_against_schema`); README "Output record". `tests/test_versioning.py` pins `SCHEMA_VERSION` to a SHA-256 fingerprint of all check-defining source; editing any check without bumping the version fails the suite. During development this test failed each time a check changed. Adding EC-TESTS-NOT-RUN after the 1.0.0 handoff bumped the schema to 1.1.0 and appended a new fingerprint; the 1.0.0 entry was left unchanged. |
| 5 | End-to-end on at least three real public repositories, with findings and false positives reported. | Seven repositories, below. |
| 6 | LIMITATIONS.md. | `LIMITATIONS.md`. |
| 7 | README with install, usage, every check and the failure it prevents. | `README.md`. |

Test suite: `python -m pytest` → 162 passed (including the two spelling-tool tests, which need hunspell). `tools/check_us_spelling.py` → OK.

## Real-repository runs

Each repository was fetched by hand with a shallow `git clone` of the default
branch on 2026-09-22 and analyzed offline. Nothing was reported to, filed
on, or sent to any of these projects.

| Repository | Commit | Primary language | Non-blank LOC | Python test files | Workflows |
|---|---|---|---|---|---|
| psf/requests | 611c6162cbc4 | Python | 9,841 | 15 | 8 |
| pallets/flask | d73fa1cdcbd8 | Python | 14,085 | 48 | 5 |
| encode/httpx | b5addb64f016 | Python | 14,376 | 37 | 2 |
| pydantic/pydantic | 915896d16383 | Python | 178,153 | 336 | 10 |
| pytest-dev/pytest | 6a9ba0f02f82 | Python | 98,493 | 143 | 6 |
| astral-sh/ruff | caf021af3e5c | Rust | 971,961 | 263 (+2,626 test-data files) | 22 |
| vitejs/vite | 1544bb1b7ac9 | TypeScript | 95,225 | 0 | 13 |

Verdicts under schema 1.1.0 (finding count in parentheses, `uN` = N unknown locations). The triage below was done on the 1.0.0 run; where 1.1.0 changed a number, the 1.1.0 section at the end says so.

| Check | requests | flask | httpx | pydantic | pytest | ruff | vite |
|---|---|---|---|---|---|---|---|
| GT-SKIP-SATISFIES | UNKNOWN u1 | UNKNOWN u1 | UNKNOWN u1 | PASS | PASS | PASS | FAIL (2) |
| GT-CONTINUE-ON-ERROR | PASS | PASS | PASS | PASS | FAIL (1) | PASS | PASS |
| GT-AGGREGATOR-PERMISSIVE | UNKNOWN | UNKNOWN | UNKNOWN | PASS | PASS | PASS | FAIL (2) |
| GT-NO-PROPAGATION | UNKNOWN u1 | UNKNOWN u1 | UNKNOWN u1 | UNKNOWN u27 | PASS | UNKNOWN u14 | UNKNOWN u2 |
| GT-NO-GATE | FAIL (1) | FAIL (1) | FAIL (1) | FAIL (1) | FAIL (1) | FAIL (1) | FAIL (1) |
| EC-EXIT-BEFORE-ASSERT | PASS | PASS | PASS | PASS | PASS | UNKNOWN u3 | UNKNOWN |
| EC-EQUALITY-OVERRIDE | PASS | PASS | PASS | FAIL (2) u18 | UNKNOWN u5 | UNKNOWN u31 | UNKNOWN |
| EC-RUNNER-PATCHED | PASS | PASS | PASS | PASS | UNKNOWN u49 | UNKNOWN u3 | UNKNOWN |
| EC-TESTS-NOT-RUN | FAIL (1) | PASS | PASS | FAIL (3) u1 | FAIL (3) u59 | UNKNOWN u7 | UNKNOWN |
| EC-NO-ASSERTION | FAIL (10) | FAIL (1) | FAIL (2) | FAIL (168) | FAIL (27) | FAIL (1) u3 | UNKNOWN |
| EC-MOCK-ONLY | PASS | PASS | PASS | PASS | PASS | UNKNOWN u3 | UNKNOWN |
| EC-SPECIAL-CASED | PASS | PASS | PASS | PASS | PASS | UNKNOWN u31 | UNKNOWN |
| EC-ASSERTION-NONSTANDARD | PASS | PASS | PASS | FAIL (8) | FAIL (1) | FAIL (3) u3 | UNKNOWN |

Runtime: under 1 s for the small repositories, 5–10 s for pydantic, pytest and ruff.

## Triage

"True positive" below means the construct the check describes is present and
has the stated effect. It does not mean the project is careless; many of
these are deliberate. Where a count was triaged by sample rather than in
full, that is said.

### Gate topology

- **GT-NO-GATE fired on all seven.** None commits branch protection or
  rulesets. This is the expected evidence-absence result (see LIMITATIONS),
  not seven defects. It carries no discrimination on public repositories.
- **vite, GT-SKIP-SATISFIES (2) and GT-AGGREGATOR-PERMISSIVE (2): true
  positives on the inferred basis.** `test-passed`, named "Build & Test Passed
  or Skipped", has `if: (!cancelled() && !failure())` and `needs: test`. When
  `test` fails, `!failure()` is false, the job is skipped, and a skipped job
  reports Success. Its sibling `test-failed` runs on failure and only echoes,
  so it is green too. Whether either is the required check could not be
  confirmed from the snapshot.
- **ruff, GT-SKIP-SATISFIES and GT-AGGREGATOR-PERMISSIVE: false positive in
  the first run, fixed.** The aggregator `required-checks-passed` has
  `if: always() && github.ref != 'refs/heads/main'`, which cannot be false on
  a pull request. The detector originally treated every non-allowlisted
  expression as skippable and fired. The allowlist now includes conjuncts
  that are true on every pull-request run; a discrimination fixture
  (`skip-discrim-pr-true`) and a counter-fixture where the condition is false
  on merge-queue events (`skip-bad-merge-queue`) were added. The same
  aggregator verifies through `toJSON(needs)` and `jq`, a form the detector
  also did not recognize at first; it is recognized now (`agg-good-tojson`).
- **pytest, GT-CONTINUE-ON-ERROR (1): true positive, deliberate.** The test
  matrix job has `continue-on-error: ${{ matrix.xfail && true || false }}`;
  seven matrix entries set `xfail: true`, so their test failures do not fail
  the run.
- **GT-NO-PROPAGATION**: UNKNOWN everywhere except pytest. On pydantic (27),
  ruff (14) and vite (2) these are test jobs not wired into the aggregator the
  detector inferred as the gate. Spot-checked: ruff's `cargo-test-linux-release`
  and `cargo-test-other`, and pydantic's `core-test-builds-arch`, are indeed
  absent from their aggregator's `needs:`. Whether they are required directly
  in settings is not visible, so they are reported as UNKNOWN, not FAIL.
  requests, flask and httpx have no aggregator and declare nothing, so there
  is no required set to test against.

### Evidence channel

- **EC-NO-ASSERTION.** requests (10): all ten reviewed; all are tests with no
  assertion (attribute-access smoke tests such as `requests.packages.idna`,
  "does not raise" tests). flask (1): reviewed; `test_werkzeug_passthrough_errors`
  records `passthrough_errors` into a dict through a monkeypatched
  `run_simple` and never asserts on it: a true positive and the most interesting single finding in the run.
  httpx (2): reviewed; two "close does not raise" tests. pydantic (168): 115
  are in benchmark files (benchmarks, not verification: true to the
  definition); the other 53 were not individually reviewed; the one sampled
  (`test_generics.py`, subscripting a generic model) is a smoke test.
  pytest (57): 27 are in `testing/example_scripts/`, which are inputs for
  pytest's own tests, and 4 are documentation examples under `doc/`: those 31
  are false positives of scope (test data classified as tests). Of the other
  26, two were reviewed (a pytester run whose result is never checked, a
  `chown` that must not raise): both true positives. ruff (7): six in
  lint-rule fixture files and one in a completion-evaluation input, all test
  data rather than tests: false positives of scope.
  - In the first run pytest showed 509 findings. Most came from pytester's
    `result.stdout.fnmatch_lines(...)`, which raises on mismatch but has no
    `assert` in its name; it and pexpect's `expect` were added to the
    assertion allowlist. A `@pytest.fixture` named `test_apps` in flask's
    `conftest.py` was also reported as a test; fixtures and `conftest.py` are
    now excluded from test discovery.
- **EC-ASSERTION-NONSTANDARD.** pydantic (8): all reviewed. Six are
  assertions placed inside a `pytest.raises` block after the call that raises
  (for example in `pydantic-core/tests/validators/test_is_instance.py`), so
  they never execute: true positives, genuinely dead assertions. One is a
  false positive: in `tests/test_edge_cases.py` the assertion itself is the
  raising statement and the preceding bare call is a list `append`. One is an
  `assert True` in an exception handler: true to the pattern, harmless (the
  real check is an `assert False` in the `try`). pytest (1): `assert True or
  explode` in `test_assertrewrite.py`, deliberately testing short-circuit
  rewriting: true to the pattern, benign. ruff (3): tuple and constant
  assertions in the lint fixture for pyflakes rule F631, which exists to flag
  exactly this pattern: false positives of scope (test data).
  - In the first run `assert x == x` was reported as a tautology. That was
    wrong: `==` invokes `__eq__` and can fail, and pydantic and pytest use it
    to test reflexivity. The pattern now covers only `is`. `assert False`
    used as a should-have-raised guard was also removed from the
    swallowed/unreachable patterns after pydantic's `test_migration.py`
    showed it.
- **EC-EQUALITY-OVERRIDE.** pydantic (2): `_ALWAYS_EQ.__eq__`/`__ne__` in
  `pydantic-core/tests/test_tzinfo.py`, an object "equal to anything" used to
  test comparison protocol. True to the pattern (comparisons against it
  verify nothing); benign intent. The 18 pydantic UNKNOWNs are other `__eq__`
  definitions in test code (6 in a benchmark file), not individually
  reviewed; the 5 pytest UNKNOWNs are field-comparing `__eq__` helpers in
  `testing/`. The check does not judge these. ruff's 31 UNKNOWNs are all parse failures: 3 deliberately invalid
  `*_test.py` files under `crates/ruff_python_parser/resources/inline/err/`
  and 28 incomplete-code inputs under `crates/ty_completion_eval/truth/`.
- **EC-RUNNER-PATCHED.** pytest (47 UNKNOWN): pytest's own `src/_pytest/`
  hook implementations rewrite reports because that is what a test runner
  does. In the first run these were 17 FAILs; plugin code outside test paths
  now reports UNKNOWN instead. No repository had a finding in test code.
- **EC-SPECIAL-CASED.** First run: 4 FAILs in pytest's
  `src/_pytest/config/__init__.py` for reading `PYTEST_VERSION`, which is
  pytest's own implementation. Files importing pytest and pytest's own package
  are now test infrastructure. No findings remain on any repository, so this
  check's precision on real code is unmeasured.
- **EC-EXIT-BEFORE-ASSERT, EC-MOCK-ONLY**: no findings on any repository;
  precision unmeasured. In the first run, ruff's lint fixtures produced 29
  exit findings (fixture files that contain `sys.exit(0)` because a lint rule
  is about it); test-data classification removed them.

### Self-run

Running the detector on its own repository produced four EC-SPECIAL-CASED
findings in `src/plumbline_detector/py/checks.py`: the detector's own table of
probe strings (`"PYTEST_CURRENT_TEST"` and others) matched, because the check
looked for the strings anywhere in implementation code. That is the linter
false-positive class. The check now requires an actual read (environment
lookup, `sys` attribute, `sys.modules` membership); fixture
`special-discrim-table` (strings in a table, PASS) and `special-bad-probe2`
(reads via `from os import environ` and `hasattr(sys, ...)`, FAIL) were
added. Re-running the seven repositories after this change gave identical
verdicts and counts. The remaining self-run findings are the deliberately
defective fixture test files under `fixtures/`; the defective helper and
implementation files there are classified as test data and are not analyzed,
which is itself a live demonstration of the test-data blind spot described
in LIMITATIONS.md.

### What this run does and does not show

- The checks fire on real code, and several findings are real hollow
  evidence (dead assertions in pydantic-core, an assertion-free flask test
  that collects a value and never checks it, a permissive aggregator in vite).
- Every false-positive class found was either fixed with a discrimination
  fixture or is documented above and in LIMITATIONS.md. The fixes were made
  after looking at these repositories, so these seven are no longer an
  unbiased sample for measuring precision. Phase B must use data the detector
  has not been tuned on.
- None of the seven is expected to contain deliberate tampering, so this run
  says nothing about recall against an adversary.

## Schema 1.1.0: which tests actually run

Added: the pytest collection model and `EC-TESTS-NOT-RUN`. Re-run on the
same seven commits; two runs per repository, byte-identical.

- **EC-TESTS-NOT-RUN findings, all reviewed, all true positives:** requests
  (1): `test_request_recovery`, `@pytest.mark.skip` ("fails
  non-deterministically under pytest-xdist"). pydantic (3 groups, 7 tests):
  `@pytest.mark.skip` tests in `tests/test_main.py` (5, "not implemented"),
  `tests/test_generics.py` and `tests/test_computed_fields.py`. pytest (3 groups,
  4 tests): `@pytest.mark.skip` in `testing/acceptance_test.py` ("Test is not
  isolated") and `testing/test_warnings.py` (2), and
  `@pytest.mark.xfail(run=False)` in `testing/_py/test_local.py`. These are
  tests that are present, counted, and never executed.
- **UNKNOWNs:** pytest (59): 54 are test files under
  `testing/example_scripts/` (excluded by `norecursedirs`) or outside
  `testpaths`, which are pytest's own test inputs; 5 are conftest collection
  hooks. pydantic (1): a Makefile invocation with shell variables. ruff (7):
  four files outside any collection root (two lint fixtures, one
  completion-evaluation input, one benchmark script) and three parse
  failures.
- **Effect on EC-NO-ASSERTION:** tests outside collection scope are no longer
  counted. pytest went from 57 findings to 27 (the 27 in
  `testing/example_scripts/` and 4 in `doc/` are gone; the `python_files`
  setting added `testing/python/*.py` as test code). ruff went from 7 to 1.
  Other repositories unchanged.
- **Detector defects found in this run and fixed** (each with a fixture):
  - pytest's main tox command, `{env:_PYTEST_TOX_COVERAGE_RUN:} pytest
    {posargs:{env:_PYTEST_TOX_DEFAULT_POSARGS:}}`, was not recognized
    (nested tox substitutions), and `changedir` was ignored; every pytest test
    was reported as outside collection scope. Tox substitutions are now
    resolved innermost-first.
  - Any `-p` plugin flag, and `--pyargs`, made an invocation unresolvable;
    and one unresolvable invocation marked every test in the repository as
    run. Now `-p` is followed, `--pyargs` names are resolved to paths, and
    an unresolvable invocation turns only the otherwise-unrun tests into
    UNKNOWN.
  - Once `testing/python/*.py` became test code, two new FAILs appeared in
    pytest, both detector errors: a `pytest_pyfunc_call` hook defined inside
    a test on a plugin registered with a nested pytester session was treated
    as patching the real session (now UNKNOWN), and `except
    pytest.fail.Exception` was read as `except Exception` because only the
    last name component was compared (now exact names). Fixture
    `runner-discrim-nested` covers both.
- **Not measured:** how often "runs" is wrong because an invocation the
  model accepts is never actually executed by CI (see LIMITATIONS, "It
  unions invocations").
