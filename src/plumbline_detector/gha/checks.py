"""Gate-topology checks over GitHub Actions workflows.

Grounding: GitHub documents that "If a job within a workflow is skipped due to
a conditional, it will report its status as 'Success'", and branch protection
treats success, skipped and neutral alike when evaluating a required check.
A skipped required job therefore satisfies the gate.
"""

from __future__ import annotations

from ..model import CheckResult, Location
from . import model as M

NO_WORKFLOWS = "no GitHub Actions workflow files (.github/workflows/*.yml|yaml)"


def _base(check_id: str, gm: M.GHAModel) -> CheckResult:
    r = CheckResult(check_id)
    if not gm.workflow_paths:
        r.absent_reason = NO_WORKFLOWS
        return r
    r.had_input = True
    r.unknowns.extend(gm.issues)
    return r


def _required_set(gm: M.GHAModel, gate: M.GateInfo):
    """Return (basis, {job_key: [contexts]}, unmatched_contexts)."""
    if gate.contexts:
        produced: dict = {}
        unmatched = []
        for ctx in sorted(gate.contexts):
            hit = False
            for wf in gm.workflows.values():
                for job in wf.jobs.values():
                    if M.context_match(gm, job, ctx):
                        produced.setdefault(job.key(), []).append(ctx)
                        hit = True
            if not hit:
                unmatched.append(ctx)
        return "declared", produced, unmatched
    produced = {}
    for job in gm.pr_jobs():
        if M.is_aggregator(gm, job):
            produced[job.key()] = [job.display]
    return ("inferred" if produced else "none"), produced, []


def _job(gm, key):
    return gm.workflows[key[0]].jobs[key[1]]


def gt_no_gate(gm: M.GHAModel, gate: M.GateInfo) -> CheckResult:
    """GT-NO-GATE: no branch-protection artifact and no required check declared.

    Branch protection normally lives in repository settings, not in the
    repository. This check reports what the artifact itself evidences: if
    nothing in the snapshot (or supplied by the operator) declares a required
    check, the snapshot carries no evidence that CI gates merges at all.
    """
    r = _base("GT-NO-GATE", gm)
    r.unknowns = list(gate.issues) if r.had_input else []
    r.stats = {"gate_sources": sorted(set(gate.sources)), "required_context_count": len(gate.contexts)}
    if not r.had_input:
        return r
    if gate.contexts:
        return r
    if gate.protection_without_checks:
        r.findings.extend(gate.protection_without_checks)
        return r
    if not gate.issues:
        r.findings.append(
            Location(
                M.WORKFLOW_DIR,
                None,
                "workflows exist but no required status check is declared in any recognized artifact "
                "(.github/settings.yml, .github/rulesets/*.json) or supplied by the operator",
            )
        )
    return r


def gt_skip_satisfies(gm: M.GHAModel, gate: M.GateInfo) -> CheckResult:
    """GT-SKIP-SATISFIES: a required check produced by a job that an `if:`
    conditional can skip. A skipped job reports Success, so the required
    check is satisfied without the job having run.
    """
    r = _base("GT-SKIP-SATISFIES", gm)
    if not r.had_input:
        return r
    basis, produced, unmatched = _required_set(gm, gate)
    r.basis = basis
    r.stats = {"required_producing_jobs": len(produced), "required_contexts_unmatched": unmatched}
    if basis == "none":
        r.unknowns.append(
            Location(M.WORKFLOW_DIR, None, "no required check declared and no aggregator job to infer one from")
        )
        return r
    for key in sorted(produced):
        job = _job(gm, key)
        if M.is_skippable_if(job.if_expr):
            r.findings.append(
                Location(
                    job.workflow,
                    job.if_line or job.line,
                    f"job {job.id!r} produces required check(s) {sorted(produced[key])} but has "
                    f"`if: {job.if_expr}`; when the condition is false the job is skipped and reports Success",
                    {"job": job.id, "if": str(job.if_expr), "basis": basis},
                )
            )
    return r


def gt_continue_on_error(gm: M.GHAModel, gate: M.GateInfo) -> CheckResult:
    """GT-CONTINUE-ON-ERROR: `continue-on-error` enabled on a test-running
    step or job. A step-level setting turns a failing test step into a passing
    job; a job-level setting keeps a failing job from failing the workflow run
    and from blocking jobs that need it.
    """
    r = _base("GT-CONTINUE-ON-ERROR", gm)
    if not r.had_input:
        return r
    examined = 0

    def classify(raw):
        v = str(raw).strip()
        if v == "false":
            return None
        if v == "true":
            return "always"
        if v.startswith("${{") and v.endswith("}}"):
            return "conditional"
        return "unrecognized"

    for wf in gm.workflows.values():
        for job in wf.jobs.values():
            status = M.job_test_status(gm, job)
            if job.continue_on_error is not None:
                kind = classify(job.continue_on_error)
                examined += 1
                if kind == "unrecognized":
                    r.unknowns.append(Location(wf.path, job.coe_line, f"job {job.id!r}: unrecognized continue-on-error value"))
                elif kind and status == "yes":
                    r.findings.append(
                        Location(
                            wf.path,
                            job.coe_line,
                            f"test-running job {job.id!r} has continue-on-error ({kind}): its failure does not fail the run",
                            {"job": job.id, "scope": "job", "kind": kind},
                        )
                    )
                elif kind and status == "unknown":
                    r.unknowns.append(Location(wf.path, job.coe_line, f"job {job.id!r} has continue-on-error; cannot tell whether it runs tests"))
            for step in job.steps:
                if step.continue_on_error is None:
                    continue
                examined += 1
                kind = classify(step.continue_on_error)
                if kind == "unrecognized":
                    r.unknowns.append(Location(wf.path, step.coe_line, f"job {job.id!r} step {step.index}: unrecognized continue-on-error value"))
                elif kind and M.step_runs_tests(step):
                    r.findings.append(
                        Location(
                            wf.path,
                            step.coe_line,
                            f"test step in job {job.id!r} has continue-on-error ({kind}): failing tests leave the job green",
                            {"job": job.id, "scope": "step", "step": step.index, "kind": kind},
                        )
                    )
    r.stats = {"continue_on_error_sites": examined}
    return r


def gt_aggregator_permissive(gm: M.GHAModel, gate: M.GateInfo) -> CheckResult:
    """GT-AGGREGATOR-PERMISSIVE: an aggregator/summary job whose green does not
    mean its dependencies passed. Two shapes:
      (a) no non-skipping `if:` (always() / !cancelled()): when a needed job
          fails, the aggregator is skipped, and a skipped job reports Success;
      (b) runs always but never inspects `needs.<job>.result` for some or all
          of its needs, so it passes whatever they did.
    """
    r = _base("GT-AGGREGATOR-PERMISSIVE", gm)
    if not r.had_input:
        return r
    aggs = [j for j in gm.pr_jobs() if M.is_aggregator(gm, j)]
    r.stats = {"aggregators": len(aggs)}
    if not aggs:
        if not r.unknowns:
            r.had_input = False
            r.absent_reason = "no aggregator/summary job in any pull-request-triggered workflow"
        return r
    for job in aggs:
        if not M.runs_always(job):
            why = "has no `if:`" if job.if_expr is None else f"has `if: {job.if_expr}`"
            r.findings.append(
                Location(
                    job.workflow,
                    job.if_line or job.line,
                    f"aggregator {job.id!r} {why}; when any of {job.needs} fails it is skipped and reports Success",
                    {"job": job.id, "shape": "skippable"},
                )
            )
            continue
        kind, covered = M.verification(job)
        if kind == "unrecognized":
            r.unknowns.append(Location(job.workflow, job.line, f"aggregator {job.id!r} inspects needs in a form not modeled"))
            continue
        unverified = [] if "*" in covered else [n for n in job.needs if n not in covered]
        if kind == "none" or unverified:
            r.findings.append(
                Location(
                    job.workflow,
                    job.line,
                    f"aggregator {job.id!r} runs always but does not verify the result of {unverified or job.needs}; "
                    "it passes regardless of their outcome",
                    {"job": job.id, "shape": "unverified", "unverified": unverified or job.needs},
                )
            )
    return r


def _propagates(gm, wf, job_id, required_keys, memo, stack):
    """'yes' | 'no' | 'unknown': can failure of wf.jobs[job_id] reach a
    required check? Direct if the job is required; otherwise through a
    dependent that runs always and verifies this job's result."""
    key = (wf.path, job_id)
    if key in memo:
        return memo[key]
    if key in stack:
        return "unknown"
    stack = stack | {key}
    if key in required_keys:
        memo[key] = "yes"
        return "yes"
    outcome = "no"
    for dep in wf.jobs.values():
        if job_id not in dep.needs:
            continue
        if not M.runs_always(dep):
            # dependent is skipped when this job fails -> reports Success
            continue
        kind, covered = M.verification(dep)
        if kind == "unrecognized":
            outcome = "unknown" if outcome == "no" else outcome
            continue
        if "*" in covered or job_id in covered:
            res = _propagates(gm, wf, dep.id, required_keys, memo, stack)
            if res == "yes":
                outcome = "yes"
                break
            if res == "unknown":
                outcome = "unknown"
    memo[key] = outcome
    return outcome


def gt_no_propagation(gm: M.GHAModel, gate: M.GateInfo) -> CheckResult:
    """GT-NO-PROPAGATION: a test-running job in a pull-request-triggered
    workflow whose failure cannot reach any required check. Its red X is
    advisory; the merge button does not see it.
    """
    r = _base("GT-NO-PROPAGATION", gm)
    if not r.had_input:
        return r
    basis, produced, _ = _required_set(gm, gate)
    r.basis = basis
    if basis == "none":
        r.unknowns.append(Location(M.WORKFLOW_DIR, None, "no required check declared and no aggregator job to infer one from"))
        return r
    required_keys = set(produced)
    memo: dict = {}
    tested = 0
    for wf in gm.workflows.values():
        if not wf.pr_triggered:
            continue
        for job in wf.jobs.values():
            status = M.job_test_status(gm, job)
            if status == "no":
                continue
            tested += 1
            res = _propagates(gm, wf, job.id, required_keys, memo, frozenset())
            if status == "unknown" and res != "yes":
                r.unknowns.append(Location(wf.path, job.line, f"job {job.id!r} may run tests (reusable workflow not visible); propagation not established"))
                continue
            if res == "unknown":
                r.unknowns.append(Location(wf.path, job.line, f"job {job.id!r}: propagation passes through a construct not modeled"))
            elif res == "no":
                loc = Location(
                    wf.path,
                    job.line,
                    f"test-running job {job.id!r}: failure reaches no required check ({basis} required set)",
                    {"job": job.id, "basis": basis},
                )
                # An inferred required set cannot rule out that this job is
                # itself required in repository settings: report, don't fail.
                (r.findings if basis == "declared" else r.unknowns).append(loc)
    r.stats = {"test_jobs_examined": tested, "required_producing_jobs": len(required_keys)}
    return r


ALL = [gt_skip_satisfies, gt_continue_on_error, gt_aggregator_permissive, gt_no_propagation, gt_no_gate]
