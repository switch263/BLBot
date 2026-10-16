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


@pytest.mark.parametrize("n, shown", [
    (1_234_567, "1,234,567"), (-1_500, "-1,500"), (10**27, f"{10**27:,}"),
    (10**60, "1e60"), (12345 * 10**40, "1.234e44"), (MAX_AMOUNT, "9.999e299"),
])
def test_format_coins_full_until_it_would_hog_the_message(n, shown):
    from game_common import format_coins
    assert format_coins(n) == shown


def test_format_coins_signed():
    from game_common import format_coins
    assert format_coins(1500, signed=True) == "+1,500"
    assert format_coins(10**60, signed=True) == "+1e60"
    assert format_coins(-10**60, signed=True) == "-1e60"


# Message content is capped at 2,000 chars — the vault's win board quotes
# five money figures, which at a maxed stake ran ~3,000 and 400'd every
# Submit click.
MESSAGE_MAX = 2000


@pytest.mark.parametrize("difficulty", ["normal", "hard", "extra"])
def test_vault_board_fits_at_the_ceiling(difficulty):
    pytest.importorskip("discord")
    import vault
    from game_common import format_coins
    bet = MAX_AMOUNT
    g = vault.VaultGame(1, 2, "x" * 32, bet, vault.DIFFICULTIES[difficulty])
    g.attempts = [([1] * g.cfg["code_length"], "🟢" * 5)] * (vault.MAX_ATTEMPTS - 1)
    assert len(vault.TheVault._render(None, g)) <= MESSAGE_MAX
    g.ended = True
    big = format_coins(bet)
    footer = (f"{g.cfg['solve_flavor'][0]}\nCracked in **5** attempt(s). Payout: **75.00×** → "
              f"**{big}** coins (net **+{big}**).\n💥 **YOU BROKE THE BANK.** The house owed "
              f"**{big}** and could only scrape together **{big}** — emergency measures incoming.\n"
              f"Balance: **{big}**\n-# ⭐ Prestige multiplier: ×10")
    assert len(vault.TheVault._render(None, g, footer)) <= MESSAGE_MAX


def test_scientific_figures_parse_back_without_overstating():
    from game_common import format_coins
    for n in (10**40 + 7, 98765 * 10**60, MAX_AMOUNT):
        back = parse_amount(format_coins(n))
        assert back is not None and back <= n


def test_fill_formats_money_placeholders_like_format_coins():
    from game_common import fill
    tpl = "{thief} took **{amount:,}** ({pct}%) and owes {fine:+,}"
    assert fill(tpl, thief="a", amount=1500, pct=5, fine=10**50) == "a took **1,500** (5%) and owes +1e50"
    assert fill("{x}", x="{not a field}") == "{not a field}"


def test_wallet_shows_every_digit_under_the_headline():
    from game_common import format_coins_exact
    assert format_coins_exact(1500) == "**1,500**"
    exact = format_coins_exact(MAX_AMOUNT)
    assert exact.startswith("**9.999e299**\n") and f"{MAX_AMOUNT:,}" in exact
    assert len(exact) <= 1024  # embed field value cap


def test_no_cog_prints_raw_full_digit_money():
    """Every money figure in a cog's f-strings goes through format_coins.
    `.format` flavor templates may keep `{amount:,}` — they're filled with
    game_common.fill, which routes it the same way."""
    import io
    import pathlib
    import re
    import tokenize
    field = re.compile(r"\{[^{}]*:\+?,\}")
    root = pathlib.Path(__file__).resolve().parents[1]
    bad = []
    for p in sorted((root / "cogs").glob("*.py")):
        src = p.read_text()
        skip = []
        offs = [0]
        for line in src.splitlines(keepends=True):
            offs.append(offs[-1] + len(line))
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                skip.append((offs[tok.start[0] - 1] + tok.start[1], offs[tok.end[0] - 1] + tok.end[1]))
        for m in field.finditer(src):
            if not any(a <= m.start() < b for a, b in skip):
                bad.append(f"{p.name}:{src.count(chr(10), 0, m.start()) + 1} {m.group(0)}")
    assert not bad, "use format_coins(...) instead of :, —\n" + "\n".join(bad)
