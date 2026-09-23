from unittest import mock

import pytest

from pkg import calc


@pytest.mark.timeout(5)
def test_mean():
    assert calc.mean([1, 2]) == pytest.approx(1.5, rel=1e-6)


def test_speed():
    assert calc.elapsed() < 0.5
    assert calc.elapsed() < 10


def test_parse():
    try:
        assert calc.parse("1") == 1
    except AssertionError as e:
        raise AssertionError("parse of '1'") from e


def test_total():
    with mock.patch.object(calc, "total", wraps=calc.total) as spy:
        assert calc.total([1, 2]) == 3
    spy.assert_called_once()


def test_fetch():
    with mock.patch("pkg.calc.fetch", return_value=[1, 2]):
        assert calc.total() == 3
