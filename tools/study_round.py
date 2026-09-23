"""Run one round of the held-out precision study, the detector's learning
loop (docs/PRECISION_STUDY.md, "How the detector learns").

The detector itself stays offline; this harness is the operator's tool and
is the only part that reaches the network (to clone the round's
repositories). Two steps, with human-reviewed labeling between them:

  prepare   clone the pre-registered repositories (shallow, default branch),
            record their commits, run the detector on each, draw the sample,
            and write the labelers' packet: definitions.md (README check
            definitions at this commit plus the label rubric), batchN.jsonl,
            and LABELER_PROMPT.md.
  finalize  validate labelsN.jsonl, score (per check and pooled, Wilson
            95%), write the author-audit sheet, commit-ready files under
            docs/precision/roundN/ (labeled_findings.jsonl,
            repositories.json, round.json, score.md), and rebuild
            measurements.json, which recalibrates every check's grade.

Before `prepare`, the round's protocol (repository list, detector commit)
must already be committed in docs/PRECISION_STUDY.md; `prepare` refuses to
run on a dirty tree so the detector under test is exactly a commit.

Usage:
  python tools/study_round.py prepare  --round 5 --repos-file r5.txt --workdir W [--batches 4]
  python tools/study_round.py finalize --round 5 --workdir W
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import subprocess
import sys

from plumbline_detector import SCHEMA_VERSION
from plumbline_detector.record import analyze, dumps, ruleset_fingerprint

ROOT = pathlib.Path(__file__).resolve().parent.parent

LABEL_KEYS = {"TP": "tp", "FP-detector": "fp_detector", "FP-scope": "fp_scope"}

PROMPT = """You are an independent reviewer labeling findings produced by a static
analysis tool that checks whether a repository's test and CI evidence
actually verifies anything. Your labels measure the tool's precision, so be
accurate and skeptical in both directions.

Directory: {workdir}

1. Read `definitions.md` fully: each check's definition, the three labels
   (TP, FP-detector, FP-scope) and the scope rules.
2. Read `batch{{N}}.jsonl`: one finding per line (check, repo, file, line,
   message, detail, source context).
3. For each finding inspect the repository at `<directory>/<repo>/` (the
   file, helpers, conftest.py, test configuration, package.json, runner
   config, .github/workflows) as needed to decide whether the construct the
   check describes is present at that location and has the stated effect.
4. Write `labels{{N}}.jsonl`: one line per item, in order:
   {{"item": ..., "label": "TP" | "FP-detector" | "FP-scope", "reason": "<concrete evidence, file:line>"}}

Rules: read nothing outside definitions.md, your batch and the repositories
(not the detector's code, not earlier rounds). Do not run the tool, use the
network, or modify the repositories. No person's name, email or profile in
reasons. A deliberate construct is still a TP if the description holds.
"""

SCOPE_RULES = """
**Scope rule for EC-NO-ASSERTION (and -JS).** These checks concern correctness
tests. A benchmark (pytest-benchmark / CodSpeed, or a perf-only loop) is out
of their scope: label FP-scope if one is reported. A test that CI never runs
(example or demo projects, files outside the configured test paths) is
FP-scope for every check except EC-TESTS-NOT-RUN(-JS).

"""


def git(*args, cwd=ROOT):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def definitions() -> str:
    readme = (ROOT / "README.md").read_text()
    proto = (ROOT / "docs/PRECISION_STUDY.md").read_text()
    labels = proto[proto.index("**Labels.**"):proto.index("**Labelers.**")]
    run = readme[readme.index("### Which tests actually run"):readme.index("## The checks")]
    checks = readme[readme.index("## The checks"):readme.index("## Measuring the detector")]
    js = readme[readme.index("### Evidence channel (JavaScript / TypeScript)"):readme.index("## Layout")]
    return "# Labeling definitions\n\n" + labels + SCOPE_RULES + run + checks + js


def prepare(a):
    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("refusing: the detector tree has uncommitted changes; commit the protocol first")
    work = pathlib.Path(a.workdir)
    work.mkdir(parents=True, exist_ok=True)
    slugs = [s.strip() for s in open(a.repos_file) if s.strip() and not s.startswith("#")]
    commits, missing = {}, []
    for slug in slugs:
        name = slug.split("/")[-1]
        dest = work / name
        if not dest.exists():
            r = subprocess.run(["git", "clone", "-q", "--depth", "1", f"https://github.com/{slug}", str(dest)])
            if r.returncode != 0:
                missing.append(slug)  # reported missing, never replaced
                continue
        commits[name] = git("rev-parse", "HEAD", cwd=dest)
    (work / "repositories.json").write_text(json.dumps(commits, indent=2, sort_keys=True) + "\n")
    out = work / "out"
    out.mkdir(exist_ok=True)
    for name in sorted(commits):
        (out / f"{name}.json").write_text(dumps(analyze(str(work / name))))
    subprocess.run([sys.executable, str(ROOT / "tools/precision_sample.py"), "--records", str(out), "--repos", str(work), "--out", str(work / "sample.jsonl")], check=True)
    items = open(work / "sample.jsonl").readlines()
    for i in range(a.batches):
        (work / f"batch{i + 1}.jsonl").write_text("".join(items[i::a.batches]))
    (work / "definitions.md").write_text(definitions())
    (work / "LABELER_PROMPT.md").write_text(PROMPT.format(workdir=work.resolve()))
    meta = {
        "round": a.round,
        "schema": SCHEMA_VERSION,
        "detector_commit": git("rev-parse", "--short", "HEAD"),
        "ruleset_fingerprint": ruleset_fingerprint(),
        "date": datetime.date.today().isoformat(),
    }
    (work / "round.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    print(f"{len(commits)} repositories, {len(items)} items in {a.batches} batches; missing: {missing or 'none'}")
    print(f"next: give each labeler {work / 'LABELER_PROMPT.md'} with N = 1..{a.batches}, then run finalize")


def finalize(a):
    work = pathlib.Path(a.workdir)
    items = {json.loads(l)["item"]: json.loads(l) for l in open(work / "sample.jsonl")}
    labels = {}
    for f in sorted(work.glob("labels*.jsonl")):
        for line in open(f):
            if line.strip():
                x = json.loads(line)
                if x["label"] not in LABEL_KEYS or x["item"] in labels:
                    sys.exit(f"bad or duplicate label in {f}: {x}")
                labels[x["item"]] = x
    if set(items) != set(labels):
        sys.exit(f"labels do not cover the sample: missing {sorted(set(items) - set(labels))[:5]}, extra {sorted(set(labels) - set(items))[:5]}")
    dest = ROOT / f"docs/precision/round{a.round}"
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    for iid in sorted(items):
        it, lb = items[iid], labels[iid]
        rows.append({k: it[k] for k in ("item", "check", "repo", "file", "line", "message", "pool_size")} | {"commit": json.load(open(work / "repositories.json"))[it["repo"]], "label": lb["label"], "reason": lb["reason"]})
    (dest / "labeled_findings.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    (dest / "repositories.json").write_text((work / "repositories.json").read_text())
    (dest / "round.json").write_text((work / "round.json").read_text())
    score = subprocess.run(
        [sys.executable, str(ROOT / "tools/precision_score.py"), "--sample", str(work / "sample.jsonl"), "--labels", *map(str, sorted(work.glob("labels*.jsonl"))), "--audit-out", str(work / "audit.txt")],
        capture_output=True, text=True, check=True,
    ).stdout
    (dest / "score.md").write_text(score)
    subprocess.run([sys.executable, str(ROOT / "tools/build_measurements.py")], check=True)
    print(score)
    print(f"audit sheet: {work / 'audit.txt'}; round files: {dest}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--repos-file", required=True)
    p.add_argument("--workdir", required=True)
    p.add_argument("--batches", type=int, default=4)
    f = sub.add_parser("finalize")
    f.add_argument("--round", type=int, required=True)
    f.add_argument("--workdir", required=True)
    a = ap.parse_args()
    {"prepare": prepare, "finalize": finalize}[a.cmd](a)


if __name__ == "__main__":
    main()
