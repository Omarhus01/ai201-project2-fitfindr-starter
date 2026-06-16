"""
Isolation tests for agent._parse_query — the parser-robustness layer. Fully
offline: tools._chat is monkeypatched, no real Groq call ever happens.
"""

import json as _json

import pytest

import agent
import tools


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
