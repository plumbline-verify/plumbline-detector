"""Evidence-channel checks for JavaScript / TypeScript tests.

The same failure modes as the Python checks, for jest, vitest, mocha (with
chai), jasmine, node:test, playwright and cypress. Check IDs carry a -JS
suffix: their precision is measured separately from the Python checks.
"""

from __future__ import annotations

import re

from ..model import CheckResult, Location
from .common import JSModel, framework_for, local_definitions, text, walk

NO_JS_TESTS = "no JS/TS test files found (*.test.*, *.spec.*, *.cy.*, __tests__/, test/ with it()/test() cases)"

# Calls whose root identifier makes an assertion.
ASSERT_ROOTS = frozenset({"expect", "assert", "expectTypeOf", "assertType", "should"})
# Member names that assert when called on any object: chai/should/sinon/node:test/ava
# style (t.is, t.deepEqual ...), plus cypress `.should(...)`.
ASSERT_METHODS = frozenset(
    {
        "should", "is", "not", "deepEqual", "notDeepEqual", "equal", "notEqual", "strictEqual", "notStrictEqual",
        "deepStrictEqual", "notDeepStrictEqual", "ok", "true", "false", "truthy", "falsy", "throws", "throwsAsync",
        "notThrows", "notThrowsAsync", "rejects", "doesNotThrow", "doesNotReject", "match", "doesNotMatch",
        "snapshot", "assert", "fail", "regex", "like", "calledWith", "calledOnce", "verify",
    }
)
# Queries that throw when nothing matches (testing-library getBy*/findBy*,
# cypress cy.contains): an implicit existence assertion.
THROWING_QUERY_RE = re.compile(r"^(getBy|getAllBy|findBy|findAllBy)[A-Z]")
# Matchers whose result depends only on their operands: literal vs literal is
# decided before the test runs. Matchers that inspect outside state
# (toHaveBeenWarned, toHaveBeenCalled ...) are excluded.
PURE_MATCHERS = frozenset(
    {"toBe", "toEqual", "toStrictEqual", "toBeTruthy", "toBeFalsy", "toBeDefined", "toBeUndefined", "toBeNull",
     "toBeNaN", "toBeGreaterThan", "toBeGreaterThanOrEqual", "toBeLessThan", "toBeLessThanOrEqual", "toBeCloseTo",
     "toContain", "toMatch", "toHaveLength"}
)
JEST_MATCHER_RE = re.compile(r"^(to[A-Z]\w*|resolves|rejects|not)$")


def _root_identifier(node, src):
    while node is not None and node.type in ("member_expression", "call_expression", "await_expression", "parenthesized_expression", "subscript_expression"):
        if node.type == "call_expression":
            node = node.child_by_field_name("function")
        elif node.type == "member_expression":
            node = node.child_by_field_name("object")
        elif node.type == "subscript_expression":
            node = node.child_by_field_name("object")
        else:
            node = node.named_children[0] if node.named_children else None
    return text(node, src) if node is not None and node.type == "identifier" else None


def _is_assertion_call(call, src, helpers, t_param):
    fn = call.child_by_field_name("function")
    root = _root_identifier(fn, src)
    if root in ASSERT_ROOTS or root in helpers:
        return True
    args = call.child_by_field_name("arguments")
    # an asserting function handed to a runner: runWith(checkOutput)
    if args is not None and any(a.type == "identifier" and text(a, src) in helpers for a in args.named_children):
        return True
    if fn is not None and fn.type == "member_expression":
        prop = text(fn.child_by_field_name("property"), src)
        obj_root = root
        if prop in ASSERT_METHODS and (obj_root in ("t", "assert", "sinon", "td", "cy", t_param) or prop == "should"):
            return True
        # supertest / superagent chains: request(app).get("/").expect(200)
        if prop == "expect":
            return True
        if THROWING_QUERY_RE.match(prop) or (obj_root == "cy" and prop == "contains"):
            return True
    if fn is not None and fn.type == "identifier" and THROWING_QUERY_RE.match(text(fn, src)):
        return True
    return False


def _has_assertion(node, src, helpers, t_param=None) -> bool:
    for n in walk(node):
        if n.type == "call_expression" and _is_assertion_call(n, src, helpers, t_param):
            return True
        # chai property assertions: expect(x).to.be.true ; x.should.exist
        if n.type == "member_expression" and text(n.child_by_field_name("property"), src) == "should":
            return True
        if n.type == "throw_statement":
            return True
    return False


def _first_param(fn, src):
    params = fn.child_by_field_name("parameters") or fn.child_by_field_name("parameter")
    if params is None:
        return None
    if params.type == "identifier":
        return text(params, src)
    for p in params.named_children:
        if p.type in ("identifier", "required_parameter"):
            return text(p, src).split(":")[0].strip()
    return None


def asserting_helpers(jm: JSModel) -> frozenset:
    """Names of functions defined in JS/TS test-like files that assert,
    closed under calls between them."""
    defs: dict[str, list] = {}
    aliases: dict[str, set] = {}
    for jf in list(jm.files.values()) + list(jm.support.values()):
        for n in walk(jf.root):
            name, body = None, None
            if n.type == "function_declaration":
                name, body = text(n.child_by_field_name("name"), jf.src), n
            elif n.type == "variable_declarator":
                v = n.child_by_field_name("value")
                if v is not None and v.type in ("arrow_function", "function_expression", "function"):
                    name, body = text(n.child_by_field_name("name"), jf.src), v
                elif v is not None and v.type == "call_expression":
                    f = v.child_by_field_name("function")
                    if f is not None and f.type == "member_expression" and text(f.child_by_field_name("property"), jf.src) == "bind":
                        target = f.child_by_field_name("object")
                        if target is not None and target.type == "identifier":
                            aliases.setdefault(text(n.child_by_field_name("name"), jf.src), set()).add(text(target, jf.src))
            if name and body is not None:
                defs.setdefault(name, []).append((body, jf.src))
    helpers: set = set()
    changed = True
    while changed:
        changed = False
        frozen = frozenset(helpers)
        for name, bodies in defs.items():
            if name not in helpers and any(_has_assertion(b, s, frozen) for b, s in bodies):
                helpers.add(name)
                changed = True
        for name, targets in aliases.items():
            if name not in helpers and targets & helpers:
                helpers.add(name)
                changed = True
    return frozenset(helpers)


def _base(check_id, jm):
    r = CheckResult(check_id)
    r.unknowns.extend(i for i in jm.issues if i.file in set(jm.candidate_paths))
    return r


def ec_js_no_assertion(jm: JSModel) -> CheckResult:
    """EC-NO-ASSERTION-JS: a JS/TS test case whose callback contains no
    assertion the detector can see: expect/assert/should chains, node:test
    and ava `t.*` assertions, sinon.assert, testing-library getBy*/findBy*
    queries (they throw), cypress `.should`/`cy.contains`, a thrown error, or
    a call to a test-file function that itself asserts. Skipped and todo
    tests are excluded (EC-TESTS-NOT-RUN-JS reports them)."""
    r = _base("EC-NO-ASSERTION-JS", jm)
    helpers = asserting_helpers(jm)
    total = 0
    for jf in jm.tests():
        for tc in jf.tests:
            if tc.body is None or {"skip", "todo"} & tc.modifiers:
                continue
            total += 1
            if tc.body.type in ("identifier", "member_expression"):
                ref = text(tc.body, jf.src).split(".")[-1]
                if ref in helpers:
                    continue
                r.unknowns.append(Location(jf.path, tc.line, f"test {tc.name!r} runs function reference {ref!r} defined elsewhere; not evaluated"))
                continue
            if not _has_assertion(tc.body, jf.src, helpers, _first_param(tc.body, jf.src)):
                r.findings.append(Location(jf.path, tc.line, f"test {tc.name!r} contains no assertion the detector can see", {"test": tc.name}))
    r.had_input = total > 0 or bool(r.unknowns)
    if not r.had_input:
        r.absent_reason = NO_JS_TESTS
    r.stats = {"test_cases": total}
    return r


def ec_js_tests_not_run(jm: JSModel) -> CheckResult:
    """EC-TESTS-NOT-RUN-JS: test cases present but never run.
    FAIL: `.skip` / `xit` / `xdescribe` (unconditional), `.todo` and pending
    tests with no body, and `.only` / `fit` / `fdescribe` in a file, which
    silently excludes every other test in that file under jest and mocha
    (and the whole run under mocha). Under vitest, `.only` makes a CI run
    fail (allowOnly defaults to false when CI is set), so it is not reported
    for vitest projects. Conditional skips (skipIf/runIf, `(cond ? it :
    it.skip)`) are not evaluated. An unknown test framework makes `.only`
    UNKNOWN."""
    r = _base("EC-TESTS-NOT-RUN-JS", jm)
    total = 0
    for jf in jm.tests():
        total += len(jf.tests)
        skipped = [t for t in jf.tests if "skip" in t.modifiers]
        todo = [t for t in jf.tests if ("todo" in t.modifiers or t.body is None) and "skip" not in t.modifiers]
        for t in skipped:
            r.findings.append(Location(jf.path, t.line, f"test {t.name!r} never runs: skipped unconditionally", {"kind": "skipped", "test": t.name}))
        for t in todo:
            r.findings.append(Location(jf.path, t.line, f"test {t.name!r} has no body (todo/pending): counted, never runs", {"kind": "todo", "test": t.name}))
        only = [t for t in jf.tests if "only" in t.modifiers]
        if only:
            fw = framework_for(jm, jf.path)
            excluded = [t for t in jf.tests if "only" not in t.modifiers and "skip" not in t.modifiers and t.body is not None]
            if "vitest" in fw and not ({"jest", "mocha"} & fw):
                continue
            if not fw & {"jest", "mocha", "jasmine"}:
                r.unknowns.append(Location(jf.path, only[0].line, ".only present; effect depends on the test framework, which is not identified"))
                continue
            if excluded:
                r.findings.append(
                    Location(jf.path, only[0].line, f".only in this file: {len(excluded)} other test(s) never run", {"kind": "only", "excluded": len(excluded)})
                )
    r.had_input = total > 0 or bool(r.unknowns)
    if not r.had_input:
        r.absent_reason = NO_JS_TESTS
    r.stats = {"test_cases": total}
    return r


def _is_literal(node):
    return node is not None and node.type in ("true", "false", "number", "string", "null", "undefined", "template_string") and (
        node.type != "template_string" or not any(c.type == "template_substitution" for c in node.children)
    )


def _returned_or_awaited(node):
    """Is this expression awaited, returned, or the arrow body itself?"""
    p = node.parent
    while p is not None and p.type in ("parenthesized_expression", "member_expression", "call_expression") and p.child_by_field_name("function") != node:
        if p.type == "call_expression":
            break
        node, p = p, p.parent
    if p is None:
        return False
    return p.type in ("await_expression", "return_statement", "arrow_function")


def _always_passes(matcher, subject, args, src) -> bool:
    """expect(<literal>).matcher(<literals>) that passes whatever the code
    does. Literals that differ make an assertion that always fails (a
    should-not-reach guard), which is not reported."""
    s = text(subject, src)
    if matcher in ("toBe", "toEqual", "toStrictEqual"):
        return len(args) == 1 and _is_literal(args[0]) and text(args[0], src) == s
    if matcher in ("toBeTruthy", "toBeDefined") and not args:
        return _truthy_literal(subject, src)
    if matcher == "toBeFalsy" and not args:
        return subject.type in ("false", "null", "undefined") or s in ("0", '""', "''")
    if matcher == "toBeNull" and not args:
        return subject.type == "null"
    if matcher == "toBeUndefined" and not args:
        return subject.type == "undefined"
    return False


def _truthy_literal(node, src) -> bool:
    if node.type == "true":
        return True
    if node.type == "number":
        try:
            return float(text(node, src).replace("_", "")) != 0
        except ValueError:
            return False
    if node.type == "string":
        return text(node, src) not in ('""', "''")
    return False


def ec_js_assertion_nonstandard(jm: JSModel) -> CheckResult:
    """EC-ASSERTION-NONSTANDARD-JS: assertions that cannot fail or may not run.
      bare-expect      `expect(x);` with no matcher
      uncalled-matcher `expect(x).toBe;` / `.toBeTruthy` without () (jest,
                       vitest matchers are functions; chai's property
                       assertions are not reported)
      constant         `expect(true).toBe(true)`, `expect(1).toEqual(1)`,
                       `assert(true)`, `assert.ok(1)`: both sides literal
      unawaited        `expect(p).resolves...` / `.rejects...` neither
                       awaited nor returned: the test can end first"""
    r = _base("EC-ASSERTION-NONSTANDARD-JS", jm)
    count = 0
    for jf in jm.tests():
        src = jf.src
        fw = framework_for(jm, jf.path)
        chai = "chai" in fw and not ({"jest", "vitest"} & fw)
        local_defs = local_definitions(jf.root, src)
        for n in walk(jf.root):
            if n.type == "expression_statement" and n.named_children:
                e = n.named_children[0]
                if e.type == "call_expression" and text(e.child_by_field_name("function"), src) == "expect":
                    count += 1
                    r.findings.append(Location(jf.path, n.start_point[0] + 1, "expect(...) with no matcher asserts nothing", {"pattern": "bare-expect"}))
                elif e.type == "member_expression" and not chai:
                    prop = text(e.child_by_field_name("property"), src)
                    if JEST_MATCHER_RE.match(prop) and prop.startswith("to") and _root_identifier(e, src) == "expect":
                        count += 1
                        r.findings.append(Location(jf.path, n.start_point[0] + 1, f"matcher .{prop} is referenced but never called", {"pattern": "uncalled-matcher"}))
            if n.type != "call_expression":
                continue
            fn = n.child_by_field_name("function")
            if fn is None:
                continue
            # expect(<literal>).toX(<literal>)
            if fn.type == "member_expression":
                obj = fn.child_by_field_name("object")
                prop = text(fn.child_by_field_name("property"), src)
                if obj is not None and obj.type == "call_expression" and text(obj.child_by_field_name("function"), src) == "expect" and prop.startswith("to"):
                    count += 1
                    a1 = obj.child_by_field_name("arguments").named_children
                    a2 = n.child_by_field_name("arguments").named_children
                    if prop in PURE_MATCHERS and len(a1) == 1 and _is_literal(a1[0]) and _always_passes(prop, a1[0], a2, src):
                        r.findings.append(Location(jf.path, n.start_point[0] + 1, f"expect(<literal>).{prop}(<literal>) cannot fail", {"pattern": "constant"}))
                # expect(p).resolves/rejects.toX() not awaited or returned
                if prop.startswith("to") and obj is not None and obj.type == "member_expression" and text(obj.child_by_field_name("property"), src) in ("resolves", "rejects"):
                    if _root_identifier(obj, src) == "expect" and not _returned_or_awaited(n):
                        r.findings.append(Location(jf.path, n.start_point[0] + 1, ".resolves/.rejects assertion is neither awaited nor returned: the test can finish before it runs", {"pattern": "unawaited"}))
            if text(fn, src) in ("assert", "assert.ok", "assert.isTrue", "assert.isOk") and "assert" not in local_defs:
                args = n.child_by_field_name("arguments").named_children
                if args and _truthy_literal(args[0], src):
                    r.findings.append(Location(jf.path, n.start_point[0] + 1, f"{text(fn, src)}(<truthy literal>) cannot fail", {"pattern": "constant"}))
    r.had_input = bool(jm.tests()) or bool(r.unknowns)
    if not r.had_input:
        r.absent_reason = NO_JS_TESTS
    r.stats = {"expect_calls_examined": count}
    return r


def ec_js_exit_before_assert(jm: JSModel) -> CheckResult:
    """EC-EXIT-BEFORE-ASSERT-JS: `process.exit()` / `process.exit(0)` in a
    JS/TS test file: the runner process ends with success before remaining
    assertions run. A non-zero literal status is not reported; a non-literal
    status is UNKNOWN."""
    r = _base("EC-EXIT-BEFORE-ASSERT-JS", jm)
    for jf in jm.tests():
        for n in walk(jf.root):
            if n.type == "call_expression" and text(n.child_by_field_name("function"), jf.src) == "process.exit":
                args = n.child_by_field_name("arguments").named_children
                if not args or (args[0].type == "number" and text(args[0], jf.src) == "0"):
                    r.findings.append(Location(jf.path, n.start_point[0] + 1, "process.exit with success status in a test file", {}))
                elif args[0].type != "number":
                    r.unknowns.append(Location(jf.path, n.start_point[0] + 1, "process.exit with a non-literal status in a test file"))
    r.had_input = bool(jm.tests()) or bool(r.unknowns)
    if not r.had_input:
        r.absent_reason = NO_JS_TESTS
    return r


def ec_js_runner_patched(jm: JSModel) -> CheckResult:
    """EC-RUNNER-PATCHED-JS: test infrastructure rewritten so checks pass.
      custom matcher   `expect.extend({ m() { return { pass: true ... } } })`
                       where every returned `pass` is the literal true
      global override  assignment to `expect`, `it`, `test`, `describe`,
                       `assert` or their global/globalThis properties
    Files examined: test files and test-like support files (setup files are
    usually named *.setup.* or live under test/)."""
    r = _base("EC-RUNNER-PATCHED-JS", jm)
    names = {"expect", "it", "test", "describe", "assert"}
    for jf in jm.files.values():
        src = jf.src
        for n in walk(jf.root):
            if n.type == "assignment_expression":
                left = n.child_by_field_name("left")
                t = text(left, src) if left is not None else ""
                bare = t.split(".")[-1] if t.startswith(("global.", "globalThis.", "window.")) else t
                if bare in names:
                    r.findings.append(Location(jf.path, n.start_point[0] + 1, f"reassigns test primitive {t}", {"target": t}))
            if n.type == "call_expression" and text(n.child_by_field_name("function"), src) == "expect.extend":
                for m in walk(n):
                    if m.type in ("method_definition", "pair", "function_expression", "arrow_function") and m.parent is not None:
                        rets = [x for x in walk(m) if x.type == "return_statement"]
                        passes = []
                        for rt in rets:
                            for p in walk(rt):
                                if p.type == "pair" and text(p.child_by_field_name("key"), src) == "pass":
                                    passes.append(p.child_by_field_name("value"))
                        if passes and all(v is not None and v.type == "true" for v in passes) and m.type == "method_definition":
                            r.findings.append(Location(jf.path, m.start_point[0] + 1, "custom matcher always returns pass: true", {}))
    r.had_input = bool(jm.files) or bool(r.unknowns)
    if not r.had_input:
        r.absent_reason = NO_JS_TESTS
    return r


ALL = [ec_js_exit_before_assert, ec_js_runner_patched, ec_js_tests_not_run, ec_js_no_assertion, ec_js_assertion_nonstandard]
