"""Agent PR integrity study (docs/AGENT_PR_STUDY.md): prevalence tables from
aidev_scan.py output, and the seeded precision sample.

  python tools/aidev_report.py prevalence --dir DIR [--qualifying RULE ...]
  python tools/aidev_report.py sample --dir DIR [--batches 3]
"""

import argparse
import json
import math
import os
import random
from collections import defaultdict

SEED = 20260926
PER_RULE = 30
MIN_CELL = 5


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt(k, n):
    if n < MIN_CELL:
        return "n<5"
    lo, hi = wilson(k, n)
    return f"{k / n:.2%} ({lo:.2%}–{hi:.2%}), {k}/{n}"


def prevalence(a):
    prs = [json.loads(l) for l in open(os.path.join(a.dir, "prs.jsonl"))]
    prs = [p for p in prs if p["has_patches"]]
    rules = sorted({r for p in prs for r in p["rules"]})
    agents = sorted({p["agent"] for p in prs})
    qual = set(a.qualifying) if a.qualifying else set(rules)
    lines = []
    for scope, sel in (("all PRs", lambda p: True), ("merged PRs", lambda p: p["merged"])):
        lines.append(f"\n### {scope}\n")
        lines.append("| Rule | " + " | ".join(agents) + " | all |")
        lines.append("|---|" + "---|" * (len(agents) + 1))
        for rule in rules + ["ANY (qualifying)"]:
            row = [rule]
            for ag in agents + [None]:
                pool = [p for p in prs if sel(p) and (ag is None or p["agent"] == ag)]
                if rule.startswith("ANY"):
                    k = sum(1 for p in pool if qual & set(p["rules"]))
                else:
                    k = sum(1 for p in pool if rule in p["rules"])
                row.append(fmt(k, len(pool)))
            lines.append("| " + " | ".join(row) + " |")
        pool = [p for p in prs if sel(p)]
        lines.append(f"\nPRs with patches: {len(pool)}; touching test files: {sum(p['touches_tests'] for p in pool)}; touching workflows: {sum(p['touches_workflows'] for p in pool)}")
    print("\n".join(lines))


def sample(a):
    by_rule = defaultdict(list)
    for line in open(os.path.join(a.dir, "flagged.jsonl")):
        it = json.loads(line)
        by_rule[it["rule"]].append(it)
    rng = random.Random(SEED)
    items = []
    for rule in sorted(by_rule):
        pool = by_rule[rule]
        chosen = pool if len(pool) <= PER_RULE else rng.sample(pool, PER_RULE)
        for it in chosen:
            items.append({"item": f"{rule}#{len(items) + 1}", "rule": rule, "pool_size": len(pool), "filename": it["filename"], "status": it["status"], "detail": it["detail"], "patch": it["patch"], "agent": it["agent"]})
    with open(os.path.join(a.dir, "sample.jsonl"), "w") as out:
        for it in items:
            out.write(json.dumps(it) + "\n")
    for i in range(a.batches):
        with open(os.path.join(a.dir, f"batch{i + 1}.jsonl"), "w") as out:
            for it in items[i::a.batches]:
                out.write(json.dumps({k: v for k, v in it.items() if k != "agent"}) + "\n")  # labelers do not see the agent
    print({r: len(v) for r, v in sorted(by_rule.items())}, len(items))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prevalence")
    p.add_argument("--dir", required=True)
    p.add_argument("--qualifying", nargs="*")
    s = sub.add_parser("sample")
    s.add_argument("--dir", required=True)
    s.add_argument("--batches", type=int, default=3)
    a = ap.parse_args()
    {"prevalence": prevalence, "sample": sample}[a.cmd](a)


if __name__ == "__main__":
    main()
