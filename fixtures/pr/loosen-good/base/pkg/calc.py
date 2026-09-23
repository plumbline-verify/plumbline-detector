import time


def mean(xs):
    return sum(xs) / len(xs)


def elapsed():
    t = time.perf_counter()
    return time.perf_counter() - t


def parse(s):
    return int(s)


def fetch():
    return [1, 2]


def total(xs=None):
    return sum(fetch() if xs is None else xs)
