"""
Isolation tests for Tool 2: suggest_outfit. Fully offline — tools._chat is
monkeypatched, so no LLM call ever leaves the process.
"""

import tools
from tools import suggest_outfit
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

from _shared import SAMPLE_ITEM, FALLBACK_2


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


# ── Stretch 4: style_note threaded into suggest_outfit ────────────────────────────

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
