# PR mode: false-alarm study

## Protocol (fixed before any run; committed before results)

**Question.** On ordinary merged changes to real repositories, how often
does PR mode raise a finding, and how often is a finding factually correct?

**Detector under test.** Commit `2be5f00`, schema 1.5.0. No change to check
code between the first run and the reported numbers.

**Repositories.** Twenty public repositories used in no earlier study
(development set, precision rounds 1–4), fixed here before cloning. If one
cannot be cloned it is reported missing, not replaced.

Python (12): jpadilla/pyjwt, Kludex/python-multipart,
pydantic/pydantic-extra-types, fsspec/filesystem_spec, pallets/blinker,
hynek/stamina, pypa/setuptools-scm, pypa/wheel, mkdocs/mkdocs,
tox-dev/pyproject-api, pypa/installer, hukkin/tomli.

JavaScript / TypeScript (8): unjs/h3, unjs/unstorage, pinojs/pino-pretty,
fastify/fastify-static, expressjs/multer, expressjs/body-parser,
jshttp/cookie, vercel/ms.

**Changes.** For each repository, the 30 most recent commits on the
default branch's first-parent history, each compared with its first
parent (for squash- or merge-based projects, one commit is one merged
change). Up to 600 changes. Commits whose parent is missing from the fetched
history are skipped and counted.

**Measures.**
- *Alarm rate*: the share of changes with at least one PR-mode finding.
- *Factual precision*: every finding (or 60 drawn at random with seed
  20260924 if there are more) is labeled by independent review agents,
  who see the change's diff and both revisions:
  - **TP**: the change did what the finding says (the assertions were
    removed, the test does not run afterward, the tests are gone, the
    tampering construct was introduced).
  - **FP**: it did not (a count artifact, a rename or move the detector
    missed, a construct that was already there).
  Each TP is additionally marked *benign* (a reasonable change a reviewer
  would accept, such as deleting an obsolete test) or *weakening* (the
  change reduced verification without an evident replacement). The benign
  share is reported; it is not counted against precision.
- The author audits a seeded 20% (seed 20260925) of labels.

**Decision rules, fixed now.**
- PR mode is fit to ship as a default-on check if factual precision is at
  least 90% with a 95% Wilson lower bound of at least 80%, and the alarm
  rate is at most 10% of changes.
- If factual precision is below 80%, PR mode is not shipped; the causes
  are reported and the design revisited.
- In between, it ships as advisory, with the causes reported.

**What is not measured.** Recall: whether PR mode catches real agent
tampering. That needs a benchmark of agent-authored weakening (see
docs/PHASE_B.md, "What would measure this detector").

## Results (detector `2be5f00`, schema 1.5.0)

**Coverage.** 19 of 20 repositories; pallets/blinker could not be cloned
(the host asked for credentials) and is reported missing, not replaced.
570 changes replayed; none skipped, no errors. Commits are in
`docs/pr_study/repositories.json`; every finding and its label is in
`docs/pr_study/labeled_findings.jsonl`.

**Alarm rate: 12 of 570 changes (2.1%).** Meets the pre-registered ceiling
of 10%.

**Factual precision: 9 of 14 findings (64%; 95% Wilson interval 39–84%).**
Below the pre-registered 80% floor. **By the decision rule, PR mode is not
shipped at schema 1.5.0**; the causes are reported and the design revisited.

| Check | Findings | TP | FP |
|---|---|---|---|
| PR-TESTS-REMOVED | 7 | 5 | 2 |
| PR-NEW-TAMPERING | 4 | 1 | 3 |
| PR-ASSERTIONS-REMOVED | 2 | 2 | 0 |
| PR-TESTS-DISABLED | 1 | 1 | 0 |

**All nine true findings were benign**: tests removed with the feature
they covered, an obsolete benchmark replaced by a stronger test, a test
replaced by a pre-commit hook, an expected-failure branch removed because
the parser gained support, `continue-on-error` added for a pre-release
Python leg. On these twenty well-maintained, human-maintained
repositories, PR mode found no change that weakened verification without
a reason. That is a base rate worth knowing: the product's value depends
on agent-authored changes, which this study did not include.

**Causes of the five false positives.**
1. *Pre-existing CI constructs re-reported (3, PR-NEW-TAMPERING).* A
   conditional `continue-on-error` and an aggregator without `if:` were
   already present; the change only added matrix legs or renamed a needed
   job. "New" was decided by finding identifier, which includes the
   message, and the message contains the leg count and the needs list.
2. *Tests moved to a renamed class in another file (2, PR-TESTS-REMOVED).*
   Re-added tests were matched by class-qualified name, so a move from a
   module-level or differently named class was not recognized.

Two TPs are overstated in their wording: a count of 30 removed tests where
many were folded into `it.each` tables (some genuinely removed), and a
"does not run" for an `xfail(run=False)` limited to Python below 3.9.

**Audit.** The author checked the seeded 20% (PR#4, PR#11, PR#14) against
the repositories' history and agrees with all three.

**What changes next (to be measured on fresh repositories, not these):**
decide "new" for tampering findings by construct identity (check, file,
job or test), not by message; match removed tests to re-added ones by
function name without the class and by body; report partial effects
(matrix legs, Python versions) as partial.
