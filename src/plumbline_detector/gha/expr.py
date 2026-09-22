"""Minimal evaluator for GitHub Actions expressions over a job's matrix.

Supports: matrix.<key>, string/number/boolean/null literals, == != && || !
and parentheses, with GitHub's semantics (== on strings is
case-insensitive; && and || return an operand; falsy is false, 0, '' and
null). Anything else (other contexts, functions) is unevaluable: the caller
must treat the result as unknown.
"""

from __future__ import annotations

import itertools
import re

from . import yamlnodes as Y


class Unevaluable(Exception):
    pass


_TOK = re.compile(r"\s*(==|!=|&&|\|\||!|\(|\)|'(?:[^']|'')*'|matrix\.[A-Za-z0-9_-]+|true|false|null|-?\d+(?:\.\d+)?)")
MAX_LEGS = 512


def _tokens(expr):
    pos, out = 0, []
    expr = expr.strip()
    while pos < len(expr):
        m = _TOK.match(expr, pos)
        if not m:
            raise Unevaluable(expr[pos:pos + 20])
        out.append(m.group(1))
        pos = m.end()
        while pos < len(expr) and expr[pos].isspace():
            pos += 1
    return out


def _truthy(v):
    return not (v is None or v is False or v == 0 or v == "")


def _eq(a, b):
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    return a == b


def evaluate(expr: str, leg: dict):
    toks = _tokens(expr)
    i = 0

    def peek():
        return toks[i] if i < len(toks) else None

    def take():
        nonlocal i
        i += 1
        return toks[i - 1]

    def p_or():
        v = p_and()
        while peek() == "||":
            take()
            r = p_and()
            v = v if _truthy(v) else r
        return v

    def p_and():
        v = p_cmp()
        while peek() == "&&":
            take()
            r = p_cmp()
            v = r if _truthy(v) else v
        return v

    def p_cmp():
        v = p_not()
        while peek() in ("==", "!="):
            op = take()
            r = p_not()
            v = _eq(v, r) if op == "==" else not _eq(v, r)
        return v

    def p_not():
        if peek() == "!":
            take()
            return not _truthy(p_not())
        return p_atom()

    def p_atom():
        t = take() if peek() is not None else None
        if t is None:
            raise Unevaluable("truncated")
        if t == "(":
            v = p_or()
            if take() != ")":
                raise Unevaluable("paren")
            return v
        if t.startswith("'"):
            return t[1:-1].replace("''", "'")
        if t in ("true", "false"):
            return t == "true"
        if t == "null":
            return None
        if t.startswith("matrix."):
            return leg.get(t[len("matrix."):])
        return float(t) if "." in t else int(t)

    v = p_or()
    if i != len(toks):
        raise Unevaluable("trailing")
    return v


def _scalar(v):
    if not isinstance(v, Y.YStr):
        raise Unevaluable("non-scalar matrix value")
    s = str(v)
    if v.plain:
        if s in ("true", "false"):
            return s == "true"
        if s in ("null", "~", ""):
            return None
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        if re.fullmatch(r"-?\d+\.\d+", s):
            return float(s)
    return s


def legs(matrix) -> list[dict]:
    """Enumerate the matrix legs (exclude entries are ignored, which can only
    add legs, so 'some leg makes it true' stays sound)."""
    if matrix is None:
        return [{}]
    if not isinstance(matrix, Y.YMap):
        raise Unevaluable("dynamic matrix")
    base, include = {}, []
    for k, v in matrix.items():
        if k == "exclude":
            continue
        if k == "include":
            if not isinstance(v, Y.YList):
                raise Unevaluable("dynamic include")
            for entry in v:
                if not isinstance(entry, Y.YMap):
                    raise Unevaluable("include entry")
                include.append({ek: _scalar(ev) for ek, ev in entry.items()})
            continue
        if not isinstance(v, Y.YList):
            raise Unevaluable(f"dynamic matrix key {k}")
        base[k] = [_scalar(x) for x in v]
    keys = sorted(base)
    combos = [dict(zip(keys, vals)) for vals in itertools.product(*(base[k] for k in keys))] if keys else []
    if len(combos) > MAX_LEGS:
        raise Unevaluable("matrix too large")
    for inc in include:
        matched = False
        for leg in combos:
            if all(_eq(leg[k], v) for k, v in inc.items() if k in base):
                matched = True
                leg.update({k: v for k, v in inc.items() if k not in base})
        if not matched:
            combos.append(dict(inc))
    return combos or [{}]
