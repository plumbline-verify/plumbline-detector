"""GitHub Actions workflow model built from line-preserving YAML.

Only constructs on the allowlists below are interpreted. Anything else in a
position that matters to gating is recorded as an issue, and every check that
depends on that position returns UNKNOWN rather than PASS.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from . import yamlnodes as Y
from ..model import Location

WORKFLOW_DIR = ".github/workflows"
PR_EVENTS = frozenset({"pull_request", "pull_request_target", "merge_group"})

# Job-level `if:` forms that cannot cause the job to be skipped by a
# conditional. Allowlist: every other expression is treated as skippable.
NON_SKIPPING_IFS = frozenset(
    {"always()", "!cancelled()", "true", "success() || failure()", "failure() || success()"}
)

# Commands that run a test suite. Allowlist: a job is classified test-running
# by command only if one of these matches a `run:` script.
TEST_COMMAND_PATTERNS = [
    re.compile(p)
    for p in (
        r"\bpytest\b",
        r"\bpy\.test\b",
        r"-m\s+unittest\b",
        r"(^|[\s;&|(])(tox|nox)(\s|$)",
        r"\bmake\s+(-\S+\s+)*(test|tests|check)\b",
        r"\b(npm|pnpm|yarn|bun)\s+(run\s+)?test\b",
        r"\b(jest|vitest|mocha|karma)\b",
        r"\bgo\s+test\b",
        r"\bcargo\s+(test|nextest)\b",
        r"\bmvnw?\b.*\b(test|verify)\b",
        r"\bgradlew?\b.*\b(test|check)\b",
        r"\bdotnet\s+test\b",
        r"\bctest\b",
        r"\bbazel\s+test\b",
        r"\brspec\b",
        r"\bphpunit\b",
        r"\bhatch\s+(test|run\s+\S*test)",
        r"\bcoverage\s+run\b",
        r"\bjust\s+test\b",
        r"manage\.py\s+test\b",
        r"\bswift\s+test\b",
        r"\bmix\s+test\b",
    )
]
TEST_NAME_RE = re.compile(r"(^|[^a-z])(tests?|pytest)([^a-z]|$)")

AGGREGATOR_NAME_RE = re.compile(
    r"(all[-_ ]?(green|pass(ed)?|done|ok|checks?|jobs?|tests?|required)"
    r"|ci[-_ ]?(success|ok|pass(ed)?|done|status|result|required)"
    r"|required|summary|conclusion|gate|results?|finished|complete"
    r"|status[-_ ]?checks?|check[-_ ]?(all|status)|alls-green|merge[-_ ]?ready|success)"
)
# Step commands that do nothing substantive: the shape of an aggregator body.
TRIVIAL_RUN_RE = re.compile(
    r"^\s*(echo\b.*|exit\s+\d+|true|false|:|printf\b.*|\[\[?.*|test\s.*|jq\b.*|if\b.*|then\b.*|else\b.*|fi|elif\b.*|done|for\b.*|do\b.*|#.*|)\s*$"
)
ALLS_GREEN_RE = re.compile(r"^re-actors/alls-green@")


def norm_expr(value) -> str:
    s = str(value).strip()
    if s.startswith("${{") and s.endswith("}}"):
        s = s[3:-2].strip()
    return re.sub(r"\s+", " ", s).lower()


@dataclass
class Step:
    index: int
    line: int
    name: str | None
    run: str | None
    uses: str | None
    if_expr: str | None
    continue_on_error: str | None  # raw value
    coe_line: int | None
    texts: list[str]  # every string value in the step, for reference scans


@dataclass
class Job:
    workflow: str
    id: str
    line: int
    name: str | None
    if_expr: str | None
    if_line: int | None
    needs: list[str]
    steps: list[Step]
    uses: str | None
    continue_on_error: str | None
    coe_line: int | None
    has_matrix: bool
    raw_texts: list[str]

    @property
    def display(self) -> str:
        return self.name if self.name is not None else self.id

    def key(self):
        return (self.workflow, self.id)


@dataclass
class Workflow:
    path: str
    triggers: set[str]
    jobs: dict[str, Job]

    @property
    def pr_triggered(self) -> bool:
        return bool(self.triggers & PR_EVENTS)


@dataclass
class GHAModel:
    workflow_paths: list[str] = field(default_factory=list)
    workflows: dict[str, Workflow] = field(default_factory=dict)
    issues: list[Location] = field(default_factory=list)  # parse / shape problems

    def pr_jobs(self):
        for wf in self.workflows.values():
            if wf.pr_triggered:
                for job in wf.jobs.values():
                    yield job

    def issues_for(self, path: str):
        return [i for i in self.issues if i.file == path]


def _strings(value, out):
    if isinstance(value, str):
        out.append(str(value))
    elif isinstance(value, dict):
        for v in value.values():
            _strings(v, out)
    elif isinstance(value, list):
        for v in value:
            _strings(v, out)
    return out


def _scalar(value, what, path, issues):
    if value is None:
        return None
    if isinstance(value, Y.YStr):
        return str(value)
    issues.append(Location(path, Y.line_of(value), f"{what} is not a scalar; cannot interpret"))
    return None


def _parse_triggers(on, path, issues) -> set[str]:
    if isinstance(on, Y.YStr):
        return {str(on)}
    if isinstance(on, Y.YList) and all(isinstance(x, Y.YStr) for x in on):
        return {str(x) for x in on}
    if isinstance(on, Y.YMap):
        return set(on.keys())
    issues.append(Location(path, Y.line_of(on), "unrecognized 'on:' trigger shape"))
    return set()


def _parse_step(i, raw, path, issues) -> Step | None:
    if not isinstance(raw, Y.YMap):
        issues.append(Location(path, Y.line_of(raw), f"step {i} is not a mapping"))
        return None
    run = _scalar(raw.get("run"), "step run", path, issues)
    uses = _scalar(raw.get("uses"), "step uses", path, issues)
    if run is None and uses is None:
        issues.append(Location(path, raw.line, f"step {i} has neither run nor uses"))
    return Step(
        index=i,
        line=raw.line,
        name=_scalar(raw.get("name"), "step name", path, issues),
        run=run,
        uses=uses,
        if_expr=_scalar(raw.get("if"), "step if", path, issues),
        continue_on_error=_scalar(raw.get("continue-on-error"), "continue-on-error", path, issues),
        coe_line=raw.key_lines.get("continue-on-error"),
        texts=_strings(raw, []),
    )


def _parse_job(wf_path, job_id, raw, issues) -> Job | None:
    if not isinstance(raw, Y.YMap):
        issues.append(Location(wf_path, Y.line_of(raw), f"job {job_id!r} is not a mapping"))
        return None
    needs_raw = raw.get("needs")
    needs: list[str] = []
    if isinstance(needs_raw, Y.YStr):
        needs = [str(needs_raw)]
    elif isinstance(needs_raw, Y.YList) and all(isinstance(n, Y.YStr) for n in needs_raw):
        needs = [str(n) for n in needs_raw]
    elif needs_raw is not None:
        issues.append(Location(wf_path, Y.line_of(needs_raw), f"job {job_id!r}: unrecognized needs shape"))
    steps_raw = raw.get("steps")
    steps: list[Step] = []
    if isinstance(steps_raw, Y.YList):
        for i, s in enumerate(steps_raw):
            st = _parse_step(i, s, wf_path, issues)
            if st is not None:
                steps.append(st)
    elif steps_raw is not None:
        issues.append(Location(wf_path, Y.line_of(steps_raw), f"job {job_id!r}: steps is not a list"))
    uses = _scalar(raw.get("uses"), "job uses", wf_path, issues)
    if steps_raw is None and uses is None:
        issues.append(Location(wf_path, raw.line, f"job {job_id!r} has neither steps nor uses"))
    strategy = raw.get("strategy")
    has_matrix = isinstance(strategy, Y.YMap) and "matrix" in strategy
    return Job(
        workflow=wf_path,
        id=job_id,
        line=raw.line,
        name=_scalar(raw.get("name"), "job name", wf_path, issues),
        if_expr=_scalar(raw.get("if"), "job if", wf_path, issues),
        if_line=raw.key_lines.get("if"),
        needs=needs,
        steps=steps,
        uses=uses,
        continue_on_error=_scalar(raw.get("continue-on-error"), "continue-on-error", wf_path, issues),
        coe_line=raw.key_lines.get("continue-on-error"),
        has_matrix=has_matrix,
        raw_texts=_strings(raw, []),
    )


def is_workflow_path(p: str) -> bool:
    pp = PurePosixPath(p)
    return str(pp.parent) == WORKFLOW_DIR and pp.suffix in (".yml", ".yaml")


def build(snap) -> GHAModel:
    m = GHAModel()
    for p in snap.all_paths():
        if not is_workflow_path(p):
            continue
        m.workflow_paths.append(p)
        if p in snap.unread:
            m.issues.append(Location(p, None, f"workflow not read: {snap.unread[p]}"))
            continue
        try:
            doc = Y.load(snap.files[p])
        except Y.YAMLShapeError as e:
            m.issues.append(Location(p, e.line, f"workflow unparseable: {e}"))
            continue
        if not isinstance(doc, Y.YMap):
            m.issues.append(Location(p, Y.line_of(doc), "workflow top level is not a mapping"))
            continue
        before = len(m.issues)
        if "on" not in doc:
            m.issues.append(Location(p, doc.line, "workflow has no 'on:' key"))
            triggers = set()
        else:
            triggers = _parse_triggers(doc["on"], p, m.issues)
        jobs_raw = doc.get("jobs")
        jobs: dict[str, Job] = {}
        if not isinstance(jobs_raw, Y.YMap):
            m.issues.append(Location(p, Y.line_of(jobs_raw, doc.line), "workflow 'jobs:' missing or not a mapping"))
        else:
            for jid, jraw in jobs_raw.items():
                job = _parse_job(p, jid, jraw, m.issues)
                if job is not None:
                    jobs[jid] = job
            for job in jobs.values():
                for n in job.needs:
                    if n not in jobs:
                        m.issues.append(Location(p, job.line, f"job {job.id!r} needs unknown job {n!r}"))
        del before
        m.workflows[p] = Workflow(path=p, triggers=triggers, jobs=jobs)
    return m


# --- classification -------------------------------------------------------


def step_runs_tests(step: Step) -> bool:
    if step.run is None:
        return False
    return any(pat.search(step.run) for pat in TEST_COMMAND_PATTERNS)


def local_callee(model: GHAModel, job: Job) -> Workflow | None:
    if job.uses and job.uses.startswith("./"):
        return model.workflows.get(job.uses[2:].split("@")[0])
    return None


def job_test_status(model: GHAModel, job: Job, _seen=None) -> str:
    """'yes' | 'no' | 'unknown'. By command first, then by job name/id."""
    if any(step_runs_tests(s) for s in job.steps):
        return "yes"
    if job.uses:
        callee = local_callee(model, job)
        if callee is None:
            return "unknown"
        seen = _seen or set()
        if callee.path in seen:
            return "unknown"
        seen = seen | {callee.path}
        stats = {job_test_status(model, j, seen) for j in callee.jobs.values()}
        if "yes" in stats:
            return "yes"
        return "unknown" if "unknown" in stats else "no"
    label = f"{job.id} {job.name or ''}".lower()
    if TEST_NAME_RE.search(label):
        return "yes"
    return "no"


def is_skippable_if(expr: str | None) -> bool:
    return expr is not None and norm_expr(expr) not in NON_SKIPPING_IFS


def runs_always(job: Job) -> bool:
    return job.if_expr is not None and norm_expr(job.if_expr) in NON_SKIPPING_IFS


def _trivial_step(step: Step) -> bool:
    if step.uses is not None:
        return bool(ALLS_GREEN_RE.match(step.uses))
    if step.run is None:
        return False
    return all(TRIVIAL_RUN_RE.match(line) for line in step.run.splitlines())


def is_aggregator(model: GHAModel, job: Job) -> bool:
    if not job.needs or job.uses:
        return False
    if any(step_runs_tests(s) for s in job.steps):
        return False
    named = bool(AGGREGATOR_NAME_RE.search(f"{job.id} {job.name or ''}".lower()))
    trivial = all(_trivial_step(s) for s in job.steps)
    return named or trivial


_NEEDS_RESULT_RE = re.compile(r"needs\.(\*|[A-Za-z_][\w-]*)\.result")
_FAILING_EXIT_RE = re.compile(r"\bexit\s+1\b|(^|[\s;&|])false\b|\[\[?\s|\btest\s|\bjq\s+-e\b|\bexit\s+\$")


def verification(job: Job) -> tuple[str, set[str]]:
    """How an aggregator inspects its needs.

    Returns (kind, covered) where kind is:
      'alls-green'  re-actors/alls-green consumes toJSON(needs)
      'explicit'    a step references needs.<x>.result and can exit non-zero
      'unrecognized' needs results are referenced in a form we do not model
      'none'        needs results are never inspected
    covered is the set of need names verified ('*' means all).
    """
    for s in job.steps:
        if s.uses and ALLS_GREEN_RE.match(s.uses):
            if any("tojson(needs)" in re.sub(r"\s+", "", t.lower()) for t in s.texts):
                return "alls-green", {"*"}
            return "unrecognized", set()
    covered: set[str] = set()
    referenced = False
    for s in job.steps:
        refs: set[str] = set()
        for t in s.texts:
            refs |= set(_NEEDS_RESULT_RE.findall(t))
        if not refs:
            continue
        referenced = True
        can_fail = s.run is not None and bool(_FAILING_EXIT_RE.search(s.run))
        if can_fail:
            covered |= refs
    if covered:
        return "explicit", covered
    return ("unrecognized" if referenced else "none"), set()


def context_match(model: GHAModel, job: Job, ctx: str) -> bool:
    """Does this job produce a check run whose name equals the required context?"""
    disp = job.display
    if job.uses:
        return ctx == disp or ctx.startswith(disp + " / ")
    if "${{" in disp:
        parts = re.split(r"\$\{\{.*?\}\}", disp)
        pattern = ".+".join(re.escape(x) for x in parts)
        return re.fullmatch(pattern, ctx) is not None
    if job.has_matrix:
        return ctx == disp or ctx.startswith(disp + " (")
    return ctx == disp


# --- gate artifacts -------------------------------------------------------


@dataclass
class GateInfo:
    sources: list[str] = field(default_factory=list)
    contexts: set[str] = field(default_factory=set)
    issues: list[Location] = field(default_factory=list)
    protection_without_checks: list[Location] = field(default_factory=list)


def _is_ruleset_path(p: str) -> bool:
    pp = PurePosixPath(p)
    if pp.suffix != ".json":
        return False
    parts = pp.parts
    return (len(parts) >= 3 and parts[0] == ".github" and parts[1] == "rulesets") or (
        len(parts) == 2 and parts[0] == ".github" and "ruleset" in pp.name
    )


def _ruleset_contexts(doc, where, info: GateInfo):
    if not isinstance(doc, dict) or not isinstance(doc.get("rules"), list):
        info.issues.append(Location(where, None, "ruleset JSON lacks a 'rules' list"))
        return
    found_rule = False
    for rule in doc["rules"]:
        if not isinstance(rule, dict) or not isinstance(rule.get("type"), str):
            info.issues.append(Location(where, None, "ruleset rule without a string 'type'"))
            continue
        if rule["type"] != "required_status_checks":
            continue
        found_rule = True
        checks = (rule.get("parameters") or {}).get("required_status_checks")
        if not isinstance(checks, list):
            info.issues.append(Location(where, None, "required_status_checks rule without a checks list"))
            continue
        for c in checks:
            if isinstance(c, dict) and isinstance(c.get("context"), str):
                info.contexts.add(c["context"])
            else:
                info.issues.append(Location(where, None, "required status check entry without a string 'context'"))
    if not found_rule:
        info.protection_without_checks.append(Location(where, None, "ruleset declares no required_status_checks rule"))


def _settings_contexts(doc, where, info: GateInfo):
    branches = doc.get("branches") if isinstance(doc, Y.YMap) else None
    if branches is None:
        return False
    if not isinstance(branches, Y.YList):
        info.issues.append(Location(where, Y.line_of(branches), "settings 'branches' is not a list"))
        return True
    for b in branches:
        prot = b.get("protection") if isinstance(b, Y.YMap) else None
        if not isinstance(prot, Y.YMap):
            continue
        rsc = prot.get("required_status_checks")
        if not isinstance(rsc, Y.YMap):
            info.protection_without_checks.append(Location(where, prot.line, "branch protection declares no required_status_checks"))
            continue
        before = len(info.contexts)
        ctxs = rsc.get("contexts")
        if isinstance(ctxs, Y.YList):
            info.contexts |= {str(c) for c in ctxs if isinstance(c, Y.YStr)}
        checks = rsc.get("checks")
        if isinstance(checks, Y.YList):
            for c in checks:
                if isinstance(c, Y.YMap) and isinstance(c.get("context"), Y.YStr):
                    info.contexts.add(str(c["context"]))
        if len(info.contexts) == before:
            info.protection_without_checks.append(Location(where, rsc.line, "required_status_checks lists no contexts"))
    return True


def gate_info(snap, required_checks: list[str], gate_files: list[tuple[str, bytes]]) -> GateInfo:
    info = GateInfo()
    if required_checks:
        info.sources.append("operator:--required-check")
        info.contexts |= set(required_checks)
    for label, data in gate_files:
        info.sources.append(f"operator:{label}")
        try:
            doc = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            info.issues.append(Location(label, None, f"gate file unparseable: {e}"))
            continue
        docs = doc if isinstance(doc, list) else [doc]
        for d in docs:
            _ruleset_contexts(d, label, info)
    for p in snap.all_paths():
        if _is_ruleset_path(p):
            info.sources.append(p)
            if p in snap.unread:
                info.issues.append(Location(p, None, f"ruleset not read: {snap.unread[p]}"))
                continue
            try:
                doc = json.loads(snap.files[p].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                info.issues.append(Location(p, None, f"ruleset unparseable: {e}"))
                continue
            _ruleset_contexts(doc, p, info)
        elif p in (".github/settings.yml", ".github/settings.yaml"):
            if p in snap.unread:
                info.sources.append(p)
                info.issues.append(Location(p, None, f"settings not read: {snap.unread[p]}"))
                continue
            try:
                doc = Y.load(snap.files[p])
            except Y.YAMLShapeError as e:
                info.sources.append(p)
                info.issues.append(Location(p, e.line, f"settings unparseable: {e}"))
                continue
            if _settings_contexts(doc, p, info):
                info.sources.append(p)
    return info
