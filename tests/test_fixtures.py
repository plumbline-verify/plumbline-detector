"""Every check: known-good -> PASS, known-bad -> FAIL, absent/unparseable
input -> UNKNOWN. Expectations are exact; a check that stops firing on its
known-bad fixture fails this suite."""

import os

import pytest

from plumbline_detector.record import CHECK_ORDER, analyze

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures")

# (fixture, check, verdict, number of findings)
CASES = [
    # GT-SKIP-SATISFIES
    ("gha/skip-good", "GT-SKIP-SATISFIES", "PASS", 0),
    ("gha/skip-discrim-always", "GT-SKIP-SATISFIES", "PASS", 0),
    ("gha/skip-bad", "GT-SKIP-SATISFIES", "FAIL", 1),
    ("gha/skip-bad-matrix", "GT-SKIP-SATISFIES", "FAIL", 1),
    ("gha/agg-absent", "GT-SKIP-SATISFIES", "UNKNOWN", 0),  # nothing declared, nothing to infer
    # GT-CONTINUE-ON-ERROR
    ("gha/coe-good", "GT-CONTINUE-ON-ERROR", "PASS", 0),
    ("gha/coe-bad-step", "GT-CONTINUE-ON-ERROR", "FAIL", 1),
    ("gha/coe-bad-job", "GT-CONTINUE-ON-ERROR", "FAIL", 1),
    ("gha/coe-unrecognized", "GT-CONTINUE-ON-ERROR", "UNKNOWN", 0),
    # GT-AGGREGATOR-PERMISSIVE
    ("gha/agg-good-allsgreen", "GT-AGGREGATOR-PERMISSIVE", "PASS", 0),
    ("gha/agg-good-explicit", "GT-AGGREGATOR-PERMISSIVE", "PASS", 0),
    ("gha/agg-bad-skippable", "GT-AGGREGATOR-PERMISSIVE", "FAIL", 1),
    ("gha/agg-bad-unverified", "GT-AGGREGATOR-PERMISSIVE", "FAIL", 1),
    ("gha/agg-bad-partial", "GT-AGGREGATOR-PERMISSIVE", "FAIL", 1),
    ("gha/agg-absent", "GT-AGGREGATOR-PERMISSIVE", "UNKNOWN", 0),
    # GT-NO-PROPAGATION
    ("gha/prop-good", "GT-NO-PROPAGATION", "PASS", 0),
    ("gha/prop-bad-unwired", "GT-NO-PROPAGATION", "FAIL", 1),
    ("gha/prop-bad-skipped-gate", "GT-NO-PROPAGATION", "FAIL", 1),
    ("gha/prop-inferred", "GT-NO-PROPAGATION", "UNKNOWN", 0),
    # GT-NO-GATE
    ("gha/gate-good", "GT-NO-GATE", "PASS", 0),
    ("gha/skip-good", "GT-NO-GATE", "PASS", 0),
    ("gha/gate-bad", "GT-NO-GATE", "FAIL", 1),
    ("gha/gate-bad-protection-no-checks", "GT-NO-GATE", "FAIL", 1),
    ("gha/gate-malformed", "GT-NO-GATE", "UNKNOWN", 0),
    # EC-EXIT-BEFORE-ASSERT
    ("py/exit-good", "EC-EXIT-BEFORE-ASSERT", "PASS", 0),
    ("py/exit-bad", "EC-EXIT-BEFORE-ASSERT", "FAIL", 1),
    ("py/exit-bad-os", "EC-EXIT-BEFORE-ASSERT", "FAIL", 1),
    ("py/exit-unknown", "EC-EXIT-BEFORE-ASSERT", "UNKNOWN", 0),
    # EC-EQUALITY-OVERRIDE (eq-good is the required discrimination case)
    ("py/eq-good", "EC-EQUALITY-OVERRIDE", "PASS", 0),
    ("py/eq-bad-impl", "EC-EQUALITY-OVERRIDE", "FAIL", 1),
    ("py/eq-bad-test", "EC-EQUALITY-OVERRIDE", "FAIL", 2),
    ("py/eq-bad-lambda", "EC-EQUALITY-OVERRIDE", "FAIL", 1),
    ("py/eq-unknown-testhelper", "EC-EQUALITY-OVERRIDE", "UNKNOWN", 0),
    # EC-RUNNER-PATCHED
    ("py/runner-good", "EC-RUNNER-PATCHED", "PASS", 0),
    ("py/runner-bad", "EC-RUNNER-PATCHED", "FAIL", 2),
    ("py/runner-bad-hook", "EC-RUNNER-PATCHED", "FAIL", 3),
    ("py/runner-bad-pyfunc", "EC-RUNNER-PATCHED", "FAIL", 1),
    ("py/runner-bad-unittest", "EC-RUNNER-PATCHED", "FAIL", 2),
    # EC-NO-ASSERTION
    ("py/noassert-good", "EC-NO-ASSERTION", "PASS", 0),
    ("py/noassert-bad", "EC-NO-ASSERTION", "FAIL", 3),
    # EC-MOCK-ONLY
    ("py/mock-good", "EC-MOCK-ONLY", "PASS", 0),
    ("py/mock-bad", "EC-MOCK-ONLY", "FAIL", 2),
    # EC-SPECIAL-CASED
    ("py/special-good", "EC-SPECIAL-CASED", "PASS", 0),
    ("py/special-bad", "EC-SPECIAL-CASED", "FAIL", 1),
    ("py/special-bad-probe", "EC-SPECIAL-CASED", "FAIL", 2),
    # EC-ASSERTION-NONSTANDARD
    ("py/nonstd-good", "EC-ASSERTION-NONSTANDARD", "PASS", 0),
    ("py/nonstd-bad", "EC-ASSERTION-NONSTANDARD", "FAIL", 9),
]

GT = [c for c in CHECK_ORDER if c.startswith("GT-")]
EC = [c for c in CHECK_ORDER if c.startswith("EC-")]
MALFORMED_GHA = ["malformed-syntax", "malformed-dupkey", "malformed-merge", "malformed-shape", "malformed-binary", "malformed-empty"]

_cache = {}


def run(fixture):
    if fixture not in _cache:
        _cache[fixture] = {c["id"]: c for c in analyze(os.path.join(FIX, fixture))["checks"]}
    return _cache[fixture]


@pytest.mark.parametrize("fixture,check,verdict,n", CASES, ids=[f"{c[1]}:{c[0]}" for c in CASES])
def test_fixture(fixture, check, verdict, n):
    res = run(fixture)[check]
    assert res["verdict"] == verdict, res
    assert len(res["findings"]) == n, res["findings"]
    for f in res["findings"]:
        assert f["file"] and f["message"]


def test_every_check_has_pass_fail_and_unknown_cases():
    for check in CHECK_ORDER:
        verdicts = {v for _, c, v, _ in CASES if c == check}
        assert {"PASS", "FAIL"} <= verdicts, check
    # UNKNOWN on absent / unparseable input is covered for every check below.


@pytest.mark.parametrize("check", CHECK_ORDER)
def test_empty_directory_is_unknown(tmp_path, check):
    res = {c["id"]: c for c in analyze(str(tmp_path))["checks"]}[check]
    assert res["verdict"] == "UNKNOWN"


@pytest.mark.parametrize("check", GT)
def test_gt_absent_workflows_unknown(check):
    # Python-only repository: no workflow files at all.
    assert run("py/eq-good")[check]["verdict"] == "UNKNOWN"


@pytest.mark.parametrize("fixture", MALFORMED_GHA)
@pytest.mark.parametrize("check", [c for c in GT if c != "GT-NO-GATE"])
def test_malformed_workflow_never_passes(fixture, check):
    res = run(f"gha/{fixture}")[check]
    assert res["verdict"] == "UNKNOWN", res
    assert res["unknowns"], "a parse failure must be reported as a location"


@pytest.mark.parametrize("fixture", MALFORMED_GHA)
def test_malformed_workflow_no_gate_not_pass(fixture):
    assert run(f"gha/{fixture}")["GT-NO-GATE"]["verdict"] != "PASS"


@pytest.mark.parametrize("check", EC)
def test_ec_unparseable_test_file_unknown(check):
    res = run("py/malformed")[check]
    assert res["verdict"] == "UNKNOWN", res
    assert any("parse failure" in u["message"] for u in res["unknowns"])


@pytest.mark.parametrize("check", EC)
def test_ec_no_tests_unknown(check):
    assert run("py/no-tests")[check]["verdict"] == "UNKNOWN"


def test_equality_discrimination_value_object_outside_tests():
    """Required discrimination case: a legitimate value-object __eq__ in
    implementation code must not fire, while an always-true __eq__ in
    implementation code must."""
    good = run("py/eq-good")["EC-EQUALITY-OVERRIDE"]
    assert good["verdict"] == "PASS" and good["stats"]["equality_definitions_examined"] == 2
    bad = run("py/eq-bad-impl")["EC-EQUALITY-OVERRIDE"]
    assert bad["findings"][0]["file"] == "pkg/solver.py"


def test_inferred_basis_is_labeled():
    res = run("gha/prop-inferred")
    assert res["GT-NO-PROPAGATION"]["basis"] == "inferred"
    assert res["GT-NO-PROPAGATION"]["unknowns"]


def test_unread_file_blocks_pass(tmp_path, monkeypatch):
    from plumbline_detector import snapshot

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 + 1 == 2\n")
    (tmp_path / "tests" / "test_big.py").write_text("x = 1\n" * 10)
    monkeypatch.setattr(snapshot, "MAX_FILE_BYTES", 40)
    res = {c["id"]: c for c in analyze(str(tmp_path))["checks"]}
    assert res["EC-NO-ASSERTION"]["verdict"] == "UNKNOWN"
    assert any("size_limit" in u["message"] for u in res["EC-NO-ASSERTION"]["unknowns"])
