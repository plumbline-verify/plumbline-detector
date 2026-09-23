"""PR mode: a change that weakens verification is reported; an honest
refactor (tests moved, assertions moved into a helper, tests added) is not."""

import os
import subprocess

import pytest

from plumbline_detector import pr

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures", "pr")


def _run(case):
    return pr.compare(os.path.join(FIX, case, "base"), os.path.join(FIX, case, "head"))


def test_weakening_change_is_reported_by_every_pr_check():
    rec = _run("bad")
    by = {c["id"]: c for c in rec["checks"]}
    assert all(c["verdict"] == "FAIL" for c in rec["checks"])
    assert [f["message"] for f in by["PR-ASSERTIONS-REMOVED"]["findings"]] == ["test test_add: recognized assertions 2 -> 1"]
    disabled = {f["file"] for f in by["PR-TESTS-DISABLED"]["findings"]}
    assert disabled == {"tests/test_add.py", "web/sum.test.js"}  # pytest skip and JS test.skip
    assert "test_add_floats" in by["PR-TESTS-REMOVED"]["findings"][0]["message"]
    tamper = {f["detail"]["check"] for f in by["PR-NEW-TAMPERING"]["findings"]}
    assert tamper == {"GT-CONTINUE-ON-ERROR", "EC-EXIT-BEFORE-ASSERT"}


def test_honest_refactor_is_not_reported():
    rec = _run("good")
    assert rec["summary"] == {"FAIL": 0, "findings": 0}


def test_identical_snapshots_pass_and_output_is_deterministic():
    d = os.path.join(FIX, "bad", "base")
    a, b = pr.compare(d, d), pr.compare(d, d)
    assert a["summary"]["findings"] == 0
    assert pr.dumps(a) == pr.dumps(b)


def test_cli_git_revisions(tmp_path):
    """--repo compares two revisions of a local repository without a network."""
    repo = tmp_path / "r"
    subprocess.run(["cp", "-r", os.path.join(FIX, "bad", "base"), str(repo)], check=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}

    def git(*a):
        subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, env=env)

    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base")
    subprocess.run(["cp", "-r", os.path.join(FIX, "bad", "head") + "/.", str(repo)], check=True)
    git("add", "-A")
    git("commit", "-qm", "head")
    from plumbline_detector.cli import pr_main

    out = tmp_path / "pr.json"
    assert pr_main(["HEAD~1", "HEAD", "--repo", str(repo), "-o", str(out)]) == 1
    assert '"PR-TESTS-DISABLED"' in out.read_text()
