"""Score the detector on TRACE extractions (docs/RECALL_STUDY.md).

Inputs (all kept outside the repository; TRACE is CC-BY-SA-4.0):
  --extract  output of tools/trace_extract.py
  --labels   parsed labels from tools/trace_extract.py --labels-out
  --blind    code-visible labels, {trajectory_id: "yes" | "no" | "unclear"}
Outputs:
  --rows     per-trajectory flags (scratch only; never committed)
  stdout     the aggregate tables for docs/RECALL_STUDY.md

Usage: python tools/trace_recall.py --extract E --labels L --blind B --rows R
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import patch_scan  # noqa: E402

from plumbline_detector import pr  # noqa: E402

TM, TCT, CG = "Test Modification", "Test Case Targeting", "Coverage Gaming"
TSE = {TM, TCT, CG}


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt(k, n):
    if n == 0:
        return "n = 0"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.1%} ({lo:.1%}–{hi:.1%})"


def is_test_or_ci(path):
    return patch_scan.is_test_path(path) or bool(patch_scan.WORKFLOW_RE.search(path))


def _put(root, path, content):
    dest = os.path.join(root, path)
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w") as f:
            f.write(content)
        return True
    except OSError:  # a path that is also a directory in this trajectory
        return False


def pr_mode(rec):
    """PR-mode findings on the reconstructable part of one trajectory."""
    changed = [f for f in rec["files"] if f["reconstructable"]]
    if not changed:
        return None, []
    tmp = tempfile.mkdtemp(prefix="trace-pr-")
    base, head = os.path.join(tmp, "base"), os.path.join(tmp, "head")
    os.makedirs(base)
    os.makedirs(head)
    try:
        for c in rec["context"]:
            _put(base, c["path"], c["content"])
            _put(head, c["path"], c["content"])
        for f in changed:
            if f["status"] != "added" and f["base"] is not None:
                _put(base, f["path"], f["base"])
            if f["status"] != "removed" and f["head"] is not None:
                _put(head, f["path"], f["head"])
        try:
            r = pr.compare(base, head)
        except Exception as e:  # reported, never silently dropped
            return f"error: {e!r}"[:200], []
        return None, [{"check": ch["id"], "file": x["file"], "message": x["message"][:160]} for ch in r["checks"] for x in ch["findings"]]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def score(rec):
    net = [(f["path"], rule) for f in rec["files"] for rule, _ in patch_scan.scan_file(f["path"], f["status"], f["patch"])]
    per_edit = [(e["path"], rule) for e in rec["events"] for rule, _ in patch_scan.scan_file(e["path"], e["status"], e["patch"])]
    err, prf = pr_mode(rec)
    return {
        "patch_rules": sorted({r for _, r in net}),
        "per_edit": sorted({r for _, r in per_edit}),
        "pr_mode": sorted({x["check"] for x in prf}),
        "pr_findings": prf,
        "pr_error": err,
        "any_change": bool(rec["files"]),
        "test_change": any(is_test_or_ci(f["path"]) for f in rec["files"]),
        "pr_reconstructable": any(is_test_or_ci(f["path"]) and f["reconstructable"] for f in rec["files"]),
        "unreconstructed": bool(rec["unreconstructed"]) or any(not f["reconstructable"] for f in rec["files"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--blind", required=True)
    ap.add_argument("--rows", required=True)
    a = ap.parse_args()
    labels = {json.loads(l)["trajectory_id"]: json.loads(l) for l in open(a.labels)}
    blind = json.load(open(a.blind))
    rows = []
    for line in open(a.extract):
        rec = json.loads(line)
        lab = labels[rec["trajectory_id"]]
        s = score(rec)
        s["combined"] = bool(s["patch_rules"] or s["pr_mode"])
        cats = set(lab["categories"])
        s.update(trajectory_id=rec["trajectory_id"], benign=lab["benign"], categories=sorted(cats), code_visible=blind.get(rec["trajectory_id"]))
        rows.append(s)
    with open(a.rows, "w") as out:
        for r in rows:
            out.write(json.dumps(r) + "\n")

    pops = {
        "H-TM": [r for r in rows if TM in r["categories"]],
        "H-TSE": [r for r in rows if TSE & set(r["categories"])],
        "H-TCT": [r for r in rows if TCT in r["categories"]],
        "H-CG": [r for r in rows if CG in r["categories"]],
        "B": [r for r in rows if r["benign"]],
        "H-other": [r for r in rows if r["categories"] and not TSE & set(r["categories"])],
    }
    vis = [r for r in pops["H-TM"] if r["code_visible"] == "yes"]
    vis_rec = [r for r in vis if r["pr_reconstructable"]]
    b_rec = [r for r in pops["B"] if r["pr_reconstructable"]]
    units = [("Patch rules (per file, primary)", lambda r: bool(r["patch_rules"])), ("Patch rules (per edit)", lambda r: bool(r["per_edit"])), ("PR mode", lambda r: bool(r["pr_mode"])), ("Combined", lambda r: r["combined"])]

    print("## Coverage\n")
    print("| Population | Trajectories | Any change | Test/CI change | PR-reconstructable | Unreconstructed edits | PR-mode errors |")
    print("|---|---|---|---|---|---|---|")
    for name, p in pops.items():
        print(f"| {name} | {len(p)} | {sum(r['any_change'] for r in p)} | {sum(r['test_change'] for r in p)} | {sum(r['pr_reconstructable'] for r in p)} | {sum(r['unreconstructed'] for r in p)} | {sum(bool(r['pr_error']) for r in p)} |")
    cv = collections.Counter(r["code_visible"] for r in pops["H-TM"])
    print(f"\nCode-visible labels on H-TM: yes {cv['yes']}, no {cv['no']}, unclear {cv['unclear']}, missing {cv[None]}.\n")

    print("## Measures 1, 2 and 4: recall and false-alarm rate\n")
    print("| Detector | Recall, H-TM (1) | Recall, code-visible H-TM (2) | False alarms, B (4) |")
    print("|---|---|---|---|")
    for name, f in units:
        print(f"| {name} | {fmt(sum(map(f, pops['H-TM'])), len(pops['H-TM']))} | {fmt(sum(map(f, vis)), len(vis))} | {fmt(sum(map(f, pops['B'])), len(pops['B']))} |")
    print("\n## Measure 3 and the decision inputs (PR mode)\n")
    k3 = sum(bool(r["pr_mode"]) for r in vis_rec)
    kb = sum(bool(r["pr_mode"]) for r in b_rec)
    print(f"- PR-mode recall, code-visible and PR-reconstructable H-TM: {fmt(k3, len(vis_rec))}")
    print(f"- PR-mode false alarms, PR-reconstructable B: {fmt(kb, len(b_rec))}")
    print(f"- Combined recall, code-visible and PR-reconstructable H-TM: {fmt(sum(r['combined'] for r in vis_rec), len(vis_rec))}")
    print("\n## Measures 5 and 7: combined detector by category\n")
    print("| Population | Flagged (combined) |")
    print("|---|---|")
    for name in ("H-TSE", "H-TM", "H-TCT", "H-CG", "H-other"):
        p = pops[name]
        print(f"| {name} | {fmt(sum(r['combined'] for r in p), len(p))} |")
    print("\n## Measure 8: which rules and checks fire (trajectories)\n")
    print("| Rule or check | H-TM | H-TSE | H-other | B |")
    print("|---|---|---|---|---|")
    names = sorted({x for r in rows for x in r["patch_rules"] + r["pr_mode"]})
    for n in names:
        c = [sum(n in r["patch_rules"] + r["pr_mode"] for r in pops[p]) for p in ("H-TM", "H-TSE", "H-other", "B")]
        print(f"| {n} | " + " | ".join(map(str, c)) + " |")


if __name__ == "__main__":
    main()
