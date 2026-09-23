import pytest
from zope.interface.verify import verifyObject
from mypkg.testing import eq_

from pkg import Concrete


def test_benchmark_speed(benchmark):
    benchmark(Concrete().run)


@pytest.mark.benchmark
def test_marked_benchmark():
    Concrete().run()


def test_webtest_status(testapp):
    testapp.get("/protected", status=403)


def test_zope_conformance():
    verifyObject(object, Concrete())


def test_nose_style():
    eq_(Concrete().run(), 1)


def test_real_gap():
    Concrete().run()
