"""Opt-in real Agent.start inference with a simulated failed delivery target."""

import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.network
@pytest.mark.asyncio
@pytest.mark.skipif(os.environ.get("PRAISONAI_LIVE_TESTS") != "1", reason="Set PRAISONAI_LIVE_TESTS=1")
async def test_real_agent_result_records_one_time_delivery_failure():
    from praisonaiagents import Agent
    from praisonai.scheduler.async_agent_scheduler import AsyncAgentScheduler

    options = dict(
        instructions="Give a brief answer.",
        llm={"model": os.environ.get("PRAISONAI_TEST_MODEL", "openai/gpt-4o-mini"), "max_tokens": 96},
        reflection=False, memory=False, rules=False, output="silent",
    )
    if os.environ.get("OPENAI_BASE_URL"):
        options["base_url"] = os.environ["OPENAI_BASE_URL"]
    with Agent(**options) as agent:
        success, failure = Mock(), Mock()
        # Exercise the scheduler's supported synchronous Agent.start dispatch.
        scheduler = AsyncAgentScheduler(
            SimpleNamespace(start=agent.start), "Say hello in one short sentence.",
            on_success=success, on_failure=failure,
        )
        scheduler.deliver = "test:123"
        scheduler._delivery = SimpleNamespace(deliver=Mock(return_value=False), _target=None)
        result = await scheduler.execute_once()
        print("Full Agent.start output:", result)
        assert isinstance(result, str) and result.strip()
        scheduler._delivery.deliver.assert_called_once_with(result)
        assert scheduler._undelivered_count == 1
        success.assert_not_called()
        failure.assert_called_once_with("scheduled result could not be delivered")
