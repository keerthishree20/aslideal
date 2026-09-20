# AsliDeal

**Is that "% off" real?** AsliDeal takes an Amazon.in listing and checks its discount against what other Indian stores charge for the same product today.

Amazon.in shows almost every product with a struck-through M.R.P. and a big percentage off. The M.R.P. is a legal maximum printed on the box, not the price anyone actually sells at. So "69% off" can mean a real bargain, or it can mean every store sells it at that price. AsliDeal tells you which, and shows the evidence.

![AsliDeal home page](docs/home.png)

> **boAt Airdopes Prime 412**: Amazon.in shows ₹1,399, "69% off" an M.R.P. of ₹4,490. Flipkart and Zepto both sell it for ₹1,399, and no in-stock seller charges ₹4,490. Against the market, the saving is 0%.

![AsliDeal report for boAt Airdopes Prime 412](docs/airdopes-report.png)

Each report shows the verdict as two gauges (claimed discount vs real saving), every matching seller on one price axis with the M.R.P. and street price marked, the SerpApi calls that produced the evidence, and every listing that was left out and why. Checks can also come out the other way, as with the JBL Tune 520BT, where Amazon is really 17% cheaper: [report](docs/jbl-report.png).

**Demo video** (80 s, no narration): [`docs/asli-deal-demo.mp4`](docs/asli-deal-demo.mp4)

## Run it

```bash
./run.sh            # http://localhost:8000
```

That's it. With no API key it runs in **demo mode** on the recorded SerpApi responses in `fixtures/cache/`: click any product in the "Checked products" gallery to see a full report. Nothing is fetched from the network.

To check any product live, get a free key at [serpapi.com](https://serpapi.com), then:

```bash
cp .env.example .env    # put your key after SERPAPI_KEY=
./run.sh
```

Paste an amazon.in product link, or type a product name and pick the exact listing.

Needs Python 3.9 or newer. Tests, after `./run.sh` has run once to create the environment: `cd backend && .venv/bin/python -m pytest`.

## How SerpApi is used

Every verdict comes from five SerpApi engines. There's no other data source.

| Engine | What it provides |
|---|---|
| `amazon_product` | **The claim:** the listing's exact title, brand, price, M.R.P. (`old_price`) and stock, by ASIN |
| `amazon` | Product-name search on amazon.in, so the user can pick the exact listing |
| `google_shopping` (`gl=in`) | Indian sellers' listings and prices for the model |
| `google` web search (`gl=in`) | More sellers from the popular-products block, plus retailer pages (Flipkart, Vijay Sales, the brand's own store) whose snippet carries a price and stock status |
| `google_immersive_product` | Every store behind a grouped Google product, with price and stock |

A live check costs at most five searches. Every response is cached on disk, so repeating a check is free. The cache also serves as the demo data.

## How a verdict is reached

1. **Claim.** Amazon.in price *P* and M.R.P. *M*, so the claimed discount is `1 - P/M`.
2. **Evidence.** All listings found by the three Google engines.
3. **Matching.** This is the hard part, because a wrong comparison is worse than none. A listing counts only if:
   - it names the same model, with the words in order and side by side. boAt sells both *Airdopes Prime 412* earbuds and *Rockerz 412* headphones, and *Pro 6* is not *Air Buds Pro 6*.
   - it has no extra tier word (*Pro*, *Max*, *Plus*, *Pro+*...).
   - it has the same memory, when the listing states one (8GB/128GB vs 8GB/256GB).
   - it isn't an accessory, a spare part, or a renewed unit.
   - it's in stock, sold in India, not an EMI or financing listing, and not an import reseller.
   - it's priced at no more than 110% of the printed M.R.P. (a listing well above it is an import or a different item), and at no less than 40% of Amazon's price (below that, it's a part or a mislabelled listing).

   Each seller counts once. Every rejected listing is shown in the report with its reason.
4. **Street price.** The median of the other in-stock sellers. Amazon's own listings are never evidence for Amazon's claim.
5. **Verdict.**

| Verdict | When |
|---|---|
| Real saving | Amazon is at least 10% below the street price |
| Discount from a price nobody charges | Claimed discount ≥ 20%, but Amazon is less than 10% below (and at most 5% above) the street price, and no in-stock seller charges the M.R.P. |
| Normal price | Close to the street price, with no big claim |
| Cheaper elsewhere | At least 5% above the street price |
| Not enough data | Fewer than two other in-stock sellers of the exact product |

The wording states what the prices show and nothing about intent.

## Measured coverage

`backend/scripts/evaluate.py` runs a fixed set of 8 Amazon.in listings, all showing an M.R.P. The set was fixed on 2026-09-18 and hasn't been edited to improve the score. Three of the products were also used while developing the matcher. Results as of 2026-09-18:

| Product | Verdict |
|---|---|
| boAt Airdopes Prime 412 | Discount from a price nobody charges: "69% off" ₹4,490, market price ₹1,399 |
| Prestige PIC 20 induction cooktop | Discount from a price nobody charges: "36% off" ₹3,645, market price about ₹2,470 |
| JBL Tune 520BT | Real saving: 17% below 6 other sellers |
| Philips HL7756 mixer grinder | Real saving: 10% below 3 other sellers |
| Redmi Note 14 Pro 5G (8/128) | Not enough data: no other seller of the same variant found |
| Noise Pro 6 smart watch | Not enough data: one other seller |
| Samsung Galaxy M36 5G | Not enough data |
| Samsung Galaxy M56 5G | Listing had no price on Amazon.in |

**4 of 8 reach a verdict.** The rest say so instead of guessing. Three of the misses come from too few Indian sellers indexed by Google for the exact model, and one from Amazon.in showing no price for the listing. Phones are hardest, because a listing must state the same memory variant to count.

## Limitations

- It's a snapshot of today's prices. SerpApi has no price history, so the tool can't say whether a price was raised before a sale.
- Only in-stock sellers indexed by Google count as evidence.
- Matching is deliberately strict. Some real matches are rejected (e.g. a seller who writes "ColorFit Pro 6" for Amazon's "Pro 6").

## Layout

```
backend/aslideal/serp.py      SerpApi client with disk cache and demo mode
backend/aslideal/match.py     same-product rules
backend/aslideal/pipeline.py  claim -> evidence -> filters
backend/aslideal/verdict.py   street price and verdict
backend/aslideal/api.py       FastAPI + the page in web/
backend/tests/                matcher, verdict and end-to-end tests on recorded data
fixtures/cache/               recorded SerpApi responses (no keys)
```
