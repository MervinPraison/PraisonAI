"""Async twin of test_non_idempotent_tool_not_retried.py.

`@tool(restart_safe=False)` is the documented contract for "an effectful tool
that must never be silently re-executed" (tools/decorator.py:300-307). The sync
retry loops honour it; `_execute_tool_async_with_retry` never consulted the
declaration, so an async agent re-ran the tool body up to `max_attempts` times.
"""
import asyncio

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ToolConfig
from praisonaiagents.errors import ToolExecutionError
from praisonaiagents.tools.retry import RetryPolicy

# The effectful tool raises ``RuntimeError``. The async path flattens it into an
# error dict (nothing surfaces), while the sync path re-raises it wrapped in a
# ``ToolExecutionError``. Catch *only* those two expected failures so an unrelated
# setup error can never masquerade as a valid execution count.
EXPECTED_FAILURE = (RuntimeError, ToolExecutionError)

ATTEMPTS = 3
FAST = ToolConfig(retry_policy=RetryPolicy(max_attempts=ATTEMPTS, initial_delay_ms=0))


def _charges(declare, is_async, attr="restart_safe"):
    """Run a failing effectful tool once; return how many times the body ran."""
    charged = []

    def charge_card(amount: str) -> str:
        """Charge a customer's card."""
        charged.append(amount)
        raise RuntimeError("gateway 502 from acquirer")

    if declare is not None:
        setattr(charge_card, attr, declare)

    agent = Agent(instructions="x", tools=[charge_card], tool_config=FAST)
    try:
        if is_async:
            asyncio.run(agent.execute_tool_async("charge_card", {"amount": "100"}))
        else:
            agent.execute_tool("charge_card", {"amount": "100"})
    except EXPECTED_FAILURE:
        pass
    return len(charged)


@pytest.mark.parametrize("attr", ["restart_safe", "idempotent"])
def test_async_honours_the_declaration(attr):
    assert _charges(False, is_async=True, attr=attr) == 1, (
        f"a tool declared {attr}=False was re-run on the async path"
    )


@pytest.mark.parametrize("attr", ["restart_safe", "idempotent"])
def test_async_matches_sync(attr):
    assert _charges(False, is_async=True, attr=attr) == _charges(False, is_async=False, attr=attr)


@pytest.mark.parametrize("declare", [None, True])
def test_undeclared_and_safe_tools_still_retry_on_async(declare):
    """Controls: the veto must not blanket-disable async retry."""
    assert _charges(declare, is_async=True) == ATTEMPTS


@pytest.mark.parametrize("declare", [None, True])
def test_sync_controls_unchanged(declare):
    assert _charges(declare, is_async=False) == ATTEMPTS


@pytest.mark.parametrize("attr", ["restart_safe", "idempotent"])
def test_async_honours_declaration_on_override_only_tool(attr):
    """A task-scoped tool supplied *only* via ``tools_override`` (never registered
    on the agent) must still be vetoed. ``_execute_tool_async_impl`` resolves it
    from the override list, so the idempotency check has to see it there too --
    otherwise the effectful body is retried ``max_attempts`` times.
    """
    charged = []

    def charge_card(amount: str) -> str:
        """Charge a customer's card."""
        charged.append(amount)
        raise RuntimeError("gateway 502 from acquirer")

    setattr(charge_card, attr, False)

    # Agent has NO tools of its own; the effectful tool arrives only at call time.
    agent = Agent(instructions="x", tools=[], tool_config=FAST)
    try:
        asyncio.run(agent.execute_tool_async(
            "charge_card", {"amount": "100"}, tools_override=[charge_card]
        ))
    except EXPECTED_FAILURE:
        pass

    assert len(charged) == 1, (
        f"an override-only tool declared {attr}=False was re-run on the async path"
    )
