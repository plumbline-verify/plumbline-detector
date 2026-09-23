"""PR mode: did this change weaken verification?

The repository checks ask whether a snapshot's evidence is real, which
requires claims about what a whole codebase lacks. PR mode compares the base
and head snapshots of one change and reports only what the change did to its
own verification. A repository's own assertion idioms (harness methods,
type-level assertions, macros) are present on both sides and cancel out.

Checks:
  PR-ASSERTIONS-REMOVED  a test present and running on both sides has fewer
                         recognized assertions on head than on base
  PR-TESTS-DISABLED      a test that runs on base is skipped, deselected,
                         ignored or turned into a todo on head
  PR-TESTS-REMOVED       tests deleted from a file (or with their file) and
                         not re-added anywhere under the same name, when the
                         file does not gain at least as many tests as it lost
  PR-TOLERANCE-LOOSENED  a test present and running on both sides has a
                         numeric tolerance or threshold in an assertion
                         moved in the looser direction (rtol raised,
                         places lowered, `assert t < N` with N raised)
  PR-TIMEOUT-RAISED      a test's timeout, a test file's timeout, or a
                         runner configuration's timeout is raised
  PR-ASSERTION-SWALLOWED a test present on both sides gains a try (or
                         suppress) whose handler catches assertion failures
                         and discards them
  PR-MOCK-UNDER-TEST     a test present on both sides newly patches a name
                         it also calls directly, or a JS test file newly
                         mocks its own subject module (sum.test.js -> ./sum)
  PR-TESTS-EXCLUDED      a runner or coverage configuration touched by the
                         change gains an exclusion: --ignore/--deselect,
                         -k/-m "not ...", testPathIgnorePatterns,
                         collect_ignore, coverage omit, and the like
  PR-NEW-TAMPERING       a repository-check finding of a tampering pattern
                         (exit before assert, constant __eq__, runner patch,
                         special-cased input, assertion that cannot fail,
                         continue-on-error on tests, skippable required gate)
                         that is new on head, in a file the change touched

A finding says what the change did, at a location in the change. It says
nothing about intent: deleting an obsolete test is a PR-TESTS-REMOVED true
positive that a reviewer may accept.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field

from . import SCHEMA_VERSION, __version__, loosen, snapshot
from .js import checks as js_checks
from .js import common as js_common
from .model import Location
from .py.assertions import asserting_helpers, is_assertion
from .py.common import is_skipped, iter_test_functions
from .record import analyze, build_models, ruleset_fingerprint

PR_CHECKS = [
    "PR-ASSERTIONS-REMOVED",
    "PR-TESTS-DISABLED",
    "PR-TESTS-REMOVED",
    "PR-TOLERANCE-LOOSENED",
    "PR-TIMEOUT-RAISED",
    "PR-ASSERTION-SWALLOWED",
    "PR-MOCK-UNDER-TEST",
    "PR-TESTS-EXCLUDED",
    "PR-NEW-TAMPERING",
]

# Repository checks whose findings are local tampering patterns: a new one in
# a touched file is something the change introduced.
TAMPER_CHECKS = frozenset(
    {
        "GT-SKIP-SATISFIES",
        "GT-CONTINUE-ON-ERROR",
        "GT-AGGREGATOR-PERMISSIVE",
        "EC-EXIT-BEFORE-ASSERT",
        "EC-EQUALITY-OVERRIDE",
        "EC-RUNNER-PATCHED",
        "EC-SPECIAL-CASED",
        "EC-ASSERTION-NONSTANDARD",
        "EC-EXIT-BEFORE-ASSERT-JS",
        "EC-RUNNER-PATCHED-JS",
        "EC-ASSERTION-NONSTANDARD-JS",
    }
)
DISABLED_KINDS = frozenset({"skipped", "deselected", "ignored"})


@dataclass(frozen=True)
class TestState:
    file: str
    line: int | None
    assertions: int
    running: bool
    profile: dict = field(default=None, compare=False)


def _py_inventory(snap) -> dict:
    """(file, class, name) -> TestState for Python tests."""
    _, _, pm, coll = build_models(snap)
    helpers = asserting_helpers(pm)
    disabled = set()
    if coll.pytest_evidence:
        for idx, (kind, _, _) in coll.not_run.items():
            if kind in DISABLED_KINDS:
                it = coll.items[idx]
                disabled.add((it.file, it.cls or "", it.name))
    out = {}
    for pf in pm.tests():
        for func, cls in iter_test_functions(pf):
            key = (pf.path, cls.name if cls else "", func.name)
            n = sum(1 for node in ast.walk(func) if is_assertion(node, helpers))
            running = not is_skipped(func) and key not in disabled
            out[key] = TestState(pf.path, func.lineno, n, running, loosen.py_profile(func, helpers))
    return out


def _js_inventory(snap, files: dict | None = None) -> dict:
    """(file, title, occurrence) -> TestState for JS/TS test cases. File-level
    loosening profiles go into `files` when given."""
    jm = js_common.build(snap)
    helpers = js_checks.asserting_helpers(jm)
    out = {}
    for jf in jm.tests():
        if files is not None:
            files[jf.path] = loosen.js_file_profile(jf)
        roots = js_checks.plan_roots(jf.root, jf.src)
        seen: dict = {}
        for tc in jf.tests:
            occ = seen.get(tc.name, 0)
            seen[tc.name] = occ + 1
            n = 0
            if tc.body is not None:
                for node in js_common.walk(tc.body):
                    if node.type == "call_expression" and js_checks._is_assertion_call(node, jf.src, helpers, None, roots):
                        n += 1
            running = tc.body is not None and not ({"skip", "todo"} & tc.modifiers)
            out[(jf.path, tc.name, str(occ))] = TestState(jf.path, tc.line, n, running, loosen.js_profile(tc, jf.src))
    return out


def _changed_files(base, head) -> set:
    paths = set(base.all_paths()) | set(head.all_paths())
    return {p for p in paths if base.files.get(p) != head.files.get(p) or (p in base.unread) != (p in head.unread)}


def _bare(key) -> str:
    """Python: the function name alone; JS: the title."""
    return key[1] if key[2].isdigit() else key[2]


_VOLATILE = re.compile(r"\[[^\]]*\]|\([^)]*\d[^)]*\)|\d+")


def _construct(message: str) -> str:
    """A finding message with its volatile parts removed: bracketed lists,
    parenthesized counts, numbers."""
    return _VOLATILE.sub("", message)


def _name(key) -> str:
    # Python keys: (file, class, name); JS keys: (file, title, occurrence)
    if key[2].isdigit():
        return key[1]
    return f"{key[1]}.{key[2]}" if key[1] else key[2]


def _compare_profiles(key, b: TestState, h: TestState, add) -> None:
    pb, ph = b.profile, h.profile
    if pb is None or ph is None:
        return
    name = _name(key)
    for kind, old, new in loosen.loosened(pb["bounds"], ph["bounds"]):
        add("PR-TOLERANCE-LOOSENED", Location(h.file, h.line, f"test {name}: {kind} {loosen.fmt(old)} -> {loosen.fmt(new)}", {"kind": kind, "before": old, "after": new}))
    for kind, old, new in loosen.loosened(pb["timeouts"], ph["timeouts"]):
        add("PR-TIMEOUT-RAISED", Location(h.file, h.line, f"test {name}: {kind} {loosen.fmt(old)} -> {loosen.fmt(new)}", {"kind": kind, "before": old, "after": new}))
    if ph["swallowed"] > pb["swallowed"]:
        add("PR-ASSERTION-SWALLOWED", Location(h.file, h.line, f"test {name}: assertion failures caught and discarded ({pb['swallowed']} -> {ph['swallowed']})", {"before": pb["swallowed"], "after": ph["swallowed"]}))
    for target in sorted(ph["mocks"] - pb["mocks"]):
        add("PR-MOCK-UNDER-TEST", Location(h.file, h.line, f"test {name}: now patches {target} and calls it directly", {"target": target}))


def compare(base_dir: str, head_dir: str) -> dict:
    """The PR record for base -> head."""
    base, head = snapshot.load(base_dir), snapshot.load(head_dir)
    changed = _changed_files(base, head)
    results = {c: {"findings": [], "unknowns": []} for c in PR_CHECKS}

    jsf_base, jsf_head = {}, {}
    inv_base = _py_inventory(base) | _js_inventory(base, jsf_base)
    inv_head = _py_inventory(head) | _js_inventory(head, jsf_head)

    def add(check, loc):
        results[check]["findings"].append(loc)

    for key in sorted(set(inv_base) & set(inv_head)):
        b, h = inv_base[key], inv_head[key]
        if b.running and h.running and h.file in changed:
            _compare_profiles(key, b, h, add)
        if b.running and h.running and h.assertions < b.assertions:
            results["PR-ASSERTIONS-REMOVED"]["findings"].append(
                Location(h.file, h.line, f"test {_name(key)}: recognized assertions {b.assertions} -> {h.assertions}", {"before": b.assertions, "after": h.assertions})
            )
        if b.running and not h.running:
            results["PR-TESTS-DISABLED"]["findings"].append(Location(h.file, h.line, f"test {_name(key)} ran before this change and does not run after it"))

    # a test re-added anywhere under the same function name (whatever its
    # class or file) was moved, not removed
    head_names = {_name(k) for k in inv_head} | {_bare(k) for k in inv_head}
    by_file: dict = {}
    for key in set(inv_base) - set(inv_head):
        if inv_base[key].running and _name(key) not in head_names and _bare(key) not in head_names:
            by_file.setdefault(key[0], []).append(key)
    for file, keys in sorted(by_file.items()):
        added = [k for k in set(inv_head) - set(inv_base) if k[0] == file]
        if len(keys) > len(added):
            names = sorted(_name(k) for k in keys)
            gone = "" if file in head.files else " (file deleted)"
            results["PR-TESTS-REMOVED"]["findings"].append(
                Location(file, None, f"{len(keys)} test(s) removed{gone} and not re-added elsewhere: {', '.join(names[:5])}{' …' if len(names) > 5 else ''}", {"tests": names[:20], "added_in_file": len(added)})
            )

    for path in sorted(set(jsf_base) & set(jsf_head) & changed):
        fb, fh = jsf_base[path], jsf_head[path]
        for kind, old, new in loosen.loosened(fb["timeouts"], fh["timeouts"]):
            add("PR-TIMEOUT-RAISED", Location(path, None, f"{kind}: {loosen.fmt(old)} -> {loosen.fmt(new)}", {"kind": kind, "before": old, "after": new}))
        for target in sorted(fh["mocks"] - fb["mocks"]):
            add("PR-MOCK-UNDER-TEST", Location(path, None, f"test file now mocks its own subject module {target}", {"target": target}))

    for path in sorted(changed):
        cb = loosen.config_profile(path, base.files[path]) if path in base.files else None
        ch = loosen.config_profile(path, head.files[path]) if path in head.files else None
        if ch is None:
            continue
        for key, tok in sorted(ch["exclusions"] - (cb["exclusions"] if cb else frozenset())):
            add("PR-TESTS-EXCLUDED", Location(path, None, f"adds exclusion {key} {tok}", {"key": key, "token": tok}))
        if cb is not None:
            for kind, old, new in loosen.loosened(cb["timeouts"], ch["timeouts"]):
                add("PR-TIMEOUT-RAISED", Location(path, None, f"configured {kind}: {loosen.fmt(old)} -> {loosen.fmt(new)}", {"kind": kind, "before": old, "after": new}))

    rec_base, rec_head = analyze(base_dir), analyze(head_dir)
    # "new" is decided by construct identity, not by message text: counts
    # (matrix legs) and lists (an aggregator's needs) in a message change
    # when the construct itself was already there
    before = {(c["id"], f["file"], _construct(f["message"])) for c in rec_base["checks"] for f in c["findings"]}
    for c in rec_head["checks"]:
        if c["id"] not in TAMPER_CHECKS:
            continue
        for f in c["findings"]:
            if (c["id"], f["file"], _construct(f["message"])) not in before and f["file"] in changed:
                results["PR-NEW-TAMPERING"]["findings"].append(Location(f["file"], f["line"], f"{c['id']}: {f['message']}", {"check": c["id"]}))

    checks = []
    for c in PR_CHECKS:
        fs = sorted(results[c]["findings"], key=lambda l: (l.file, l.line or 0, l.message))
        checks.append({"id": c, "verdict": "FAIL" if fs else "PASS", "findings": [f.to_json(c) for f in fs]})
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "pr",
        "tool": {"name": "plumbline-detector", "version": __version__},
        "provenance": {
            "ruleset_fingerprint": ruleset_fingerprint(),
            "base_content_id": base.content_id(),
            "head_content_id": head.content_id(),
            "files_changed": len(changed),
        },
        "summary": {"FAIL": sum(1 for c in checks if c["verdict"] == "FAIL"), "findings": sum(len(c["findings"]) for c in checks)},
        "checks": checks,
    }


def dumps(record: dict) -> str:
    return json.dumps(record, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def to_markdown(record: dict) -> str:
    """A pull-request comment."""
    n = record["summary"]["findings"]
    if not n:
        return "**Plumbline: no verification weakening found in this change.**\n"
    out = [f"**Plumbline: this change weakens verification ({n} finding{'s' if n != 1 else ''}).**", ""]
    for c in record["checks"]:
        for f in c["findings"]:
            where = f"{f['file']}:{f['line']}" if f.get("line") else f["file"]
            out.append(f"- `{c['id']}` {where}: {f['message']}")
    out += ["", "A finding says what the change did, not why. Removing an obsolete test is a finding a reviewer may accept."]
    return "\n".join(out) + "\n"

