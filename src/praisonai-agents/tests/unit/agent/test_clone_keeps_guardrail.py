"""A per-channel clone must keep the guardrail the original was given.

`clone_for_channel()` rebuilds the agent from `getattr(self, '_guardrails_config',
None)`, but `_guardrails_config` used to be only a local inside `__init__` and was
never assigned to the instance. The getattr therefore always yielded None and the
clone was constructed with no guardrail at all.

This matters because `clone_for_channel()` is the code path that serves traffic:
one clone per channel in the bot gateway, one per HTTP invocation in the API.
"""
from praisonaiagents import Agent


def _reject(output):
    """Guardrail that always refuses."""
    return (False, "contains PII")


def _agent():
    return Agent(name="Support", instructions="i", llm="gpt-4o-mini", guardrails=_reject)


def test_original_agent_withholds():
    """Control: without this passing, the rest proves nothing."""
    assert _agent()._guardrail_fn is not None


def test_clone_keeps_the_guardrail():
    clone = _agent().clone_for_channel()
    assert clone._guardrail_fn is not None, (
        "clone_for_channel() produced an agent with no output guardrail; "
        "the gateway serves one such clone per channel"
    )


def test_resolved_config_is_persisted_for_the_clone_to_read():
    """clone_for_channel() reads this attribute; it must exist."""
    agent = _agent()
    assert hasattr(agent, "_guardrails_config")
    assert agent._guardrails_config is not None


def test_no_guardrail_stays_no_guardrail():
    """A plain agent must not acquire one, and its clone must not either."""
    plain = Agent(name="Plain", instructions="i", llm="gpt-4o-mini")
    assert plain._guardrail_fn is None
    assert plain.clone_for_channel()._guardrail_fn is None


def test_approval_config_is_persisted_for_the_clone_to_read():
    """clone_for_channel() reads _approval_config; it must exist so the served
    clone keeps the operator's approval policy."""
    agent = Agent(
        name="Approving", instructions="i", llm="gpt-4o-mini", approval="read_only"
    )
    assert hasattr(agent, "_approval_config")
    assert agent._approval_config == "read_only"


def test_clone_keeps_the_approval_policy():
    """A served clone must reconstruct with the same approval policy, otherwise
    the gateway serves untrusted traffic with the operator's policy dropped."""
    agent = Agent(
        name="Approving", instructions="i", llm="gpt-4o-mini", approval="read_only"
    )
    clone = agent.clone_for_channel()
    assert clone._approval_config == "read_only", (
        "clone_for_channel() produced an agent without the approval policy; "
        "the gateway serves one such clone per channel"
    )
    assert clone._perm_deny == agent._perm_deny, (
        "the read_only preset's enforced deny set was not preserved on the clone"
    )


def test_no_approval_stays_no_approval():
    """A plain agent must not acquire a policy, and neither must its clone."""
    plain = Agent(name="Plain", instructions="i", llm="gpt-4o-mini")
    assert plain._approval_config is None
    assert plain.clone_for_channel()._approval_config is None
