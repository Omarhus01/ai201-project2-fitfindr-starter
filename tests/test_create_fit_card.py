"""
Isolation tests for Tool 3: create_fit_card. Fully offline — tools._chat is
monkeypatched, so no LLM call ever leaves the process.
"""

import pytest

import tools
from tools import create_fit_card

from _shared import SAMPLE_ITEM, OUTFIT, FIT_CARD_EMPTY_GUARD, FIT_CARD_FALLBACK


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
