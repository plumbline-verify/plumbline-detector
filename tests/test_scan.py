"""History scan: a period's merged changes are scanned, triaged by an
analyst, and reported; the report refuses an incomplete triage sheet."""

import csv
import os
import subprocess

from plumbline_detector import scan

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures", "pr")
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def _repo(tmp_path, case):
    repo = tmp_path / "r"
    subprocess.run(["cp", "-r", os.path.join(FIX, case, "base"), str(repo)], check=True)

    def git(*a):
        subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, env=ENV)

    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base", "--date", "2026-01-01T00:00:00")
    subprocess.run(["cp", "-r", os.path.join(FIX, case, "head") + "/.", str(repo)], check=True)
    git("add", "-A")
    git("commit", "-qm", "head", "--date", "2026-02-01T00:00:00")
    return str(repo)


def test_scan_flags_the_weakening_change_and_reports_after_triage(tmp_path):
    repo, out = _repo(tmp_path, "loosen-bad"), str(tmp_path / "out")
    assert scan.main(["run", repo, "--since", "2000-01-01", "--out", out]) == 0
    rows = list(csv.DictReader(open(os.path.join(out, "triage.csv"))))
    assert len(rows) == 1  # one merged change after the root, flagged
    checks = set(rows[0]["checks"].split())
    assert {"PR-TOLERANCE-LOOSENED", "PR-TIMEOUT-RAISED", "PR-TESTS-EXCLUDED"} <= checks
    html_out = str(tmp_path / "r.html")
    # an untriaged sheet is refused
    assert scan.main(["report", out, "--triage", os.path.join(out, "triage.csv"), "--target", "T", "-o", html_out]) == 2
    rows[0]["verdict"] = "weakening"
    with open(os.path.join(out, "triage.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert scan.main(["report", out, "--triage", os.path.join(out, "triage.csv"), "--target", "T", "-o", html_out]) == 0
    text = open(html_out).read()
    assert "1 of 1 (100.00%)" in text and "Evidence Read: T" in text


def test_honest_change_is_not_flagged(tmp_path):
    repo, out = _repo(tmp_path, "loosen-good"), str(tmp_path / "out")
    assert scan.main(["run", repo, "--since", "2000-01-01", "--out", out]) == 0
    assert list(csv.DictReader(open(os.path.join(out, "triage.csv")))) == []
