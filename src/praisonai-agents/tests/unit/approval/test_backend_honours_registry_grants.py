"""A backend must not bypass the registry's standing approval grants.

`_resolve_approval_decision` has two branches. The no-backend branch consults
the registry. The backend branch called `backend.request_approval[_sync]`
directly and returned, never consulting is_env_auto_approve, is_yaml_approved,
is_auto_approved or is_already_approved.

That is the DEFAULT branch: a bare Agent() on a TTY installs a ConsoleBackend,
and every chat/gateway backend sets the same attribute. Measured before the
fix, with PRAISONAI_AUTO_APPROVE=true and a backend attached:

    backend prompted: 3 times for 3 identical calls   (should have been 0)

So the environment auto-approve was ignored, a YAML approval was ignored, and
an "approve for this session" grant was never remembered -- the user was asked
again on every call.

The gate must still fail closed: with no standing grant, the backend is asked.
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents.approval import ApprovalDecision


class _CountingBackend:
    def __init__(self, approved=True, scope="once"):
        self.calls = 0
        self._approved = approved
        self._scope = scope

    def request_approval_sync(self, request):
        self.calls += 1
        return ApprovalDecision(
            approved=self._approved, reason="from backend", scope=self._scope
        )

    def request_approval(self, request):
        return self.request_approval_sync(request)


def _agent_with_backend(backend):
    from praisonaiagents import Agent
    agent = Agent(name="t", instructions="x", llm="gpt-4o-mini")
    agent._approval_backend = backend
    return agent


@pytest.fixture
def no_env_grant(monkeypatch):
    monkeypatch.delenv("PRAISONAI_AUTO_APPROVE", raising=False)


@pytest.fixture
def env_grant(monkeypatch):
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")


@pytest.fixture(autouse=True)
def _clean_registry():
    """Isolate the in-memory approval/session stores between tests."""
    from praisonaiagents.approval import get_approval_registry

    get_approval_registry().clear_approved()
    yield
    get_approval_registry().clear_approved()


class TestStandingGrantsAreHonoured:

    def test_env_auto_approve_skips_the_backend(self, env_grant):
        backend = _CountingBackend()
        agent = _agent_with_backend(backend)
        agent._resolve_approval_decision("execute_command", {"command": "ls"})
        assert backend.calls == 0, (
            "PRAISONAI_AUTO_APPROVE was set and the user was prompted anyway"
        )

    def test_it_still_approves(self, env_grant):
        agent = _agent_with_backend(_CountingBackend())
        decision = agent._resolve_approval_decision("execute_command", {"command": "ls"})
        assert decision.approved is True

    def test_repeated_calls_stay_silent(self, env_grant):
        backend = _CountingBackend()
        agent = _agent_with_backend(backend)
        for _ in range(3):
            agent._resolve_approval_decision("execute_command", {"command": "ls"})
        assert backend.calls == 0


class TestTheGateStillAsks:

    def test_without_a_grant_the_backend_is_consulted(self, no_env_grant):
        backend = _CountingBackend()
        agent = _agent_with_backend(backend)
        agent._resolve_approval_decision("execute_command", {"command": "ls"})
        assert backend.calls == 1, "the approval gate stopped asking"

    def test_a_denial_is_still_a_denial(self, no_env_grant):
        agent = _agent_with_backend(_CountingBackend(approved=False))
        decision = agent._resolve_approval_decision("execute_command", {"command": "ls"})
        assert decision.approved is False

    def test_a_harmless_tool_is_not_gated(self, no_env_grant):
        """Guards against the change widening what gets prompted."""
        backend = _CountingBackend()
        agent = _agent_with_backend(backend)
        agent._resolve_approval_decision("some_harmless_tool", {})
        assert backend.calls == 0


class TestSessionGrantIsRemembered:
    """A "[s] this session" grant at the backend prompt must be honoured
    for the rest of the run without re-prompting -- the same contract the
    no-backend registry path already keeps via _persist_scoped_decision.
    """

    def test_session_grant_is_recorded_and_honoured(self, no_env_grant):
        """A 'session' decision from the backend is recorded in the registry's
        reusable-target store and honoured by the fast path on the next call --
        the exact contract the no-backend path keeps via _persist_scoped_decision.
        """
        from praisonaiagents.approval import get_approval_registry

        registry = get_approval_registry()
        backend = _CountingBackend(scope="session")
        agent = _agent_with_backend(backend)

        d1 = agent._resolve_approval_decision("execute_command", {"command": "ls"})
        assert d1.approved is True
        assert backend.calls == 1
        # The session grant must now be in the reusable-target store, keyed by
        # this agent's per-instance scope id (not just the exact-args cache).
        scope_id = getattr(agent, "_approval_scope_id", None) or agent.name
        assert registry._is_session_scoped(
            agent.name, "execute_command", {"command": "ls"}, scope_id
        ), "backend 'session' grant was never recorded in the registry"

        # A second identical call is served from the standing grant, not the
        # backend.
        d2 = agent._resolve_approval_decision("execute_command", {"command": "ls"})
        assert d2.approved is True
        assert backend.calls == 1, (
            "a 'this session' grant was not remembered; the backend was asked again"
        )

    def test_a_once_grant_is_not_a_standing_grant(self, no_env_grant):
        """Failing closed: a plain 'once' approval must NOT create a reusable
        session grant. A later call under a *different* target is re-prompted."""
        from praisonaiagents.approval import get_approval_registry

        registry = get_approval_registry()
        backend = _CountingBackend(scope="once")
        agent = _agent_with_backend(backend)
        agent._resolve_approval_decision("execute_command", {"command": "ls"})
        scope_id = getattr(agent, "_approval_scope_id", None) or agent.name
        assert not registry._is_session_scoped(
            agent.name, "execute_command", {"command": "ls"}, scope_id
        ), "a one-shot approval was wrongly recorded as a standing session grant"

        # A different target under the same tool must still ask.
        agent._resolve_approval_decision("execute_command", {"command": "pwd"})
        assert backend.calls == 2, (
            "a one-shot approval was wrongly treated as a standing grant"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
