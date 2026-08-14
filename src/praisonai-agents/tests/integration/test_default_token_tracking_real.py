"""Opt-in real-provider coverage for default token collection."""

import os

import pytest


@pytest.mark.network
@pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason="Set RUN_REAL_KEY_TESTS=1 and OPENAI_API_KEY for the real agentic test",
)
def test_default_agent_start_records_real_provider_usage():
    from praisonaiagents import Agent
    from praisonaiagents.telemetry.token_collector import get_token_collector

    collector = get_token_collector()
    collector.reset()
    result = Agent(
        name="token-collector-real-smoke",
        instructions="Reply with the single word OK.",
        llm="gpt-4o-mini",
    ).start("Say OK")
    summary = collector.get_session_summary()

    print(result)
    print(summary)
    assert result
    assert summary["total_interactions"] >= 1
    assert summary["total_metrics"]["input_tokens"] > 0
    assert summary["total_metrics"]["output_tokens"] > 0
