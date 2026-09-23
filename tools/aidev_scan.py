"""Agent PR integrity study (docs/AGENT_PR_STUDY.md): stream AIDev's
file-level patches, apply tools/patch_scan.py, and write per-PR flags plus
the flagged patches for sampling.

Only the columns named in the protocol are read. Nothing about authors,
committers, users, titles, bodies, messages or repository names is loaded.

Usage: python tools/aidev_scan.py --out DIR
"""

import argparse
import json
import os
import sys
import urllib.request

import fsspec
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(__file__))
from patch_scan import is_test_path, scan_file  # noqa: E402

BASE = "https://huggingface.co/datasets/hao-li/AIDev-7.6M/resolve/{rev}/{name}"
API = "https://huggingface.co/api/datasets/hao-li/AIDev-7.6M"
PATCH_KEEP = 8000  # characters of patch kept for labeling


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rev = json.load(urllib.request.urlopen(API))["sha"]
    fs = fsspec.filesystem("https")

    prs = pq.ParquetFile(fs.open(BASE.format(rev=rev, name="pull_request.parquet"), block_size=2**22)).read(columns=["id", "agent", "state", "merged_at"]).to_pydict()
    meta = {i: (ag, bool(m)) for i, ag, m in zip(prs["id"], prs["agent"], prs["merged_at"])}
    flags = {}  # pr_id -> set(rules)
    touched = {}  # pr_id -> (touches tests, touches workflows)
    flagged_items = open(os.path.join(a.out, "flagged.jsonl"), "w")
    pf = pq.ParquetFile(fs.open(BASE.format(rev=rev, name="pr_commit_details.parquet"), block_size=2**24))
    seen_patches = 0
    for g in range(pf.metadata.num_row_groups):
        t = pf.read_row_group(g, columns=["pr_id", "filename", "status", "patch"]).to_pydict()
        for pr_id, fn, st, patch in zip(t["pr_id"], t["filename"], t["status"], t["patch"]):
            if pr_id not in meta or fn is None:
                continue
            seen_patches += 1
            tt, tw = touched.get(pr_id, (False, False))
            touched[pr_id] = (tt or is_test_path(fn), tw or fn.startswith(".github/workflows/"))
            for rule, detail in scan_file(fn, st or "", patch):
                flags.setdefault(pr_id, set()).add(rule)
                flagged_items.write(json.dumps({"pr_id": pr_id, "agent": meta[pr_id][0], "rule": rule, "detail": detail, "filename": fn, "status": st, "patch": (patch or "")[:PATCH_KEEP]}) + "\n")
        del t
        print(f"row group {g + 1}/{pf.metadata.num_row_groups} done; patches in scope so far {seen_patches}", flush=True)
    flagged_items.close()
    with open(os.path.join(a.out, "prs.jsonl"), "w") as out:
        for pr_id, (agent, merged) in meta.items():
            tt, tw = touched.get(pr_id, (False, False))
            out.write(json.dumps({"pr_id": pr_id, "agent": agent, "merged": merged, "has_patches": pr_id in touched, "touches_tests": tt, "touches_workflows": tw, "rules": sorted(flags.get(pr_id, ()))}) + "\n")
    json.dump({"dataset": "hao-li/AIDev-7.6M", "revision": rev, "prs": len(meta), "patches_in_scope": seen_patches}, open(os.path.join(a.out, "run.json"), "w"), indent=2)
    print("done")


if __name__ == "__main__":
    main()
