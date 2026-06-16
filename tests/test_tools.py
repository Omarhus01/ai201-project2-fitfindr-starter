"""
Isolation tests for the FitFindr tools.

Phase 1 covers Tool 1 (search_listings) only. Every test here is fully offline —
search_listings is a pure function over local JSON with no LLM and no network.
"""

import pytest

import tools
from tools import search_listings, suggest_outfit, create_fit_card, compare_price
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

FIT_CARD_EMPTY_GUARD = "No outfit to caption yet — generate a styling idea first."
FIT_CARD_FALLBACK = (
    "Couldn't write a caption for this one right now — "
    "but it's a great find worth showing off."
)

FALLBACK_2 = (
    "Couldn't generate a full styling idea for this one — "
    "but it's a versatile piece worth grabbing."
)

# A minimal valid listing dict for the Tool 2 tests (no network — _chat is patched).
SAMPLE_ITEM = {
    "id": "lst_x", "title": "Vintage Band Tee", "description": "soft faded cotton",
    "category": "tops", "style_tags": ["vintage", "graphic tee"], "size": "M",
    "condition": "good", "price": 19.0, "colors": ["grey"], "brand": None,
    "platform": "depop",
}


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


# ── Tool 2: suggest_outfit (all offline — tools._chat is monkeypatched) ──────────

def test_suggest_outfit_llm_raises_returns_fallback(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("simulated API/timeout error")
    monkeypatch.setattr(tools, "_chat", boom)
    out = suggest_outfit(SAMPLE_ITEM, get_example_wardrobe())
    assert out == FALLBACK_2


def test_suggest_outfit_llm_empty_returns_fallback(monkeypatch):
    for empty in ("", "   \n\t ", None):
        monkeypatch.setattr(tools, "_chat", lambda *a, **k: empty)
        out = suggest_outfit(SAMPLE_ITEM, get_example_wardrobe())
        assert out == FALLBACK_2


def test_suggest_outfit_empty_wardrobe_takes_general_path(monkeypatch):
    captured = {}

    def stub(messages, temperature, max_tokens):
        captured["messages"] = messages
        return "general styling advice here"

    monkeypatch.setattr(tools, "_chat", stub)
    out = suggest_outfit(SAMPLE_ITEM, get_empty_wardrobe())
    assert out  # non-empty
    prompt = " ".join(m["content"] for m in captured["messages"])
    assert "the shopper hasn't added any wardrobe items" in prompt


def test_suggest_outfit_non_empty_wardrobe_names_real_pieces(monkeypatch):
    captured = {}

    def stub(messages, temperature, max_tokens):
        captured["messages"] = messages
        return "Outfit 1: wear it with the jeans."

    monkeypatch.setattr(tools, "_chat", stub)
    suggest_outfit(SAMPLE_ITEM, get_example_wardrobe())
    prompt = " ".join(m["content"] for m in captured["messages"])
    assert "Baggy straight-leg jeans" in prompt


def test_suggest_outfit_defensive_access_no_items_key(monkeypatch):
    monkeypatch.setattr(tools, "_chat", lambda *a, **k: "advice")
    # Wardrobe dict missing the "items" key must not raise (treated as empty).
    out = suggest_outfit(SAMPLE_ITEM, {"_note": "new user template"})
    assert isinstance(out, str) and out


# ── Tool 3: create_fit_card (all offline — tools._chat is monkeypatched) ─────────

OUTFIT = "Wear it with baggy jeans and chunky sneakers for an easy y2k look."


def test_fit_card_empty_outfit_guard_no_llm_call(monkeypatch):
    # Sentinel: if the guard fails to short-circuit and _chat is called, fail loudly.
    def sentinel(*args, **kwargs):
        pytest.fail("_chat must NOT be called when outfit is empty")
    monkeypatch.setattr(tools, "_chat", sentinel)
    for empty in ("", "   \n\t ", None):
        assert create_fit_card(empty, SAMPLE_ITEM) == FIT_CARD_EMPTY_GUARD


def test_fit_card_llm_raises_returns_fallback(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("simulated API/timeout error")
    monkeypatch.setattr(tools, "_chat", boom)
    assert create_fit_card(OUTFIT, SAMPLE_ITEM) == FIT_CARD_FALLBACK


def test_fit_card_llm_empty_returns_fallback(monkeypatch):
    for empty in ("", "   \n ", None):
        monkeypatch.setattr(tools, "_chat", lambda *a, **k: empty)
        assert create_fit_card(OUTFIT, SAMPLE_ITEM) == FIT_CARD_FALLBACK


def test_fit_card_prompt_content(monkeypatch):
    captured = {}

    def stub(messages, temperature, max_tokens):
        captured["messages"] = messages
        return "cute thrifted fit caption"

    monkeypatch.setattr(tools, "_chat", stub)
    item = dict(SAMPLE_ITEM, price=18.0, platform="depop", brand=None)
    create_fit_card(OUTFIT, item)
    prompt = " ".join(m["content"] for m in captured["messages"])
    assert "$18" in prompt and "$18.0" not in prompt
    assert "depop" in prompt
    # brand is None → must not appear anywhere in the prompt
    assert "Brand" not in prompt


# ── _parse_query (parser-robustness layer — patch tools._chat, fully offline) ────

import json as _json

import agent


def test_parse_valid_json_coerces_int_price(monkeypatch):
    raw = _json.dumps(
        {"description": "vintage tee", "size": "M", "max_price": 30, "in_scope": True}
    )
    monkeypatch.setattr(tools, "_chat", lambda *a, **k: raw)
    out = agent._parse_query("anything")
    assert out["description"] == "vintage tee"
    assert out["size"] == "M"
    assert out["max_price"] == 30.0
    assert isinstance(out["max_price"], float)  # int 30 coerced to float
    assert out["in_scope"] is True


def test_parse_empty_description_is_valid(monkeypatch):
    raw = _json.dumps(
        {"description": "", "size": None, "max_price": None, "in_scope": True}
    )
    monkeypatch.setattr(tools, "_chat", lambda *a, **k: raw)
    out = agent._parse_query("size M please")
    assert out["description"] == ""  # empty is valid, flows to no-results downstream


def test_parse_empty_size_coerced_to_none(monkeypatch):
    raw = _json.dumps(
        {"description": "tee", "size": "  ", "max_price": None, "in_scope": True}
    )
    monkeypatch.setattr(tools, "_chat", lambda *a, **k: raw)
    assert agent._parse_query("x")["size"] is None


def test_parse_malformed_json_raises_valueerror(monkeypatch):
    monkeypatch.setattr(tools, "_chat", lambda *a, **k: "not json at all {")
    with pytest.raises(ValueError):
        agent._parse_query("x")


def test_parse_missing_key_raises_valueerror(monkeypatch):
    raw = _json.dumps({"description": "tee", "size": None, "max_price": None})  # no in_scope
    monkeypatch.setattr(tools, "_chat", lambda *a, **k: raw)
    with pytest.raises(ValueError):
        agent._parse_query("x")


def test_parse_wrong_types_raise_valueerror(monkeypatch):
    bad_payloads = [
        {"description": "tee", "size": None, "max_price": "cheap", "in_scope": True},
        {"description": "tee", "size": None, "max_price": None, "in_scope": "true"},
        {"description": "tee", "size": None, "max_price": True, "in_scope": True},  # bool price
        {"description": 123, "size": None, "max_price": None, "in_scope": True},
    ]
    for payload in bad_payloads:
        monkeypatch.setattr(tools, "_chat", lambda *a, _p=payload, **k: _json.dumps(_p))
        with pytest.raises(ValueError):
            agent._parse_query("x")


def test_parse_service_error_is_not_valueerror(monkeypatch):
    class FakeGroqError(Exception):
        pass

    def boom(*args, **kwargs):
        raise FakeGroqError("connection reset")

    monkeypatch.setattr(tools, "_chat", boom)
    with pytest.raises(Exception) as excinfo:
        agent._parse_query("x")
    assert not isinstance(excinfo.value, ValueError)  # must stay distinguishable from 1a


# ── run_agent (loop-branching layer — patch agent._parse_query + tools.* — offline) ─

from agent import run_agent

ONE_A = (
    "I couldn't read that request — try naming an item, a size, or a price, "
    "e.g. 'vintage denim jacket size M under $40.'"
)
SERVICE_ERROR = (
    "FitFindr is having trouble reaching its service right now — "
    "please try again in a moment."
)
ONE_B = (
    "FitFindr only helps find and style secondhand clothing. Tell me what you're "
    "after — for example, 'vintage denim jacket, size M, under $40' — and I'll dig "
    "something up."
)


def _scope(in_scope=True, description="vintage graphic tee", size=None, max_price=30.0):
    return {
        "description": description, "size": size,
        "max_price": max_price, "in_scope": in_scope,
    }


def test_run_agent_happy_path_state_flow(monkeypatch):
    fake_item = dict(SAMPLE_ITEM, title="Top Result Tee")
    calls = {}

    def fake_suggest(new_item, wardrobe, style_note=None):
        calls["suggest_args"] = (new_item, wardrobe)
        return "OUTFIT SUGGESTION"

    def fake_card(outfit, new_item):
        calls["card_args"] = (outfit, new_item)
        return "FIT CARD"

    monkeypatch.setattr(agent, "_parse_query", lambda q: _scope())
    monkeypatch.setattr(tools, "search_listings", lambda d, s, m: [fake_item])
    monkeypatch.setattr(tools, "suggest_outfit", fake_suggest)
    monkeypatch.setattr(tools, "create_fit_card", fake_card)

    wardrobe = {"items": [{"name": "thing"}]}
    session = run_agent("vintage graphic tee under $30", wardrobe)

    # All keys populated, no error, both LLM tools were called.
    assert session["error"] is None
    assert session["selected_item"] is fake_item
    assert session["outfit_suggestion"] == "OUTFIT SUGGESTION"
    assert session["fit_card"] == "FIT CARD"
    assert "suggest_args" in calls and "card_args" in calls

    # State-identity (`is`, not ==): the exact objects flowed through, no re-entry.
    assert calls["suggest_args"][0] is session["selected_item"]
    assert calls["suggest_args"][1] is session["wardrobe"]
    assert calls["card_args"][0] is session["outfit_suggestion"]
    assert calls["card_args"][1] is session["selected_item"]


def test_run_agent_no_results_does_not_call_suggest(monkeypatch):
    def sentinel(*args, **kwargs):
        pytest.fail("suggest_outfit/create_fit_card must NOT be called on no-results")

    monkeypatch.setattr(agent, "_parse_query", lambda q: _scope(description="designer ballgown"))
    monkeypatch.setattr(tools, "search_listings", lambda d, s, m: [])
    monkeypatch.setattr(tools, "suggest_outfit", sentinel)
    monkeypatch.setattr(tools, "create_fit_card", sentinel)

    session = run_agent("designer ballgown under $30", get_example_wardrobe())

    assert session["error"] is not None
    assert "designer ballgown" in session["error"]
    assert "Try removing" in session["error"]
    assert session["search_results"] == []
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None


def test_run_agent_out_of_scope_never_searches(monkeypatch):
    def sentinel(*args, **kwargs):
        pytest.fail("search_listings must NOT be called when out of scope")

    monkeypatch.setattr(agent, "_parse_query", lambda q: _scope(in_scope=False, description=""))
    monkeypatch.setattr(tools, "search_listings", sentinel)

    session = run_agent("what's the capital of France", get_example_wardrobe())
    assert session["error"] == ONE_B
    assert session["search_results"] == []
    assert session["fit_card"] is None


def test_run_agent_parse_fail_is_1a(monkeypatch):
    def boom(q):
        raise ValueError("bad json")

    monkeypatch.setattr(agent, "_parse_query", boom)
    monkeypatch.setattr(
        tools, "search_listings",
        lambda *a, **k: pytest.fail("no tools on parse failure"),
    )
    session = run_agent("???", get_example_wardrobe())
    assert session["error"] == ONE_A


def test_run_agent_service_error_distinct_from_1a(monkeypatch):
    def boom(q):
        raise ConnectionError("groq down")

    monkeypatch.setattr(agent, "_parse_query", boom)
    session = run_agent("vintage tee", get_example_wardrobe())
    assert session["error"] == SERVICE_ERROR
    assert session["error"] != ONE_A


# ── handle_query (app layer — patch app.run_agent — fully offline) ───────────────

import app


def _session(**overrides):
    base = {
        "query": "", "parsed": {}, "search_results": [], "selected_item": None,
        "wardrobe": {}, "outfit_suggestion": None, "fit_card": None, "error": None,
        "loosened": None, "price_check": None,
    }
    base.update(overrides)
    return base


def test_handle_query_empty_guard_does_not_run_agent(monkeypatch):
    monkeypatch.setattr(app, "run_agent", lambda *a, **k: pytest.fail("run_agent must not run"))
    for q in ("", "   \n "):
        panel1, panel2, panel3 = app.handle_query(q, "Example wardrobe")
        assert panel1 == "Please enter what you're looking for."
        assert panel2 == "" and panel3 == ""


def test_handle_query_error_path(monkeypatch):
    monkeypatch.setattr(app, "run_agent", lambda q, w, s=None: _session(error="some error message"))
    panel1, panel2, panel3 = app.handle_query("anything", "Example wardrobe")
    assert panel1 == "some error message"
    assert panel2 == "" and panel3 == ""


def test_handle_query_happy_path_listing_format(monkeypatch):
    item = {
        "title": "Y2K Baby Tee — Butterfly Print", "price": 18.0,
        "platform": "depop", "condition": "excellent",
    }
    full = _session(
        selected_item=item,
        outfit_suggestion="wear it with jeans",
        fit_card="cute thrifted fit",
    )
    monkeypatch.setattr(app, "run_agent", lambda q, w, s=None: full)
    panel1, panel2, panel3 = app.handle_query("vintage graphic tee", "Example wardrobe")
    assert panel1 == "Y2K Baby Tee — Butterfly Print — $18, depop, excellent condition"
    assert panel2 == "wear it with jeans"
    assert panel3 == "cute thrifted fit"


# ── Stretch 1: retry with loosened size filter (run_agent layer, offline) ────────

def test_run_agent_retry_succeeds_drops_size(monkeypatch):
    fake_item = dict(SAMPLE_ITEM, title="Found Without Size")
    calls = []

    def fake_search(description, size, max_price):
        calls.append((description, size, max_price))
        if size is not None:
            return []
        return [fake_item]

    monkeypatch.setattr(agent, "_parse_query", lambda q: _scope(size="L"))
    monkeypatch.setattr(tools, "search_listings", fake_search)
    monkeypatch.setattr(tools, "suggest_outfit", lambda i, w, style_note=None: "OUTFIT")
    monkeypatch.setattr(tools, "create_fit_card", lambda o, i: "CARD")

    session = run_agent("vintage graphic tee size L under $30", get_example_wardrobe())

    assert calls == [("vintage graphic tee", "L", 30.0), ("vintage graphic tee", None, 30.0)]
    assert session["loosened"] == "size filter (L)"
    assert session["error"] is None
    assert session["selected_item"] is fake_item
    assert session["outfit_suggestion"] == "OUTFIT"
    assert session["fit_card"] == "CARD"


def test_run_agent_retry_also_empty_errors_no_suggest(monkeypatch):
    def sentinel(*args, **kwargs):
        pytest.fail("suggest_outfit must NOT be called when both attempts are empty")

    monkeypatch.setattr(agent, "_parse_query", lambda q: _scope(size="L"))
    monkeypatch.setattr(tools, "search_listings", lambda d, s, m: [])
    monkeypatch.setattr(tools, "suggest_outfit", sentinel)
    monkeypatch.setattr(tools, "create_fit_card", sentinel)

    session = run_agent("vintage graphic tee size L under $30", get_example_wardrobe())

    assert session["error"] is not None
    assert session["loosened"] is None
    assert session["selected_item"] is None


def test_run_agent_no_size_does_not_retry(monkeypatch):
    calls = []

    def fake_search(description, size, max_price):
        calls.append((description, size, max_price))
        return []

    def sentinel(*args, **kwargs):
        pytest.fail("suggest_outfit must NOT be called on no-results")

    monkeypatch.setattr(agent, "_parse_query", lambda q: _scope(size=None))
    monkeypatch.setattr(tools, "search_listings", fake_search)
    monkeypatch.setattr(tools, "suggest_outfit", sentinel)
    monkeypatch.setattr(tools, "create_fit_card", sentinel)

    session = run_agent("designer ballgown under $30", get_example_wardrobe())

    assert len(calls) == 1  # search_listings called ONCE — nothing to loosen
    assert session["error"] is not None
    assert session["loosened"] is None


# ── Stretch 1: loosened note surfaces in app.py's listing panel ──────────────────

# ── Stretch 2: compare_price (4th tool, pure function, no network) ───────────────

def _real_item(title_substring):
    for listing in tools.load_listings():
        if title_substring in listing["title"]:
            return listing
    raise AssertionError(f"no listing found containing {title_substring!r}")


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


def test_compare_price_loop_integration_sets_price_check(monkeypatch):
    fake_item = dict(SAMPLE_ITEM)

    monkeypatch.setattr(agent, "_parse_query", lambda q: _scope())
    monkeypatch.setattr(tools, "search_listings", lambda d, s, m: [fake_item])
    monkeypatch.setattr(tools, "suggest_outfit", lambda i, w, style_note=None: "OUTFIT")
    monkeypatch.setattr(tools, "create_fit_card", lambda o, i: "CARD")

    session = run_agent("vintage graphic tee under $30", get_example_wardrobe())

    assert session["price_check"] is not None
    assert session["price_check"]["verdict"] in {"good deal", "fair", "high", "insufficient data"}
    # non-blocking: the rest of the flow still completed regardless of the verdict
    assert session["outfit_suggestion"] == "OUTFIT"
    assert session["fit_card"] == "CARD"


def test_compare_price_insufficient_data_does_not_block_flow(monkeypatch):
    fake_item = {"id": "lst_unique", "title": "One-Off Item", "category": "one_of_a_kind", "price": 50.0}

    monkeypatch.setattr(agent, "_parse_query", lambda q: _scope())
    monkeypatch.setattr(tools, "search_listings", lambda d, s, m: [fake_item])
    monkeypatch.setattr(tools, "suggest_outfit", lambda i, w, style_note=None: "OUTFIT")
    monkeypatch.setattr(tools, "create_fit_card", lambda o, i: "CARD")

    session = run_agent("one off item", get_example_wardrobe())

    assert session["price_check"]["verdict"] == "insufficient data"
    assert session["error"] is None
    assert session["outfit_suggestion"] == "OUTFIT"
    assert session["fit_card"] == "CARD"


def test_handle_query_price_check_line_shown_when_sufficient(monkeypatch):
    item = {
        "title": "Mesh Long-Sleeve Top", "price": 15.0,
        "platform": "depop", "condition": "good", "category": "tops",
    }
    full = _session(
        selected_item=item,
        outfit_suggestion="wear it with jeans",
        fit_card="cute thrifted fit",
        price_check={"verdict": "good deal", "item_price": 15.0, "median_comparable": 21.0, "n_comparable": 14},
    )
    monkeypatch.setattr(app, "run_agent", lambda q, w, s=None: full)
    panel1, _, _ = app.handle_query("mesh top", "Example wardrobe")
    assert "Price check: good deal ($15 vs $21 median for tops)" in panel1


def test_handle_query_price_check_line_omitted_when_insufficient(monkeypatch):
    item = {
        "title": "One-Off Item", "price": 50.0,
        "platform": "depop", "condition": "good", "category": "one_of_a_kind",
    }
    full = _session(
        selected_item=item,
        outfit_suggestion="wear it with jeans",
        fit_card="cute thrifted fit",
        price_check={"verdict": "insufficient data", "item_price": 50.0, "median_comparable": None, "n_comparable": 0},
    )
    monkeypatch.setattr(app, "run_agent", lambda q, w, s=None: full)
    panel1, _, _ = app.handle_query("one off item", "Example wardrobe")
    assert "Price check" not in panel1


def test_handle_query_shows_loosened_note(monkeypatch):
    item = {
        "title": "Vintage Polo Shirt — Forest Green", "price": 18.0,
        "platform": "depop", "condition": "good",
    }
    full = _session(
        selected_item=item,
        outfit_suggestion="wear it with jeans",
        fit_card="cute thrifted fit",
        loosened="size filter (L)",
    )
    monkeypatch.setattr(app, "run_agent", lambda q, w, s=None: full)
    panel1, _, _ = app.handle_query("vintage polo shirt size L", "Example wardrobe")
    assert panel1.startswith("No exact size match — showing results without the size filter.\n")


# ── Stretch 4: style profile persistence (utils/profile.py, offline, tmp_path only) ──

from utils.profile import load_profile, save_profile


def test_profile_save_then_load_round_trips(tmp_path):
    path = tmp_path / "style_profile.json"
    profile = {"wardrobe_choice": "Example wardrobe", "style_note": "I like y2k and grunge"}
    save_profile(profile, path=str(path))
    assert load_profile(path=str(path)) == profile


def test_profile_missing_file_returns_none(tmp_path):
    path = tmp_path / "does_not_exist.json"
    assert load_profile(path=str(path)) is None


def test_profile_corrupt_file_returns_none_no_exception(tmp_path):
    path = tmp_path / "style_profile.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert load_profile(path=str(path)) is None


# ── Stretch 4: style_note threaded into suggest_outfit (offline, _chat patched) ──

def test_suggest_outfit_style_note_appears_in_prompt(monkeypatch):
    captured = {}

    def stub(messages, temperature, max_tokens):
        captured["messages"] = messages
        return "styled with the note in mind"

    monkeypatch.setattr(tools, "_chat", stub)
    suggest_outfit(SAMPLE_ITEM, get_example_wardrobe(), style_note="I like y2k and grunge")
    prompt = " ".join(m["content"] for m in captured["messages"])
    assert "I like y2k and grunge" in prompt


def test_suggest_outfit_without_style_note_unchanged(monkeypatch):
    captured = {}

    def stub(messages, temperature, max_tokens):
        captured["messages"] = messages
        return "Outfit 1: wear it with the jeans."

    monkeypatch.setattr(tools, "_chat", stub)
    # No third argument — exercises the back-compat default (style_note=None).
    out = suggest_outfit(SAMPLE_ITEM, get_example_wardrobe())
    assert out == "Outfit 1: wear it with the jeans."
    prompt = " ".join(m["content"] for m in captured["messages"])
    assert "style preference" not in prompt
