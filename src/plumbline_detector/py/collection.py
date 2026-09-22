"""Which tests actually run: a static model of pytest collection and selection.

Inputs, all read from the snapshot:
  * pytest configuration, located and parsed as pytest itself does
    (precedence pytest.toml, .pytest.toml, pytest.ini, .pytest.ini,
    pyproject.toml, tox.ini, setup.cfg; first directory upward that has one);
  * invocations of pytest found in GitHub Actions `run:` scripts, tox.ini
    `commands`, noxfile.py `session.run(...)`, Makefile recipes and *.sh
    scripts; when none is found, a plain `pytest` at each configuration root;
  * conftest.py `collect_ignore` / `collect_ignore_glob`;
  * test functions, their markers and unconditional skips.

A test RUNS if at least one invocation collects it, selects it, and it is not
unconditionally skipped. Adding invocations can only make more tests run, so
every inference here errs toward "runs": the model reports a test as not run
only when every invocation it can see excludes it. Anything it cannot
resolve (a shell variable, `${{ }}` in the arguments, -o / -c / --rootdir,
--pyargs, a collection hook) makes the affected conclusion UNKNOWN.
"""

from __future__ import annotations

import ast
import configparser
import fnmatch
import posixpath
import re
import shlex
import tomllib
from dataclasses import dataclass, field

from ..model import Location
from .common import PyModel, dotted, qualname

CONFIG_NAMES = ["pytest.toml", ".pytest.toml", "pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg"]
DEFAULT_PYTHON_FILES = ["test_*.py", "*_test.py"]
DEFAULT_PYTHON_CLASSES = ["Test"]
DEFAULT_PYTHON_FUNCTIONS = ["test"]
DEFAULT_NORECURSE = ["*.egg", ".*", "_darcs", "build", "CVS", "dist", "node_modules", "venv", "{arch}"]

# Options that take a value (so the next token is not a path).
VALUE_OPTS = {
    "-k", "-m", "-p", "-c", "-o", "-W", "-n", "-r",
    "--deselect", "--ignore", "--ignore-glob", "--rootdir", "--confcutdir", "--basetemp",
    "--dist", "--maxfail", "--tb", "--durations", "--durations-min", "--cov", "--cov-report",
    "--cov-config", "--cov-fail-under", "--junitxml", "--junit-xml", "--junit-prefix",
    "--log-level", "--log-cli-level", "--log-file", "--log-format", "--timeout", "--reruns",
    "--reruns-delay", "--randomly-seed", "--capture", "--import-mode", "--color", "--override-ini",
    "--config-file", "--numprocesses", "--maxprocesses", "--html", "--json-report-file",
    "--hypothesis-profile", "--hypothesis-seed", "--benchmark-json", "--benchmark-save",
    "--benchmark-storage", "--benchmark-min-rounds", "--splits", "--group", "--count",
    "--asyncio-mode", "--ds", "--dc", "--doctest-glob", "--rootdir", "--basetemp",
}
# -p (load a plugin) is not unbounding: plugins that change collection are
# a documented blind spot, not something every -p should hide behind.
UNBOUNDING_OPTS = {"-c", "-o", "--override-ini", "--rootdir", "--config-file"}
NON_RUN_OPTS = {"--co", "--collect-only", "--setup-plan", "--fixtures", "--markers", "--version", "-h", "--help", "--fixtures-per-test"}
WRAPPER_TOKENS = {"uv", "run", "poetry", "pdm", "hatch", "pipenv", "rye", "xvfb-run", "-a", "timeout", "sudo", "env", "time", "exec", "--", "-E", "--locked", "--frozen", "--no-sync", "--active"}
PYTHON_RE = re.compile(r"^(.*/)?(python|python3|python3\.\d+|py|pypy3?)(\.exe)?$")
UNRESOLVED_RE = re.compile(r"\$|\{\{|\}\}|`|\{[^}]*\}")


# --------------------------------------------------------------------------
# configuration


@dataclass
class PytestConfig:
    dir: str  # repo-relative directory ("" is the root)
    file: str | None
    values: dict
    broken: bool = False
    fallback_only: bool = False  # a pyproject.toml without pytest config: rootdir only

    def args(self, key, default):
        v = self.values.get(key)
        if v is None:
            return list(default)
        if isinstance(v, list):
            return [str(x) for x in v]
        try:
            return shlex.split(str(v))
        except ValueError:
            return None


def _load_config(path: str, data: bytes):
    """Return (values | None if the file holds no pytest config, error)."""
    name = posixpath.basename(path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, "not UTF-8"
    if name.endswith(".toml"):
        try:
            doc = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            return None, f"TOML error: {e}"
        if name in ("pytest.toml", ".pytest.toml"):
            return dict(doc.get("pytest", {})), None
        tool = doc.get("tool", {}).get("pytest", {})
        if not isinstance(tool, dict):
            return None, None
        native = {k: v for k, v in tool.items() if k != "ini_options"}
        if native:
            return native, None
        ini = tool.get("ini_options")
        if isinstance(ini, dict):
            return {k: (v if isinstance(v, list) else str(v)) for k, v in ini.items()}, None
        return None, None
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read_string(text, source=path)
    except configparser.Error as e:
        return None, f"INI error: {type(e).__name__}"
    section = "tool:pytest" if name == "setup.cfg" else "pytest"
    if cp.has_section(section):
        return {k: v for k, v in cp.items(section)}, None
    if name in ("pytest.ini", ".pytest.ini"):
        return {}, None
    return None, None


def find_configs(snap, issues) -> dict[str, PytestConfig]:
    """Map directory -> the config pytest would use when that directory is
    the first one found holding a config."""
    by_dir: dict[str, dict[str, str]] = {}
    for p in snap.all_paths():
        d, name = posixpath.split(p)
        if name in CONFIG_NAMES:
            by_dir.setdefault(d, {})[name] = p
    out = {}
    for d, names in sorted(by_dir.items()):
        pyproject = None
        for name in CONFIG_NAMES:
            if name not in names:
                continue
            p = names[name]
            if name == "pyproject.toml":
                pyproject = p
            if p in snap.unread:
                issues.append(Location(p, None, f"config not read: {snap.unread[p]}"))
                out[d] = PytestConfig(d, p, {}, broken=True)
                break
            values, err = _load_config(p, snap.files[p])
            if err:
                issues.append(Location(p, None, f"config unparseable: {err}"))
                out[d] = PytestConfig(d, p, {}, broken=True)
                break
            if values is not None:
                out[d] = PytestConfig(d, p, values)
                break
        else:
            if pyproject is not None:
                out[d] = PytestConfig(d, pyproject, {}, fallback_only=True)
    return out


def config_for(dir_: str, configs: dict[str, PytestConfig]) -> PytestConfig:
    d = dir_
    fallback = None
    while True:
        c = configs.get(d)
        if c is not None:
            if not c.fallback_only:
                return c
            fallback = fallback or c
        if d == "":
            break
        d = posixpath.dirname(d)
    return fallback or PytestConfig("", None, {})


# --------------------------------------------------------------------------
# tests


@dataclass
class TestItem:
    file: str
    cls: str | None
    name: str
    line: int
    markers: frozenset
    skipped: str | None  # reason if unconditionally skipped
    parametrized: bool

    def nodeid_from(self, rootdir: str) -> str:
        rel = posixpath.relpath(self.file, rootdir or ".") if rootdir else self.file
        return "::".join([rel] + ([self.cls] if self.cls else []) + [self.name])


def _matches_prefix_or_glob(name, options):
    for o in options:
        if name.startswith(o):
            return True
        if any(ch in o for ch in "*?[") and fnmatch.fnmatch(name, o):
            return True
    return False


def _marker_name(dec, imports):
    target = dec.func if isinstance(dec, ast.Call) else dec
    qn = qualname(target, imports) or ""
    for prefix in ("pytest.mark.", "_pytest.mark."):
        if qn.startswith(prefix):
            return qn[len(prefix):].split(".")[0], dec
    return None, dec


def _markers(decorators, imports):
    names, skip = set(), None
    parametrized = False
    for dec in decorators:
        name, node = _marker_name(dec, imports)
        qn = qualname(dec.func if isinstance(dec, ast.Call) else dec, imports) or ""
        if qn in ("unittest.skip",):
            skip = skip or "unittest.skip"
        if name is None:
            continue
        names.add(name)
        if name == "parametrize":
            parametrized = True
        if name == "skip":
            skip = skip or "@pytest.mark.skip"
        if name == "skipif" and isinstance(node, ast.Call) and node.args:
            a = node.args[0]
            if isinstance(a, ast.Constant) and a.value is True:
                skip = skip or "@pytest.mark.skipif(True)"
        if name == "xfail" and isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "run" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                    skip = skip or "@pytest.mark.xfail(run=False)"
    return names, skip, parametrized


def _pytestmark(body, imports):
    names, skip = set(), None
    for st in body:
        if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in st.targets):
            v = st.value
            elts = v.elts if isinstance(v, (ast.List, ast.Tuple)) else [v]
            n, s, _ = _markers(elts, imports)
            names |= n
            skip = skip or s
    return names, skip


def _module_skip(tree, imports):
    """Top-level, unconditional module skip."""
    for st in tree.body:
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
            qn = qualname(st.value.func, imports) or ""
            if qn == "pytest.skip" and any(k.arg == "allow_module_level" and isinstance(k.value, ast.Constant) and k.value.value is True for k in st.value.keywords):
                return "module-level pytest.skip"
        if isinstance(st, ast.Raise) and st.exc is not None:
            t = st.exc.func if isinstance(st.exc, ast.Call) else st.exc
            if (dotted(t) or "").split(".")[-1] == "SkipTest":
                return "module-level raise SkipTest"
    return None


def _body_skip(fn, imports):
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if not body:
        return None
    st = body[0]
    if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
        qn = qualname(st.value.func, imports) or ""
        if qn == "pytest.skip" or (dotted(st.value.func) or "") == "self.skipTest":
            return "skipped as its first statement"
    if isinstance(st, ast.Raise) and st.exc is not None:
        t = st.exc.func if isinstance(st.exc, ast.Call) else st.exc
        if (dotted(t) or "").split(".")[-1] == "SkipTest":
            return "skipped as its first statement"
    return None


def enumerate_tests(pf, cfg: PytestConfig) -> list[TestItem]:
    funcs = cfg.args("python_functions", DEFAULT_PYTHON_FUNCTIONS) or DEFAULT_PYTHON_FUNCTIONS
    classes = cfg.args("python_classes", DEFAULT_PYTHON_CLASSES) or DEFAULT_PYTHON_CLASSES
    imp = pf.imports
    mod_marks, mod_skip = _pytestmark(pf.tree.body, imp)
    mod_skip = _module_skip(pf.tree, imp) or mod_skip
    items = []
    for node in pf.tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _matches_prefix_or_glob(node.name, funcs):
            if _is_fixture(node, imp):
                continue
            m, s, par = _markers(node.decorator_list, imp)
            items.append(TestItem(pf.path, None, node.name, node.lineno, frozenset(m | mod_marks), mod_skip or s or _body_skip(node, imp), par))
        elif isinstance(node, ast.ClassDef):
            bases = [(dotted(b) or "").split(".")[-1] for b in node.bases]
            unit = any(b.endswith("TestCase") for b in bases)
            if not (unit or _matches_prefix_or_glob(node.name, classes)):
                continue
            if not unit and any(isinstance(x, ast.FunctionDef) and x.name == "__init__" for x in node.body):
                continue
            cm, cs, _ = _markers(node.decorator_list, imp)
            pm_names, pm_skip = _pytestmark(node.body, imp)
            for item in node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                ok = item.name.startswith("test") if unit else _matches_prefix_or_glob(item.name, funcs)
                if not ok or _is_fixture(item, imp):
                    continue
                m, s, par = _markers(item.decorator_list, imp)
                skip = mod_skip or cs or pm_skip or s or _body_skip(item, imp)
                items.append(TestItem(pf.path, node.name, item.name, item.lineno, frozenset(m | cm | pm_names | mod_marks), skip, par))
    return items


def _is_fixture(fn, imports):
    for d in fn.decorator_list:
        t = d.func if isinstance(d, ast.Call) else d
        if (qualname(t, imports) or dotted(t) or "").split(".")[-1] in ("fixture", "yield_fixture"):
            return True
    return False


# --------------------------------------------------------------------------
# selection expressions (-k / -m)

_TOKEN_RE = re.compile(r"\s*(\(|\)|[\w:+\-.\[\]\\/]+)")


def _parse_expr(expr: str):
    toks = []
    pos = 0
    expr = expr.strip()
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            return None
        toks.append(m.group(1))
        pos = m.end()
        while pos < len(expr) and expr[pos].isspace():
            pos += 1
    if not toks:
        return lambda match: True
    i = 0

    def peek():
        return toks[i] if i < len(toks) else None

    def take():
        nonlocal i
        i += 1
        return toks[i - 1]

    def p_or():
        left = p_and()
        while peek() == "or":
            take()
            right = p_and()
            left = (lambda a, b: lambda f: a(f) or b(f))(left, right)
        return left

    def p_and():
        left = p_not()
        while peek() == "and":
            take()
            right = p_not()
            left = (lambda a, b: lambda f: a(f) and b(f))(left, right)
        return left

    def p_not():
        t = peek()
        if t == "not":
            take()
            inner = p_not()
            return lambda f: not inner(f)
        if t == "(":
            take()
            inner = p_or()
            if take() != ")":
                raise ValueError
            return inner
        if t is None or t in ("and", "or", ")"):
            raise ValueError
        ident = take()
        return lambda f: f(ident)

    try:
        fn = p_or()
        if i != len(toks):
            return None
        return fn
    except (ValueError, IndexError):
        return None


def keyword_selected(expr_fn, item: TestItem, rootdir: str) -> bool:
    rel = posixpath.relpath(item.file, rootdir) if rootdir else item.file
    names = [item.name, posixpath.basename(item.file)] + ([item.cls] if item.cls else [])
    names += [p for p in posixpath.dirname(rel).split("/") if p]
    names += list(item.markers)
    lowered = [n.lower() for n in names]
    return expr_fn(lambda ident: any(ident.lower() in n for n in lowered))


def marker_selected(expr_fn, item: TestItem) -> bool:
    return expr_fn(lambda ident: ident in item.markers)


# --------------------------------------------------------------------------
# invocations


@dataclass
class Invocation:
    source: str  # file of origin
    line: int | None
    cwd: str | None  # None: unknown
    args: list[str] | None  # None: unresolvable
    extra_addopts: list[str] = field(default_factory=list)
    default: bool = False

    def describe(self):
        where = f"{self.source}:{self.line}" if self.line else self.source
        return f"{'default invocation' if self.default else 'invocation'} at {where}"


def _split_commands(script: str):
    script = script.replace("\\\n", " ")
    for line in script.splitlines():
        for part in re.split(r"&&|\|\||;|\|", line):
            part = part.strip()
            if part and not part.startswith("#"):
                yield part


def _pytest_args(tokens):
    """If this simple command runs pytest, return the argument list."""
    toks = [t for t in tokens if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t)]
    for i, t in enumerate(toks):
        base = posixpath.basename(t)
        if base in ("pytest", "py.test"):
            if all(x in WRAPPER_TOKENS or PYTHON_RE.match(x) for x in toks[:i]):
                return toks[i + 1:]
            return None
        if t == "-m" and i + 1 < len(toks) and toks[i + 1] == "pytest":
            head = toks[:i]
            if head and (PYTHON_RE.match(head[-1]) or head[-2:] == ["coverage", "run"] or head[-1] == "{envpython}"):
                return toks[i + 2:]
            return None
    return None


def _join(cwd, d):
    if cwd is None or d is None or UNRESOLVED_RE.search(d):
        return None
    j = posixpath.normpath(posixpath.join(cwd, d))
    if j.startswith("..") or posixpath.isabs(j):
        return None
    return "" if j == "." else j


def invocations_from_script(script, source, line, cwd, env_addopts=None):
    out = []
    for cmd in _split_commands(script):
        try:
            toks = shlex.split(cmd, comments=True)
        except ValueError:
            continue
        if not toks:
            continue
        if toks[0] in ("cd", "pushd") and len(toks) == 2:
            cwd = _join(cwd, toks[1])
            continue
        args = _pytest_args(toks)
        if args is None:
            continue
        if any(a in NON_RUN_OPTS for a in args):
            continue
        extra = []
        if env_addopts is not None:
            if UNRESOLVED_RE.search(env_addopts):
                args = None
            else:
                try:
                    extra = shlex.split(env_addopts)
                except ValueError:
                    args = None
        if args is not None and any(UNRESOLVED_RE.search(a) for a in args):
            args = None
        out.append(Invocation(source, line, cwd, args, extra))
    return out


def _gha_invocations(gm):
    out = []
    for wf in gm.workflows.values():
        for job in wf.jobs.values():
            for st in job.steps:
                if not st.run:
                    continue
                wd = st.working_directory or job.run_working_directory or wf.run_working_directory or "."
                cwd = _join("", wd)
                env = {**wf.env, **job.env, **st.env}
                out += invocations_from_script(st.run, wf.path, st.line, cwd, env.get("PYTEST_ADDOPTS"))
    return out


_TOX_INNER = re.compile(r"\{([^{}]*)\}")
_TOX_FACTOR_PREFIX = re.compile(r"^\s*[\w.!,-]+:\s+")


def _tox_substitute(text: str) -> str:
    """Resolve tox substitutions innermost-first. Defaults are taken
    (`{posargs:X}` -> X, `{env:N:D}` -> D); anything else unknown becomes a
    `$UNRESOLVED` token, which makes the invocation unresolvable."""

    def one(m):
        body = m.group(1)
        if body == "posargs":
            return ""
        if body.startswith("posargs:"):
            return body[len("posargs:"):]
        if body.startswith("env:"):
            parts = body.split(":", 2)
            return parts[2] if len(parts) == 3 else "$UNRESOLVED"
        if body in ("toxinidir", "tox_root"):
            return "."
        if body == "envpython":
            return "python"
        return "$UNRESOLVED"

    for _ in range(10):
        new = _TOX_INNER.sub(one, text)
        if new == text:
            break
        text = new
    return text


def _tox_invocations(snap):
    out = []
    for p in snap.paths():
        if posixpath.basename(p) != "tox.ini":
            continue
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            cp.read_string(snap.files[p].decode("utf-8"), source=p)
        except (configparser.Error, UnicodeDecodeError):
            continue
        d = posixpath.dirname(p)
        for sec in cp.sections():
            if not (sec == "testenv" or sec.startswith("testenv:")) or not cp.has_option(sec, "commands"):
                continue
            cwd = d
            if cp.has_option(sec, "changedir"):
                cwd = _join(d, _tox_substitute(cp.get(sec, "changedir").strip()))
            lines = [_TOX_FACTOR_PREFIX.sub("", ln) for ln in cp.get(sec, "commands").splitlines()]
            text = _tox_substitute("\n".join(lines))
            out += invocations_from_script(text, p, None, cwd)
    return out


def _nox_invocations(pm: PyModel):
    out = []
    for pf in pm.files.values():
        if posixpath.basename(pf.path) != "noxfile.py":
            continue
        d = posixpath.dirname(pf.path)
        chdir = any(isinstance(n, ast.Call) and (dotted(n.func) or "").endswith(".chdir") for n in ast.walk(pf.tree))
        for n in ast.walk(pf.tree):
            if not (isinstance(n, ast.Call) and (dotted(n.func) or "").split(".")[-1] == "run" and n.args):
                continue
            words, resolvable = [], True
            for a in n.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    words.append(a.value)
                elif isinstance(a, ast.Starred) and "posargs" in (dotted(a.value) or ""):
                    continue
                else:
                    resolvable = False
            args = _pytest_args(words) if words else None
            if args is None and not (words and words[0] == "pytest"):
                continue
            out.append(Invocation(pf.path, n.lineno, None if chdir else d, args if resolvable else None))
    return out


def _make_and_sh_invocations(snap):
    out = []
    for p in snap.paths():
        name = posixpath.basename(p)
        if name not in ("Makefile", "makefile", "GNUmakefile") and not name.endswith(".sh"):
            continue
        try:
            text = snap.files[p].decode("utf-8")
        except UnicodeDecodeError:
            continue
        d = posixpath.dirname(p)
        if name.endswith(".sh"):
            # shell scripts are assumed to run from the repository root
            out += invocations_from_script(text, p, None, "")
        else:
            for i, line in enumerate(text.splitlines(), 1):
                if line.startswith("\t"):
                    out += invocations_from_script(line.lstrip("\t@-"), p, i, d)
    return out


# --------------------------------------------------------------------------
# collection


@dataclass
class Collection:
    configs: dict
    invocations: list
    items: list  # TestItem
    runs: dict  # item index -> True
    not_run: dict  # item index -> (kind, reason, detail-source)
    issues: list  # Location, unknowns
    pytest_evidence: bool
    collected_files: set


def _conftest_ignores(pm: PyModel, issues):
    """dir -> (paths, globs), repo-relative, from unconditional module-level
    collect_ignore / collect_ignore_glob in conftest.py."""
    out = {}
    for pf in pm.files.values():
        if posixpath.basename(pf.path) != "conftest.py":
            continue
        d = posixpath.dirname(pf.path)
        paths, globs = [], []
        for node in ast.walk(pf.tree):
            target = None
            values = None
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                ts = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in ts:
                    if isinstance(t, ast.Name) and t.id in ("collect_ignore", "collect_ignore_glob"):
                        target, values = t.id, node.value
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id in ("collect_ignore", "collect_ignore_glob") and node.func.attr in ("append", "extend"):
                target = node.func.value.id
                values = node.args[0] if node.args else None
                if node.func.attr == "append" and values is not None:
                    values = ast.List(elts=[values])
            if target is None:
                continue
            top_level = any(node is st or (isinstance(st, ast.Expr) and st.value is node) for st in pf.tree.body)
            elts = values.elts if isinstance(values, (ast.List, ast.Tuple)) else None
            consts = [e.value for e in elts or [] if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if not top_level or elts is None or len(consts) != len(elts):
                issues.append(Location(pf.path, node.lineno, f"{target} set conditionally or from a non-literal; collection effect not evaluated"))
                continue
            bucket = paths if target == "collect_ignore" else globs
            bucket += [posixpath.normpath(posixpath.join(d, c)) for c in consts]
        if paths or globs:
            out[d] = (paths, globs)
        for n in pf.tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in ("pytest_collection_modifyitems", "pytest_ignore_collect", "pytest_collect_file", "pytest_deselected"):
                issues.append(Location(pf.path, n.lineno, f"conftest defines {n.name}; selection it performs is not evaluated"))
    return out


def _under(path, root):
    return root == "" or path == root or path.startswith(root + "/")


def _fnmatch_ex(pattern, path):
    if "/" not in pattern:
        return fnmatch.fnmatch(posixpath.basename(path), pattern)
    return fnmatch.fnmatch("/" + path, "*/" + pattern.lstrip("/"))


def _parse_args(tokens, snap_paths, cwd):
    """Split pytest arguments into options and positional args."""
    opts = {"k": None, "m": None, "deselect": [], "ignore": [], "ignore_glob": [], "unbounded": None, "pyargs": False}
    positional = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        name, eq, val = t.partition("=")
        if t.startswith("-") and len(t) > 1:
            key = name if eq else t
            if key.startswith("-k") and key != "-k" and not eq:
                key, val, eq = "-k", t[2:], "="
            if key.startswith("-m") and key != "-m" and not eq and not t.startswith("--"):
                key, val, eq = "-m", t[2:], "="
            if key in UNBOUNDING_OPTS:
                opts["unbounded"] = f"uses {key}"
            if key == "--pyargs":
                opts["pyargs"] = True
            if key in VALUE_OPTS or key in UNBOUNDING_OPTS - {"--pyargs"}:
                if not eq:
                    if i + 1 >= len(tokens):
                        break
                    val = tokens[i + 1]
                    i += 1
                if key == "-k":
                    opts["k"] = val
                elif key == "-m":
                    opts["m"] = val
                elif key == "--deselect":
                    opts["deselect"].append(val)
                elif key == "--ignore":
                    opts["ignore"].append(_join(cwd, val))
                elif key == "--ignore-glob":
                    opts["ignore_glob"].append(val)
            elif not eq and i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                nxt = _join(cwd, tokens[i + 1].split("::")[0])
                if nxt is None or nxt not in snap_paths:
                    i += 1  # treat as the option's value
        else:
            positional.append(t)
        i += 1
    return opts, positional


def build(snap, pm: PyModel, gm) -> Collection:
    issues: list[Location] = []
    configs = find_configs(snap, issues)
    invs = _gha_invocations(gm) + _tox_invocations(snap) + _nox_invocations(pm) + _make_and_sh_invocations(snap)
    pytest_evidence = bool(invs) or any(not c.fallback_only for c in configs.values()) or any(
        posixpath.basename(p) == "conftest.py" for p in pm.files
    ) or any("pytest" in pf.imports.values() or any(v.startswith("pytest.") for v in pf.imports.values()) for pf in pm.tests())
    if not invs:
        roots = sorted({c.dir for c in configs.values() if not c.fallback_only}) or [""]
        invs = [Invocation("(none found)", None, r, [], default=True) for r in roots]
    ignores = _conftest_ignores(pm, issues)

    all_paths = set(snap.all_paths())
    dirs = set()
    for p in all_paths:
        d = posixpath.dirname(p)
        while d and d not in dirs:
            dirs.add(d)
            d = posixpath.dirname(d)
    path_set = all_paths | dirs

    # candidate test modules: anything a config or pytest's defaults would call a test file
    items: list[TestItem] = []
    for p in sorted(pm.files):
        pf = pm.files[p]
        cfg = config_for(posixpath.dirname(p), configs)
        pats = (cfg.args("python_files", DEFAULT_PYTHON_FILES) or DEFAULT_PYTHON_FILES) + DEFAULT_PYTHON_FILES
        if any(_fnmatch_ex(pat, p) for pat in pats) or pf.is_test and posixpath.basename(p) != "conftest.py":
            items += enumerate_tests(pf, cfg)

    runs: dict[int, bool] = {}
    reasons: dict[int, list] = {i: [] for i in range(len(items))}
    collected_files: set = set()
    unresolved: list = []
    for inv in invs:
        if inv.args is None or inv.cwd is None:
            unresolved.append(inv)
            issues.append(Location(inv.source, inv.line, "pytest invocation with arguments or working directory not statically resolvable"))
            continue
        first = next((a for a in inv.args if not a.startswith("-")), None)
        start = _join(inv.cwd, first.split("::")[0]) if first else inv.cwd
        if start is None:
            unresolved.append(inv)
            continue
        cfg = config_for(start if start in dirs or start == "" else posixpath.dirname(start), configs)
        if cfg.broken:
            unresolved.append(inv)
            continue
        addopts = cfg.args("addopts", [])
        if addopts is None:
            issues.append(Location(cfg.file or "", None, "addopts not parseable"))
            addopts = []
        opts, positional = _parse_args(addopts + inv.extra_addopts + inv.args, path_set, inv.cwd)
        if opts["unbounded"]:
            unresolved.append(inv)
            issues.append(Location(inv.source, inv.line, f"pytest invocation {opts['unbounded']}; its selection is not evaluated"))
            continue
        rootdir = cfg.dir
        norecurse = cfg.args("norecursedirs", DEFAULT_NORECURSE) or DEFAULT_NORECURSE
        pyfiles = cfg.args("python_files", DEFAULT_PYTHON_FILES) or DEFAULT_PYTHON_FILES
        if opts["pyargs"]:
            positional = [_pyarg_path(a, inv.cwd, path_set) for a in positional]
            if any(a is None for a in positional):
                unresolved.append(inv)
                issues.append(Location(inv.source, inv.line, "pytest --pyargs names a module not found in the snapshot"))
                continue
        if positional:
            roots = [(_join(inv.cwd, a.split("::")[0]), a.split("::")[1:]) for a in positional]
        elif inv.cwd == rootdir and cfg.args("testpaths", []):
            roots = []
            for tp in cfg.args("testpaths", []):
                base = _join(rootdir, tp)
                if base is None:
                    continue
                if any(ch in tp for ch in "*?["):
                    roots += [(d, []) for d in sorted(path_set) if fnmatch.fnmatch(d, base)]
                else:
                    roots.append((base, []))
        else:
            roots = [(inv.cwd, [])]
        kfn = _parse_expr(opts["k"]) if opts["k"] else None
        mfn = _parse_expr(opts["m"]) if opts["m"] else None
        if (opts["k"] and kfn is None) or (opts["m"] and mfn is None):
            unresolved.append(inv)
            issues.append(Location(inv.source, inv.line, "selection expression not parseable; its effect is not evaluated"))
            continue
        for idx, it in enumerate(items):
            why = _collect_reason(it, roots, rootdir, norecurse, pyfiles, opts, ignores)
            if why is None:
                collected_files.add(it.file)
                nodeid = it.nodeid_from(rootdir)
                if any(nodeid.startswith(d) for d in opts["deselect"]):
                    why = ("deselected", "--deselect")
                elif kfn is not None and not keyword_selected(kfn, it, rootdir):
                    why = ("deselected-param" if it.parametrized else "deselected", f"-k {opts['k']!r}")
                elif mfn is not None and not marker_selected(mfn, it):
                    why = ("deselected", f"-m {opts['m']!r}")
            if why is None:
                if it.skipped:
                    why = ("skipped", it.skipped)
                else:
                    runs[idx] = True
                    continue
            reasons[idx].append((why[0], why[1], inv))
    not_run = {}
    for idx in range(len(items)):
        if runs.get(idx):
            continue
        kinds = reasons[idx]
        # the most specific explanation: skipped > deselected > ignored > scope
        kinds.sort(key=lambda r: SPECIFICITY.index(r[0]))
        best = kinds[0] if kinds else ("scope", "no invocation collects it", None)
        if unresolved and best[0] != "skipped":
            best = ("unresolved", f"excluded by every resolved invocation ({best[1]}), but an unresolved invocation may run it", best[2])
        not_run[idx] = best
    return Collection(configs, invs, items, runs, not_run, issues, pytest_evidence, collected_files)


def _pyarg_path(name, cwd, path_set):
    """Map a --pyargs module name to a path in the snapshot, or None."""
    if "/" in name or name.endswith(".py"):
        return name
    rel = name.replace(".", "/")
    for base in (cwd, "src", ""):
        for cand in (rel, rel + ".py"):
            j = _join(base or "", cand)
            if j is not None and j in path_set:
                return posixpath.relpath(j, cwd) if cwd else j
    return None


SPECIFICITY = ["skipped", "deselected", "deselected-param", "ignored", "scope", "unresolved"]


def _collect_reason(it, roots, rootdir, norecurse, pyfiles, opts, ignores):
    """None if some collection root collects the item; else the most
    specific (kind, reason) among the roots that do not."""
    found = []
    for root, sel in roots:
        if root is None or not _under(it.file, root):
            continue
        why = _collect_from_root(it, root, sel, norecurse, pyfiles, opts, ignores)
        if why is None:
            return None
        found.append(why)
    if not found:
        return ("scope", "outside every collection root (testpaths / invocation paths)")
    return sorted(found, key=lambda w: SPECIFICITY.index(w[0]))[0]


def _collect_from_root(it, root, sel, norecurse, pyfiles, opts, ignores):
    f = it.file
    explicit_file = root == f
    if not explicit_file:
        d = posixpath.dirname(f)
        while d and d != root and _under(d, root):
            if any(_fnmatch_ex(pat, d) for pat in norecurse):
                return ("scope", f"inside {d}/, matched by norecursedirs")
            d = posixpath.dirname(d)
        for ign in opts["ignore"]:
            if ign is not None and _under(f, ign):
                return ("ignored", f"--ignore {ign}")
    for g in opts["ignore_glob"]:
        if fnmatch.fnmatch(f, g) or fnmatch.fnmatch("/" + f, "*/" + g):
            return ("ignored", f"--ignore-glob {g}")
    for cdir, (paths, globs) in sorted(ignores.items()):
        if not _under(f, cdir):
            continue
        where = f"{cdir + '/' if cdir else ''}conftest.py"
        for pth in paths:
            if _under(f, pth) and not explicit_file:
                return ("ignored", f"collect_ignore in {where}")
        for g in globs:
            if fnmatch.fnmatch(f, g):
                return ("ignored", f"collect_ignore_glob in {where}")
    if not explicit_file and not any(_fnmatch_ex(p, f) for p in pyfiles):
        return ("scope", "file name does not match python_files")
    if sel:
        chain = ([it.cls] if it.cls else []) + [it.name]
        if chain[: len(sel)] != [x.split("[")[0] for x in sel]:
            return ("scope", "not among the node IDs selected on the command line")
    return None
