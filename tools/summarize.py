"""Print a compact summary of one or more detector records."""
import json
import sys

for f in sys.argv[1:]:
    r = json.load(open(f))
    inv = r["inventory"]
    sha = (r["provenance"]["commit_sha"] or "-")[:10]
    print(f"{f.split('/')[-1]} sha={sha} lang={inv['primary_language']} loc={inv['loc_nonblank_total']} "
          f"py_test_files={inv['test_file_count']} workflows={inv['github_workflow_files']}")
    for c in r["checks"]:
        print(f"   {c['id']:26} {c['verdict']:8} F={len(c['findings']):4} U={len(c['unknowns']):3} "
              f"{c.get('basis', ''):9} {c['reason'][:70]}")
