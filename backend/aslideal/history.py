"""A record of what every live check saw, so a product's price can be compared with itself.

SerpApi has no price history, so this is the only way to see whether a price or a
"% off" moved: keep what each check found. Replays from the cache are not recorded,
and one entry per product per day is enough.
"""

import json
from datetime import date
from pathlib import Path

from .serp import ROOT

FILE = ROOT / "fixtures" / "history.json"


def load(path=FILE) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return {}


def record(listing: dict, verdict: dict, path=FILE, today=None) -> list:
    """Add today's reading for one product, replacing an earlier one from the same day."""
    day = str(today or date.today())
    entry = {
        "date": day,
        "price": listing["price"],
        "mrp": listing["mrp"],
        "claimed_discount": verdict["claimed_discount"],
        "street_price": verdict["street_price"],
        "real_discount": verdict["real_discount"],
        "sellers": verdict["sellers_used"],
        "kind": verdict["kind"],
    }
    path = Path(path)
    data = load(path)
    days = [e for e in data.get(listing["asin"], []) if e["date"] != day]
    days.append(entry)
    days.sort(key=lambda e: e["date"])
    data[listing["asin"]] = days
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    return days


def changes(days: list) -> dict:
    """What moved between the first and latest reading."""
    if len(days) < 2:
        return {}
    first, last = days[0], days[-1]
    out = {"since": first["date"], "readings": len(days)}
    if first["price"] and last["price"]:
        out["price_change"] = round(last["price"] - first["price"], 2)
    if first["street_price"] and last["street_price"]:
        out["street_change"] = round(last["street_price"] - first["street_price"], 2)
    if first["mrp"] and last["mrp"] and first["mrp"] != last["mrp"]:
        out["mrp_change"] = round(last["mrp"] - first["mrp"], 2)
    return out
