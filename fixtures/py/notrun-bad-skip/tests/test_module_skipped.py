import pytest

from pkg.calc import add

pytestmark = pytest.mark.skip(reason="whole module disabled")


def test_add_again():
    assert add(1, 2) == 3
