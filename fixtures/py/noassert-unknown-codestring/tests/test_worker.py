from pkg.worker import run_in_worker


def test_worker_math():
    run_in_worker("""
x = 1 + 1
assert x == 2
""")
