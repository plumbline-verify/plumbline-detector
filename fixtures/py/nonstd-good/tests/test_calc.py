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


def test_should_have_raised_guard():
    with pytest.raises(TypeError):
        add(1, None)
        assert False, "add should have raised"


def test_reflexive_equality():
    x = add(0.0, float("nan"))
    assert not (x == x)


def test_exception_info():
    try:
        assert False
    except AssertionError as e:
        info = e
    assert info is not None
