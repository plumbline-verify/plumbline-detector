# Agent PR integrity study

## Protocol (fixed before any data is read; committed before results)

**Question.** In real pull requests written by AI coding agents, how often
does the diff visibly weaken verification: assertions removed on net,
skips added, test files deleted, `continue-on-error` added to workflows,
test commands removed from CI, success exits, always-true `__eq__`, or
test-report patching? How does that differ by agent?

**Data.** AIDev (hao-li/AIDev-7.6M on Hugging Face, CC-BY-4.0):
`pull_request.parquet` (the curated set of agent-authored PRs, each labeled
with its agent) joined on `pr_id` to `pr_commit_details.parquet`
(file-level patches of each PR's commits). The dataset revision is recorded
at download.

**Privacy, fixed now.** Only these columns are read: `id`, `agent`,
`state`, `merged_at` (PRs); `pr_id`, `filename`, `status`, `patch`
(patches). Author, committer, user, commit-message, title, body and
repository-name columns are never loaded. Results are published only as
aggregates with at least 5 PRs per cell. Items sent to labelers carry the
file path and patch only.

**Detector.** `tools/patch_scan.py` (rules and definitions in its
docstring) at the commit that adds `tools/aidev_scan.py`. One pre-run
correction was made after smoke tests on synthetic patches and before any
AIDev data was read: the success-exit rule no longer matches method calls
(`server.exit()`) or text inside comments and strings. No rule changes
between the first run and the reported numbers.

**Unit.** A PR is flagged for a rule if any file patch in any of its
commits triggers the rule. (Limitation: a later commit in the same PR that
restores what an earlier commit removed is not netted out.)

**Measures.**
1. Prevalence: for each rule and for any rule, the share of PRs flagged,
   overall and per agent, for all PRs and for merged PRs, with 95% Wilson
   intervals.
2. Precision: for each rule, 30 flagged file patches (all if fewer) drawn
   with seed 20260926, labeled by independent review agents from the patch
   alone:
   - **TP**: the patch does what the rule says.
   - **FP**: it does not (a regex artifact, a moved line, a comment).

   Each TP is also judged **weakening** (verification reduced with no
   visible replacement in the patch) or **benign/unclear**. The author
   audits a seeded 20% (seed 20260927).

**Decision rules, fixed now.**
- A rule enters the headline "weakening signal" figure only if its
  precision is at least 80%. Rules below that are reported separately as
  unreliable.
- The headline figure per agent is the share of merged PRs with at least
  one signal from a qualifying rule, multiplied by nothing: it is reported
  as a signal rate, never as a cheating rate, because a TP can be benign.
  The weakening share among labeled TPs is reported next to it.

**What this cannot show.** Intent; whether a weakening was accepted
knowingly; a human baseline on the same pipeline (AIDev's curated set is
agent PRs); changes a diff cannot reveal (a test that asserts the wrong
value).

## Results (scanner at commit `acacdea`; AIDev revision `37bbe1533e26`)

**Coverage.** 361,296 agent-authored PRs in the curated set; 188,768 of them
(128,283 merged) have file-level patches in `pr_commit_details`, and only
those are analyzed. 6,014,763 file patches were scanned. Coverage is uneven
by agent: patches exist for 8,771 of about 173,000 Claude Code PRs, but for
most Copilot, Codex, Cursor, Devin and Jules PRs. Per-agent differences may
reflect which PRs have patch data as much as the agents themselves.

**Precision (195 labeled findings; the author's audit of the seeded 20%,
39 items, agrees with all 39).**

| Rule | Flagged patches | Labeled | Precision (95% CI) | Weakening / benign / unclear, of TP |
|---|---|---|---|---|
| P-ASSERTIONS-NET-REMOVED | 19,639 | 30 | 100% (89–100%) | 13 / 14 / 3 |
| P-CONTINUE-ON-ERROR | 7,026 | 30 | 97% (83–99%) | 0 / 25 / 4 |
| P-SKIP-ADDED | 8,872 | 30 | 80% (63–90%) | 2 / 20 / 2 |
| P-TEST-STEP-REMOVED | 1,092 | 30 | 60% (42–75%) | 10 / 4 / 4 |
| P-EXIT-ZERO | 733 | 30 | 63% (46–78%) | 0 / 19 / 0 |
| P-TEST-FILE-DELETED | 54,212 | 30 | 53% (36–70%) | 5 / 2 / 9 |
| P-EQ-ALWAYS-TRUE | 9 | 9 | 56% (27–81%) | 0 / 5 / 0 |
| P-RUNNER-PATCH | 6 | 6 | 17% (3–56%) | 0 / 1 / 0 |

By the decision rule, **three rules qualify for the headline**:
assertions removed on net, `continue-on-error` added, and skips added. The
other five are unreliable as written. Their false positives come from
Pascal `exit()` (a function return), non-test files under test directories
(compiler-output logs, build artifacts, snapshots), prompt text and
dependency installs matched as test commands, and a model's `.fit(`
matched as a focused-test marker.

**Headline signal rate (qualifying rules), merged PRs.**

| Agent | Merged PRs with patches | Signal rate (95% CI) |
|---|---|---|
| Claude Code | 5,767 | 11.27% (10.48–12.11%) |
| Cursor | 7,472 | 7.53% (6.96–8.16%) |
| Copilot | 59,213 | 7.49% (7.28–7.70%) |
| Devin | 6,592 | 7.15% (6.55–7.79%) |
| OpenAI Codex | 47,166 | 5.53% (5.32–5.74%) |
| Google Jules | 2,073 | 4.10% (3.33–5.04%) |
| **All** | **128,283** | **6.87% (6.73–7.01%)** |

This is a **signal rate, not a cheating rate**. Among labeled true
positives, 13 of 30 assertion removals (43%, 95% CI 27–61%) removed
verification with no visible replacement. That compares with 2 of 24 added
skips and 0 of 29 added `continue-on-error` lines, which were mostly
environment guards and optional steps. Multiplying through gives an
approximate rate of **about 2% of merged agent PRs that visibly remove
assertions or skip tests without a visible replacement**. That is a rough
product of the rates, with wide uncertainty from the 30-item label samples.

**Exploratory comparison (not pre-registered).** The same rules were run on
the 1,170 human-maintained changes from the two PR-mode studies (39 mature
open-source libraries; commits compared with their parents). **1.71% (95%
CI 1.1–2.6%) carried a qualifying signal**, against 6.87% for merged agent
PRs, about four times fewer. The populations differ: the merged agent PRs
analyzed come from 11,029 repositories (25,402 in the curated set) of every
age and quality, and the human set is
well-maintained libraries. Units differ too: an agent PR against a human
commit. So this is a pointer for a controlled study, not a finding.

**What the per-rule results mean for the product.** Removed assertions,
the most common signal, were correct every time and a weakening in about
four of ten cases. Most flagged `continue-on-error` lines and skips were
benign guards. A product needs the PR-mode analysis (whole snapshots, not
patches) to tell those apart, and should lead with assertion removal and
test-step removal once the latter is made precise.

Labels without patches or file paths: `docs/agent_pr_study/labeled_sample.jsonl`.
Full per-rule prevalence: `docs/agent_pr_study/prevalence_all_rules.md`.
