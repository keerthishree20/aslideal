from aslideal import history

LISTING = {"asin": "B0TEST00001", "price": 1399, "mrp": 4490}
VERDICT = {"claimed_discount": 0.69, "street_price": 1399, "real_discount": 0.0,
           "sellers_used": 2, "kind": "reference_gap"}


def test_one_entry_per_day_and_changes(tmp_path):
    f = tmp_path / "history.json"
    history.record(LISTING, VERDICT, path=f, today="2026-09-01")
    history.record(LISTING, VERDICT, path=f, today="2026-09-01")  # same day replaces
    days = history.record({**LISTING, "price": 1599}, {**VERDICT, "street_price": 1499}, path=f, today="2026-09-08")
    assert [d["date"] for d in days] == ["2026-09-01", "2026-09-08"]
    moved = history.changes(days)
    assert moved["price_change"] == 200 and moved["street_change"] == 100
    assert moved["since"] == "2026-09-01" and moved["readings"] == 2


def test_no_changes_from_a_single_reading(tmp_path):
    f = tmp_path / "history.json"
    days = history.record(LISTING, VERDICT, path=f, today="2026-09-01")
    assert history.changes(days) == {}


def test_missing_file_reads_as_empty(tmp_path):
    assert history.load(tmp_path / "nope.json") == {}
