import pytest

from pkg.calc import add


def test_add():
    assert add(2, 3) == 5


@pytest.mark.slow
def test_big():
    assert add(10**6, 10**6) == 2 * 10**6
