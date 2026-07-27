"""Human-friendly coin-amount parsing for every economy command.

Players can type amounts with thousands separators and magnitude suffixes
instead of long strings of zeros:

    500            -> 500
    100,000        -> 100000
    100_000_000    -> 100000000
    2k             -> 2000
    1.5k           -> 1500
    5m             -> 5000000
    1b             -> 1000000000
    1t             -> 1000000000000
    1q / 1qa       -> 1000000000000000      (quadrillion)
    1qi            -> 1000000000000000000   (quintillion — the cap)

When the caller passes `available=` (a balance the amount is drawn against),
contextual amounts work too:

    all / max      -> available
    half           -> available // 2
    50%            -> half of available (any 0-100%)

`parse_amount` is the single source of truth. Cogs declare their amount
parameter as `str` (so slash fields accept text, not just digits) and call
`parse_amount` at the top of the handler; on None they show `amount_error`.

It's a pure module — no Discord, no DB.
"""

import re
from decimal import Decimal, InvalidOperation

_SUFFIXES = {
    "k": 1_000,
    "m": 1_000_000,
    "b": 1_000_000_000,
    "t": 1_000_000_000_000,
    # Balances run to a quintillion (economy.MAX_COINS), so `t` alone would
    # leave players typing thirteen zeros for a routine amount.
    "q": 1_000_000_000_000_000,      # quadrillion
    "qa": 1_000_000_000_000_000,     # ...spelled out, same thing
    "qi": 1_000_000_000_000_000_000,  # quintillion — the ceiling itself
}

# The coin ceiling, mirrored from economy.MAX_COINS (a test pins them equal).
# Duplicated rather than imported so this module stays pure — no DB, no config.
# Anything a player types above it is rejected outright rather than clamped:
# "9999qi" is a typo or a probe, not a bet, and silently reinterpreting it as a
# quintillion-coin stake is worse than saying no.
MAX_AMOUNT = 2**63 - 1  # 9,223,372,036,854,775,807 — see economy.MAX_COINS

# Amounts are parsed with Decimal, never float. A float carries only 53 bits of
# mantissa (~9e15), so at this ceiling `float("9223372036854775807")` rounds UP
# past the cap and the exact maximum would be rejected, and typing
# "1000000000000000001" would silently land on ...000. Decimal is exact for
# both the integer and the `1.5k` decimal forms.

# digits with optional , _ or space grouping, optional decimal, optional suffix
_AMOUNT_RE = re.compile(r"^([0-9][0-9,_ ]*(?:\.[0-9]+)?)\s*(qa|qi|k|m|b|t|q)?$",
                         re.IGNORECASE)
_PERCENT_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*%$")

# Shown to the user when their amount couldn't be read.
AMOUNT_HELP = "Try a number like `500`, `100,000`, `2k`, `1.5m`, `1b`, or `2.5q`."
CONTEXT_HELP = AMOUNT_HELP[:-1] + " — or `all`, `half`, or `50%`."


def parse_amount(text, available: int | None = None) -> int | None:
    """Parse a human-typed coin amount into a non-negative int, or None if it
    isn't a valid amount. Accepts thousands separators (`,` `_` space) and the
    suffixes k/m/b/t/q(a)/qi (case-insensitive), with or without a
    decimal (`1.5k`).

    With `available=` (the balance the amount draws on), also accepts the
    contextual forms `all`/`max`, `half`, and percentages like `50%`. Those
    return None when no `available` was given — a bare "/gift all" has nothing
    to be all OF unless the caller says so.

    Already-int input passes straight through (so handlers are safe to call it
    twice or on a default). Booleans, negatives, junk, and anything above
    MAX_AMOUNT return None."""
    if isinstance(text, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(text, int):
        return text if 0 <= text <= MAX_AMOUNT else None
    if isinstance(text, float):
        if not (0 <= text <= MAX_AMOUNT):
            return None
        return int(text)
    if text is None:
        return None

    s = str(text).strip().lower().lstrip("$").strip()
    if not s:
        return None

    if available is not None:
        if s in ("all", "max"):
            return available
        if s == "half":
            return available // 2
        pm = _PERCENT_RE.match(s)
        if pm:
            try:
                pct = Decimal(pm.group(1))
            except (InvalidOperation, ValueError):
                return None
            if not 0 <= pct <= 100:
                return None
            # Decimal, not float: 50% of a 9-quintillion balance must be exact.
            return int(Decimal(available) * pct / 100)

    m = _AMOUNT_RE.match(s)
    if not m:
        return None

    num_part = m.group(1).replace(",", "").replace("_", "").replace(" ", "")
    suffix = m.group(2)
    if num_part in ("", "."):
        return None
    try:
        value = Decimal(num_part)
    except (InvalidOperation, ValueError):
        return None
    if suffix:
        value *= _SUFFIXES[suffix]
    if not value.is_finite() or value < 0 or value > MAX_AMOUNT:
        return None
    return int(value)


def amount_error(raw, contextual: bool = False) -> str:
    """A friendly 'couldn't read that' message for an unparseable amount.
    Pass contextual=True where all/half/% are accepted (i.e. the caller
    parsed with `available=`) so the help text advertises those forms."""
    help_text = CONTEXT_HELP if contextual else AMOUNT_HELP
    return f"❓ Couldn't read **{raw}** as an amount. {help_text}"
