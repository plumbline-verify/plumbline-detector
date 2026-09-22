from pkg.etag import matches, parse


def test_wildcard():
    assert matches("abc", ["*"]) is True
    assert parse("*") == ["*"]
