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
