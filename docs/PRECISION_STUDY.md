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

## Results

(Filled in after the run.)
