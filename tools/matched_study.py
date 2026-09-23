"""Matched study (docs/MATCHED_STUDY.md): agent and human changes in the same
repositories, on the agent PR study's qualifying rules.

Repository identity is used internally only. Outputs carry a SHA-256 of the
repository URL, never the URL, name, commit messages or author identities.

  python tools/matched_study.py sample  --prs PRS.jsonl.gz --out DIR
  python tools/matched_study.py run     --out DIR [--jobs 6]
  python tools/matched_study.py analyze --out DIR
"""

import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
from patch_scan import scan_file  # noqa: E402

AIDEV = "https://huggingface.co/datasets/hao-li/AIDev-7.6M/resolve/37bbe1533e26cc1e1374917dba1186d1c8a4dc81/pull_request.parquet"
QUAL = {"P-ASSERTIONS-NET-REMOVED", "P-CONTINUE-ON-ERROR", "P-SKIP-ADDED"}
SAMPLE_SEED = 20260930
N_REPOS = 300
MIN_AGENT_PRS = 5
WINDOW_PAD = dt.timedelta(days=30)
CLONE_TIMEOUT = 600
MAX_BYTES = 2 * 1024**3
BOT_RE = re.compile(r"dependabot|renovate|github-actions|pre-commit-ci|allcontributors|copilot|devin|codex|cursor|jules|claude|\[bot\]", re.I)
STATUS = {"A": "added", "M": "modified", "D": "removed", "R": "renamed", "C": "added", "T": "modified"}


def rhash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def sample(a):
    import fsspec
    import pyarrow.parquet as pq

    with_patches = set()
    with gzip.open(a.prs, "rt") as fh:
        for line in fh:
            r = json.loads(line)
            if r["has_patches"] and r["merged"]:
                with_patches.add(r["pr_id"])
    t = pq.ParquetFile(fsspec.filesystem("https").open(AIDEV, block_size=2**22)).read(columns=["id", "number", "repo_url", "merged_at"]).to_pydict()
    by_repo = defaultdict(list)
    for pid, num, url, merged in zip(t["id"], t["number"], t["repo_url"], t["merged_at"]):
        if pid in with_patches and merged:
            by_repo[url].append((num, merged))
    frame = sorted(u for u, prs in by_repo.items() if len(prs) >= MIN_AGENT_PRS)
    chosen = random.Random(SAMPLE_SEED).sample(frame, min(N_REPOS, len(frame)))
    os.makedirs(a.out, exist_ok=True)
    # repository URLs stay in the private work directory only
    with open(os.path.join(a.out, "sample_private.jsonl"), "w") as out:
        for url in chosen:
            prs = by_repo[url]
            out.write(json.dumps({"repo_url": url, "agent_numbers": sorted({n for n, _ in prs}), "first": min(m for _, m in prs), "last": max(m for _, m in prs)}) + "\n")
    print(f"frame {len(frame)} repositories; sampled {len(chosen)}")


def _git(repo, *args, **kw):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, **kw)


def _clone_url(api_url: str) -> str:
    # AIDev stores api.github.com/repos/OWNER/NAME
    m = re.search(r"repos/([^/]+/[^/]+)$", api_url)
    return f"https://github.com/{m.group(1)}" if m else api_url


def _split_patch(patch: str):
    """unified diff of a commit -> [(filename, body)]"""
    files, cur, body = [], None, []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            if cur is not None:
                files.append((cur, "\n".join(body)))
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            cur, body = (m.group(2) if m else None), []
        elif cur is not None:
            body.append(line)
    if cur is not None:
        files.append((cur, "\n".join(body)))
    return files


def _lang(paths):
    py = sum(p.endswith(".py") for p in paths)
    js = sum(p.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")) for p in paths)
    if py == js == 0:
        return "other"
    return "Python" if py >= js else "JS/TS"


def _tree_bytes(root):
    # lstat: a broken symlink in a checkout is not an error (harness correction 1)
    return sum(os.lstat(os.path.join(dp, f)).st_size for dp, _, fs in os.walk(root) for f in fs)


def _walk(item, keep=None):
    """Clone one repository and classify every change in its window.
    Returns the result record; with `keep` (a set of indices counted from the
    oldest change, which later pushes cannot shift), also returns the
    flagged file patches of those changes."""
    url = item["repo_url"]
    h = rhash(url)
    first = dt.datetime.fromisoformat(item["first"].replace("Z", "+00:00")) - WINDOW_PAD
    last = dt.datetime.fromisoformat(item["last"].replace("Z", "+00:00")) + WINDOW_PAD
    tmp = tempfile.mkdtemp(prefix="matched-")
    repo = os.path.join(tmp, "r")
    kept = {}
    try:
        try:
            r = subprocess.run(["git", "clone", "-q", "--single-branch", f"--shallow-since={(first - dt.timedelta(days=1)).date()}", _clone_url(url), repo],
                               capture_output=True, timeout=CLONE_TIMEOUT)
        except subprocess.TimeoutExpired:
            return {"repo": h, "skipped": "clone timeout"}, kept
        if r.returncode != 0:
            return {"repo": h, "skipped": "clone failed"}, kept
        size = _tree_bytes(repo)
        if size > MAX_BYTES:
            return {"repo": h, "skipped": "over 2 GB"}, kept
        log = _git(repo, "log", "--first-parent", f"--since={first.isoformat()}", f"--until={last.isoformat()}",
                   "--format=%H%x1f%P%x1f%an%x1f%ae%x1f%B%x1e", text=True, errors="replace").stdout
        numbers = set(item["agent_numbers"])
        commits = []
        for rec in log.split("\x1e"):
            rec = rec.strip("\n")
            if not rec:
                continue
            parts = rec.split("\x1f")
            if len(parts) < 5:
                continue
            sha, parents, an, ae, msg = parts[0], parts[1].split(), parts[2], parts[3], parts[4]
            if parents:
                commits.append((sha, parents, an, ae, msg))
        changes, bots = [], 0
        all_paths = []
        n_changes = sum(1 for c in commits if not (not ({int(n) for n in re.findall(r"#(\d+)", c[4])} & numbers) and (BOT_RE.search(c[2]) or BOT_RE.search(c[3]))))
        for sha, parents, an, ae, msg in commits:
            refs = {int(n) for n in re.findall(r"#(\d+)", msg)}
            if refs & numbers:
                group = "agent"
            elif BOT_RE.search(an) or BOT_RE.search(ae):
                bots += 1
                continue
            else:
                group = "human"
            from_oldest = n_changes - 1 - len(changes)
            diff = _git(repo, "diff", "-M", parents[0], sha, text=True, errors="replace").stdout
            ns = _git(repo, "diff", "-M", "--name-status", parents[0], sha, text=True, errors="replace").stdout
            status = {}
            for line in ns.splitlines():
                cols = line.split("\t")
                if len(cols) >= 2:
                    status[cols[-1]] = STATUS.get(cols[0][:1], "modified")
            lines = sum(1 for l in diff.splitlines() if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---")))
            rules = set()
            paths = []
            flagged_files = []
            for fn, body in _split_patch(diff):
                if fn is None:
                    continue
                paths.append(fn)
                hit = sorted({rule for rule, _ in scan_file(fn, status.get(fn, "modified"), body) if rule in QUAL})
                if hit:
                    rules.update(hit)
                    flagged_files.append({"filename": fn, "status": status.get(fn, "modified"), "rules": hit, "patch": body})
            all_paths += paths
            changes.append({"group": group, "lines": lines, "rules": sorted(rules)})
            if keep is not None and from_oldest in keep:
                kept[from_oldest] = {"group": group, "lines": lines, "rules": sorted(rules), "files": flagged_files}
        return {"repo": h, "language": _lang(all_paths), "bots_excluded": bots, "changes": changes}, kept
    except Exception as e:  # reported, never silently dropped
        return {"repo": h, "skipped": f"error: {type(e).__name__}"}, kept
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def process(item):
    return _walk(item)[0]


def run(a):
    items = [json.loads(l) for l in open(os.path.join(a.out, "sample_private.jsonl"))]
    mode = "w"
    if a.retry_errors:
        # re-run only repositories skipped by a harness error; every other result is kept as is
        path = os.path.join(a.out, "repos.jsonl")
        prior = [json.loads(l) for l in open(path)]
        errored = {r["repo"] for r in prior if r.get("skipped", "").startswith("error:")}
        with open(path, "w") as out:
            for r in prior:
                if r["repo"] not in errored:
                    out.write(json.dumps(r, sort_keys=True) + "\n")
        items = [it for it in items if rhash(it["repo_url"]) in errored]
        mode = "a"
    with ProcessPoolExecutor(a.jobs) as ex, open(os.path.join(a.out, "repos.jsonl"), mode) as out:
        for i, res in enumerate(ex.map(process, items), 1):
            out.write(json.dumps(res, sort_keys=True) + "\n")
            out.flush()
            if i % 10 == 0:
                print(f"{i}/{len(items)} repositories", flush=True)
    print("done")


def mh_rr(strata):
    """Mantel-Haenszel risk ratio with Greenland-Robins 95% CI.
    strata: [(a, n1, c, n0)] exposed events/total, unexposed events/total."""
    num = den = 0.0
    var_num = 0.0
    for a_, n1, c, n0 in strata:
        n = n1 + n0
        num += a_ * n0 / n
        den += c * n1 / n
        var_num += (n1 * n0 * (a_ + c) - a_ * c * n) / (n * n)
    if num == 0 or den == 0:
        return float("nan"), float("nan"), float("nan")
    rr = num / den
    se = math.sqrt(var_num / (num * den))
    return rr, rr * math.exp(-1.96 * se), rr * math.exp(1.96 * se)


def analyze(a):
    repos = [json.loads(l) for l in open(os.path.join(a.out, "repos.jsonl"))]
    skipped = [r for r in repos if "skipped" in r]
    done = [r for r in repos if "changes" in r]

    def strata(filter_change=lambda c: True, filter_repo=lambda r: True):
        out = []
        for r in done:
            if not filter_repo(r):
                continue
            ag = [c for c in r["changes"] if c["group"] == "agent" and filter_change(c)]
            hu = [c for c in r["changes"] if c["group"] == "human" and filter_change(c)]
            if len(ag) >= 1 and len(hu) >= 5:
                out.append((sum(bool(c["rules"]) for c in ag), len(ag), sum(bool(c["rules"]) for c in hu), len(hu)))
        return out

    def line(label, st):
        rr, lo, hi = mh_rr(st)
        a_ = sum(s[0] for s in st); n1 = sum(s[1] for s in st); c = sum(s[2] for s in st); n0 = sum(s[3] for s in st)
        return f"| {label} | {len(st)} | {a_}/{n1} ({a_ / max(1, n1):.2%}) | {c}/{n0} ({c / max(1, n0):.2%}) | {rr:.2f} ({lo:.2f}–{hi:.2f}) |"

    print(f"repositories: {len(repos)} sampled, {len(done)} analyzed, {len(skipped)} skipped "
          f"({dict((k, sum(1 for r in skipped if r['skipped'] == k)) for k in sorted({r['skipped'] for r in skipped}))})")
    print(f"bot changes excluded: {sum(r['bots_excluded'] for r in done)}")
    print("\n| Stratum | Repositories | Agent changes with signal | Human changes with signal | MH risk ratio (95% CI) |")
    print("|---|---|---|---|---|")
    print(line("**All (primary)**", strata()))
    for lang in ("Python", "JS/TS", "other"):
        print(line(f"Language: {lang}", strata(filter_repo=lambda r, L=lang: r["language"] == L)))
    for lab, lo_, hi_ in (("Size ≤50 lines", 0, 50), ("Size 51–500", 51, 500), ("Size >500", 501, 10**12)):
        print(line(lab, strata(filter_change=lambda c, lo_=lo_, hi_=hi_: lo_ <= c["lines"] <= hi_)))
    st = strata()
    higher = sum(1 for a_, n1, c, n0 in st if a_ / n1 > c / n0)
    print(f"\nrepositories where the agent rate exceeds the human rate: {higher} of {len(st)}")


# --- precision relabel (MATCHED_STUDY.md, "Precision check") -----------------
RELABEL_SEED = 20260931
AUDIT_SEED = 20260932
RELABEL_N = 100
MAX_PATCH_LINES = 300


def _primary(done):
    for r in done:
        ag = [c for c in r["changes"] if c["group"] == "agent"]
        hu = [c for c in r["changes"] if c["group"] == "human"]
        if len(ag) >= 1 and len(hu) >= 5:
            yield r


def relabel_sample(a):
    """Draw the flagged changes to relabel from the primary analysis set.
    A change is identified by its repository and its index counted from the
    oldest change in the window."""
    repos = [json.loads(l) for l in open(os.path.join(a.out, "repos.jsonl"))]
    done = [r for r in repos if "changes" in r]
    pools = {"agent": [], "human": []}
    for r in _primary(done):
        n = len(r["changes"])
        for i, c in enumerate(r["changes"]):
            if c["rules"]:
                pools[c["group"]].append({"repo": r["repo"], "from_oldest": n - 1 - i, "group": c["group"], "lines": c["lines"], "rules": c["rules"]})
    rng = random.Random(RELABEL_SEED)
    chosen = []
    for g in ("agent", "human"):
        pool = sorted(pools[g], key=lambda x: (x["repo"], x["from_oldest"]))
        chosen += rng.sample(pool, min(RELABEL_N, len(pool)))
    with open(os.path.join(a.out, "relabel_sample.jsonl"), "w") as out:
        for c in chosen:
            out.write(json.dumps(c, sort_keys=True) + "\n")
    print(f"pools: agent {len(pools['agent'])}, human {len(pools['human'])}; sampled {len(chosen)}")


def _relabel_one(args):
    item, wanted = args
    rec, kept = _walk(item, keep={w["from_oldest"] for w in wanted})
    out = []
    for w in wanted:
        k = kept.get(w["from_oldest"])
        ok = k is not None and k["group"] == w["group"] and k["rules"] == w["rules"] and k["lines"] == w["lines"]
        out.append({**w, "reproduced": ok, "files": k["files"] if ok else None, "skipped": rec.get("skipped")})
    return out


def relabel_extract(a):
    """Re-clone the sampled repositories, recover each sampled change's
    flagged file patches, and write blind labeling packets (no group, no
    repository, shuffled). Everything stays in the private work directory."""
    items = {rhash(it["repo_url"]): it for it in (json.loads(l) for l in open(os.path.join(a.out, "sample_private.jsonl")))}
    sample = [json.loads(l) for l in open(os.path.join(a.out, "relabel_sample.jsonl"))]
    by_repo = defaultdict(list)
    for w in sample:
        by_repo[w["repo"]].append(w)
    results = []
    with ProcessPoolExecutor(a.jobs) as ex:
        for res in ex.map(_relabel_one, [(items[h], ws) for h, ws in sorted(by_repo.items())]):
            results += res
    rng = random.Random(RELABEL_SEED + 1)
    rng.shuffle(results)
    key, packets = [], []
    for n, r in enumerate(results, 1):
        item_id = f"M{n:03d}"
        key.append({"item": item_id, "group": r["group"], "repo": r["repo"], "from_oldest": r["from_oldest"], "rules": r["rules"], "reproduced": r["reproduced"], "skipped": r["skipped"]})
        if not r["reproduced"]:
            continue
        files = []
        for f in r["files"]:
            lines = f["patch"].splitlines()
            files.append({**f, "patch": "\n".join(lines[:MAX_PATCH_LINES]) + (f"\n[... {len(lines) - MAX_PATCH_LINES} more lines]" if len(lines) > MAX_PATCH_LINES else "")})
        packets.append({"item": item_id, "rules": r["rules"], "files": files})
    with open(os.path.join(a.out, "relabel_key_private.jsonl"), "w") as out:
        for k in key:
            out.write(json.dumps(k, sort_keys=True) + "\n")
    with open(os.path.join(a.out, "relabel_packets.jsonl"), "w") as out:
        for p in packets:
            out.write(json.dumps(p, sort_keys=True) + "\n")
    audit = sorted(random.Random(AUDIT_SEED).sample([p["item"] for p in packets], max(1, round(len(packets) * 0.2))))
    with open(os.path.join(a.out, "relabel_audit_items.json"), "w") as out:
        json.dump(audit, out)
    print(f"{len(results)} sampled, {len(packets)} reproduced; audit {len(audit)} items")


def _wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def relabel_score(a):
    key = {k["item"]: k for k in (json.loads(l) for l in open(os.path.join(a.out, "relabel_key_private.jsonl")))}
    labels = {}
    for path in a.labels:
        for l in open(path):
            if l.strip():
                r = json.loads(l)
                labels[r["item"]] = r
    print(f"sampled {len(key)}; not reproduced {sum(1 for k in key.values() if not k['reproduced'])}; labeled {len(labels)}")
    prec = {}
    print("\n| Group | Labeled | Precision (95% CI) | Weakening / benign / unclear, of TP |")
    print("|---|---|---|---|")
    for g in ("agent", "human"):
        items = [labels[i] for i, k in key.items() if k["group"] == g and i in labels]
        tp = [x for x in items if x["label"] == "TP"]
        lo, hi = _wilson(len(tp), len(items))
        prec[g] = len(tp) / len(items) if items else float("nan")
        wk = sum(1 for x in tp if x.get("weakening") is True)
        bn = sum(1 for x in tp if x.get("weakening") is False)
        print(f"| {g} | {len(items)} | {len(tp)}/{len(items)} ({prec[g]:.0%}; {lo:.0%}–{hi:.0%}) | {wk} / {bn} / {len(tp) - wk - bn} |")
    if a.audit:
        audit = [json.loads(l) for l in open(a.audit) if l.strip()]
        agree = sum(1 for x in audit if x["item"] in labels and labels[x["item"]]["label"] == x["label"])
        print(f"\nauthor audit: {agree} of {len(audit)} labels agree")
    diff = abs(prec["agent"] - prec["human"])
    print(f"\nprecision difference: {diff:.1%} ({'over' if diff > 0.10 else 'within'} the 10-point threshold)")
    if diff > 0.10:
        repos = [json.loads(l) for l in open(os.path.join(a.out, "repos.jsonl"))]
        st = []
        for r in _primary([r for r in repos if "changes" in r]):
            ag = [c for c in r["changes"] if c["group"] == "agent"]
            hu = [c for c in r["changes"] if c["group"] == "human"]
            st.append((sum(bool(c["rules"]) for c in ag) * prec["agent"], len(ag), sum(bool(c["rules"]) for c in hu) * prec["human"], len(hu)))
        rr, lo, hi = mh_rr(st)
        print(f"precision-adjusted MH risk ratio: {rr:.2f} ({lo:.2f}–{hi:.2f}); interval from the unadjusted variance on scaled counts")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample"); s.add_argument("--prs", required=True); s.add_argument("--out", required=True)
    r = sub.add_parser("run"); r.add_argument("--out", required=True); r.add_argument("--jobs", type=int, default=6)
    r.add_argument("--retry-errors", action="store_true")
    z = sub.add_parser("analyze"); z.add_argument("--out", required=True)
    q = sub.add_parser("relabel-sample"); q.add_argument("--out", required=True)
    x = sub.add_parser("relabel-extract"); x.add_argument("--out", required=True); x.add_argument("--jobs", type=int, default=6)
    y = sub.add_parser("relabel-score"); y.add_argument("--out", required=True); y.add_argument("--labels", nargs="+", required=True); y.add_argument("--audit")
    a = ap.parse_args()
    {"sample": sample, "run": run, "analyze": analyze, "relabel-sample": relabel_sample, "relabel-extract": relabel_extract, "relabel-score": relabel_score}[a.cmd](a)


if __name__ == "__main__":
    main()
