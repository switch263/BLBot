"""!date: written-out date formatting and timezone resolution."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("discord")

from date import format_date, ordinal, resolve_zone  # noqa: E402


@pytest.mark.parametrize("n,expected", [
    (1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"),
    (12, "12th"), (13, "13th"), (21, "21st"), (22, "22nd"), (23, "23rd"), (31, "31st"),
])
def test_ordinal(n, expected):
    assert ordinal(n) == expected


def test_format_date_central():
    dt = datetime(2026, 10, 7, 15, 42, tzinfo=ZoneInfo("America/Chicago"))
    assert format_date(dt) == "Wednesday, October 7th, 2026 — 3:42 PM CDT"


def test_format_date_midnight_and_winter():
    dt = datetime(2026, 1, 1, 0, 5, tzinfo=ZoneInfo("America/Chicago"))
    assert format_date(dt) == "Thursday, January 1st, 2026 — 12:05 AM CST"


def test_utc_late_evening_is_still_yesterday_in_central():
    utc = datetime(2026, 10, 8, 2, 0, tzinfo=ZoneInfo("UTC"))
    assert format_date(utc.astimezone(resolve_zone("central"))).startswith("Wednesday, October 7th")


@pytest.mark.parametrize("name,key", [
    ("pacific", "America/Los_Angeles"), ("EST", "America/New_York"),
    ("Europe/London", "Europe/London"), ("utc", "UTC"),
])
def test_resolve_zone(name, key):
    assert resolve_zone(name) == ZoneInfo(key)


def test_resolve_zone_rejects_garbage():
    assert resolve_zone("narnia") is None
    assert resolve_zone("../../etc/passwd") is None


def test_sass_lines_never_about_family():
    from date import SASS_LINES
    banned = ("mother", "mom", "mama", "father", "dad", "sister", "brother",
              "family", "parent", "grandma", "grandpa", "wife", "son", "daughter")
    for line in SASS_LINES:
        words = line.lower().replace(",", " ").replace(".", " ").split()
        assert not any(b in words for b in banned), line


# ---- Saved timezone (/pref set timezone) ------------------------------------

def test_validate_timezone_stores_iana_name():
    from date import validate_timezone
    assert validate_timezone("  Pacific ") == "America/Los_Angeles"
    assert validate_timezone("Europe/London") == "Europe/London"
    for bad in ("", "   ", "narnia"):
        with pytest.raises(ValueError):
            validate_timezone(bad)


class _Member:
    def __init__(self, uid, name="someone"):
        self.id = uid
        self.display_name = name


def test_pick_zone_priority():
    import user_settings
    from date import TIMEZONE_SETTING, pick_zone
    me, friend, stranger = 910001, 910002, 910003
    user_settings.set_value(me, TIMEZONE_SETTING, "America/New_York")
    user_settings.set_value(friend, TIMEZONE_SETTING, "Asia/Tokyo")

    # Nothing typed → my saved zone.
    assert pick_zone(me, None) == (ZoneInfo("America/New_York"), None)
    # Typed zone beats my saved one.
    assert pick_zone(me, "pacific") == (ZoneInfo("America/Los_Angeles"), None)
    # @member → their saved zone, even over typed text.
    assert pick_zone(me, "<@910002>", _Member(friend)) == (ZoneInfo("Asia/Tokyo"), None)
    # No saved zone anywhere → server default (Central unless TZ is set).
    assert pick_zone(stranger, None) == (resolve_zone(None), None)


def test_pick_zone_errors():
    from date import pick_zone
    tz, err = pick_zone(910004, None, _Member(910005, "Gator"))
    assert tz is None and "**Gator** hasn't saved a timezone" in err
    tz, err = pick_zone(910004, None, _Member(910004))
    assert tz is None and err.startswith("You haven't")
    tz, err = pick_zone(910004, "narnia")
    assert tz is None and "narnia" in err
