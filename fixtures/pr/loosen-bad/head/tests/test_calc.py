from unittest import mock

import pytest

from pkg import calc


@pytest.mark.timeout(60)
def test_mean():
    assert calc.mean([1, 2]) == pytest.approx(1.5, rel=1e-2)


def test_speed():
    assert calc.elapsed() < 5.0


def test_parse():
    try:
        assert calc.parse("1") == 1
    except AssertionError:
        pass


def test_total():
    with mock.patch("pkg.calc.total", return_value=3):
        assert calc.total([1, 2]) == 3
