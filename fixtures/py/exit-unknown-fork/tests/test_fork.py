import os

from pkg.calc import add


def test_child_process():
    pid = os.fork()
    if pid == 0:
        add(1, 1)
        os._exit(0)
    _, status = os.waitpid(pid, 0)
    assert status == 0
