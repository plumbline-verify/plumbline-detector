import unittest

import pytest

from pkg.calc import add


def test_add():
    assert add(2, 3) == 5


@pytest.mark.skip(reason="flaky")
def test_negative():
    assert add(-1, -1) == -2


@pytest.mark.skipif(True, reason="later")
def test_zero():
    assert add(0, 0) == 0


def test_large():
    pytest.skip("too slow")
    assert add(10**9, 1) == 10**9 + 1


class TestAdd(unittest.TestCase):
    @unittest.skip("broken")
    def test_float(self):
        self.assertEqual(add(0.1, 0.2), 0.3)
