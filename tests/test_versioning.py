"""A change to any check must bump SCHEMA_VERSION.

fingerprint.json maps each released schema version to the ruleset
fingerprint (hash of all check-defining source). If check code changes, the
computed fingerprint no longer matches the entry for the current version and
this test fails until the version is bumped and a new entry appended.
Existing entries are never edited: versions are unique and ordered, and no
fingerprint is reused under two versions."""

import json
from importlib import resources

from plumbline_detector import SCHEMA_VERSION
from plumbline_detector.record import ruleset_fingerprint


def _history():
    return json.loads(resources.files("plumbline_detector").joinpath("fingerprint.json").read_text())


def test_current_version_pinned_to_current_code():
    hist = _history()
    assert SCHEMA_VERSION in hist, f"no fingerprint recorded for schema {SCHEMA_VERSION}"
    assert hist[SCHEMA_VERSION] == ruleset_fingerprint(), (
        "check code changed without a schema version bump: bump SCHEMA_VERSION, "
        "append the new fingerprint to fingerprint.json, and update schema/record.schema.json"
    )


def test_history_is_append_only_shape():
    hist = _history()
    versions = list(hist)
    key = lambda v: tuple(int(x) for x in v.split("."))
    assert versions == sorted(versions, key=key)
    assert versions[-1] == SCHEMA_VERSION
    assert len(set(hist.values())) == len(hist)
