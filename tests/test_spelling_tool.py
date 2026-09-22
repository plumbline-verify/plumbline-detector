"""The US-spelling check must itself be able to fail."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent / "tools" / "check_us_spelling.py"

pytestmark = pytest.mark.skipif(shutil.which("hunspell") is None, reason="hunspell (en_US, en_GB) not installed")


def _run(tmp_path, text):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tools").mkdir()
    shutil.copy(TOOL, tmp_path / "tools" / TOOL.name)
    (tmp_path / "doc.md").write_text(text)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return subprocess.run([sys.executable, "tools/" + TOOL.name], cwd=tmp_path, capture_output=True, text=True)


def test_flags_british_spellings(tmp_path):
    p = _run(tmp_path, "The colour and behaviour were analysed; the licence was cancelled. Organise the defence.\n")
    assert p.returncode == 1
    for w in ("colour", "behaviour", "analysed", "licence", "cancelled", "Organise", "defence"):
        assert w in p.stdout, w


def test_accepts_us_spelling_and_code_spans(tmp_path):
    p = _run(tmp_path, "The color was analyzed and canceled. Use `!cancelled()` in workflows.\n")
    assert p.returncode == 0, p.stdout
