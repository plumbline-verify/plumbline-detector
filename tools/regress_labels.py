"""Re-run the detector over repositories from earlier precision rounds and
report, per label, how many labeled findings the current ruleset still
produces. A regression check only: these repositories are no longer
held out, so the result is not a precision measurement.

A labeled finding is matched by (check, file, line). Repositories must be
checked out at the commit recorded in the round's repositories.json.

Usage: python tools/regress_labels.py --round docs/precision/round3 --repos DIR [--repos DIR ...] [--show FP-detector]
"""

import argparse
import json
import os
import subprocess
from collections import Counter

from plumbline_detector.record import analyze


def head(path):
    try:
        return subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", required=True, action="append")
    ap.add_argument("--repos", required=True, action="append")
    ap.add_argument("--show", action="append", default=[])
    a = ap.parse_args()
    total = Counter()
    for rd in a.round:
        commits = json.load(open(os.path.join(rd, "repositories.json")))
        rows = [json.loads(line) for line in open(os.path.join(rd, "labeled_findings.jsonl")) if line.strip()]
        by_repo = {}
        for row in rows:
            by_repo.setdefault(row["repo"], []).append(row)
        for repo, items in sorted(by_repo.items()):
            path = next((os.path.join(d, repo) for d in a.repos if os.path.isdir(os.path.join(d, repo))), None)
            if path is None or head(path) != commits.get(repo):
                print(f"skip {repo}: checkout missing or at another commit")
                continue
            rec = analyze(path)
            have = {(c["id"], f["file"], f["line"]) for c in rec["checks"] for f in c["findings"]}
            for row in items:
                kept = (row["check"], row["file"], row["line"]) in have
                total[(row["label"], kept)] += 1
                if row["label"] in a.show and kept:
                    print(f"  still reported [{row['label']}] {row['check']} {repo}/{row['file']}:{row['line']}")
                if row["label"] == "TP" and not kept:
                    print(f"  LOST TP {row['check']} {repo}/{row['file']}:{row['line']}  {row['message'][:80]}")
    for label in ("TP", "FP-detector", "FP-scope"):
        k, g = total[(label, True)], total[(label, False)]
        print(f"{label}: {k} still reported, {g} no longer reported")


if __name__ == "__main__":
    main()
