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


def _runs_restart_safe(restart_safe, message="boom", max_attempts=3):
    """Same as ``_runs`` but declares replay-safety via the public ``restart_safe``
    contract on a ``@tool``-decorated FunctionTool instead of a raw ``idempotent``
    attribute. ``restart_safe=False`` is the documented way an effectful tool
    marks itself unsafe to re-run, so the retry veto must honour it too."""
    from praisonaiagents.tools.decorator import tool

    calls = []

    @tool(restart_safe=restart_safe)
    def charge_card(amount: str) -> str:
        """Charge a customer's card."""
        calls.append(amount)
        raise RuntimeError(message)

    cfg = ToolConfig(retry_policy=RetryPolicy(max_attempts=max_attempts,
                                              initial_delay_ms=0))
    agent = Agent(instructions="x", tools=[charge_card], tool_config=cfg)
    try:
        agent.execute_tool("charge_card", {"amount": "100"})
    except Exception:
        pass
    return len(calls)


def test_restart_safe_false_is_not_retried():
    """A ``@tool(restart_safe=False)`` must not be re-driven (outer loop)."""
    assert _runs_restart_safe(restart_safe=False) == 1


def test_restart_safe_false_is_not_retried_for_a_known_transient():
    """Same declaration, inner loop: a transient error must not re-charge."""
    assert _runs_restart_safe(restart_safe=False, message="connection reset") == 1


def test_restart_safe_true_still_retries():
    """``restart_safe=True`` is explicitly replay-safe, so it retries as before."""
    assert _runs_restart_safe(restart_safe=True) == 3


def test_restart_safe_undeclared_still_retries():
    """``restart_safe=None`` (undeclared) must not silently disable retries."""
    assert _runs_restart_safe(restart_safe=None) == 3


def test_base_tool_restart_safe_false_is_not_retried():
    """A ``BaseTool`` subclass declaring ``restart_safe=False`` runs once."""
    from praisonaiagents.tools.base import BaseTool

    calls = []

    class ChargeCard(BaseTool):
        name = "charge_card"
        description = "Charge a customer's card."
        restart_safe = False

        def run(self, amount: str) -> str:
            calls.append(amount)
            raise RuntimeError("boom")

    agent = Agent(instructions="x", tools=[ChargeCard()], tool_config=FAST)
    try:
        agent.execute_tool("charge_card", {"amount": "100"})
    except Exception:
        pass
    assert len(calls) == 1
