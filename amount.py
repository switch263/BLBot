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
    1qi            -> 1000000000000000000   (quintillion)
    1sx / 1sp      -> sextillion (1e21) / septillion (1e24)
    1oc / 1no / 1dc-> octillion (1e27) / nonillion (1e30) / decillion (1e33)
    2.5e40         -> scientific notation, for when the suffixes run out

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
from decimal import Context, Decimal, InvalidOperation

_SUFFIXES = {
    "k": 10**3,
    "m": 10**6,
    "b": 10**9,
    "t": 10**12,
    # Balances have no practical ceiling any more (economy.MAX_COINS is a
    # 1e300 guard), so the short names keep going past a trillion —
    # nobody should have to type thirty zeros for a routine bet. Past
    # decillion, scientific notation (`1e40`) takes over.
    "q": 10**15,      # quadrillion
    "qa": 10**15,     # ...spelled out, same thing
    "qi": 10**18,     # quintillion
    "sx": 10**21,     # sextillion
    "sp": 10**24,     # septillion
    "oc": 10**27,     # octillion
    "no": 10**30,     # nonillion
    "dc": 10**33,     # decillion
}

# The coin guard, mirrored from economy.MAX_COINS (a test pins them equal).
# Duplicated rather than imported so this module stays pure — no DB, no config.
# Anything a player types above it is rejected outright rather than clamped:
# "1e500" is a typo or a probe, not a bet.
MAX_AMOUNT = 10**300 - 1  # see economy.MAX_COINS

# Amounts are parsed with Decimal, never float. A float carries only 53 bits of
# mantissa (~9e15), so `float("9223372036854775807")` rounds UP and typing
# "1000000000000000001" would silently land on ...000. Decimal is exact for
# both the integer and the `1.5k` decimal forms — but only up to the context
# precision, so every calculation runs under _CTX (enough digits to hold the
# guard with room to spare; the default 28 would round a 30-digit stake).
_CTX = Context(prec=700)

# digits with optional , _ or space grouping, optional decimal, optional
# exponent (`2.5e40`) OR magnitude suffix — never both.
_AMOUNT_RE = re.compile(
    r"^([0-9][0-9,_ ]*(?:\.[0-9]+)?)\s*(?:e\+?([0-9]{1,3})|(qa|qi|sx|sp|oc|no|dc|k|m|b|t|q))?$",
    re.IGNORECASE)
_PERCENT_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*%$")

# Shown to the user when their amount couldn't be read.
AMOUNT_HELP = "Try a number like `500`, `100,000`, `2k`, `1.5m`, `1b`, `2.5q`, or `1e30`."
CONTEXT_HELP = AMOUNT_HELP[:-1] + " — or `all`, `half`, or `50%`."


def parse_amount(text, available: int | None = None) -> int | None:
    """Parse a human-typed coin amount into a non-negative int, or None if it
    isn't a valid amount. Accepts thousands separators (`,` `_` space), the
    suffixes k/m/b/t/q(a)/qi/sx/sp/oc/no/dc (case-insensitive) and scientific
    notation (`2.5e40`), with or without a decimal (`1.5k`).

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
            # Decimal, not float: 50% of a 40-digit balance must be exact.
            return int(_CTX.divide(_CTX.multiply(Decimal(available), pct), Decimal(100)))

    m = _AMOUNT_RE.match(s)
    if not m:
        return None

    num_part = m.group(1).replace(",", "").replace("_", "").replace(" ", "")
    exponent, suffix = m.group(2), m.group(3)
    if num_part in ("", "."):
        return None
    try:
        value = Decimal(num_part)
    except (InvalidOperation, ValueError):
        return None
    if exponent:
        value = _CTX.multiply(value, _CTX.power(Decimal(10), Decimal(exponent)))
    elif suffix:
        value = _CTX.multiply(value, Decimal(_SUFFIXES[suffix.lower()]))
    if not value.is_finite() or value < 0 or value > MAX_AMOUNT:
        return None
    return int(value)


def amount_error(raw, contextual: bool = False) -> str:
    """A friendly 'couldn't read that' message for an unparseable amount.
    Pass contextual=True where all/half/% are accepted (i.e. the caller
    parsed with `available=`) so the help text advertises those forms."""
    help_text = CONTEXT_HELP if contextual else AMOUNT_HELP
    return f"❓ Couldn't read **{raw}** as an amount. {help_text}"
