"""Dark-pattern signals, read off the same data the verdict uses.

India's CCPA named thirteen dark patterns in its 2023 guidelines. Three of them
leave traces in price data, and this module reports only those three, plus what
buyers say about the product. Every signal says what was seen, never what anyone
intended.

    inflated reference  the "% off" is measured from a price no seller charges
    false urgency       a deal label that never says when the deal ends
    drip pricing        the cheapest sticker price isn't cheapest after delivery
    conditional saving  the advertised saving needs a particular card or coupon
"""

import re

from .verdict import is_own, rupees

URGENCY = re.compile(r"limited time|deal of the day|ends (in|soon)|hurry|last chance|today only|lightning deal", re.I)
EXPIRY = re.compile(r"\b(ends|until|till|expires)\b.{0,24}\d|\d+\s*(hours?|hrs?|days?|minutes?)\s*(left|remaining)", re.I)


def _texts(listing: dict) -> list:
    out = list(listing.get("badges") or [])
    for p in listing.get("promotions") or []:
        out.append(p.get("text", ""))
    for c in listing.get("coupons") or []:
        out.append(c.get("text", ""))
    out.append(listing.get("deal_text") or "")
    return [t for t in out if t]


def inflated_reference(listing: dict, verdict: dict) -> dict:
    """The claim measured against what sellers actually charge."""
    claimed, mrp = verdict.get("claimed_discount") or 0, listing.get("mrp")
    if not mrp or claimed < 0.2:
        return {"flag": False, "detail": "No large discount claimed." if not claimed else
                f"Claims {round(claimed * 100)}% off, which is modest."}
    if verdict.get("street_price") is None:
        return {"flag": None, "detail": "Not enough other sellers to judge the reference price."}
    if verdict.get("mrp_charged_by"):
        return {"flag": False,
                "detail": f"{', '.join(verdict['mrp_charged_by'])} really does charge about {rupees(mrp)}."}
    return {"flag": True,
            "detail": f"The {round(claimed * 100)}% is measured from {rupees(mrp)}; no in-stock seller found charges that. "
                      f"They charge about {rupees(verdict['street_price'])}."}


def false_urgency(listing: dict) -> dict:
    """A deal label with no end time is the CCPA's 'false urgency'."""
    labels = [t for t in _texts(listing) if URGENCY.search(t)]
    if not labels:
        return {"flag": False, "detail": "No countdown or limited-time label on this listing."}
    dated = [t for t in labels if EXPIRY.search(t)]
    if dated:
        return {"flag": False, "detail": f"Time-limited, and it says when it ends: \"{dated[0]}\"."}
    return {"flag": True, "detail": f"\"{labels[0]}\" — the listing never says when it ends."}


def drip_pricing(offers: list) -> dict:
    """Delivery charges can change who is actually cheapest."""
    priced = [o for o in offers if o.get("in_stock") and o.get("total")]
    if len(priced) < 2:
        return {"flag": None, "detail": "Not enough sellers quote a delivery charge to compare."}
    by_sticker = min(priced, key=lambda o: o["price"])
    by_total = min(priced, key=lambda o: o["total"])
    if by_sticker["seller"] == by_total["seller"]:
        return {"flag": False, "detail": f"{by_sticker['seller']} is cheapest either way, at {rupees(by_total['total'])} delivered."}
    return {"flag": True,
            "detail": f"{by_sticker['seller']} looks cheapest at {rupees(by_sticker['price'])}, but delivered it's "
                      f"{rupees(by_sticker['total'])}. {by_total['seller']} costs {rupees(by_total['total'])} delivered."}


def conditional_savings(listing: dict) -> dict:
    """Bank and coupon offers are real money, but only for some buyers."""
    offers = []
    for o in listing.get("bank_offers") or []:
        if o.get("extracted_savings"):
            offers.append((o["extracted_savings"], f"{o.get('title', 'Bank offer')}: {o.get('content', '')[:90]}"))
    for c in listing.get("promotions") or []:
        if c.get("extracted_discount"):
            offers.append((c["extracted_discount"], c.get("text", "coupon")))
    if not offers:
        return {"flag": False, "detail": "No card or coupon offers attached to this listing."}
    offers.sort(reverse=True)
    best, headline = offers[0]
    return {"flag": True, "best_saving": best,
            "detail": f"Up to {rupees(best)} more off, but only for some buyers — {headline}",
            "all": [text for _, text in offers[:4]]}


def buyer_complaints(reviews: dict, limit: int = 3) -> list:
    """What buyers keep raising, worst first: a cheap product can be cheap for a reason."""
    summary = (reviews or {}).get("summary") or {}
    out = []
    for i in summary.get("insights") or []:
        m = i.get("mentions") or {}
        total, negative = m.get("total") or 0, m.get("negative") or 0
        if not total or i.get("sentiment") == "positive":
            continue
        out.append({"topic": i.get("title", "?"), "share": round(negative / total, 2),
                    "negative": negative, "total": total, "sentiment": i.get("sentiment")})
    out.sort(key=lambda r: r["share"], reverse=True)
    return out[:limit]


def report(listing: dict, verdict: dict, offers: list, reviews: dict = None) -> dict:
    """The whole card: three CCPA-shaped signals, the offers fine print, and buyer complaints."""
    checks = {
        "inflated_reference": inflated_reference(listing, verdict),
        "false_urgency": false_urgency(listing),
        "drip_pricing": drip_pricing([o for o in offers if not is_own(o.get("seller", ""))]),
        "conditional_savings": conditional_savings(listing),
    }
    return {
        "checks": checks,
        "flagged": sum(1 for c in checks.values() if c["flag"]),
        "complaints": buyer_complaints(reviews),
    }
