import sys

import pytest

from pkg.calc import add


def test_add():
    assert add(2, 3) == 5


@pytest.mark.skipif(sys.platform == "win32", reason="posix only")
def test_posix():
    assert add(1, 1) == 2


@pytest.mark.slow
def test_slow():
    assert add(10, 10) == 20
