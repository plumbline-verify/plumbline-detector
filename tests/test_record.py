import json
import os
import shutil
import subprocess
import sys

import jsonschema
import pytest

from plumbline_detector import SCHEMA_VERSION
from plumbline_detector.record import analyze, dumps

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIX = os.path.join(ROOT, "fixtures")
SCHEMA = json.load(open(os.path.join(ROOT, "schema", "record.schema.json")))


@pytest.mark.parametrize("fixture", ["gha/prop-good", "py/nonstd-bad", "gha/malformed-syntax", "py/malformed"])
def test_record_validates_against_schema(fixture):
    jsonschema.validate(analyze(os.path.join(FIX, fixture)), SCHEMA)


def test_schema_const_matches_code():
    assert SCHEMA["properties"]["schema_version"]["const"] == SCHEMA_VERSION


def _cli(*args, env=None):
    return subprocess.run([sys.executable, "-m", "plumbline_detector.cli", *args], capture_output=True, env=env, check=True).stdout


def test_two_runs_byte_identical():
    target = os.path.join(FIX, "py/nonstd-bad")
    a, b = _cli(target), _cli(target)
    assert a == b and len(a) > 1000


def test_location_independent(tmp_path):
    """The same content at a different path produces the same record."""
    src = os.path.join(FIX, "gha/agg-bad-unverified")
    dst = tmp_path / "copy"
    shutil.copytree(src, dst)
    assert _cli(src) == _cli(str(dst))


def test_timestamp_is_opt_in(tmp_path):
    rec = json.loads(_cli(os.path.join(FIX, "py/eq-good")))
    assert rec["provenance"]["timestamp"] is None
    rec = json.loads(_cli(os.path.join(FIX, "py/eq-good"), "--timestamp", "2026-09-22T00:00:00Z"))
    assert rec["provenance"]["timestamp_source"] == "operator"


def test_label_is_hashed_not_recorded():
    out = _cli(os.path.join(FIX, "py/eq-good"), "--label", "acme/secret-repo")
    assert b"acme" not in out and b"secret-repo" not in out
    assert json.loads(out)["repo"]["label_sha256"]


def test_config_changes_config_hash():
    a = analyze(os.path.join(FIX, "gha/gate-bad"))
    b = analyze(os.path.join(FIX, "gha/gate-bad"), required_checks=["test"])
    assert a["provenance"]["config_hash"] != b["provenance"]["config_hash"]
    verdict = {c["id"]: c["verdict"] for c in b["checks"]}
    assert verdict["GT-NO-GATE"] == "PASS"


def test_operator_gate_file(tmp_path):
    gate = os.path.join(FIX, "gha/gate-good/.github/rulesets/main.json")
    out = json.loads(_cli(os.path.join(FIX, "gha/gate-bad"), "--gate-file", gate))
    assert {c["id"]: c["verdict"] for c in out["checks"]}["GT-NO-GATE"] == "PASS"


def test_commit_sha_read_from_git_metadata(tmp_path):
    shutil.copytree(os.path.join(FIX, "py/eq-good"), tmp_path / "r")
    git = tmp_path / "r" / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text("a" * 40 + "\n")
    rec = analyze(str(tmp_path / "r"))
    assert rec["provenance"]["commit_sha"] == "a" * 40
    assert rec["provenance"]["commit_sha_source"] == "git_ref"


def test_symlink_outside_root_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "test_leak.py").write_text("def test_x():\n    pass\n")
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_ok.py").write_text("def test_ok():\n    assert 1\n")
    os.symlink(outside, repo / "tests" / "linked")
    rec = analyze(str(repo))
    assert rec["inventory"]["symlinks_not_followed"] == 1
    assert "test_leak" not in dumps(rec)


def test_not_a_directory_exit_code(tmp_path):
    p = subprocess.run([sys.executable, "-m", "plumbline_detector.cli", str(tmp_path / "nope")], capture_output=True)
    assert p.returncode == 2
