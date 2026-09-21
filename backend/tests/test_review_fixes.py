"""Regression tests for the bugs found in the 2026-09-21 code review, one per finding."""

import os
import time

import pytest

from aslideal import match
from aslideal.pipeline import MAX_PRODUCT_PAGES, parse_asin
from aslideal.serp import Serp


# 1. "Pack of 3" is Amazon's usual wording; it must count like "3 Pack".
def test_pack_of_n_is_counted():
    assert match.counts("Nivea Men Face Wash 100ml (Pack of 3)") == {"pack": {3}}
    ref = "Nivea Men Dark Spot Face Wash 100ml (Pack of 3)"
    assert not match.same_product(ref, "Nivea Men Dark Spot Face Wash 100ml (Pack of 2)", "Nivea")
    assert match.same_product(ref, "Nivea Men Dark Spot Face Wash 100ml, Pack of 3", "Nivea")
    assert match.counts("Set of 4 mugs") == {"set": {4}}


# 2. A listing that states only its RAM can't stand in for a particular storage variant.
def test_storage_must_be_stated_when_the_reference_states_it():
    ref = "Samsung Galaxy M56 5G (Light Green, 8GB, 256GB Storage)"
    assert not match.same_product(ref, "Samsung Galaxy M56 5G 8GB RAM Light Green", "Samsung")
    assert match.same_product(ref, "Samsung Galaxy M56 5G 256GB Light Green", "Samsung")
    assert match.same_product(ref, "Samsung Galaxy M56 5G (8GB/256GB)", "Samsung")
    assert not match.same_product(ref, "Samsung Galaxy M56 5G (8GB/128GB)", "Samsung")


# 5. Ordinary ten-letter words are searches, not ASINs.
@pytest.mark.parametrize("word", ["smartwatch", "headphones", "television", "smartphone", "sunglasses"])
def test_ten_letter_words_are_not_asins(word):
    assert parse_asin(word) is None


def test_real_asins_still_parse():
    assert parse_asin("B0FDFRGWN8") == "B0FDFRGWN8"
    assert parse_asin("b0fdfrgwn8") == "B0FDFRGWN8"
    assert parse_asin("8193237323") == "8193237323"          # books use ISBN-10 as ASIN
    assert parse_asin("https://www.amazon.in/x/dp/B0C3V5X3QT?ref=y") == "B0C3V5X3QT"


# 7. With a key, recorded responses expire, so a later check sees today's prices.
def test_live_cache_expires_but_demo_never_does(tmp_path, monkeypatch):
    calls = []

    class FakeResp:
        status_code = 200
        def json(self):
            calls.append(1)
            return {"n": len(calls)}

    live = Serp(api_key="k", cache_dir=tmp_path, demo=False, max_age_hours=1)
    monkeypatch.setattr(live._http, "get", lambda *a, **k: FakeResp())
    assert live.search(engine="x", q="y") == {"n": 1}
    assert live.search(engine="x", q="y") == {"n": 1}          # fresh: from disk
    old = time.time() - 2 * 3600
    for f in tmp_path.glob("*.json"):
        os.utime(f, (old, old))
    assert live.search(engine="x", q="y") == {"n": 2}          # stale: fetched again
    for f in tmp_path.glob("*.json"):
        os.utime(f, (old, old))
    demo = Serp(api_key="", cache_dir=tmp_path, demo=True, max_age_hours=1)
    assert demo.search(engine="x", q="y") == {"n": 2}          # demo replays forever


# 8. The product-page budget is shared, not topped up by the fallback.
def test_product_page_budget_is_shared():
    import inspect
    from aslideal import pipeline
    src = inspect.getsource(pipeline.check)
    assert "max(1, MAX_PRODUCT_PAGES - used)" not in src
    assert MAX_PRODUCT_PAGES == 2


# 9. Brands that begin with a filler word still match.
def test_brand_starting_with_the():
    title = "The Derma Co 1% Hyaluronic Sunscreen Aqua Gel 50g"
    assert match.same_product(title, title, "The Derma Co")
