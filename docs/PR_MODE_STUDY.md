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
