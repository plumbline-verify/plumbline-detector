"""JavaScript / TypeScript analysis with tree-sitter.

Grammar by extension: TypeScript for .ts/.mts/.cts, TSX for .tsx, the
JavaScript grammar (which includes JSX) for .js/.jsx/.mjs/.cjs. A tree with
any ERROR or MISSING node is a parse failure: its file is reported, never
analyzed as if it were clean.

A JS/TS file is a test file when its name follows a test convention
(`*.test.*`, `*.spec.*`, `*.cy.*`, anything under `__tests__/`, or a file
under `test/` / `tests/`) and it declares at least one test case. Files
under `fixtures/`, `__fixtures__/`, `__mocks__/` and `__snapshots__/` are
never test files.
"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass, field

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Parser

from ..model import Location

JS_EXTS = (".js", ".jsx", ".mjs", ".cjs")
TS_EXTS = (".ts", ".mts", ".cts")
TSX_EXTS = (".tsx",)
ALL_EXTS = JS_EXTS + TS_EXTS + TSX_EXTS

_LANGS = {
    "js": Language(tree_sitter_javascript.language()),
    "ts": Language(tree_sitter_typescript.language_typescript()),
    "tsx": Language(tree_sitter_typescript.language_tsx()),
}

TYPE_TEST_RE = re.compile(r"\.(test|spec)-d\.(ts|mts|cts|tsx)$")
VITEST_CONFIG_RE = re.compile(r"^(vitest|vite)\.(config|workspace)\.(js|mjs|cjs|ts|mts|cts)$")
TYPECHECK_ON_RE = re.compile(r"typecheck\s*:\s*(true\b|\{[^{}]*\benabled\s*:\s*true\b)")
TEST_NAME_RE = re.compile(r"\.(test|spec|cy)\.(js|jsx|mjs|cjs|ts|mts|cts|tsx)$")
DATA_DIRS = frozenset({"fixtures", "__fixtures__", "__mocks__", "__snapshots__", "node_modules"})
TEST_DIRS = frozenset({"test", "tests", "__tests__"})
# Support modules parsed only as sources of asserting helpers.
SUPPORT_NAME_RE = re.compile(r"(test[-_]?utils?|test[-_]?helpers?|testing|test-setup|setup-?tests?)", re.I)

# Functions that declare a test case (jest, vitest, mocha, jasmine, node:test,
# playwright, cypress) and a suite.
TEST_FUNCS = frozenset({"it", "test", "specify"})
SUITE_FUNCS = frozenset({"describe", "context", "suite"})
SKIP_ALIASES = {"xit": "it", "xtest": "test", "xspecify": "specify", "xdescribe": "describe", "xcontext": "context"}
ONLY_ALIASES = {"fit": "it", "fdescribe": "describe"}


def is_js(path: str) -> bool:
    return path.endswith(ALL_EXTS) and not path.endswith(".d.ts")


def lang_for(path: str) -> str:
    if path.endswith(TSX_EXTS):
        return "tsx"
    if path.endswith(TS_EXTS):
        return "ts"
    return "js"


def test_like_path(path: str) -> bool:
    parts = path.split("/")
    if any(p in DATA_DIRS for p in parts[:-1]):
        return False
    return bool(TEST_NAME_RE.search(parts[-1])) or any(p in TEST_DIRS for p in parts[:-1])


def text(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def has_parse_error(root) -> bool:
    return root.has_error


@dataclass
class TestCase:
    file: str
    line: int
    name: str
    body: object | None  # function node, or None (pending / todo)
    modifiers: frozenset  # {"skip", "only", "todo", "each"} from itself and enclosing suites
    call: object


@dataclass
class JSFile:
    path: str
    src: bytes
    root: object
    tests: list = field(default_factory=list)
    is_test: bool = False


@dataclass
class JSModel:
    files: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    candidate_paths: list = field(default_factory=list)  # test-like paths, parsed or not
    frameworks: dict = field(default_factory=dict)  # package.json dir -> set of frameworks
    package_scripts: dict = field(default_factory=dict)
    support: dict = field(default_factory=dict)  # helper-source files, not tests
    typecheck_dirs: set = field(default_factory=set)  # vitest typecheck enabled at/below

    def typechecked(self, path: str) -> bool:
        """vitest runs this file's type-level assertions: a *.test-d.* file,
        or a file under a directory whose vitest/vite config enables
        typecheck or whose package scripts pass --typecheck."""
        if TYPE_TEST_RE.search(posixpath.basename(path)):
            return True
        return any(d == "" or path.startswith(d + "/") for d in self.typecheck_dirs)

    def tests(self):
        return [f for f in self.files.values() if f.is_test]


def _callee_parts(fn, src):
    """`it.only.each` -> ['it', 'only', 'each']; identifiers only."""
    parts = []
    while fn is not None:
        if fn.type == "identifier":
            parts.append(text(fn, src))
            break
        if fn.type == "member_expression":
            prop = fn.child_by_field_name("property")
            parts.append(text(prop, src) if prop is not None else "?")
            fn = fn.child_by_field_name("object")
            continue
        if fn.type == "call_expression":  # test.each(table)(...)
            fn = fn.child_by_field_name("function")
            parts.append("()")
            continue
        return None
    return list(reversed(parts))


def classify_call(call, src):
    """For a call_expression: ('test'|'suite', modifiers) or None."""
    fn = call.child_by_field_name("function")
    parts = _callee_parts(fn, src)
    if not parts:
        return None
    head, rest = parts[0], [p for p in parts[1:] if p != "()"]
    mods = set()
    if head in SKIP_ALIASES:
        head = SKIP_ALIASES[head]
        mods.add("skip")
    if head in ONLY_ALIASES:
        head = ONLY_ALIASES[head]
        mods.add("only")
    kind = "test" if head in TEST_FUNCS else "suite" if head in SUITE_FUNCS else None
    if kind is None:
        return None
    for r in rest:
        if r in ("skip", "only", "todo", "each", "concurrent", "sequential", "fails", "failing", "skipIf", "runIf", "fixme", "serial", "parallel"):
            mods.add(r)
        else:
            return None  # an unknown member (e.g. test.describe in playwright handled below)
    if "()" in parts[1:] and "each" not in mods and not ({"skipIf", "runIf"} & mods):
        return None
    return kind, mods


def _function_arg(call):
    """The test body: an inline function, or an identifier naming one (a
    function reference). None when the test has no body (pending)."""
    args = call.child_by_field_name("arguments")
    if args is None:
        return None
    named = args.named_children
    fns = [a for a in named if a.type in ("arrow_function", "function_expression", "function")]
    if fns:
        return fns[-1]
    # a function reference, an ava macro `test(title, macro, ...args)`, or a
    # call that returns the test function `it(title, withSetup(async () => {}))`
    for a in named[1:]:
        if a.type in ("identifier", "member_expression", "call_expression"):
            return a
    return None


def _has_title(call):
    args = call.child_by_field_name("arguments")
    if args is None or not args.named_children:
        return False
    return args.named_children[0].type in ("string", "template_string", "binary_expression", "member_expression", "identifier") and (
        args.named_children[0].type in ("string", "template_string", "binary_expression")
        or len(args.named_children) >= 2
    )


def local_definitions(root, src) -> set:
    """Names bound by function declarations or variable declarators in a file."""
    out = set()
    for n in walk(root):
        if n.type == "function_declaration":
            out.add(text(n.child_by_field_name("name"), src))
        elif n.type == "variable_declarator":
            nm = n.child_by_field_name("name")
            if nm is not None and nm.type == "identifier" and not _requires_test_module(n.child_by_field_name("value"), src):
                out.add(text(nm, src))
    return out


TEST_MODULES = frozenset({"node:test", "test", "ava", "vitest", "@jest/globals", "mocha", "tap", "tape", "uvu", "@playwright/test"})


def _requires_test_module(value, src) -> bool:
    """`require('node:test')` (or `.test` of it): binds the framework's own
    primitive, not a local function that happens to share its name."""
    while value is not None and value.type in ("member_expression", "await_expression"):
        value = value.child_by_field_name("object") if value.type == "member_expression" else (value.named_children[0] if value.named_children else None)
    if value is None or value.type != "call_expression" or text(value.child_by_field_name("function"), src) not in ("require", "import"):
        return False
    args = value.child_by_field_name("arguments")
    return bool(args and args.named_children and args.named_children[0].type == "string" and text(args.named_children[0], src)[1:-1] in TEST_MODULES)


def _first_string(call, src):
    args = call.child_by_field_name("arguments")
    if args is None:
        return "?"
    for a in args.named_children:
        if a.type in ("string", "template_string"):
            return text(a, src)[1:-1][:80]
    return "?"


def extract_tests(jf: JSFile):
    src = jf.src
    shadowed = local_definitions(jf.root, src) & (TEST_FUNCS | SUITE_FUNCS)

    def visit(node, inherited):
        if node.type == "call_expression":
            c = classify_call(node, src)
            head = (_callee_parts(node.child_by_field_name("function"), src) or [""])[0]
            if c and head in shadowed:
                c = None  # a local function that happens to be called test/it
            if c and c[0] == "test" and not _has_title(node):
                c = None
            if c:
                kind, mods = c
                # skipIf/runIf(cond) are conditional: not an unconditional skip
                effective = set(inherited) | (mods - {"skipIf", "runIf"})
                fn = _function_arg(node)
                if kind == "test":
                    jf.tests.append(TestCase(jf.path, node.start_point[0] + 1, _first_string(node, src), fn, frozenset(effective), node))
                    return
                for child in node.children:
                    visit(child, effective)
                return
        for child in node.children:
            visit(child, inherited)

    visit(jf.root, frozenset())


def _frameworks_from_package(data: bytes):
    try:
        pkg = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, {}
    deps = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        if isinstance(pkg.get(key), dict):
            deps.update(pkg[key])
    fw = set()
    for name, label in (("jest", "jest"), ("vitest", "vitest"), ("mocha", "mocha"), ("ava", "ava"), ("jasmine", "jasmine"), ("@playwright/test", "playwright"), ("cypress", "cypress"), ("chai", "chai")):
        if name in deps:
            fw.add(label)
    scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}
    return fw, {k: v for k, v in scripts.items() if isinstance(v, str)}


def framework_for(model: JSModel, path: str) -> set:
    """Frameworks declared by the nearest package.json at or above the file,
    unioned with the root package.json (monorepos hoist test tooling)."""
    d = posixpath.dirname(path)
    found = set()
    while True:
        if d in model.frameworks:
            found |= model.frameworks[d]
            break
        if d == "":
            break
        d = posixpath.dirname(d)
    return found | model.frameworks.get("", set())


def build(snap) -> JSModel:
    m = JSModel()
    for p in snap.all_paths():
        if posixpath.basename(p) == "package.json" and p in snap.files and "node_modules" not in p.split("/"):
            fw, scripts = _frameworks_from_package(snap.files[p])
            if fw is None:
                m.issues.append(Location(p, None, "package.json unparseable"))
                continue
            m.frameworks[posixpath.dirname(p)] = fw
            m.package_scripts[posixpath.dirname(p)] = scripts
            if any(re.search(r"\bvitest\b.*--typecheck\b", v) for v in scripts.values()):
                m.typecheck_dirs.add(posixpath.dirname(p))
        elif VITEST_CONFIG_RE.match(posixpath.basename(p)) and p in snap.files and "node_modules" not in p.split("/"):
            if TYPECHECK_ON_RE.search(snap.files[p].decode("utf-8", "replace")):
                m.typecheck_dirs.add(posixpath.dirname(p))
    for p in snap.all_paths():
        if not is_js(p):
            continue
        support = SUPPORT_NAME_RE.search(p) and "node_modules" not in p.split("/")
        if not test_like_path(p) and not support:
            continue
        if not test_like_path(p):
            if p in snap.files:
                root = Parser(_LANGS[lang_for(p)]).parse(snap.files[p]).root_node
                if not has_parse_error(root):
                    m.support[p] = JSFile(p, snap.files[p], root)
            continue
        m.candidate_paths.append(p)
        if p in snap.unread:
            m.issues.append(Location(p, None, f"not read: {snap.unread[p]}"))
            continue
        src = snap.files[p]
        parser = Parser(_LANGS[lang_for(p)])
        root = parser.parse(src).root_node
        if has_parse_error(root):
            m.issues.append(Location(p, _first_error_line(root), "JS/TS parse failure"))
            continue
        jf = JSFile(p, src, root)
        extract_tests(jf)
        jf.is_test = bool(jf.tests)
        m.files[p] = jf
    return m


def _first_error_line(root):
    for n in walk(root):
        if n.type == "ERROR" or n.is_missing:
            return n.start_point[0] + 1
    return None
