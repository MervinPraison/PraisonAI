"""Opt-in timed-tool and Agent.start check with real model inference.

Set PRAISONAI_LIVE_TESTS=1 and configure an OpenAI-compatible provider.
PRAISONAI_TEST_MODEL and OPENAI_BASE_URL may point at a local model.
"""

import os

import pytest


@pytest.mark.live
def test_real_agent_uses_result_from_timed_tool():
    from praisonaiagents import Agent
    from praisonaiagents.config import ToolConfig

    def lookup_code() -> str:
        """Return the verification code."""
        return "AMBER58129"

    options = dict(
        name="TimedToolVerification",
        instructions="Follow the request exactly and give only the answer.",
        llm={
            "model": os.environ.get("PRAISONAI_TEST_MODEL", "openai/gpt-4o-mini"),
            "temperature": 0,
            "max_tokens": 96,
        },
        tools=[lookup_code],
        tool_config=ToolConfig(timeout=10),
        reflection=False,
        memory=False,
        rules=False,
        output="silent",
    )
    if os.environ.get("OPENAI_BASE_URL"):
        options["base_url"] = os.environ["OPENAI_BASE_URL"]

    with Agent(**options) as agent:
        code = agent._execute_tool_with_context("lookup_code", {}, None)
        assert code == "AMBER58129"
        assert agent._tool_executor is not None
        response = agent.start(f"The tool returned {code}. Repeat that code exactly, with no other words.")
        print("Full Agent.start output:", response)
        assert isinstance(response, str) and code.casefold() in response.casefold()
