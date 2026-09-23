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
