"""
Isolation tests for Tool 4 (Stretch 2): compare_price. Pure function over local
JSON, no LLM, no network.
"""

import tools
from tools import compare_price

from _shared import _real_item


def test_compare_price_good_deal_real_data():
    # Mesh Long-Sleeve Top: $15 vs the OTHER 14 tops' median $21.5 (-30.2%) — well below
    # threshold. The comparable set excludes the item itself, so the median is taken over
    # the other 14 tops, not all 15.
    item = _real_item("Mesh Long-Sleeve Top")
    result = compare_price(item)
    assert result["verdict"] == "good deal"
    assert result["item_price"] == 15.0
    assert result["median_comparable"] == 21.5
    assert result["n_comparable"] == 14  # 15 tops minus the item itself


def test_compare_price_high_real_data():
    # Knit Cardigan: $35 vs the other 14 tops' median $20.5 (+70.7%) — well above threshold.
    item = _real_item("Knit Cardigan")
    result = compare_price(item)
    assert result["verdict"] == "high"
    assert result["item_price"] == 35.0
    assert result["median_comparable"] == 20.5


def test_compare_price_fair_real_data():
    # Vintage Band Tee: $19 vs the other 14 tops' median $21.5 (-11.6%) — inside the band.
    item = _real_item("Vintage Band Tee")
    result = compare_price(item)
    assert result["verdict"] == "fair"
    assert result["item_price"] == 19.0
    assert result["median_comparable"] == 21.5


def test_compare_price_insufficient_data_few_comparables(monkeypatch):
    fake_listings = [
        {"id": "a", "category": "hats", "price": 10.0},
        {"id": "b", "category": "tops", "price": 20.0},
    ]
    monkeypatch.setattr(tools, "load_listings", lambda: fake_listings)
    item = {"id": "a", "category": "hats", "price": 10.0}  # only 1 in category, 0 comparables
    result = compare_price(item)
    assert result["verdict"] == "insufficient data"
    assert result["n_comparable"] == 0
    assert result["median_comparable"] is None
    assert result["item_price"] == 10.0


def test_compare_price_never_raises_on_bad_input():
    for bad in ({}, {"category": "tops"}, {"price": "not a number", "category": "tops"},
                {"price": None, "category": "tops"}, None, "not a dict", 42):
        result = compare_price(bad)
        assert result["verdict"] == "insufficient data"
