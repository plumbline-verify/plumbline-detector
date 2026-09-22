from pkg.calc import add


def test_db_roundtrip():
    assert add(1, 1) == 2
