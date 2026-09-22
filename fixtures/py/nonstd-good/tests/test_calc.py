import pytest

from pkg.calc import add


def test_add():
    assert add(2, 3) == 5, "sum"
    assert add(1, 1) == add(1, 1)


def test_raises():
    with pytest.raises(TypeError) as exc:
        add(1, None)
    assert "unsupported" in str(exc.value)


def test_assert_inside_raises_is_the_raiser():
    with pytest.raises(AssertionError):
        value = add(1, 1)
        assert value == 3
