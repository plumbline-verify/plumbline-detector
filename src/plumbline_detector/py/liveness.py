"""Which files under test directories are test code, and which are test data.

A file in a test path is test code when a test runner can execute it:
  * pytest collects it (from the collection model), or
  * it is a conftest.py in a directory at or above a collected file, or
  * test code imports it, directly or transitively (including
    `pytest_plugins` strings in conftest.py).

A test-path file that is none of these, and whose name does not look like a
test module (the configured `python_files` or pytest's defaults), is test
data: input that a test reads, lints, documents or copies, not code a runner
executes. Linters' functional inputs, documentation roots and example
projects are the common cases. A file that does look like a test module stays
test code even when nothing collects it: an uncollected test is what
EC-TESTS-NOT-RUN reports.

Applied only when there is evidence that pytest is the runner and at least
one invocation was resolved; otherwise nothing is reclassified.
"""

from __future__ import annotations

import ast
import posixpath

from .collection import DEFAULT_PYTHON_FILES, _fnmatch_ex, config_for
from .common import PyModel


def _module_index(paths):
    """last dotted component -> [(parts_without_suffix, path)]"""
    index: dict[str, list] = {}
    for p in paths:
        parts = p[:-3].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            index.setdefault(parts[-1], []).append((parts, p))
    return index


def _resolve(dotted: str, index) -> list[str]:
    want = dotted.split(".")
    out = []
    for parts, path in index.get(want[-1], []):
        if parts[-len(want):] == want:
            out.append(path)
    return out


def _imported_modules(pf) -> list[str]:
    """Dotted names a file imports, with relative imports made absolute
    against the file's own path."""
    here = pf.path[:-3].split("/")
    pkg = here[:-1]
    names = []
    for node in ast.walk(pf.tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                mod = ".".join(base + (node.module.split(".") if node.module else []))
            else:
                mod = node.module or ""
            if mod:
                names.append(mod)
                names += [f"{mod}.{a.name}" for a in node.names if a.name != "*"]
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytest_plugins" for t in node.targets):
            v = node.value
            for e in v.elts if isinstance(v, (ast.List, ast.Tuple)) else [v]:
                if isinstance(e, ast.Constant) and isinstance(e.value, str):
                    names.append(e.value)
    return names


def reclassify(pm: PyModel, coll, snap) -> list[str]:
    """Move dead, non-test-named test-path files to pm.data_paths. Returns
    the moved paths."""
    if not coll.pytest_evidence or coll.resolved_invocations == 0:
        return []
    py_paths = sorted(set(pm.test_paths) | set(pm.impl_paths))
    index = _module_index(py_paths)
    collected = set(coll.collected_files)
    collected_dirs = {posixpath.dirname(p) for p in collected}

    def conftest_live(p):
        d = posixpath.dirname(p)
        return any(cd == d or cd.startswith(d + "/") or d == "" for cd in collected_dirs)

    live = set(collected) | {p for p in pm.test_paths if posixpath.basename(p) == "conftest.py" and conftest_live(p)}
    frontier = list(live)
    while frontier:
        p = frontier.pop()
        pf = pm.files.get(p)
        if pf is None:
            continue
        for name in _imported_modules(pf):
            for target in _resolve(name, index):
                if target not in live:
                    live.add(target)
                    frontier.append(target)

    moved = []
    for p in list(pm.test_paths):
        if p in live:
            continue
        cfg = config_for(posixpath.dirname(p), coll.configs)
        pats = (cfg.args("python_files", DEFAULT_PYTHON_FILES) or DEFAULT_PYTHON_FILES) + DEFAULT_PYTHON_FILES
        name = posixpath.basename(p)
        if name != "conftest.py" and (any(_fnmatch_ex(pat, p) for pat in pats) or name == "tests.py"):
            continue  # looks like a test module: stays test code
        # a conftest.py pytest would not load (no collected test at or
        # below its directory) configures nothing: data
        moved.append(p)
    for p in moved:
        pm.test_paths.remove(p)
        pm.data_paths.append(p)
        if p in pm.files:
            pm.files[p].is_test = False
    pm.data_paths.sort()
    # parse problems in files that are now data no longer block test checks
    return moved
