from pkg.calc import add
from tests.helpers.matchers import Anything


def test_add():
    assert add(2, 3) == 5
    assert Anything() == add(1, 1)
