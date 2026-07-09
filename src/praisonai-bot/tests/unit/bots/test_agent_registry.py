"""Tests for the phone-number -> agent routing registry (Issue #2859).

Assigning a phone number to an agent is a gateway/channel concern: inbound
WhatsApp/SMS messages are routed to the agent responsible for that number. The
mapping lives in the bot layer (``AgentRegistry``), not on the core ``Agent``.
"""

from __future__ import annotations

import pytest

from praisonai_bot.bots import AgentRegistry, normalize_number


class _FakeAgent:
    def __init__(self, name: str) -> None:
        self.name = name


class TestNormalizeNumber:
    def test_strips_formatting_and_preserves_plus(self):
        assert normalize_number("+1 (415) 555-0123") == "+14155550123"

    def test_already_canonical(self):
        assert normalize_number("+14155550123") == "+14155550123"

    def test_no_plus_preserved_as_digits(self):
        assert normalize_number("020 7183 8750") == "02071838750"

    def test_blank_and_none_normalise_to_none(self):
        assert normalize_number("   ") is None
        assert normalize_number("") is None
        assert normalize_number(None) is None

    def test_non_string_is_none(self):
        assert normalize_number(1234) is None


class TestAgentRegistry:
    def test_assign_and_resolve(self):
        agent = _FakeAgent("support")
        reg = AgentRegistry()
        reg.assign("+14155550123", agent)
        assert reg.resolve("+14155550123") is agent

    def test_resolve_ignores_formatting(self):
        agent = _FakeAgent("support")
        reg = AgentRegistry()
        reg.assign("+1 (415) 555-0123", agent)
        assert reg.resolve("+14155550123") is agent

    def test_unknown_number_returns_none(self):
        reg = AgentRegistry()
        assert reg.resolve("+14155550123") is None

    def test_default_agent_fallback(self):
        fallback = _FakeAgent("default")
        reg = AgentRegistry(default_agent=fallback)
        assert reg.resolve("+19998887777") is fallback

    def test_specific_beats_default(self):
        fallback = _FakeAgent("default")
        support = _FakeAgent("support")
        reg = AgentRegistry(default_agent=fallback)
        reg.assign("+14155550123", support)
        assert reg.resolve("+14155550123") is support
        assert reg.resolve("+19998887777") is fallback

    def test_reassign_replaces_agent(self):
        a = _FakeAgent("a")
        b = _FakeAgent("b")
        reg = AgentRegistry()
        reg.assign("+14155550123", a)
        reg.assign("+14155550123", b)
        assert reg.resolve("+14155550123") is b
        assert len(reg) == 1

    def test_unassign(self):
        reg = AgentRegistry()
        reg.assign("+14155550123", _FakeAgent("a"))
        assert reg.unassign("+1 415 555 0123") is True
        assert reg.resolve("+14155550123") is None
        assert reg.unassign("+14155550123") is False

    def test_invalid_number_raises(self):
        reg = AgentRegistry()
        with pytest.raises(ValueError):
            reg.assign("   ", _FakeAgent("a"))

    def test_contains_len_and_iter(self):
        a = _FakeAgent("a")
        reg = AgentRegistry()
        reg.assign("+14155550123", a)
        assert "+1 (415) 555-0123" in reg
        assert "+19998887777" not in reg
        assert len(reg) == 1
        assert dict(reg) == {"+14155550123": a}

    def test_numbers(self):
        reg = AgentRegistry()
        reg.assign("+14155550123", _FakeAgent("a"))
        reg.assign("+442071838750", _FakeAgent("b"))
        assert sorted(reg.numbers()) == ["+14155550123", "+442071838750"]


def test_registry_routes_real_agents():
    """Integration: real ``Agent`` instances resolve by phone number.

    No LLM call is made — this only exercises construction + routing, so it is
    offline-safe and needs no API key.
    """
    try:
        from praisonaiagents import Agent
    except Exception:  # pragma: no cover - optional dep missing
        pytest.skip("praisonaiagents not importable")

    support = Agent(name="support", instructions="Be helpful")
    sales = Agent(name="sales", instructions="Sell things")

    reg = AgentRegistry()
    reg.assign("+14155550123", support)
    reg.assign("+442071838750", sales)

    assert reg.resolve("+1 415 555 0123") is support
    assert reg.resolve("+44 20 7183 8750") is sales
    assert reg.resolve("+10000000000") is None
