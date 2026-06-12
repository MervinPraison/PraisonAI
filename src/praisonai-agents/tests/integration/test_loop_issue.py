"""
Integration test for agent.chat() loop vulnerability with broken tools.

Verifies that agent.chat() does not make excessive tool calls when tools
return unhelpful results (regression test for infinite-loop guardrails).
"""

import os

import pytest

from praisonaiagents import Agent, tool


@tool
def broken_weather_tool(location: str) -> str:
    """Get weather information for a location. Intentionally unhelpful."""
    return f"Weather data unavailable for {location}. Please try again with a different tool."


@tool
def another_broken_tool(query: str) -> str:
    """Search for information. Also broken and unhelpful."""
    return f"No results found for '{query}'. Please try a different search."


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY for real LLM integration test",
)
class TestAgentChatLoopIssue:
    """Regression test for excessive tool-call loops in agent.chat()."""

    def test_loop_vulnerability_resolved(self):
        """Agent should not make excessive tool calls with broken tools."""
        agent = Agent(
            name="test-agent",
            llm="gpt-4o-mini",
            instructions=(
                "You are a helpful assistant. Always try to fulfil user requests "
                "using available tools."
            ),
            tools=[broken_weather_tool, another_broken_tool],
        )

        call_count = 0
        original_execute_tool = agent.execute_tool

        def counting_execute_tool(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 10:
                raise RuntimeError("Safety valve triggered: too many tool calls")
            return original_execute_tool(*args, **kwargs)

        agent.execute_tool = counting_execute_tool

        response = agent.chat(
            "What's the weather like in New York? I really need this information!"
        )

        assert response is not None
        assert call_count <= 5, (
            f"Agent made {call_count} tool calls — guardrails may not be working"
        )
