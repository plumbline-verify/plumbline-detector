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
    ("gha/skip-discrim-pr-true", "GT-SKIP-SATISFIES", "PASS", 0),  # skip only possible on push to main
    ("gha/skip-bad-merge-queue", "GT-SKIP-SATISFIES", "FAIL", 1),  # skipped on merge_group events
    ("gha/agg-absent", "GT-SKIP-SATISFIES", "UNKNOWN", 0),  # nothing declared, nothing to infer
    # GT-CONTINUE-ON-ERROR
    ("gha/coe-good", "GT-CONTINUE-ON-ERROR", "PASS", 0),
    ("gha/coe-bad-step", "GT-CONTINUE-ON-ERROR", "FAIL", 1),
    ("gha/coe-bad-job", "GT-CONTINUE-ON-ERROR", "FAIL", 1),
    ("gha/coe-unrecognized", "GT-CONTINUE-ON-ERROR", "UNKNOWN", 0),
    ("gha/coe-discrim-matrix", "GT-CONTINUE-ON-ERROR", "PASS", 0),  # no matrix leg makes it true
    ("gha/coe-bad-include", "GT-CONTINUE-ON-ERROR", "FAIL", 1),  # an include leg makes it true
    ("gha/coe-unknown-expr", "GT-CONTINUE-ON-ERROR", "UNKNOWN", 0),  # non-matrix context
    # GT-AGGREGATOR-PERMISSIVE
    ("gha/agg-good-allsgreen", "GT-AGGREGATOR-PERMISSIVE", "PASS", 0),
    ("gha/agg-good-explicit", "GT-AGGREGATOR-PERMISSIVE", "PASS", 0),
    ("gha/agg-good-tojson", "GT-AGGREGATOR-PERMISSIVE", "PASS", 0),
    ("gha/skip-discrim-pr-true", "GT-AGGREGATOR-PERMISSIVE", "PASS", 0),
    ("gha/skip-bad-merge-queue", "GT-AGGREGATOR-PERMISSIVE", "FAIL", 1),
    ("gha/agg-bad-skippable", "GT-AGGREGATOR-PERMISSIVE", "FAIL", 1),
    ("gha/agg-bad-unverified", "GT-AGGREGATOR-PERMISSIVE", "FAIL", 1),
    ("gha/agg-bad-partial", "GT-AGGREGATOR-PERMISSIVE", "FAIL", 1),
    ("gha/agg-absent", "GT-AGGREGATOR-PERMISSIVE", "UNKNOWN", 0),
    ("gha/agg-discrim-release", "GT-AGGREGATOR-PERMISSIVE", "UNKNOWN", 0),  # a release gate is not an aggregator
    ("gha/agg-discrim-coverage", "GT-AGGREGATOR-PERMISSIVE", "UNKNOWN", 0),  # a coverage upload job is not the gate
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
    ("py/exit-discrim-caught", "EC-EXIT-BEFORE-ASSERT", "PASS", 0),  # caught locally
    ("py/exit-unknown-double", "EC-EXIT-BEFORE-ASSERT", "UNKNOWN", 0),  # inside a test double
    ("py/exit-unknown-fork", "EC-EXIT-BEFORE-ASSERT", "UNKNOWN", 0),  # child process after os.fork
    # EC-EQUALITY-OVERRIDE (eq-good is the required discrimination case)
    ("py/eq-good", "EC-EQUALITY-OVERRIDE", "PASS", 0),
    ("py/eq-bad-impl", "EC-EQUALITY-OVERRIDE", "FAIL", 1),
    ("py/eq-bad-test", "EC-EQUALITY-OVERRIDE", "FAIL", 2),
    ("py/eq-bad-lambda", "EC-EQUALITY-OVERRIDE", "FAIL", 1),
    ("py/eq-unknown-testhelper", "EC-EQUALITY-OVERRIDE", "UNKNOWN", 0),
    ("py/eq-unknown-stateful", "EC-EQUALITY-OVERRIDE", "UNKNOWN", 0),  # ignores other, but not constant
    ("py/eq-unknown-stateful2", "EC-EQUALITY-OVERRIDE", "UNKNOWN", 0),  # different literals chosen by state
    # EC-RUNNER-PATCHED
    ("py/runner-good", "EC-RUNNER-PATCHED", "PASS", 0),
    ("py/runner-bad", "EC-RUNNER-PATCHED", "FAIL", 2),
    ("py/runner-bad-hook", "EC-RUNNER-PATCHED", "FAIL", 3),
    ("py/runner-bad-pyfunc", "EC-RUNNER-PATCHED", "FAIL", 1),
    ("py/runner-bad-unittest", "EC-RUNNER-PATCHED", "FAIL", 2),
    ("py/runner-discrim-nested", "EC-RUNNER-PATCHED", "UNKNOWN", 0),  # hook on a nested pytester session
    ("py/live-data", "EC-RUNNER-PATCHED", "PASS", 0),  # conftest in a data dir pytest never loads
    ("py/live-data", "EC-ASSERTION-NONSTANDARD", "PASS", 0),  # lint input under tests/functional is data
    ("py/live-data", "EC-EQUALITY-OVERRIDE", "FAIL", 1),  # imported helper is live test code
    ("py/runner-discrim-nested", "EC-ASSERTION-NONSTANDARD", "PASS", 0),  # pytest.fail.Exception is not Exception
    # EC-TESTS-NOT-RUN
    ("py/notrun-good", "EC-TESTS-NOT-RUN", "PASS", 0),
    ("py/notrun-discrim-override", "EC-TESTS-NOT-RUN", "PASS", 0),  # CI runs the slow tests separately
    ("py/notrun-bad-skip", "EC-TESTS-NOT-RUN", "FAIL", 5),
    ("py/notrun-bad-deselect", "EC-TESTS-NOT-RUN", "FAIL", 3),
    ("py/notrun-bad-ignore", "EC-TESTS-NOT-RUN", "FAIL", 2),
    ("py/notrun-unknown-scope", "EC-TESTS-NOT-RUN", "UNKNOWN", 0),
    ("py/notrun-unknown-invocation", "EC-TESTS-NOT-RUN", "UNKNOWN", 0),
    ("py/notrun-malformed-config", "EC-TESTS-NOT-RUN", "UNKNOWN", 0),
    ("py/notrun-discrim-toxtoml", "EC-TESTS-NOT-RUN", "PASS", 0),  # [tool.tox] env runs the stress tests
    # EC-NO-ASSERTION
    ("py/noassert-good", "EC-NO-ASSERTION", "PASS", 0),
    ("py/noassert-bad", "EC-NO-ASSERTION", "FAIL", 3),
    ("py/noassert-discrim-helpers", "EC-NO-ASSERTION", "PASS", 0),  # decorator, support-module helper, test calling a test
    ("py/noassert-discrim-r2", "EC-NO-ASSERTION", "PASS", 0),  # partial, callable class, fixture closure, RaisesGroup
    ("py/noassert-unknown-codestring", "EC-NO-ASSERTION", "UNKNOWN", 0),  # asserts only inside executed code
    # EC-MOCK-ONLY
    ("py/mock-good", "EC-MOCK-ONLY", "PASS", 0),
    ("py/mock-bad", "EC-MOCK-ONLY", "FAIL", 2),
    ("py/mock-discrim-attrassign", "EC-MOCK-ONLY", "PASS", 0),  # real module attribute assigned in finally
    # EC-SPECIAL-CASED
    ("py/special-good", "EC-SPECIAL-CASED", "PASS", 0),
    ("py/special-bad", "EC-SPECIAL-CASED", "FAIL", 1),
    ("py/special-bad-probe", "EC-SPECIAL-CASED", "FAIL", 2),
    ("py/special-bad-probe2", "EC-SPECIAL-CASED", "FAIL", 2),
    ("py/special-discrim-seqlit", "EC-SPECIAL-CASED", "PASS", 0),  # the sequence literal also appears in code
    ("py/special-discrim-table", "EC-SPECIAL-CASED", "PASS", 0),  # strings in a table are not a probe
    # EC-ASSERTION-NONSTANDARD
    ("py/nonstd-good", "EC-ASSERTION-NONSTANDARD", "PASS", 0),
    ("py/nonstd-bad", "EC-ASSERTION-NONSTANDARD", "FAIL", 9),
    ("py/nonstd-discrim-r1", "EC-ASSERTION-NONSTANDARD", "PASS", 0),  # caching identity, recording handler, else-raise, later raise
    # JavaScript / TypeScript
    ("js/good", "EC-NO-ASSERTION-JS", "PASS", 0),  # helper, getByText, each, awaited/returned resolves
    ("js/noassert-bad", "EC-NO-ASSERTION-JS", "FAIL", 2),
    ("js/good-r2", "EC-NO-ASSERTION-JS", "PASS", 0),  # supertest .expect, .bind alias, asserting callback
    ("js/good-r2", "EC-ASSERTION-NONSTANDARD-JS", "PASS", 0),  # stateful matcher on a literal, assert(0) guard
    ("js/good-r3", "EC-TESTS-NOT-RUN-JS", "PASS", 0),  # local function named test; each with a function reference
    ("js/good-r3", "EC-NO-ASSERTION-JS", "PASS", 0),
    ("js/good-r3", "EC-ASSERTION-NONSTANDARD-JS", "PASS", 0),  # local assert(); literals that differ (always fails)
    ("js/good", "EC-TESTS-NOT-RUN-JS", "PASS", 0),
    ("js/notrun-bad", "EC-TESTS-NOT-RUN-JS", "FAIL", 5),  # skip, xit, todo, pending, xdescribe
    ("js/notrun-only", "EC-TESTS-NOT-RUN-JS", "FAIL", 1),  # .only under jest excludes siblings
    ("js/notrun-only-vitest", "EC-TESTS-NOT-RUN-JS", "PASS", 0),  # vitest fails CI runs on .only
    ("js/notrun-only-unknownfw", "EC-TESTS-NOT-RUN-JS", "UNKNOWN", 0),
    ("js/good", "EC-ASSERTION-NONSTANDARD-JS", "PASS", 0),
    ("js/nonstd-bad", "EC-ASSERTION-NONSTANDARD-JS", "FAIL", 4),  # bare, uncalled, constant, unawaited
    ("js/nonstd-chai", "EC-ASSERTION-NONSTANDARD-JS", "PASS", 0),  # chai property assertions are real
    ("js/exit-good", "EC-EXIT-BEFORE-ASSERT-JS", "PASS", 0),
    ("js/exit-bad", "EC-EXIT-BEFORE-ASSERT-JS", "FAIL", 1),
    ("js/good", "EC-RUNNER-PATCHED-JS", "PASS", 0),  # a real custom matcher computes pass
    ("js/runner-bad", "EC-RUNNER-PATCHED-JS", "FAIL", 2),  # always-pass matcher, reassigned it
]

JS = [c for c in CHECK_ORDER if c.endswith("-JS")]


@pytest.mark.parametrize("check", JS)
def test_js_unparseable_unknown(check):
    res = run("js/malformed")[check]
    assert res["verdict"] == "UNKNOWN", res
    assert any("parse failure" in u["message"] for u in res["unknowns"])


@pytest.mark.parametrize("check", JS)
def test_js_no_tests_unknown(check):
    assert run("js/no-tests")[check]["verdict"] == "UNKNOWN"

GT = [c for c in CHECK_ORDER if c.startswith("GT-")]
EC = [c for c in CHECK_ORDER if c.startswith("EC-") and not c.endswith("-JS")]
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


def test_not_run_reasons_are_specific():
    res = run("py/notrun-bad-deselect")["EC-TESTS-NOT-RUN"]
    msgs = " | ".join(f["message"] for f in res["findings"])
    assert "-k 'not overflow'" in msgs and "-m 'not flaky'" in msgs and "--deselect" in msgs
    res = run("py/notrun-bad-ignore")["EC-TESTS-NOT-RUN"]
    msgs = " | ".join(f["message"] for f in res["findings"])
    assert "collect_ignore in tests/conftest.py" in msgs and "--ignore tests/integration" in msgs


def test_malformed_pytest_config_reported():
    res = run("py/notrun-malformed-config")["EC-TESTS-NOT-RUN"]
    assert any("config unparseable" in u["message"] for u in res["unknowns"])


def test_out_of_scope_tests_not_counted_by_no_assertion(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\nnorecursedirs = tests/data\n")
    (tmp_path / "tests" / "data").mkdir(parents=True)
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 + 1 == 2\n")
    (tmp_path / "tests" / "data" / "test_input.py").write_text("def test_placeholder():\n    pass\n")
    res = {c["id"]: c for c in analyze(str(tmp_path))["checks"]}
    assert res["EC-NO-ASSERTION"]["verdict"] == "PASS"
    assert res["EC-TESTS-NOT-RUN"]["verdict"] == "UNKNOWN"


def test_configured_python_files_become_test_code(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\npython_files = check_*.py\n")
    (tmp_path / "check_math.py").write_text("def test_math():\n    pass\n")
    res = {c["id"]: c for c in analyze(str(tmp_path))["checks"]}
    assert res["EC-NO-ASSERTION"]["verdict"] == "FAIL"
