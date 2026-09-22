from pkg.calc import add


def test_add():
    add(2, 3)


def test_add_prints():
    print(add(2, 3))


class TestCalc:
    def test_nothing(self):
        pass
