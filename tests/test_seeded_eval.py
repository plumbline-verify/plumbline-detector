"""Mechanics of tools/seeded_eval.py, using existing fixtures as a two-entry
corpus. This checks the harness scores correctly; it is not a measurement."""

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import seeded_eval  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def test_harness_scores_tamper_and_benign(tmp_path):
    corpus = tmp_path / "corpus"
    shutil.copytree(os.path.join(FIX, "py/eq-bad-impl"), corpus / "t1")
    shutil.copytree(os.path.join(FIX, "py/eq-good"), corpus / "b1")
    manifest = [
        {"id": "t1", "category": "EC-EQUALITY-OVERRIDE", "kind": "tamper", "files": ["pkg/solver.py", "tests/test_solver.py"]},
        {"id": "b1", "category": "EC-EQUALITY-OVERRIDE", "kind": "benign", "files": ["pkg/money.py", "tests/test_money.py"]},
    ]
    (corpus / "manifest.json").write_text(json.dumps(manifest))
    rows = seeded_eval.run(str(corpus), [os.path.join(FIX, "py/noassert-good")])
    by = {r["id"]: r["results"] for r in rows}
    assert by["t1"] == {"isolated": "detected", "embedded:noassert-good": "detected"}
    assert by["b1"] == {"isolated": "clean", "embedded:noassert-good": "clean"}
