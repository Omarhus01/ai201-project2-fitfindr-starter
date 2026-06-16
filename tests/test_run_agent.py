"""
Tests for the run_agent planning loop (agent.py) — the loop-branching layer.
Patches agent._parse_query and tools.* so every test is fully offline.

Covers: the baseline branches (1a parse-fail, 1b out-of-scope, 2a no-results, the
happy path), Stretch 1's retry-with-loosened-size-filter branch, and Stretch 2's
non-blocking compare_price enrichment.
"""

import pytest

import agent
import tools
from agent import run_agent
from utils.data_loader import get_example_wardrobe

from _shared import SAMPLE_ITEM, ONE_A, ONE_B, SERVICE_ERROR, _scope


# ── baseline branches: happy path, 2a no-results, 1b out-of-scope, 1a / service error ─

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


# ── Stretch 1: retry with loosened size filter ────────────────────────────────────

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


# ── Stretch 2: compare_price wired in as a non-blocking enrichment ────────────────

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
