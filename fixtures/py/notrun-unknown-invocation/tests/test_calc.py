from pkg.calc import add


def test_add():
    assert add(2, 3) == 5


def test_overflow():
    assert add(2**63, 1) == 2**63 + 1
