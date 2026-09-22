from pkg.primes import factorial, speed


def test_factorial():
    assert factorial(5) == 120
    assert factorial(0) == 1


def test_speed():
    assert speed("turbo") == 100
