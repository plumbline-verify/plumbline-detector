import json
import os
import subprocess
import sys

from plumbline_detector.cli import diff_main
from plumbline_detector.record import analyze, dumps
from plumbline_detector.render import to_markdown, to_sarif

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def test_sarif_structure_and_levels():
    rec = analyze(os.path.join(FIX, "py/nonstd-bad"))
    sarif = json.loads(to_sarif(rec))
    run = sarif["runs"][0]
    assert sarif["version"] == "2.1.0"
    assert {r["id"] for r in run["tool"]["driver"]["rules"]} == {c["id"] for c in rec["checks"]}
    errors = [r for r in run["results"] if r["level"] == "error"]
    assert len(errors) == sum(len(c["findings"]) for c in rec["checks"])
    assert all(r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in errors)


def test_sarif_reports_unknowns_as_notes():
    rec = analyze(os.path.join(FIX, "gha/malformed-syntax"))
    notes = [r for r in json.loads(to_sarif(rec))["runs"][0]["results"] if r["level"] == "note"]
    assert notes


def test_markdown_lists_every_check_and_disclaimer():
    rec = analyze(os.path.join(FIX, "py/runner-bad"))
    md = to_markdown(rec)
    for c in rec["checks"]:
        assert f"`{c['id']}`" in md
    assert "not a certificate" in md
    assert "TestReport" in md


def test_renderers_deterministic():
    rec = analyze(os.path.join(FIX, "gha/agg-bad-unverified"))
    assert to_sarif(rec) == to_sarif(analyze(os.path.join(FIX, "gha/agg-bad-unverified")))
    assert to_markdown(rec) == to_markdown(analyze(os.path.join(FIX, "gha/agg-bad-unverified")))


def test_finding_ids_stable_across_line_shift(tmp_path):
    (tmp_path / "tests").mkdir()
    t = tmp_path / "tests" / "test_a.py"
    t.write_text("def test_a():\n    pass\n")
    a = analyze(str(tmp_path))
    t.write_text("\n\n\ndef test_a():\n    pass\n")
    b = analyze(str(tmp_path))
    fa = {c["id"]: c for c in a["checks"]}["EC-NO-ASSERTION"]["findings"][0]
    fb = {c["id"]: c for c in b["checks"]}["EC-NO-ASSERTION"]["findings"][0]
    assert fa["line"] != fb["line"] and fa["id"] == fb["id"]


def test_diff_flags_new_findings(tmp_path, capsys):
    (tmp_path / "tests").mkdir()
    t = tmp_path / "tests" / "test_a.py"
    t.write_text("def test_a():\n    assert 1 + 1 == 2\n")
    old = tmp_path.parent / "old.json"
    old.write_text(dumps(analyze(str(tmp_path))))
    t.write_text("def test_a():\n    assert 1 + 1 == 2\n\n\ndef test_b():\n    pass\n")
    new = tmp_path.parent / "new.json"
    new.write_text(dumps(analyze(str(tmp_path))))
    assert diff_main([str(old), str(new)]) == 1
    assert "+ EC-NO-ASSERTION" in capsys.readouterr().out
    assert diff_main([str(new), str(new)]) == 0


def test_cli_formats():
    for fmt in ("sarif", "markdown"):
        p = subprocess.run([sys.executable, "-m", "plumbline_detector.cli", os.path.join(FIX, "py/eq-good"), "--format", fmt], capture_output=True, check=True)
        assert p.stdout


def test_measured_precision_attached_and_honest():
    from plumbline_detector.record import load_measurements, ruleset_fingerprint

    rec = analyze(os.path.join(FIX, "py/nonstd-bad"))
    m = {c["id"]: c["measured_precision"] for c in rec["checks"]}
    assert m["EC-NO-ASSERTION"]["labeled"] > 0 and 0 <= m["EC-NO-ASSERTION"]["precision"] <= 1
    lo, hi = m["EC-NO-ASSERTION"]["ci95"]
    assert lo <= m["EC-NO-ASSERTION"]["precision"] <= hi
    assert m["GT-NO-GATE"] is None  # never labeled, by protocol
    measurements, digest = load_measurements()
    measured_fps = {r["ruleset_fingerprint"] for r in measurements["rounds"]}
    for v in m.values():
        if v:
            assert v["same_ruleset"] == (ruleset_fingerprint() in measured_fps)
    assert rec["provenance"]["measurements_sha256"] == digest
    md = to_markdown(rec)
    assert "Measured precision" in md and "not measured" in md
