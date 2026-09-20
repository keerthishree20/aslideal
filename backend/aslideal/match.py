"""Decide whether two listings are the same product.

A wrong match is worse than no match: comparing Airdopes Prime 412 against
the 413's prices, or against a ₹199 silicone case, would produce a
confident verdict about the wrong thing. So the rules are strict and a
listing that doesn't pass them is dropped rather than scored down.

A product is identified by its name up to and including its first model
number: 'Galaxy M56 5G Mobile (Light Green, 8GB...)' is 'galaxy m56',
'Nord Buds 4 TWS Earbuds with 52dB ANC' is 'nord buds 4'. The words after
that are descriptions ('Mobile', 'Smart Watch') that other sellers phrase
differently, so they aren't required.

1. The identity words must appear in the candidate, in order and side by
   side: boAt sells both 'Airdopes Prime 412' earbuds and 'Rockerz 412'
   headphones, and 'Pro 6' is not 'Buds Air 6 Pro'.
2. The candidate's name must not add a tier word (pro, max, plus...) the
   reference lacks: '15' is in 'iPhone 15 Pro' too.
3. The brand has to appear. A reference with no brand isn't matched at all.
4. A reference that states its memory (8GB, 128GB), or a count of jars or
   packs, only matches listings stating the same.
5. If the reference's name says what the product is after the model number
   ('Pro 6 Smart Watch'), the candidate must share one of those words:
   'Air Buds Pro 6' is earbuds.
6. Accessory, spare-part and refurbished words (case, motor, jar,
   renewed...) in the candidate but not the reference mean it's something
   *for* the product, or not new.
"""

import re

ACCESSORY_WORDS = {
    "case", "cover", "skin", "skins", "sticker", "protector", "tempered", "pouch",
    "strap", "straps", "holder", "stand", "mount", "compatible", "replacement",
    "decal", "sleeve", "keychain", "lanyard",
    # Spare parts. Words like 'motor' and 'jar' also appear in real product names
    # ('Turbo Motor', '3 Jars'), so parts are mostly caught by price instead.
    "spare", "spares", "part", "parts", "gasket", "coupler", "refill", "cartridge",
    "assly", "panel", "lcd", "guard",
    # not new
    "refurbished", "renewed", "refurb", "used", "preowned", "pre",
}
TIER_WORDS = {"pro", "max", "plus", "ultra", "lite", "mini", "neo", "fe", "anc", "prime"}
# Words sellers attach inconsistently; never evidence of a different product.
FILLER = {"the", "with", "and", "for", "of", "in", "new", "launch", "latest", "edition", "&", "w"}

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?\+?")


_CAPACITY = re.compile(r"^\d+(?:gb|tb)$")
# Sellers write the same size a dozen ways: '3L', '3 L', '3 Litre', '750 W', '100 g'.
_UNIT_GAP = re.compile(r"(\d+)\s*(gb|tb|ml|l|ltr|litre|litres|liter|liters|g|gm|gms|kg|w|watt|watts)\b")
_UNIT_CANON = {"ltr": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l",
               "gm": "g", "gms": "g", "watt": "w", "watts": "w"}


def _join_units(text: str) -> str:
    return _UNIT_GAP.sub(lambda m: m.group(1) + _UNIT_CANON.get(m.group(2), m.group(2)), text)


def tokens(text: str) -> list:
    """Lowercase words, with a trailing '+' split off as 'plus' (Pro+ is not Pro)
    and sizes normalised, so '3 Litre', '3L' and '3 L' are all '3l'."""
    out = []
    for t in _TOKEN.findall(_join_units((text or "").lower())):
        if t.endswith("+"):
            out += [t[:-1], "plus"]
        else:
            out.append(t)
    return out


def core_name(title: str) -> str:
    """The product's name before sellers start listing features.

    'Airdopes Prime 412, 4Mics AI-ENx Tech, 50 Hrs Battery (Midnight Black)'
    -> 'Airdopes Prime 412'. Amazon puts features after the first comma, most
    Google Shopping titles after a comma, pipe, dash, colon or bracket.
    """
    title = re.sub(r"^\s*20\d\d\s+launch\s+", "", title or "", flags=re.I)
    return re.split(r"\s*(?:,|\||\(|\[|\s-\s|\s–\s|;|:)", title, maxsplit=1)[0].strip()


def is_model(token: str) -> bool:
    return any(c.isdigit() for c in token)


def identity(title: str, brand: str = "") -> list:
    """The words that name this product: its name through the first model number
    and any tier words right after it ('Note 14 Pro plus')."""
    brand_words = set(tokens(brand))
    words = [t for t in tokens(core_name(title)) if t not in FILLER and t not in brand_words]
    for i, t in enumerate(words):
        if is_model(t):
            # 'Note 14 Pro' and 'Note 14 Pro+' are different phones from 'Note 14'.
            end = i + 1
            while end < len(words) and words[end] in TIER_WORDS:
                end += 1
            return words[:end]
    return words  # no model number at all: the whole name has to match


def describing_words(title: str, brand: str = "") -> set:
    """The words right after the identity, up to the first number or spec:
    'Pro 6 Smart Watch' -> {'smart', 'watch'}; 'Note 14 Pro 5G Titan Black' -> {}
    (colours and specs aren't what the product is)."""
    brand_words = set(tokens(brand))
    words = [t for t in tokens(core_name(title)) if t not in FILLER and t not in brand_words]
    out = set()
    for t in words[len(identity(title, brand)):]:
        if not t.isalpha():
            break
        out.add(t)
    return out


# '4 Jars' and '3 Jars' are different SKUs of the same mixer, at different prices.
_COUNTED = re.compile(r"(\d+)\s*(?:[a-z]+\s+){0,3}(jars?|packs?)\b")


def counts(text: str) -> dict:
    out = {}
    for n, noun in _COUNTED.findall((text or "").lower()):
        out.setdefault(noun.rstrip("s"), set()).add(int(n))
    return out


def is_accessory(candidate: str, reference: str) -> bool:
    extra = set(tokens(candidate)) - set(tokens(reference))
    return bool(extra & ACCESSORY_WORDS)


_SIZED = re.compile(r"^(\d+)(?:gb|tb|ml|l|g|kg|w)$")


def bare(token: str) -> str:
    """'750w' -> '750', so a seller writing '750 Watt', '750W' or plain '750' all match.
    The memory rule still compares the full tokens, so 128GB never passes as 256GB."""
    m = _SIZED.match(token)
    return m.group(1) if m else token


def contains_run(words: list, run: list) -> bool:
    n = len(run)
    return any(words[i:i + n] == run for i in range(len(words) - n + 1))


def same_product(reference: str, candidate: str, brand: str = "", model: str = "") -> bool:
    cand_words = [t for t in tokens(candidate) if t not in FILLER]
    cand_tokens = set(cand_words)
    # A manufacturer's model code is the strongest identity there is, and it rescues
    # titles that open with marketing ("Philips India's No.1 Hair Styling Brand...").
    if model and model in cand_tokens:
        pass
    elif not contains_run([bare(t) for t in cand_words], [bare(t) for t in identity(reference, brand)]):
        # In order and side by side: 'Pro 6' is not 'Buds Air 6 Pro'.
        return False
    elif describing_words(reference, brand) and not describing_words(reference, brand) & cand_tokens:
        # 'Pro 6' is inside 'Air Buds Pro 6' too. If the reference's name goes on to
        # say what it is ('Smart Watch', 'Mixer Grinder'), the candidate has to share a word of it.
        return False
    # Against the reference's name only: a 'pro' in Amazon's feature blurb
    # ('Hustle like a pro') must not excuse a Pro model.
    tiers = set(tokens(core_name(candidate))) & TIER_WORDS
    if tiers - set(tokens(core_name(reference))):
        return False
    # 8GB/128GB and 8GB/256GB are the same name at different prices. A reference
    # that states its memory only matches listings that state the same memory.
    # A listing that states a different number of jars (or packs) is a different SKU.
    ref_counts, cand_counts = counts(reference), counts(candidate)
    for noun, nums in cand_counts.items():
        if noun in ref_counts and not (nums & ref_counts[noun]):
            return False
    ref_caps = {t for t in tokens(reference) if _CAPACITY.match(t)}
    cand_caps = {t for t in cand_tokens if _CAPACITY.match(t)}
    if ref_caps and (not cand_caps or not cand_caps <= ref_caps):
        return False
    if not brand or not set(tokens(brand)) <= cand_tokens:
        return False
    if is_accessory(candidate, reference):
        return False
    return True


def similarity(reference: str, candidate: str) -> float:
    """Jaccard overlap of the core names, used to rank candidates that all pass same_product."""
    a = set(tokens(core_name(reference))) - FILLER
    b = set(tokens(core_name(candidate))) - FILLER
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def model_token(model_number: str) -> str:
    """'BHS393/00' -> 'bhs393'. Only codes with a digit count; '2024' alone doesn't."""
    if not model_number:
        return ""
    head = re.split(r"[/\\ ]", str(model_number).strip())[0].lower()
    head = re.sub(r"[^a-z0-9]", "", head)
    has_letters = any(c.isalpha() for c in head)
    return head if len(head) >= 4 and any(c.isdigit() for c in head) and has_letters else ""


def short_query(title: str, brand: str = "", model: str = "") -> str:
    """The second try when the fuller query finds nothing: brand and model name, or
    the manufacturer's model code for a title that never names its model
    ("Philips India's No.1 Hair Styling Brand Hair Straightener")."""
    if model and model not in tokens(title):
        return f"{brand} {model}".strip()
    original = {t.lower(): t for t in re.findall(r"[A-Za-z0-9.]+", core_name(title))}
    ident = identity(title, brand)
    spell = lambda t: original.get(t) or original.get(bare(t)) or bare(t)
    return " ".join(([brand] if brand else []) + [spell(t) for t in ident])


def search_query(title: str, brand: str = "") -> str:
    """What to type into Google Shopping: brand, identity, and one describing word.

    'PHILIPS HL7756' alone finds spare parts; 'PHILIPS HL7756 Mixer' finds mixers.
    """
    ident = identity(title, brand)
    words = [t for t in tokens(core_name(title)) if t not in set(tokens(brand))]
    after = [t for t in words[len(ident):] if not is_model(t) and t not in FILLER][:1]
    # Keep the seller's own spelling: 'HL7756' not 'hl7756', and '750' not the
    # normalised '750w', which Google matches poorly.
    original = {t.lower(): t for t in re.findall(r"[A-Za-z0-9.]+", core_name(title))}
    spell = lambda t: original.get(t) or original.get(bare(t)) or bare(t)
    return " ".join(([brand] if brand else []) + [spell(t) for t in ident + after])
