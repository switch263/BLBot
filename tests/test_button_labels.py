"""Button labels with money in them must fit Discord's 80-char cap at any
balance — a full `f"{n:,}"` of a big payout 400'd every edit of the game
message (bigfoot's "Head Back" button took the whole view down)."""
import pytest

from amount import MAX_AMOUNT, format_compact, parse_amount
from game_common import BUTTON_LABEL_MAX, button_label


@pytest.mark.parametrize("n, shown", [
    (0, "0"), (999, "999"), (1000, "1k"), (1500, "1.5k"), (1999, "1.99k"),
    (12_345, "12.3k"), (999_999, "999k"), (1_000_000, "1m"),
    (2_500_000_000, "2.5b"), (10**15, "1q"), (450 * 10**18, "450qi"),
    (10**36, "1e36"), (25 * 10**39, "2.5e40"), (-1500, "-1.5k"),
])
def test_format_compact(n, shown):
    assert format_compact(n) == shown


@pytest.mark.parametrize("n", [1, 10**3 + 7, 10**18 - 1, 10**35 + 3, 10**100 + 9, MAX_AMOUNT])
def test_compact_never_overstates_and_parses_back(n):
    s = format_compact(n)
    assert len(s) <= 8
    back = parse_amount(s)
    assert back is not None and back <= n


def test_label_at_the_ceiling_fits():
    label = button_label(f"Head Back (99.99×, +{format_compact(MAX_AMOUNT)})")
    assert len(label) <= BUTTON_LABEL_MAX


def test_button_label_clamps():
    assert button_label("short") == "short"
    long = button_label("x" * 500)
    assert len(long) == BUTTON_LABEL_MAX and long.endswith("…")
