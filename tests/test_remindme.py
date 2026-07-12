"""parse_when: the '!remindme <when> <what>' front-of-string time parser."""
import time
from datetime import datetime, timedelta

import pytest

pytest.importorskip("discord")

from remindme import parse_when  # noqa: E402


def _delay(due):
    return due - time.time()


# ---- Durations -------------------------------------------------------------

@pytest.mark.parametrize("raw,seconds,text", [
    ("7 days check the gator", 7 * 86400, "check the gator"),
    ("in 7 days check the gator", 7 * 86400, "check the gator"),
    ("2h30m withdraw", 2.5 * 3600, "withdraw"),
    ("90 minutes", 90 * 60, ""),
    ("1 week pig derby", 604800, "pig derby"),
    ("10s blink", 10, "blink"),
    ("1.5 hours nap", 1.5 * 3600, "nap"),
    ("1d12h long nap", 1.5 * 86400, "long nap"),
    ("2 hours, 30 minutes split units", 2.5 * 3600, "split units"),
    ("1 month rent", 2592000, "rent"),
])
def test_durations(raw, seconds, text):
    due, rest = parse_when(raw)
    assert due is not None, rest
    assert abs(_delay(due) - seconds) < 2
    assert rest == text


def test_duration_stops_at_first_non_time_token():
    due, rest = parse_when("2 days 3 dogs to feed")
    assert due is not None
    # '3 dogs' isn't a unit pair, so it belongs to the message.
    assert abs(_delay(due) - 2 * 86400) < 2
    assert rest == "3 dogs to feed"


# ---- Absolute times ----------------------------------------------------------

def test_bare_clock_time_is_implicit_at():
    due, rest = parse_when("12pm lunch")
    assert due is not None
    assert rest == "lunch"
    got = datetime.fromtimestamp(due)
    assert (got.hour, got.minute) == (12, 0)
    assert 0 < _delay(due) <= 86400  # today or rolled to tomorrow, never past


@pytest.mark.parametrize("tok,hm", [
    ("18:30", (18, 30)),
    ("9:15am", (9, 15)),
    ("noon", (12, 0)),
    ("midnight", (0, 0)),
])
def test_bare_clock_variants(tok, hm):
    due, rest = parse_when(f"{tok} do the thing")
    assert due is not None
    assert rest == "do the thing"
    got = datetime.fromtimestamp(due)
    assert (got.hour, got.minute) == hm


def test_bare_clock_does_not_eat_durations():
    # '10m' is a duration, not a clock time.
    due, rest = parse_when("10m stretch")
    assert due is not None
    assert abs(_delay(due) - 600) < 2
    assert rest == "stretch"


def test_at_hhmm_rolls_to_tomorrow_when_past():
    past = (datetime.now() - timedelta(hours=1)).strftime("%H:%M")
    due, rest = parse_when(f"at {past} pay taxes")
    assert due is not None
    assert rest == "pay taxes"
    assert 0 < _delay(due) <= 86400


def test_at_full_datetime():
    target = datetime.now() + timedelta(days=3)
    raw = target.strftime("at %Y-%m-%d %H:%M") + " court date"
    due, rest = parse_when(raw)
    assert due is not None
    assert rest == "court date"
    got = datetime.fromtimestamp(due)
    assert got.replace(second=0, microsecond=0) == target.replace(second=0, microsecond=0)


def test_at_date_only_defaults_to_9am():
    target = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
    due, rest = parse_when(f"at {target} rent")
    assert due is not None
    assert rest == "rent"
    assert datetime.fromtimestamp(due).hour == 9


def test_tomorrow_with_ampm():
    due, rest = parse_when("tomorrow 9pm heist")
    assert due is not None
    assert rest == "heist"
    got = datetime.fromtimestamp(due)
    assert (got.hour, got.minute) == (21, 0)
    assert got.date() == (datetime.now() + timedelta(days=1)).date()


def test_tomorrow_bare_defaults_to_9am():
    due, rest = parse_when("tomorrow stretch")
    assert due is not None
    assert rest == "stretch"
    assert datetime.fromtimestamp(due).hour == 9


# ---- Rejections --------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    "",
    "later maybe",
    "7 dogs walk them",   # number + non-unit
    "at nonsense thing",
    "at 25:99 impossible",
    "in",
])
def test_bad_input_returns_error(raw):
    due, msg = parse_when(raw)
    assert due is None
    assert isinstance(msg, str) and msg
