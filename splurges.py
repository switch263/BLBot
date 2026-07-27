"""The Splurge catalog — everything a player can set fire to.

The economy has plenty of ways to WIN coins and almost none to lose them on
purpose. This is the sink: a wealth-gated catalog of increasingly deranged
purchases that destroy coins outright (cogs/splurge.py spends them through
economy.burn_purchase, which is a true void sink — nothing goes to the house,
nothing is minted anywhere).

Two escalators keep it interesting as a player gets richer:

  * TIERS unlock on total wealth (wallet + bank). Broke players see the gas
    station energy drink; a player brushing the MAX_COINS ceiling sees the
    option to buy a share of the house itself. You can only buy from tiers
    you've unlocked, so the catalog grows with the fortune.
  * REPEAT PURCHASES cost more every time — `price_for()` multiplies the base
    price by ESCALATION per copy already owned. Buying the same thing forever
    gets exponentially more expensive, which is the point.

Splurges are PURELY COSMETIC with exactly one deliberate exception. They grant
no items, no odds, no coins back — they're trophies in `/flex` and nothing
else. A sink that pays out isn't a sink, and anything with a mechanical effect
would eventually be worth farming.

The exception is SHARES_KEY ("Buy Into the House", Tier 7): each share draws a
slice of economy.HOUSE_PROFIT_SHARE_PCT of house PROFIT, split pro-rata among
shareholders, and any shareholder is permanently barred from gambling. Shares
are repeatable and dilutive — a second buyer thins everyone's slice. The
mechanic lives in economy.py (see its "House profit sharing" block); this
module only names the key and describes the deal.

Pure data module — no Discord, no DB (same contract as items.py).
"""

# The coin ceiling, mirrored from economy.MAX_COINS (a test pins them equal).
# Duplicated rather than imported so this module stays pure. Escalated prices
# clamp here: nothing may cost more than a wallet can physically hold.
MAX_PRICE = 2**63 - 1  # mirrors economy.MAX_COINS; a test pins them equal

# Each repeat purchase of the same splurge costs this much more than the last.
ESCALATION = 1.6

# The one splurge with a mechanical effect — see the module docstring. Named
# here so cogs/splurge.py and economy.py agree on the key without hardcoding
# the string in three places.
SHARES_KEY = "house_share"

# --- Tiers -----------------------------------------------------------------
# (tier number, display name, wealth needed to unlock, the flavor line shown
# when it's still locked). Wealth is wallet + bank (economy.get_wealth).
TIERS = {
    1: ("Petty Cash", 0,
        "Everyone starts here. Congratulations."),
    2: ("Disposable Income", 1_000_000,
        "Come back when you have a million to waste."),
    3: ("Serious Money", 100_000_000,
        "The good stuff opens at a hundred million."),
    4: ("Generational Wealth", 10_000_000_000,
        "Ten billion. Then we'll talk."),
    5: ("Oligarch", 1_000_000_000_000,
        "A trillion, or get out of the lobby."),
    6: ("Post-Economic", 100_000_000_000_000,
        "Money stopped meaning anything a hundred trillion ago."),
    7: ("Engine-Breaking", 500_000_000_000_000,
        "Half a quadrillion. At this point you're the problem."),
}

# --- Catalog ---------------------------------------------------------------
# `unique: True` means one per player, ever — a trophy, not a habit. Everything
# else is repeatable at an escalating price.
SPLURGES = {
    # --- Tier 1: Petty Cash -------------------------------------------------
    "energy_drink": {
        "name": "Gas Station Energy Drink", "emoji": "🥤", "tier": 1, "price": 5_000,
        "blurb": "A can of something legally distinct from battery acid.",
        "flavor": "Tastes like a fire alarm. You buy another immediately.",
    },
    "scratchers": {
        "name": "Fistful of Scratchers", "emoji": "🎫", "tier": 1, "price": 15_000,
        "blurb": "Lottery tickets you scratch and immediately throw away.",
        "flavor": "Zero winners. You knew that going in. You did it anyway.",
    },
    "gold_chain": {
        "name": "Suspiciously Light Gold Chain", "emoji": "📿", "tier": 1, "price": 40_000,
        "blurb": "It's gold in the same way a hot dog is beef.",
        "flavor": "Turned your neck green in under an hour. Worth it.",
    },
    "novelty_hat": {
        "name": "Novelty Top Hat", "emoji": "🎩", "tier": 1, "price": 60_000,
        "blurb": "Enormous. Impractical. Yours.",
        "flavor": "You wear it to the casino. Nobody comments. You mention it four times.",
    },
    "bar_tab": {
        "name": "Cover the Whole Bar Tab", "emoji": "🍺", "tier": 1, "price": 90_000,
        "blurb": "You buy a round for strangers who will not remember you.",
        "flavor": "Three of them said 'thanks man'. That's the entire return on investment.",
    },
    "billboard": {
        "name": "Roadside Billboard of Your Face", "emoji": "🪧", "tier": 1, "price": 150_000,
        "blurb": "Forty feet of you, squinting at traffic.",
        "flavor": "Two accidents so far. Both entirely deserved.",
    },
    "ringtone": {
        "name": "Custom Ringtone of Your Own Voice", "emoji": "🔔", "tier": 1, "price": 220_000,
        "blurb": "It's you, shouting your own name, every time anyone calls.",
        "flavor": "You have set this as your alarm. You hate waking up now.",
    },
    "taxidermy_raccoon": {
        "name": "Taxidermied Raccoon", "emoji": "🦝", "tier": 1, "price": 350_000,
        "blurb": "Posed mid-scream. Unsettling from every angle.",
        "flavor": "The taxidermist asked no questions and made no eye contact.",
    },

    # --- Tier 2: Disposable Income ------------------------------------------
    "hot_tub": {
        "name": "Hot Tub Nobody Will Sit In", "emoji": "🛁", "tier": 2, "price": 600_000,
        "blurb": "Six seats. You have invited zero people.",
        "flavor": "The chemicals cost more than the tub. It's been beige for months.",
    },
    "jet_ski": {
        "name": "Jet Ski (No Lake Nearby)", "emoji": "🌊", "tier": 2, "price": 1_500_000,
        "blurb": "A watercraft, on a trailer, in a driveway, forever.",
        "flavor": "You've sat on it in the garage making the noise. Twice.",
    },
    "vanity_plate": {
        "name": "Vanity Plate Reading 'DEGEN'", "emoji": "🚗", "tier": 2, "price": 2_500_000,
        "blurb": "Seven letters announcing your entire personality.",
        "flavor": "The DMV clerk sighed so hard the form moved.",
    },
    "toast_chef": {
        "name": "Private Chef Who Only Makes Toast", "emoji": "👨‍🍳", "tier": 2, "price": 4_000_000,
        "blurb": "Classically trained. Contractually limited to toast.",
        "flavor": "It is, admittedly, exceptional toast.",
    },
    "racehorse": {
        "name": "Racehorse With Three Good Legs", "emoji": "🐎", "tier": 2, "price": 7_500_000,
        "blurb": "A thoroughbred with an asterisk.",
        "flavor": "Came last. Bit a steward. You've never been prouder.",
    },
    "gold_toilet": {
        "name": "Solid Gold Toilet", "emoji": "🚽", "tier": 2, "price": 12_000_000,
        "blurb": "Freezing cold. Structurally questionable. Extremely gold.",
        "flavor": "Guests ask about it. You explain at length. They stop asking.",
    },
    "self_statue": {
        "name": "Life-Size Statue of Yourself", "emoji": "🗿", "tier": 2, "price": 18_000_000,
        "unique": True,
        "blurb": "Marble. Heroic pose. Nobody asked for it.",
        "flavor": "The sculptor took liberties with the jawline. You paid extra for them.",
    },
    "fireworks_3am": {
        "name": "Fireworks Show at 3 AM", "emoji": "🎆", "tier": 2, "price": 25_000_000,
        "blurb": "Twenty minutes of artillery over a sleeping neighborhood.",
        "flavor": "Four noise complaints and one genuine call to the authorities.",
    },

    # --- Tier 3: Serious Money ----------------------------------------------
    "yacht": {
        "name": "Yacht You'll Never Board", "emoji": "⛵", "tier": 3, "price": 50_000_000,
        "blurb": "Moored somewhere expensive, accruing barnacles.",
        "flavor": "The crew has stopped sending updates. You've stopped reading them.",
    },
    "legally_ambiguous_tiger": {
        "name": "Legally Ambiguous Tiger", "emoji": "🐅", "tier": 3, "price": 90_000_000,
        "blurb": "Ownership status: pending, in several jurisdictions.",
        "flavor": "It does not like you. It has made this extremely clear.",
    },
    "sandbar": {
        "name": "Sandbar That Floods Daily", "emoji": "🏝️", "tier": 3, "price": 175_000_000,
        "blurb": "Beachfront property, twice a day, briefly.",
        "flavor": "The deed is technically valid for about four hours each morning.",
    },
    "pilotless_helicopter": {
        "name": "Helicopter With No Pilot", "emoji": "🚁", "tier": 3, "price": 300_000_000,
        "blurb": "A helicopter. That's the whole purchase. No pilot included.",
        "flavor": "You've been in the seat. You have not touched anything. Good.",
    },
    "vault_room": {
        "name": "Vault Room For Coins You Won't Spend", "emoji": "🏛️", "tier": 3, "price": 500_000_000,
        "blurb": "A reinforced room to store money you refuse to use.",
        "flavor": "You go in and look at it sometimes. This is not a hobby. This is a warning sign.",
    },
    "last_place_team": {
        "name": "Last-Place Sports Team", "emoji": "⚽", "tier": 3, "price": 900_000_000,
        "blurb": "Yours now. Still losing. Now it's your fault.",
        "flavor": "The fans have made a banner about you. It is not complimentary.",
    },
    "empty_skyscraper": {
        "name": "Empty Skyscraper", "emoji": "🏢", "tier": 3, "price": 1_500_000_000,
        "blurb": "Ninety floors. Zero tenants. Lights on anyway.",
        "flavor": "Visible from orbit at night. Costs a fortune. Contains one chair.",
    },
    "submarine": {
        "name": "Personal Submarine (Untested)", "emoji": "🛥️", "tier": 3, "price": 2_500_000_000,
        "blurb": "Rated to a depth nobody has been willing to verify.",
        "flavor": "The manual is in a language the manufacturer refuses to identify.",
    },

    # --- Tier 4: Generational Wealth ----------------------------------------
    "private_island": {
        "name": "Actual Private Island", "emoji": "🏖️", "tier": 4, "price": 5_000_000_000,
        "blurb": "A real one, above sea level, with trees and everything.",
        "flavor": "You've visited once. It was humid. You left early.",
    },
    "space_ticket": {
        "name": "One-Way Space Ticket", "emoji": "🚀", "tier": 4, "price": 12_000_000_000,
        "blurb": "Emphasis, throughout the paperwork, on 'one-way'.",
        "flavor": "You have not booked a date. You will not book a date.",
    },
    "small_angry_dinosaur": {
        "name": "Cloned Dinosaur (Small, Angry)", "emoji": "🦖", "tier": 4, "price": 25_000_000_000,
        "blurb": "Knee-high. Furious. Extremely illegal.",
        "flavor": "It has learned to open the fridge. Nobody taught it that.",
    },
    "crater_deed": {
        "name": "Deed to a Moon Crater", "emoji": "🌙", "tier": 4, "price": 45_000_000_000,
        "blurb": "A certificate no government on any world recognizes.",
        "flavor": "Framed in the hallway. You point it out to everyone who visits.",
    },
    "volcano_lair": {
        "name": "Hollowed-Out Volcano Lair", "emoji": "🌋", "tier": 4, "price": 80_000_000_000,
        "blurb": "Active. That's not a bug, that's the aesthetic.",
        "flavor": "The contractors quit twice. The second time they didn't come back for the tools.",
    },
    "one_way_time_machine": {
        "name": "Time Machine That Only Goes Forward", "emoji": "⏳", "tier": 4, "price": 140_000_000_000,
        "blurb": "Fully functional. Travels forward at exactly one second per second.",
        "flavor": "The salesman was technically honest and you technically signed.",
    },
    "ego_cathedral": {
        "name": "Cathedral to Your Own Ego", "emoji": "⛪", "tier": 4, "price": 200_000_000_000,
        "unique": True,
        "blurb": "Stained glass depicting your greatest bets. Mostly the losses.",
        "flavor": "The congregation is zero. The acoustics are magnificent.",
    },
    "carved_mountain": {
        "name": "Mountain With Your Face Carved In It", "emoji": "🏔️", "tier": 4, "price": 250_000_000_000,
        "unique": True,
        "blurb": "Permanent, enormous, and visible from three counties.",
        "flavor": "They got the nose wrong. There is no fixing it. It is forever.",
    },

    # --- Tier 5: Oligarch ---------------------------------------------------
    "small_country_stake": {
        "name": "Controlling Stake in a Small Country", "emoji": "🏳️", "tier": 5, "price": 500_000_000_000,
        "blurb": "You now have opinions about their agriculture policy.",
        "flavor": "The national anthem has been quietly re-recorded in your key.",
    },
    "weather_rights": {
        "name": "Rights to the Local Weather", "emoji": "🌦️", "tier": 5, "price": 1_000_000_000_000,
        "blurb": "It still does whatever it wants. But legally, it's yours.",
        "flavor": "You get blamed for every rainy weekend now. Correctly.",
    },
    "orbital_billboard": {
        "name": "Orbital Billboard", "emoji": "🛰️", "tier": 5, "price": 2_000_000_000_000,
        "blurb": "Your name, in low earth orbit, visible at dusk.",
        "flavor": "Astronomers have written a formal letter. You framed that too.",
    },
    "black_hole_naming": {
        "name": "Naming Rights to a Black Hole", "emoji": "🕳️", "tier": 5, "price": 4_000_000_000_000,
        "blurb": "An object that destroys everything it touches, named after you.",
        "flavor": "Astronomers called the name 'thematically appropriate' and hung up.",
    },
    "private_army": {
        "name": "Private Army (Unpaid, Mutinous)", "emoji": "🎖️", "tier": 5, "price": 7_000_000_000_000,
        "blurb": "Thousands strong. Morale: catastrophic.",
        "flavor": "They've elected a spokesman. He wants a word. You are avoiding him.",
    },
    "sun_dimmer": {
        "name": "Device That Slightly Dims the Sun", "emoji": "☀️", "tier": 5, "price": 12_000_000_000_000,
        "blurb": "Only by a bit. Only sometimes. Nobody consented to this.",
        "flavor": "Crop yields are down four percent and it is squarely your doing.",
    },
    "clone_army": {
        "name": "A Thousand Clones of Yourself", "emoji": "👥", "tier": 5, "price": 18_000_000_000_000,
        "blurb": "All of them gamble. None of them are good at it.",
        "flavor": "They've formed a union. Their first demand is that you stop.",
    },
    "new_element": {
        "name": "A New Element Named After You", "emoji": "⚗️", "tier": 5, "price": 25_000_000_000_000,
        "unique": True,
        "blurb": "Synthesized at enormous cost. Half-life: four milliseconds.",
        "flavor": "It existed. Briefly. Like most of your good ideas.",
    },

    # --- Tier 6: Post-Economic ----------------------------------------------
    "delete_monday": {
        "name": "Delete Monday From the Calendar", "emoji": "📅", "tier": 6, "price": 50_000_000_000_000,
        "blurb": "Gone. Tuesday is now load-bearing.",
        "flavor": "Nobody thanked you. Tuesday has become significantly worse.",
    },
    "gravity_lease": {
        "name": "Lease on Gravity", "emoji": "🪐", "tier": 6, "price": 80_000_000_000_000,
        "blurb": "Ninety-nine years, renewable, non-transferable.",
        "flavor": "You have not read the termination clause. You should read it.",
    },
    "buy_a_number": {
        "name": "Buy a Number (It's Yours Now)", "emoji": "🔢", "tier": 6, "price": 145_000_000_000_000,
        "blurb": "One integer, exclusively licensed to you. Others must pay to count past it.",
        "flavor": "You chose a small one. Mathematicians are furious. Accountants are worse.",
    },
    "rename_ocean": {
        "name": "Rename an Ocean", "emoji": "🌊", "tier": 6, "price": 120_000_000_000_000,
        "blurb": "Every map, every atlas, every globe. Updated.",
        "flavor": "Sailors refuse to say it out loud. They call it 'the other one'.",
    },
    "buy_silence": {
        "name": "Buy the Concept of Silence", "emoji": "🤐", "tier": 6, "price": 175_000_000_000_000,
        "blurb": "You own quiet now. Everyone else is renting.",
        "flavor": "You have not experienced any since the purchase. Rich irony, that.",
    },
    "edit_physics": {
        "name": "One Edit to the Laws of Physics", "emoji": "⚛️", "tier": 6, "price": 200_000_000_000_000,
        "blurb": "A single change, applied universally, no take-backs.",
        "flavor": "You used it to make dice slightly heavier. It did not help you win.",
    },
    "own_a_color": {
        "name": "Exclusive Ownership of a Color", "emoji": "🎨", "tier": 6, "price": 220_000_000_000_000,
        "unique": True,
        "blurb": "Nobody else may perceive it without your written consent.",
        "flavor": "You picked a shade of beige. This says everything about you.",
    },
    "second_moon": {
        "name": "Commission a Second Moon", "emoji": "🌒", "tier": 6, "price": 250_000_000_000_000,
        "unique": True,
        "blurb": "The tides are a disaster. It's up there anyway.",
        "flavor": "Coastal cities have questions. You have a moon.",
    },

    # --- Tier 7: Engine-Breaking --------------------------------------------
    SHARES_KEY: {
        "name": "Buy Into the House", "emoji": "🏛️", "tier": 7, "price": 300_000_000_000_000,
        "blurb": ("**THE ONLY SPLURGE THAT DOES SOMETHING.** One share of the "
                  "casino. Shareholders split **25% of house profit**, paid out "
                  "as the house earns it — and are **barred from gambling** for "
                  "good. Buy more shares for a bigger slice; every new investor "
                  "dilutes everyone."),
        "flavor": "You stopped playing the game and started owning a piece of it. Congratulations, allegedly.",
    },
    "own_luck": {
        "name": "Sole Ownership of Luck", "emoji": "🍀", "tier": 7, "price": 350_000_000_000_000,
        "unique": True,
        "blurb": "The abstract concept. Deeded to you. Exclusively.",
        "flavor": "It has not made you luckier. Ownership and possession are different things.",
    },
    "delete_a_year": {
        "name": "Delete a Year From History", "emoji": "🗓️", "tier": 7, "price": 450_000_000_000_000,
        "blurb": "Pick one. It's gone. Everyone quietly agrees not to mention it.",
        "flavor": "Something important happened in there. Nobody can remember what.",
    },
    "unmake_gambling": {
        "name": "Unmake the Concept of Gambling", "emoji": "🚫", "tier": 7, "price": 550_000_000_000_000,
        "unique": True,
        "blurb": "The single most self-defeating purchase available.",
        "flavor": "It didn't take. You're still here. So is everyone else.",
    },
    "rewrite_arithmetic": {
        "name": "Rewrite Arithmetic", "emoji": "➗", "tier": 7, "price": 600_000_000_000_000,
        "blurb": "Addition works differently now. Nobody consulted anybody.",
        "flavor": "Your balance is unchanged. Somehow. That part was load-bearing.",
    },
    "buy_the_void": {
        "name": "Purchase the Void You've Been Burning Into", "emoji": "🕳️", "tier": 7, "price": 750_000_000_000_000,
        "unique": True,
        "blurb": "Every coin you've ever destroyed went somewhere. You now own there.",
        "flavor": "It is full of your money. You cannot get any of it back. That was the deal.",
    },
    "become_the_bot": {
        "name": "Become BLBot", "emoji": "🤖", "tier": 7, "price": 850_000_000_000_000,
        "unique": True,
        "blurb": "Total identity transfer. You are the house now. Forever.",
        "flavor": "You have read every bet ever placed. You wish you hadn't.",
    },
    "overflow_the_counter": {
        "name": "Deliberately Overflow the Coin Counter", "emoji": "💥", "tier": 7, "price": 900_000_000_000_000,
        "blurb": "You've heard the engine has a limit. You'd like to pay to find it.",
        "flavor": "It held. It always holds now. You spent a fortune proving someone patched it.",
    },
}


def tier_name(tier: int) -> str:
    """Display name for a tier number."""
    return TIERS.get(tier, ("Unknown", 0, ""))[0]


def tier_requirement(tier: int) -> int:
    """Wealth needed to unlock a tier."""
    return TIERS.get(tier, ("", 0, ""))[1]


def tier_locked_hint(tier: int) -> str:
    """The taunt shown for a tier the player hasn't unlocked."""
    return TIERS.get(tier, ("", 0, ""))[2]


def unlocked_tiers(wealth: int) -> list[int]:
    """Every tier a player of this wealth can buy from, lowest first."""
    return [t for t in sorted(TIERS) if wealth >= tier_requirement(t)]


def next_tier(wealth: int) -> int | None:
    """The next tier this player hasn't unlocked yet, or None at the top."""
    for t in sorted(TIERS):
        if wealth < tier_requirement(t):
            return t
    return None


def price_for(key: str, owned: int = 0) -> int:
    """What the next copy of `key` costs someone who already owns `owned`.

    Repeat purchases escalate geometrically (ESCALATION per copy) and clamp at
    MAX_PRICE — nothing may cost more than a wallet can physically hold."""
    entry = SPLURGES[key]
    price = int(entry["price"] * (ESCALATION ** max(0, owned)))
    return min(max(price, entry["price"]), MAX_PRICE)


def is_unique(key: str) -> bool:
    """True if this splurge is a one-per-player trophy."""
    return bool(SPLURGES[key].get("unique"))


def by_tier(tier: int) -> list[tuple[str, dict]]:
    """Every (key, entry) in a tier, cheapest first."""
    return sorted(
        ((k, v) for k, v in SPLURGES.items() if v["tier"] == tier),
        key=lambda kv: kv[1]["price"],
    )


def resolve(text: str) -> str | None:
    """Find a splurge key from loose user input — exact key, exact name, or a
    unique case-insensitive substring of either. None if it's ambiguous or
    unknown, so the caller can say so instead of guessing wrong."""
    if not text:
        return None
    needle = text.strip().lower()
    if needle in SPLURGES:
        return needle
    hits = [k for k, v in SPLURGES.items() if v["name"].lower() == needle]
    if len(hits) == 1:
        return hits[0]
    hits = [k for k, v in SPLURGES.items()
            if needle in k.lower() or needle in v["name"].lower()]
    return hits[0] if len(hits) == 1 else None


# --- Burn ranks ------------------------------------------------------------
# Titles earned on LIFETIME coins destroyed through the catalog. Purely a
# bragging surface for /flex and /bonfire — no mechanical effect, same as the
# splurges themselves.
BURN_RANKS = [
    (0, "Tightwad", "🪙"),
    (1_000_000, "Loose Change", "💵"),
    (100_000_000, "Spender", "💸"),
    (10_000_000_000, "Big Spender", "🔥"),
    (1_000_000_000_000, "Conspicuous Consumer", "🎩"),
    (50_000_000_000_000, "Money Incinerator", "🌋"),
    (250_000_000_000_000, "Economic Hazard", "☢️"),
    (750_000_000_000_000, "The Void's Best Customer", "🕳️"),
]


def burn_rank(total_burned: int) -> tuple[str, str]:
    """(title, emoji) earned for a lifetime burn total."""
    title, emoji = BURN_RANKS[0][1], BURN_RANKS[0][2]
    for threshold, name, icon in BURN_RANKS:
        if total_burned >= threshold:
            title, emoji = name, icon
    return title, emoji


def next_rank(total_burned: int) -> tuple[int, str] | None:
    """(threshold, title) of the next rank up, or None at the top."""
    for threshold, name, _ in BURN_RANKS:
        if total_burned < threshold:
            return threshold, name
    return None
