"""History scan: which merged changes in a period weakened their own
verification? For a technical-diligence evidence read.

  plumbline-scan run REPO --since YYYY-MM-DD --out DIR [--until ...] [--no-pr-mode]
  plumbline-scan report DIR --triage DIR/triage.csv --target "Target A" -o report.html

`run` walks the first-parent history of the checked-out branch in the
period. Each merged change is compared with its first parent by:

  diff rules   the three diff-level rules that met the published precision
               bar (patch_rules: assertions removed on net, skips added,
               continue-on-error added). They read any language's diff.
  PR mode      the before-and-after checks (plumbline_detector.pr), on
               Python and JS/TS tests. Skipped with --no-pr-mode.

It also runs the repository checks (gate topology, evidence channels) on
the checked-out head. It writes:

  scan.json       provenance and counts
  findings.jsonl  one line per finding
  triage.csv      one row per flagged change, for an analyst to mark
                  verdict (weakening / benign / unclear / false-alarm)

`report` turns the scan and the completed triage sheet into a
self-contained HTML report. Only changes marked `weakening` appear as
findings; the others are counted.

Everything runs locally and offline, and nothing leaves the machine. No
author names or emails are read or recorded.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from importlib import resources

from . import SCHEMA_VERSION, __version__
from .patch_rules import scan_file

DIFF_RULES = ("P-ASSERTIONS-NET-REMOVED", "P-SKIP-ADDED", "P-CONTINUE-ON-ERROR")
STATUS = {"A": "added", "M": "modified", "D": "removed", "R": "renamed", "C": "added", "T": "modified"}
VERDICTS = ("weakening", "benign", "unclear", "false-alarm")
PLAIN = {
    "P-ASSERTIONS-NET-REMOVED": "assertions removed on net",
    "P-SKIP-ADDED": "skip / xfail / todo / .only marker added",
    "P-CONTINUE-ON-ERROR": "continue-on-error added to CI",
    "PR-ASSERTIONS-REMOVED": "a test kept running with fewer assertions",
    "PR-TESTS-DISABLED": "a test stopped running",
    "PR-TESTS-REMOVED": "tests removed and not re-added",
    "PR-TOLERANCE-LOOSENED": "a tolerance or threshold loosened",
    "PR-TIMEOUT-RAISED": "a test timeout raised",
    "PR-ASSERTION-SWALLOWED": "assertion failures caught and discarded",
    "PR-MOCK-UNDER-TEST": "the code under test mocked",
    "PR-TESTS-EXCLUDED": "tests excluded by configuration",
    "PR-NEW-TAMPERING": "a tampering construct introduced",
}


def _git(repo, *args, text=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=text, errors="replace" if text else None)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {(r.stderr or '')[:300]}")
    return r.stdout


def _split_patch(patch: str):
    files, cur, body = [], None, []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            if cur is not None:
                files.append((cur, "\n".join(body)))
            parts = line.split(" b/", 1)
            cur, body = (parts[1] if len(parts) == 2 else None), []
        elif cur is not None:
            body.append(line)
    if cur is not None:
        files.append((cur, "\n".join(body)))
    return files


def _materialize(repo, rev, dest):
    os.makedirs(dest)
    data = subprocess.run(["git", "-C", repo, "archive", "--format=tar", rev], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", dest], input=data, check=True, capture_output=True)


def _module_hashes():
    base = resources.files("plumbline_detector")
    return {m: hashlib.sha256(base.joinpath(m).read_bytes()).hexdigest()[:16] for m in ("patch_rules.py", "pr.py", "loosen.py", "scan.py")}


def run(a) -> int:
    repo = os.path.abspath(a.repo)
    os.makedirs(a.out, exist_ok=True)
    head = _git(repo, "rev-parse", "HEAD").strip()
    args = ["log", "--first-parent", "--format=%H %P%x1f%cI", f"--since={a.since}"]
    if a.until:
        args.append(f"--until={a.until}")
    commits = []
    for line in _git(repo, *args).splitlines():
        shas, _, date = line.partition("\x1f")
        parts = shas.split()
        if len(parts) >= 2:
            commits.append((parts[0], parts[1], date))
    if a.max_commits:
        commits = commits[: a.max_commits]
    print(f"{len(commits)} merged changes in the period", file=sys.stderr)

    findings, skipped = [], Counter()
    tmp = tempfile.mkdtemp(prefix="plumbline-scan-")
    pr_mode = not a.no_pr_mode
    if pr_mode:
        from . import pr
    try:
        for n, (sha, parent, date) in enumerate(commits, 1):
            base = {"commit": sha, "parent": parent, "date": date}
            diff = _git(repo, "diff", "-M", parent, sha)
            status = {}
            for line in _git(repo, "diff", "-M", "--name-status", parent, sha).splitlines():
                cols = line.split("\t")
                if len(cols) >= 2:
                    status[cols[-1]] = STATUS.get(cols[0][:1], "modified")
            for fn, body in _split_patch(diff):
                if fn is None:
                    continue
                for rule, detail in scan_file(fn, status.get(fn, "modified"), body):
                    if rule in DIFF_RULES:
                        findings.append({**base, "check": rule, "file": fn, "line": None, "message": f"{PLAIN[rule]} ({detail})"})
            if pr_mode:
                b, h = os.path.join(tmp, "base"), os.path.join(tmp, "head")
                try:
                    _materialize(repo, parent, b)
                    _materialize(repo, sha, h)
                    rec = pr.compare(b, h)
                    for c in rec["checks"]:
                        for f in c["findings"]:
                            findings.append({**base, "check": c["id"], "file": f["file"], "line": f.get("line"), "message": f["message"]})
                except subprocess.CalledProcessError:
                    if shutil.disk_usage(tmp).free < 2 * 1024**3:
                        raise RuntimeError("scan aborted: less than 2 GB free")
                    skipped["tree not extractable"] += 1
                except Exception as e:  # reported, never silently dropped
                    skipped[f"PR mode error: {type(e).__name__}"] += 1
                finally:
                    shutil.rmtree(b, ignore_errors=True)
                    shutil.rmtree(h, ignore_errors=True)
            if n % 25 == 0:
                print(f"  {n}/{len(commits)}", file=sys.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    from .record import analyze

    repo_record = analyze(repo)
    flagged = {}
    for f in findings:
        flagged.setdefault(f["commit"], []).append(f)
    scan = {
        "tool": {"name": "plumbline-detector", "version": __version__, "schema": SCHEMA_VERSION, "modules": _module_hashes()},
        "repository": {"head": head, "since": a.since, "until": a.until, "first_parent_changes": len(commits)},
        "pr_mode": pr_mode,
        "counts": {"findings": len(findings), "flagged_changes": len(flagged), "skipped": dict(skipped)},
        "repository_checks": [{"id": c["id"], "verdict": c["verdict"], "grade": c.get("grade"), "findings": [f["message"] for f in c["findings"]], "unknowns": [u["message"] for u in c.get("unknowns", [])]} for c in repo_record["checks"]],
    }
    with open(os.path.join(a.out, "scan.json"), "w") as fh:
        json.dump(scan, fh, indent=2, sort_keys=True)
    with open(os.path.join(a.out, "findings.jsonl"), "w") as fh:
        for f in findings:
            fh.write(json.dumps(f, sort_keys=True) + "\n")
    with open(os.path.join(a.out, "triage.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item", "commit", "date", "checks", "files", "summary", "verdict", "note"])
        for i, (sha, fs) in enumerate(sorted(flagged.items(), key=lambda x: x[1][0]["date"]), 1):
            w.writerow([f"F{i:03d}", sha[:12], fs[0]["date"][:10], " ".join(sorted({f["check"] for f in fs})),
                        " ".join(sorted({f["file"] for f in fs}))[:300], "; ".join(sorted({f["message"] for f in fs}))[:400], "", ""])
    print(f"{len(findings)} findings on {len(flagged)} of {len(commits)} changes; triage sheet: {os.path.join(a.out, 'triage.csv')}", file=sys.stderr)
    return 0


def _e(s) -> str:
    return html.escape(str(s))


def report(a) -> int:
    scan = json.load(open(os.path.join(a.dir, "scan.json")))
    rows = list(csv.DictReader(open(a.triage, newline="")))
    bad = [r for r in rows if r["verdict"].strip() and r["verdict"].strip() not in VERDICTS]
    todo = [r for r in rows if not r["verdict"].strip()]
    if bad or todo:
        print(f"triage incomplete: {len(todo)} rows without a verdict, {len(bad)} with an unknown verdict (use one of {', '.join(VERDICTS)})", file=sys.stderr)
        return 2
    v = Counter(r["verdict"].strip() for r in rows)
    n = scan["repository"]["first_parent_changes"]
    weak = [r for r in rows if r["verdict"].strip() == "weakening"]
    gates = [c for c in scan["repository_checks"] if c["id"].startswith("GT-")]
    gate_fail = [c for c in gates if c["verdict"] == "FAIL"]
    rate = f"{len(weak)} of {n} ({100 * len(weak) / max(1, n):.2f}%)"
    items = "".join(
        f"<tr><td>{_e(r['item'])}</td><td><code>{_e(r['commit'])}</code><br>{_e(r['date'])}</td><td>{_e(r['summary'])}<br><span class=note>{_e(r['files'])}</span></td><td>{_e(r['note'])}</td></tr>"
        for r in weak
    ) or "<tr><td colspan=4>No merged change in the period weakened verification.</td></tr>"
    gate_rows = "".join(f"<tr><td><code>{_e(c['id'])}</code></td><td>{_e(c['verdict'])}</td><td>{_e('; '.join(c['findings'] or c.get('unknowns', []) or (['could not be determined from the snapshot'] if c['verdict'] == 'UNKNOWN' else []))[:400])}</td></tr>" for c in gates)
    skipped = scan["counts"]["skipped"]
    doc = f"""<!doctype html><html lang=en><head><meta charset=utf-8><title>Evidence Read: {_e(a.target)}</title><style>
@page{{size:Letter;margin:.5in .55in}}body{{font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;color:#1c1f23;font-size:9.6pt;line-height:1.35;margin:0}}
h1{{font-size:16pt;margin:0}}.sub{{color:#555;font-size:9pt;margin-bottom:8px}}h2{{font-size:10.2pt;margin:10px 0 3px;border-bottom:1px solid #d8dde3;text-transform:uppercase;letter-spacing:.4px;color:#2b3a4a}}
table{{width:100%;border-collapse:collapse;font-size:8.9pt}}th,td{{text-align:left;padding:3px 6px;border-bottom:1px solid #eceff2;vertical-align:top}}th{{background:#f3f5f7}}
.kpi{{display:flex;gap:8px;margin:6px 0}}.kpi div{{flex:1;border:1px solid #d8dde3;border-radius:4px;padding:5px 8px}}.kpi b{{display:block;font-size:14pt}}.kpi span,.note{{color:#555;font-size:8.4pt}}
code{{font-family:Menlo,Consolas,monospace;font-size:8.6pt;background:#f3f5f7;padding:0 3px}}.foot{{margin-top:10px;color:#666;font-size:8.2pt;border-top:1px solid #d8dde3;padding-top:4px}}</style></head><body>
<h1>Evidence Read: {_e(a.target)}</h1><div class=sub>Plumbline · merged changes {_e(scan['repository']['since'])} to {_e(scan['repository']['until'] or 'head')} · head <code>{_e(scan['repository']['head'][:12])}</code> · detector {_e(scan['tool']['version'])}, schema {_e(scan['tool']['schema'])}</div>
<h2>Summary</h2><div class=kpi><div><b>{n}</b><span>merged changes examined</span></div><div><b>{len(rows)}</b><span>changes flagged by the checks</span></div><div><b>{len(weak)}</b><span>confirmed weakening ({_e(rate)})</span></div><div><b>{len(gate_fail)}</b><span>gate checks failed</span></div></div>
<p>Every flagged change was reviewed by an analyst. Of {len(rows)} flagged: {v['weakening']} weakened verification with nothing replacing it, {v['benign']} were benign (refactors, environment guards, removed features), {v['unclear']} could not be judged from the change, and {v['false-alarm']} were false alarms.</p>
<h2>Changes that weakened verification</h2><table><tr><th>Item</th><th>Change</th><th>What the change did</th><th>Analyst note</th></tr>{items}</table>
<h2>Gates</h2><table><tr><th>Check</th><th>Result</th><th>Detail</th></tr>{gate_rows}</table>
<h2>Coverage and limits</h2><p>Diff rules read every change in any language. Before-and-after checks cover Python and JS/TS tests{'' if scan['pr_mode'] else ' and were not run for this read'}. Skipped: {_e(skipped) if skipped else 'none'}. Gate results come from the repository snapshot; host settings not visible in it (branch protection, rulesets) are reported separately if access was granted. A finding says what a change did, not why. The checks' measured precision and the rules that failed are published at github.com/plumbline-verify/plumbline-detector.</p>
<div class=foot>Reproducible: scan.json and findings.jsonl reproduce this read byte-for-byte with the same detector version. Module hashes: {_e(scan['tool']['modules'])}.</div></body></html>"""
    with open(a.output, "w") as fh:
        fh.write(doc)
    print(f"report: {a.output}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="plumbline-scan", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="scan a repository's merged changes in a period")
    r.add_argument("repo")
    r.add_argument("--since", required=True, help="start date, e.g. 2025-09-23")
    r.add_argument("--until")
    r.add_argument("--out", required=True)
    r.add_argument("--max-commits", type=int)
    r.add_argument("--no-pr-mode", action="store_true", help="diff rules only (fast)")
    p = sub.add_parser("report", help="build the client report from a completed triage sheet")
    p.add_argument("dir")
    p.add_argument("--triage", required=True)
    p.add_argument("--target", required=True, help='name shown on the report, e.g. "Target A"')
    p.add_argument("-o", "--output", required=True)
    a = ap.parse_args(argv)
    return {"run": run, "report": report}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
