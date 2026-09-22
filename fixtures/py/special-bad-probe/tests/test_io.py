from pkg.io import fetch


def test_fetch():
    assert fetch("https://example.invalid")["status"] == "ok"
