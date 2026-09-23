"""Phase B: run the detector over Auditing Sabotage Bench workspaces and
write asb_results.json (see docs/PHASE_B.md).

Usage: python tools/phaseb_asb.py PATH_TO_ASB_CHECKOUT
"""
import glob, json, os, sys, yaml
from plumbline_detector.record import analyze
ASB = sys.argv[1] if len(sys.argv) > 1 else "asb"
rows = []
for f in sorted(glob.glob(f"{ASB}/codebases/_rubrics/*.yaml")):
    if f.endswith(("_finished.yaml", "bugs.yaml")):
        continue
    d = yaml.safe_load(open(f))
    for key in d:
        if not isinstance(d[key], list):
            continue
        for e in d[key]:
            if not isinstance(e, dict) or "workspace" not in e:
                continue
            ws = os.path.join(ASB, e["workspace"])
            if "persuasion" in e["id"] or not os.path.isdir(ws):
                continue  # persuasion variants are overlays of a sabotaged base
            label = 1 if key.startswith("sabot") else 0 if key.startswith("honest") else None
            rows.append((e["id"], key, label, ws))
out = []
for id_, key, label, ws in rows:
    rec = analyze(ws)
    fails = {c["id"]: len(c["findings"]) for c in rec["checks"] if c["findings"]}
    verdicts = {c["verdict"] for c in rec["checks"]}
    out.append({"id": id_, "group": key, "sabotaged": label, "findings": sum(fails.values()), "by_check": fails,
                "unknown_checks": sum(1 for c in rec["checks"] if c["verdict"] == "UNKNOWN")})
    print(json.dumps(out[-1]))
json.dump(out, open("asb_results.json", "w"), indent=1)
sab = [x["findings"] for x in out if x["sabotaged"] == 1]
hon = [x["findings"] for x in out if x["sabotaged"] == 0]
auc = sum((a > b) + 0.5 * (a == b) for a in sab for b in hon) / (len(sab) * len(hon))
print(f"sabotaged {len(sab)}, honest {len(hon)}, AUROC {auc:.2f}")
