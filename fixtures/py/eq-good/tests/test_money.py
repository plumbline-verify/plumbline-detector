from pkg.money import Money


def test_equal():
    assert Money(1, "USD") == Money(1, "USD")
    assert Money(1, "USD") != Money(2, "USD")
