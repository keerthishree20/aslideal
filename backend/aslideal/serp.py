"""SerpApi client with a disk cache.

Every response is written to ``fixtures/cache/<key>.json`` together with the
parameters that produced it. The free plan is 250 searches a month, so a
lookup that has been made once is never paid for again, and the committed
cache doubles as the demo data for anyone who clones the repo without a key.
"""

import hashlib
import json
import os
from pathlib import Path

import httpx

ENDPOINT = "https://serpapi.com/search.json"
ACCOUNT_ENDPOINT = "https://serpapi.com/account.json"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = ROOT / "fixtures" / "cache"


class SerpError(Exception):
    """A search could not be answered, from the network or the cache."""


class DemoMiss(SerpError):
    """Demo mode was asked for a search that is not in the cache."""


def cache_key(params: dict) -> str:
    clean = {k: str(v) for k, v in params.items() if k != "api_key"}
    blob = json.dumps(clean, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


class Serp:
    def __init__(self, api_key=None, cache_dir=DEFAULT_CACHE, demo=None, transport=None):
        self.api_key = api_key if api_key is not None else os.environ.get("SERPAPI_KEY", "")
        if demo is None:
            demo = os.environ.get("DEMO_MODE", "") == "1" or not self.api_key
        self.demo = demo
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.Client(timeout=120, transport=transport)
        self.live_calls = 0

    def search(self, **params) -> dict:
        path = self.cache_dir / f"{cache_key(params)}.json"
        if path.exists():
            return json.loads(path.read_text())["response"]
        if self.demo:
            raise DemoMiss("This search isn't in the demo data. Add a SERPAPI_KEY to run live searches.")

        try:
            resp = self._http.get(ENDPOINT, params={**params, "api_key": self.api_key})
        except httpx.HTTPError as e:
            raise SerpError(f"SerpApi didn't answer: {type(e).__name__}") from e
        self.live_calls += 1
        try:
            data = resp.json()
        except ValueError:
            raise SerpError(f"SerpApi returned HTTP {resp.status_code} with no JSON body")
        if data.get("error"):
            # "no results" is a valid answer and worth caching; anything else is not.
            if "hasn't returned any results" not in data["error"]:
                raise SerpError(data["error"])
        data.pop("search_metadata", None)  # holds the account's json_endpoint and timing noise
        path.write_text(json.dumps({"params": params, "response": data}, ensure_ascii=False))
        return data

    def quota(self):
        """Searches left this month. The account endpoint doesn't count against the quota."""
        if self.demo:
            return None
        data = self._http.get(ACCOUNT_ENDPOINT, params={"api_key": self.api_key}).json()
        return {
            "plan": data.get("plan_name"),
            "left": data.get("total_searches_left"),
            "per_month": data.get("searches_per_month"),
        }

    def cached_queries(self, engine="amazon", field="k"):
        """Queries already in the cache, which is what demo mode can answer."""
        out = []
        for p in sorted(self.cache_dir.glob("*.json")):
            params = json.loads(p.read_text())["params"]
            if params.get("engine") == engine and params.get(field):
                out.append(params[field])
        return sorted(set(out))
