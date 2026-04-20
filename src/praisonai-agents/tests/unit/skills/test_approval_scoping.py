"""
Test G-A regression: approval scoping bug fix.

Verifies that skills with allowed-tools do not leak approval across agents.
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile
import os

from praisonaiagents.approval import get_approval_registry


def test_skill_allowed_tools_do_not_leak_across_agents():
    """G-A regression test: skill allowed-tools should not leak across agents.

    The pre-fix bug: ``_resolve_skill_invocation`` set ``AutoApproveBackend``
    for the whole agent (via ``set_backend(...)``), which granted approval for
    every tool on that agent. The fix pre-approves only the named tools via
    ``registry.auto_approve_tool`` scoped to ``(agent_name, tool_name)``.
    """
    registry = get_approval_registry()
    registry._agent_tool_auto_approve.clear()

    # Mock the skill_manager to avoid constructing a real Agent.
    agent_x = Mock()
    agent_x.name = "agent_x"
    agent_x.display_name = "agent_x"
    agent_x.skill_manager = Mock()
    agent_x.skill_manager.get_allowed_tools.return_value = ["read_file"]
    agent_x.skill_manager.invoke.return_value = "Skill activated"

    from praisonaiagents.agent.chat_mixin import ChatMixin
    agent_x._resolve_skill_invocation = ChatMixin._resolve_skill_invocation.__get__(agent_x)

    result = agent_x._resolve_skill_invocation("/demo")
    assert result == "Skill activated"

    # Correct per-agent, per-tool scoping:
    assert registry.is_auto_approved("read_file", agent_name="agent_x")
    assert not registry.is_auto_approved("read_file", agent_name="agent_y")
    assert not registry.is_auto_approved("write_file", agent_name="agent_x")

    # Pre-fix bug signature: agent-wide backend swap must NOT happen anymore.
    assert registry._global_backend is None
    assert "agent_x" not in registry._agent_backends


def test_approval_registry_auto_approve_methods():
    """``auto_approve_tool`` requires a stable per-agent scope (no global form)."""
    registry = get_approval_registry()
    registry._agent_tool_auto_approve.clear()

    registry.auto_approve_tool("read_file", agent_name="agent1")

    assert registry.is_auto_approved("read_file", agent_name="agent1")
    assert not registry.is_auto_approved("read_file", agent_name="agent2")
    assert not registry.is_auto_approved("write_file", agent_name="agent1")

    # Explicit design: refuse anonymous / global scope for skill approvals.
    with pytest.raises(ValueError):
        registry.auto_approve_tool("write_file", agent_name=None)
    with pytest.raises(ValueError):
        registry.auto_approve_tool("write_file", agent_name="")


def test_approval_decision_includes_auto_approved_tools():
    """Sync approval honours per-agent auto-approval."""
    registry = get_approval_registry()
    registry._agent_tool_auto_approve.clear()
    registry.clear_approved()

    registry.add_requirement("read_file", "high")
    registry.auto_approve_tool("read_file", agent_name="agent1")

    decision = registry.approve_sync("agent1", "read_file", {})
    assert decision.approved
    assert decision.reason == "Auto-approved (skill)"
    assert decision.approver == "skill"


@pytest.mark.asyncio
async def test_async_approval_decision_includes_auto_approved_tools():
    """Async approval honours per-agent auto-approval."""
    registry = get_approval_registry()
    registry._agent_tool_auto_approve.clear()
    registry.clear_approved()  # context-var reset so "Already approved" doesn't fire

    registry.add_requirement("read_file", "high")
    registry.auto_approve_tool("read_file", agent_name="agent1")

    decision = await registry.approve_async("agent1", "read_file", {})
    assert decision.approved
    assert decision.reason == "Auto-approved (skill)"
    assert decision.approver == "skill"