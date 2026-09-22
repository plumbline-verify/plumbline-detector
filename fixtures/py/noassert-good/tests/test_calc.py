import unittest

import pytest

from pkg.calc import add


def check_sum(a, b, expected):
    assert add(a, b) == expected


def test_add():
    assert add(2, 3) == 5


def test_add_via_helper():
    check_sum(1, 1, 2)


def test_type_error():
    with pytest.raises(TypeError):
        add(1, None)


@pytest.mark.skip(reason="placeholder")
def test_later():
    pass


class TestAdd(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 2), 4)
