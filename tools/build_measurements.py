"""Build src/plumbline_detector/measurements.json from the committed
precision-study label files (docs/precision/round*/labeled_findings.jsonl).

The detector reports, next to each verdict, the most recent held-out
measurement of that check. This script is the only way that file is made, so
every number in it traces to a labeled finding.
"""

import json
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent



def rounds_meta():
    """Round metadata (schema, detector commit, ruleset fingerprint, date),
    as pre-registered in docs/PRECISION_STUDY.md, from each round's
    docs/precision/roundN/round.json."""
    out = {}
    for f in sorted(ROOT.glob("docs/precision/round*/round.json")):
        meta = json.loads(f.read_text())
        out[meta.pop("round")] = meta
    return out


def main():
    rounds = []
    for n, meta in sorted(rounds_meta().items()):
        rows = [json.loads(l) for l in open(ROOT / f"docs/precision/round{n}/labeled_findings.jsonl")]
        repos = json.load(open(ROOT / f"docs/precision/round{n}/repositories.json"))
        checks = defaultdict(lambda: {"labeled": 0, "tp": 0, "fp_detector": 0, "fp_scope": 0, "pool": 0})
        for r in rows:
            c = checks[r["check"]]
            c["labeled"] += 1
            c["pool"] = r["pool_size"]
            c[{"TP": "tp", "FP-detector": "fp_detector", "FP-scope": "fp_scope"}[r["label"]]] += 1
        rounds.append({"round": n, **meta, "repositories": len(repos), "checks": dict(sorted(checks.items()))})
    out = ROOT / "src/plumbline_detector/measurements.json"
    out.write_text(json.dumps({"source": "docs/PRECISION_STUDY.md", "rounds": rounds}, indent=2, sort_keys=True) + "\n")
    print(out)


if __name__ == "__main__":
    main()
