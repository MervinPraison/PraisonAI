"""One-time async runs must account for delivery and invoke the right callback."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from praisonai.scheduler.async_agent_scheduler import AsyncAgentScheduler

pytestmark = [pytest.mark.offline, pytest.mark.asyncio]


def make_scheduler(outcome, callback_error=False):
    result = "NO_REPLY" if outcome == "suppressed" else "Result"
    agent = SimpleNamespace(astart=AsyncMock(return_value=result), hook_runner=Mock(), name="test")
    success, failure = Mock(), Mock()
    scheduler = AsyncAgentScheduler(agent, "Task", on_success=success, on_failure=failure)
    delivery = Mock()
    delivery.deliver.return_value = outcome != "failed"
    delivery._target = None
    if outcome != "unconfigured":
        scheduler.deliver = "test:123"
        scheduler._delivery = delivery
    if callback_error:
        (failure if outcome == "failed" else success).side_effect = ValueError("callback failed")
    return scheduler, agent, delivery, success, failure, result


@pytest.mark.parametrize("outcome", ["delivered", "failed", "suppressed", "unconfigured"])
async def test_execute_once_records_delivery_and_calls_callback(outcome):
    scheduler, agent, delivery, success, failure, result = make_scheduler(outcome)
    assert await scheduler.execute_once() == result
    agent.astart.assert_awaited_once_with("Task")
    assert scheduler._delivered_count == int(outcome == "delivered")
    assert scheduler._undelivered_count == int(outcome == "failed")
    if outcome == "failed":
        success.assert_not_called()
        failure.assert_called_once_with("scheduled result could not be delivered")
        agent.hook_runner.execute_sync.assert_called_once()
        event, payload = agent.hook_runner.execute_sync.call_args.args
        assert event.value == "message_undelivered"
        assert payload.content == result
    else:
        success.assert_called_once_with(result)
        failure.assert_not_called()
        agent.hook_runner.execute_sync.assert_not_called()
    if outcome in ("delivered", "failed"):
        delivery.deliver.assert_called_once_with(result)
    else:
        delivery.deliver.assert_not_called()


@pytest.mark.parametrize("outcome", ["delivered", "failed"])
async def test_callback_error_does_not_replace_agent_result(outcome):
    scheduler, _, _, success, failure, result = make_scheduler(outcome, callback_error=True)
    assert await scheduler.execute_once() == result
    (failure if outcome == "failed" else success).assert_called_once()


@pytest.mark.parametrize("error", [ValueError("execution failed"), asyncio.CancelledError()])
async def test_execution_error_propagates_without_delivery(error):
    scheduler, agent, delivery, success, failure, _ = make_scheduler("delivered")
    agent.astart.side_effect = error
    with pytest.raises(type(error)) as caught:
        await scheduler.execute_once()
    assert caught.value is error
    delivery.deliver.assert_not_called()
    success.assert_not_called()
    failure.assert_not_called()
