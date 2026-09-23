"""Loosening: verification that stays in place but checks less.

The removal checks in PR mode see assertions deleted, tests skipped and
tests removed. They miss a change that keeps every assertion and makes it
easier to pass. This module extracts, per test and per configuration file,
the parts of verification that can be loosened without being removed:

  bounds      numeric tolerances and thresholds inside assertions
              (rtol/atol/delta/places, assert x < N, toBeLessThan(N), ...)
  timeouts    per-test and configured test timeouts
  swallowed   assertions inside a try whose handler discards the failure
  mocks       names a test patches and also calls directly: the test
              exercises its own replacement, not the code
  exclusions  paths, node ids and expressions a runner configuration
              removes from collection or from coverage

Each item carries a direction: whether a larger value checks less (+1) or a
smaller one does (-1). PR mode compares base and head and reports only a
move in the looser direction. A finding says what the change did; a
threshold relaxed because the specification changed is still a relaxed
threshold, and a reviewer may accept it.
"""

from __future__ import annotations

import ast
import re
from pathlib import PurePosixPath

from .js import common as js_common
from .py.assertions import is_assertion
from .py.common import call_name, dotted

# --- numbers -----------------------------------------------------------------

_PY_OPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: a**b}


def py_number(node):
    """A numeric literal, or constant arithmetic over literals (60 * 1000,
    10 ** -6); None for anything else."""
    try:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = py_number(node.operand)
            return None if v is None else (-v if isinstance(node.op, ast.USub) else v)
        if isinstance(node, ast.BinOp) and type(node.op) in _PY_OPS:
            a, b = py_number(node.left), py_number(node.right)
            if a is None or b is None or (isinstance(node.op, ast.Pow) and abs(b) > 64):
                return None
            return float(_PY_OPS[type(node.op)](a, b))
    except (ArithmeticError, ValueError):
        return None
    return None


def js_number(node, src):
    if node is None:
        return None
    t = node.type
    try:
        if t == "number":
            s = js_common.text(node, src).replace("_", "").rstrip("n")
            return float(int(s, 0)) if s[:2].lower() in ("0x", "0o", "0b") else float(s)
        if t == "parenthesized_expression" and node.named_children:
            return js_number(node.named_children[0], src)
        if t == "unary_expression":
            op = node.children[0].type
            v = js_number(node.child_by_field_name("argument"), src)
            return None if v is None or op not in ("-", "+") else (-v if op == "-" else v)
        if t == "binary_expression":
            op = node.child_by_field_name("operator").type
            a, b = js_number(node.child_by_field_name("left"), src), js_number(node.child_by_field_name("right"), src)
            if a is None or b is None:
                return None
            if op == "*":
                return a * b
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "/":
                return a / b
            if op == "**" and abs(b) <= 64:
                return a**b
    except (ArithmeticError, ValueError):
        return None
    return None


# --- Python per-test profile -------------------------------------------------

TOL_UP = frozenset({"rtol", "atol", "rel", "abs", "delta", "tol", "tolerance", "epsilon", "eps", "max_diff", "rel_tol", "abs_tol"})
TOL_DOWN = frozenset({"places", "decimal", "significant", "digits"})
_UPPER_ASSERTS = {"assertLess": 1, "assertLessEqual": 1}
_LOWER_ASSERTS = {"assertGreater": 1, "assertGreaterEqual": 1}
_CMP_UP = (ast.Lt, ast.LtE)  # x < N: a larger N checks less
_CMP_DOWN = (ast.Gt, ast.GtE)  # x > N: a smaller N checks less
_BROAD = frozenset({"AssertionError", "Exception", "BaseException"})
_PATCHERS = frozenset({"patch", "setattr", "object"})


def _last(name):
    return (name or "").split(".")[-1]


def _handler_catches_assertion(h: ast.ExceptHandler) -> bool:
    if h.type is None:
        return True
    types = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    return any(_last(dotted(t)) in _BROAD for t in types)


def _discards(body, helpers) -> bool:
    """A handler body that neither re-raises nor checks anything."""
    for node in (n for stmt in body for n in ast.walk(stmt)):
        if isinstance(node, ast.Raise) or is_assertion(node, helpers):
            return False
        if isinstance(node, ast.Call) and _last(call_name(node)) in ("fail", "skip", "xfail"):
            return False
    return True


def _has_assertion(nodes, helpers) -> bool:
    return any(is_assertion(n, helpers) for stmt in nodes for n in ast.walk(stmt))


def _patch_target(call: ast.Call):
    """The attribute name a patch call replaces, or None.
    patch("a.b.f") / mocker.patch("a.b.f") / monkeypatch.setattr("a.b.f", v)
    -> "f"; patch.object(X, "f") / monkeypatch.setattr(X, "f", v) -> "f"."""
    name = call_name(call) or ""
    parts = name.split(".")
    if parts[-1] not in _PATCHERS or (parts[-1] == "object" and (len(parts) < 2 or parts[-2] != "patch")):
        return None
    if parts[-1] == "setattr" and not (len(parts) >= 2 and parts[-2] == "monkeypatch"):
        return None
    args = call.args
    if not args or any(kw.arg == "wraps" for kw in call.keywords):  # a spy that calls through
        return None
    first = args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        if parts[-1] == "object":
            return None
        return first.value.rsplit(".", 1)[-1] if "." in first.value else None
    if len(args) >= 2 and isinstance(args[1], ast.Constant) and isinstance(args[1].value, str):
        return args[1].value
    return None


def py_profile(func, helpers) -> dict:
    bounds, timeouts, swallowed = [], [], 0
    targets, called = set(), set()
    for d in func.decorator_list:
        if isinstance(d, ast.Call):
            dn = dotted(d.func) or ""
            if dn.endswith("mark.timeout") and d.args and py_number(d.args[0]) is not None:
                timeouts.append(("mark.timeout", py_number(d.args[0]), 1))
            for kw in d.keywords:
                if dn.split(".")[-1] == "settings" and kw.arg == "deadline" and py_number(kw.value) is not None:
                    timeouts.append(("hypothesis.deadline", py_number(kw.value), 1))
                if kw.arg == "timeout" and dn.endswith("mark.timeout") and py_number(kw.value) is not None:
                    timeouts.append(("mark.timeout", py_number(kw.value), 1))
            t = _patch_target(d)
            if t:
                targets.add(t)
    for node in (n for stmt in func.body for n in ast.walk(stmt)):
        if isinstance(node, ast.Call):
            cn = call_name(node) or ""
            last = _last(cn)
            t = _patch_target(node)
            if t:
                targets.add(t)
            for kw in node.keywords:
                v = py_number(kw.value)
                if v is None:
                    continue
                if kw.arg in TOL_UP:
                    bounds.append((f"{kw.arg}@{last}", v, 1))
                elif kw.arg in TOL_DOWN:
                    bounds.append((f"{kw.arg}@{last}", v, -1))
                elif kw.arg == "timeout":
                    timeouts.append((f"timeout@{last}", v, 1))
            if last in ("assertAlmostEqual", "assertNotAlmostEqual") and len(node.args) >= 3 and py_number(node.args[2]) is not None:
                bounds.append((f"places@{last}", py_number(node.args[2]), -1 if last == "assertAlmostEqual" else 1))
            for table, sense in ((_UPPER_ASSERTS, 1), (_LOWER_ASSERTS, -1)):
                if last in table and len(node.args) > table[last] and py_number(node.args[table[last]]) is not None:
                    bounds.append((f"arg@{last}", py_number(node.args[table[last]]), sense))
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
        elif isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            cmp = node.test
            items = [cmp.left, *cmp.comparators]
            for i, op in enumerate(cmp.ops):
                left, right = items[i], items[i + 1]
                rv, lv = py_number(right), py_number(left)
                if rv is not None and lv is None:
                    if isinstance(op, _CMP_UP):
                        bounds.append((f"assert<{i}", rv, 1))
                    elif isinstance(op, _CMP_DOWN):
                        bounds.append((f"assert>{i}", rv, -1))
                elif lv is not None and rv is None:
                    if isinstance(op, _CMP_UP):  # N < x: lower bound
                        bounds.append((f"assert>{i}", lv, -1))
                    elif isinstance(op, _CMP_DOWN):  # N > x: upper bound
                        bounds.append((f"assert<{i}", lv, 1))
        elif isinstance(node, ast.Try):
            if _has_assertion(node.body, helpers) and any(_handler_catches_assertion(h) and _discards(h.body, helpers) for h in node.handlers):
                swallowed += 1
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                ce = item.context_expr
                if isinstance(ce, ast.Call) and _last(call_name(ce)) == "suppress" and any(_last(dotted(a)) in _BROAD for a in ce.args):
                    if _has_assertion(node.body, helpers):
                        swallowed += 1
    # a target counts only when the test also calls it directly, outside
    # the patch itself: the test then exercises its own replacement
    mocks = targets & called
    return {"bounds": bounds, "timeouts": timeouts, "swallowed": swallowed, "mocks": frozenset(mocks)}


# --- JS per-test profile -----------------------------------------------------

JS_UP = frozenset({"toBeLessThan", "toBeLessThanOrEqual", "below", "lessThan", "most", "lte", "lt", "isBelow", "isAtMost"})
JS_DOWN = frozenset({"toBeGreaterThan", "toBeGreaterThanOrEqual", "above", "greaterThan", "least", "gte", "gt", "isAbove", "isAtLeast"})
_JS_ASSERT_HEADS = frozenset({"expect", "assert", "should", "expectTypeOf", "t"})


def _member_prop(fn, src):
    if fn is not None and fn.type == "member_expression":
        p = fn.child_by_field_name("property")
        return js_common.text(p, src) if p is not None else None
    if fn is not None and fn.type == "identifier":
        return js_common.text(fn, src)
    return None


def _args(call):
    a = call.child_by_field_name("arguments")
    return a.named_children if a is not None else []


def _root_ident(fn, src):
    while fn is not None:
        if fn.type == "identifier":
            return js_common.text(fn, src)
        if fn.type == "member_expression":
            fn = fn.child_by_field_name("object")
        elif fn.type == "call_expression":
            fn = fn.child_by_field_name("function")
        else:
            return None
    return None


def _is_js_assertion(call, src) -> bool:
    return _root_ident(call.child_by_field_name("function"), src) in _JS_ASSERT_HEADS


def _js_timeout_arg(node, src):
    """{timeout: N} / {testTimeout: N} in an object literal."""
    if node.type != "object":
        return None
    for pair in node.named_children:
        if pair.type == "pair":
            k = js_common.text(pair.child_by_field_name("key"), src).strip("'\"")
            if k in ("timeout", "testTimeout"):
                return js_number(pair.child_by_field_name("value"), src)
    return None


def js_profile(tc, src) -> dict:
    bounds, timeouts, swallowed = [], [], 0
    mocks = set()
    # timeout given to the test call itself: it(title, fn, 5000) / test(title, {timeout}, fn)
    for a in _args(tc.call)[1:]:
        v = js_number(a, src) if a.type in ("number", "binary_expression") else _js_timeout_arg(a, src)
        if v is not None:
            timeouts.append(("test-arg", v, 1))
    if tc.body is None:
        return {"bounds": bounds, "timeouts": timeouts, "swallowed": 0, "mocks": frozenset()}
    spied, called = set(), set()
    for node in js_common.walk(tc.body):
        if node.type == "call_expression":
            fn = node.child_by_field_name("function")
            prop = _member_prop(fn, src)
            args = _args(node)
            if prop in JS_UP or prop in JS_DOWN:
                # expect(x).toBeLessThan(N): N is the first argument;
                # assert.isBelow(x, N): the second
                idx = 1 if prop.startswith("is") else 0
                if len(args) > idx and js_number(args[idx], src) is not None:
                    bounds.append((f"{prop}", js_number(args[idx], src), 1 if prop in JS_UP else -1))
            elif prop == "toBeCloseTo" and len(args) >= 2 and js_number(args[1], src) is not None:
                bounds.append(("toBeCloseTo.digits", js_number(args[1], src), -1))
            elif prop in ("closeTo", "approximately"):
                idx = 2 if _root_ident(fn, src) == "assert" else 1
                if len(args) > idx and js_number(args[idx], src) is not None:
                    bounds.append((f"{prop}.delta", js_number(args[idx], src), 1))
            elif prop in ("timeout", "setTimeout") and _root_ident(fn, src) in ("this", "jest") and args and js_number(args[0], src) is not None:
                timeouts.append((f"{_root_ident(fn, src)}.{prop}", js_number(args[0], src), 1))
            elif prop == "setConfig" and args:
                v = _js_timeout_arg(args[0], src)
                if v is not None:
                    timeouts.append(("setConfig.testTimeout", v, 1))
            elif prop == "spyOn" and len(args) >= 2 and args[1].type == "string":
                # spyOn(obj, "f") replaced only when chained into a mock
                parent = node.parent
                if parent is not None and parent.type == "member_expression":
                    chained = _member_prop(parent, src) or ""
                    if chained.startswith("mock"):
                        spied.add(js_common.text(args[1], src).strip("'\"`"))
            if prop is not None and not _is_js_assertion(node, src):
                called.add(prop)
        elif node.type == "try_statement":
            block = node.child_by_field_name("body")
            handler = node.child_by_field_name("handler")
            if block is None or handler is None:
                continue
            has_assert = any(n.type == "call_expression" and _is_js_assertion(n, src) for n in js_common.walk(block))
            hbody = handler.child_by_field_name("body")
            rethrows = hbody is not None and any(
                n.type == "throw_statement" or (n.type == "call_expression" and (_is_js_assertion(n, src) or _member_prop(n.child_by_field_name("function"), src) == "fail"))
                for n in js_common.walk(hbody)
            )
            if has_assert and not rethrows:
                swallowed += 1
    mocks = {s for s in spied if s in called}
    return {"bounds": bounds, "timeouts": timeouts, "swallowed": swallowed, "mocks": frozenset(mocks)}


def _test_stem(path: str) -> str:
    name = PurePosixPath(path).name
    name = re.sub(r"\.(c|m)?[jt]sx?$", "", name)
    return re.sub(r"[._-](test|spec)$", "", name)


def js_file_profile(jf) -> dict:
    """File-level: top-level timeouts, and module mocks of the test's own
    subject (sum.test.js mocking ./sum)."""
    src = jf.src
    timeouts, mocks = [], set()
    stem = _test_stem(jf.path)
    for node in js_common.walk(jf.root):
        if node.type != "call_expression":
            continue
        fn = node.child_by_field_name("function")
        prop, root = _member_prop(fn, src), _root_ident(fn, src)
        args = _args(node)
        if root in ("jest", "vi") and prop in ("mock", "doMock") and args and args[0].type == "string":
            target = js_common.text(args[0], src).strip("'\"`")
            if target.startswith(".") and _test_stem(target) == stem:
                mocks.add(target)
        elif root == "jest" and prop == "setTimeout" and args and js_number(args[0], src) is not None:
            timeouts.append(("jest.setTimeout", js_number(args[0], src), 1))
    return {"timeouts": timeouts, "mocks": frozenset(mocks)}


# --- configuration -----------------------------------------------------------

PY_CFG = frozenset({"pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml", ".coveragerc", "conftest.py", "noxfile.py"})
_JS_CFG = re.compile(r"^((jest|vitest|karma|playwright|ava)\.config\.[cm]?[jt]s|(jest|vitest)\.config\.json|package\.json|\.mocharc(\.[a-z]+)?)$")
_RUNNER_FILE = re.compile(r"(^|/)(\.github/workflows/[^/]+\.ya?ml|Makefile|justfile|[^/]*\.sh)$")
_RUNNER_WORD = re.compile(r"\b(pytest|py\.test|tox|nox|mocha|jest|vitest|ava)\b")
_FLAG = re.compile(r"(--ignore(?:-glob)?|--deselect|--testPathIgnorePatterns|--exclude)(?:=|\s+)(['\"]?)([^\s'\"]+)\2")
_EXPR = re.compile(r"(?<![\w-])(-k|-m)\s*(?:=\s*)?(['\"])(.*?)\2")
_TIMEOUT_FLAG = re.compile(r"--timeout(?:=|\s+)(\d+(?:\.\d+)?)")
_LIST_KEYS = {
    "testPathIgnorePatterns": "js",
    "modulePathIgnorePatterns": "js",
    "coveragePathIgnorePatterns": "js",
    "testIgnore": "js",
    "exclude": "vitest",
    "collect_ignore": "py",
    "collect_ignore_glob": "py",
    "norecursedirs": "py",
    "omit": "cov",
    "exclude_lines": "cov",
    "exclude_also": "cov",
}
_DEFAULTS = re.compile(r"node_modules|(^|[/*])\.git\b|\bvenv\b|\.venv|\.tox|__pycache__|(^|/)(dist|build|out|coverage|site-packages)(/|$)|\.eggs?\b|\.nox")
_INI_KV = re.compile(r"^\s*(timeout)\s*=\s*(\d+(?:\.\d+)?)\s*$", re.M)
_JS_TIMEOUT_KV = re.compile(r"[\"']?(testTimeout|hookTimeout|timeout)[\"']?\s*:\s*(\d[\d_]*(?:\s*\*\s*\d[\d_]*)*)")


def _config_kind(path: str) -> str | None:
    name = PurePosixPath(path).name
    if name in PY_CFG:
        return "py"
    if _JS_CFG.match(name):
        return "js"
    if _RUNNER_FILE.search(path):
        return "runner"
    return None


def _value_region(text: str, start: int) -> str:
    """The value that follows `key =` / `key:` at `start`: a bracketed list,
    or the rest of the line and its indented continuation lines (INI)."""
    i = start
    while i < len(text) and text[i] in " \t":
        i += 1
    if i < len(text) and text[i] in "[(":
        depth, j = 0, i
        while j < len(text):
            if text[j] in "[(":
                depth += 1
            elif text[j] in "])":
                depth -= 1
                if depth == 0:
                    return text[i : j + 1]
            j += 1
        return text[i:]
    end = text.find("\n", i)
    end = len(text) if end < 0 else end
    region = text[i:end]
    for line in text[end + 1 :].split("\n"):
        if line[:1] in (" ", "\t") and line.strip():
            region += "\n" + line
        else:
            break
    return region


def _tokens(region: str) -> list:
    quoted = re.findall(r"(['\"])(.*?)\1", region)
    if quoted:
        return [q for _, q in quoted]
    return [t for t in re.split(r"[\s,\[\]]+", region) if t]


def _is_pytest_section(text: str, pos: int, name: str) -> bool:
    """INI and TOML: is `pos` inside a pytest (or coverage, for coverage
    keys) section? Other files have no sections."""
    if name not in ("tox.ini", "setup.cfg", "pyproject.toml", "pytest.ini", ".coveragerc"):
        return True
    heads = list(re.finditer(r"^\s*\[([^\]]+)\]", text[:pos], re.M))
    if not heads:
        return name in ("pytest.ini", ".coveragerc")
    sec = heads[-1].group(1).strip().lower()
    return sec in ("pytest", "tool:pytest", "tool.pytest.ini_options", "tool.pytest") or "coverage" in sec or name == "pytest.ini"


def config_profile(path: str, data: bytes) -> dict:
    """{"exclusions": set of (key, token), "timeouts": [(key, value, 1)]}."""
    kind = _config_kind(path)
    if kind is None:
        return {"exclusions": frozenset(), "timeouts": []}
    text = data.decode("utf-8", "replace")
    name = PurePosixPath(path).name
    excl, timeouts = set(), []
    lines = text.split("\n")
    for ln in lines:
        if kind == "runner" and not _RUNNER_WORD.search(ln):
            continue
        if kind == "js" and name == "package.json" and not _RUNNER_WORD.search(ln):
            continue
        for m in _FLAG.finditer(ln):
            excl.add((m.group(1), m.group(3)))
        for m in _EXPR.finditer(ln):
            # only negated terms deselect: -k "not slow and not flaky"
            for term in re.split(r"\s+and\s+", m.group(3)):
                term = term.strip().strip("()")
                if term.startswith("not "):
                    excl.add((m.group(1), term))
        for m in _TIMEOUT_FLAG.finditer(ln):
            timeouts.append(("--timeout", float(m.group(1)), 1))
    if kind == "runner":
        return {"exclusions": frozenset(t for t in excl if not _DEFAULTS.search(t[1])), "timeouts": timeouts}
    for key, scope in _LIST_KEYS.items():
        if scope == "vitest" and not name.startswith("vitest.config"):
            continue
        if scope == "js" and kind != "js":
            continue
        if scope in ("py", "cov") and kind != "py":
            continue
        for m in re.finditer(r"(?<![\w.])[\"']?" + re.escape(key) + r"[\"']?\s*[:=]\s*", text):
            if kind == "py" and not _is_pytest_section(text, m.start(), name) and name != "conftest.py":
                continue
            for tok in _tokens(_value_region(text, m.end())):
                excl.add((key, tok))
    if kind == "py":
        for m in _INI_KV.finditer(text):
            if _is_pytest_section(text, m.start(), name):
                timeouts.append(("timeout", float(m.group(2)), 1))
    else:
        for m in _JS_TIMEOUT_KV.finditer(text):
            try:
                v = 1.0
                for part in m.group(2).replace("_", "").split("*"):
                    v *= float(part.strip())
            except ValueError:
                continue
            timeouts.append((m.group(1), v, 1))
    return {"exclusions": frozenset(t for t in excl if not _DEFAULTS.search(t[1])), "timeouts": timeouts}


# --- comparison --------------------------------------------------------------


def loosened(before: list, after: list) -> list:
    """Pairs (kind, old, new) that moved in the looser direction. Items are
    compared in order within a kind, and only when the kind occurs the same
    number of times on both sides: an added or removed assertion is not a
    changed one."""
    by_b, by_a = {}, {}
    for k, v, s in before:
        by_b.setdefault((k, s), []).append(v)
    for k, v, s in after:
        by_a.setdefault((k, s), []).append(v)
    out = []
    for (k, s), vb in sorted(by_b.items()):
        va = by_a.get((k, s))
        if va is None or len(va) != len(vb):
            continue
        for old, new in zip(vb, va):
            if (new - old) * s > 0:
                out.append((k, old, new))
    return out


def fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() and abs(v) < 1e15 else f"{v:g}"
