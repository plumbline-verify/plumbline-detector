from pkg.calc import add


def test_add(number):
    assert add(2, 3) == number
