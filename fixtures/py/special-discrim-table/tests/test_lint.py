from pkg.lint import is_probe


def test_is_probe():
    assert is_probe("PYTEST_CURRENT_TEST")
    assert not is_probe("PATH")
