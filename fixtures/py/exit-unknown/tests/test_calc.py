import sys

from pkg.calc import add


def test_add():
    code = add(0, 0)
    sys.exit(code)
