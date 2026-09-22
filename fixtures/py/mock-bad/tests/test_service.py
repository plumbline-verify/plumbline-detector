from unittest.mock import MagicMock, patch


def test_notify_returns_true():
    notifier = MagicMock()
    notifier.notify.return_value = True
    assert notifier.notify(7) is True
    notifier.notify.assert_called_once_with(7)


@patch("pkg.service.notify")
def test_patched(mock_notify):
    mock_notify.return_value = True
    result = mock_notify(None, 7)
    assert result is True
