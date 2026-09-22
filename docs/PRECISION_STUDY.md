# Held-out precision study

## Protocol (fixed before any run; committed before results)

**Question.** When the detector reports a finding on a repository it was not
tuned on, how often is the finding correct?

**Detector under test.** Commit `ebeaaf0`, schema 1.1.0, ruleset fingerprint
`sha256:5b770029ad9baccae07647322b7e8230d64bef5237fbddda25d43f1cc7c76678`.
No change to check code is made between the first run and the reported
numbers. Defects found during the study are fixed afterward, in later
commits, and do not alter the numbers reported here.

**Repositories.** Twenty public Python projects, none used during
development (the seven in ACCEPTANCE.md are excluded). Chosen for spread
(web frameworks, CLIs, libraries, tooling, a unittest-runner project), not
for expected results, and fixed here before cloning:

pallets/click, pallets/jinja, pallets/werkzeug, encode/starlette,
fastapi/fastapi, psf/black, python-attrs/attrs, pypa/packaging,
Textualize/rich, marshmallow-code/marshmallow, scrapy/scrapy, celery/celery,
aio-libs/aiohttp, python-poetry/poetry, tox-dev/tox, pytest-dev/pytest-mock,
httpie/cli, django/django, sqlalchemy/sqlalchemy, python/mypy.

Each is a shallow clone of the default branch; the commit is recorded.

**Sampling.** For each check, all findings across the twenty repositories are
pooled. If a check has 40 findings or fewer, every finding is labeled;
otherwise 40 are drawn uniformly at random with a fixed seed (20260922).
GT-NO-GATE is reported but not labeled: it is an evidence-absence result
whose precision is not meaningful on public repositories (see LIMITATIONS).

**Labels.** Each sampled finding is labeled against the check's definition in
README.md:

- **TP** — the construct the check describes is present at that location and
  has the stated effect.
- **FP-detector** — the construct is not present, or does not have the
  stated effect (a detector error).
- **FP-scope** — the construct is present, but the location is not what the
  check is about (for example, test data or a test of the test framework
  itself), so the finding misleads.

A TP says nothing about intent: a deliberate `@pytest.mark.skip` is a TP of
EC-TESTS-NOT-RUN. Precision = TP / (TP + FP-detector + FP-scope), reported
with a 95% Wilson interval.

**Labelers.** Findings are labeled by independent review agents given the
finding, the source around it, and the check definition, not the detector
code. The detector's author then audits a random 20% of the labels and
reports the agreement rate. Labels are not changed after the audit except
where the audit finds a factual error (for example, a misread line); every
such change is listed.

**What is not measured.** Recall. Nothing here says how many real defects
the detector misses.

## Results (round 1, detector `ebeaaf0`)

Run on 2026-09-22 over the twenty repositories at the commits listed in
`precision/round1/repositories.json`. Every labeled finding, with its label
and the labeler's one-sentence reason, is in
`precision/round1/labeled_findings.jsonl`.

**Erratum in the protocol above.** The ruleset fingerprint quoted in the
protocol (`sha256:5b77…`) is wrong: it is the value of an earlier,
never-released pin of schema 1.1.0. Commit `ebeaaf0`, the one the protocol
names, pins `sha256:3dc55876e94295047850de8c6df2aacdc8bea90303d712c25c60f6a30b75792b`,
and every record in this study carries that fingerprint. The code under test
is exactly `ebeaaf0` (the only later change before the run was this
document). The protocol text is left as committed.

### Precision

| Check | Findings (pool) | Labeled | TP | FP-detector | FP-scope | Precision | 95% CI |
|---|---|---|---|---|---|---|---|
| EC-TESTS-NOT-RUN | 19 | 19 | 17 | 2 | 0 | 89% | 69%–97% |
| EC-NO-ASSERTION | 568 | 40 | 26 | 12 | 2 | 65% | 50%–78% |
| EC-ASSERTION-NONSTANDARD | 43 | 40 | 20 | 18 | 2 | 50% | 35%–65% |
| GT-CONTINUE-ON-ERROR | 3 | 3 | 1 | 2 | 0 | 33% | 6%–79% |
| EC-EXIT-BEFORE-ASSERT | 3 | 3 | 0 | 3 | 0 | 0% | 0%–56% |
| EC-EQUALITY-OVERRIDE | 2 | 2 | 0 | 1 | 1 | 0% | 0%–66% |
| EC-SPECIAL-CASED | 2 | 2 | 0 | 2 | 0 | 0% | 0%–66% |
| EC-MOCK-ONLY | 1 | 1 | 0 | 1 | 0 | 0% | 0%–79% |
| GT-AGGREGATOR-PERMISSIVE | 1 | 1 | 0 | 0 | 1 | 0% | 0%–79% |
| GT-SKIP-SATISFIES | 1 | 1 | 0 | 0 | 1 | 0% | 0%–79% |
| All labeled (unweighted) | | 112 | 64 | 41 | 7 | 57% | 48%–66% |

GT-NO-GATE fired on all twenty (not labeled, per protocol). GT-NO-PROPAGATION
and EC-RUNNER-PATCHED produced no findings.

**Plainly:** on code it had not seen, EC-TESTS-NOT-RUN was right about nine
times in ten; EC-NO-ASSERTION about two times in three; the
nonstandard-assertion patterns half the time; and the five rarely-firing
checks were wrong on every one of their eight findings. Those eight are too
few to estimate a rate, but zero out of eight is not a result to explain
away.

### Where the false positives came from

The 48 false positives come from nine recurring causes and four single cases:

| Cause | Check | FP |
|---|---|---|
| `x.attr is x.attr` treated as a tautology; it reads a property or descriptor twice and tests caching | EC-ASSERTION-NONSTANDARD | 14 |
| Assertion helpers not recognized: asserting decorators (`@collect_cases`, `@test_mutation`), assertion helpers in a non-test package (SQLAlchemy's `eq_`, `is_`), tests calling other test functions | EC-NO-ASSERTION | 12 |
| "Swallowed" assertions that are not: a handler that captures the exception for later checks, a `try/except/else: raise` "was not called" check, module-level capture of an exception class | EC-ASSERTION-NONSTANDARD | 5 |
| `SystemExit` raised inside a test double (a mock method, a monkeypatched stub) and caught by the code under test, or caught locally | EC-EXIT-BEFORE-ASSERT | 3 |
| Test data classified as tests (Django's test-runner sample apps, SQLAlchemy's mypy input files) | EC-NO-ASSERTION | 2 |
| `continue-on-error` expression that no active matrix entry makes true | GT-CONTINUE-ON-ERROR | 2 |
| Tests run by a tox environment declared in `[tool.tox]` in `pyproject.toml`, which is not read | EC-TESTS-NOT-RUN | 2 |
| A sequence literal (`["*"]`) counted as appearing only in tests; it also appears in implementation code | EC-SPECIAL-CASED | 2 |
| A release-gate job inferred to be the merge aggregator | GT-SKIP-SATISFIES, GT-AGGREGATOR-PERMISSIVE | 2 |
| Single cases: a stateful `__eq__` reported as constant; a deliberately pathological `__eq__` used as ORM input; a mock-only report on a test that calls real code first; an assertion after a call that does not raise | several | 4 |

### Label audit

The author reviewed 23 labels (a seeded random 20%, listed in
`precision/round1/score.md`) against the source and agreed with all 23. Two
were checked beyond the labeler's reasoning: click's `stress` tox
environment is declared in `pyproject.toml` `[tool.tox.env.stress]` and run
by `.github/workflows/nightly.yaml`; SQLAlchemy's matrix does include
`pypy-3.11`. No label was changed.

Labelers flagged some items as ambiguous (for example `assert True` placed
next to a real `assert False`, or a collected benchmark with no assertion);
they were labeled by the rule "intent does not matter", which counts them as
TP. A stricter reader would move up to seven TPs to FP-scope, which would
lower the figures above, not raise them.

### Notable true positives

- aiohttp `tests/test_web_exceptions.py::test_empty_text_304` evaluates
  `resp.text is None` without `assert`, so it checks nothing (and constructs
  `HTTPNoContent`, not a 304 response).
- SQLAlchemy `test/sql/test_metadata.py::test_auto_append_lowercase_table`:
  the loop body's only statement is `assert True`.
- SQLAlchemy runs its whole test step on PyPy 3.11 with `continue-on-error`,
  so failures there do not fail the job.
- Unconditionally skipped tests (counted in tests, from the 17 TP findings):
  scrapy 9, aiohttp 7, celery 3, httpie 3, poetry 3, mypy 1.

Observation only: none of these was reported to the projects.

### What this changes

The detector was fixed after this round (next commit). Those fixes were made
while looking at these twenty repositories, so this set can no longer
measure the fixed detector's precision. A second round on a new,
pre-registered set of repositories is needed to measure it.

## Round 2 protocol (fixed before any run; committed before results)

**Detector under test.** Commit `282dc09`, schema 1.2.0, ruleset fingerprint
`sha256:2db2c62cd6808bab42af532fe03d7a080afb1f0159614b65d0b1e43673dd0410` (read from `fingerprint.json` at that commit, not copied by hand).
No check code changes between the first round-2 run and the reported numbers.

**Repositories.** Twenty public Python projects used in neither the
development set (ACCEPTANCE.md) nor round 1, fixed here before cloning:

encode/uvicorn, fastapi/typer, python-jsonschema/jsonschema,
pallets/itsdangerous, urllib3/urllib3, pypa/pipx, pypa/virtualenv,
pypa/build, PyCQA/flake8, PyCQA/isort, pylint-dev/pylint, sphinx-doc/sphinx,
jazzband/pip-tools, joke2k/faker, arrow-py/arrow, dateutil/dateutil,
Delgan/loguru, tqdm/tqdm, hynek/structlog, python-trio/trio.

If a repository cannot be cloned, it is reported as missing, not replaced.

**Sampling, labels, labelers, audit.** As in round 1: pool per check, label
all if 40 or fewer, else 40 at random with seed 20260922; labels TP /
FP-detector / FP-scope against the README definitions; independent labeling
agents that do not see the detector code or round-1 results; the author
audits a seeded random 20% (seed 20260923). GT-NO-GATE is not labeled.

## Results (round 2, detector `dfb2c43`, schema 1.2.0)

Run over the twenty round-2 repositories at the commits in
`precision/round2/repositories.json`; all records carry the pre-registered
fingerprint `sha256:2db2c62c…`. Labeled findings are in
`precision/round2/labeled_findings.jsonl`. All twenty repositories cloned; in
sphinx, git could not re-encode two `.inc` test inputs on checkout (not
Python, not analyzed).

### Precision

| Check | Findings (pool) | Labeled | TP | FP-detector | FP-scope | Precision | 95% CI |
|---|---|---|---|---|---|---|---|
| GT-CONTINUE-ON-ERROR | 5 | 5 | 5 | 0 | 0 | 100% | 57%–100% |
| EC-EQUALITY-OVERRIDE | 6 | 6 | 5 | 0 | 1 | 83% | 44%–97% |
| EC-NO-ASSERTION | 273 | 40 | 25 | 15 | 0 | 62% | 47%–76% |
| EC-TESTS-NOT-RUN | 7 | 7 | 4 | 0 | 3 | 57% | 25%–84% |
| EC-ASSERTION-NONSTANDARD | 19 | 19 | 7 | 0 | 12 | 37% | 19%–59% |
| EC-EXIT-BEFORE-ASSERT | 5 | 5 | 0 | 1 | 4 | 0% | 0%–43% |
| GT-AGGREGATOR-PERMISSIVE | 1 | 1 | 0 | 0 | 1 | 0% | 0%–79% |
| All labeled (unweighted) | | 83 | 46 | 16 | 21 | 55% | 45%–66% |

**Plainly: overall precision did not improve.** Round 1 was 57% (48–66%);
round 2 is 55% (45–66%). The round-1 fixes removed their own causes (none of
round 1's nine recurring causes reappears below), but new data brought new
causes. The fixes did not generalize into higher precision.

### Where the false positives came from

| Cause | Check | FP | Kind |
|---|---|---|---|
| pylint's `tests/functional/` files: lint inputs that deliberately contain the patterns (constant asserts, `quit()`, an always-true `__eq__`, a skipped test) and are linted, never run | NONSTANDARD 12, EXIT 4, EQUALITY 1, TESTS-NOT-RUN 1 | 18 | scope |
| Assertion helper reached through `functools.partial` (isort's `partial(isort_test, ...)`) | NO-ASSERTION | 5 | detector |
| `pytest.RaisesGroup` / `pytest.RaisesExc` (pytest 8.4 APIs) not recognized | NO-ASSERTION | 3 | detector |
| Sphinx `tests/roots/` autodoc input modules, excluded by `collect_ignore` or holding `@overload` stubs named `test` | TESTS-NOT-RUN | 2 | scope |
| Assertions inside a code string executed in a web worker (urllib3 emscripten tests) | NO-ASSERTION | 2 | detector |
| Assertion helper reached through a parametrized callable, a fixture-returned closure, or a helper in a `_tests/` directory (not recognized as a test directory) | NO-ASSERTION | 3 | detector |
| A third-party validator that raises (`stdnum`), and warnings turned into errors | NO-ASSERTION | 2 | detector |
| `os._exit(0)` ending a forked child process; the parent reports the result | EXIT | 1 | detector |
| A coverage-upload job inferred to be the merge aggregator | AGGREGATOR | 1 | scope |

One repository, pylint, supplied 18 of the 37 false positives. A linter's
test inputs are made of exactly the patterns these checks look for. This
concentration is itself a finding about the detector: test-data
classification by directory name (`fixtures/`, `resources/` ...) misses the
layouts real projects use (`tests/functional/`, `tests/roots/`), and a single
such repository can swing a pooled estimate.

**Post-hoc views (not pre-registered; for diagnosis only).** Excluding
pylint, precision is 46/65 = 71%. Counting only detector errors (treating
FP-scope as excluded), precision is 46/62 = 74% in round 2 against 64/105 =
61% in round 1: the errors in reading code went down, the errors in knowing
what is test code went up.

### Label audit

The author reviewed 17 labels (seeded random 20%, listed in
`precision/round2/score.md`) and agreed with all 17. The audit found one
inconsistency between labelers outside the audited set: a faker test that
turns a warning into an error was labeled TP ("does not crash"), while a
dateutil test doing the same with `warnings.simplefilter("error")` was
labeled FP-detector. Both labels stand, as the protocol allows corrections
only for factual errors; moving either would change the overall figure by
about one point.

### Notable true positives

- typer `tests/test_tutorial/test_parameter_types/test_file/test_tutorial005.py`:
  `assert "Config line written"` asserts a non-empty string, which is always
  true.
- tqdm `test_envwrap_types`: `assert 1, "1" == nofallback()` and
  `assert 1.1, "1.1" == annotated()` assert the constants; the comparisons
  are the messages.
- pipx: an assertion after the raising call inside `pytest.raises`, which
  the repository's own lint suppression calls dead code.
- urllib3 runs six matrix legs (emscripten, Python 3.15) with
  `continue-on-error`; tqdm does so on Windows; typer's nightly CPython job
  and pipx's package test job are fully `continue-on-error`.

Observation only: none of these was reported to the projects.

### What round 2 says about the detector

1. Precision on unseen Python projects is about 55%, and fixing the last
   round's errors did not move it. Expect a long tail of project-specific
   patterns.
2. The dominant remaining problem is not reading code but knowing what is a
   test: test inputs for lint tools, documentation tools and parsers. That
   needs a better model of which files a test runner actually executes,
   not more patterns.
3. EC-NO-ASSERTION is stable at 62–65% and is limited by assertion helpers
   the static view cannot follow (`partial`, closures, code strings,
   third-party validators). Its findings should be read as "no assertion the
   detector can see", which the README already says.
4. The rarely-firing checks remain unmeasurable at this sample size: across
   both rounds, EC-EXIT-BEFORE-ASSERT has produced 8 findings and none was a
   true positive.
