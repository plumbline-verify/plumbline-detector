import pytest

from pkg.calc import add


class EqLimiter:
    calls = 0

    def __eq__(self, other):
        self.calls += 1
        return self.calls > 1


def test_add():
    with pytest.raises(TypeError):
        add(EqLimiter(), None)
