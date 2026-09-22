import functools


class Box:
    @functools.cached_property
    def items(self):
        return []


def add(a, b):
    return a + b
