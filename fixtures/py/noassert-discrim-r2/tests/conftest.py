import pytest

from pkg.calc import add


@pytest.fixture
def sum_checker():
    def check(a, b, expected):
        assert add(a, b) == expected
    return check
