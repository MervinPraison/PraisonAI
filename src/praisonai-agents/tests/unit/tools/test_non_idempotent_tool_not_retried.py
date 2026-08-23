"""A tool that declares `idempotent = False` must not be re-driven on failure.

The tool body runs *before* it fails, so a retry duplicates whatever side effect
it already performed -- the docstring on `_is_tool_idempotent` names the hazard
exactly: "send a second email, charge twice".

Two retry loops can re-drive a tool, and they split the work by error type:

  * the inner loop (`_execute_tool_with_circuit_breaker`) retries errors whose
    *classified type* is in the policy's retry_on set;
  * the outer loop (`_execute_tool_with_context`) retries on the
    `_praison_retryable` flag, for types the inner loop does not handle.

Both must honour the declaration, or the veto only works for some error messages.
`test_declared_unsafe_is_not_retried` covers the outer loop ("boom" classifies as
unknown) and `test_declared_unsafe_is_not_retried_for_a_known_transient` covers
the inner one ("connection reset" classifies as a transient).
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ToolConfig
from praisonaiagents.tools.retry import RetryPolicy

FAST = ToolConfig(retry_policy=RetryPolicy(max_attempts=3, initial_delay_ms=0))


def _runs(idempotent, message="boom", max_attempts=3):
    """Run a failing tool once through execute_tool; return how often the body ran."""
    calls = []

    def charge_card(amount: str) -> str:
        """Charge a customer's card."""
        calls.append(amount)
        raise RuntimeError(message)

    if idempotent is not None:
        charge_card.idempotent = idempotent

    cfg = ToolConfig(retry_policy=RetryPolicy(max_attempts=max_attempts,
                                              initial_delay_ms=0))
    agent = Agent(instructions="x", tools=[charge_card], tool_config=cfg)
    try:
        agent.execute_tool("charge_card", {"amount": "100"})
    except Exception:
        pass
    return len(calls)


def test_declared_unsafe_is_not_retried():
    """Outer loop: an unclassified error still must not re-charge the card."""
    assert _runs(idempotent=False) == 1


def test_declared_unsafe_is_not_retried_for_a_known_transient():
    """Inner loop: a message that classifies as a transient must not either."""
    assert _runs(idempotent=False, message="connection reset") == 1


@pytest.mark.parametrize("attempts", [1, 2, 3, 4, 6])
def test_declaration_beats_the_retry_budget(attempts):
    """Whatever max_attempts says, a declared-unsafe tool runs once."""
    assert _runs(idempotent=False, max_attempts=attempts) == 1


def test_undeclared_tool_still_retries():
    """The veto must not silently disable retries for ordinary tools."""
    assert _runs(idempotent=None) == 3


def test_declared_safe_tool_still_retries():
    assert _runs(idempotent=True) == 3
