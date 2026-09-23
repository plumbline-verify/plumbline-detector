from unittest import mock

import pytest

from pkg import calc


@pytest.mark.timeout(5)
def test_mean():
    assert calc.mean([1, 2]) == pytest.approx(1.5, rel=1e-6)


def test_speed():
    assert calc.elapsed() < 0.5


def test_parse():
    assert calc.parse("1") == 1


def test_total():
    assert calc.total([1, 2]) == 3
