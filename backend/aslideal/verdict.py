"""Compare a claimed discount with what other sellers actually charge.

The claim comes from Amazon.in: a price and a struck-through M.R.P. The
street price comes from Google Shopping: the median of what other in-stock
sellers charge for the same product. Two numbers fall out:

    claimed discount  = 1 - price / MRP
    real discount     = 1 - price / street price

When the claimed discount is large and the real one is near zero, the "% off"
is measured against a reference price that nobody is actually charging. The
wording stays at that: an M.R.P. is a legal printed maximum, not an invented
number, so the tool reports what the prices show and nothing about intent.
"""

from dataclasses import dataclass, field
from statistics import median

# Below this many other in-stock sellers there's no street price to speak of.
MIN_SELLERS = 2
# A discount is only "real" if it beats the street price by this much.
REAL_DEAL = 0.10
# Within this band either side of the street price, the price is the going rate.
SAME_PRICE = 0.05
# A claimed discount smaller than this isn't worth flagging.
BIG_CLAIM = 0.20
# A seller within this fraction of the MRP counts as charging the MRP.
AT_MRP = 0.95
# With only two other sellers, this much disagreement means there's no going rate.
SPREAD = 1.5


@dataclass
class Offer:
    seller: str
    price: float
    in_stock: bool = True
    title: str = ""
    link: str = ""
    logo: str = ""
    shipping: str = ""     # what the seller says about delivery
    total: float = 0       # price once delivery is added, when the seller quotes it


@dataclass
class Verdict:
    kind: str  # real_deal | reference_gap | going_rate | above_market | unverified
    headline: str
    price: float
    mrp: float = None
    claimed_discount: float = None
    street_price: float = None
    real_discount: float = None
    sellers_used: int = 0
    mrp_charged_by: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def rupees(x: float) -> str:
    n = int(round(x))
    s = str(n)
    if len(s) > 3:  # Indian grouping: 1,23,456
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return "₹" + s


def pct(x: float) -> str:
    return f"{round(x * 100)}%"


def is_own(seller: str) -> bool:
    """The claim is Amazon's, so Amazon's own listings can't also be the evidence."""
    return seller.lower().startswith("amazon")


def judge(price: float, mrp, offers: list) -> Verdict:
    claimed = 1 - price / mrp if mrp and mrp > price else 0.0
    others = [o for o in offers if o.in_stock and not is_own(o.seller) and o.price > 0]
    out_of_stock = [o for o in offers if not o.in_stock]

    v = Verdict(kind="unverified", headline="", price=price, mrp=mrp, claimed_discount=claimed)
    for o in out_of_stock:
        v.notes.append(f"{o.seller} lists {rupees(o.price)} but is out of stock, so it isn't counted.")

    if len(others) < MIN_SELLERS:
        found = {0: "No other in-stock seller", 1: "Only one other in-stock seller"}[len(others)]
        v.headline = f"{found} found for this exact product. That's not enough to say what it normally sells for."
        return v

    # Two sellers who disagree wildly have no midpoint worth quoting: the median
    # would sit at a price neither of them charges.
    prices = sorted(o.price for o in others)
    if len(others) == 2 and prices[1] > SPREAD * prices[0]:
        v.headline = (f"Only two other in-stock sellers, and they disagree: {rupees(prices[0])} and "
                      f"{rupees(prices[1])}. That's not a street price.")
        v.notes.append("A third seller would settle it; check again later.")
        return v

    street = median(o.price for o in others)
    real = 1 - price / street
    v.street_price = street
    v.real_discount = real
    v.sellers_used = len(others)
    if mrp:
        v.mrp_charged_by = [o.seller for o in others if o.price >= AT_MRP * mrp]

    n = f"{len(others)} other in-stock sellers"
    if real >= REAL_DEAL:
        v.kind = "real_deal"
        v.headline = f"Real saving: {pct(real)} below the {rupees(street)} that {n} charge."
    elif real <= -SAME_PRICE:
        v.kind = "above_market"
        v.headline = f"{pct(-real)} more than the {rupees(street)} that {n} charge."
        if claimed >= BIG_CLAIM:
            v.headline += f" The \"{pct(claimed)} off\" label doesn't change that."
    elif claimed >= BIG_CLAIM and not v.mrp_charged_by:
        v.kind = "reference_gap"
        v.headline = (
            f"\"{pct(claimed)} off\" is measured from {rupees(mrp)}, which none of the {n} charge. "
            f"They sell it for about {rupees(street)}, so the saving vs the market is {pct(max(real, 0))}."
        )
    else:
        v.kind = "going_rate"
        v.headline = f"The going rate: {n} charge about {rupees(street)}."
    return v
