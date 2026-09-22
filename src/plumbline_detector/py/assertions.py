"""What counts as an assertion. Allowlist: a construct is an assertion only if
it matches one of the forms below, or is a call to a function defined in a
test path that itself (transitively) contains one."""

from __future__ import annotations

import ast

from .common import PyModel, call_name, dotted

RAISES_CONTEXTS = frozenset({"raises", "warns", "deprecated_call", "assertRaises", "assertRaisesRegex", "assertWarns", "assertWarnsRegex", "assertLogs", "assertNoLogs"})
FAIL_CALLS = frozenset({"fail"})


def _is_assert_call(call: ast.Call, helpers: frozenset[str]) -> bool:
    name = call_name(call)
    if name is None:
        return False
    if name.lower().startswith("assert"):
        return True
    if name in RAISES_CONTEXTS:
        return True
    if name in FAIL_CALLS:
        d = dotted(call.func) or ""
        return d in ("pytest.fail", "self.fail", "fail")
    return name in helpers


def is_assertion(node, helpers: frozenset[str] = frozenset()) -> bool:
    if isinstance(node, ast.Assert):
        return True
    if isinstance(node, ast.Call):
        return _is_assert_call(node, helpers)
    if isinstance(node, ast.Raise) and node.exc is not None:
        exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        return (dotted(exc) or "").split(".")[-1] == "AssertionError"
    return False


def contains_assertion(func, helpers: frozenset[str] = frozenset()) -> bool:
    return any(is_assertion(n, helpers) for n in ast.walk(func))


def asserting_helpers(pm: PyModel) -> frozenset[str]:
    """Names of functions defined in test paths that contain an assertion,
    closed under calls between such functions."""
    defs: dict[str, list] = {}
    for pf in pm.tests():
        for node in ast.walk(pf.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("test"):
                defs.setdefault(node.name, []).append(node)
    helpers: set[str] = set()
    changed = True
    while changed:
        changed = False
        frozen = frozenset(helpers)
        for name, nodes in defs.items():
            if name in helpers:
                continue
            if any(contains_assertion(n, frozen) for n in nodes):
                helpers.add(name)
                changed = True
    return frozenset(helpers)
