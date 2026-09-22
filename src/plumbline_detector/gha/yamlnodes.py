"""YAML loading that keeps line numbers and refuses ambiguity.

PyYAML's constructor applies YAML 1.1 typing (the bare key `on` becomes the
boolean True, `yes` becomes True) and silently keeps the last of duplicate
keys. Neither is acceptable for evidence: we compose the node graph and build
our own values, where every scalar stays a string carrying its line, and
duplicate keys, merge keys, non-scalar keys and multi-document streams are
parse errors.
"""

from __future__ import annotations

import yaml


class YAMLShapeError(Exception):
    def __init__(self, message: str, line: int | None):
        super().__init__(message)
        self.line = line


class YStr(str):
    line: int
    plain: bool

    def __new__(cls, value: str, line: int, plain: bool):
        obj = super().__new__(cls, value)
        obj.line = line
        obj.plain = plain
        return obj


class YMap(dict):
    line: int

    def __init__(self, line: int):
        super().__init__()
        self.line = line
        self.key_lines: dict[str, int] = {}


class YList(list):
    line: int

    def __init__(self, line: int):
        super().__init__()
        self.line = line


def _build(node, depth=0):
    if depth > 200:
        raise YAMLShapeError("nesting too deep", node.start_mark.line + 1)
    line = node.start_mark.line + 1
    if isinstance(node, yaml.ScalarNode):
        return YStr(node.value, line, node.style is None)
    if isinstance(node, yaml.SequenceNode):
        out = YList(line)
        for item in node.value:
            out.append(_build(item, depth + 1))
        return out
    if isinstance(node, yaml.MappingNode):
        out = YMap(line)
        for knode, vnode in node.value:
            if not isinstance(knode, yaml.ScalarNode):
                raise YAMLShapeError("non-scalar mapping key", knode.start_mark.line + 1)
            if knode.tag == "tag:yaml.org,2002:merge" or knode.value == "<<":
                raise YAMLShapeError("merge key '<<' is not supported", knode.start_mark.line + 1)
            key = knode.value
            if key in out:
                raise YAMLShapeError(f"duplicate key {key!r}", knode.start_mark.line + 1)
            out[key] = _build(vnode, depth + 1)
            out.key_lines[key] = knode.start_mark.line + 1
        return out
    raise YAMLShapeError(f"unrecognized node type {type(node).__name__}", line)


def load(data: bytes):
    """Parse a single YAML document. Raises YAMLShapeError on any problem."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise YAMLShapeError(f"not UTF-8: {e.reason}", None) from None
    try:
        nodes = list(yaml.compose_all(text, Loader=yaml.SafeLoader))
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        raise YAMLShapeError(f"YAML error: {getattr(e, 'problem', None) or e}", mark.line + 1 if mark else None) from None
    except RecursionError:
        raise YAMLShapeError("YAML recursion limit", None) from None
    if len(nodes) != 1 or nodes[0] is None:
        raise YAMLShapeError(f"expected exactly one YAML document, found {len([n for n in nodes if n is not None])}", None)
    return _build(nodes[0])


def line_of(value, default=None):
    return getattr(value, "line", default)
