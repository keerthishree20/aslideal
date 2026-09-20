"""End to end on recorded SerpApi responses. Runs offline: demo mode never touches the network."""

import pytest

from aslideal.pipeline import check, offer_problem, parse_asin
from aslideal.serp import DemoMiss, Serp
from aslideal.verdict import Offer

EXPECTED = {
    "B0FDFRGWN8": "reference_gap",  # boAt Airdopes Prime 412: 69% off ₹4,490, sold at ₹1,399 everywhere
    "B0C3V5X3QT": "real_deal",      # JBL Tune 520BT
    "B01GZSQJPA": "real_deal",      # Philips HL7756
    "B00YMJ0OI8": "real_deal",      # Prestige PIC 20: 10 sellers found once the query dropped "Watts"
    "B0F7LXZG7S": "unverified",     # Redmi Note 14 Pro: no other seller states the same memory
}


@pytest.fixture(scope="module")
def serp():
    return Serp(api_key="", demo=True)


@pytest.mark.parametrize("asin,kind", EXPECTED.items())
def test_recorded_verdicts(serp, asin, kind):
    assert check(serp, asin)["verdict"]["kind"] == kind


def test_airdopes_evidence(serp):
    r = check(serp, "B0FDFRGWN8")
    sellers = {o["seller"] for o in r["offers"]}
    assert {"Flipkart", "Zepto"} <= sellers
    rejected = " ".join(o["title"] for o in r["rejected"])
    assert "Rockerz" in rejected or "413" in rejected


def test_offer_filters():
    assert offer_problem(Offer("EMI Snapmint", 1399)) == "financing listing, not a retail price"
    assert offer_problem(Offer("desertcart.in", 1766)) == "import reseller"
    assert offer_problem(Offer("Shop", 1, link="https://www.desertcart.com.sa/x")) == "ships from outside India"
    assert offer_problem(Offer("Some Store", 1, link="https://example.ae/p")) == "ships from outside India"
    assert offer_problem(Offer("Shop", 6000), mrp=4490) == "priced above the M.R.P."
    assert offer_problem(Offer("Shop", 450), price=3499) == "too cheap to be the same new item"
    assert offer_problem(Offer("Flipkart", 1399), mrp=4490, price=1399) is None


def test_parse_asin():
    assert parse_asin("https://www.amazon.in/boAt-Multipoint/dp/B0FDFRGWN8/ref=sr_1_1?k=x") == "B0FDFRGWN8"
    assert parse_asin("b0fdfrgwn8") == "B0FDFRGWN8"
    assert parse_asin("boAt Airdopes") is None


def test_demo_mode_never_calls_out(serp):
    with pytest.raises(DemoMiss):
        serp.search(engine="amazon_product", asin="B000000000", amazon_domain="amazon.in")
