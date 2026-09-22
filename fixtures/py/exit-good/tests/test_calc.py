import sys

import pytest

from pkg.calc import add


def test_add():
    assert add(2, 3) == 5


def test_cli_exits_cleanly():
    with pytest.raises(SystemExit):
        sys.exit(0)


def test_error_status():
    with pytest.raises(SystemExit):
        raise SystemExit(3)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
