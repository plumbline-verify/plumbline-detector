import pytest

from pkg.calc import Box, add


def test_items_cached():
    box = Box()
    assert box.items is box.items


def test_not_called():
    try:
        assert add(1, 1) == 3
    except AssertionError:
        pass
    else:
        raise AssertionError("expected the comparison to fail")


def test_records_failure():
    failures = []
    try:
        assert add(1, 1) == 2
    except AssertionError as exc:
        failures.append(exc)
    assert not failures


def test_raise_after_assert():
    with pytest.raises(RuntimeError):
        add(1, 1)
        assert add(2, 2) == 4
        raise RuntimeError("expected")
