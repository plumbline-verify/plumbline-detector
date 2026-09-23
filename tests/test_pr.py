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
    removal = ("PR-ASSERTIONS-REMOVED", "PR-TESTS-DISABLED", "PR-TESTS-REMOVED", "PR-NEW-TAMPERING")
    assert all(by[c]["verdict"] == "FAIL" for c in removal)
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


def test_moves_and_preexisting_constructs_are_not_reported():
    """PR-study causes: tests moved into a renamed class in another file,
    and a conditional continue-on-error that was already there (the change
    only adds a matrix leg)."""
    rec = _run("discrim-r1")
    assert rec["summary"] == {"FAIL": 0, "findings": 0}


def _messages(rec):
    return {(c["id"], f["file"], f["message"]) for c in rec["checks"] for f in c["findings"]}


def test_loosening_is_reported_by_each_loosening_check():
    """Verification kept in place but made easier to pass (the TRACE miss
    categories): tolerances and thresholds, timeouts, swallowed failures,
    mocks of the code under test, configuration exclusions."""
    got = _messages(_run("loosen-bad"))
    expected = {
        ("PR-TOLERANCE-LOOSENED", "tests/test_calc.py", "test test_mean: rel@approx 1e-06 -> 0.01"),
        ("PR-TOLERANCE-LOOSENED", "tests/test_calc.py", "test test_speed: assert<0 0.5 -> 5"),
        ("PR-TOLERANCE-LOOSENED", "web/sum.test.js", "test sum is close: toBeCloseTo.digits 5 -> 1"),
        ("PR-TOLERANCE-LOOSENED", "web/sum.test.js", "test sum is close: toBeLessThan 4 -> 40"),
        ("PR-TIMEOUT-RAISED", "pyproject.toml", "configured timeout: 30 -> 300"),
        ("PR-TIMEOUT-RAISED", "tests/test_calc.py", "test test_mean: mark.timeout 5 -> 60"),
        ("PR-TIMEOUT-RAISED", "web/jest.config.js", "configured testTimeout: 5000 -> 30000"),
        ("PR-TIMEOUT-RAISED", "web/sum.test.js", "test sum is close: test-arg 1000 -> 10000"),
        ("PR-ASSERTION-SWALLOWED", "tests/test_calc.py", "test test_parse: assertion failures caught and discarded (0 -> 1)"),
        ("PR-ASSERTION-SWALLOWED", "web/sum.test.js", "test sum adds: assertion failures caught and discarded (0 -> 1)"),
        ("PR-MOCK-UNDER-TEST", "tests/test_calc.py", "test test_total: now patches total and calls it directly"),
        ("PR-MOCK-UNDER-TEST", "web/sum.test.js", "test file now mocks its own subject module ./sum"),
        ("PR-TESTS-EXCLUDED", "pyproject.toml", "adds exclusion --ignore tests/test_slow.py"),
        ("PR-TESTS-EXCLUDED", "pyproject.toml", "adds exclusion -k not flaky"),
        ("PR-TESTS-EXCLUDED", "web/jest.config.js", "adds exclusion testPathIgnorePatterns <rootDir>/legacy/"),
    }
    assert expected <= got
    assert {m for m in got if m[0] != "PR-NEW-TAMPERING"} == expected


def test_loosening_discrimination():
    """The mirror image of loosen-bad must be silent: tolerances tightened,
    thresholds lowered, timeouts lowered, a handler that re-raises, a spy
    that calls through (wraps=), a patched dependency, a mocked sibling
    module, an added (not changed) threshold, a default exclusion
    (.venv, /dist/), an exclusion in a non-test tool's section, and a
    removed exclusion."""
    rec = _run("loosen-good")
    assert rec["summary"] == {"FAIL": 0, "findings": 0}


def test_loosened_compares_only_matching_kinds():
    from plumbline_detector.loosen import loosened

    # an added assertion is not a changed one
    assert loosened([("assert<0", 1.0, 1)], [("assert<0", 1.0, 1), ("assert<0", 9.0, 1)]) == []
    assert loosened([("places", 7.0, -1)], [("places", 2.0, -1)]) == [("places", 7.0, 2.0)]
    assert loosened([("places", 2.0, -1)], [("places", 7.0, -1)]) == []


def test_config_exclusions_need_a_runner_context():
    from plumbline_detector.loosen import config_profile

    wf = b"steps:\n  - run: pip install --ignore-installed x\n  - run: pytest --deselect tests/test_a.py::test_b\n  - run: eslint --ignore tests\n"
    assert config_profile(".github/workflows/ci.yml", wf)["exclusions"] == {("--deselect", "tests/test_a.py::test_b")}
    toml = b'[tool.coverage.run]\nomit = ["pkg/legacy.py"]\n[tool.ruff]\nexclude = ["x"]\n'
    assert config_profile("pyproject.toml", toml)["exclusions"] == {("omit", "pkg/legacy.py")}
