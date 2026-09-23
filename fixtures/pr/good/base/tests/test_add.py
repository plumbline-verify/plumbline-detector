from pkg import add


def test_add():
    assert add(1, 2) == 3
    assert add(-1, 1) == 0


def test_add_zero():
    assert add(0, 0) == 0


def test_add_floats():
    assert add(0.5, 0.25) == 0.75


class Harness:
    def did_create(self, x):
        assert x


def test_harness_idiom():
    Harness().did_create(add(1, 1))
