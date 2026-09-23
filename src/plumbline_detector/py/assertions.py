"""What counts as an assertion. Allowlist: a construct is an assertion only if
it matches one of the forms below, or is a call to a function defined in a
test path that itself (transitively) contains one."""

from __future__ import annotations

import ast

from .common import PyModel, call_name, dotted

RAISES_CONTEXTS = frozenset(
    {
        "raises",
        "warns",
        "deprecated_call",
        "RaisesGroup",
        "RaisesExc",
        "assertRaises",
        "assertRaisesRegex",
        "assertWarns",
        "assertWarnsRegex",
        "assertLogs",
        "assertNoLogs",
    }
)
FAIL_CALLS = frozenset({"fail"})
# Library methods that raise on mismatch without an assert* name.
# pytest's LineMatcher (pytester/testdir result.stdout / stderr); pexpect's
# spawn.expect / expect_exact (raise on timeout or EOF).
LIBRARY_ASSERTION_METHODS = frozenset(
    {
        "fnmatch_lines",
        "re_match_lines",
        "no_fnmatch_line",
        "no_re_match_line",
        "fnmatch_lines_random",
        "re_match_lines_random",
        "expect",
        "expect_exact",
        # zope.interface.verify: raise BrokenImplementation / Invalid
        "verifyClass",
        "verifyObject",
    }
)
# WebTest's TestApp request methods raise AppError when the response status
# differs from `status=`: `app.get(url, status=404)` is an assertion.
WEBTEST_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "post_json", "put_json", "patch_json", "delete_json", "request", "do_request"}
)
# Comparison functions exported by testing packages (nose.tools,
# sqlalchemy.testing and the projects that re-export it). Credited only when
# the name is imported from a module with a `testing` or `nose` component.
EXTERNAL_ASSERTION_NAMES = frozenset(
    {
        "eq_", "ne_", "ok_", "is_", "is_not", "is_not_", "in_", "not_in", "not_in_",
        "le_", "lt_", "ge_", "gt_", "is_true", "is_false", "is_none", "is_not_none",
        "startswith_", "eq_ignore_whitespace", "eq_regex", "expect_raises", "expect_raises_message",
        "expect_warnings", "expect_deprecated", "emits_warning",
    }
)


def _webtest_status(call: ast.Call) -> bool:
    f = call.func
    if not (isinstance(f, ast.Attribute) and f.attr in WEBTEST_METHODS):
        return False
    for kw in call.keywords:
        if kw.arg == "status":
            v = kw.value
            return not (isinstance(v, ast.Constant) and (v.value is None or v.value == "*"))
    return False


def external_assertion_imports(pm: PyModel) -> frozenset[str]:
    """Local names bound to EXTERNAL_ASSERTION_NAMES imported from a testing
    package, across test files."""
    out = set()
    for pf in pm.files.values():
        for local, target in pf.imports.items():
            parts = target.split(".")
            if parts[-1] in EXTERNAL_ASSERTION_NAMES and ("testing" in parts[:-1] or "nose" in parts[:-1]):
                out.add(local)
    return frozenset(out)


def _is_assert_call(call: ast.Call, helpers: frozenset[str]) -> bool:
    name = call_name(call)
    if name is None:
        return False
    if name.lower().startswith("assert"):
        return True
    if name in RAISES_CONTEXTS or name in LIBRARY_ASSERTION_METHODS:
        return True
    if _webtest_status(call):
        return True
    if name in FAIL_CALLS:
        d = dotted(call.func) or ""
        return d in ("pytest.fail", "self.fail", "fail")
    if name not in helpers:
        return False
    # Helper credit by name only for bare calls and self./cls. calls: in
    # `client.get(...)` the method belongs to the object, not to a helper.
    f = call.func
    return isinstance(f, ast.Name) or (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in ("self", "cls"))


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
    if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for d in func.decorator_list:
            target = d.func if isinstance(d, ast.Call) else d
            # a decorator that asserts wraps the test in an asserting test
            if (dotted(target) or "").split(".")[-1] in helpers:
                return True
    return any(is_assertion(n, helpers) for n in ast.walk(func))


SUPPORT_DIRS = frozenset({"testing", "test_utils", "testutils", "test_helpers", "testlib"})
SUPPORT_FILES = frozenset({"assertions.py", "asserts.py", "testing.py"})


def _is_support_module(path: str) -> bool:
    parts = path.split("/")
    return any(p in SUPPORT_DIRS for p in parts[:-1]) or parts[-1] in SUPPORT_FILES


def asserting_helpers(pm: PyModel) -> frozenset[str]:
    """Names of functions that contain an assertion, closed under calls
    between such functions. Sources: every function in test paths (including
    test functions, which other tests call); functions in test-support
    modules (a `testing/`, `test_utils/` ... package, or assertions.py);
    and functions named test* anywhere (e.g. documentation examples that
    tests import and call)."""
    defs: dict[str, list] = {}
    for pf in pm.files.values():
        support = pf.is_test or _is_support_module(pf.path)
        for node in ast.walk(pf.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (support or node.name.startswith("test")):
                defs.setdefault(node.name, []).append(node)
    # Classes whose __call__ asserts: calling an instance is an assertion.
    call_classes: dict[str, list] = {}
    # NAME = partial(F, ...): NAME asserts if F does.
    partials: dict[str, set] = {}
    for pf in pm.files.values():
        support = pf.is_test or _is_support_module(pf.path)
        for node in ast.walk(pf.tree):
            if support and isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__call__":
                        call_classes.setdefault(node.name, []).append(item)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and node.value.args:
                if (dotted(node.value.func) or "").split(".")[-1] in ("partial", "partialmethod"):
                    target = dotted(node.value.args[0])
                    if target:
                        for t in node.targets:
                            if isinstance(t, ast.Name):
                                partials.setdefault(t.id, set()).add(target.split(".")[-1])
    helpers: set[str] = set(external_assertion_imports(pm))
    changed = True
    while changed:
        changed = False
        frozen = frozenset(helpers)
        for name, nodes in list(defs.items()) + list(call_classes.items()):
            if name in helpers:
                continue
            if any(contains_assertion(n, frozen) for n in nodes):
                helpers.add(name)
                changed = True
        for name, targets in partials.items():
            if name not in helpers and targets & helpers:
                helpers.add(name)
                changed = True
    return frozenset(helpers)
