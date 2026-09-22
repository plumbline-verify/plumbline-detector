from pkg.calc import add


class Approx:
    def __init__(self, v):
        self.v = v

    def __eq__(self, other):
        return abs(self.v - other) < 1e-9


def test_add():
    assert Approx(5) == add(2, 3)
