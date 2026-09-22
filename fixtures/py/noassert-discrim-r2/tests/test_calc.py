from functools import partial

import pytest

from pkg.calc import add
from tests.utils import SumChecker, check_sum

verbose_check = partial(check_sum, verbose=True)


def test_partial_helper():
    verbose_check(1, 2, 3)


def test_callable_class():
    SumChecker(4)(2, 2)


def test_fixture_closure(sum_checker):
    sum_checker(3, 3, 6)


def test_raises_group():
    with pytest.RaisesGroup(ValueError):
        raise ExceptionGroup("g", [ValueError(add(1, 1))])
