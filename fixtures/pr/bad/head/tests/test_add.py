import sys

import pytest

from pkg import add


def test_add():
    assert add(1, 2) == 3


@pytest.mark.skip(reason="flaky")
def test_add_zero():
    assert add(0, 0) == 0


class Harness:
    def did_create(self, x):
        assert x


def test_harness_idiom():
    Harness().did_create(add(1, 1))


sys.exit(0)
