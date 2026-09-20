from aslideal.verdict import Offer, judge, rupees


def offers(*prices, seller="Shop", in_stock=True):
    return [Offer(seller=f"{seller}{i}", price=p, in_stock=in_stock) for i, p in enumerate(prices)]


def test_discount_from_a_price_nobody_charges():
    v = judge(1399, 4490, offers(1399, 1399, 1599))
    assert v.kind == "reference_gap"
    assert v.street_price == 1399
    assert round(v.claimed_discount, 2) == 0.69
    assert "₹4,490" in v.headline and "69% off" in v.headline


def test_a_seller_charging_the_mrp_means_the_reference_is_real():
    v = judge(1399, 4490, offers(1399, 1399, 4490))
    assert v.mrp_charged_by == ["Shop2"]
    assert v.kind == "going_rate"


def test_real_saving_against_other_sellers():
    v = judge(3005, 4999, offers(3499, 3499, 3699, 3999))
    assert v.kind == "real_deal"
    assert v.street_price == 3599


def test_more_expensive_than_everyone_else_despite_the_label():
    v = judge(5499, 8999, offers(3999, 4199, 4299))
    assert v.kind == "above_market"
    assert "doesn't change that" in v.headline


def test_out_of_stock_and_amazon_listings_are_not_evidence():
    evidence = offers(4490, in_stock=False) + [Offer("amazon.in", 1399), Offer("Flipkart", 1399)]
    v = judge(1399, 4490, evidence)
    assert v.kind == "unverified"
    assert v.sellers_used == 0
    assert "out of stock" in v.notes[0]


def test_indian_number_grouping():
    assert rupees(1399) == "₹1,399"
    assert rupees(123456) == "₹1,23,456"
    assert rupees(12345678) == "₹1,23,45,678"


def test_two_sellers_who_disagree_have_no_street_price():
    v = judge(5499, 8999, offers(5499, 8999))
    assert v.kind == "unverified"
    assert "disagree" in v.headline
    # a third seller settles it
    assert judge(5499, 8999, offers(5499, 8999, 5599)).kind != "unverified"
    # two sellers who roughly agree are fine
    assert judge(3005, 4999, offers(3499, 3599)).kind == "real_deal"
