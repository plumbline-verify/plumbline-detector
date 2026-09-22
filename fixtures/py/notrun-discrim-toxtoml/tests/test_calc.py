import pytest

from pkg.calc import add


def test_add():
    assert add(2, 3) == 5


@pytest.mark.stress
def test_many():
    for i in range(1000):
        assert add(i, i) == 2 * i
