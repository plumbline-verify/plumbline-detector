from pkg.calc import add


def check_sum(a, b, expected, *, verbose=False):
    assert add(a, b) == expected


class SumChecker:
    def __init__(self, expected):
        self.expected = expected

    def __call__(self, a, b):
        assert add(a, b) == self.expected
