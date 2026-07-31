"""
Tests for launch(protocol="mcp") delegating to praisonai_mcp.serve_agents.

Both Agent.launch(protocol="mcp") and PraisonAIAgents.launch(protocol="mcp")
should route through the same serve_agents adapter (one vocabulary), while
protocol="http" behaviour is left untouched.
"""
import sys
import types

import pytest

from praisonaiagents import Agent
from praisonaiagents.agents import PraisonAIAgents


def _install_fake_mcp(monkeypatch):
    """Install a fake praisonai_mcp module exposing a recording serve_agents."""
    calls = {}

    def fake_serve_agents(agents, *, host="127.0.0.1", port=7777, **kwargs):
        calls["agents"] = list(agents)
        calls["host"] = host
        calls["port"] = port
        calls["kwargs"] = kwargs
        return "served"

    fake_module = types.ModuleType("praisonai_mcp")
    fake_module.serve_agents = fake_serve_agents
    monkeypatch.setitem(sys.modules, "praisonai_mcp", fake_module)
    return calls


def test_agents_launch_mcp_delegates(monkeypatch):
    """PraisonAIAgents.launch(protocol='mcp') reaches serve_agents with all agents."""
    calls = _install_fake_mcp(monkeypatch)

    a1 = Agent(name="support", instructions="help")
    a2 = Agent(name="billing", instructions="bill")
    group = PraisonAIAgents(agents=[a1, a2])

    result = group.launch(protocol="mcp", port=7777)

    assert result == "served"
    assert calls["agents"] == [a1, a2]
    assert calls["port"] == 7777


def test_agent_launch_mcp_single(monkeypatch):
    """Agent.launch(protocol='mcp') serves [self] via the same serve_agents path."""
    calls = _install_fake_mcp(monkeypatch)

    agent = Agent(name="solo", instructions="do things")
    result = agent.launch(protocol="mcp", port=9999)

    assert result == "served"
    assert calls["agents"] == [agent]
    assert calls["port"] == 9999


def test_agents_launch_mcp_missing_package(monkeypatch):
    """A missing praisonai-mcp yields a clean None + guidance, not a traceback."""
    monkeypatch.setitem(sys.modules, "praisonai_mcp", None)

    agent = Agent(name="solo", instructions="do things")
    group = PraisonAIAgents(agents=[agent])

    assert group.launch(protocol="mcp") is None


def test_agent_launch_mcp_missing_package(monkeypatch):
    """Single-agent MCP launch also fails cleanly when the package is absent."""
    monkeypatch.setitem(sys.modules, "praisonai_mcp", None)

    agent = Agent(name="solo", instructions="do things")
    assert agent.launch(protocol="mcp") is None


def _install_fake_mcp_missing_transport(monkeypatch):
    """Install a praisonai_mcp whose serve_agents raises ImportError.

    Mirrors the real case where praisonai-mcp is installed but its optional
    transport backend is not, so the missing dependency only surfaces when
    serve_agents() lazily imports it — after the top-level import succeeded.
    """
    def raising_serve_agents(agents, **kwargs):
        raise ImportError("No module named 'fastapi'")

    fake_module = types.ModuleType("praisonai_mcp")
    fake_module.serve_agents = raising_serve_agents
    monkeypatch.setitem(sys.modules, "praisonai_mcp", fake_module)


def test_agent_launch_mcp_missing_transport_extras(monkeypatch):
    """A late transport ImportError is handled, not raised to the caller."""
    _install_fake_mcp_missing_transport(monkeypatch)

    agent = Agent(name="solo", instructions="do things")
    assert agent.launch(protocol="mcp") is None


def test_agents_launch_mcp_missing_transport_extras(monkeypatch):
    """Multi-agent launch also handles a late transport ImportError cleanly."""
    _install_fake_mcp_missing_transport(monkeypatch)

    group = PraisonAIAgents(agents=[Agent(name="solo", instructions="do things")])
    assert group.launch(protocol="mcp") is None


def test_invalid_protocol_rejected():
    """An unknown protocol raises/reports rather than serving."""
    agent = Agent(name="solo", instructions="do things")
    with pytest.raises(ValueError):
        agent.launch(protocol="grpc")
