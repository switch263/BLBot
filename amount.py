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

_SUFFIXES = {
    "k": 1_000,
    "m": 1_000_000,
    "b": 1_000_000_000,
    "t": 1_000_000_000_000,
}

# digits with optional , _ or space grouping, optional decimal, optional suffix
_AMOUNT_RE = re.compile(r"^([0-9][0-9,_ ]*(?:\.[0-9]+)?)\s*([kmbt])?$", re.IGNORECASE)
_PERCENT_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*%$")

# Shown to the user when their amount couldn't be read.
AMOUNT_HELP = "Try a number like `500`, `100,000`, `2k`, `1.5m`, or `1b`."
CONTEXT_HELP = AMOUNT_HELP[:-1] + " — or `all`, `half`, or `50%`."


def parse_amount(text, available: int | None = None) -> int | None:
    """Parse a human-typed coin amount into a non-negative int, or None if it
    isn't a valid amount. Accepts thousands separators (`,` `_` space) and the
    suffixes k/m/b/t (case-insensitive), with or without a decimal (`1.5k`).

    With `available=` (the balance the amount draws on), also accepts the
    contextual forms `all`/`max`, `half`, and percentages like `50%`. Those
    return None when no `available` was given — a bare "/gift all" has nothing
    to be all OF unless the caller says so.

    Already-int input passes straight through (so handlers are safe to call it
    twice or on a default). Booleans, negatives, and junk return None."""
    if isinstance(text, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(text, int):
        return text if text >= 0 else None
    if isinstance(text, float):
        return int(text) if text >= 0 else None
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
            pct = float(pm.group(1))
            if not 0 <= pct <= 100:
                return None
            return int(available * pct / 100)

    m = _AMOUNT_RE.match(s)
    if not m:
        return None

    num_part = m.group(1).replace(",", "").replace("_", "").replace(" ", "")
    suffix = m.group(2)
    if num_part in ("", "."):
        return None
    try:
        value = float(num_part)
    except ValueError:
        return None
    if suffix:
        value *= _SUFFIXES[suffix]
    if value < 0 or value != value or value in (float("inf"), float("-inf")):
        return None
    return int(value)


def amount_error(raw, contextual: bool = False) -> str:
    """A friendly 'couldn't read that' message for an unparseable amount.
    Pass contextual=True where all/half/% are accepted (i.e. the caller
    parsed with `available=`) so the help text advertises those forms."""
    help_text = CONTEXT_HELP if contextual else AMOUNT_HELP
    return f"❓ Couldn't read **{raw}** as an amount. {help_text}"
