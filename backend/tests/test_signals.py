from aslideal import signals

VERDICT = {"claimed_discount": 0.69, "street_price": 1399, "mrp_charged_by": []}


def test_inflated_reference_only_when_nobody_charges_the_mrp():
    listing = {"mrp": 4490}
    assert signals.inflated_reference(listing, VERDICT)["flag"] is True
    charged = {**VERDICT, "mrp_charged_by": ["Croma"]}
    assert signals.inflated_reference(listing, charged)["flag"] is False
    thin = {**VERDICT, "street_price": None}
    assert signals.inflated_reference(listing, thin)["flag"] is None  # unknown, not innocent
    small = {**VERDICT, "claimed_discount": 0.05}
    assert signals.inflated_reference(listing, small)["flag"] is False


def test_false_urgency_needs_a_deadline():
    assert signals.false_urgency({"badges": ["Limited time deal"]})["flag"] is True
    assert signals.false_urgency({"badges": ["Deal ends in 4 hours"]})["flag"] is False
    assert signals.false_urgency({"badges": ["Customers usually keep this item"]})["flag"] is False
    assert signals.false_urgency({})["flag"] is False


def test_drip_pricing_compares_delivered_prices():
    cheap_sticker = {"seller": "A", "price": 1000, "total": 1200, "in_stock": True}
    cheap_total = {"seller": "B", "price": 1050, "total": 1050, "in_stock": True}
    out = signals.drip_pricing([cheap_sticker, cheap_total])
    assert out["flag"] is True and "B" in out["detail"]
    same = [{"seller": "A", "price": 1000, "total": 1000, "in_stock": True},
            {"seller": "B", "price": 1100, "total": 1100, "in_stock": True}]
    assert signals.drip_pricing(same)["flag"] is False
    assert signals.drip_pricing(same[:1])["flag"] is None


def test_conditional_savings_quotes_the_biggest_offer():
    listing = {"bank_offers": [
        {"title": "Cashback", "content": "Upto ₹41 cashback", "extracted_savings": 41},
        {"title": "Bank Offer", "content": "Upto ₹2,500 off on select cards", "extracted_savings": 2500}]}
    out = signals.conditional_savings(listing)
    assert out["flag"] is True and out["best_saving"] == 2500
    assert "2,500" in out["detail"]
    assert signals.conditional_savings({})["flag"] is False


def test_complaints_rank_by_share_and_skip_praise():
    reviews = {"summary": {"insights": [
        {"title": "Sound quality", "sentiment": "positive", "mentions": {"total": 100, "negative": 10}},
        {"title": "Reliability", "sentiment": "negative", "mentions": {"total": 30, "negative": 23}},
        {"title": "Connectivity", "sentiment": "mixed", "mentions": {"total": 100, "negative": 40}}]}}
    out = signals.buyer_complaints(reviews)
    assert [c["topic"] for c in out] == ["Reliability", "Connectivity"]
    assert out[0]["share"] == 0.77
    assert signals.buyer_complaints(None) == []


def test_report_counts_flags_and_ignores_amazons_own_offer():
    listing = {"mrp": 4490, "badges": ["Limited time deal"]}
    offers = [{"seller": "Amazon.in", "price": 1, "total": 1, "in_stock": True}]
    out = signals.report(listing, VERDICT, offers)
    assert out["flagged"] == 2                      # inflated reference + false urgency
    assert out["checks"]["drip_pricing"]["flag"] is None   # Amazon's own listing isn't evidence
