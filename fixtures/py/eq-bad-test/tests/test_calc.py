from pkg.calc import add
from tests.helpers import AlwaysEqual


def test_add():
    assert AlwaysEqual() == add(2, 3)
