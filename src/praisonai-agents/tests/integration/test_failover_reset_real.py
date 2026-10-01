"""Real agent turn after an explicit failover reset.

Run with RUN_REAL_KEY_TESTS=1 and OPENAI_API_KEY configured.
"""

import os

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_REAL_KEY_TESTS") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason="Set RUN_REAL_KEY_TESTS=1 and OPENAI_API_KEY for the real agentic test",
)


def test_agent_turn_uses_primary_after_reset():
    from praisonaiagents import Agent
    from praisonaiagents.llm.failover import AuthProfile, FailoverManager
    from praisonaiagents.llm.llm import LLM

    model = os.environ.get("PRAISONAI_TEST_MODEL", "gpt-4o-mini")
    manager = FailoverManager()
    primary = AuthProfile(
        name="primary",
        provider="openai",
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_BASE_URL"),
        model=model,
    )
    manager.add_profile(primary)
    manager.mark_failure(primary, "simulated rate limit", is_rate_limit=True)
    manager.reset_all()
    assert manager.get_next_profile() is primary
    assert primary.is_available

    agent = Agent(
        name="reset-smoke",
        instructions="Answer briefly.",
        llm=LLM(model=model, failover_manager=manager),
        output="silent",
    )
    result = agent.start("Say hello in one sentence.")
    print(result)
    assert isinstance(result, str) and result.strip()
