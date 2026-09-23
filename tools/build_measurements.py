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

# Round metadata, as pre-registered in docs/PRECISION_STUDY.md.
ROUNDS = {
    1: {"schema": "1.1.0", "detector_commit": "ebeaaf0", "ruleset_fingerprint": "sha256:3dc55876e94295047850de8c6df2aacdc8bea90303d712c25c60f6a30b75792b", "date": "2026-09-22"},
    2: {"schema": "1.2.0", "detector_commit": "dfb2c43", "ruleset_fingerprint": "sha256:2db2c62cd6808bab42af532fe03d7a080afb1f0159614b65d0b1e43673dd0410", "date": "2026-09-22"},
    3: {"schema": "1.3.0", "detector_commit": "ea36d78", "ruleset_fingerprint": "sha256:47147ca9f073da2cc48d5265613488eca4294726d7de9ff5ad9471b5f79d6e64", "date": "2026-09-23"},
}


def main():
    rounds = []
    for n, meta in sorted(ROUNDS.items()):
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
