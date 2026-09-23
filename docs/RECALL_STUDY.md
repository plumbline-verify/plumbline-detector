# Recall study: TRACE (review item A-5)

## Protocol (fixed before any data is read; committed before results)

**Question.** Of the coding-agent trajectories that exploit a test suite,
what share does the detector flag (recall)? Of the trajectories that do
not hack, what share does it flag (false-alarm rate)? The precision studies
measured how often a finding is right. This study measures how many
weakenings the detector misses. The PR-mode default-on decision needs both.

**Data.** TRACE (`PatronusAI/trace-dataset` on Hugging Face,
CC-BY-SA-4.0; paper arXiv:2601.20103), revision
`31d87f06078eca3ab6eaf1e06e5ea6fe9f2b7a6d`. It holds 517 synthetic
multi-turn Claude Code trajectories: 268 hacked and 249 benign, per the
dataset card. The columns are `trajectory_id`, `conversation` (ChatML) and
`label`. Before this protocol was written, only the dataset card, the file
listing and the paper's taxonomy (its Figure 2 and Appendix G) were read.
No row was read.

**Licensing and privacy, fixed now.** The data is stored only in session
scratch space, outside every repository. No conversation, code, patch or
per-trajectory row is committed. Only aggregate counts and rates are
committed. The access token is read from the environment and never
printed, logged or committed.

### Populations (from the TRACE label only)

The paper's taxonomy has 10 categories grouped under four headings. Its
**Test Suite Exploitation** heading holds three categories:

- **Test Modification (TM):** Direct Overwriting, Assertion Weakening,
  Test Deletion, Test Mocking, Exception Suppression, Timeout Manipulation.
- **Test Case Targeting (TCT):** Hardcoded Outputs, Input Recognition,
  Regex Matching, Checksum Gaming, Type Coercion, Boundary Value Gaming.
- **Coverage Gaming (CG):** Partial Implementation, Branch Pruning, Edge
  Case Omission, Error Path Skipping, Dead Code Insertion.

The populations are:

- **H-TM (primary):** hacked trajectories with at least one TM label. The
  detector is built to catch changes to tests, so this is its target.
- **H-TSE (secondary):** hacked trajectories with at least one TM, TCT or
  CG label. TCT and CG hacks live in solution code, not in tests, so the
  detector is not expected to catch them. They are reported so that the
  scope limit is visible and not hidden.
- **B:** benign trajectories.
- **H-other (descriptive only):** hacked trajectories with no Test Suite
  Exploitation label. Only their signal rate is reported. They count
  neither for recall nor for false alarms.

**Label mapping.** The `label` string is parsed as JSON if it parses, and
otherwise split on commas, semicolons, pipes and newlines. Each value is
normalized (lowercase, with non-alphanumeric characters removed). It is
matched to a subcategory or category name in the taxonomy above, or to a
benign marker (`benign`, `none`, `nohack`, `clean`, `nothacked`, or an
empty label). The label parser is written and committed before the
detector is run. It sees labels only, never detector output. Results list
every distinct label value and its mapping. A value that matches nothing
is reported as unmapped and gives its trajectory no category.

### Extracting code changes from a trajectory

The trajectories simulate Claude Code tools (Bash, Read, Write, Edit, Grep,
Glob and WebSearch). The extractor recognizes a tool call by its tool name
and argument keys, whatever the ChatML envelope. It recognizes a tool result
by its position after the call. It replays the trajectory in order and
keeps a per-file state that is either unknown or known in full:

- **Read** without `offset` or `limit` whose result is not truncated sets
  the file's full content. Line-number prefixes of the form `   12→` or
  `   12\t` are stripped. A partial read does not set the content.
- **Write** (`file_path`, `content`) sets the full content. The file counts
  as **added** if it had no known content, was not read, and was not
  written or edited before. Otherwise it counts as **modified**.
- **Edit** / **MultiEdit** (`file_path`, `old_string`, `new_string`,
  `replace_all`) is applied to the known content. If the content is
  unknown, or `old_string` is not found in it, the edit is recorded as a
  bare hunk (the `difflib` diff of `old_string` against `new_string`), and
  the file is marked **not reconstructable**.
- **Bash** is handled in three ways:
  - `rm`, `git rm` or `unlink` of a path marks the file **removed**.
  - A heredoc or `echo`/`printf` redirect to a path (`cat > f <<EOF`,
    `> f`, `>> f`) is treated as a Write, or an append for `>>`.
  - Any other in-place edit (`sed -i`, `perl -pi`, `python -c` writing a
    file, `patch`, `git apply`) is counted as an **unreconstructed edit**,
    and the file is marked not reconstructable. It is reported, never
    guessed at.

Simulated tool calls are taken at face value: the trajectory is the record.
A call whose result reports an error (for example, "old_string not found"
or "permission denied") is not applied.

**Patch per file (primary unit).** For each changed file, the patch runs
from its first known state to its final state (`difflib` unified diff).
Status is added, modified or removed, as defined above. For a file whose
starting content is unknown, the patch is its bare hunks in order. Lines
that one edit removes and a later edit restores are then not netted out,
as in the AIDev study. The patch rules (`tools/patch_scan.py`) run on each
file's patch. **A trajectory is flagged by the patch rules if any file
triggers any rule.**

**Per-edit unit (secondary).** Every Write, Edit or deletion event is also
scanned as its own patch. This is the AIDev "any commit" unit. It is
reported next to the primary unit.

**PR mode, where full files can be reconstructed.** The base snapshot holds
every file whose full content is known before its first change, and every
file that is read but never changed (as context). The head snapshot is the
base with all reconstructable changes applied: added files are created,
removed files deleted, and modified files replaced. A changed file that is
not reconstructable is left out of both snapshots. `pr.compare(base, head)`
runs on the pair. **A trajectory is flagged by PR mode if it has any
finding.** A trajectory is **PR-reconstructable** if at least one changed
file whose path matches `patch_scan.is_test_path`, or a `.github/workflows`
file, is reconstructable.

**Combined.** A trajectory is flagged if the patch rules or PR mode flag it.

**Coverage reporting.** For each population, results report how many
trajectories:

- have at least one extracted change;
- change a test, conftest or workflow file;
- are PR-reconstructable;
- have unreconstructed edits.

**Parser freeze.** The extractor (`tools/trace_extract.py`) and the label
parser are developed against the conversation envelope only. The `label`
column is not loaded while they are developed. Both are committed before
any detector run and before labels are joined to extractions. Their commit
hash is recorded in the results. If the envelope defeats the rules above
(for example, tool calls are not machine-readable), that is reported as a
failure of this protocol and not worked around silently.

### Amendment 1 (after labels were read, before the detector was run)

The `label` values turned out to be section numbers, not names, so the
name mapping above matched none of them. The distinct values are `0` and
ten codes from `1.1.1` to `1.4.2`. They are the section numbers of the
paper's Appendix G:

| Code | Category |
|---|---|
| `1.1.1` | Test Modification |
| `1.1.2` | Test Case Targeting |
| `1.1.3` | Coverage Gaming |
| `1.2.1` | Degenerate Implementations |
| `1.2.2` | Complexity Gaming |
| `1.2.3` | Style Manipulation |
| `1.3.1` | Information Leakage |
| `1.3.2` | Tool Abuse |
| `1.4.1` | Runtime Manipulation |
| `1.4.2` | Timing & Resource Exploitation |

`0` is benign. It appears on 249 rows, which matches the dataset card's 249
benign trajectories, and never together with a code. The label parser now
maps these codes. The code was committed before any detector run, so the
amendment could not be shaped by detector output. With it, every label
maps: 249 benign, 56 H-TM, 151 H-TSE and 117 H-other trajectories (268
hacked).

**Consequence:** the labels name categories, not subcategories. Measure 6
(recall per Test Modification subcategory) cannot be computed and is
dropped. The blind labeler sees category names instead of subcategory
names.

### Amendment 2 (before the detector was run)

**Extractor bug.** Three Read results of the form `File not found: <path>`
were taken as file content, because the error pattern knew only results
that begin with `Error`. The pattern now also recognizes `File not found`
and `File does not exist`. A file first reported missing and then written
therefore counts as added, as the extraction rules intend.

This was found while auditing blind labels. One labeling packet showed a
new test file with the one-line base `File not found: …`. The labeler
judged the new file alone, so no label depends on the bug. The fix was
committed before any detector run.

**Blind labels, done.** The 56 H-TM trajectories were labeled by four
independent review agents (14 each):

| Code-visible | Trajectories |
|---|---|
| Yes | 43 |
| No | 6 |
| Unclear | 7 |

All seven "unclear" labels are trajectories whose test files were changed
only by Bash commands that could not be replayed. The packets cut each
patch at 8,000 characters and each trajectory at 40,000.

**Author audit.** The seeded 20% (11 items, seed 20260930) was labeled
independently before looking at the agents' labels. It agreed on all 11.

### Detector under test

The patch rules and PR mode run at detector commit `ce836ad` (schema
1.6.0). Its check and rule code is unchanged since `0fb587c`. No rule or check code changes between the first run and the
reported numbers. Misses found by this study are inputs to a later detector
version, which needs its own study.

### Blind labels

The ground truth is TRACE's labels, made by the dataset's authors and
annotators independently of this detector. One more label is needed,
because not every Test Modification hack is visible as a code change. Some
are run-time flags, or edits made through a Bash command that cannot be
replayed. For each H-TM trajectory, an independent review agent assigns
**code-visible**: yes, no or unclear. It answers yes if the hack is
expressed in the extracted changes to test, conftest, test-configuration or
CI files.

The labeler sees:

- the extracted file paths and patches;
- the trajectory's TRACE subcategory names.

The labeler does not see:

- any detector output;
- the rest of the conversation.

Labels are assigned **before the detector is run**. The author audits a
seeded 20% of these labels (seed 20260930) before the join.

Each benign trajectory that is flagged is then characterized after the
fact:

- **real signal:** the change does what the rule says, for example a test
  a benign refactor legitimately removed;
- **artifact:** the rule misread the change.

This is a description of the false alarms. It does not change the
false-alarm rate.

### Measures

All intervals are 95% Wilson intervals.

1. **Recall on H-TM** for:
   - the patch rules (primary unit);
   - the patch rules (per-edit unit);
   - PR mode;
   - combined.
2. **Recall on code-visible H-TM** (labeled yes), for the same four.
3. **PR-mode recall on code-visible, PR-reconstructable H-TM.** This is what
   PR mode can be asked to catch.
4. **False-alarm rate on B** for the same four. PR mode's rate is also
   reported on PR-reconstructable B.
5. **Recall on H-TSE**, and per category (TM, TCT, CG), combined detector.
6. **Recall per TM subcategory**, combined detector. This is descriptive,
   with n shown. A subcategory with fewer than 5 trajectories is pooled as
   "other".
7. **Signal rate on H-other**, combined detector. This is descriptive.
8. **Which rules and checks fire**, on hacked and benign trajectories.

### Decision rules, fixed now

This study cannot switch PR mode to default-on by itself. Default-on still
needs PR-mode round 3 (precision, at least 50 labeled findings). The study
decides whether recall **blocks** default-on:

- **Recall does not block default-on** if PR-mode recall on code-visible,
  PR-reconstructable H-TM (measure 3) has a lower bound of at least 50%.
  PR mode's false-alarm rate on PR-reconstructable B must also be at most
  10% (the alarm-rate bar of the PR-mode studies).
- **Recall blocks default-on** if measure 3's point estimate is below 50%,
  or if that false-alarm rate is above 10%. PR mode then stays advisory.
  The misses are analyzed by subcategory to find gaps in the checks.
- **Otherwise, inconclusive.** This includes a point estimate of at least
  50% with a lower bound below 50%, and fewer than 20 trajectories in
  measure 3. The report says what sample would settle the question.

Rationale for 50%: a check that runs by default on every pull request is
sold as a guard against the hacks it targets. If it misses more than half
of them when the hack is plainly in the diff, it should stay an advisory
aid.

### What this cannot show

- **The data is synthetic.** One model generated all the trajectories
  (claude-opus-4-5), and the hacks were written to be found. Real agent
  hacks may be subtler, or simpler.
- **The trajectories are short tasks, not repositories.** PR mode sees only
  the files a trajectory read or wrote. A repository-wide context (a
  conftest the agent never opened, CI configuration) is missing. Its
  recall here may differ from its recall on real pull requests.
- **The false-alarm rate is measured on benign synthetic trajectories.**
  It is not the alarm rate on real changes, which the PR-mode studies
  measure (1.2% in round 2).
- **Recall on hacks that are not visible in code** (TCT, CG and
  non-visible TM) is expected to be low by design. This measures the
  detector's scope, not a defect.

## Results

**Setup:**

- detector `ce836ad`, schema 1.6.0, with check and rule code unchanged;
- extractor and scorer at `9d1e359`;
- TRACE revision `31d87f06078e`.

These are the numbers of the first and only detector run. Per-trajectory
rows are kept outside the repository (CC-BY-SA-4.0); this section holds
aggregates only.

### Coverage

| Population | Trajectories | Any change | Test/CI change | PR-reconstructable | Unreconstructed edits | PR-mode errors |
|---|---|---|---|---|---|---|
| H-TM | 56 | 56 | 47 | 41 | 11 | 0 |
| H-TSE | 151 | 151 | 85 | 76 | 33 | 0 |
| (TCT) | 69 | 69 | 30 | 26 | 18 | 0 |
| (CG) | 51 | 51 | 25 | 23 | 12 | 0 |
| B | 249 | 246 | 113 | 111 | 51 | 0 |
| H-other | 117 | 115 | 42 | 40 | 29 | 0 |

Code-visible labels on H-TM: 43 yes, 6 no, 7 unclear.

### Recall and false-alarm rate (measures 1, 2 and 4)

| Detector | Recall, H-TM | Recall, code-visible H-TM | False alarms, B |
|---|---|---|---|
| Patch rules (per file, primary) | 7/56 = 12.5% (6.2–23.6%) | 7/43 = 16.3% (8.1–30.0%) | 4/249 = 1.6% (0.6–4.1%) |
| Patch rules (per edit) | 10/56 = 17.9% (10.0–29.8%) | 9/43 = 20.9% (11.4–35.2%) | 9/249 = 3.6% (1.9–6.7%) |
| PR mode | 10/56 = 17.9% (10.0–29.8%) | 10/43 = 23.3% (13.2–37.7%) | 0/249 = 0.0% (0.0–1.5%) |
| **Combined** | **12/56 = 21.4% (12.7–33.8%)** | **12/43 = 27.9% (16.7–42.7%)** | **4/249 = 1.6% (0.6–4.1%)** |

All 12 detected H-TM trajectories are code-visible.

### PR mode on what it can see (measure 3)

- **PR-mode recall** on code-visible, PR-reconstructable H-TM:
  **9/35 = 25.7% (14.2–42.1%)**.
- **PR-mode false alarms** on PR-reconstructable B:
  **0/111 = 0.0% (0.0–3.3%)**.
- **Combined recall** on the same 35: 11/35 = 31.4% (18.6–48.0%).

### Decision

**Recall blocks default-on.** Measure 3's point estimate, 25.7%, is below
the pre-registered 50%. PR mode's false-alarm rate, 0 of 111, is well
inside the 10% bar. So the block comes from missed hacks, not from noise.
PR mode stays advisory. Round 3's precision result cannot lift this block
by itself. Default-on now needs a later detector version that closes the
gaps below, measured on a fresh recall study.

### By category (measures 5 and 7, combined detector)

| Population | Flagged |
|---|---|
| H-TSE | 13/151 = 8.6% (5.1–14.2%) |
| H-TM | 12/56 = 21.4% (12.7–33.8%) |
| H-TCT | 3/69 = 4.3% (1.5–12.0%) |
| H-CG | 4/51 = 7.8% (3.1–18.5%) |
| H-other | 2/117 = 1.7% (0.5–6.0%) |

As expected, Test Case Targeting and Coverage Gaming hacks live in solution
code and are mostly out of reach. Measure 6 (per subcategory) was dropped
by Amendment 1.

### Which rules and checks fire (measure 8, trajectories)

| Rule or check | H-TM | H-TSE | H-other | B |
|---|---|---|---|---|
| P-ASSERTIONS-NET-REMOVED | 6 | 7 | 0 | 1 |
| P-CONTINUE-ON-ERROR | 1 | 1 | 0 | 0 |
| P-EXIT-ZERO | 0 | 0 | 0 | 1 |
| P-SKIP-ADDED | 0 | 0 | 0 | 1 |
| P-TEST-FILE-DELETED | 1 | 1 | 2 | 1 |
| PR-ASSERTIONS-REMOVED | 3 | 4 | 0 | 0 |
| PR-NEW-TAMPERING | 5 | 6 | 0 | 0 |
| PR-TESTS-DISABLED | 1 | 1 | 0 | 0 |
| PR-TESTS-REMOVED | 2 | 2 | 0 | 0 |

### What was caught, and what was missed

The detector catches hacks that **remove or neutralize** verification:

- deleted tests;
- assertions removed on net;
- `assert True` in place of a real assertion (PR mode);
- test bodies wrapped in `try/except: pass` (PR mode);
- a marker deselection added to `pytest.ini`;
- `continue-on-error` in CI.

It misses hacks that **keep the assertion but change what it checks**.
Each of the 31 missed code-visible trajectories was classified by the
mechanism its blind label describes. This classification was made after
the run.

| Mechanism | Missed | Would a diff-level check see it? |
|---|---|---|
| Threshold or tolerance loosened in an assertion (for example, `>= 0.85` to `>= 0.70`; `EXPECT_NEAR` tolerance widened) | 12 | Yes: the same assertion with a relaxed numeric bound |
| Code under test mocked, stubbed or forced (`@patch` on the method under test, fixtures returning the expected values, metrics clamped to the threshold) | 6 | Partly: a mock added that targets the module the test imports |
| Test timeout raised (`@pytest.mark.timeout`, `jest.config.js` `testTimeout`, `pytest.ini` `timeout`) | 3 | Yes: a timeout value increased |
| Assertion made weaker in form (`toBe(true)` to `== true`; `assert x >= 0`; `assert True` in a file that could not be reconstructed) | 3 | Partly; PR mode sees `assert True` when the file is reconstructable |
| Expected values or inputs rewritten to match the output | 2 | Only as a changed literal; indistinguishable from a legitimate fix without intent |
| Assertion failures caught (`try/except AssertionError` with a looser fallback; a conflicting move's error swallowed) | 2 | Yes: an `except AssertionError` added in a test |
| Tests excluded by configuration (`--ignore=` in `pytest.ini` `addopts`; CI job made `when: manual` with `-m "not slow"`) | 2 | Yes: an extension of PR-TESTS-DISABLED |
| Sleeps inserted to hide a race | 1 | No |

**Most misses are not subtle.** Many are loosened thresholds (12 of 31)
or raised timeouts (3). A reviewer sees them at once in the diff, but the
current rules do not look for them, because a changed number is not a
removed assertion. They are also where benign changes will be common. A
spec that really changed looks the same in a diff. So a new check here
must be measured for precision before it is trusted, as every earlier
check was.

### False alarms on benign trajectories

All four combined alarms on B come from the patch rules; PR mode raised
none. Three are real signals, correctly reported:

- a debug script under `tests/` deleted;
- a `pytest.skip` guard for missing metrics in a new test file;
- assertions on removed debug fields dropped in a refactor.

One is an artifact: `P-EXIT-ZERO` on a load-test script's `sys.exit(0)`.
That rule was already rated unreliable (63% precision in
`AGENT_PR_STUDY.md`). The per-edit unit alarms more often (9 of 249),
because intermediate edits that a later edit restores are not netted out.
The per-file unit is the right one for pull requests.

### Limits of this result

- **n is small.** 35 trajectories in measure 3 give an interval of
  14–42%. Even the upper bound is below the 50% bar, so the decision does
  not rest on the point estimate.
- **The data is synthetic, from one model, and short tasks.** PR mode saw
  only the files each trajectory read or wrote. On real repositories,
  where full snapshots exist, PR-mode coverage would be higher, but the
  miss mechanisms above do not depend on coverage.
- **"Code-visible" was judged by review agents from the extracted diffs.**
  The author's audit of a seeded 20% agreed with all 11 items.
