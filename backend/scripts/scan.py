"""Scan a whole search from the command line and save it as CSV.

    python -m scripts.scan "wireless earbuds under 2000" --limit 5 --csv earbuds.csv

A live scan costs up to seven SerpApi searches per listing; anything already in the
cache is free, and DEMO_MODE=1 uses the cache only.
"""

import argparse
import csv
import sys

from dotenv import load_dotenv

from aslideal.api import SCAN_COLUMNS
from aslideal.pipeline import scan
from aslideal.serp import ROOT, Serp


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--csv", help="write the rows to this file")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    serp = Serp()
    result = scan(serp, args.query, max(1, min(args.limit, 10)))
    for row in result["rows"]:
        real = row.get("real_discount")
        print(f"{row['kind']:14} claimed {round((row['claimed_discount'] or 0) * 100):>3}%  "
              f"real {'  ?' if real is None else f'{round(real * 100):>3}'}%  {row['title'][:60]}")
    print("\n" + result["headline"])
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SCAN_COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(result["rows"])
        print(f"saved {len(result['rows'])} rows to {args.csv}")
    print(f"live searches: {serp.live_calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
