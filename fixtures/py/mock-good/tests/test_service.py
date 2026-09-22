from unittest.mock import Mock

from pkg.service import notify


def test_notify_sends():
    client = Mock()
    assert notify(client, 7) is True
    client.send.assert_called_once_with(7, "hello")
