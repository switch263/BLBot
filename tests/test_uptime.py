"""!uptime: duration formatting."""
import pytest

pytest.importorskip("discord")

from admin import format_uptime  # noqa: E402


@pytest.mark.parametrize("seconds,expected", [
    (0, "0 seconds"),
    (0.9, "0 seconds"),
    (1, "1 second"),
    (59, "59 seconds"),
    (60, "1 minute"),
    (3725, "1 hour, 2 minutes, 5 seconds"),
    (86400, "1 day"),
    (2 * 86400 + 3600 + 1, "2 days, 1 hour, 1 second"),
])
def test_format_uptime(seconds, expected):
    assert format_uptime(seconds) == expected
