# Limitations

This file states what the detector cannot see. It is written to be harsher
than a critic would be. If you are about to rely on a PASS, read all of it.

## What a PASS means, and what it does not

A PASS means: the detector had input for that check, parsed all of it, and
none of its patterns matched. It does **not** mean the evidence is real. Each
check looks for a short list of specific constructs. Hollow evidence built
from any construct not on that list passes. The detector is a floor, not a
certificate.

The checks are syntactic and static. They cannot tell what a test verifies,
only whether it has certain shapes. A test with a meaningful-looking
assertion on the wrong property, a weak tolerance, a tautology hidden behind
a helper, or an expected value copied from the implementation's own output
passes every check here. So do tests with correct assertions on inputs that
never exercise the defect. **The falsifiability gap (a test that would not
fail if the code were wrong) is detected only in its crudest forms.** Mutation
testing is the tool for that, and it needs to execute code, which this
detector never does.

## The five gaps, honestly

| Gap | Coverage |
|---|---|
| Proxy-coverage (execution without detection) | Partial: tests with no assertion, assertions that cannot fail or cannot run, mock-only tests. Tests with real but weak assertions are invisible. |
| Reproducibility (works warm, not cold) | **None.** Nothing here checks lockfiles, pinned dependencies, network use in tests, or whether a clean clone builds. |
| Falsifiability (would not fail if wrong) | Crude forms only (see above). |
| Invocation (the check never ran and reported success) | Partial, for GitHub Actions only: skippable required jobs, permissive aggregators, `continue-on-error`, test jobs that cannot reach a required check, exit-0-before-assert. Tests excluded by configuration (`-k`, `--deselect`, `norecursedirs`, `collect_ignore`, markers), test files never collected, and test steps skipped by a step-level `if:` are **not** detected. |
| Outcome (the measured thing is not the thing that matters) | **None.** This is a judgment about product intent that no static pattern can make. |

## Gate topology: what the snapshot does not contain

- **Branch protection and rulesets live in repository settings, not in the
  repository.** Almost no public repository commits them. `GT-NO-GATE` will
  therefore fire on almost every repository; it reports that the *artifact*
  carries no evidence of a gate, not that no gate exists. It fired on all
  seven repositories in the acceptance run. Treat it as "ask for the settings
  export", and pass the export with `--gate-file` or `--required-check`.
- Without a declared required set, the gate checks infer one from aggregator
  jobs. That inference is a heuristic: the real required checks may be
  different jobs, other workflows, or third-party status checks. Findings on
  an inferred basis are labeled `basis: "inferred"`; `GT-NO-PROPAGATION`
  reports them as UNKNOWN rather than FAIL for this reason.
- Only GitHub Actions is understood. GitLab CI, CircleCI, Jenkins, Azure
  Pipelines, Buildkite, Travis and every other CI system are invisible; a
  repository gated only by one of them is reported as having no workflows.
- Reusable workflows from other repositories (`uses: org/repo/...@ref`) and
  composite or JavaScript actions are opaque. A job that calls one is
  classified as "may run tests" and produces UNKNOWN where it matters. Local
  reusable workflows are followed for classification; their
  check-run names are matched approximately (`caller / callee`).
- Test-running is recognized by an allowlist of command patterns (`pytest`,
  `tox`, `npm test`, `cargo test`, `go test`, and others) and by job names
  containing "test". A test suite run through a wrapper script
  (`./ci.sh`, `make ci`, a custom action) is not recognized as tests, so
  `GT-CONTINUE-ON-ERROR` and `GT-NO-PROPAGATION` do not look at it. Conversely
  a job named "test-docs" that runs no tests is treated as a test job.
- Expression evaluation is minimal. A job-level `if:` counts as non-skipping
  only if it is built from a short allowlist of forms. Anything else is
  treated as skippable, including conditions that a human can see are always
  true on pull requests. That errs toward FAIL; it produced a false positive
  on ruff before the `github.ref != 'refs/heads/main'` form was added to the
  allowlist, and other forms will produce more.
- Aggregator verification is recognized by pattern (`re-actors/alls-green`,
  `needs.X.result` plus a way to exit non-zero, `toJSON(needs)` plus
  `exit 1`). The detector does not check that the script's logic is correct,
  e.g. whether it treats `cancelled` or `skipped` as failure. A script that
  reads the results and then ignores them passes if it contains `exit 1`
  anywhere.
- Required-check names are matched against job names by exact match, matrix
  suffix, and `${{ }}` wildcard. Check-run names set by third-party apps,
  names built from expressions GitHub resolves differently, and workflow-name
  prefixes are not modeled.
- Workflow-level `paths:`/`branches:` filters, `concurrency` cancellation,
  merge-queue configuration, required reviewers, CODEOWNERS, and who can
  bypass protection are not analyzed.
- The claim that a skipped job satisfies a required check rests on GitHub's
  documentation as quoted in the project brief. The detector does not verify
  GitHub's live behavior, which can change.

## Evidence-channel checks: what static analysis cannot see

- **Dynamic code defeats every check.** `getattr(mod, "Test" + "Report")`,
  `__import__`, `exec`, `importlib`, string-built attribute names, monkeypatching
  through a helper defined in another package, or patching done in a
  `sitecustomize.py`, `.pth` file, pytest plugin installed from PyPI, or an
  environment variable (`PYTEST_ADDOPTS`, `-p plugin`) are all invisible.
- **Name resolution is shallow.** Imports are resolved within a file only.
  An `__eq__` assigned from a function defined in another module is UNKNOWN;
  an assertion helper imported from a non-test package is recognized only if
  its name starts with `assert` or is on the library allowlist; a test that
  calls such a helper is otherwise reported as having no assertion (false
  positive) — or, if the helper shares a name with an asserting function in a
  test path, credited with one it may not have (false negative).
- **Only Python is analyzed.** JavaScript/TypeScript, Java, C#, Go, Rust
  tests are counted in the inventory and otherwise ignored. A repository whose
  tests are in those languages gets UNKNOWN for every EC check.
- **Python grammar is the interpreter's.** A file using syntax newer than the
  running Python, or Python 2 code, is a parse failure and makes the relevant
  checks UNKNOWN. Record `provenance.environment.python` alongside any result.
- **Test-path classification is by name and directory.** Tests in files that
  pytest is configured to collect under other names (`python_files`,
  `testpaths` in `pytest.ini`/`pyproject.toml`) are not seen as tests. Test
  helpers outside `tests/`/`test/` directories are treated as implementation
  code. Configuration files are not read.
- **Test-data classification can hide code.** A non-package `.py` file under
  `fixtures/`, `resources/`, `testdata/`, `test_data/`, `example_scripts/` or
  `snapshots/` is treated as data and not analyzed. A hollow helper placed
  there and imported via `sys.path` manipulation would be missed. `conftest.py`,
  `test_*.py`, `*_test.py` and `tests.py` files are always analyzed, wherever
  they are.
- `EC-EXIT-BEFORE-ASSERT` looks only at test paths. An exit in implementation
  code that tests call is not detected. `os.kill`, `signal`, `atexit`
  handlers that call `os._exit(0)`, and threads that exit the process are not
  detected.
- `EC-EQUALITY-OVERRIDE` detects an `__eq__` that never reads the other
  operand. An `__eq__` that reads it and returns `True` anyway (`other; return
  True`, `return other is other or True`) passes. `__hash__`, `__bool__`,
  `__lt__`, `__contains__`, `__instancecheck__` and `__getattr__` tricks are not
  checked. Legitimate always-equal sentinels in tests (e.g. an `ANY` matcher
  modeled on `unittest.mock.ANY`) **are** reported; the finding is literally
  true (comparisons against it verify nothing) but the intent is benign.
- `EC-RUNNER-PATCHED` knows pytest and unittest. Other runners (nose2,
  Robot, behave, ward, hypothesis internals, tox/nox wrappers that rewrite
  exit codes, shell `|| true` in CI) are not covered. In repositories that are
  themselves test frameworks or pytest plugins, reporting-rewrite code is the
  product; it is reported as UNKNOWN, which means a malicious plugin
  outside test paths is also only UNKNOWN.
- `EC-NO-ASSERTION` counts smoke tests ("it did not raise") and benchmarks as
  findings. That is accurate to the definition, and it will fire on most
  mature projects: in the acceptance run, 115 of the 168 findings in pydantic
  were in benchmark files. Use the count and the ratio in `stats`, not the
  verdict alone. It does not see assertions made by fixtures, by
  `hypothesis` strategies, by type checkers, by snapshot libraries that do not
  use an `assert` name, or by custom library helpers not on the allowlist.
- `EC-MOCK-ONLY` is deliberately narrow: any non-mock name in the test body
  (a fixture, an imported function, `self.x`) makes it not fire. A test whose
  real call is irrelevant to its assertions passes. Mocks provided by
  fixtures are not recognized as mocks. It produced no findings on the seven
  repositories in the acceptance run, so its false-positive rate on real code
  is not measured.
- `EC-SPECIAL-CASED` finds only the direct shape `if param == literal:
  return literal`. Lookup tables, `match` statements, dictionary dispatch,
  special cases computed from a hash of the input, and hard-coded outputs
  returned without a comparison are missed. A legitimate special case that
  happens to have the shape (an HTTP status mapping, a documented fast path
  whose value is not written anywhere outside tests) fires. Test-context
  probing is recognized only through `os.environ` / `os.getenv` reads with a
  literal key, `sys._called_from_test`, and `sys.modules` membership; probing
  through `sys.argv`, `inspect.stack()`, the `__main__` module, a copied
  environment dictionary, or a computed key is missed. It produced no
  findings on the acceptance repositories; its real-world precision is not
  measured.
- `EC-ASSERTION-NONSTANDARD` is an operational list of patterns, not the
  taxonomy of any published study. The "unreachable in raises-block" pattern
  assumes the first bare call is the one that raises; when the raising
  statement is the assertion itself after an unrelated call, it is a false
  positive (1 of 7 in the pydantic acceptance run).
- ImpossibleBench's other strategies are **not** checked: modifying test
  files (needs history or a reference copy of the tests) and recording call
  state across calls to game stateful tests.

## Things the record itself cannot vouch for

- The snapshot is whatever directory was given. The detector cannot tell
  whether it is complete, current, or the code that was deployed.
- `commit_sha` is read from `.git` metadata if present, or taken from the
  operator. The detector does not verify that the files match that commit.
- The record is deterministic for identical input, options, and
  environment. A different Python or PyYAML version can change parse results;
  both are recorded, and the ruleset fingerprint covers the detector's own
  code but not the interpreter.
- Symlinked content is not followed and files over 4 MiB are not read; both
  are counted, and unread files in a check's scope make it UNKNOWN, but
  content reachable only through a symlink is simply absent.

## Calibration

Nothing here has been calibrated against labeled data. The acceptance run
(docs/ACCEPTANCE.md) is seven repositories chosen by hand, triaged by
sampling, not by exhaustive review. No precision or recall figure in this
repository should be read as a measured rate. Phase B (Auditing Sabotage
Bench) is the first planned measurement; expect it to be sobering, since
sabotaged evaluation code in ML repositories mostly corrupts *what is
computed*, which is the outcome gap this detector does not address.
