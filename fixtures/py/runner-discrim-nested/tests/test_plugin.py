import pytest

from pkg.calc import add


def test_add():
    assert add(2, 3) == 5


def test_hook_registration(pytester):
    """Exercises hook ordering on a nested pytester session, not this one."""

    class Short:
        def pytest_pyfunc_call(self):
            return True

    item = pytester.getitem("def test_func(): raise ValueError")
    item.config.pluginmanager.register(Short())
    assert item.config.hook.pytest_pyfunc_call(pyfuncitem=item)


def test_raises_reports_missing_exception():
    try:
        pytest.raises(ValueError, add, 1, 2)
    except pytest.fail.Exception:
        pass
    else:
        pytest.fail("expected pytest.raises to fail")
