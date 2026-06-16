"""
Isolation tests for Tool 1: search_listings. Fully offline — it's a pure function
over local JSON with no LLM and no network.
"""

from tools import search_listings


# ── starter tests (from the milestone, kept as-is) ──────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []  # empty list, no exception


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


# ── real price filter (non-vacuous: must return results AND respect the ceiling) ──

def test_price_filter_returns_results_under_ceiling():
    results = search_listings("vintage graphic tee", size=None, max_price=25)
    assert len(results) > 0
    assert all(item["price"] <= 25 for item in results)


# ── size token-equality (ALL/subset rule) ───────────────────────────────────────

def test_size_us8_excludes_us85():
    results = search_listings("sneakers", size="US 8", max_price=None)
    sizes = {item["size"] for item in results}
    # Every result must carry the US 8 token set; US 8.5 must never appear.
    assert "US 8.5" not in sizes
    assert all(item["size"] == "US 8" or "One Size" in item["size"] for item in results)


def test_size_L_excludes_XL():
    results = search_listings("jacket", size="L", max_price=None)
    sizes = {item["size"] for item in results}
    assert "XL" not in sizes
    assert "W30 L30" not in sizes


# ── One Size inclusion ───────────────────────────────────────────────────────────

def test_size_query_includes_one_size():
    # A specific-size query must still surface One Size items (they fit any size).
    results = search_listings("bag", size="M", max_price=None)
    assert any("One Size" in item["size"] for item in results)


# ── head-noun gate (pure: head noun absent from the dataset → []) ────────────────

def test_head_noun_gate_midi_skirt_empty():
    assert search_listings("flowy midi skirt", size=None, max_price=None) == []


def test_head_noun_gate_ballgown_empty():
    assert search_listings("designer ballgown", size=None, max_price=None) == []


# ── size filter (relabeled — NOT a head-noun test; "boots" exists in the data) ───

def test_combat_boots_size_us8_empty():
    # "boots" exists (Suede Chelsea Boots, US 8.5), so this is empty because the
    # US 8 size filter excludes the only boots, not because of the head-noun gate.
    assert search_listings("combat boots", size="US 8", max_price=None) == []


# ── empty description ────────────────────────────────────────────────────────────

def test_empty_description_returns_empty():
    assert search_listings("", None, None) == []


# ── happy path: correct sort (score desc, then condition, then price asc) ────────

def test_happy_path_sorted_and_top_result():
    results = search_listings("vintage graphic tee", size=None, max_price=30)
    assert len(results) > 0
    # Top result is the Y2K Baby Tee (score 3, excellent, $18) per the walkthrough.
    assert results[0]["title"].startswith("Y2K Baby Tee")
    # Verify the sort key is non-increasing across the list.
    rank = {"excellent": 3, "good": 2, "fair": 1}

    def score_of(item):
        combined = " ".join([
            item["title"], item["description"], " ".join(item["style_tags"]),
            item["category"], " ".join(item["colors"]),
        ]).lower()
        import re
        toks = set(re.findall(r"[a-z0-9]+", combined))
        return sum(1 for t in {"vintage", "graphic", "tee"} if t in toks)

    keys = [(-score_of(i), -rank[i["condition"]], i["price"]) for i in results]
    assert keys == sorted(keys)
