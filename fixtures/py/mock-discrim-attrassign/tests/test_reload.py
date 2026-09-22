from unittest import mock

import pytest

from pkg import reload


def test_records_error():
    fake = mock.MagicMock(side_effect=RuntimeError())
    wrapped = reload.check_errors(fake)
    with mock.patch.object(reload, "_errors") as errors:
        try:
            with pytest.raises(RuntimeError):
                wrapped()
        finally:
            reload._last = None
    assert errors.append.call_count == 1
