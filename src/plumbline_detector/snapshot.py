"""Read-only view of a repository snapshot on disk.

The snapshot is walked in sorted order, symlinks are never followed, and
nothing outside the root is read (the one exception is a `.git` file whose
gitdir pointer is honored only if it resolves inside the root). Files that
cannot be read are recorded, never silently dropped: a check whose domain
contains an unread file cannot return PASS.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import PurePosixPath

# Directory names excluded from analysis. These hold installed third-party
# code or tool caches, not the repository's own evidence. Every exclusion is
# counted in the record so a reader can see what was not examined.
EXCLUDED_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        ".nox",
        "__pycache__",
        "site-packages",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".eggs",
    }
)

MAX_FILE_BYTES = 4 * 1024 * 1024

# Extension -> language. Allowlist: files with other extensions are counted
# as "other" and are not analyzed.
LANGUAGE_BY_EXT = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".java": "java",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".php": "php",
    ".scala": "scala",
}

_HEX_SHA = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")


@dataclass
class Snapshot:
    root: str
    files: dict[str, bytes] = field(default_factory=dict)  # relpath -> content
    unread: dict[str, str] = field(default_factory=dict)  # relpath -> reason
    excluded_dir_count: int = 0
    symlink_count: int = 0

    def paths(self):
        return sorted(self.files)

    def all_paths(self):
        return sorted(set(self.files) | set(self.unread))

    def content_id(self) -> str:
        """Content address of the snapshot: sha256 over sorted (path, sha256)
        pairs of every file considered, including unread markers. Independent
        of directory location, mtimes and ownership."""
        h = hashlib.sha256()
        for p in self.all_paths():
            h.update(p.encode("utf-8", "surrogateescape"))
            h.update(b"\0")
            if p in self.files:
                h.update(hashlib.sha256(self.files[p]).hexdigest().encode())
            else:
                h.update(b"unread:" + self.unread[p].encode())
            h.update(b"\n")
        return "sha256:" + h.hexdigest()


def load(root: str) -> Snapshot:
    if not os.path.isdir(root):
        raise NotADirectoryError(root)
    snap = Snapshot(root=os.path.abspath(root))
    for dirpath, dirnames, filenames in os.walk(snap.root, followlinks=False):
        kept = []
        for d in sorted(dirnames):
            full = os.path.join(dirpath, d)
            if d in EXCLUDED_DIRS:
                snap.excluded_dir_count += 1
            elif os.path.islink(full):
                snap.symlink_count += 1
            else:
                kept.append(d)
        dirnames[:] = kept
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = PurePosixPath(os.path.relpath(full, snap.root).replace(os.sep, "/")).as_posix()
            try:
                st = os.lstat(full)
            except OSError as e:
                snap.unread[rel] = f"stat_error:{type(e).__name__}"
                continue
            if stat.S_ISLNK(st.st_mode):
                snap.symlink_count += 1
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            if st.st_size > MAX_FILE_BYTES:
                snap.unread[rel] = "size_limit"
                continue
            try:
                with open(full, "rb") as fh:
                    data = fh.read(MAX_FILE_BYTES + 1)
            except OSError as e:
                snap.unread[rel] = f"read_error:{type(e).__name__}"
                continue
            if len(data) > MAX_FILE_BYTES:
                snap.unread[rel] = "size_limit"
                continue
            snap.files[rel] = data
    return snap


def language_of(path: str) -> str | None:
    return LANGUAGE_BY_EXT.get(PurePosixPath(path).suffix.lower())


def inventory(snap: Snapshot, test_path_pred) -> dict:
    langs: dict[str, dict] = {}
    loc_total = 0
    test_files = 0
    for p, data in snap.files.items():
        lang = language_of(p)
        if lang is None:
            continue
        loc = sum(1 for line in data.splitlines() if line.strip())
        slot = langs.setdefault(lang, {"files": 0, "loc": 0, "test_files": 0})
        slot["files"] += 1
        slot["loc"] += loc
        loc_total += loc
        if test_path_pred(p):
            slot["test_files"] += 1
            test_files += 1
    primary = None
    if langs:
        primary = sorted(langs.items(), key=lambda kv: (-kv[1]["loc"], kv[0]))[0][0]
    return {
        "languages": dict(sorted(langs.items())),
        "primary_language": primary,
        "loc_nonblank_total": loc_total,
        "test_file_count": test_files,
        "file_count": len(snap.files),
        "unread_files": [{"file": k, "reason": v} for k, v in sorted(snap.unread.items())],
        "excluded_dir_count": snap.excluded_dir_count,
        "symlinks_not_followed": snap.symlink_count,
    }


def _read_inside(root: str, rel: str) -> str | None:
    full = os.path.realpath(os.path.join(root, rel))
    if not (full == root or full.startswith(root + os.sep)):
        return None
    try:
        with open(full, "r", encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def commit_sha(root: str) -> tuple[str | None, str]:
    """Return (sha, source). Reads .git metadata directly; never runs git."""
    root = os.path.realpath(root)
    gitdir = os.path.join(root, ".git")
    if os.path.isfile(gitdir):
        txt = _read_inside(root, ".git")
        if not txt or not txt.startswith("gitdir:"):
            return None, "unreadable_git_file"
        target = os.path.realpath(os.path.join(root, txt[len("gitdir:"):].strip()))
        if not target.startswith(root + os.sep):
            return None, "gitdir_outside_snapshot"
        gitdir = target
    if not os.path.isdir(gitdir):
        return None, "no_git_metadata"
    rel_gitdir = os.path.relpath(gitdir, root)
    head = _read_inside(root, os.path.join(rel_gitdir, "HEAD"))
    if head is None:
        return None, "unreadable_head"
    head = head.strip()
    if _HEX_SHA.match(head):
        return head, "git_head_detached"
    if not head.startswith("ref:"):
        return None, "unrecognized_head"
    ref = head[4:].strip()
    loose = _read_inside(root, os.path.join(rel_gitdir, ref))
    if loose is not None and _HEX_SHA.match(loose.strip()):
        return loose.strip(), "git_ref"
    packed = _read_inside(root, os.path.join(rel_gitdir, "packed-refs"))
    if packed:
        for line in packed.splitlines():
            parts = line.strip().split(" ")
            if len(parts) == 2 and parts[1] == ref and _HEX_SHA.match(parts[0]):
                return parts[0], "git_packed_ref"
    return None, "ref_unresolved"
