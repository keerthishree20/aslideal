"""Amazon claim -> Google Shopping product -> every store's price -> verdict.

A check costs at most five searches: the Amazon.in product page, Google
Shopping, Google web search, and up to two Immersive Product pages.
"""

import re
from urllib.parse import urlparse
from collections import Counter
from dataclasses import asdict

from . import history, match, signals
from .serp import DemoMiss, Serp, SerpError
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
    """The claim: one exact Amazon.in listing, its price, M.R.P. and fine print.

    Returns the listing and the raw response, which also carries review insights.
    """
    data = serp.search(engine="amazon_product", asin=asin, amazon_domain="amazon.in")
    pr = data.get("product_results")
    if not pr or not pr.get("extracted_price"):
        return None, data
    listing = _listing(pr)
    # The page's brand field reads 'Visit the boAt Store'; the spec table has the plain name.
    listing["brand"] = ((data.get("item_specifications") or {}).get("brand")
                        or (data.get("product_details") or {}).get("brand_name")
                        or re.sub(r"^Visit the (.*) Store$", r"\1", listing["brand"]))
    listing["in_stock"] = "in stock" in (pr.get("stock") or "").lower()
    # The fine print the dark-pattern checks read.
    for field in ("badges", "bank_offers", "promotions", "coupons", "delivery"):
        listing[field] = pr.get(field) or []
    details = data.get("product_details") or {}
    specs = data.get("item_specifications") or {}
    listing["model"] = match.model_token(details.get("model_number") or specs.get("model_number") or "")
    return listing, data


# Places that quote a price but aren't shops selling this product new.
NOT_A_SHOP = ("facebook.", "instagram.", "youtube.", "pinterest.", "twitter.", "x.com",
              "reddit.", "quora.", "olx.", "linkedin.")


def seller_from(source: str, link: str, title: str) -> str:
    """Google Lens sometimes gives the page title where the shop's name belongs.
    The link's hostname is the honest answer: 'flipkart.com' -> 'Flipkart'."""
    looks_like_title = not source or len(source) > 34 or source[:20].lower() == (title or "")[:20].lower()
    if not looks_like_title:
        return source
    host = (urlparse(link).hostname or "").replace("www.", "")
    if not host:
        return source or "?"
    label = host.split(".")[0]
    return label.title() if label.isalpha() else host


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
    listing, amazon_raw = amazon_product(serp, asin)
    if listing is None:
        # No price usually means the listing is dead, but its title still names the
        # product, so offer the listings that do have a price.
        dead = amazon_raw.get("product_results") or {}
        title, stock = dead.get("title", ""), (dead.get("stock") or "").strip().rstrip(".")
        why = f"This Amazon.in listing has no price{f' — it says \'{stock}\'' if stock else ''}."
        if not title:
            return {"error": f"{why} Nothing else to go on for {asin}."}
        brand = re.sub(r"^Visit the (.*) Store$", r"\1", dead.get("brand", "") or "")
        try:
            suggestions = amazon_search(serp, match.search_query(title, brand))
        except (DemoMiss, SerpError):
            suggestions = []
        return {"error": why, "unavailable": True, "title": title,
                "suggestions": [s for s in suggestions if s["price"]][:6]}
    if not listing["brand"]:
        return {"error": "This listing names no brand, so other sellers' listings can't be matched to it safely."}

    title, brand, model = listing["title"], listing["brand"], listing.get("model", "")
    shopping_q = match.search_query(title, brand)
    shopping = serp.search(engine="google_shopping", q=shopping_q, gl="in", hl="en", location="India")

    result = {"listing": listing, "shopping_query": shopping_q, "matched_product": None,
              "offers": [], "rejected": [], "verdict": None, "trail": []}
    # What each SerpApi call contributed, shown in the report as "How we checked".
    trail = result["trail"]
    mrp_text = f", M.R.P. ₹{listing['mrp']:,.0f}" if listing["mrp"] else ", no M.R.P. shown"
    trail.append({"engine": "amazon_product", "query": asin,
                  "found": f"Amazon.in listing at ₹{listing['price']:,.0f}{mrp_text}"})
    offers = {}

    def add(o: Offer):
        reason = offer_problem(o, listing["mrp"], listing["price"]) or (
            # Store titles are checked too: one grouped product can hide a different model.
            None if match.same_product(title, o.title, brand, model) else "different product or accessory")
        if reason:
            result["rejected"].append({**asdict(o), "reason": reason})
            return
        # One seller counts once, at its best in-stock price, however many listings it has.
        key = o.seller.lower()
        if key not in offers or (o.in_stock, -o.price) > (offers[key].in_stock, -offers[key].price):
            offers[key] = o

    # Each Google Shopping result is one seller's price for one listing.
    candidates = []

    def scan_shopping(data, query):
        found = []
        for r in data.get("shopping_results", []):
            if not r.get("source") or not r.get("extracted_price"):
                continue  # a grouped "₹1,300+" result names no seller and no single price
            before = len(result["rejected"])
            add(Offer(seller=r["source"], price=r["extracted_price"], title=r.get("title", ""),
                      link=r.get("product_link", ""), logo=r.get("source_icon", "")))
            if len(result["rejected"]) == before and r.get("immersive_product_page_token"):
                found.append(r)
        trail.append({"engine": "google_shopping", "query": query,
                      "found": plural(len(data.get("shopping_results", [])), "shopping result")})
        candidates.extend(found)

    def open_products(budget):
        """Opening a product lists every store that carries it. Amazon's own listing
        only ever lists Amazon, so other sellers' listings are opened first."""
        candidates.sort(key=lambda r: (not is_own(r["source"]), bool(r.get("multiple_sources")),
                                       match.similarity(title, r["title"])), reverse=True)
        opened = 0
        while candidates and opened < budget:
            best = candidates.pop(0)
            opened += 1
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
            for st in pr.get("stores", []):
                sticker = st.get("extracted_price") or st.get("extracted_total") or 0
                add(Offer(seller=st.get("name", "?"), price=sticker,
                          in_stock=_in_stock(st), title=st.get("title") or pr.get("title") or best["title"],
                          link=st.get("link", ""), logo=st.get("logo", ""),
                          shipping=st.get("shipping", ""), total=st.get("extracted_total") or sticker))
            trail.append({"engine": "google_immersive_product", "query": best["title"][:80],
                          "found": plural(len(pr.get("stores", [])), "store") + " selling it"})
            if enough():
                break
        return opened

    def enough():
        return len(_others(offers.values())) >= MIN_SELLERS

    scan_shopping(shopping, shopping_q)

    # Google web search surfaces other products and retailer pages (Flipkart,
    # Croma, the brand's own store) that Google Shopping often leaves out.
    web = serp.search(engine="google", q=f"{shopping_q} price", gl="in", hl="en", location="India", num="20")
    for r in web.get("immersive_products", []):
        if not r.get("source") or not r.get("extracted_price"):
            continue
        before = len(result["rejected"])
        add(Offer(seller=r["source"], price=r["extracted_price"], title=r.get("title", ""), link=r.get("link", ""),
                  logo=r.get("source_logo", "")))
        if len(result["rejected"]) == before and r.get("immersive_product_page_token"):
            candidates.append(r)
    priced_pages = 0
    for r in web.get("organic_results", []):
        snippet = r.get("rich_snippet") or {}
        # Retailer pages carry the price in either half of the rich snippet.
        for half in (snippet.get("top") or {}, snippet.get("bottom") or {}):
            price = (half.get("detected_extensions") or {}).get("price")  # a range ('₹18,080 to ₹28,993') is skipped
            if not (r.get("source") and price):
                continue
            priced_pages += 1
            in_stock = not any("out of stock" in e.lower() for e in half.get("extensions", []))
            add(Offer(seller=r["source"], price=price, in_stock=in_stock, title=r.get("title", ""), link=r.get("link", ""),
                      logo=r.get("favicon", "")))
            break
    trail.append({"engine": "google", "query": f"{shopping_q} price",
                  "found": f"{plural(len(web.get('immersive_products', [])), 'product listing')}, "
                           f"{plural(priced_pages, 'retailer page')} with a price"})

    used = open_products(MAX_PRODUCT_PAGES)

    # Still nothing? The precise query may be too narrow ('Prestige PIC 20 Watts'
    # finds gas stoves), so try the bare brand and model once.
    # Still thin? Google Lens sees the product in the photo and often quotes the
    # sellers it recognises, which is a different index from Shopping's.
    if not enough() and listing.get("thumbnail"):
        try:
            lens = serp.search(engine="google_lens", url=listing["thumbnail"], country="in", hl="en")
            seen = 0
            for m in lens.get("visual_matches") or []:
                price = m.get("price") or {}
                link = m.get("link", "")
                if price.get("currency") != "₹" or not price.get("extracted_value"):
                    continue   # Lens quotes foreign listings too; rupees only
                if any(h in (urlparse(link).hostname or "") for h in NOT_A_SHOP):
                    continue   # a social post quoting a price is not a seller
                seen += 1
                add(Offer(seller=seller_from(m.get("source", ""), link, m.get("title", "")),
                          price=price["extracted_value"], title=m.get("title", ""),
                          link=link, logo=m.get("source_icon", "")))
            trail.append({"engine": "google_lens", "query": "the listing's own photo",
                          "found": plural(seen, "seller price") + " recognised in the image"})
        except (DemoMiss, SerpError):
            pass   # an extra look, never required

    short_q = match.short_query(title, brand, model)
    if not enough() and short_q.lower() != shopping_q.lower():
        try:
            scan_shopping(serp.search(engine="google_shopping", q=short_q, gl="in", hl="en", location="India"), short_q)
            open_products(max(1, MAX_PRODUCT_PAGES - used))
        except DemoMiss:
            # Demo mode only has what was recorded; a missing second try isn't fatal.
            pass

    final = sorted(offers.values(), key=lambda o: o.price)
    result["offers"] = [asdict(o) for o in final]
    reasons = Counter(r["reason"] for r in result["rejected"])
    trail.append({"engine": "match", "query": " ".join(match.identity(title, brand)),
                  "found": f"{plural(len(_others(final)), 'other in-stock seller')} kept, "
                           f"{plural(len(result['rejected']), 'listing')} left out",
                  "reasons": dict(reasons.most_common())})
    result["verdict"] = asdict(judge(listing["price"], listing["mrp"], final))
    result["signals"] = signals.report(listing, result["verdict"], result["offers"],
                                       amazon_raw.get("reviews_information"))
    # Only live checks are worth recording; a replay would just repeat what's there.
    if not serp.demo:
        result["history"] = history.record(listing, result["verdict"])
    else:
        result["history"] = history.load().get(asin, [])
    if not final:
        result["verdict"]["headline"] = "Couldn't find this exact product sold anywhere else, so there's nothing to compare against."
    return result


def scan(serp: Serp, query: str, limit: int = 5) -> dict:
    """Check a whole shelf: the advertised deals Amazon.in shows for one search.

    Answers the question a single product can't: of the discounts on offer right
    now, how many are measured from a price no other seller charges?
    """
    listings = [i for i in amazon_search(serp, query) if i["mrp"] and not i["sponsored"]]
    rows, counts = [], Counter()
    for item in listings[:limit]:
        try:
            r = check(serp, item["asin"])
        except (DemoMiss, SerpError) as e:
            counts["couldn't check"] += 1
            rows.append({**item, "kind": "error", "headline": str(e)})
            continue
        if "error" in r:
            counts["couldn't check"] += 1
            rows.append({**item, "kind": "error", "headline": r["error"]})
            continue
        v = r["verdict"]
        counts[v["kind"]] += 1
        rows.append({**item, "kind": v["kind"], "headline": v["headline"], "street_price": v["street_price"],
                     "real_discount": v["real_discount"], "sellers": v["sellers_used"],
                     "flagged": r["signals"]["flagged"]})
    judged = sum(n for k, n in counts.items() if k not in ("unverified", "error", "couldn't check"))
    gap = counts.get("reference_gap", 0)
    return {
        "query": query,
        "rows": rows,
        "counts": dict(counts),
        "headline": (f"{gap} of the {plural(judged, 'advertised deal')} we could judge "
                     f"{'is' if gap == 1 else 'are'} measured from a price no other seller charges." if judged else
                     "None of these listings had enough other sellers to judge."),
    }


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _others(offers) -> list:
    return [o for o in offers if o.in_stock and not is_own(o.seller)]
