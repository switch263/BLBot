import discord
from discord.ext import commands
from discord import app_commands
import random
import string
import sys
import os
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from economy import get_coins, add_coins, deduct_coins, jail_message

logger = logging.getLogger(__name__)

MIN_BET = 50

# ==============================================================================
# COMPONENT POOLS
# Each outcome template pulls random pieces from these to generate a unique line.
# Over 20 pools × 40 outcomes × 2-4 templates each = hundreds of thousands of combos.
# ==============================================================================

KITTY = [
    "a tabby named Steve French", "a three-legged cat called Rascal",
    "Whiskers IV", "Fartso", "Lil Stinker", "Madame Purrington",
    "a feral orange bastard called Jimbo", "'The Shit Kitty'",
    "a kitten with a mustache", "Big Dave (a Maine Coon the size of a raccoon)",
    "a kitten named after Ricky's dad", "a one-eared menace called Doctor",
    "'Princess Trinketbottom, Countess of Lot 3'", "a skinny kitten named Tupac",
    "a cat who won't stop farting (you named him Julian)",
]

KITTY_DANGER = [
    "a pine tree", "the Kabooger Industries dumpster", "Julian's trunk",
    "a discarded washing machine", "the culvert behind the Dairy Mart",
    "a smoldering tire pile", "the roof of the Dairy Mart",
    "a broken fridge in Lot 9", "Ricky's hood (the car, not the garment)",
    "a possum family's custody battle", "a shopping cart going downhill",
    "a tarp labeled 'DO NOT OPEN'", "the well behind the Lahey residence",
    "Randy's gym bag (the kitty did NOT consent)",
]

BUBBLES_QUIP = [
    "'That's my kitty, boys!'", "'Frig OFF.'", "'Decent, decent.'",
    "'It's all she's gonna be.'", "'Don't touch my kitty.'",
    "'Kitties are smarter than people, bud.'",
    "'I'll be in the shed if anybody needs me.'",
    "'Sweet baby corn on a cracker.'",
    "'I could tell you a lot of things about a lot of things.'",
    "'I got a doctorate in kitties.'",
]

RICKY_ISM = [
    "'Worst-case Ontario.'", "'It's not rocket appliances.'",
    "'I am not a smart man, Julian.'", "'I'll get a drivin' lesbian.'",
    "'Way she goes, sometimes way she goes.'",
    "'Get two birds stoned at once.'",
    "'Make like a tree, and get outta here.'",
    "'The ball's in your corner now.'",
    "'Survival of the fetus.'",
    "'What comes around is all around.'",
    "'Gotta take the bull by the horns of a dilemma.'",
    "'I'm not the sharpest tool in the world, boys.'",
    "'Indian giver? That's fucking racist, Julian.'",
    "'I am the liquor' — no wait, that's Jim.'",
]

JULIAN_LINE = [
    "'That's just the way she goes, boys.'",
    "'This is the SMART play, listen to me.'",
    "'Stay calm, we got this.'",
    "'I had this ALL figured out.'",
    "He sips his rum and coke. Does not spill a drop.",
    "'This is the one, boys. This is the big score.'",
    "'Trust me.' He does not elaborate.",
    "'Alright, here's what we're gonna do.'",
    "He stares at the horizon for five full seconds.",
    "'Boys, boys, listen. Listen.'",
    "He does the Julian Walk.",
]

LAHEY_LINE = [
    "'The *hic* SHIT, is HITTING, the FAN.'",
    "'There's a shit storm coming, boys.'",
    "'I am the liquor, Randy.'",
    "'Shit wind, Randy. Shit wind.'",
    "'I have shit breath, Bubs.'",
    "'What if I'm a shit magnet?'",
    "'The shit puppets are off their strings.'",
    "'Randy. The shit abyss stares back.'",
    "'Everyone is a shit.'",
    "'The shit hawks are circling, Randy.'",
    "'I'm gonna shit tonight.'",
    "'I'd say we're in a shit tsunami, Randy.'",
]

RANDY_LINE = [
    "Randy is eating a cheeseburger. Shirtless.",
    "Randy takes off his shirt for emphasis.",
    "Randy is always here somehow. It is unsettling.",
    "'I love cheeseburgers, Mr. Lahey.'",
    "'I'm hungry, Jim.'",
    "Randy's gut enters the room before he does.",
    "Randy is drinking Mountain Dew out of a 2L bottle.",
    "'Jimmmm, can I get a burger?'",
    "Randy is eating a burger AND an ice cream sandwich at once.",
]

CASH_ITEM = [
    "a wet stack of bills",
    "Julian's secret rum-stained cash stash",
    "a sleeve of coins labeled 'FOR FUEL'",
    "a gnarled-up roll of twenties",
    "a Ziploc of loose change and a tooth (the tooth is free)",
    "coins in a Kraft Dinner box",
    "a wad in a prop microphone",
    "cash stuffed in a tube sock",
    "a cookie tin labeled 'NOT DRUGS'",
    "a wad duct-taped to the underside of a camper",
    "a wallet a gym rat forgot at the weight bench",
    "change jar labeled 'BUBBLES'S KITTY FUND — DO NOT TOUCH' (you touched it)",
    "rolled bills in a McCain's Crinkle Cut Fries bag",
    "an envelope marked 'DEFINITELY NOT GRANDMA'S INHERITANCE'",
]

LOCATION = [
    "behind the Dairy Mart",
    "in Lot 3",
    "outside Bubbles's shed",
    "in Ricky's Chrysler LeBaron",
    "at the DirtyBurger drive-thru",
    "in J-Roc's studio (the shed (the OTHER shed))",
    "at the detox center (yet again)",
    "at Julian's cousin's wedding",
    "in the Sunnyvale parking lot, after dark",
    "next to the coin-operated hydro pole",
    "in the Swayze Express",
    "at the Sunnyvale Gazebo (technically a tarp)",
    "at Sam Losco's place (the lawn has eyes)",
    "near Ray's wheelchair after a long night",
]

SCHEME = [
    "a kitty resort",
    "an underground hash farm",
    "a fireworks stand (the stand itself is illegal)",
    "a car wash that only does passenger sides",
    "the Free-Range Tire Co.",
    "a bootleg Canadian X-Men porno",
    "Sunnyvale Private Security (just Randy with a flashlight)",
    "a shopping cart repo operation",
    "a 'gentlemen's' open-mic night at Julian's trailer",
    "a weed-whacker sharpening business that is suspiciously profitable",
    "a scheme to pawn off all the microwaves in the park back to the park",
]

ABSURDITY = [
    "A possum watches in silent judgment.",
    "A plastic bag drifts past like destiny.",
    "The sky cracks open and a single crow laughs.",
    "The park's one working streetlight flickers in Morse code.",
    "A shit hawk circles ominously.",
    "The hydro pole hums. It has opinions.",
    "A raccoon gives you the finger. Impressive.",
    "Somewhere, a baby cries. It might be Randy.",
    "A Molson bottle rolls exactly 14 inches and stops.",
    "An Oldsmobile starts on its own. Nobody acknowledges this.",
    "A disposable camera flash goes off. Nobody is holding a camera.",
    "A tiny child with a big mullet makes eye contact and walks away.",
    "The Dairy Mart cashier audibly sighs.",
    "Ray's wheelchair rolls by, unmanned.",
]

CHAR_LINE = RICKY_ISM + JULIAN_LINE + LAHEY_LINE + BUBBLES_QUIP

POOLS = {
    "kitty": KITTY,
    "kitty_danger": KITTY_DANGER,
    "bubbles_quip": BUBBLES_QUIP,
    "ricky_ism": RICKY_ISM,
    "julian_line": JULIAN_LINE,
    "lahey_line": LAHEY_LINE,
    "randy_line": RANDY_LINE,
    "cash_item": CASH_ITEM,
    "location": LOCATION,
    "scheme": SCHEME,
    "absurdity": ABSURDITY,
    "char_line": CHAR_LINE,
}

# ==============================================================================
# OUTCOMES — each with a list of templates.
# Templates can use {name} (the user) and {pool_name} for any POOLS key.
# ==============================================================================

OUTCOMES = [
    # ----- BIG FLAT WINS -----
    {"weight": 4, "kind": "flat", "value": 300, "templates": [
        "🐱 **Bubbles rescues {kitty} from {kitty_danger}.** {bubbles_quip} Hands {name} 300 coins as a finder's fee.",
        "🐱 Bubbles finds {kitty} {location}. {bubbles_quip} Gives {name} 300 'for your continued moral support.'",
        "🐱 **Bubbles builds a kitty palace** and invites {name} to the ribbon-cutting. {bubbles_quip} 300 coin honorarium.",
    ]},
    {"weight": 3, "kind": "flat", "value": 500, "templates": [
        "💰 You find {cash_item} under the porch. Julian is asleep. {name} walks away with 500.",
        "💰 {cash_item} — just sitting {location}. {julian_line} You take it anyway. +500.",
        "💰 Ricky leaves {cash_item} on the car roof. Drives off. You collect. +500.",
    ]},
    {"weight": 3, "kind": "flat", "value": 400, "templates": [
        "🌿 **Ricky's hash garden harvest is bountiful.** {ricky_ism} The Mounties are on vacation. +400.",
        "🌿 Ricky gives you a share of the 'sweater' operation. {ricky_ism} +400.",
        "🌿 You help harvest a half-decent crop {location}. {ricky_ism} 400 coin cut.",
    ]},
    {"weight": 5, "kind": "flat", "value": 150, "templates": [
        "🛒 **Bubbles builds a shopping cart** and sells it to {name} at cost. Nets you 150. {bubbles_quip}",
        "🛒 Bubbles fixes your go-kart and refuses payment. You 'accidentally' drop 150 back in his coat. {absurdity}",
        "🛒 Bubbles trades you a 'customized' cart for 150. {bubbles_quip}",
    ]},
    {"weight": 6, "kind": "flat", "value": 100, "templates": [
        "🎤 **J-Roc drops a verse about {name}.** 'Yo, you know how it is, know'mean?' +100 in royalties.",
        "🎤 J-Roc insists {name} sounds 'like a sample,' puts you on the mixtape. 100 coin studio stipend.",
        "🎤 T cuts a track dissing {name}. It slaps SO hard {name} gets the publishing. +100.",
    ]},
    {"weight": 5, "kind": "flat", "value": 200, "templates": [
        "🍻 **Sam Losco buys you a round.** Then another. Then pays {name} 200 to leave. Fair.",
        "🍻 Sam Losco traps {name} in a 45-minute rant about 'the ferret situation.' Pays 200 in hush money.",
        "🍻 Sam Losco shouts at you {location} and then tips {name} 200 coins for 'listening.'",
    ]},
    {"weight": 5, "kind": "flat", "value": 250, "templates": [
        "🍝 Sam Losco invites {name} over 'for pepperoni.' Don't ask what kind. You leave 250 richer.",
        "🍝 Sam's basement has 'the good pepperoni.' {name} doesn't look at anything too closely. +250.",
        "🍝 Sam pays {name} 250 to help 'move some pepperoni' from one freezer to another. {absurdity}",
    ]},
    {"weight": 5, "kind": "flat", "value": 180, "templates": [
        "🌳 **Bubbles shows {name} the Candy Tree.** You did not know it was real. +180. {bubbles_quip}",
        "🌳 Bubbles reveals he has a Candy Tree out back. The branches jangle with Werther's Originals. +180.",
        "🌳 The Candy Tree exists. Bubbles forbids questions. {bubbles_quip} +180.",
    ]},
    {"weight": 5, "kind": "flat", "value": 220, "templates": [
        "🎣 **Ricky takes {name} fishin'** and catches a muffler. Inside: 220 coins. {ricky_ism}",
        "🎣 You go fishin' with Ricky. Ricky catches a shopping cart. Cart is full of change. {ricky_ism} +220.",
        "🎣 You help Ricky 'fish' (he just sits on the dock with a bat). {ricky_ism} Somehow nets 220.",
    ]},
    {"weight": 3, "kind": "flat", "value": 350, "templates": [
        "🎰 **Sam's illegal VLT machine pays out for once.** +350 and a stuffed ferret. {absurdity}",
        "🎰 Lucky night at Sam Losco's back room. +350. You don't talk about this in public.",
        "🎰 Sam lets you play 'just one pull.' It hits. +350. Do not go back tomorrow.",
    ]},
    {"weight": 3, "kind": "flat", "value": 450, "templates": [
        "💼 **{name} briefly becomes Julian's lawyer.** No qualifications. Court does not notice. +450.",
        "💼 Julian needs a 'legal advisor.' {name} said 'sure.' Case dismissed. Retainer: 450.",
        "💼 {name} argues a traffic ticket down using only 'way she goes' as precedent. Judge pays you 450.",
    ]},
    {"weight": 2, "kind": "flat", "value": 600, "templates": [
        "💸 **You find Cyrus's stash in the tall grass.** You run. You keep running. 600 coins and night terrors.",
        "💸 Cyrus's envelope, forgotten under a pylon. You don't question it. +600 and you leave town briefly.",
        "💸 {absurdity} And then you found 600 coins. Unrelated. Probably.",
    ]},
    {"weight": 4, "kind": "flat", "value": 160, "templates": [
        "🍺 **Jim Lahey buys {name} a drink** and quotes Nietzsche for 20 minutes. You leave with 160 and thoughts.",
        "🍺 Jim Lahey recites a poem titled 'The Shit Apostle.' {name} claps. Lahey tips 160.",
        "🍺 Lahey corners {name} with: {lahey_line} Pays 160 for the audience.",
    ]},
    {"weight": 4, "kind": "flat", "value": 100, "templates": [
        "🐈 Bubbles lets {name} pet a kitty for free. Also hands you 100 coins because 'you looked like you needed it, bud.'",
        "🐈 Kitty audit complete: {name} is approved. Bubbles pays 100. {bubbles_quip}",
        "🐈 Bubbles finds {name} {location} and just hands over 100 coins. No explanation. No eye contact.",
    ]},
    {"weight": 3, "kind": "flat", "value": 300, "templates": [
        "🪩 **{name} wins the Sunnyvale Talent Show** with a routine involving a shopping cart and pyrotechnics. +300.",
        "🪩 Talent night at the park: {name} performs 'the Julian' (just walks around with rum). +300 from judges.",
        "🪩 {name} enters the talent show, wins by default (everyone else was arrested). +300.",
    ]},

    # ----- MULTIPLIER WINS (scale with bet) -----
    {"weight": 5, "kind": "mult", "value": 3, "templates": [
        "🚗 **Julian's car scheme works.** {julian_line} ×3 your bet.",
        "🚗 Julian's 'collision resolution service' (insurance scam) pays out. {julian_line} ×3.",
        "🚗 You drive the getaway for Julian's {scheme}. Clean. ×3.",
    ]},
    {"weight": 2, "kind": "mult", "value": 5, "templates": [
        "📺 **Cable scam pays off.** J-Roc hooks up the whole park. Protection money rolls in. ×5.",
        "📺 You run {scheme} with J-Roc. It goes bigger than expected. ×5.",
        "📺 Everyone in Sunnyvale forgets to cancel their trial subscription to your fake service. ×5.",
    ]},
    {"weight": 7, "kind": "mult", "value": 2, "templates": [
        "🍔 **Randy's Dirty Burger delivery run** goes smooth. {randy_line} 2× cut.",
        "🍔 You ride shotgun on Randy's burger run. {randy_line} 2× payout.",
        "🍔 You convince Randy to share a tip. He shares half. 2×.",
    ]},
    {"weight": 1, "kind": "mult", "value": 10, "templates": [
        "🤼 **Greasy Jim wins the title match.** {name} had him at ×10 odds. You are rich and slightly oily.",
        "🤼 You bet on the underdog. The underdog bit the ref. ×10.",
        "🤼 Sunnyvale's illegal wrestling league pays out on a fluke. ×10. {absurdity}",
    ]},
    {"weight": 4, "kind": "mult", "value": 2.5, "templates": [
        "🎸 **You play bass for J-Roc's new mixtape.** 'Yo that's heat, {name}, that's HEAT.' ×2.5.",
        "🎸 J-Roc samples {name}'s voice saying 'frig off' and it hits the charts. ×2.5.",
        "🎸 You drop a single verse on J-Roc's track. {name} now has a SoundCloud. ×2.5.",
    ]},
    {"weight": 3, "kind": "mult", "value": 4, "templates": [
        "🚛 **You help Ricky hotwire the liquor store truck.** Everything goes exactly according to plan. Inconceivable. ×4.",
        "🚛 Ricky needed a wheelman for {scheme}. {name} drove. No cops. ×4.",
        "🚛 {name} runs a 'delivery' for Ricky. Don't ask what. ×4.",
    ]},
    {"weight": 2, "kind": "mult", "value": 6, "templates": [
        "🍟 **The Dirty Burger franchise pays out.** Julian paid his cousin back. {name} gets a cut. ×6.",
        "🍟 Your Dirty Burger shares appreciated 600%. {julian_line} ×6.",
        "🍟 {name} convinced corporate to expand the franchise into a third tarp. ×6.",
    ]},
    {"weight": 2, "kind": "mult", "value": 7, "templates": [
        "🎥 **The boys get a reality show deal** and {name} has producer credit. ×7.",
        "🎥 {name}'s 'behind the scenes' camera footage becomes a documentary. ×7.",
        "🎥 A network picks up 'Trailer Park {name}.' ×7.",
    ]},
    {"weight": 2, "kind": "mult", "value": 8, "templates": [
        "🐆 **THE SHIT LEOPARDS ARE LOOSE IN THE KITCHEN.** {lahey_line} You profit somehow. ×8.",
        "🐆 Shit tsunami opens a window of opportunity {name} did not see coming. ×8.",
        "🐆 Mid-chaos, {name} notices the till is unguarded. ×8. {absurdity}",
    ]},
    {"weight": 6, "kind": "mult", "value": 1.5, "templates": [
        "🛒 You corner the returnable-bottle market. SmartMart guy is livid. ×1.5.",
        "🛒 {name} runs a beer can collection route {location}. Bicycle powered. ×1.5.",
        "🛒 Ricky forgot to sell his empties. {name} did not. ×1.5.",
    ]},
    {"weight": 4, "kind": "mult", "value": 2, "templates": [
        "🚬 **Ricky sells {name} 'sweaters' (hash).** Quality surprisingly acceptable. You flip them. ×2.",
        "🚬 You broker a deal between Ricky and {location}. ×2. {ricky_ism}",
        "🚬 {name} is Ricky's newest associate. Lasts 14 hours. ×2 regardless.",
    ]},

    # ----- BREAK EVEN -----
    {"weight": 10, "kind": "mult", "value": 1, "templates": [
        "🏚️ **Just another day in Sunnyvale.** A shopping cart rolls by. {name} ponders. {absurdity} Break even.",
        "🏚️ Nothing happens today. {absurdity} Break even.",
        "🏚️ {name} walks laps around the park. {char_line} Bet returned.",
    ]},

    # ----- ZERO / LOSSES -----
    {"weight": 8, "kind": "zero", "value": None, "templates": [
        "🚔 **Ricky gets arrested** for 'drivin' without a lesbian.' {name} was in the car. Lose bet.",
        "🚔 Officer George Green pulls {name} over. {ricky_ism} Ticket > bet. Lose bet.",
        "🚔 {name} takes the fall for Ricky. Classic. Lose bet.",
    ]},
    {"weight": 6, "kind": "zero", "value": None, "templates": [
        "🍺 **{name} spent all their coins on rum & coke** trying to console Julian. Julian doesn't remember you. Lose bet.",
        "🍺 Julian invites {name} to 'celebrate.' Bar tab closes the bet. {julian_line}",
        "🍺 You match Julian drink-for-drink. Julian matched you silently with water. Lose bet.",
    ]},
    {"weight": 5, "kind": "zero", "value": None, "templates": [
        "🐦 **The shit hawks circle.** {name} drops the coins and takes cover. {lahey_line}",
        "🐦 Shit hawk drops {location}. {name} dives. Coins scatter.",
        "🐦 {name} stares at a shit hawk. The hawk wins the staring contest. Lose bet.",
    ]},
    {"weight": 4, "kind": "zero", "value": None, "templates": [
        "🪑 **Randy eats the last cheeseburger.** Both of them. Including {name}'s. {randy_line}",
        "🪑 {name} left food unattended. Randy was in a 50m radius. Guaranteed loss.",
        "🪑 {randy_line} And yeah, he ate your money too.",
    ]},
    {"weight": 5, "kind": "zero", "value": None, "templates": [
        "🛵 **Trinity 'borrows' {name}'s scooter AND some coins.** She's 12. {ricky_ism} You can't say no.",
        "🛵 Trinity requires 'gas money' for her bike. {name} pays. Trinity does not have a bike.",
        "🛵 {name} is out-hustled by a 12-year-old. Lose bet. {ricky_ism}",
    ]},
    {"weight": 3, "kind": "zero", "value": None, "templates": [
        "🚓 **The Mounties do a sweep.** {name} ditched coins {location}. They weren't even looking for you. Lose bet.",
        "🚓 Sarah warned {name} the Mounties were coming. {name} panicked.",
        "🚓 A K9 unit sniffs {name}. The dog is disappointed. Lose bet anyway.",
    ]},

    # ----- FINES (lose bet + percentage of bet) -----
    {"weight": 6, "kind": "fine", "value": 0.5, "templates": [
        "🥴 **Mr. Lahey stumbles up, drunk as a shit skunk.** {lahey_line} Surprise inspection. Fine.",
        "🥴 Jim Lahey fines {name} for {scheme}. {lahey_line}",
        "🥴 Lahey, swaying: {lahey_line} {name} pays a 'behavioral' fine.",
    ]},
    {"weight": 3, "kind": "fine", "value": 1.0, "templates": [
        "💩 **THE SHIT BLIZZARD ARRIVES.** {lahey_line} Double loss.",
        "💩 Shit tsunami. {name} loses bet + a full bet again. {absurdity}",
        "💩 Lahey screams at the sky. Somehow {name} is billed twice.",
    ]},
    {"weight": 3, "kind": "fine", "value": 0.75, "templates": [
        "🚜 **Corey and Trevor crash {name}'s car** into Lot 3 again. Body shop bill + bet. Ouch.",
        "🚜 Corey and Trevor borrow {name}'s car. 'For a thing.' The thing was a wall.",
        "🚜 Two dummies, one car, zero insurance. {name} pays. {ricky_ism}",
    ]},
    {"weight": 3, "kind": "fine", "value": 0.6, "templates": [
        "🔫 **Ricky shoots the air conditioner.** It lands on {name}'s car. Partial fine + bet. {ricky_ism}",
        "🔫 Ricky discharges a rifle 'accidentally.' {name} is somehow liable.",
        "🔫 Ricky was cleaning his gun. With his foot. Again. {name} pays the bills.",
    ]},
    {"weight": 3, "kind": "fine", "value": 0.6, "templates": [
        "🧟 **Ricky is convinced there's a grow-op ghost.** Burns sage. And the trailer. {name} co-signed.",
        "🧟 Ricky sets 'one small fire' to 'cleanse the place.' It is larger than one. Fine.",
        "🧟 A fire of Ricky's making. Again. {name} is the named insured.",
    ]},
    {"weight": 4, "kind": "mult", "value": 0.5, "templates": [
        "🎤 **Karaoke night at The Dirty Burger** goes sideways. Mr. Lahey commandeers the mic. Partial refund.",
        "🎤 {name} was halfway through 'Margaritaville' when Lahey snatched the mic.",
        "🎤 Open-mic chaos. Half your coins back. {lahey_line}",
    ]},

    # ----- FLAT LOSSES (bet + fixed amount) -----
    {"weight": 5, "kind": "flat", "value": -200, "templates": [
        "🧾 **Julian hands {name} his rum tab.** It is itemized. Dated back to 2004. Lose bet + 200.",
        "🧾 Julian: 'You owe me 200. From that thing.' {name} does not remember 'that thing.' Pays.",
        "🧾 Julian produces a napkin with numbers on it. It is legally binding in Sunnyvale. −200.",
    ]},
    {"weight": 3, "kind": "flat", "value": -300, "templates": [
        "🏠 **Randy has moved into {name}'s trailer.** He ate everything. Lose bet + 300 in groceries.",
        "🏠 Randy's 'just staying the night.' It has been seven nights. Groceries bill: 300.",
        "🏠 {randy_line} Also he's in your trailer now. Permanent. 300 in food damages.",
    ]},
    {"weight": 2, "kind": "flat", "value": -400, "templates": [
        "⛪ **Pastor Dave stopped by for a 'friendly chat.'** {name} is now tithing. Lose bet + 400.",
        "⛪ Pastor Dave's 'collection plate' is a pillowcase. {name} contributes 400.",
        "⛪ Dave smiles. His teeth are filed. {name} tithes 400. {absurdity}",
    ]},
    {"weight": 5, "kind": "flat", "value": -150, "templates": [
        "📼 **Bubbles charges {name} for a Beta tape** that's been late since 1993. Lose bet + 150.",
        "📼 Bubbles runs a library. Strict fines. {bubbles_quip} −150.",
        "📼 A video rental Bubbles loaned you in 1991 is now due. {name} pays 150 and a late fee.",
    ]},
    {"weight": 3, "kind": "flat", "value": -250, "templates": [
        "👮 **Officer George Green pulls {name} over** for 'looking Ricky-adjacent.' 250-coin ticket.",
        "👮 Green writes {name} a ticket for 'general vibes.' 250.",
        "👮 'You've got Ricky aura, son.' Green is not wrong. 250-coin fine.",
    ]},
    {"weight": 3, "kind": "flat", "value": -100, "templates": [
        "🐈 **Bubbles's kitty committee conducts an audit** of {name}'s recent decisions. Judgment is costly. −100.",
        "🐈 The kitties stare at {name} until {name} hands them 100 coins. This is a known transaction.",
        "🐈 Madame Purrington issues a ruling. {name} appeals. Appeal is rejected. 100-coin judgment.",
    ]},
]


def _compose(templates: list[str], name: str) -> str:
    """Pick a random template and fill in {name} + any {pool_name} placeholders."""
    template = random.choice(templates)
    fields = {"name": name}
    for _, field, _, _ in string.Formatter().parse(template):
        if field and field not in fields:
            fields[field] = random.choice(POOLS[field]) if field in POOLS else f"{{{field}}}"
    return template.format(**fields)


class Sunnyvale(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Sunnyvale Chronicles loaded.")

    def _pick(self):
        total = sum(o["weight"] for o in OUTCOMES)
        roll = random.uniform(0, total)
        running = 0.0
        for o in OUTCOMES:
            running += o["weight"]
            if roll <= running:
                return o
        return OUTCOMES[-1]

    async def _do_day(self, ctx_or_interaction, bet: int):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        async def reply(content, **kwargs):
            if is_slash:
                await ctx_or_interaction.response.send_message(content, **kwargs)
                return await ctx_or_interaction.original_response()
            return await ctx_or_interaction.send(content, **kwargs)

        if not guild:
            await reply("Server only, decent.")
            return
        jmsg = jail_message(guild.id, user.id)
        if jmsg:
            await reply(jmsg)
            return
        if bet < MIN_BET:
            await reply(f"Bet at least **{MIN_BET}** or Julian will find out, boys.")
            return
        if get_coins(guild.id, user.id) < bet:
            await reply(f"You're broke as frig. Balance: **{get_coins(guild.id, user.id)}**")
            return

        deduct_coins(guild.id, user.id, bet)
        outcome = self._pick()
        flavor = _compose(outcome["templates"], user.display_name)

        kind = outcome["kind"]
        if kind == "flat":
            value = outcome["value"]
            if value >= 0:
                add_coins(guild.id, user.id, value)
                net = value - bet
                line = f"**{'+'if net >= 0 else ''}{net}** coins _(flat payout of {value} minus {bet} bet)_"
            else:
                extra = min(get_coins(guild.id, user.id), abs(value))
                if extra > 0:
                    deduct_coins(guild.id, user.id, extra)
                line = f"**Lost {bet}** + extra **{extra}** in damages."
        elif kind == "mult":
            m = outcome["value"]
            payout = int(bet * m)
            add_coins(guild.id, user.id, payout)
            net = payout - bet
            line = f"**{'+'if net >= 0 else ''}{net}** coins _(×{m} on {bet} bet)_"
        elif kind == "zero":
            line = f"**Lost {bet}** coins."
        elif kind == "fine":
            m = outcome["value"]
            extra = min(get_coins(guild.id, user.id), int(bet * m))
            if extra > 0:
                deduct_coins(guild.id, user.id, extra)
                line = f"**Lost {bet}** + **{extra}** fine."
            else:
                line = f"**Lost {bet}**. Tried to fine you more but you're already tapped."
        else:
            line = "???"

        text = (
            f"🏚️ **{user.display_name}** rolls through Sunnyvale Trailer Park for **{bet}** coins.\n\n"
            f"{flavor}\n\n"
            f"{line}\n"
            f"Balance: **{get_coins(guild.id, user.id)}**"
        )
        await reply(text)

    @commands.command(name="sunnyvale", aliases=["tpb", "trailerparkboys"])
    @commands.guild_only()
    async def sunnyvale_prefix(self, ctx, bet: int):
        await self._do_day(ctx, bet)

    @app_commands.command(name="sunnyvale", description="Spend a day in Sunnyvale Trailer Park. Anything can happen. It usually does.")
    @app_commands.describe(bet=f"Coins to risk (min {MIN_BET})")
    async def sunnyvale_slash(self, interaction: discord.Interaction, bet: int):
        await self._do_day(interaction, bet)


async def setup(bot):
    await bot.add_cog(Sunnyvale(bot))
