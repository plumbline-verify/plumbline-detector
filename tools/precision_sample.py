"""Draw the labeling sample for the held-out precision study.

For each check (except GT-NO-GATE), pool findings across the given records;
label all if there are 40 or fewer, else draw 40 with random.Random(SEED).
Each sampled item carries the source around its location so a labeler does
not need the repository. Output: one JSON object per line.

Usage: `python tools/precision_sample.py --records DIR --repos DIR --out sample.jsonl`
"""

import argparse
import glob
import json
import os
import random

SEED = 20260922
CAP = 40
CONTEXT = 12


def context(repo_dir, file, line):
    path = os.path.join(repo_dir, file)
    if not os.path.isfile(path):
        return None
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    if line is None:
        lo, hi = 0, min(len(lines), 2 * CONTEXT)
    else:
        lo, hi = max(0, line - 1 - CONTEXT), min(len(lines), line + CONTEXT)
    return "\n".join(f"{i + 1:5d}{'>' if line == i + 1 else ' '} {lines[i]}" for i in range(lo, hi))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--repos", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pools = {}
    for f in sorted(glob.glob(os.path.join(a.records, "*.json"))):
        repo = os.path.basename(f)[:-5]
        rec = json.load(open(f))
        for c in rec["checks"]:
            if c["id"] == "GT-NO-GATE":
                continue
            for x in c["findings"]:
                pools.setdefault(c["id"], []).append((repo, x))
    rng = random.Random(SEED)
    n = 0
    with open(a.out, "w") as out:
        for check in sorted(pools):
            pool = sorted(pools[check], key=lambda rx: (rx[0], rx[1]["file"], rx[1]["line"] or 0, rx[1]["message"]))
            chosen = pool if len(pool) <= CAP else rng.sample(pool, CAP)
            for repo, x in chosen:
                n += 1
                item = {
                    "item": f"{check}#{n}",
                    "check": check,
                    "pool_size": len(pool),
                    "repo": repo,
                    "file": x["file"],
                    "line": x["line"],
                    "message": x["message"],
                    "detail": x.get("detail", {}),
                    "context": context(os.path.join(a.repos, repo), x["file"], x["line"]),
                }
                out.write(json.dumps(item, sort_keys=True) + "\n")
    print(f"{n} items")


if __name__ == "__main__":
    main()
