# Matched study: agent and human changes in the same repositories

## Protocol (fixed before any repository is cloned; committed before results)

**Question.** Within the same repositories and the same time window, do
changes merged from AI-agent pull requests carry verification-weakening
signals more often than changes merged by humans? This answers review item
A-2: the earlier comparison was unmatched.

**Operator approval.** Repository identity (the AIDev `repo_url` and PR
`number` fields) is used internally for this study. Repository names,
commit messages and author identities are never published or committed.
Author names and emails are read only to exclude bots, and are not stored.

**Sampling frame.**
- Repositories in AIDev's curated set with at least 5 merged agent PRs
  that have patch data.
- From that frame, 300 repositories drawn uniformly (seed 20260930).
- A repository is skipped if it cannot be cloned within 10 minutes, or if
  the clone exceeds 2 GB. Skips are reported, never replaced.

**Window.** Per repository: from 30 days before its first merged agent PR
to 30 days after its last.

**Units.** Every first-parent commit on the default branch inside the
window, compared with its first parent: one merged change each. Merge
commits are compared with their first parent.

**Labels.**
- **Agent change:** the commit message references the number of a
  merged AIDev agent PR in that repository, as "#N" in the usual squash
  or merge form.
- **Bot change**, excluded: authored by an account whose name or email
  matches a fixed pattern. The patterns are dependabot, renovate,
  github-actions, pre-commit-ci, allcontributors, and the agents' own
  bot accounts (anything containing "copilot", "devin", "codex",
  "cursor", "jules", "claude" or "[bot]"). Excluded changes are counted.
- **Human change:** everything else. Some unrecorded agent work will sit
  in the human group; that biases the comparison toward no difference.

**Signals.** The three qualifying rules of the agent PR study
(`tools/patch_scan.py`: assertions removed on net, `continue-on-error`
added, skips added), applied to each change's per-file diff. The rules
are unchanged from the agent PR study.

**Primary analysis.** The Mantel–Haenszel risk ratio (agent against human)
of carrying at least one signal, stratified by repository, with a 95%
confidence interval. Only repositories with at least one agent change and
at least 5 human changes in the window contribute.

**Secondary analyses.**
- The same ratio within strata of primary language (Python, JS/TS, other)
  and of change size (lines changed: up to 50, 51–500, over 500).
- Per-repository rates.
- The share of repositories where the agent rate exceeds the human rate.

**Precision check.** Signals are re-labeled on a sample: 100 flagged agent
changes and 100 flagged human changes (all, if fewer), seed 20260931.
Independent reviewers see the diff without knowing its group. The author
audits a seeded 20% (seed 20260932). If precision differs between groups
by more than 10 points, the risk ratio is also reported adjusted for
group-specific precision.

**Decision rules, fixed now.**
- The report states an agent effect only if the lower bound of the 95%
  interval on the primary ratio is above 1.
- If the interval includes 1, the report says so plainly, and the
  unmatched comparison is withdrawn from the report.
- Per-agent figures stay under review A-6 and are not part of this
  protocol.

**What this cannot show.** Intent; changes that do not reference their PR
number (they fall into the human group); repositories that squash without
PR references (they contribute no agent changes and drop out).

## Harness corrections

Recorded while the run was in progress, before any result was analyzed.

1. **Broken symlinks (2026-09-23).** The repository-size check used
   `os.path.getsize`, which follows symlinks. A checkout containing a
   broken symlink raised `FileNotFoundError`, and the repository was
   skipped as an error. The check now uses `lstat`. Only the repositories
   skipped by a harness error are re-run (`run --retry-errors`); every
   other result is kept unchanged. The number of repositories affected is
   reported with the results.

## Results (2026-09-23; precision check pending)

Harness correction 1 re-ran the 11 repositories skipped by a harness
error: 10 `FileNotFoundError` from broken symlinks and 1 `OSError` in the
same size walk. All 11 then completed. No other result was re-run.

**Coverage.** 300 repositories were sampled and 297 analyzed. Three were
skipped: 1 clone failed and 2 were over 2 GB. 262 met the analysis
threshold of at least one agent change and at least five human changes.
12,613 bot changes were excluded.

| Stratum | Repositories | Agent changes with signal | Human changes with signal | MH risk ratio (95% CI) |
|---|---|---|---|---|
| **All (primary)** | 262 | 152/6778 (2.24%) | 2206/86236 (2.56%) | **1.01 (0.85–1.22)** |
| Language: Python | 80 | 87/2306 (3.77%) | 725/24484 (2.96%) | 1.13 (0.88–1.46) |
| Language: JS/TS | 124 | 57/3750 (1.52%) | 1347/55849 (2.41%) | 0.95 (0.72–1.26) |
| Language: other | 58 | 8/722 (1.11%) | 134/5903 (2.27%) | 0.69 (0.34–1.41) |
| Size ≤50 lines | 223 | 10/2655 (0.38%) | 148/36872 (0.40%) | 1.21 (0.59–2.49) |
| Size 51–500 | 208 | 60/2741 (2.19%) | 678/28643 (2.37%) | 0.92 (0.68–1.24) |
| Size >500 | 139 | 69/1068 (6.46%) | 1201/12651 (9.49%) | 0.79 (0.62–1.01) |

The agent rate exceeds the human rate in 46 of the 262 repositories.

**Decision rule applied.** The interval on the primary ratio includes 1.
So, as fixed in advance:

- **No agent effect is stated.** Within the same repositories and period,
  agent-authored changes carry a qualifying weakening signal at a rate
  indistinguishable from human-authored changes.
- **The unmatched comparison is withdrawn from the report.** That is the
  1.71% in 39 mature libraries. The apparent gap reflected where agents
  are deployed, as review item A-2 warned.

**What this does not change.** The population rates for agent PRs, and
their audited precision, measure what agent PRs do. They make no
comparison with humans. The matched result says that weakening is a
property of changes in these repositories, whoever writes them. That
argues for checking every change, not only agents' changes.

**Still to run (pre-registered).** Precision relabel: 100 flagged agent
changes and 100 flagged human changes, seed 20260931, with an author
audit at seed 20260932. The result is final only after it. If precision
differs between the groups by more than 10 points, the adjusted ratio is
added.
