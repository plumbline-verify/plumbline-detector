import pytest

from pkg.calc import add


def test_add():
    assert add(2, 3) == 5


def test_overflow():
    assert add(2**63, 1) == 2**63 + 1


@pytest.mark.flaky
def test_concurrency():
    assert add(1, 1) == 2


def test_rounding():
    assert add(0.1, 0.2) == 0.3
