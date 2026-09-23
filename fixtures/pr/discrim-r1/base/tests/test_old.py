from pkg import f


class TestDiscover:
    def test_discover_one(self):
        assert f(1) == 1

    def test_discover_two(self):
        assert f(2) == 2
