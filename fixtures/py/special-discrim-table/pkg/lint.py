import os

# A linter's pattern table mentions the probe strings without reading them.
PROBES = frozenset({"PYTEST_CURRENT_TEST", "_called_from_test"})


def is_probe(name):
    return name in PROBES


def home():
    return os.environ.get("HOME", "/")
