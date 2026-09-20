"""Run the check on a frozen set of Amazon.in listings and report the hit rate.

The question this answers: for how many real products can the tool reach a
verdict at all? The set is fixed by ASIN, every one a listing that shows a
struck-through M.R.P., fixed on 2026-09-18. Three of them (boAt, JBL,
Philips) were also used while developing the matcher. Don't edit the set to
improve the number; add a new set instead.

Everything goes through the cache, so a rerun costs nothing and only new
checks spend searches.

    python -m scripts.evaluate              # live, uses SERPAPI_KEY
    DEMO_MODE=1 python -m scripts.evaluate  # replay from fixtures only
"""

import json
import sys
from collections import Counter

from dotenv import load_dotenv

from aslideal.pipeline import check
from aslideal.serp import ROOT, DemoMiss, Serp, SerpError

FROZEN_SET = {
    "B0FDFRGWN8": "boAt Airdopes Prime 412",
    "B0C3V5X3QT": "JBL Tune 520BT",
    "B01GZSQJPA": "Philips HL7756 mixer grinder",
    "B00YMJ0OI8": "Prestige PIC 20 induction cooktop",
    "B0F7LXZG7S": "Redmi Note 14 Pro 5G",
    "B0DGXRLS1C": "Noise Pro 6 smart watch",
    "B0F43VZ4H1": "Samsung Galaxy M56 5G",
    "B0FDB9ZCTD": "Samsung Galaxy M36 5G",
}
# A second set, fixed on 2026-09-20 to measure coverage beyond the first eight:
# different categories, and deliberately awkward listings (no model number in the
# title, a brand Amazon's search doesn't name).
SET_B = {
    "B00MIYM0VS": "Milton Thermosteel flask 1L",
    "B078JDNZJ8": "Havells Instanio 3L water heater",
    "B08TTXNZ4Y": "boAt Rockerz 255 Pro+",
    "B08CFJBZRK": "Prestige Iris 750W mixer grinder",
    "B095BPMHWH": "Philips hair straightener",
    "B006LX9VPU": "Nivea Men face wash 100g",
}
NO_VERDICT = {"unverified", "error", "not_in_demo_data"}
OUT = ROOT / "fixtures" / "evaluation.json"


def main():
    load_dotenv(ROOT / ".env")
    serp = Serp()
    sets = {"set A (2026-09-18)": FROZEN_SET, "set B (2026-09-20)": SET_B}
    if len(sys.argv) > 1 and sys.argv[1] == "--set-a":
        sets = {"set A (2026-09-18)": FROZEN_SET}
    rows = []
    for label, products in sets.items():
        print(f"\n{label}")
        rows += run_set(serp, products)
    counts = Counter(r["kind"] for r in rows)
    verdicts = sum(n for k, n in counts.items() if k not in NO_VERDICT)
    print(f"\n{verdicts}/{len(rows)} listings reached a verdict  {dict(counts)}")
    quota = serp.quota()
    print(f"live searches this run: {serp.live_calls}" + (f", left this month: {quota['left']}" if quota else ""))
    OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    return 0


def run_set(serp, products):
    rows = []
    for asin, name in products.items():
        try:
            r = check(serp, asin)
        except DemoMiss:
            rows.append({"asin": asin, "name": name, "kind": "not_in_demo_data"})
            continue
        except SerpError as e:
            r = {"error": str(e)}
        if "error" in r:
            rows.append({"asin": asin, "name": name, "kind": "error", "headline": r["error"]})
            print(f"{name[:34]:34} error          {r['error']}", flush=True)
            continue
        v = r["verdict"]
        rows.append({
            "asin": asin, "name": name, "kind": v["kind"], "headline": v["headline"],
            "sellers": v["sellers_used"], "price": v["price"], "mrp": v["mrp"], "street": v["street_price"],
        })
        print(f"{name[:34]:34} {v['kind']:14} sellers={v['sellers_used']:<2} {v['headline'][:90]}", flush=True)
    return rows


if __name__ == "__main__":
    sys.exit(main())
