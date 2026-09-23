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

## Round 3 protocol (fixed before any run; committed before results)

**Detector under test.** Commit `ea36d78`, schema 1.3.0, ruleset fingerprint
`sha256:47147ca9f073da2cc48d5265613488eca4294726d7de9ff5ad9471b5f79d6e64` (read from `fingerprint.json` at that commit). No check code changes
between the first round-3 run and the reported numbers.

**Repositories.** None used in development, acceptance, round 1 or round 2.
If a repository cannot be cloned it is reported missing, not replaced.

Python (20): pallets/quart, encode/httpcore, aio-libs/yarl,
aio-libs/multidict, sqlalchemy/alembic, celery/kombu,
marshmallow-code/webargs, python-attrs/cattrs, benoitc/gunicorn,
bottlepy/bottle, falconry/falcon, tornadoweb/tornado, Pylons/pyramid,
PyCQA/pyflakes, PyCQA/pycodestyle, PyCQA/bandit, python-poetry/poetry-core,
Textualize/textual, pytest-dev/pytest-xdist, jazzband/django-debug-toolbar.

JavaScript / TypeScript (10): koajs/koa, fastify/fastify, date-fns/date-fns,
sindresorhus/got, lodash/lodash, pinojs/pino, remix-run/react-router,
TanStack/query, colinhacks/zod, reduxjs/redux-toolkit.

This is the first measurement of the `-JS` checks. The JS/TS development
set (express, vue core, axios, chalk, vite) is excluded.

**Sampling, labels, labelers, audit.** As in rounds 1 and 2: findings pooled
per check across all thirty repositories; all labeled if 40 or fewer, else
40 at random (seed 20260922); TP / FP-detector / FP-scope against the README
definitions; independent labeling agents without access to the detector code
or earlier rounds; the author audits a seeded random 20% (seed 20260923).
GT-NO-GATE is not labeled.

## Results (round 3, detector `ea36d78`, schema 1.3.0)

All thirty repositories cloned; every record carries the pre-registered
fingerprint `sha256:47147ca9…`. Labeled findings are in
`precision/round3/labeled_findings.jsonl`.

### Precision

| Check | Findings (pool) | Labeled | TP | FP-detector | FP-scope | Precision | 95% CI |
|---|---|---|---|---|---|---|---|
| EC-ASSERTION-NONSTANDARD-JS | 45 | 40 | 39 | 1 | 0 | 98% | 87%–100% |
| EC-TESTS-NOT-RUN | 14 | 14 | 10 | 4 | 0 | 71% | 45%–88% |
| EC-NO-ASSERTION | 445 | 40 | 26 | 6 | 8 | 65% | 50%–78% |
| EC-NO-ASSERTION-JS | 249 | 40 | 15 | 25 | 0 | 38% | 24%–53% |
| EC-TESTS-NOT-RUN-JS | 64 | 40 | 11 | 29 | 0 | 28% | 16%–43% |
| EC-ASSERTION-NONSTANDARD | 57 | 40 | 6 | 0 | 34 | 15% | 7%–29% |
| GT-CONTINUE-ON-ERROR | 2 | 2 | 2 | 0 | 0 | 100% | 34%–100% |
| EC-EXIT-BEFORE-ASSERT-JS | 1 | 1 | 1 | 0 | 0 | 100% | 21%–100% |
| EC-SPECIAL-CASED | 1 | 1 | 1 | 0 | 0 | 100% | 21%–100% |
| EC-EQUALITY-OVERRIDE | 1 | 1 | 0 | 1 | 0 | 0% | 0%–79% |
| GT-AGGREGATOR-PERMISSIVE | 2 | 2 | 0 | 0 | 2 | 0% | 0%–66% |
| GT-SKIP-SATISFIES | 2 | 2 | 0 | 0 | 2 | 0% | 0%–66% |
| All labeled (unweighted) | | 223 | 111 | 66 | 46 | 50% | 43%–56% |

Python checks 45/102 (44%); JS/TS checks 66/121 (55%).

**Plainly: overall precision is 50%, the third round in a row near that
figure (57%, 55%, 50%).** The fixes after each round remove that round's
causes; each new set of repositories brings new ones.

### Where the false positives came from

| Cause | Check | FP | Kind |
|---|---|---|---|
| pytest-xdist `example/loadscope/`: a scheduling demo whose `test_*.py` files hold `sleep(5); assert True`, outside `testpaths` | NONSTANDARD | 34 | scope |
| svelte-query tests whose body is `withEffectRoot(async () => …)`, a call returning the test function, read as "no body" | TESTS-NOT-RUN-JS 24 | 24 | detector |
| Type-level assertions (zod's `util.assertEqual<A, B>(true)`, `@ts-expect-error`, `satisfies`) enforced by `vitest --typecheck` | NO-ASSERTION-JS | 17 | detector |
| Assertions through `tspl` plans or helpers receiving an assertion function (`check(assert.equal, …)`) | NO-ASSERTION-JS | 6 | detector |
| Benchmarks with no assertion (labelers split; see below) | NO-ASSERTION | 6 | scope |
| Assertion APIs not recognized: webtest `status=`, `zope.interface.verify*`, SQLAlchemy's `eq_` used from alembic | NO-ASSERTION | 5 | detector |
| ava macro tests (`test(title, macro, …)`) read as "no body" | TESTS-NOT-RUN-JS | 5 | detector |
| Hypothesis tests deselected by `addopts` but run by dedicated CI jobs with `-m hypothesis` | TESTS-NOT-RUN | 4 | detector |
| An AI-agent workflow's `conclusion` job inferred to be the merge aggregator | GT-SKIP, GT-AGGREGATOR | 4 | scope |
| gunicorn `examples/` files excluded by `norecursedirs` but named like tests | NO-ASSERTION | 3 | scope 2, detector 1 |
| Single cases: `.rejects` inside `await Promise.all([...])`; ava `t.pass()`; node:test `t.assert.ifError`; a helper method reached through `pilot.app.…` | several | 4 | detector |

Two repository-specific patterns, pytest-xdist's example directory and
svelte-query's test-body helper, account for 58 of the 112 false
positives.

### Label audit

The author reviewed 45 labels (seeded random 20%) and agreed with all 45.
Labelers were inconsistent on one class: of 16 sampled benchmark functions
with no assertion, 10 were labeled TP ("collected and run, asserts
nothing") and 6 FP-scope ("a benchmark is not a correctness test"). Labels
stand as given; labeling all 16 one way or the other moves overall
precision between 45% and 52%.

### Post-hoc views (not pre-registered; for diagnosis only)

- Excluding pytest-xdist's `example/loadscope/`: 111/189 = 59%.
- Detector errors only, TP / (TP + FP-detector): 111/177 = 63% (round 1:
  61%, round 2: 74%).

### Notable true positives

- zod: dozens of `expect(x).toBeNull;` lines across its v3 and v4 test
  suites reference the matcher without calling it, so none of those checks
  runs; zod also has `expect(true).toBe(true)` as the entire body of tests.
- react-router: `expect(true).toBe(true)` as a test's only assertion, and
  eight tests inside an unconditional `describe.skip`.
- falcon: `assert ws.close_reason == reason or 'Bad Request'`, which parses
  as `(a == b) or 'Bad Request'` and cannot fail.
- pyramid: `assertTrue(result.body, b'foo')`, where `b'foo'` is the
  failure message, not a comparand.
- kombu: two assertions after the raising call inside `pytest.raises`.
- fastify: `process.exit(0)` in a test body (behind a guard that is false
  on supported Node versions) and a `test-unit` job with
  `continue-on-error: true`.

Observation only: none of these was reported to the projects.

### What three rounds say

1. Precision on unseen repositories has stayed at 50–57% across three
   versions of the detector. Each round's fixes work on that round's causes
   and do not raise the next round's figure. The error distribution is
   long-tailed and clustered: in every round, one or two repositories'
   idioms produce half the false positives.
2. Per-check precision is the useful number, and it is now shipped with every
   finding. EC-ASSERTION-NONSTANDARD-JS (98%, one round) and
   GT-CONTINUE-ON-ERROR (8 of 10 across rounds 1–3; 7 of 7 after the
   round-1 fix) are the strongest; EC-TESTS-NOT-RUN has ranged 57–89%. The
   others should be read as leads for review, not verdicts.
3. The remaining large classes are about context the checks do not model:
   which files a runner executes (example and demo directories), which
   helpers a framework provides (test-body wrappers, macros), and which
   checks happen at type-check time.

## Precision targets (set after round 3, before round 4)

A single pooled number hides what matters: whether a given finding can be
acted on without review. Targets are therefore per check, and each check's
grade in the output is computed from its latest measurement
(`src/plumbline_detector/record.py`, `grade`):

| Grade | Requirement (latest held-out round) | Meaning for a finding |
|---|---|---|
| verdict | n ≥ 20 labeled, precision ≥ 90%, 95% Wilson lower bound ≥ 80% | A confirmed defect often enough to act on without review. SARIF level `error`. |
| advisory | n ≥ 10, precision ≥ 70% | Usually right; review each one. SARIF `warning`. |
| experimental | anything else, including unmeasured | A lead. SARIF `note`. |

Program targets for the next held-out round: pooled precision ≥ 80%, and
every check that produced at least 20 findings at advisory grade or better.
A check that misses the advisory bar in two consecutive rounds is
redesigned or removed from the default operator set, not tuned again.

## How the detector learns

The detector does not change itself at run time. A run is a pure function of
the snapshot and the versioned ruleset, and that property is what makes a
record usable as evidence. Learning happens between versions, in a loop
whose every step is recorded:

1. **Measure** on repositories the current ruleset has never seen
   (pre-registered sample, blind labels, author audit).
2. **Cluster** the false positives by cause. Each cause becomes a rule
   change plus a discrimination fixture that fails without the change.
3. **Regress** on every earlier round's labels (`tools/regress_labels.py`).
   A lost true positive blocks the change unless the scope definition itself
   changed, which is then stated here and given to the next labelers.
4. **Version**: the ruleset fingerprint changes, so the schema version bumps.
5. **Recalibrate**: the next round's measurement replaces the old one in
   `measurements.json`, and every check's `grade` follows from it. A check
   earns or loses verdict grade on held-out evidence only, never on the
   repositories that shaped it.

## Round 3 follow-up (schema 1.4.0)

Fixes for the round-3 false-positive classes, each with a discrimination
fixture:

- Python: out-of-scope trees (`example/`, `examples/`, `bench/` outside
  every resolved invocation's scope) are not judged by the per-test quality
  checks; benchmarks are exempt from EC-NO-ASSERTION; WebTest `status=`,
  zope `verifyClass`/`verifyObject`, and `eq_`-family functions from testing
  packages count as assertions; a constant `__eq__` on an abstract class is
  UNKNOWN; `python -Im pytest`, `python -bb -m pytest`, `coverage run
  [options] -m pytest`, shebang scripts and action `run:` inputs are read as
  invocations.
- GitHub Actions: workflows whose `pull_request` trigger lists only
  non-code activity types (`labeled` …) are not PR-triggered for gate
  inference.
- JS/TS: call-produced test bodies, ava macros, tspl plans, `t.assert.*`,
  assertion methods passed as arguments, `assert*`/`expect*`-named calls,
  type-level assertions where vitest type-checks, and `.rejects` inside an
  awaited `Promise.all`.

**Scope decision (benchmarks).** Round-3 labelers split on benchmark
functions without assertions: 10 labeled TP, 6 FP-scope. From schema 1.4.0
EC-NO-ASSERTION is defined over correctness tests only; benchmarks are
counted in `stats.benchmarks_excluded`. Round-4 labelers receive this
definition. The 10 benchmark TPs appear as "lost" in the regression below
by design.

**Regression on rounds 1–3** (`tools/regress_labels.py`, schema 1.4.0; the
same repositories at the same commits): 210 of 221 labeled true positives
still reported, and all 11 no longer reported are benchmark functions (the
scope decision above); 189 of 197 labeled false positives no longer
reported (117 of 123 FP-detector, 72 of 74 FP-scope). These are the
repositories the fixes were written against, so the figures show that the
fixes do what they were meant to and break nothing labeled. They are **not**
a precision estimate; only a fresh held-out round is.
