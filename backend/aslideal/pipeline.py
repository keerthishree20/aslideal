"""Amazon claim -> Google Shopping product -> every store's price -> verdict.

A check costs at most five searches: the Amazon.in product page, Google
Shopping, Google web search, and up to two Immersive Product pages.
"""

import re
from urllib.parse import urlparse
from dataclasses import asdict

from . import match
from .serp import Serp
from .verdict import MIN_SELLERS, Offer, is_own, judge

# Each product page is one search; stop after this many even if sellers are thin.
MAX_PRODUCT_PAGES = 2
ASIN_IN_URL = re.compile(r"/(?:dp|gp/product|product)/([A-Z0-9]{10})")
ASIN = re.compile(r"^[A-Z0-9]{10}$")
FINANCE_WORDS = {"emi", "finance", "loan"}
# .in storefronts that import foreign stock at foreign prices.
IMPORT_RESELLERS = ("desertcart", "ubuy")
# Delivery charges can push a total slightly past the M.R.P.; more than this can't be the same item.
ABOVE_MRP = 1.10
# A new item at under 40% of Amazon's price is a spare part, a used unit or a
# mislabelled listing, not a discount.
TOO_CHEAP = 0.40
# Google converts foreign listings to rupees; their prices say nothing about the Indian market.
FOREIGN_TLD = re.compile(r"\.(?:sa|ae|uk|us|ca|au|sg|pk|bd|lk|np|qa|kw|om|bh|my|de)$")


def parse_asin(text: str):
    """The ASIN in an amazon.in link, or the text itself if it is one."""
    text = text.strip()
    m = ASIN_IN_URL.search(text)
    if m:
        return m.group(1)
    return text.upper() if ASIN.match(text.upper()) else None


def _listing(r: dict) -> dict:
    price, mrp = r.get("extracted_price"), r.get("extracted_old_price")
    return {
        "asin": r["asin"],
        "title": r.get("title", ""),
        "brand": r.get("brand", ""),
        "price": price,
        "mrp": mrp,
        "claimed_discount": round(1 - price / mrp, 3) if price and mrp and mrp > price else 0,
        "thumbnail": r.get("thumbnail"),
        "link": r.get("link_clean") or r.get("link"),
        "rating": r.get("rating"),
        "reviews": r.get("reviews"),
        "sponsored": bool(r.get("sponsored")),
    }


def amazon_search(serp: Serp, query: str) -> list:
    """Amazon.in results for a product name, for the user to pick the exact product from."""
    data = serp.search(engine="amazon", k=query.strip(), amazon_domain="amazon.in")
    return [_listing(r) for r in data.get("organic_results", []) if r.get("asin") and r.get("extracted_price")]


def amazon_product(serp: Serp, asin: str):
    """The claim: one exact Amazon.in listing's price and M.R.P."""
    data = serp.search(engine="amazon_product", asin=asin, amazon_domain="amazon.in")
    pr = data.get("product_results")
    if not pr or not pr.get("extracted_price"):
        return None
    listing = _listing(pr)
    # The page's brand field reads 'Visit the boAt Store'; the spec table has the plain name.
    listing["brand"] = ((data.get("item_specifications") or {}).get("brand")
                        or (data.get("product_details") or {}).get("brand_name")
                        or re.sub(r"^Visit the (.*) Store$", r"\1", listing["brand"]))
    listing["in_stock"] = "in stock" in (pr.get("stock") or "").lower()
    return listing


def offer_problem(o: Offer, mrp=None, price=None):
    """Why an offer can't stand for what the product sells for in India, if it can't."""
    name = o.seller.lower()
    if any(r in name for r in IMPORT_RESELLERS):
        return "import reseller"
    # The M.R.P. is the printed maximum retail price, so a listing well above it
    # is an import or a different product, not the going rate.
    if mrp and o.price > ABOVE_MRP * mrp:
        return "priced above the M.R.P."
    if price and o.price < TOO_CHEAP * price:
        return "too cheap to be the same new item"
    if any(w in name.split() for w in FINANCE_WORDS) or "snapmint" in name:
        return "financing listing, not a retail price"
    host = urlparse(o.link).hostname or ""
    for label in (name, host):
        if FOREIGN_TLD.search(label):
            return "ships from outside India"
    return None


def _in_stock(store: dict) -> bool:
    details = " ".join(store.get("details_and_offers") or []).lower()
    return "out of stock" not in details


def check(serp: Serp, asin: str) -> dict:
    listing = amazon_product(serp, asin)
    if listing is None:
        return {"error": f"Amazon.in has no price for {asin}. The listing may be unavailable."}
    if not listing["brand"]:
        return {"error": "This listing names no brand, so other sellers' listings can't be matched to it safely."}

    title, brand = listing["title"], listing["brand"]
    shopping_q = match.search_query(title, brand)
    shopping = serp.search(engine="google_shopping", q=shopping_q, gl="in", hl="en", location="India")

    result = {"listing": listing, "shopping_query": shopping_q, "matched_product": None,
              "offers": [], "rejected": [], "verdict": None}
    offers = {}

    def add(o: Offer):
        reason = offer_problem(o, listing["mrp"], listing["price"]) or (
            # Store titles are checked too: one grouped product can hide a different model.
            None if match.same_product(title, o.title, brand) else "different product or accessory")
        if reason:
            result["rejected"].append({**asdict(o), "reason": reason})
            return
        # One seller counts once, at its best in-stock price, however many listings it has.
        key = o.seller.lower()
        if key not in offers or (o.in_stock, -o.price) > (offers[key].in_stock, -offers[key].price):
            offers[key] = o

    # Each Google Shopping result is one seller's price for one listing.
    candidates = []
    for r in shopping.get("shopping_results", []):
        if not r.get("source") or not r.get("extracted_price"):
            continue  # a grouped "₹1,300+" result names no seller and no single price
        before = len(result["rejected"])
        add(Offer(seller=r["source"], price=r["extracted_price"], title=r.get("title", ""),
                  link=r.get("product_link", "")))
        if len(result["rejected"]) == before and r.get("immersive_product_page_token"):
            candidates.append(r)

    # Google web search surfaces other products and retailer pages (Flipkart,
    # Croma, the brand's own store) that Google Shopping often leaves out.
    web = serp.search(engine="google", q=f"{shopping_q} price", gl="in", hl="en", location="India", num="20")
    for r in web.get("immersive_products", []):
        if not r.get("source") or not r.get("extracted_price"):
            continue
        before = len(result["rejected"])
        add(Offer(seller=r["source"], price=r["extracted_price"], title=r.get("title", ""), link=r.get("link", "")))
        if len(result["rejected"]) == before and r.get("immersive_product_page_token"):
            candidates.append(r)
    for r in web.get("organic_results", []):
        top = (r.get("rich_snippet") or {}).get("top") or {}
        price = (top.get("detected_extensions") or {}).get("price")  # a range ('₹18,080 to ₹28,993') is skipped
        if r.get("source") and price:
            in_stock = not any("out of stock" in e.lower() for e in top.get("extensions", []))
            add(Offer(seller=r["source"], price=price, in_stock=in_stock, title=r.get("title", ""), link=r.get("link", "")))

    # Opening a product lists every store that carries it. Amazon's own listing
    # only ever lists Amazon, so other sellers' listings are opened first.
    candidates.sort(key=lambda r: (not is_own(r["source"]), bool(r.get("multiple_sources")),
                                   match.similarity(title, r["title"])), reverse=True)
    for best in candidates[:MAX_PRODUCT_PAGES]:
        product = serp.search(engine="google_immersive_product",
                              page_token=best["immersive_product_page_token"], more_stores="true")
        pr = product.get("product_results", {})
        if result["matched_product"] is None:
            result["matched_product"] = {
                "title": pr.get("title") or best["title"],
                "price_range": pr.get("price_range"),
                "rating": pr.get("rating"),
                "reviews": pr.get("reviews"),
                "thumbnail": (pr.get("thumbnails") or [best.get("thumbnail")])[0],
            }
        for s in pr.get("stores", []):
            add(Offer(seller=s.get("name", "?"), price=s.get("extracted_total") or s.get("extracted_price") or 0,
                      in_stock=_in_stock(s), title=s.get("title") or pr.get("title") or best["title"],
                      link=s.get("link", "")))
        if len(_others(offers.values())) >= MIN_SELLERS:
            break

    final = sorted(offers.values(), key=lambda o: o.price)
    result["offers"] = [asdict(o) for o in final]
    result["verdict"] = asdict(judge(listing["price"], listing["mrp"], final))
    if not final:
        result["verdict"]["headline"] = "Couldn't find this exact product sold anywhere else, so there's nothing to compare against."
    return result


def _others(offers) -> list:
    return [o for o in offers if o.in_stock and not is_own(o.seller)]
