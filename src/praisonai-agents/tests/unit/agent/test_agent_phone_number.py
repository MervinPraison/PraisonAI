"""Tests for assigning a phone number to an agent (Issue #2859).

The core ``Agent`` accepts an optional ``phone_number`` identity attribute so an
agent can be assigned a contact number (used by channel/bot layers such as
WhatsApp/SMS for routing). This is a lightweight string attribute — no config
object, no new dependencies.
"""

from __future__ import annotations

import inspect

from praisonaiagents import Agent


class TestAgentPhoneNumber:
    def test_init_accepts_phone_number(self):
        """`Agent.__init__` must expose a `phone_number=` parameter."""
        sig = inspect.signature(Agent.__init__)
        assert "phone_number" in sig.parameters

    def test_phone_number_assigned(self):
        agent = Agent(name="support", instructions="Be helpful", phone_number="+14155550123")
        assert agent.phone_number == "+14155550123"

    def test_phone_number_defaults_to_none(self):
        agent = Agent(name="support", instructions="Be helpful")
        assert agent.phone_number is None

    def test_phone_number_whitespace_stripped(self):
        agent = Agent(name="support", instructions="Be helpful", phone_number="  +14155550123  ")
        assert agent.phone_number == "+14155550123"

    def test_blank_phone_number_normalised_to_none(self):
        agent = Agent(name="support", instructions="Be helpful", phone_number="   ")
        assert agent.phone_number is None

    def test_phone_number_preserved_on_channel_clone(self):
        agent = Agent(name="support", instructions="Be helpful", phone_number="+14155550123")
        clone = agent.clone_for_channel()
        assert clone.phone_number == "+14155550123"


def test_agent_with_phone_number_runs_real_llm():
    """Real agentic test — agent with an assigned phone number runs end-to-end.

    Skips gracefully when no LLM API key is configured so unit runs stay
    deterministic and offline-safe.
    """
    import os

    if not os.environ.get("OPENAI_API_KEY"):
        import pytest

        pytest.skip("OPENAI_API_KEY not set; skipping real agentic test")

    agent = Agent(
        name="support",
        instructions="You are a helpful assistant.",
        phone_number="+14155550123",
    )
    result = agent.start("Say hello in one short sentence.")
    print("Real agentic output:", result)
    assert result
    assert agent.phone_number == "+14155550123"
