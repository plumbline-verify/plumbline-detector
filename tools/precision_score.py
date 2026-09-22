"""Score the held-out precision study.

Reads the sample (tools/precision_sample.py output) and label files, and
prints per-check precision with a 95% Wilson interval, pooled figures, and
the items drawn for the author's 20% audit (fixed seed).

Usage: python tools/precision_score.py --sample sample.jsonl --labels labels*.jsonl [--audit-out audit.txt]
"""

import argparse
import json
import math
import random
from collections import Counter, defaultdict

AUDIT_SEED = 20260923
LABELS = ("TP", "FP-detector", "FP-scope")


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True)
    ap.add_argument("--labels", nargs="+", required=True)
    ap.add_argument("--audit-out")
    a = ap.parse_args()
    items = {json.loads(l)["item"]: json.loads(l) for l in open(a.sample)}
    labels = {}
    for f in a.labels:
        for line in open(f):
            if line.strip():
                x = json.loads(line)
                assert x["label"] in LABELS, x
                assert x["item"] not in labels, f"duplicate label {x['item']}"
                labels[x["item"]] = x
    missing = sorted(set(items) - set(labels))
    extra = sorted(set(labels) - set(items))
    assert not missing and not extra, (missing, extra)
    by = defaultdict(Counter)
    pool = {}
    for iid, it in items.items():
        by[it["check"]][labels[iid]["label"]] += 1
        pool[it["check"]] = it["pool_size"]
    print("| Check | Findings (pool) | Labeled | TP | FP-detector | FP-scope | Precision | 95% CI |")
    print("|---|---|---|---|---|---|---|---|")
    tot = Counter()
    for check in sorted(by):
        c = by[check]
        n = sum(c.values())
        lo, hi = wilson(c["TP"], n)
        tot.update(c)
        print(f"| {check} | {pool[check]} | {n} | {c['TP']} | {c['FP-detector']} | {c['FP-scope']} | {c['TP'] / n:.0%} | {lo:.0%}–{hi:.0%} |")
    n = sum(tot.values())
    lo, hi = wilson(tot["TP"], n)
    print(f"| all labeled (unweighted) | | {n} | {tot['TP']} | {tot['FP-detector']} | {tot['FP-scope']} | {tot['TP'] / n:.0%} | {lo:.0%}–{hi:.0%} |")
    rng = random.Random(AUDIT_SEED)
    audit = sorted(rng.sample(sorted(items), math.ceil(len(items) * 0.2)))
    if a.audit_out:
        with open(a.audit_out, "w") as out:
            for iid in audit:
                it, lb = items[iid], labels[iid]
                out.write(f"=== {iid} [{it['repo']}] {it['file']}:{it['line']}\n{it['message']}\nLABEL {lb['label']}: {lb['reason']}\n{it['context']}\n\n")
    print(f"\naudit items ({len(audit)}): {', '.join(audit)}")


if __name__ == "__main__":
    main()
