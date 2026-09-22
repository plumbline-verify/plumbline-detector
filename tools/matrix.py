"""Print a verdict matrix for fixture directories (development aid)."""
import sys
from plumbline_detector.record import analyze, CHECK_ORDER
ab = {c: c.split("-",1)[1][:10] for c in CHECK_ORDER}
paths = sys.argv[1:]
print(f"{'fixture':32}" + " ".join(f"{c[:3]+c.split('-')[1][:6]:>9}" for c in CHECK_ORDER))
for p in paths:
    rec = analyze(p)
    print(f"{p.split('fixtures/')[-1][:32]:32}" + " ".join(f"{c['verdict'][:4]+('/'+str(len(c['findings'])) if c['findings'] else ''):>9}" for c in rec["checks"]))
