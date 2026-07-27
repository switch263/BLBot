"""parse_amount: the single source of truth for typed coin amounts."""
import pytest

import economy
from amount import MAX_AMOUNT, parse_amount


@pytest.mark.parametrize("raw,want", [
    ("500", 500),
    ("100,000", 100_000),
    ("100_000_000", 100_000_000),
    ("2k", 2_000),
    ("1.5k", 1_500),
    ("5m", 5_000_000),
    ("1b", 1_000_000_000),
    ("1t", 1_000_000_000_000),
    ("1q", 1_000_000_000_000_000),
    ("1qa", 1_000_000_000_000_000),
    ("2.5q", 2_500_000_000_000_000),
    ("1qi", 1_000_000_000_000_000_000),
    ("0.5QI", 500_000_000_000_000_000),
    ("$5k", 5_000),
    (" 10K ", 10_000),
    (42, 42),
    (0, 0),
])
def test_plain_forms(raw, want):
    assert parse_amount(raw) == want


@pytest.mark.parametrize("raw", ["junk", "", None, -5, True, "-500", "%", "k", "1.2.3"])
def test_rejects_garbage(raw):
    assert parse_amount(raw) is None


def test_contextual_forms_require_available():
    for raw in ("all", "max", "half", "50%"):
        assert parse_amount(raw) is None


def test_contextual_forms():
    assert parse_amount("all", available=777) == 777
    assert parse_amount("max", available=777) == 777
    assert parse_amount("half", available=777) == 388
    assert parse_amount("50%", available=1_000) == 500
    assert parse_amount("100%", available=333) == 333
    assert parse_amount("0%", available=333) == 0
    assert parse_amount("150%", available=333) is None
    # plain forms still parse when available is passed
    assert parse_amount("2k", available=777) == 2_000


def test_ceiling_matches_economy():
    # amount.py duplicates the ceiling to stay a pure module — keep them equal.
    assert MAX_AMOUNT == economy.MAX_COINS


@pytest.mark.parametrize("raw", [
    "9999qi",                     # suffix form past the ceiling
    "99999999999999999999999",    # raw digits past the ceiling
    MAX_AMOUNT + 1,               # already-int input past the ceiling
    float(MAX_AMOUNT) * 10,
])
def test_rejects_above_ceiling(raw):
    # Absurd stakes are refused outright, not silently clamped — a typed
    # amount that big is a typo or a probe, never a real bet.
    assert parse_amount(raw) is None


def test_accepts_exactly_the_ceiling():
    # Exact to the last digit — this is why parsing uses Decimal, not float.
    # float(str(MAX_AMOUNT)) rounds UP past the cap and would reject it.
    assert parse_amount(str(MAX_AMOUNT)) == MAX_AMOUNT
    assert parse_amount(str(MAX_AMOUNT + 1)) is None
    assert parse_amount("9qi") == 9_000_000_000_000_000_000
    assert parse_amount("1000000t") == 1_000_000_000_000_000_000


def test_large_amounts_keep_every_digit():
    # float() carries 53 bits of mantissa (~9e15), so these used to round.
    assert parse_amount("1000000000000000001") == 1_000_000_000_000_000_001
    assert parse_amount("9223372036854775806") == 9_223_372_036_854_775_806
    # ...and a percentage of a huge balance must be exact too.
    assert parse_amount("50%", available=MAX_AMOUNT) == MAX_AMOUNT // 2
    assert parse_amount("all", available=MAX_AMOUNT) == MAX_AMOUNT
