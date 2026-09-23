"""Scan every blob reachable from every ref before a history is made public.

A secret removed in a later commit is still public once the history is
pushed, so this reads each distinct blob in `git rev-list --all --objects`,
not the working tree.

Checks:
  secrets    token and key formats (GitHub, Hugging Face, OpenAI/Anthropic,
             AWS, Slack, Google, private-key blocks, bearer tokens,
             password assignments)
  emails     every address except placeholders (example.*, *.invalid,
             noreply addresses)
  private    literal terms from --private-terms FILE (one per line), kept
             outside the repository: addresses, contact names, sampled
             repository URLs. The file's contents are never printed; a hit
             is reported by term number.
  metadata   the same secret and private-term checks over commit authors
             and messages
  license    LICENSE at HEAD is the full Apache-2.0 text

Exit status 1 on any finding. Output names the blob, a path it appears at
and the rule, never the matched secret itself.

Usage: python tools/prepublish_scan.py [--repo DIR] [--private-terms FILE]
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys

SECRETS = {
    "github-token": re.compile(rb"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}"),
    "hf-token": re.compile(rb"\bhf_[A-Za-z0-9]{30,}"),
    "api-key-sk": re.compile(rb"\bsk-(ant-|proj-)?[A-Za-z0-9_-]{24,}"),
    "aws-access-key": re.compile(rb"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    "slack-token": re.compile(rb"\bxox[abpors]-[A-Za-z0-9-]{10,}"),
    "google-api-key": re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"),
    "private-key": re.compile(rb"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY"),
    "bearer-token": re.compile(rb"(?i)authorization:\s*bearer\s+[A-Za-z0-9._-]{20,}"),
    "password-assignment": re.compile(rb"(?i)\b(password|passwd|secret|api_key|apikey|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
}
EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_OK = re.compile(rb"(@example\.(com|org|net|invalid)|\.invalid$|noreply|no-reply|@users\.noreply\.github\.com$)", re.I)
APACHE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def git(repo, *args, **kw):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, check=True, **kw).stdout


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--private-terms")
    a = ap.parse_args(argv)
    terms = []
    if a.private_terms:
        terms = [t.strip().lower().encode() for t in open(a.private_terms, encoding="utf-8") if t.strip() and not t.startswith("#")]

    paths = {}
    for line in git(a.repo, "rev-list", "--all", "--objects").decode("utf-8", "surrogateescape").splitlines():
        sha, _, path = line.partition(" ")
        if path:
            paths.setdefault(sha, path)
    kinds = git(a.repo, "cat-file", "--batch-check=%(objectname) %(objecttype)", input="\n".join(paths).encode()).decode().splitlines()
    blobs = [l.split()[0] for l in kinds if l.endswith(" blob")]

    findings = []
    for sha in blobs:
        data = git(a.repo, "cat-file", "blob", sha)
        where = paths[sha]
        for name, rx in SECRETS.items():
            if rx.search(data):
                findings.append((where, sha[:10], f"secret:{name}"))
        for m in EMAIL.finditer(data):
            if not EMAIL_OK.search(m.group(0)):
                findings.append((where, sha[:10], "email (address withheld)"))
                break
        low = data.lower()
        for i, t in enumerate(terms, 1):
            if t in low:
                findings.append((where, sha[:10], f"private term #{i}"))

    try:
        lic = git(a.repo, "show", "HEAD:LICENSE")
        if hashlib.sha256(lic).hexdigest() != APACHE_SHA256:
            findings.append(("LICENSE", "HEAD", "license: not the full Apache-2.0 text"))
    except subprocess.CalledProcessError:
        findings.append(("LICENSE", "HEAD", "license: MISSING"))

    meta = git(a.repo, "log", "--all", "--format=%an <%ae>%n%cn <%ce>%n%B").lower()
    for i, t in enumerate(terms, 1):
        if t in meta:
            findings.append(("commit metadata", "-", f"private term #{i}"))
    for name, rx in SECRETS.items():
        if rx.search(meta):
            findings.append(("commit metadata", "-", f"secret:{name}"))

    refs = git(a.repo, "for-each-ref", "--format=%(refname)").decode().split()
    print(f"refs {len(refs)}, blobs scanned {len(blobs)}, private terms {len(terms)}")
    for f in sorted(set(findings)):
        print("  ".join(f))
    print("CLEAN" if not findings else f"{len(set(findings))} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
