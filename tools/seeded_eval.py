"""Seeded-tampering evaluation.

Measures the detector against a corpus of variants it was not written
against. Each variant is a directory of files to overlay onto a project, and
a manifest entry names its category (a check ID) and kind (tamper | benign).

Two modes, both reported:
  isolated  the variant alone, in an otherwise empty directory
  embedded  the variant overlaid onto a real host repository (noise test)

Scoring for a variant, looking only at the variant's target check:
  tamper  detected   = a finding located in one of the variant's files
          abstained  = no such finding, but an UNKNOWN located in them
          missed     = neither
  benign  false_alarm = a finding located in one of the variant's files
          clean       = no such finding
GT-NO-GATE findings are not file-located; for that check the verdict of the
isolated run is scored instead (FAIL = detected / false alarm), and embedded
mode is not scored.

Usage:
  python tools/seeded_eval.py --corpus DIR [--host DIR ...] [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import defaultdict

from plumbline_detector.record import CHECK_ORDER, analyze

UNLOCATED = {"GT-NO-GATE"}


def overlay(src_dir, dst_dir, files):
    for rel in files:
        dst = os.path.join(dst_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(src_dir, rel), dst)


def score(rec, entry, mode):
    check = {c["id"]: c for c in rec["checks"]}[entry["category"]]
    files = set(entry["files"])
    if entry["category"] in UNLOCATED:
        if mode != "isolated":
            return None
        hit, unk = check["verdict"] == "FAIL", check["verdict"] == "UNKNOWN"
    else:
        hit = any(f["file"] in files for f in check["findings"])
        unk = any(u["file"] in files for u in check["unknowns"])
    if entry["kind"] == "tamper":
        return "detected" if hit else ("abstained" if unk else "missed")
    return "false_alarm" if hit else "clean"


def other_checks_firing(rec, entry):
    files = set(entry["files"])
    return sorted(
        c["id"] for c in rec["checks"] if c["id"] != entry["category"] and any(f["file"] in files for f in c["findings"])
    )


def run(corpus, hosts):
    manifest = json.load(open(os.path.join(corpus, "manifest.json")))
    rows = []
    for entry in manifest:
        vdir = os.path.join(corpus, entry["id"])
        missing = [f for f in entry["files"] if not os.path.isfile(os.path.join(vdir, f))]
        if missing or entry["category"] not in CHECK_ORDER:
            rows.append({**entry, "error": f"bad manifest entry: missing={missing}"})
            continue
        row = {**entry, "results": {}}
        with tempfile.TemporaryDirectory() as tmp:
            overlay(vdir, tmp, entry["files"])
            rec = analyze(tmp)
            row["results"]["isolated"] = score(rec, entry, "isolated")
            row["cross_fires"] = other_checks_firing(rec, entry)
        for host in hosts:
            with tempfile.TemporaryDirectory() as tmp:
                dst = os.path.join(tmp, "h")
                shutil.copytree(host, dst, symlinks=True, ignore=shutil.ignore_patterns(".git"))
                overlay(vdir, dst, entry["files"])
                row["results"][f"embedded:{os.path.basename(host.rstrip('/'))}"] = score(analyze(dst), entry, "embedded")
        rows.append(row)
    return rows


def summarize(rows):
    table = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for r in rows:
        for mode, outcome in (r.get("results") or {}).items():
            if outcome is not None:
                table[mode][(r["category"], r["kind"])][outcome] += 1
    return {m: {f"{c}|{k}": dict(v) for (c, k), v in sorted(t.items())} for m, t in table.items()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--host", action="append", default=[])
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    rows = run(a.corpus, a.host)
    out = {"rows": rows, "summary": summarize(rows)}
    text = json.dumps(out, indent=2, sort_keys=True)
    if a.out:
        open(a.out, "w").write(text + "\n")
    for mode, t in out["summary"].items():
        print(f"== {mode}")
        for key, counts in t.items():
            print(f"  {key:40} {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
