"""HTTP API and the single-page UI.

    uvicorn aslideal.api:app --port 8000

Without a SERPAPI_KEY (or with DEMO_MODE=1) every answer comes from the
recorded responses in fixtures/cache, so the app works on a fresh clone.
"""

import csv
import io
import json
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import history
from . import pipeline
from .pipeline import amazon_search, check, parse_asin
from .serp import ROOT, DemoMiss, Serp, SerpError

load_dotenv(ROOT / ".env")
WEB = Path(__file__).resolve().parent / "web"

app = FastAPI(title="AsliDeal")
serp = Serp()


def _answer(fn, *args):
    try:
        return fn(serp, *args)
    except DemoMiss as e:
        raise HTTPException(404, str(e))
    except SerpError as e:
        raise HTTPException(502, f"SerpApi: {e}")


def recorded_listings() -> list:
    """Amazon.in listings already in the cache: the products that can be checked for free."""
    samples = []
    for p in sorted(serp.cache_dir.glob("*.json")):
        entry = json.loads(p.read_text())
        if entry["params"].get("engine") != "amazon_product":
            continue
        pr = entry["response"].get("product_results") or {}
        if pr.get("extracted_price"):
            samples.append({"asin": pr["asin"], "title": pr.get("title", ""), "thumbnail": pr.get("thumbnail")})
    return samples


@app.get("/api/status")
def status():
    """Demo or live, searches left, and the products the recorded data can answer."""
    try:
        quota = serp.quota()
    except Exception:  # the page still works if the account endpoint is down
        quota = None
    return {"demo": serp.demo, "quota": quota, "samples": recorded_listings()}


_gallery_memo = {"key": None, "cards": None}


def _cache_signature():
    """Changes whenever a response is added to or rewritten in the cache."""
    files = list(serp.cache_dir.glob("*.json"))
    return len(files), max((f.stat().st_mtime_ns for f in files), default=0)


@app.get("/api/gallery")
def gallery():
    """Verdicts for every product in the recorded data. Always replayed, never live,
    so opening the home page doesn't spend searches.

    Replaying every product on every page load grows with the cache, so the result
    is kept until the recorded data changes."""
    key = _cache_signature()
    if _gallery_memo["key"] == key:
        return _gallery_memo["cards"]
    cards = _build_gallery()
    _gallery_memo.update(key=key, cards=cards)
    return cards


def _build_gallery():
    recorded = Serp(api_key="", cache_dir=serp.cache_dir, demo=True)
    cards = []
    for sample in recorded_listings():
        try:
            r = check(recorded, sample["asin"])
        except DemoMiss:
            continue
        if "error" in r:
            continue
        v = r["verdict"]
        cards.append({
            "asin": sample["asin"], "title": r["listing"]["title"], "brand": r["listing"]["brand"],
            "thumbnail": r["listing"]["thumbnail"], "kind": v["kind"], "price": v["price"], "mrp": v["mrp"],
            "claimed_discount": v["claimed_discount"], "real_discount": v["real_discount"],
            "street_price": v["street_price"], "sellers": v["sellers_used"],
            # every listing looked at for this product, kept or not
            "screened": len(r["offers"]) + len(r["rejected"]),
            "left_out": len(r["rejected"]),
        })
    order = ["reference_gap", "above_market", "real_deal", "going_rate", "unverified"]
    cards.sort(key=lambda c: order.index(c["kind"]))
    return cards


@app.get("/api/history/{asin}")
def product_history(asin: str):
    """Every live check ever run on this product, and what moved since the first one."""
    days = history.load().get(parse_asin(asin) or asin.upper(), [])
    return {"days": days, "changes": history.changes(days)}


@app.get("/api/scan")
def scan_shelf(q: str, limit: int = 5):
    """Check several advertised deals at once. Costs up to seven searches per product."""
    limit = max(1, min(limit, 10))
    return _answer(pipeline.scan, q, limit)


SCAN_COLUMNS = ["asin", "title", "brand", "price", "mrp", "claimed_discount", "street_price",
                "real_discount", "sellers", "kind", "flagged", "headline", "link"]


@app.get("/api/scan.csv")
def scan_csv(q: str, limit: int = 5):
    """The same shelf scan as a spreadsheet, for anyone comparing deals over time."""
    result = scan_shelf(q, limit)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=SCAN_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in result["rows"]:
        writer.writerow({k: row.get(k, "") for k in SCAN_COLUMNS})
    slug = re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")[:40] or "scan"
    return Response(out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="aslideal-{slug}.csv"'})


@app.get("/api/lens")
def lens(url: str):
    """Identify a product from a photo, then look it up on Amazon.in."""
    try:
        data = serp.search(engine="google_lens", url=url, country="in", hl="en")
    except DemoMiss as e:
        raise HTTPException(404, str(e))
    except SerpError as e:
        raise HTTPException(502, f"SerpApi: {e}")
    matches = [m for m in (data.get("visual_matches") or []) if m.get("title")]
    if not matches:
        raise HTTPException(422, "Google Lens didn't recognise a product in that image.")
    best = matches[0]["title"]
    # Lens often quotes a price with the match, which is a free look at the market.
    sightings = [{"source": m.get("source", "?"), "title": m["title"],
                  "price": (m.get("price") or {}).get("extracted_value")}
                 for m in matches if (m.get("price") or {}).get("extracted_value")][:6]
    return {"recognised": best, "seen_at": sightings, "results": _answer(amazon_search, best)}


@app.get("/api/search")
def search(q: str):
    """A product name returns Amazon.in listings to pick from; a link or ASIN goes straight to a check."""
    q = q.strip()
    if not q:
        raise HTTPException(400, "Type a product name or paste an amazon.in link.")
    asin = parse_asin(q)
    if asin:
        return {"asin": asin, "results": []}
    if "amazon." in q or "amzn." in q:
        raise HTTPException(400, "Couldn't find a product ID in that link. Open the product page and copy its address.")
    return {"asin": None, "results": _answer(amazon_search, q)}


@app.get("/api/check/{asin}")
def check_asin(asin: str, replay: bool = False):
    """A full check. replay=1 answers only from recorded data, so the home page's
    example console never spends a search or writes a history reading."""
    asin = parse_asin(asin)
    if not asin:
        raise HTTPException(400, "That isn't an Amazon product ID.")
    if replay:
        recorded = Serp(api_key="", cache_dir=serp.cache_dir, demo=True)
        try:
            result = check(recorded, asin)
        except DemoMiss as e:
            raise HTTPException(404, str(e))
    else:
        result = _answer(check, asin)
    if result.get("unavailable"):
        return result          # dead listing, but we can point at live ones
    if "error" in result:
        raise HTTPException(422, result["error"])
    return result


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
