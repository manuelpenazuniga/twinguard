import pytest

from lockops.formatting import describe_windows, format_minute, weekly_unlocked_hours
from lockops.models import UnlockWindow


def test_format_minute():
    assert format_minute(0) == "00:00"
    assert format_minute(7 * 60 + 5) == "07:05"


def test_describe_windows_sorted():
    windows = [UnlockWindow(2, 600, 660), UnlockWindow(0, 480, 1080)]
    assert describe_windows(windows) == "Mon 08:00-18:00, Wed 10:00-11:00"


def test_describe_no_windows():
    assert describe_windows([]) == "always locked"


def test_weekly_hours():
    assert weekly_unlocked_hours([UnlockWindow(0, 480, 1080), UnlockWindow(1, 0, 30)]) == 10.5


def test_invalid_window_rejected():
    with pytest.raises(ValueError):
        UnlockWindow(0, 600, 600)
