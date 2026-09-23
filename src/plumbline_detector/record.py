"""Assemble the versioned JSON record.

Determinism: every collection is sorted, no absolute paths or wall-clock
values enter the record unless explicitly requested (--now), and JSON is
serialized with sorted keys. Two runs over identical input with identical
options and environment produce byte-identical output.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
from importlib import resources

import yaml

from . import SCHEMA_VERSION, __version__, snapshot
from .gha import checks as gha_checks
from .gha import model as gha_model
from .js import checks as js_checks
from .js import common as js_common
from .py import checks as py_checks
from .py import collection as py_collection
from .py import common as py_common
from .py import liveness as py_liveness

CHECK_ORDER = [
    "GT-SKIP-SATISFIES",
    "GT-CONTINUE-ON-ERROR",
    "GT-AGGREGATOR-PERMISSIVE",
    "GT-NO-PROPAGATION",
    "GT-NO-GATE",
    "EC-EXIT-BEFORE-ASSERT",
    "EC-EQUALITY-OVERRIDE",
    "EC-RUNNER-PATCHED",
    "EC-TESTS-NOT-RUN",
    "EC-NO-ASSERTION",
    "EC-MOCK-ONLY",
    "EC-SPECIAL-CASED",
    "EC-ASSERTION-NONSTANDARD",
    "EC-EXIT-BEFORE-ASSERT-JS",
    "EC-RUNNER-PATCHED-JS",
    "EC-TESTS-NOT-RUN-JS",
    "EC-NO-ASSERTION-JS",
    "EC-ASSERTION-NONSTANDARD-JS",
]

# Source files whose content defines check semantics. Their combined hash is
# the ruleset fingerprint; tests/test_versioning.py pins it to SCHEMA_VERSION.
FINGERPRINT_MODULES = [
    "__init__.py",
    "model.py",
    "snapshot.py",
    "record.py",
    "gha/yamlnodes.py",
    "gha/model.py",
    "gha/checks.py",
    "gha/expr.py",
    "py/common.py",
    "py/assertions.py",
    "py/checks.py",
    "py/collection.py",
    "py/liveness.py",
    "js/common.py",
    "js/checks.py",
    "catalog.py",
    "render.py",
    "pr.py",
]


def ruleset_fingerprint() -> str:
    h = hashlib.sha256()
    base = resources.files("plumbline_detector")
    for rel in FINGERPRINT_MODULES:
        data = base.joinpath(rel).read_bytes().replace(b"\r\n", b"\n")
        h.update(rel.encode() + b"\0" + hashlib.sha256(data).hexdigest().encode() + b"\n")
    return "sha256:" + h.hexdigest()


def _dist_version(name):
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def load_measurements():
    raw = resources.files("plumbline_detector").joinpath("measurements.json").read_bytes()
    return json.loads(raw), "sha256:" + hashlib.sha256(raw).hexdigest()


def measured_precision(check_id, measurements, fingerprint):
    """The most recent held-out measurement of a check, or None if it never
    produced a finding in any round. `same_ruleset` says whether it was
    measured on exactly the check code now running."""
    for rnd in sorted(measurements["rounds"], key=lambda r: -r["round"]):
        m = rnd["checks"].get(check_id)
        if m and m["labeled"]:
            return {
                "round": rnd["round"],
                "schema": rnd["schema"],
                "same_ruleset": rnd["ruleset_fingerprint"] == fingerprint,
                "repositories": rnd["repositories"],
                "labeled": m["labeled"],
                "true_positives": m["tp"],
                "precision": round(m["tp"] / m["labeled"], 3),
                "ci95": _wilson(m["tp"], m["labeled"]),
            }
    return None


# Grade policy (docs/PRECISION_STUDY.md, "Precision targets"). A check's
# grade is derived from its most recent held-out measurement, so each study
# round recalibrates which findings are verdicts and which are leads.
VERDICT_MIN_PRECISION = 0.90
VERDICT_MIN_CI_LOW = 0.80
VERDICT_MIN_LABELED = 20
ADVISORY_MIN_PRECISION = 0.70
ADVISORY_MIN_LABELED = 10


def grade(mp) -> str:
    """'verdict': findings are confirmed defects often enough to act on
    without review. 'advisory': usually right; review each finding.
    'experimental': unmeasured, too few samples, or below the advisory bar."""
    if mp is None or mp["labeled"] < ADVISORY_MIN_LABELED:
        return "experimental"
    if mp["labeled"] >= VERDICT_MIN_LABELED and mp["precision"] >= VERDICT_MIN_PRECISION and mp["ci95"][0] >= VERDICT_MIN_CI_LOW:
        return "verdict"
    if mp["precision"] >= ADVISORY_MIN_PRECISION:
        return "advisory"
    return "experimental"


class Context:
    def __init__(self, snap, collection=None):
        self.snap = snap
        self.collection = collection


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_models(snap, required_checks=(), gate_files=()):
    """GitHub Actions model, gate info, Python model and pytest collection
    model, with collected files promoted to test code and dead test-path
    files reclassified as data. Shared by analyze() and PR mode."""
    gm = gha_model.build(snap)
    gate = gha_model.gate_info(snap, list(required_checks), list(gate_files))
    pm = py_common.build(snap)
    coll = py_collection.build(snap, pm, gm)
    # Files that pytest's configuration collects are test code, whatever their name.
    for p in sorted(coll.collected_files):
        if p in pm.impl_paths:
            pm.impl_paths.remove(p)
            pm.test_paths.append(p)
            pm.files[p].is_test = True
    pm.test_paths.sort()
    # Test-path files nothing executes and nothing imports are test data.
    moved = set(py_liveness.reclassify(pm, coll, snap))
    if moved:
        keep = [i for i, it in enumerate(coll.items) if it.file not in moved]
        remap = {old: new for new, old in enumerate(keep)}
        coll.data_items = len(coll.items) - len(keep)
        coll.items = [coll.items[i] for i in keep]
        coll.not_run = {remap[i]: v for i, v in coll.not_run.items() if i in remap}
        coll.scope_excluded = {remap[i] for i in coll.scope_excluded if i in remap}
    return gm, gate, pm, coll


def analyze(
    root: str,
    required_checks: list[str] | None = None,
    gate_files: list[tuple[str, bytes]] | None = None,
    label: str | None = None,
    commit_sha: str | None = None,
    timestamp: str | None = None,
    timestamp_source: str = "not_supplied",
) -> dict:
    required_checks = sorted(set(required_checks or []))
    gate_files = sorted(gate_files or [])
    snap = snapshot.load(root)
    config = {
        "required_checks": required_checks,
        "gate_files": [{"label": lbl, "sha256": hashlib.sha256(data).hexdigest()} for lbl, data in gate_files],
        "excluded_dirs": sorted(snapshot.EXCLUDED_DIRS),
        "max_file_bytes": snapshot.MAX_FILE_BYTES,
        "python_test_dir_names": sorted(py_common.TEST_DIR_NAMES),
    }
    config_hash = "sha256:" + hashlib.sha256(_canonical(config).encode()).hexdigest()

    gm, gate, pm, coll = build_models(snap, required_checks, gate_files)
    ctx = Context(snap, coll)
    data_set = set(pm.data_paths)
    results = {}
    for fn in gha_checks.ALL:
        res = fn(gm, gate)
        results[res.check_id] = res
    for fn in py_checks.ALL:
        res = fn(pm, ctx)
        results[res.check_id] = res
    jm = js_common.build(snap)
    for fn in js_checks.ALL:
        res = fn(jm)
        results[res.check_id] = res
    assert list(sorted(results)) == sorted(CHECK_ORDER), "check registry mismatch"

    if commit_sha:
        sha, sha_source = commit_sha, "operator"
    else:
        sha, sha_source = snapshot.commit_sha(root)

    measurements, measurements_hash = load_measurements()
    fingerprint = ruleset_fingerprint()
    checks = []
    for c in CHECK_ORDER:
        entry = results[c].to_json()
        entry["measured_precision"] = measured_precision(c, measurements, fingerprint)
        entry["grade"] = grade(entry["measured_precision"])
        checks.append(entry)
    summary = {v: sum(1 for c in checks if c["verdict"] == v) for v in ("PASS", "FAIL", "UNKNOWN")}
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "plumbline-detector", "version": __version__},
        "provenance": {
            "ruleset_fingerprint": fingerprint,
            "measurements_sha256": measurements_hash,
            "operator_set": CHECK_ORDER,
            "config": config,
            "config_hash": config_hash,
            "environment": {
                "python": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "pyyaml": yaml.__version__,
                "tree_sitter": _dist_version("tree-sitter"),
                "tree_sitter_javascript": _dist_version("tree-sitter-javascript"),
                "tree_sitter_typescript": _dist_version("tree-sitter-typescript"),
            },
            "commit_sha": sha,
            "commit_sha_source": sha_source,
            "timestamp": timestamp,
            "timestamp_source": timestamp_source,
        },
        "repo": {
            "content_id": snap.content_id(),
            "label_sha256": hashlib.sha256(label.encode()).hexdigest() if label else None,
        },
        "inventory": snapshot.inventory(snap, lambda p: py_common.is_test_path(p) and p not in data_set)
        | {
            "github_workflow_files": len(gm.workflow_paths),
            "python_test_data_files": len(pm.data_paths),
            "js_test_files": len(jm.tests()),
            "js_frameworks": sorted(set().union(*jm.frameworks.values())) if jm.frameworks else [],
        },
        "summary": summary,
        "checks": checks,
    }


def dumps(record: dict) -> str:
    return json.dumps(record, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
