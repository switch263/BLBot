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

# Shown to the user when their amount couldn't be read.
AMOUNT_HELP = "Try a number like `500`, `100,000`, `2k`, `1.5m`, or `1b`."


def parse_amount(text) -> int | None:
    """Parse a human-typed coin amount into a non-negative int, or None if it
    isn't a valid amount. Accepts thousands separators (`,` `_` space) and the
    suffixes k/m/b/t (case-insensitive), with or without a decimal (`1.5k`).

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


def amount_error(raw) -> str:
    """A friendly 'couldn't read that' message for an unparseable amount."""
    return f"❓ Couldn't read **{raw}** as an amount. {AMOUNT_HELP}"
