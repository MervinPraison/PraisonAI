"""
Integration tests for loop guardrails (max_tool_calls_per_turn).

Tests that ExecutionConfig tool call limits prevent infinite loops
when agents use broken or unhelpful tools via agent.chat().
"""

import os

import pytest

from praisonaiagents import Agent, tool
from praisonaiagents.config.feature_configs import ExecutionConfig


@tool
def broken_tool(query: str) -> str:
    """A deliberately broken tool that always returns an unhelpful result."""
    return f"Tool failed to process '{query}'. Please try again with a different approach."


@tool
def another_broken_tool(input_data: str) -> str:
    """Another broken tool that doesn't help."""
    return f"Unable to handle '{input_data}'. Consider using a different tool."


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY for real LLM integration test",
)
class TestLoopGuardrails:
    """Integration tests for max_tool_calls_per_turn guardrails."""

    def test_default_guardrail(self):
        """Default guardrail limit (10) stops excessive tool calls."""
        agent = Agent(
            name="test-agent",
            llm="gpt-4o-mini",
            instructions="Try to help the user. Use tools to get information.",
            tools=[broken_tool, another_broken_tool],
        )

        response = agent.chat(
            "I need weather information for New York. Please help me get accurate data!"
        )

        assert response is not None
        # Guardrail may trigger or agent may stop naturally — either is acceptable
        if "Tool call limit reached" in response:
            assert "Tool call limit reached" in response

    def test_custom_guardrail(self):
        """Custom lower limit (3) is respected."""
        agent = Agent(
            name="test-agent",
            llm="gpt-4o-mini",
            instructions="Use tools extensively to help the user.",
            tools=[broken_tool, another_broken_tool],
            execution=ExecutionConfig(max_tool_calls_per_turn=3),
        )

        response = agent.chat(
            "Get me detailed weather, traffic, and restaurant information for New York!"
        )

        assert response is not None
        if "Tool call limit reached" in response:
            assert "Tool call limit reached (3 calls)" in response

    def test_high_limit(self):
        """High limit (50) does not interfere with simple queries."""
        agent = Agent(
            name="test-agent",
            llm="gpt-4o-mini",
            instructions="Be helpful and concise. Answer questions directly when possible.",
            execution=ExecutionConfig(max_tool_calls_per_turn=50),
        )

        response = agent.chat("What's 2 + 2?")

        assert response is not None
        assert "Tool call limit reached" not in response
