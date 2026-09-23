"""The learning-loop tooling stays consistent with the checks it measures."""

import json
import os
import pathlib
import sys

from plumbline_detector.record import CHECK_ORDER

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_measurements  # noqa: E402
import study_round  # noqa: E402


def test_labeler_definitions_cover_every_check():
    d = study_round.definitions()
    for c in CHECK_ORDER:
        assert f"`{c}`" in d, c
    for label in ("**TP**", "**FP-detector**", "**FP-scope**"):
        assert label in d


def test_every_round_has_metadata_and_labels():
    meta = build_measurements.rounds_meta()
    fingerprints = json.loads((ROOT / "src/plumbline_detector/fingerprint.json").read_text())
    for n, m in meta.items():
        assert fingerprints.get(m["schema"]) == m["ruleset_fingerprint"] or n == 1  # round 1 erratum, see PRECISION_STUDY.md
        assert os.path.isfile(ROOT / f"docs/precision/round{n}/labeled_findings.jsonl")


def test_measurements_rebuild_is_current():
    """measurements.json is exactly what build_measurements.py makes from the committed labels."""
    path = ROOT / "src/plumbline_detector/measurements.json"
    before = path.read_bytes()
    build_measurements.main()
    assert path.read_bytes() == before
