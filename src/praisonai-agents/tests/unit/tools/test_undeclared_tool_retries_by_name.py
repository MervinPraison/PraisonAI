"""An UNDECLARED tool must retry regardless of what its name happens to be.

`_tool_declares_not_idempotent` fell back to the shared `MUTATING_TOOLS` registry
-- 73 names maintained for the escalation loop guard -- which silently removed the
retry from any tool that merely shared a name with an entry, even though nothing
declared anything.

The original test for this feature parametrized only over `charge_card`, a name
absent from that registry, so it could not catch the regression it existed to
prevent. These rows are the ones that were missing.
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ToolConfig
from praisonaiagents.escalation.loop_guard import MUTATING_TOOLS
from praisonaiagents.tools.retry import RetryPolicy

ATTEMPTS = 3
FAST = ToolConfig(retry_policy=RetryPolicy(max_attempts=ATTEMPTS, initial_delay_ms=0))

# Names that ARE in the shared registry -- the rows the original test lacked.
COLLIDING = ["write_file", "store_memory", "mkdir"]
# A name that is not, matching the original test's coverage.
NON_COLLIDING = ["charge_card", "my_helper"]


@pytest.fixture(autouse=True)
def _auto_approve():
    """Some names (``write_file``, ``mkdir``) are approval-gated as HIGH risk.

    That gate is orthogonal to the retry veto under test; without auto-approval
    the tool body never runs and the retry count is unmeasurable. Approve every
    request so each test observes retry behaviour alone.
    """
    from praisonaiagents.approval import set_approval_callback
    from praisonaiagents.approval.protocols import ApprovalDecision

    set_approval_callback(lambda *a, **k: ApprovalDecision(approved=True))
    try:
        yield
    finally:
        set_approval_callback(None)


def _runs(fname, declare=None):
    calls = []

    def fn(x: str) -> str:
        """A tool."""
        calls.append(x)
        raise RuntimeError("transient blip")

    fn.__name__ = fname
    if declare is not None:
        fn.idempotent = declare

    agent = Agent(instructions="x", tools=[fn], tool_config=FAST)
    try:
        agent.execute_tool(fname, {"x": "v"})
    except Exception:
        pass
    return len(calls)


@pytest.mark.parametrize("name", COLLIDING)
def test_registry_name_alone_does_not_disable_retry(name):
    """Sharing a name with MUTATING_TOOLS is not a declaration."""
    assert name in MUTATING_TOOLS, f"{name} must be in the registry for this test to mean anything"
    assert _runs(name, declare=None) == ATTEMPTS


@pytest.mark.parametrize("name", NON_COLLIDING)
def test_undeclared_tool_retries(name):
    assert name not in MUTATING_TOOLS
    assert _runs(name, declare=None) == ATTEMPTS


@pytest.mark.parametrize("name", COLLIDING + NON_COLLIDING)
def test_explicit_declaration_still_vetoes_the_retry(name):
    """The feature itself must keep working, whatever the name."""
    assert _runs(name, declare=False) == 1


@pytest.mark.parametrize("name", COLLIDING + NON_COLLIDING)
def test_explicit_safe_declaration_still_retries(name):
    assert _runs(name, declare=True) == ATTEMPTS
