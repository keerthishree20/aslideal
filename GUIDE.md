# AsliDeal — Complete Project Guide

A complete guide from zero to a working "is this Amazon.in discount real?" checker built on SerpApi.
Covers every feature, every design decision and the reason behind it, with the real code. It is
self-contained: you can paste it into any AI chat and ask questions about the project without sharing
the repository.

**Repository:** https://github.com/keerthishree20/aslideal
**All projects:** https://github.com/keerthishree20

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack & Why](#2-tech-stack--why)
3. [Project Setup from Scratch](#3-project-setup-from-scratch)
4. [Project Structure](#4-project-structure)
5. [Architecture](#5-architecture)
6. [The SerpApi Client, Cache & Demo Mode](#6-the-serpapi-client-cache--demo-mode)
7. [Step 1: The Claim (Amazon.in)](#7-step-1-the-claim-amazonin)
8. [Step 2: Finding Other Sellers](#8-step-2-finding-other-sellers)
9. [Step 3: Same-Product Matching](#9-step-3-same-product-matching)
10. [Step 4: Offer Filters](#10-step-4-offer-filters)
11. [Step 5: Street Price & Verdict](#11-step-5-street-price--verdict)
12. [The Trail: "How We Checked"](#12-the-trail-how-we-checked)
13. [API](#13-api)
14. [Frontend: Home Page](#14-frontend-home-page)
15. [Frontend: The Report](#15-frontend-the-report)
16. [Configuration](#16-configuration)
17. [Testing](#17-testing)
18. [Evaluation (Honest Numbers)](#18-evaluation-honest-numbers)
19. [Limitations & Wording Rules](#19-limitations--wording-rules)
20. [Troubleshooting](#20-troubleshooting)
21. [Complete Feature Summary](#21-complete-feature-summary)

---

## 1. Project Overview

Amazon.in shows a struck-through **M.R.P.** and a big "% off" on almost every product. The M.R.P. is
the legal maximum printed on the box, not necessarily a price anyone charges. **AsliDeal** ("asli" means
"real" in Hindi) compares the Amazon price with what **other Indian stores charge for the same product
today**, and gives a verdict with all the evidence.

- Paste an amazon.in link, or search a product name and pick the exact listing.
- Get a verdict (Real saving / Discount from a price nobody charges / Normal price / Cheaper elsewhere /
  Not enough data), two gauges, a per-seller price chart, the steps taken, and every listing left out
  with its reason.
- **Every piece of data comes from SerpApi.** There is no other source.
- Works **without a key** in demo mode, on recorded responses.

**Status:** built for a SerpApi hackathon (due 2026-10-05). 29 tests pass. The latest commits are local
and not pushed yet.

---

## 2. Tech Stack & Why

| Technology | Role | Why We Chose It |
|---|---|---|
| **SerpApi** | All data | one API for Amazon.in, Google Shopping, Google search and Google product pages (it's also the hackathon's requirement) |
| **FastAPI** | Backend + serves the page | small, typed, one process |
| **httpx** | HTTP client | timeouts, and a mockable transport for tests |
| **Python stdlib** (`statistics.median`, `re`, `hashlib`) | Matching, cache keys, street price | no heavy dependencies |
| **Vanilla JS + CSS** | Frontend | one page; no build step |
| **pytest** | Tests | 29 tests on recorded responses, no network |
| **`run.sh`** | One-command start | finds Python ≥ 3.9, creates the venv, installs, serves |

### Why the median for the street price?
One seller with a silly price (very high or very low) would pull an average. The median is what a
typical other store charges.

---

## 3. Project Setup from Scratch

```bash
git clone https://github.com/keerthishree20/aslideal.git
cd aslideal
./run.sh                       # http://localhost:8000
```

`run.sh` tries `python3.13` down to `python3.9`, then `python3`, creates `backend/.venv`, installs
`backend/requirements.txt` and starts uvicorn. `PORT` changes the port (default 8000).

**Demo mode (no key):** click a product in the "Checked products" gallery, a "Try" chip, or "Open the
full report" on the console card. Nothing is fetched.

**Live mode:**
```bash
cp .env.example .env           # put your key after SERPAPI_KEY=
./run.sh
```
Get a free key at https://serpapi.com (250 searches a month). `.env` is git-ignored. Never commit it.

---

## 4. Project Structure

```
run.sh                       one-command start
.env.example                 SERPAPI_KEY, DEMO_MODE
backend/
  aslideal/
    serp.py                  Serp client: disk cache, DemoMiss, quota()
    pipeline.py              parse_asin, amazon_search, amazon_product, offer_problem, check (+ trail)
    match.py                 tokens, core_name, identity, describing_words, same_product, similarity, search_query
    verdict.py               Offer, Verdict, judge, is_own, rupees, pct
    api.py                   FastAPI app, .env loading, 4 routes + the page
    web/index.html  app.js  style.css
  scripts/evaluate.py        fixed evaluation set
  tests/test_match.py  test_verdict.py  test_pipeline.py
  pytest.ini  requirements.txt  requirements-dev.txt
fixtures/
  cache/*.json               every recorded SerpApi response (= demo data)
  evaluation.json            evaluation results
docs/                        screenshots (home, reports)
```

---

## 5. Architecture

```
Browser  (web/index.html, app.js, style.css)
   │  GET /api/status · /api/gallery · /api/search?q= · /api/check/{asin}
   ▼
FastAPI  api.py  (also serves the page)
   │
pipeline.check(asin)
   ├─ amazon_product ─────────────► the claim: price, M.R.P., brand, stock
   ├─ google_shopping (gl=in) ────┐
   ├─ google (gl=in) ─────────────┼─► candidate offers ─► offer_problem() + same_product()
   └─ google_immersive_product ───┘         │                   (match.py)
                                            ├─ kept (one per seller)
                                            └─ rejected (with reason)
   ▼
verdict.judge(price, mrp, offers) ─► street price (median) ─► verdict
   │
serp.py ── fixtures/cache/<hash>.json  (cache + demo data)
```

| SerpApi engine | Provides |
|---|---|
| `amazon_product` | the claim, by ASIN |
| `amazon` | product-name search on amazon.in |
| `google_shopping` (`gl=in`) | Indian sellers' listings and prices |
| `google` (`gl=in`) | popular-product results and retailer pages with a price in the snippet |
| `google_immersive_product` | every store behind a grouped Google product |

A live check costs **at most five searches**.

---

## 6. The SerpApi Client, Cache & Demo Mode

`backend/aslideal/serp.py`:

```python
def cache_key(params: dict) -> str:
    clean = {k: str(v) for k, v in params.items() if k != "api_key"}   # the key never affects or enters the cache
    blob = json.dumps(clean, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]

class Serp:
    def __init__(self, api_key=None, cache_dir=DEFAULT_CACHE, demo=None, transport=None):
        self.api_key = api_key if api_key is not None else os.environ.get("SERPAPI_KEY", "")
        if demo is None:
            demo = os.environ.get("DEMO_MODE", "") == "1" or not self.api_key
        ...

    def search(self, **params) -> dict:
        path = self.cache_dir / f"{cache_key(params)}.json"
        if path.exists():
            return json.loads(path.read_text())["response"]          # repeat = free
        if self.demo:
            raise DemoMiss("This search isn't in the demo data. Add a SERPAPI_KEY to run live searches.")
        resp = self._http.get(ENDPOINT, params={**params, "api_key": self.api_key})
        data = resp.json()
        if data.get("error"):
            # "no results" is a valid answer and worth caching; anything else is not.
            if "hasn't returned any results" not in data["error"]:
                raise SerpError(data["error"])
        data.pop("search_metadata", None)   # holds the account's json_endpoint and timing noise
        path.write_text(json.dumps({"params": params, "response": data}, ensure_ascii=False))
        return data
```

### Why cache everything to disk?
- The free plan is **250 searches a month**. A lookup made once is never paid for again.
- The committed cache **is the demo data**: anyone who clones the repo can use the app with no key.
- Tests replay real responses, so they're realistic and need no network.

`quota()` reads searches left from SerpApi's account endpoint, which doesn't count against the quota.

---

## 7. Step 1: The Claim (Amazon.in)

```python
ASIN_IN_URL = re.compile(r"/(?:dp|gp/product|product)/([A-Z0-9]{10})")

def parse_asin(text: str):
    """The ASIN in an amazon.in link, or the text itself if it is one."""
    m = ASIN_IN_URL.search(text.strip())
    if m:
        return m.group(1)
    return text.upper() if ASIN.match(text.upper()) else None
```

`amazon_product(serp, asin)` calls the `amazon_product` engine and returns title, brand, price, M.R.P.,
stock, thumbnail and claimed discount. The check stops early if:
- Amazon.in shows no price ("The listing may be unavailable."),
- the listing names **no brand**, because other sellers' listings can't be matched to it safely.

`amazon_search(serp, query)` powers the name search, so the user can pick the exact listing.

---

## 8. Step 2: Finding Other Sellers

`pipeline.check()` builds one search from the product's brand, identity words and one describing word
(`match.search_query`, e.g. `PHILIPS HL7756 Mixer`: "HL7756" alone finds spare parts), then:

1. **Google Shopping**: each result is one seller's price for one listing.
2. **Google web search** (`"<query> price"`, 20 results): `immersive_products`, plus organic retailer
   pages (Flipkart, Croma, brand stores) whose rich snippet shows a single price and stock.
3. **Google product pages** (`google_immersive_product`, `more_stores=true`): open up to **2** grouped
   products to list every store. Other sellers' products are opened first (Amazon's own product page
   only lists Amazon), ranked by `similarity()`. It stops once there are enough sellers.

Every candidate goes through one gate:

```python
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
```

---

## 9. Step 3: Same-Product Matching

The hardest part. **A wrong match is worse than no match**: comparing Airdopes Prime 412 against the
413's prices, or against a ₹199 silicone case, would produce a confident verdict about the wrong thing.

### Identity: the product's name through its first model number
```python
def core_name(title):
    """'Airdopes Prime 412, 4Mics AI-ENx Tech, 50 Hrs Battery (Midnight Black)' -> 'Airdopes Prime 412'"""
    title = re.sub(r"^\s*20\d\d\s+launch\s+", "", title or "", flags=re.I)
    return re.split(r"\s*(?:,|\||\(|\[|\s-\s|\s–\s|;|:)", title, maxsplit=1)[0].strip()

def identity(title, brand=""):
    """Name through the first model number, plus tier words right after it ('Note 14 Pro plus')."""
    words = [t for t in tokens(core_name(title)) if t not in FILLER and t not in brand_words]
    for i, t in enumerate(words):
        if is_model(t):                        # any token containing a digit
            end = i + 1
            while end < len(words) and words[end] in TIER_WORDS:
                end += 1
            return words[:end]
    return words
```

`tokens()` lowercases, splits a trailing `+` into `plus` (Pro+ is not Pro), and joins `128 GB` into `128gb`.

### The rules
```python
def same_product(reference, candidate, brand=""):
    cand_words = [t for t in tokens(candidate) if t not in FILLER]
    # 1. In order and side by side: 'Pro 6' is not 'Buds Air 6 Pro'.
    if not contains_run(cand_words, identity(reference, brand)):
        return False
    # 2. If the reference says what it is ('Smart Watch'), the candidate must share a word of it.
    kind = describing_words(reference, brand)
    if kind and not kind & set(cand_words):
        return False
    # 3. No extra tier word: '15' is inside 'iPhone 15 Pro' too.
    if (set(tokens(core_name(candidate))) & TIER_WORDS) - set(tokens(core_name(reference))):
        return False
    # 4. Stated memory must match: 8GB/128GB ≠ 8GB/256GB.
    ...
    # 5. The brand must appear.
    # 6. No accessory, spare-part or refurbished words the reference lacks.
    if is_accessory(candidate, reference):
        return False
    return True
```

| Rule | Example it stops |
|---|---|
| Identity words in order, adjacent | boAt "Rockerz 412" headphones vs "Airdopes Prime 412" earbuds |
| Describing word shared | "Air Buds Pro 6" (earbuds) vs "Pro 6 Smart Watch" |
| No added tier word | "iPhone 15 Pro" vs "iPhone 15" |
| Same memory | 256 GB variant vs 128 GB |
| Brand present | a look-alike from another brand |
| Accessory words | "case", "strap", "tempered", "spare", "renewed", "refurbished", … |

`TIER_WORDS = {pro, max, plus, ultra, lite, mini, neo, fe, anc}`. Tier words are checked against the
**core name only**, so "Hustle like a pro" in a feature blurb doesn't count.

### Why strict?
Some real matches get rejected. That's the accepted trade-off: "Not enough data" is honest, while a
wrong comparison would be confidently false.

---

## 10. Step 4: Offer Filters

Even the right product can have an unusable price:

```python
IMPORT_RESELLERS = ("desertcart", "ubuy")          # import foreign stock at foreign prices
ABOVE_MRP = 1.10      # delivery can push a total slightly past M.R.P.; more can't be the same item
TOO_CHEAP = 0.40      # a new item under 40% of Amazon's price is a part, used, or mislabelled
FINANCE_WORDS = {"emi", "finance", "loan"}
FOREIGN_TLD = re.compile(r"\.(?:sa|ae|uk|us|ca|au|sg|pk|bd|lk|np|qa|kw|om|bh|my|de)$")

def offer_problem(o, mrp=None, price=None):
    """Why an offer can't stand for what the product sells for in India, if it can't."""
    if any(r in o.seller.lower() for r in IMPORT_RESELLERS): return "import reseller"
    if mrp and o.price > ABOVE_MRP * mrp:                    return "priced above the M.R.P."
    if price and o.price < TOO_CHEAP * price:                return "too cheap to be the same new item"
    if any(w in name.split() for w in FINANCE_WORDS) or "snapmint" in name:
        return "financing listing, not a retail price"
    if FOREIGN_TLD matches the seller name or link host:     return "ships from outside India"
    return None
```

Out-of-stock sellers are kept in the list but **not counted**, with a note saying so.

---

## 11. Step 5: Street Price & Verdict

`backend/aslideal/verdict.py`:

```python
MIN_SELLERS = 2      # below this, no street price to speak of
REAL_DEAL = 0.10     # beats the street price by 10%+
SAME_PRICE = 0.05    # within 5% is the going rate
BIG_CLAIM = 0.20     # a claimed discount under 20% isn't worth flagging
AT_MRP = 0.95        # a seller within 5% of M.R.P. counts as charging it

def is_own(seller):
    """The claim is Amazon's, so Amazon's own listings can't also be the evidence."""
    return seller.lower().startswith("amazon")

def judge(price, mrp, offers):
    claimed = 1 - price / mrp if mrp and mrp > price else 0.0
    others = [o for o in offers if o.in_stock and not is_own(o.seller) and o.price > 0]
    if len(others) < MIN_SELLERS:
        ...  # "unverified": not enough to say what it normally sells for
    street = median(o.price for o in others)
    real = 1 - price / street
    v.mrp_charged_by = [o.seller for o in others if o.price >= AT_MRP * mrp]

    if real >= REAL_DEAL:                               kind = "real_deal"
    elif real <= -SAME_PRICE:                           kind = "above_market"
    elif claimed >= BIG_CLAIM and not v.mrp_charged_by: kind = "reference_gap"
    else:                                               kind = "going_rate"
```

| Kind | Shown as | When |
|---|---|---|
| `real_deal` | **Real saving** | Amazon ≥ 10% below the street price |
| `reference_gap` | **Discount from a price nobody charges** | claim ≥ 20%, Amazon within −10%…+5% of street, and no in-stock seller charges ~M.R.P. |
| `going_rate` | **Normal price** | near the street price, no big claim (or someone does charge M.R.P.) |
| `above_market` | **Cheaper elsewhere** | Amazon ≥ 5% above the street price |
| `unverified` | **Not enough data** | fewer than 2 other in-stock sellers |

The `reference_gap` headline is built from this template (values filled in from the check):

```python
f"\"{pct(claimed)} off\" is measured from {rupees(mrp)}, which none of the {n} charge. "
f"They sell it for about {rupees(street)}, so the saving vs the market is {pct(max(real, 0))}."
```

`rupees()` formats with **Indian digit grouping** (₹1,23,456).

---

## 12. The Trail: "How We Checked"

`check()` records one entry per SerpApi call:

```python
trail.append({"engine": "amazon_product", "query": asin,
              "found": f"Amazon.in listing at ₹{listing['price']:,.0f}{mrp_text}"})
trail.append({"engine": "google_shopping", "query": shopping_q,
              "found": plural(len(shopping.get("shopping_results", [])), "shopping result")})
...
trail.append({"engine": "match", "query": " ".join(match.identity(title, brand)),
              "found": f"{kept} other in-stock sellers kept, {n} listings left out",
              "reasons": dict(reasons.most_common())})
```

The last entry groups the rejections by reason. It powers the report's "How we checked", the evidence
funnel, and the home page console replay. The report is **auditable**: every number traces back to a
search.

---

## 13. API

| Method | Path | Returns |
|---|---|---|
| GET | `/api/status` | demo or live, searches left, recorded products |
| GET | `/api/scan?q=&limit=` | checks several advertised deals for one search and aggregates them; up to five searches per listing, capped at ten listings |
| GET | `/api/scan.csv?q=&limit=` | the same shelf scan as a CSV download |
| GET | `/api/lens?url=` | `google_lens` names the product in a photo, then returns Amazon.in matches and the prices Lens saw |
| GET | `/api/history/{asin}` | every reading a live check recorded for one product, and what moved since the first |
| GET | `/api/gallery` | a verdict summary per recorded product, with `screened` and `left_out` counts; **always from the cache**, so the home page never spends a search |
| GET | `/api/search?q=` | Amazon.in listings for a name |
| GET | `/api/check/{asin}` | `listing`, `verdict`, `offers`, `rejected`, `trail`, `matched_product` |
| GET | `/` | the page |

Errors map cleanly:

```python
def _answer(fn, *args):
    try:
        return fn(serp, *args)
    except DemoMiss as e:
        raise HTTPException(404, str(e))           # not in the recorded data
    except SerpError as e:
        raise HTTPException(502, f"SerpApi: {e}")  # upstream problem
```

`api.py` loads `.env` from the project root with `python-dotenv` (`load_dotenv(ROOT / ".env")`).

---

## 14. Frontend: Home Page

`backend/aslideal/web/`: one page with **a single dark theme** (the light theme was removed).

- **Search box**: paste a link or type a name. The placeholder types itself out (`typePlaceholder`).
  Results show as pickable listings.
- **Console card**: replays one recorded check line by line from its trail, then fills two ring gauges:

```js
async function replayConsole(c) {
  const r = await api("/api/check/" + c.asin);
  lines.replaceChildren(...(r.trail || []).map((s) => el("li", {}, /* engine + what it found */)));
  await sleep(700);
  for (const li of lines.children) { li.classList.add("on"); await sleep(520); }   // one line at a time
  setRing($("c-ring1"), v.claimed_discount || 0);                 // Amazon's claim
  setRing($("c-ring2"), Math.abs(real), real < 0);                // real saving (red if negative)
}
```

- **Counters**: products checked, listings screened and left out, summed from `/api/gallery` and
  animated with `countUp`.
- **Checked-products gallery** with **filters** by verdict (`renderFilters`).
- **Routing**: a report's address is `#check/<ASIN>`, so each report has its own link and Back returns
  to the gallery:

```js
function route() {
  const m = location.hash.match(/^#check\/([A-Z0-9]{10})$/);
  if (m) return runCheck(m[1]);
  $("report").hidden = true;
}
window.addEventListener("hashchange", route);
```

- **Progress dialog** during a live check (about half a minute). The steps shown are paced by a timer,
  not the server; the real record is "How we checked".

---

## 15. Frontend: The Report

`renderReport(r)` builds:

1. **Verdict** headline, the **two ring gauges** (claimed discount; real saving vs other stores) and the
   street price.
2. **Price chart** (`renderChart`): one row per seller with the store logo, and the **M.R.P.** and
   **street price** drawn as reference lines. `niceTicks()` picks round axis values. Hovering shows a
   tooltip.
3. **Seller table** with links.
4. **"How we checked"** (`renderTrail`).
5. **Evidence funnel** (`renderFunnel`): listings found → kept (same product) → left out, a stacked bar
   split by rejection reason (with an `aria-label` reading out the counts), and a collapsible table of
   every left-out listing with its reason.

```js
const segs = [["same product, kept", kept, "var(--real)"],
              ...reasons.map(([why, n], i) => [why, n, REASON_COLOURS[i % REASON_COLOURS.length]])];
// segments start at zero width, then grow to their counts on the next frame (animated)
requestAnimationFrame(() => requestAnimationFrame(() =>
  [...stack.children].forEach((seg, i) => (seg.style.flexGrow = String(segs[i][1])))));
```

Sections fade in with an IntersectionObserver (`observeReveal`).

---

## 16. Configuration

`.env` in the project root:

| Variable | Purpose |
|---|---|
| `SERPAPI_KEY` | enables live checks; without it the app runs in demo mode |
| `DEMO_MODE=1` | forces recorded data even with a key |
| `PORT` (shell) | port for `run.sh`, default 8000 |

Recorded responses hold search results only, never the key (`cache_key` drops `api_key`).

---

## 17. Testing

**Run pytest from `backend/`**. From the repo root you get 3 import errors.

```bash
./run.sh                      # once, to create backend/.venv
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q          # 29 passed
```

| File | Covers |
|---|---|
| `tests/test_match.py` | same-product rules, including look-alike model names, tiers, memory, accessories |
| `tests/test_verdict.py` | street price and every verdict threshold |
| `tests/test_pipeline.py` | end to end on the recorded responses |

---

## 18. Evaluation (Honest Numbers)

```bash
cd backend
DEMO_MODE=1 .venv/bin/python -m scripts.evaluate    # replay from fixtures
.venv/bin/python -m scripts.evaluate                # live, spends searches
```

- A fixed set of **8** Amazon.in listings, all showing an M.R.P., **frozen on 2026-09-18**. Never edit it
  to improve the score; add a new set instead.
- **4 of 8 reach a verdict.** The rest say so instead of guessing: three because too few Indian sellers
  of the exact model are indexed by Google, one because Amazon.in showed no price.
- **Three of the eight products were also used while developing the matcher**, so this is not a clean
  held-out score. Say so whenever quoting it.
- Results are in the README and `fixtures/evaluation.json`.

---

## 19. Limitations & Wording Rules

- **A snapshot, unless you keep your own.** SerpApi has no price history, so a single check can't tell
  whether a price was raised before a sale. Every live check is recorded in `fixtures/history.json`
  (one reading per product per day), and the report compares a product with its own past readings —
  but that only helps once a product has been checked more than once.
- **Only in-stock sellers Google indexes count.**
- **Matching is strict on purpose.** Phones are hardest (memory variant must be stated).
- **Wording:** the tool reports what prices show and **never** calls a retailer's discount "fake" or
  "fraud". An M.R.P. is a legal printed maximum, not an invented number. Keep this in the UI, README and
  any demo video.

---

## 20. Troubleshooting

| Problem | Fix |
|---|---|
| "not in the recorded data" | demo mode; add `SERPAPI_KEY` and make sure `DEMO_MODE` isn't `1` |
| "Not enough data" for a popular product | fewer than 2 in-stock sellers passed matching; see "What we left out, and why" |
| progress dialog takes a while | a live check makes up to 5 calls (~30 s) |
| `run.sh` needs Python 3.9+ | install 3.9+ (3.12 tested); `run.sh` looks for newer versions itself |
| searches ran out | `/api/status` shows the quota; repeat checks are free from the cache |
| pytest import errors | run it from `backend/` |
| 502 "SerpApi: …" | upstream error or bad key; the message says which |

---

## 21. Complete Feature Summary

### All Features Built

| # | Feature | Type | Key Files |
|---|---|---|---|
| 1 | SerpApi client with disk cache | Backend | `serp.py` |
| 2 | Demo mode on recorded responses | Backend | `serp.py`, `fixtures/cache/` |
| 3 | Link/ASIN parsing and name search | Backend | `pipeline.py` |
| 4 | Multi-engine seller discovery (≤5 searches) | Backend | `pipeline.py` |
| 5 | Strict same-product matching | Core | `match.py` |
| 6 | Offer filters (imports, EMI, foreign, price bounds) | Core | `pipeline.py` |
| 7 | One seller counts once | Core | `pipeline.py` |
| 8 | Median street price and five verdicts | Core | `verdict.py` |
| 9 | Trail of every call + rejection reasons | Backend | `pipeline.py` |
| 10 | Gallery endpoint that never spends a search | API | `api.py` |
| 11 | Console replay, counters, gallery filters | Frontend | `app.js`, `index.html` |
| 12 | Report: gauges, price chart, trail, evidence funnel | Frontend | `app.js`, `style.css` |
| 13 | `#check/ASIN` links | Frontend | `app.js` |
| 14 | 41 tests + two frozen evaluation sets (11/14) | Testing | `tests/`, `scripts/evaluate.py` |
| 15 | One-command start | Tooling | `run.sh` |
| 16 | Chrome extension: verdict on the Amazon.in page | Frontend | `extension/` |
| 17 | Shorter fallback search + manufacturer model codes | Core | `match.py`, `pipeline.py` |
| 18 | Size normalisation and jar/pack count rule | Core | `match.py` |
| 19 | Price history from live checks | Backend | `history.py` |
| 20 | Shareable 1200x630 result card | Frontend | `app.js` |
| 21 | Dark-pattern check (CCPA-shaped signals) | Core | `signals.py` |
| 22 | Buyer-complaint insights from Amazon reviews | Core | `signals.py` |
| 23 | Delivery-inclusive totals and conditional savings | Core | `signals.py`, `pipeline.py` |
| 24 | Shelf scan of a whole search | Backend | `pipeline.py`, `api.py` |
| 25 | Check from a photo (`google_lens`) | Backend | `api.py` |
| 26 | Lens as a price source when sellers are thin | Core | `pipeline.py` |
| 27 | Seller names taken from the link host when Lens gives a title | Core | `pipeline.py` |
| 28 | No street price from two sellers who disagree | Core | `verdict.py` |
| 29 | Unavailable listing suggests live ones instead | Backend | `pipeline.py` |
| 30 | CI on every push, MIT licence | Tooling | `.github/workflows/tests.yml`, `LICENSE` |
| 31 | Shelf scan as CSV (page, `/api/scan.csv`, `scripts/scan.py`) | Backend | `api.py`, `scripts/scan.py` |
| 32 | Gallery kept in memory until the recorded data changes (0.56 s to 0.007 s) | Backend | `api.py` |

### Data Flow Architecture

```
User: amazon.in link / ASIN / product name
   │ /api/search (name) ─► amazon engine ─► pick listing
   ▼
/api/check/{asin} ─► pipeline.check
   ├─ amazon_product ─► claim (price, M.R.P., brand)
   ├─ search_query() ─► google_shopping ─┐
   │                  ─► google (price) ─┼─► add(): offer_problem ─► same_product
   │   top candidates ─► immersive_product┘        ├─ kept (best price per seller)
   │                                               └─ rejected + reason
   ├─ judge(): others (in stock, not Amazon) ─► median ─► real vs claimed ─► verdict
   └─ trail [...engines, match{reasons}]
   ▼
Report: verdict · rings · price chart (M.R.P. + street lines) · How we checked · Evidence funnel

every SerpApi call ─► fixtures/cache/<sha1>.json  (free repeats + demo data)
```

### Tech Stack at a Glance

```
Data:      SerpApi (amazon_product, amazon, google_shopping, google, google_immersive_product)
Backend:   FastAPI + httpx + stdlib (median, regex matching)
Frontend:  vanilla JS + CSS, one dark theme
Cache:     fixtures/cache/*.json (committed, doubles as demo data)
Testing:   pytest (29, from backend/), frozen 8-listing evaluation
Run:       ./run.sh → http://localhost:8000
```
