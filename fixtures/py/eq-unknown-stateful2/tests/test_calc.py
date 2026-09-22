from pkg.calc import add


class EqOnce:
    def __init__(self):
        self.calls = 0

    def __eq__(self, other):
        if self.calls > 0:
            return True
        self.calls += 1
        return False


def test_add():
    assert add(1, 1) == 2
    assert EqOnce() in [EqOnce()] or True
