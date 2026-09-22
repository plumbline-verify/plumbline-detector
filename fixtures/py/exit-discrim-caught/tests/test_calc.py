import sys

from pkg.calc import add


def test_exit_is_captured():
    try:
        sys.exit(0)
    except SystemExit as exc:
        info = exc
    assert info.code == 0
    assert add(1, 1) == 2
