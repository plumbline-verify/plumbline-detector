"""Replay PR mode over the recent first-parent history of local clones
(docs/PR_MODE_STUDY.md). Each commit is compared with its first parent.

Usage: python tools/pr_replay.py --repos DIR --out changes.jsonl [--per-repo 30] [--jobs 6]
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor

from plumbline_detector import pr


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def materialize(repo, rev, dest):
    os.makedirs(dest)
    data = subprocess.run(["git", "-C", repo, "archive", "--format=tar", rev], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", dest], input=data, check=True)


def replay(args):
    repo, per_repo = args
    name = os.path.basename(repo.rstrip("/"))
    commits = git(repo, "rev-list", "--first-parent", f"--max-count={per_repo}", "HEAD").split()
    rows, tmp = [], tempfile.mkdtemp(prefix=f"replay-{name}-")
    try:
        for c in commits:
            parents = git(repo, "rev-list", "--parents", "-n", "1", c).split()[1:]
            if not parents:
                rows.append({"repo": name, "commit": c, "skipped": "no parent"})
                continue
            p = parents[0]
            try:
                git(repo, "cat-file", "-e", p + "^{commit}")
            except subprocess.CalledProcessError:
                rows.append({"repo": name, "commit": c, "skipped": "parent not fetched"})
                continue
            b, h = os.path.join(tmp, p), os.path.join(tmp, c)
            try:
                for rev, d in ((p, b), (c, h)):
                    if not os.path.isdir(d):
                        materialize(repo, rev, d)
            except subprocess.CalledProcessError:
                # a full disk is a harness failure, not a property of the
                # repository: stop rather than record it as a skip
                if shutil.disk_usage(tmp).free < 2 * 1024**3:
                    raise RuntimeError("replay aborted: less than 2 GB free")
                # a tree that cannot be extracted (paths the filesystem
                # rejects) is reported, never dropped
                rows.append({"repo": name, "commit": c, "skipped": "tree not extractable"})
                shutil.rmtree(b, ignore_errors=True)
                shutil.rmtree(h, ignore_errors=True)
                continue
            try:
                rec = pr.compare(b, h)
            except Exception as e:  # reported, never silently dropped
                rows.append({"repo": name, "commit": c, "parent": p, "error": repr(e)[:300]})
                continue
            findings = [dict(f, check=ch["id"]) for ch in rec["checks"] for f in ch["findings"]]
            rows.append({"repo": name, "commit": c, "parent": p, "files_changed": rec["provenance"]["files_changed"], "findings": findings})
            shutil.rmtree(b, ignore_errors=True)  # the parent is not needed again (history is walked newest first)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-repo", type=int, default=30)
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    repos = sorted(os.path.join(a.repos, d) for d in os.listdir(a.repos) if os.path.isdir(os.path.join(a.repos, d, ".git")))
    with ProcessPoolExecutor(a.jobs) as ex, open(a.out, "w") as out:
        for rows in ex.map(replay, [(r, a.per_repo) for r in repos]):
            for row in rows:
                out.write(json.dumps(row, sort_keys=True) + "\n")
            out.flush()
    rows = [json.loads(l) for l in open(a.out)]
    done = [r for r in rows if "findings" in r]
    alarms = [r for r in done if r["findings"]]
    print(f"changes {len(done)}, skipped {sum(1 for r in rows if 'skipped' in r)}, errors {sum(1 for r in rows if 'error' in r)}, "
          f"with findings {len(alarms)} ({len(alarms) / max(1, len(done)):.1%}), findings {sum(len(r['findings']) for r in done)}")


if __name__ == "__main__":
    main()
