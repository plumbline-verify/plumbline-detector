"""Extract code changes from TRACE trajectories (docs/RECALL_STUDY.md).

Replays each trajectory's simulated Claude Code tool calls (Read, Write,
Edit, MultiEdit, Bash) in order and keeps a per-file state: unknown, or
known in full. Produces, per trajectory:

  files   per changed file: first known content (or None), final content
          (or None), status (added / modified / removed), reconstructable,
          net patch (unified diff, first known state to final state; bare
          hunks in order when the start is unknown)
  events  per Write / Edit / deletion: its own patch (the per-edit unit)
  context full content of files read but never changed
  unreconstructed  Bash commands that changed files in ways not replayed

Also parses TRACE labels into the paper's taxonomy (parse_label). Nothing
here reads detector output.

Usage: python tools/trace_extract.py --parquet train.parquet --out extract.jsonl
"""

from __future__ import annotations

import argparse
import difflib
import json
import posixpath
import re
import shlex

TAXONOMY = {
    "Test Modification": ["Direct Overwriting", "Assertion Weakening", "Test Deletion", "Test Mocking", "Exception Suppression", "Timeout Manipulation"],
    "Test Case Targeting": ["Hardcoded Outputs", "Input Recognition", "Regex Matching", "Checksum Gaming", "Type Coercion", "Boundary Value Gaming"],
    "Coverage Gaming": ["Partial Implementation", "Branch Pruning", "Edge Case Omission", "Error Path Skipping", "Dead Code Insertion"],
    "Degenerate Implementations": ["Lookup Tables", "If-Else Explosion", "Copy-Paste Replication", "Goto Spaghetti", "Magic Number Hardcoding", "String Concat Abuse"],
    "Complexity Gaming": ["Algorithmic Inefficiency", "Memory Bloat", "Recursive Overflow", "Redundant Computation", "Premature Optimization"],
    "Style Manipulation": ["Comment Flooding", "Whitespace Inflation", "Variable Name Verbosity", "Import Overload", "Docstring Over-Padding", "Type Hint Gaming"],
    "Information Leakage": ["Problem Description Mining", "Example Code Copying", "Variable Name Inference", "Similar Problem Retrieval", "Metadata Mining"],
    "Tool Abuse": ["LLM Self-Reference", "Web Search Exploitation", "Compiler Error Parsing", "Debugger Manipulation"],
    "Runtime Manipulation": ["Global State Pollution", "Cache Poisoning", "File System Gaming", "Network Calls", "System Call Abuse", "Process Manipulation"],
    "Timing/Resource Exploitation": ["Race Conditions", "Memory Aliasing", "Interrupt Handling", "Resource Exhaustion", "Lazy Evaluation"],
}
TSE = ("Test Modification", "Test Case Targeting", "Coverage Gaming")
BENIGN = {"benign", "none", "nohack", "clean", "nothacked", ""}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


# Amendment 1 (docs/RECALL_STUDY.md): TRACE labels are the paper's Appendix G
# section numbers, "0" for benign.
CODES = {
    "1.1.1": "Test Modification", "1.1.2": "Test Case Targeting", "1.1.3": "Coverage Gaming",
    "1.2.1": "Degenerate Implementations", "1.2.2": "Complexity Gaming", "1.2.3": "Style Manipulation",
    "1.3.1": "Information Leakage", "1.3.2": "Tool Abuse",
    "1.4.1": "Runtime Manipulation", "1.4.2": "Timing/Resource Exploitation",
}
_SUB = {_norm(s): (cat, s) for cat, subs in TAXONOMY.items() for s in subs}
_CAT = {_norm(c): c for c in TAXONOMY}


def _label_values(label):
    if label is None:
        return [""]
    try:
        v = json.loads(label)
    except (TypeError, ValueError):
        return [x.strip() for x in re.split(r"[,;|\n]", str(label))]
    out = []

    def walk(x):
        if isinstance(x, dict):
            for k, y in x.items():
                out.append(str(k)) if isinstance(y, bool) and y else None
                walk(y) if not isinstance(y, bool) else None
        elif isinstance(x, list):
            for y in x:
                walk(y)
        elif x is not None and not isinstance(x, bool):
            out.extend(s.strip() for s in re.split(r"[,;|\n]", str(x)))
    walk(v)
    return out or [""]


def parse_label(label) -> dict:
    """{'values': [...], 'benign': bool, 'categories': [...], 'subcategories': [...], 'unmapped': [...]}"""
    vals = _label_values(label)
    cats, subs, unmapped, benign = set(), set(), [], False
    for v in vals:
        n = _norm(v)
        if v.strip() in CODES:
            cats.add(CODES[v.strip()])
        elif v.strip() == "0" or n in BENIGN:
            benign = True
        elif n in _SUB:
            cats.add(_SUB[n][0])
            subs.add(_SUB[n][1])
        elif n in _CAT:
            cats.add(_CAT[n])
        else:
            unmapped.append(v)
    return {"values": vals, "benign": benign and not cats, "categories": sorted(cats), "subcategories": sorted(subs), "unmapped": unmapped}


# ---- extraction -------------------------------------------------------------

LINE_PREFIX = re.compile(r"^\s*\d+(\t|→)")
ERROR_RE = re.compile(r"^\s*(Error\b|<tool_use_error>|File not found\b|File does not exist\b)|edit failed|has not been read yet|old_string not found|String to replace not found|No such file or directory|Permission denied", re.I)


def _strip_read(out: str):
    lines = out.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if lines and all(LINE_PREFIX.match(l) or not l.strip() for l in lines) and any(LINE_PREFIX.match(l) for l in lines):
        return "\n".join(LINE_PREFIX.sub("", l, count=1) for l in lines) + "\n"
    return out if out.endswith("\n") else out + "\n"


def _lines(s: str | None) -> list:
    return [l if l.endswith("\n") else l + "\n" for l in (s or "").splitlines(True)]


def _diff(a: str | None, b: str | None, path: str) -> str:
    return "".join(difflib.unified_diff(_lines(a), _lines(b), "a/" + path, "b/" + path, n=0))


def _split_shell(cmd: str) -> list:
    """Split on &&, ||, ;, | and newlines outside quotes."""
    parts, buf, quote, i = [], [], None, 0
    while i < len(cmd):
        ch = cmd[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < len(cmd):
                buf.append(cmd[i:i + 2])
                i += 2
                continue
            if ch == quote:
                quote = None
            buf.append(ch)
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch in ";|\n" or cmd.startswith("&&", i):
            parts.append("".join(buf))
            buf = []
            if cmd.startswith("&&", i) or cmd.startswith("||", i):
                i += 1
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


class File:
    def __init__(self):
        self.known = None       # current full content, or None if unknown
        self.base = None        # first known content before the first change
        self.read_before_change = False
        self.changed = False
        self.existed = None     # True if known to exist before first change
        self.created = False
        self.removed = False
        self.reconstructable = True
        self.hunks = []         # bare hunks, used when base is unknown


class Replay:
    def __init__(self):
        self.files: dict[str, File] = {}
        self.events = []
        self.unreconstructed = []
        self.cwd = None
        self.root = None  # each Bash call starts here; cd applies within the call

    def path(self, p: str) -> str:
        p = p.strip().strip("'\"")
        if not p.startswith("/") and not p.startswith("~") and self.cwd:
            p = posixpath.join(self.cwd, p)
        return posixpath.normpath(p).lstrip("/")

    def f(self, p) -> File:
        return self.files.setdefault(p, File())

    def _first_change(self, fl: File):
        if not fl.changed:
            fl.changed = True
            fl.base = fl.known
            fl.existed = fl.known is not None or fl.read_before_change

    def read(self, p, params, out):
        if ERROR_RE.search(out[:200]) or params.get("offset") or params.get("limit") or "truncated" in out[-300:].lower():
            return
        fl = self.f(p)
        fl.known = _strip_read(out)
        if not fl.changed:
            fl.read_before_change = True

    def write(self, p, content, append=False):
        fl = self.f(p)
        before = fl.known
        if not fl.changed and before is None and not fl.read_before_change:
            fl.created = not append
        self._first_change(fl)
        if append:
            if before is None:
                fl.reconstructable = False
                fl.hunks.append("".join("+" + l for l in content.splitlines(True)))
                self.events.append({"path": p, "status": "modified", "patch": fl.hunks[-1]})
                return
            content = before + content
        fl.known = content
        fl.removed = False
        st = "added" if before is None and fl.created else "modified"
        self.events.append({"path": p, "status": st, "patch": _diff(before, content, p)})
        if before is None and not fl.created:
            fl.hunks.append(_diff(None, content, p))

    def edit(self, p, old, new, replace_all=False):
        fl = self.f(p)
        self._first_change(fl)
        hunk = _diff(old, new, p)
        self.events.append({"path": p, "status": "modified", "patch": hunk})
        if fl.known is not None and old and old in fl.known:
            fl.known = fl.known.replace(old, new) if replace_all else fl.known.replace(old, new, 1)
        else:
            fl.reconstructable = False
            fl.known = None
            fl.hunks.append(hunk)

    def remove(self, p):
        targets = [p]
        if any(c in p for c in "*?["):
            import fnmatch
            targets = [k for k in self.files if fnmatch.fnmatch(k, p)]
        else:
            targets += [k for k in self.files if k.startswith(p.rstrip("/") + "/")]
        for t in targets:
            fl = self.f(t)
            self._first_change(fl)
            self.events.append({"path": t, "status": "removed", "patch": _diff(fl.known, None, t)})
            fl.removed = True
            fl.known = None

    def taint(self, p, cmd):
        fl = self.f(p)
        self._first_change(fl)
        fl.reconstructable = False
        fl.known = None
        if cmd[:200] not in self.unreconstructed:
            self.unreconstructed.append(cmd[:200])

    # Bash --------------------------------------------------------------
    HEREDOC = re.compile(r"cat\s*(?:(>>?)\s*(\S+)\s*<<-?\s*['\"]?(\w+)['\"]?|<<-?\s*['\"]?(\w+)['\"]?\s*(>>?)\s*(\S+))[^\n]*\n(.*?)\n\s*(?:\3|\4)\s*(?:\n|$)", re.S)

    def bash(self, cmd, out):
        self.cwd = self.root
        rest = cmd
        for m in self.HEREDOC.finditer(cmd):
            op, path, body = (m.group(1) or m.group(5)), (m.group(2) or m.group(6)), m.group(7)
            self._cds(cmd[: m.start()])
            self.write(self.path(path), body + "\n", append=op == ">>")
        rest = self.HEREDOC.sub("\n", cmd)
        # strip other heredoc bodies (python << EOF, git commit -m "$(cat <<EOF ...)")
        rest = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?\n\s*\1\b", " ", rest, flags=re.S)
        for part in _split_shell(rest):
            self._simple(part.strip(), cmd)

    def _cds(self, text):
        self.cwd = self.root
        for part in _split_shell(text):
            w = part.strip().split()
            if len(w) >= 2 and w[0] == "cd":
                self.cwd = "/" + self.path(w[1])

    def _simple(self, part, cmd):
        try:
            w = shlex.split(part, comments=False)
        except ValueError:
            w = part.split()
        if not w:
            return
        if w[0] == "sudo":
            w = w[1:] or [""]
        verb = w[0]
        if verb == "cd" and len(w) >= 2:
            self.cwd = "/" + self.path(w[1])
            return
        args = [a for a in w[1:] if not a.startswith("-")]
        if verb in ("rm", "unlink") or (verb == "git" and w[1:2] == ["rm"]):
            for a in (args[1:] if verb == "git" else args):
                self.remove(self.path(a))
            return
        if verb in ("sed", "perl") and any(a.startswith("-i") or a.startswith("-pi") for a in w[1:]):
            for a in args[1:] if verb == "sed" else args[1:]:
                if "/" in a or "." in a:
                    if not re.match(r"^s[|/#]", a):
                        self.taint(self.path(a), cmd)
            return
        if verb in ("patch",) or (verb == "git" and w[1:2] == ["apply"]):
            self.unreconstructed.append(cmd[:200])
            return
        if verb == "git" and w[1:2] in (["checkout"], ["restore"]) and "-b" not in w:
            paths = w[w.index("--") + 1:] if "--" in w else [a for a in args[1:] if re.search(r"[./]", a) and "/" in a or re.search(r"\.\w+$", a)]
            for a in paths:
                self.taint(self.path(a), cmd)
            return
        if verb in ("cp", "mv") and len(args) >= 2:
            self.taint(self.path(args[-1]), cmd)
            if verb == "mv":
                for a in args[:-1]:
                    self.taint(self.path(a), cmd)
            return
        if verb in ("echo", "printf"):
            m = re.search(r"(?<![0-9&])(>>?)\s*(\S+)\s*$", part)
            if m and m.group(2) != "/dev/null":
                try:
                    body = shlex.split(part[: m.start()])[1:]
                    text = " ".join(a for a in body if not (verb == "echo" and a in ("-e", "-n")))
                    if verb == "printf":
                        text = text.replace("\\n", "\n")
                    self.write(self.path(m.group(2)), text + ("" if verb == "printf" else "\n"), append=m.group(1) == ">>")
                except ValueError:
                    self.taint(self.path(m.group(2)), cmd)
            return
        if verb == "tee":
            for a in args:
                self.taint(self.path(a), cmd)
            return
        m = re.search(r"(?<![0-9&<])(>>?)\s*([^\s&|;]+)\s*$", part)
        if m and m.group(2) not in ("/dev/null",) and not m.group(2).startswith("&"):
            self.taint(self.path(m.group(2)), cmd)
        if verb.startswith("python") and "-c" in w:
            for p in re.findall(r"open\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][wa]", part):
                self.taint(self.path(p), cmd)

    def python_heredoc_writes(self, cmd):
        for p in re.findall(r"open\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][wa]", cmd):
            self.taint(self.path(p), cmd)


def _session_root(msgs):
    """Where relative Bash paths resolve: the first absolute cd target, else
    the deepest directory shared by the absolute file paths of tool calls."""
    paths = []
    for m in msgs:
        for call in m.get("tool_calls") or []:
            p = call.get("parameters") or {}
            if call.get("name") == "Bash":
                for part in _split_shell(p.get("command", "")):
                    w = part.strip().split()
                    if len(w) >= 2 and w[0] == "cd" and w[1].startswith("/"):
                        return posixpath.normpath(w[1].strip("'\""))
            elif str(p.get("file_path", "")).startswith("/"):
                paths.append(posixpath.dirname(p["file_path"]))
    return posixpath.commonpath(paths) if paths else None


def replay(conversation: str) -> dict:
    msgs = json.loads(conversation)
    r = Replay()
    r.root = _session_root(msgs)
    n_calls = 0
    for m in msgs:
        calls = m.get("tool_calls") or []
        results = m.get("tool_results") or []
        for i, call in enumerate(calls):
            n_calls += 1
            name, p = call.get("name"), call.get("parameters") or {}
            out = (results[i].get("output") if i < len(results) and isinstance(results[i], dict) else None) or ""
            if not isinstance(out, str):
                out = "\n".join(x if isinstance(x, str) else json.dumps(x) for x in out) if isinstance(out, list) else json.dumps(out)
            failed = bool(out) and bool(ERROR_RE.search(out[:200]))
            if name == "Read" and p.get("file_path"):
                r.read(r.path(p["file_path"]), p, out)
            elif name == "Write" and p.get("file_path") and not failed:
                r.write(r.path(p["file_path"]), p.get("content", ""))
            elif name == "Edit" and p.get("file_path") and not failed:
                r.edit(r.path(p["file_path"]), p.get("old_string", ""), p.get("new_string", ""), bool(p.get("replace_all")))
            elif name == "MultiEdit" and p.get("file_path") and not failed:
                for e in p.get("edits", []):
                    r.edit(r.path(p["file_path"]), e.get("old_string", ""), e.get("new_string", ""), bool(e.get("replace_all")))
            elif name == "Bash" and p.get("command"):
                if not failed:
                    r.bash(p["command"], out)
                    if re.search(r"\bpython3?\b[^\n]*<<", p["command"]):
                        r.python_heredoc_writes(p["command"])
                else:
                    r._cds(p["command"])
    files, context = [], []
    for path, fl in r.files.items():
        if not fl.changed:
            if fl.known is not None:
                context.append({"path": path, "content": fl.known})
            continue
        status = "removed" if fl.removed else ("added" if fl.created else "modified")
        if fl.removed and fl.created:
            continue  # created and deleted within the trajectory: no net change
        start_known = fl.base is not None or fl.created
        recon = fl.reconstructable and start_known and (fl.removed or fl.known is not None)
        if start_known and fl.reconstructable:
            patch = _diff(fl.base, None if fl.removed else fl.known, path)
        else:
            patch = "".join(fl.hunks) if not fl.removed else _diff(fl.base, None, path)
        if status == "modified" and not recon and not patch:
            patch = ""
        files.append({"path": path, "status": status, "reconstructable": recon, "base": fl.base, "head": None if fl.removed else fl.known, "patch": patch})
    return {"n_tool_calls": n_calls, "files": files, "events": r.events, "context": context, "unreconstructed": r.unreconstructed}


def main():
    import pyarrow.parquet as pq

    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--labels-out", help="write parsed labels here (separate file; never joined by this tool)")
    a = ap.parse_args()
    t = pq.read_table(a.parquet, columns=["trajectory_id", "conversation"])
    with open(a.out, "w") as out:
        for tid, conv in zip(t.column("trajectory_id").to_pylist(), t.column("conversation").to_pylist()):
            rec = replay(conv)
            rec["trajectory_id"] = tid
            out.write(json.dumps(rec) + "\n")
    if a.labels_out:
        lt = pq.read_table(a.parquet, columns=["trajectory_id", "label"])
        with open(a.labels_out, "w") as out:
            for tid, lab in zip(lt.column("trajectory_id").to_pylist(), lt.column("label").to_pylist()):
                out.write(json.dumps({"trajectory_id": tid, "raw": lab, **parse_label(lab)}) + "\n")


if __name__ == "__main__":
    main()
