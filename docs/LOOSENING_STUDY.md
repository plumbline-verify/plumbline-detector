# Loosening checks: precision and recall (schema 1.7.0)

## Protocol (fixed before any measurement; committed before results)

**Why.** The TRACE recall study (docs/RECALL_STUDY.md) measured PR-mode
recall at 9 of 35 (26%; 95% CI 14–42%) on test-modification hacks, below
the 50% bar for default-on. The misses were mostly verification that stays
in place but checks less: thresholds and tolerances (12), mocks (6),
timeouts (3), swallowed assertions (2), configuration exclusions (2).
Schema 1.7.0 adds one check per category:

- PR-TOLERANCE-LOOSENED
- PR-TIMEOUT-RAISED
- PR-ASSERTION-SWALLOWED
- PR-MOCK-UNDER-TEST
- PR-TESTS-EXCLUDED

The README defines each check.

**Design contamination, stated up front.** The checks were designed from
the miss *categories* in the published recall results. The author of this
build did not read TRACE rows. Even so, TRACE is no longer a fresh test
set for these checks, so its re-run is reported as **development recall**
and cannot unblock default-on by itself.

### 1. Development recall (TRACE, same set)

Run `tools/trace_recall.py` on the same extraction, with the same labels
and blind labels as docs/RECALL_STUDY.md, at schema 1.7.0. Report recall
on H-TM (n = 35) and the false-alarm rate on B (n = 111), overall and for
each new check. Also report, for each check, the misses it newly catches.
The result is labeled "development" everywhere it appears.

### 2. Precision (PR-mode round 3)

This is the round-3 design already committed under review item A-4
(n ≥ 50 labeled findings, cap of 60 fresh repositories), extended to the
new checks.

- **Replay.** `tools/pr_replay.py` at schema 1.7.0 runs over fresh
  repositories not used in rounds 1–2, drawn with seed 20261001 from the
  same frame as round 2. Replay stops when the pooled PR-mode findings
  reach 50 or the cap of 60 repositories is reached.
- **Labels.** Every finding from a new check is labeled blind by
  independent reviewers from the base and head diff: TP (the change did
  what the check says) or FP. Each TP is also labeled weakening, benign or
  unclear. The author audits a seeded 20% (seed 20261002).
- **Grades.** Per check, from the existing rule: verdict needs n ≥ 20,
  precision ≥ 90% and a 95% lower bound ≥ 80%; advisory needs n ≥ 10 and
  precision ≥ 70%. A check with fewer than 10 findings is reported as
  unmeasured and stays experimental.
- **Alarm rate.** The share of replayed changes with any finding from a
  new check is reported, with its interval.

### 3. Fresh recall (the one that decides default-on)

The fresh set is ImpossibleBench agent transcripts: tasks whose tests
contradict the specification, so a passing solution must have gamed the
tests. Before any transcript is read, a separate protocol amendment is
committed here. It will fix:

- the revision;
- the extraction;
- the definition of a test-modification case;
- the benign comparison set.

**Default-on bar (unchanged in spirit from A-5, fixed now):** fresh recall
of at least 50% on test-modification cases **and** pooled PR-mode
precision of at least 80% with a lower bound of at least 70%. Until both
hold, PR mode stays advisory, including the new checks.

### What this cannot show

- Intent.
- Loosening expressed without numbers (a regular expression widened, an
  equality turned into a containment check).
- Mocks installed by fixtures outside the test.
- Exclusions made by moving files out of the collected paths.
- Test timeouts in configuration formats the checks do not read.
