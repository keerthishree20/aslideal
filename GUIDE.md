# AsliDeal — Complete Project Guide

## Table of Contents
1. [What is AsliDeal?](#what-is-aslideal)
2. [Quick Start](#quick-start)
3. [Core Concepts](#core-concepts)
4. [Architecture](#architecture)
5. [Life of a Check](#life-of-a-check)
6. [Code Walkthrough](#code-walkthrough)
7. [API Reference](#api-reference)
8. [Configuration](#configuration)
9. [Demo Mode and the Cache](#demo-mode-and-the-cache)
10. [Testing and Evaluation](#testing-and-evaluation)
11. [Limitations](#limitations)
12. [Troubleshooting](#troubleshooting)

---

## What is AsliDeal?

AsliDeal checks whether an Amazon.in discount is real. Amazon.in shows a struck-through M.R.P. and a
big "% off" on almost every product. The M.R.P. is the legal maximum printed on the box, not a price
anyone actually charges. AsliDeal compares the Amazon price with what other Indian stores charge for
the **same** product today, and gives a verdict with the evidence.

Every piece of data comes from SerpApi. There is no other source.

---

## Quick Start

```bash
./run.sh            # http://localhost:8000
```

On first run, `run.sh` finds a Python of 3.9 or newer, creates `backend/.venv`, and installs the
dependencies. It then serves the app with uvicorn.

With no API key it runs in **demo mode** on recorded responses. Pick any product under "Try" to see a
full report, with nothing fetched from the network.

To check any product live:

```bash
cp .env.example .env    # put your key after SERPAPI_KEY=
./run.sh
```

Get a free key at https://serpapi.com. Then paste an amazon.in product link, or type a product name
and pick the exact listing.

`.env` is gitignored. Never commit it.

---

## Core Concepts

### The claim
The Amazon.in price *P* and M.R.P. *M*. The claimed discount is `1 - P/M`.

### The evidence
Listings for the same product from other Indian sellers, found through Google Shopping, Google web
search and Google's product pages.

### Same-product matching
The hardest part, because comparing against the wrong product is worse than not comparing. A listing
counts only if it:
- names the same model, with the model words in order and next to each other,
- adds no tier word such as *Pro*, *Max* or *Plus*,
- states the same memory, when it states one,
- is not an accessory, spare part or renewed unit,
- is in stock, sold in India, not an EMI or financing listing, and not an import reseller,
- is priced between 40% of Amazon's price and 110% of the M.R.P.

Each seller counts once. Every rejected listing appears in the report with its reason.

### Street price
The median price of the other in-stock sellers. Amazon's own listings never count as evidence for
Amazon's claim.

### Verdicts
| verdict | when |
|---|---|
| Real saving | Amazon is at least 10% below the street price |
| Discount from a price nobody charges | claimed discount of 20% or more, Amazon within 10% below to 5% above the street price, and no in-stock seller charges the M.R.P. |
| Normal price | close to the street price, with no big claim |
| Cheaper elsewhere | Amazon is at least 5% above the street price |
| Not enough data | fewer than two other in-stock sellers of the exact product |

The wording states what the prices show and says nothing about anyone's intent.

---

## Architecture

```
  Browser  backend/aslideal/web/  index.html, app.js, style.css
     │  GET /api/status, /api/search?q=, /api/check/{asin}
     ▼
  FastAPI  backend/aslideal/api.py   (serves the page too)
     │
  pipeline.py   claim ──► evidence ──► filters
     │            │           │
     │            │        match.py    same-product rules
     │            ▼
  serp.py      SerpApi client, disk cache, demo mode
     │            │
     │         fixtures/cache/*.json   recorded responses, also the demo data
     ▼
  verdict.py    street price and verdict
```

### SerpApi engines used
| engine | provides |
|---|---|
| `amazon_product` | the claim: title, brand, price, M.R.P. and stock, by ASIN |
| `amazon` | product-name search on amazon.in, to pick the exact listing |
| `google_shopping` with `gl=in` | Indian sellers' listings and prices |
| `google` with `gl=in` | more sellers from popular-products results, and retailer pages whose snippet shows a price and stock |
| `google_immersive_product` | every store behind a grouped Google product |

A live check costs at most five searches.

---

## Life of a Check

1. The user pastes an amazon.in link or picks a search result. `parse_asin()` extracts the ASIN.
2. `amazon_product()` fetches the listing: the claim.
3. `search_query()` builds a search from the product's core name and brand, and the three Google
   engines return candidate listings.
4. `same_product()` and `offer_problem()` accept or reject each candidate, recording the reason.
5. `judge()` computes the street price from the accepted sellers and picks the verdict.
6. The page shows the verdict, the accepted sellers, and every rejected listing with its reason.

---

## Code Walkthrough

| file | key functions |
|---|---|
| `backend/aslideal/serp.py` | `Serp` client. `cache_key()` hashes the request parameters. `DemoMiss` is raised in demo mode for anything not recorded. `quota()` reads searches left |
| `backend/aslideal/match.py` | `tokens()`, `core_name()`, `identity()`, `describing_words()`, `is_accessory()`, `same_product()`, `similarity()`, `search_query()` |
| `backend/aslideal/pipeline.py` | `parse_asin()`, `amazon_search()`, `amazon_product()`, `offer_problem()`, `check()` |
| `backend/aslideal/verdict.py` | `Offer`, `Verdict`, `judge()`, `is_own()` for Amazon's own listings, `rupees()` and `pct()` formatting |
| `backend/aslideal/api.py` | the FastAPI app, `.env` loading, the three API routes and the page |
| `backend/aslideal/web/` | the single-page front end |
| `backend/scripts/evaluate.py` | runs the fixed evaluation set and reports how many reach a verdict |

---

## API Reference

| method | path | returns |
|---|---|---|
| `GET` | `/api/status` | demo or live, searches left, and the products the recorded data can answer |
| `GET` | `/api/search?q=` | Amazon.in listings matching a product name |
| `GET` | `/api/check/{asin}` | the full report for one listing |
| `GET` | `/` | the page |

---

## Configuration

`.env` in the project root:

| variable | purpose |
|---|---|
| `SERPAPI_KEY` | enables live checks. Without it the app runs in demo mode |
| `DEMO_MODE=1` | forces recorded data even when a key is set |

`PORT` changes the port `run.sh` serves on, default 8000.

---

## Demo Mode and the Cache

Every SerpApi response is saved in `fixtures/cache/`, named by a hash of the request. Repeating a
check reads the saved file and costs no search. The same files are the demo data, which is why the
app works for anyone who clones it, without a key.

In demo mode, a request with no recorded response raises `DemoMiss`, and the page says the product
is not in the recorded set.

Recorded responses hold search results only, never the key.

---

## Testing and Evaluation

```bash
./run.sh                 # once, to create backend/.venv
cd backend
.venv/bin/python -m pytest
```

| file | covers |
|---|---|
| `tests/test_match.py` | the same-product rules, including the look-alike model names |
| `tests/test_verdict.py` | street price and each verdict's thresholds |
| `tests/test_pipeline.py` | end to end on the recorded responses |

### Coverage evaluation
```bash
cd backend
DEMO_MODE=1 .venv/bin/python -m scripts.evaluate    # replay from fixtures
.venv/bin/python -m scripts.evaluate                # live, uses SERPAPI_KEY
```

The evaluation set of eight listings was fixed on 2026-09-18. Do not edit it to improve the score.
Add a new set instead. Results are in the README and `fixtures/evaluation.json`.

---

## Limitations

- **A snapshot, not a history.** SerpApi has no price history, so it cannot tell whether a price was
  raised before a sale.
- **Only in-stock sellers that Google indexes count.**
- **Matching is strict on purpose.** Some real matches are rejected, and phones are hardest because
  a listing must state the same memory variant.

---

## Troubleshooting

### The page says a product is not in the recorded data
You are in demo mode, and only the recorded products work. Add `SERPAPI_KEY` to `.env` for live
checks, and make sure `DEMO_MODE` is not set to `1`.

### "Not enough data" for a product you know is widely sold
Fewer than two other in-stock sellers passed the matching rules. Open the rejected listings in the
report to see why each was excluded.

### `run.sh` says it needs Python 3.9 or newer
Install Python 3.12. The system `python3` on this machine is 3.6.

### Searches run out
The free SerpApi plan has a monthly limit, shown by `/api/status`. Repeated checks are free because
of the cache.
