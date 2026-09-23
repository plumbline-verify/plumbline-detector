"""The TRACE extractor replays tool calls as docs/RECALL_STUDY.md fixes."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import trace_extract  # noqa: E402


def _conv(calls, results):
    return json.dumps([{"role": "assistant", "content": "", "tool_calls": calls, "tool_results": [{"output": o} for o in results]}])


def test_replay_reconstructs_reads_edits_writes_and_bash():
    calls = [
        {"name": "Read", "parameters": {"file_path": "/p/tests/test_a.py"}},
        {"name": "Edit", "parameters": {"file_path": "/p/tests/test_a.py", "old_string": "    assert f(1) == 2\n", "new_string": "    assert True\n"}},
        {"name": "Edit", "parameters": {"file_path": "/p/src/x.py", "old_string": "a=1", "new_string": "a=2"}},
        {"name": "Bash", "parameters": {"command": "cd /p && rm tests/test_b.py && cat > tests/test_c.py << 'EOF'\ndef test_c():\n    pass\nEOF\nsed -i 's/x/y/' src/y.py && git commit -m \"$(cat <<'EOF'\nrm tests/test_z.py\nEOF\n)\""}},
        {"name": "Edit", "parameters": {"file_path": "/p/tests/test_e.py", "old_string": "x", "new_string": "y"}},
        {"name": "Bash", "parameters": {"command": "python3 -c \"\nprint('a' > 'b')\nrm = 1\""}},
    ]
    results = ["     1\tdef test_a():\n     2\t    assert f(1) == 2\n", "ok", "ok", "", "Error: File has not been read yet.", ""]
    r = trace_extract.replay(_conv(calls, results))
    files = {f["path"]: f for f in r["files"]}
    assert files["p/tests/test_a.py"]["reconstructable"]
    assert files["p/tests/test_a.py"]["base"] == "def test_a():\n    assert f(1) == 2\n"
    assert files["p/tests/test_a.py"]["head"] == "def test_a():\n    assert True\n"
    assert not files["p/src/x.py"]["reconstructable"] and "-a=1\n+a=2\n" in files["p/src/x.py"]["patch"]
    assert files["p/tests/test_b.py"]["status"] == "removed"
    assert files["p/tests/test_c.py"]["status"] == "added"
    assert not files["p/src/y.py"]["reconstructable"]
    assert "p/tests/test_e.py" not in files  # failed edit is not applied
    assert "p/tests/test_z.py" not in files  # text inside a commit message is not a command
    assert len(r["events"]) == 4


def test_labels_map_to_taxonomy():
    p = trace_extract.parse_label('["Assertion Weakening", "Hardcoded Outputs"]')
    assert p["categories"] == ["Test Case Targeting", "Test Modification"] and not p["benign"]
    assert trace_extract.parse_label("benign")["benign"]
    assert trace_extract.parse_label("something else")["unmapped"] == ["something else"]
