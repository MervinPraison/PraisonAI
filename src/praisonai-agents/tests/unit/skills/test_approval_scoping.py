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
    
    The bug was that _resolve_skill_invocation would set AutoApproveBackend
    for the entire agent instead of just the specific tools, causing 
    tool approval to leak across different agents.
    """
    # Create temporary skill directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        skill_dir = Path(tmp_dir) / "demo"
        skill_dir.mkdir()
        
        # Create a skill that declares allowed-tools: [read_file]
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: demo
description: Demo skill for testing
allowed-tools: [read_file]
---

# Demo Skill

This is a demo skill for testing approval scoping.
""")
        
        # Mock Agent setup to avoid full initialization
        with patch('praisonaiagents.agent.chat_mixin.get_approval_registry') as mock_get_registry:
            registry = get_approval_registry()
            mock_get_registry.return_value = registry
            
            # Clear any previous state
            registry._agent_tool_auto_approve.clear()
            
            # Create mock agents
            agent_x = Mock()
            agent_x.name = "agent_x"
            agent_x.skill_manager = Mock()
            
            agent_y = Mock()
            agent_y.name = "agent_y" 
            agent_y.skill_manager = None  # No skills
            
            # Mock skill manager for agent_x
            agent_x.skill_manager.get_allowed_tools.return_value = ["read_file"]
            agent_x.skill_manager.invoke.return_value = "Skill activated"
            
            # Import the mixin after setting up mocks
            from praisonaiagents.agent.chat_mixin import ChatMixin
            
            # Add the mixin method to agent_x
            agent_x._resolve_skill_invocation = ChatMixin._resolve_skill_invocation.__get__(agent_x)
            
            # Agent X invokes the skill
            result = agent_x._resolve_skill_invocation("/demo")
            assert result == "Skill activated"
            
            # Verify approval scoping is correct
            assert registry.is_auto_approved("read_file", agent_name="agent_x")
            assert not registry.is_auto_approved("read_file", agent_name="agent_y")
            assert not registry.is_auto_approved("write_file", agent_name="agent_x")  # not in allowed-tools
            
            # Verify no global approval backend was set (the bug fix)
            assert registry._global_backend is None


def test_approval_registry_auto_approve_methods():
    """Test the new auto_approve_tool and is_auto_approved methods."""
    registry = get_approval_registry()
    registry._agent_tool_auto_approve.clear()
    
    # Test per-agent approval
    registry.auto_approve_tool("read_file", agent_name="agent1")
    
    assert registry.is_auto_approved("read_file", agent_name="agent1")
    assert not registry.is_auto_approved("read_file", agent_name="agent2")
    assert not registry.is_auto_approved("write_file", agent_name="agent1")
    
    # Test global approval
    registry.auto_approve_tool("write_file", agent_name=None)
    
    assert registry.is_auto_approved("write_file", agent_name="agent1")
    assert registry.is_auto_approved("write_file", agent_name="agent2")
    assert registry.is_auto_approved("write_file", agent_name=None)


def test_approval_decision_includes_auto_approved_tools():
    """Test that approval checks consult the auto-approval registry."""
    registry = get_approval_registry()
    registry._agent_tool_auto_approve.clear()
    
    # Add a tool that requires approval
    registry.add_requirement("read_file", "high")
    
    # Pre-approve it for agent1
    registry.auto_approve_tool("read_file", agent_name="agent1")
    
    # Test sync approval
    decision = registry.approve_sync("agent1", "read_file", {})
    assert decision.approved
    assert decision.reason == "Auto-approved (skill)"
    assert decision.approver == "skill"
    
    # Test that agent2 does NOT get auto-approval
    decision = registry.approve_sync("agent2", "read_file", {})
    # This would normally go to interactive approval, but since we're testing
    # we expect it to not be auto-approved
    assert not (decision.reason == "Auto-approved (skill)")


@pytest.mark.asyncio
async def test_async_approval_decision_includes_auto_approved_tools():
    """Test async version of approval auto-approval."""
    registry = get_approval_registry()
    registry._agent_tool_auto_approve.clear()
    
    # Add a tool that requires approval  
    registry.add_requirement("read_file", "high")
    
    # Pre-approve it for agent1
    registry.auto_approve_tool("read_file", agent_name="agent1")
    
    # Test async approval
    decision = await registry.approve_async("agent1", "read_file", {})
    assert decision.approved
    assert decision.reason == "Auto-approved (skill)"
    assert decision.approver == "skill"