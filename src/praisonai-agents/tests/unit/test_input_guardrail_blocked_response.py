"""Rejected input has the same fixed string contract as rejected output."""
import asyncio

import pytest

from praisonaiagents import Agent


class RejectInput:
    """Reject input before model dispatch with a diagnostic-only reason."""

    def validate_input(self, content, **kwargs):
        return False, "synthetic validator diagnostic"

    def validate_output(self, content, **kwargs):
        return True, content


@pytest.mark.parametrize("entry", ["chat", "achat", "start", "stream"])
def test_rejected_input_returns_fixed_guardrail_message(entry):
    """All public entry points return usable text, not None or diagnostics."""
    agent = Agent(name="T", instructions="test", llm="gpt-4o-mini", guardrails=RejectInput())
    expected = agent._guardrail_blocked_message()
    if entry == "achat":
        result = asyncio.run(agent.achat("blocked prompt"))
    elif entry == "stream":
        result = "".join(agent.start("blocked prompt", stream=True))
    else:
        result = getattr(agent, entry)("blocked prompt")
    assert result == expected
    assert result.strip()
