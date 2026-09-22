"""Command line entry point: plumbline-detect PATH."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

from . import SCHEMA_VERSION, __version__
from .record import analyze, dumps
from .render import to_markdown, to_sarif


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="plumbline-detect",
        description="Static, offline check of whether a repository snapshot's verification evidence is real.",
    )
    ap.add_argument("path", help="directory containing the repository snapshot")
    ap.add_argument("-o", "--out", help="write the JSON record here instead of stdout")
    ap.add_argument("--required-check", action="append", default=[], metavar="NAME",
                    help="a required status check context known from outside the snapshot (repeatable)")
    ap.add_argument("--gate-file", action="append", default=[], metavar="FILE",
                    help="a GitHub ruleset JSON export supplied with the snapshot (repeatable)")
    ap.add_argument("--label", help="free-text repository label; only its SHA-256 is recorded")
    ap.add_argument("--commit-sha", help="commit SHA, when known but absent from the snapshot")
    ap.add_argument("--timestamp", help="ISO-8601 timestamp to record (keeps output deterministic)")
    ap.add_argument("--now", action="store_true", help="record the current UTC time (output is then not reproducible)")
    ap.add_argument("--format", choices=["json", "sarif", "markdown"], default="json",
                    help="json: the versioned record (default); sarif: SARIF 2.1.0 for code-scanning tools; "
                         "markdown: a human-readable report")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__} (schema {SCHEMA_VERSION})")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.path):
        print(f"error: not a directory: {args.path}", file=sys.stderr)
        return 2
    ts, ts_source = None, "not_supplied"
    if args.now:
        ts, ts_source = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "wall_clock"
    elif args.timestamp:
        ts, ts_source = args.timestamp, "operator"
    elif os.environ.get("SOURCE_DATE_EPOCH", "").isdigit():
        ts = dt.datetime.fromtimestamp(int(os.environ["SOURCE_DATE_EPOCH"]), dt.timezone.utc).isoformat()
        ts_source = "SOURCE_DATE_EPOCH"
    gate_files = []
    for f in args.gate_file:
        with open(f, "rb") as fh:
            gate_files.append((os.path.basename(f), fh.read()))
    record = analyze(
        args.path,
        required_checks=args.required_check,
        gate_files=gate_files,
        label=args.label,
        commit_sha=args.commit_sha,
        timestamp=ts,
        timestamp_source=ts_source,
    )
    out = {"json": dumps, "sarif": to_sarif, "markdown": to_markdown}[args.format](record)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(out)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def diff_main(argv=None) -> int:
    """plumbline-diff OLD.json NEW.json: findings added and resolved between
    two records of the same repository, matched by finding ID. Exit 1 if any
    finding is new, so it can gate a pull request on regressions only."""
    ap = argparse.ArgumentParser(prog="plumbline-diff", description=diff_main.__doc__)
    ap.add_argument("old")
    ap.add_argument("new")
    args = ap.parse_args(argv)
    import json

    recs = []
    for path in (args.old, args.new):
        with open(path, encoding="utf-8") as fh:
            recs.append(json.load(fh))
    old, new = recs
    if old["schema_version"] != new["schema_version"]:
        print(f"note: schema versions differ ({old['schema_version']} -> {new['schema_version']}); "
              "differences may come from the detector, not the repository", file=sys.stderr)

    def index(rec):
        return {(c["id"], f["id"]): f for c in rec["checks"] for f in c["findings"]}

    a, b = index(old), index(new)
    added = sorted(set(b) - set(a))
    resolved = sorted(set(a) - set(b))
    for key in added:
        f = b[key]
        print(f"+ {key[0]} {f['file']}:{f['line']}: {f['message']}")
    for key in resolved:
        f = a[key]
        print(f"- {key[0]} {f['file']}:{f['line']}: {f['message']}")
    verdicts_old = {c["id"]: c["verdict"] for c in old["checks"]}
    for c in new["checks"]:
        if verdicts_old.get(c["id"]) != c["verdict"]:
            print(f"~ {c['id']}: {verdicts_old.get(c['id'])} -> {c['verdict']}")
    print(f"{len(added)} new, {len(resolved)} resolved")
    return 1 if added else 0
