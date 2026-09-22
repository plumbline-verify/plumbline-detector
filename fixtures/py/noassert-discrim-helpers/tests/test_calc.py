import functools

from pkg.calc import add
from pkg.testing import eq_


def collect_cases(fn):
    @functools.wraps(fn)
    def test(*args):
        for a, b, expected in fn(*args):
            assert add(a, b) == expected
    return test


@collect_cases
def test_table():
    yield 1, 2, 3
    yield 2, 2, 4


def test_with_library_helper():
    eq_(add(2, 3), 5)


def test_base(n=1):
    assert add(n, n) == 2 * n


def test_delegates():
    test_base(n=5)
