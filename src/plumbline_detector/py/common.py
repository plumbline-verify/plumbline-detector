"""Shared Python analysis: test-path classification, parsing, name resolution."""

from __future__ import annotations

import ast
import warnings
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ..model import Location

TEST_DIR_NAMES = frozenset({"tests", "test", "_tests"})
# Directories that conventionally hold inputs for tests (lint fixtures,
# example scripts, snapshots), not test code. A .py file there is classified
# as data only if its directory is not a package (no __init__.py) and it is
# not itself collectable (conftest.py, test_*.py, *_test.py). Data files are
# counted, not analyzed.
DATA_DIR_NAMES = frozenset({"fixtures", "resources", "testdata", "test_data", "example_scripts", "snapshots"})


def is_python(path: str) -> bool:
    return PurePosixPath(path).suffix in (".py",)


def is_test_path(path: str) -> bool:
    """Allowlist of test locations: pytest's default file patterns
    (test_*.py, *_test.py), conftest.py, Django's tests.py, and any Python
    file under a directory named `tests` or `test`."""
    pp = PurePosixPath(path)
    if pp.suffix != ".py":
        return False
    name = pp.name
    if name.startswith("test_") or name.endswith("_test.py") or name in ("conftest.py", "tests.py"):
        return True
    return any(part in TEST_DIR_NAMES for part in pp.parts[:-1])


def is_collectable_name(path: str) -> bool:
    name = PurePosixPath(path).name
    return name.startswith("test_") or name.endswith("_test.py") or name in ("conftest.py", "tests.py")


def is_data_path(path: str, all_paths) -> bool:
    pp = PurePosixPath(path)
    if pp.suffix != ".py" or is_collectable_name(path):
        return False
    if not any(part in DATA_DIR_NAMES for part in pp.parts[:-1]):
        return False
    return str(pp.parent / "__init__.py") not in all_paths


def in_test_dir(path: str) -> bool:
    return any(part in TEST_DIR_NAMES for part in PurePosixPath(path).parts[:-1])


@dataclass
class PyFile:
    path: str
    tree: ast.Module
    source: bytes
    is_test: bool
    imports: dict[str, str] = field(default_factory=dict)  # local name -> dotted target


@dataclass
class PyModel:
    files: dict[str, PyFile] = field(default_factory=dict)
    issues: list[Location] = field(default_factory=list)  # (path, reason)
    test_paths: list[str] = field(default_factory=list)
    impl_paths: list[str] = field(default_factory=list)
    data_paths: list[str] = field(default_factory=list)

    def tests(self):
        return [self.files[p] for p in self.test_paths if p in self.files]

    def impls(self):
        return [self.files[p] for p in self.impl_paths if p in self.files]

    def issues_in(self, paths):
        ps = set(paths)
        return [i for i in self.issues if i.file in ps]


def _collect_imports(tree: ast.Module) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    out[a.asname] = a.name
                else:
                    root = a.name.split(".")[0]
                    out.setdefault(root, root)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                if a.name != "*":
                    out[a.asname or a.name] = f"{node.module}.{a.name}"
    return out


def build(snap) -> PyModel:
    m = PyModel()
    everything = set(snap.all_paths())
    for p in snap.all_paths():
        if not is_python(p):
            continue
        if is_data_path(p, everything):
            m.data_paths.append(p)
            continue
        (m.test_paths if is_test_path(p) else m.impl_paths).append(p)
        if p in snap.unread:
            m.issues.append(Location(p, None, f"not read: {snap.unread[p]}"))
            continue
        data = snap.files[p]
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                tree = ast.parse(data, filename=p)
        except SyntaxError as e:
            m.issues.append(Location(p, e.lineno, f"Python parse failure: {e.msg}"))
            continue
        except (ValueError, RecursionError, MemoryError) as e:
            m.issues.append(Location(p, None, f"Python parse failure: {type(e).__name__}"))
            continue
        pf = PyFile(path=p, tree=tree, source=data, is_test=is_test_path(p))
        pf.imports = _collect_imports(tree)
        m.files[p] = pf
    return m


def dotted(node) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def qualname(node, imports: dict[str, str]) -> str | None:
    d = dotted(node)
    if d is None:
        return None
    head, _, rest = d.partition(".")
    target = imports.get(head, head)
    return f"{target}.{rest}" if rest else target


def root_name(node) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call, ast.Starred)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else None


def call_name(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def is_main_guard(node) -> bool:
    if not isinstance(node, ast.If):
        return False
    t = node.test
    return (
        isinstance(t, ast.Compare)
        and isinstance(t.left, ast.Name)
        and t.left.id == "__name__"
        and len(t.comparators) == 1
        and isinstance(t.comparators[0], ast.Constant)
        and t.comparators[0].value == "__main__"
    )


def is_fixture(func) -> bool:
    for d in func.decorator_list:
        target = d.func if isinstance(d, ast.Call) else d
        if (dotted(target) or "").split(".")[-1] in ("fixture", "yield_fixture"):
            return True
    return False


def iter_test_functions(pf: PyFile):
    """Yield (func_node, class_node_or_None) for pytest/unittest test functions.
    conftest.py is not a test module, and @fixture functions are not tests."""
    if PurePosixPath(pf.path).name == "conftest.py":
        return
    for node in pf.tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            if not is_fixture(node):
                yield node, None
        elif isinstance(node, ast.ClassDef):
            bases = [dotted(b) or "" for b in node.bases]
            is_unittest = any(b.split(".")[-1].endswith("TestCase") for b in bases)
            is_pytest_cls = node.name.startswith("Test")
            if not (is_unittest or is_pytest_cls):
                continue
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test") and not is_fixture(item):
                    yield item, node


SKIP_DECORATORS = ("skip", "expectedFailure")


def is_skipped(func) -> bool:
    for d in func.decorator_list:
        target = d.func if isinstance(d, ast.Call) else d
        name = dotted(target) or ""
        last = name.split(".")[-1]
        if last in ("skip",) or name.endswith("unittest.skip") or last == "expectedFailure":
            return True
    return False


def walk_no_nested_classes(node):
    """ast.walk that does not descend into nested class definitions."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, ast.ClassDef):
            continue
        stack.extend(ast.iter_child_nodes(n))
