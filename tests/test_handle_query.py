"""
Tests for app.handle_query — the UI-facing query handler. Patches app.run_agent,
so every test is fully offline and exercises only the panel-formatting logic.
"""

import pytest

import app

from _shared import _session


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


# ── Stretch 1: loosened note surfaces in the listing panel ────────────────────────

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


# ── Stretch 2: price-check line in the listing panel ──────────────────────────────

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
