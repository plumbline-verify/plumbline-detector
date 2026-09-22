"""Alternative renderings of a record: SARIF 2.1.0 and Markdown.

Both are pure functions of the JSON record, so they inherit its determinism.
The JSON record remains the measurement of record; these are views.
"""

from __future__ import annotations

import json

from .catalog import CATALOG

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
MD_FINDINGS_PER_CHECK = 25


def _sarif_location(loc):
    phys = {"artifactLocation": {"uri": loc["file"]}}
    if loc.get("line"):
        phys["region"] = {"startLine": loc["line"]}
    return {"physicalLocation": phys}


def to_sarif(record: dict) -> str:
    """Findings become results at level 'error'; UNKNOWN locations become
    results at level 'note' so that abstentions are visible, not silent."""
    rules = []
    results = []
    for c in record["checks"]:
        title, prevents = CATALOG[c["id"]]
        rules.append(
            {
                "id": c["id"],
                "name": c["id"].replace("-", ""),
                "shortDescription": {"text": title},
                "fullDescription": {"text": prevents},
                "properties": {"verdict": c["verdict"], "measured_precision": c["measured_precision"]},
            }
        )
        for f in c["findings"]:
            results.append(
                {
                    "ruleId": c["id"],
                    "level": "error",
                    "message": {"text": f["message"]},
                    "locations": [_sarif_location(f)],
                    "partialFingerprints": {"plumblineFinding/v1": f["id"]},
                }
            )
        for u in c["unknowns"]:
            results.append(
                {
                    "ruleId": c["id"],
                    "level": "note",
                    "message": {"text": "Not evaluated: " + u["message"]},
                    "locations": [_sarif_location(u)],
                }
            )
    sarif = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": record["tool"]["name"],
                        "version": record["tool"]["version"],
                        "semanticVersion": record["tool"]["version"],
                        "rules": rules,
                        "properties": {
                            "schema_version": record["schema_version"],
                            "ruleset_fingerprint": record["provenance"]["ruleset_fingerprint"],
                            "config_hash": record["provenance"]["config_hash"],
                        },
                    }
                },
                "results": results,
                "properties": {"content_id": record["repo"]["content_id"], "commit_sha": record["provenance"]["commit_sha"]},
            }
        ],
    }
    return json.dumps(sarif, indent=2, sort_keys=True) + "\n"


def _precision_cell(m) -> str:
    if not m:
        return "not measured"
    lo, hi = m["ci95"]
    star = "" if m["same_ruleset"] else "*"
    return f"{m['precision']:.0%}{star} ({lo:.0%}–{hi:.0%}, n={m['labeled']})"


def to_markdown(record: dict) -> str:
    p, inv, s = record["provenance"], record["inventory"], record["summary"]
    out = [
        "# Verification-evidence report",
        "",
        f"Snapshot `{record['repo']['content_id']}`"
        + (f", commit `{p['commit_sha']}`" if p["commit_sha"] else ", commit not determinable")
        + ".",
        "",
        f"**{s['FAIL']} FAIL, {s['UNKNOWN']} UNKNOWN, {s['PASS']} PASS** across {len(record['checks'])} checks.",
        "",
        "A PASS means the check had input, examined all of it, and matched none of its patterns. "
        "It is not a certificate that the evidence is real. UNKNOWN means the check could not decide "
        "(nothing in scope, or something unreadable or unrecognized); it is never counted as a pass.",
        "",
        "| Check | Verdict | Findings | Not evaluated | Measured precision | What it guards against |",
        "|---|---|---|---|---|---|",
    ]
    stale = False
    for c in record["checks"]:
        title, _ = CATALOG[c["id"]]
        basis = f" ({c['basis']})" if c.get("basis") not in (None, "declared") else ""
        out.append(f"| `{c['id']}` | {c['verdict']}{basis} | {len(c['findings'])} | {len(c['unknowns'])} | {_precision_cell(c['measured_precision'])} | {title} |")
        stale = stale or bool(c["measured_precision"] and not c["measured_precision"]["same_ruleset"])
    out += [
        "",
        "Measured precision is the share of this check's findings that independent reviewers confirmed "
        "on repositories the detector had not been tuned on (docs/PRECISION_STUDY.md): "
        "precision, 95% interval, and sample size."
        + (" Values marked * were measured on an earlier version of the check code." if stale else ""),
        "",
        f"Inventory: primary language {inv['primary_language'] or 'none'}, "
        f"{inv['loc_nonblank_total']:,} non-blank lines, {inv['test_file_count']} Python test files, "
        f"{inv['github_workflow_files']} GitHub Actions workflows, {len(inv['unread_files'])} unread files.",
        "",
    ]
    for c in record["checks"]:
        if not c["findings"] and not c["unknowns"]:
            continue
        title, prevents = CATALOG[c["id"]]
        out += [f"## {c['id']}: {title}", "", f"{prevents} Verdict: **{c['verdict']}**. {c['reason']}.", ""]
        for f in c["findings"][:MD_FINDINGS_PER_CHECK]:
            where = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
            out.append(f"- `{where}`: {f['message']}")
        if len(c["findings"]) > MD_FINDINGS_PER_CHECK:
            out.append(f"- and {len(c['findings']) - MD_FINDINGS_PER_CHECK} more findings (see the JSON record)")
        if c["unknowns"]:
            out.append(f"- {len(c['unknowns'])} location(s) not evaluated (see the JSON record)")
        out.append("")
    out += [
        "---",
        f"plumbline-detector {record['tool']['version']}, schema {record['schema_version']}, "
        f"ruleset `{p['ruleset_fingerprint']}`, config `{p['config_hash']}`, "
        f"Python {p['environment']['python']}.",
        "",
    ]
    return "\n".join(out)
