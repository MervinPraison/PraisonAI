"""Streamed turns must honour the same pre-turn checks as chat()/achat()."""

from unittest.mock import Mock

from praisonaiagents import Agent
from praisonaiagents.hooks import HookEvent, HookResult


def _agent(monkeypatch):
    agent = Agent(name="s", instructions="x", llm="gpt-4o-mini")
    impl = Mock(return_value=iter(["chunk"]))
    monkeypatch.setattr(agent, "_start_stream_impl", impl)
    return agent, impl


def test_blocking_before_agent_hook_stops_iter_stream(monkeypatch):
    agent, impl = _agent(monkeypatch)
    hook_id = agent._hook_runner.registry.register_function(
        HookEvent.BEFORE_AGENT, lambda data: HookResult.block("no")
    )
    try:
        assert list(agent.iter_stream("hi")) == []
    finally:
        agent._hook_runner.registry.unregister(hook_id)
    impl.assert_not_called()


def test_iter_stream_acquires_rate_limiter(monkeypatch):
    agent, impl = _agent(monkeypatch)
    agent._rate_limiter = Mock()
    assert list(agent.iter_stream("hi")) == ["chunk"]
    agent._rate_limiter.acquire.assert_called_once()
    impl.assert_called_once()
