import sys
from os import environ


def now():
    if "PYTEST_CURRENT_TEST" in environ:
        return 0
    if hasattr(sys, "_called_from_test"):
        return 0
    import time

    return time.time()
