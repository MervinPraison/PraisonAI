"""Tests for delegate_task wiring into the subagent runtime."""

import json
import os

import pytest

os.environ.setdefault("PRAISONAI_AUTO_APPROVE", "true")

from praisonaiagents.tools import delegation_tools
from praisonaiagents.tools.delegation_tools import DelegationTools, delegate_task


def _fake_subagent_tool(output="delegated result", success=True, error=None):
    def factory(*, agent_factory=None, **kwargs):
        def spawn(task, agent_name=None, **kw):
            if success:
                return {"success": True, "output": output, "agent_name": agent_name}
            return {"success": False, "error": error or "boom", "output": None}
        return {"function": spawn}
    return factory


def test_delegate_task_success(monkeypatch):
    monkeypatch.setattr(
        delegation_tools, "create_subagent_tool", _fake_subagent_tool()
    )
    raw = DelegationTools().delegate_task("Do research", agent_type="research")
    data = json.loads(raw)
    assert data["success"] is True
    assert data["agent_type"] == "research"
    assert "delegated result" in data["output"]


def test_delegate_task_module_function(monkeypatch):
    monkeypatch.setattr(
        delegation_tools, "create_subagent_tool", _fake_subagent_tool()
    )
    raw = delegate_task("Summarize report", agent_type="analyst")
    data = json.loads(raw)
    assert data["success"] is True
    assert data["output"]


def test_delegate_task_runtime_failure(monkeypatch):
    monkeypatch.setattr(
        delegation_tools,
        "create_subagent_tool",
        _fake_subagent_tool(success=False, error="Maximum subagent depth (3) exceeded"),
    )
    raw = DelegationTools().delegate_task("Deep task", agent_type="research")
    data = json.loads(raw)
    assert data["success"] is False
    assert "depth" in data["error"]


def test_delegate_task_no_stub_message(monkeypatch):
    monkeypatch.setattr(
        delegation_tools, "create_subagent_tool", _fake_subagent_tool()
    )
    raw = DelegationTools().delegate_task("Anything")
    assert "no sub-agent runtime is wired up" not in raw


def test_delegate_task_timeout(monkeypatch):
    import time

    def factory(*, agent_factory=None, **kwargs):
        def spawn(task, agent_name=None, **kw):
            time.sleep(0.5)
            return {"success": True, "output": "too late", "agent_name": agent_name}
        return {"function": spawn}

    monkeypatch.setattr(delegation_tools, "create_subagent_tool", factory)
    raw = DelegationTools().delegate_task("Slow task", agent_type="research", timeout=1)
    data = json.loads(raw)
    # 0.5s < 1s timeout -> completes normally
    assert data["success"] is True

    raw = DelegationTools().delegate_task("Slow task", agent_type="research", timeout=0)
    # timeout=0 disables the bound; still succeeds
    assert json.loads(raw)["success"] is True


def test_delegate_task_timeout_exceeded(monkeypatch):
    import time

    def factory(*, agent_factory=None, **kwargs):
        def spawn(task, agent_name=None, **kw):
            time.sleep(2)
            return {"success": True, "output": "too late", "agent_name": agent_name}
        return {"function": spawn}

    monkeypatch.setattr(delegation_tools, "create_subagent_tool", factory)
    raw = DelegationTools().delegate_task("Slow task", agent_type="research", timeout=1)
    data = json.loads(raw)
    assert data["success"] is False
    assert "timed out" in data["error"]


def test_delegate_task_requires_approval_registered():
    from praisonaiagents.approval import get_approval_registry

    reg = get_approval_registry()
    assert "delegate_task" in reg._required_tools
