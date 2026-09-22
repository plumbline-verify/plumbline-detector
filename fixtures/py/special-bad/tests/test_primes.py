from pkg.primes import nth_prime


def test_small():
    assert nth_prime(3) == 5


def test_large():
    assert nth_prime(1729) == 14737
