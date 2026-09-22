"""US spelling check for prose, dictionary-based (no hand-assembled word list).

A word is flagged as a British spelling when all of these hold:
  * hunspell's en_US dictionary rejects it and en_GB accepts it,
  * it has at least five letters,
  * en_US suggests a single word, accepted by en_US, one edit away, with the
    same first and last letter, and either
      - en_GB rejects that suggestion (a strict regional pair:
        `colour`/`color`, `cancelled`/`canceled`), or
      - the edit is s->z or c->s (`organise`/`organize`,
        `licence`/`license`), which en_GB's Oxford spellings accept both ways.
No word list is involved: every judgment comes from the two dictionaries
plus those two substitution rules.
Prose only: Markdown outside code spans and fenced blocks, and Python
comments and docstrings outside backtick spans. Code identifiers and API
tokens (GitHub's `cancelled()`) are literal and not checked.
Requires hunspell with en_US and en_GB dictionaries. Exit 1 on findings.
"""

import ast
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORD = re.compile(r"[A-Za-z]{3,}")


def md_prose(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    return re.sub(r"`[^`]*`", " ", text)


def py_prose(text):
    out = []
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                doc = ast.get_docstring(node)
                if doc:
                    out.append(doc)
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                out.append(tok.string)
    except (SyntaxError, tokenize.TokenError):
        return ""
    return re.sub(r"`[^`]*`", " ", "\n".join(out))


def hunspell_list(words, lang):
    p = subprocess.run(["hunspell", "-d", lang, "-l"], input="\n".join(words), capture_output=True, text=True, check=True)
    return set(p.stdout.split())


def suggestions(words):
    p = subprocess.run(["hunspell", "-d", "en_US", "-a"], input="\n".join(words), capture_output=True, text=True, check=True)
    out = {}
    for line in p.stdout.splitlines():
        if line.startswith("& "):
            head, _, sugg = line.partition(": ")
            out[head.split()[1]] = [s.strip() for s in sugg.split(",")]
    return out


def dist(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _sub(a, b):
    """The (from, to) characters if b is a one-character substitution of a."""
    if len(a) != len(b):
        return None
    diffs = [(x, y) for x, y in zip(a, b) if x != y]
    return diffs[0] if len(diffs) == 1 else None


def main():
    files = subprocess.run(["git", "ls-files", "*.md", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    prose = {}
    for f in files:
        if f.startswith("fixtures/"):
            continue
        text = (ROOT / f).read_text(encoding="utf-8")
        prose[f] = md_prose(text) if f.endswith(".md") else py_prose(text)
    words = sorted({w.lower() for t in prose.values() for w in WORD.findall(t)})
    not_us = sorted(hunspell_list(words, "en_US"))
    in_gb = [w for w in not_us if w not in hunspell_list(not_us, "en_GB")]
    sugg = suggestions(in_gb)
    flagged = {}
    for w in in_gb:
        if len(w) < 5:
            continue
        cands = [
            x
            for x in sugg.get(w, [])
            if " " not in x and "-" not in x and x[0].lower() == w[0] and x[-1].lower() == w[-1] and dist(w, x.lower()) == 1
        ]
        cands = [x for x in cands if x not in hunspell_list([x], "en_US")]
        for x in cands:
            if x in hunspell_list([x], "en_GB") or _sub(w, x.lower()) in (("s", "z"), ("c", "s")):
                flagged[w] = x
                break
    if flagged:
        print("British spellings in prose:")
        for f, t in prose.items():
            for n, line in enumerate(t.splitlines(), 1):
                for w in WORD.findall(line):
                    if w.lower() in flagged:
                        print(f"  {f}:{n}: {w} (en_US suggests {flagged[w.lower()]})")
        return 1
    print(f"US spelling check: OK ({len(words)} distinct words in prose)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
