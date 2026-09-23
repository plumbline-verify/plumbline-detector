from pkg import add


def check_sum(a, b, want):
    assert add(a, b) == want


def test_add():
    check_sum(1, 2, 3)
    check_sum(-1, 1, 0)


def test_add_zero():
    assert add(0, 0) == 0


def test_add_floats():
    assert add(0.5, 0.25) == 0.75


def test_add_large():
    assert add(10**9, 1) == 10**9 + 1


class Harness:
    def did_create(self, x):
        assert x


def test_harness_idiom():
    Harness().did_create(add(1, 1))
