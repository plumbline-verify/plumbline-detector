from pkg.shell import start


def test_start_handles_exit():
    def embed():
        raise SystemExit

    assert start(embed) == "exited"
