import unittest
from unittest.mock import Mock

import pytest

from pkg.calc import add


def test_constant():
    add(2, 3)
    assert True


def test_tuple():
    assert (add(2, 3) == 6, "sum should be six")


def test_tautology():
    x = add(2, 3)
    assert x == x


def test_or_true():
    assert add(2, 3) == 6 or True


def test_pseudo_mock():
    m = Mock()
    m(add(1, 2))
    assert m.called_once_with(3)
    m.assert_called_once


def test_swallowed():
    try:
        assert add(2, 3) == 6
    except AssertionError:
        pass


def test_unreachable():
    with pytest.raises(TypeError):
        add(1, None)
        assert False, "never runs"


class TestCalc(unittest.TestCase):
    def test_misused(self):
        self.assertTrue(add(2, 3), 6)
