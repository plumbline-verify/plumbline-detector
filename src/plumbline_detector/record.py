"""Assemble the versioned JSON record.

Determinism: every collection is sorted, no absolute paths or wall-clock
values enter the record unless explicitly requested (--now), and JSON is
serialized with sorted keys. Two runs over identical input with identical
options and environment produce byte-identical output.
"""

from __future__ import annotations

import hashlib
import json
import platform
from importlib import resources

import yaml

from . import SCHEMA_VERSION, __version__, snapshot
from .gha import checks as gha_checks
from .gha import model as gha_model
from .py import checks as py_checks
from .py import common as py_common

CHECK_ORDER = [
    "GT-SKIP-SATISFIES",
    "GT-CONTINUE-ON-ERROR",
    "GT-AGGREGATOR-PERMISSIVE",
    "GT-NO-PROPAGATION",
    "GT-NO-GATE",
    "EC-EXIT-BEFORE-ASSERT",
    "EC-EQUALITY-OVERRIDE",
    "EC-RUNNER-PATCHED",
    "EC-NO-ASSERTION",
    "EC-MOCK-ONLY",
    "EC-SPECIAL-CASED",
    "EC-ASSERTION-NONSTANDARD",
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
    "py/common.py",
    "py/assertions.py",
    "py/checks.py",
    "catalog.py",
    "render.py",
]


def ruleset_fingerprint() -> str:
    h = hashlib.sha256()
    base = resources.files("plumbline_detector")
    for rel in FINGERPRINT_MODULES:
        data = base.joinpath(rel).read_bytes().replace(b"\r\n", b"\n")
        h.update(rel.encode() + b"\0" + hashlib.sha256(data).hexdigest().encode() + b"\n")
    return "sha256:" + h.hexdigest()


class Context:
    def __init__(self, snap):
        self.snap = snap


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


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

    gm = gha_model.build(snap)
    gate = gha_model.gate_info(snap, required_checks, gate_files)
    pm = py_common.build(snap)
    ctx = Context(snap)
    data_set = set(pm.data_paths)
    results = {}
    for fn in gha_checks.ALL:
        res = fn(gm, gate)
        results[res.check_id] = res
    for fn in py_checks.ALL:
        res = fn(pm, ctx)
        results[res.check_id] = res
    assert list(sorted(results)) == sorted(CHECK_ORDER), "check registry mismatch"

    if commit_sha:
        sha, sha_source = commit_sha, "operator"
    else:
        sha, sha_source = snapshot.commit_sha(root)

    checks = [results[c].to_json() for c in CHECK_ORDER]
    summary = {v: sum(1 for c in checks if c["verdict"] == v) for v in ("PASS", "FAIL", "UNKNOWN")}
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "plumbline-detector", "version": __version__},
        "provenance": {
            "ruleset_fingerprint": ruleset_fingerprint(),
            "operator_set": CHECK_ORDER,
            "config": config,
            "config_hash": config_hash,
            "environment": {
                "python": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "pyyaml": yaml.__version__,
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
        | {"github_workflow_files": len(gm.workflow_paths), "python_test_data_files": len(pm.data_paths)},
        "summary": summary,
        "checks": checks,
    }


def dumps(record: dict) -> str:
    return json.dumps(record, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
