"""Opt-in real-provider coverage for streamed tool dispatch."""

import os

import pytest


@pytest.mark.network
@pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason="Set RUN_REAL_KEY_TESTS=1 and OPENAI_API_KEY for the real agentic test",
)
def test_real_agent_dispatches_tool_while_streaming():
    from praisonaiagents import Agent

    calls = []

    def stream_lookup(code: str) -> str:
        """Return a stable value for the requested lookup code."""
        calls.append(code)
        return f"stream-result:{code}"

    agent = Agent(
        name="stream-tool-real-smoke",
        llm="gpt-4o-mini",
        instructions=(
            "Always call stream_lookup exactly once before answering. "
            "After the tool call, reply with the exact marker "
            "STREAM-FOLLOW-UP-COMPLETE and include the tool's complete "
            "result in the final answer."
        ),
        tools=[stream_lookup],
    )

    chunks = agent.start(
        "Call stream_lookup with code NEBULA-7 and report its result.",
        stream=True,
    )
    result = "".join(str(chunk) for chunk in chunks if chunk)

    print(result)
    assert calls == ["NEBULA-7"]
    assert "STREAM-FOLLOW-UP-COMPLETE" in result
    assert "stream-result:NEBULA-7" in result
