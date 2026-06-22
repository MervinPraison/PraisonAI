"""
Unit tests for HandoffToolPolicy security boundary enforcement.

Tests the critical security fix that ensures:
- tools=None means inherit agent's configured tools
- tools=[] means explicitly deny all tools (security boundary)
- HandoffToolPolicy intersect mode properly restricts tool access
- HandoffToolPolicy passthrough mode works correctly
"""
import pytest
from unittest.mock import Mock, patch
from praisonaiagents.agent.handoff import (
    HandoffToolPolicy, 
    Handoff, 
    HandoffConfig,
    handoff
)
from praisonaiagents import Agent


class TestHandoffToolPolicySecurity:
    """Test HandoffToolPolicy security boundary enforcement."""

    def test_intersect_mode_default_secure(self):
        """Test that intersect mode is the default and enforces security."""
        policy = HandoffToolPolicy()
        assert policy.mode == "intersect"
        assert policy.blocked_tools == []

    def test_passthrough_mode_explicit(self):
        """Test explicit passthrough mode configuration."""
        policy = HandoffToolPolicy(mode="passthrough", blocked_tools=["dangerous_tool"])
        assert policy.mode == "passthrough"
        assert "dangerous_tool" in policy.blocked_tools

    def test_blocked_tools_empty_list_handling(self):
        """Test that blocked_tools=[] is properly handled (not ignored via falsy logic)."""
        policy = HandoffToolPolicy(mode="passthrough", blocked_tools=[])
        assert policy.blocked_tools == []

    def test_compute_effective_tools_intersect_mode(self):
        """Test _compute_effective_tools with intersect mode (secure default)."""
        # Mock source agent with tools
        source_agent = Mock()
        source_agent.name = "source"
        source_agent.tools = [Mock(__name__="shared_tool"), Mock(__name__="source_only")]

        # Mock target agent with tools
        target_agent = Mock()
        target_agent.name = "target"
        target_agent.tools = [Mock(__name__="shared_tool"), Mock(__name__="target_only")]

        # Create handoff with intersect mode (default)
        config = HandoffConfig(tool_policy=HandoffToolPolicy(mode="intersect"))
        handoff_obj = Handoff(agent=target_agent, config=config)

        # Compute effective tools
        effective_tools = handoff_obj._compute_effective_tools(source_agent)

        # Should only include shared tools
        assert len(effective_tools) == 1
        assert effective_tools[0].__name__ == "shared_tool"

    def test_compute_effective_tools_intersect_empty_intersection(self):
        """Test intersect mode with no shared tools returns empty list."""
        # Mock source agent with different tools
        source_agent = Mock()
        source_agent.name = "source"
        source_agent.tools = [Mock(__name__="source_only")]

        # Mock target agent with different tools
        target_agent = Mock()
        target_agent.name = "target" 
        target_agent.tools = [Mock(__name__="target_only")]

        # Create handoff with intersect mode
        config = HandoffConfig(tool_policy=HandoffToolPolicy(mode="intersect"))
        handoff_obj = Handoff(agent=target_agent, config=config)

        # Compute effective tools
        effective_tools = handoff_obj._compute_effective_tools(source_agent)

        # Should return empty list (security boundary)
        assert effective_tools == []

    def test_compute_effective_tools_passthrough_no_blocked(self):
        """Test passthrough mode with no blocked tools returns None."""
        source_agent = Mock()
        source_agent.name = "source"
        
        target_agent = Mock()
        target_agent.name = "target"
        target_agent.tools = [Mock(__name__="tool1"), Mock(__name__="tool2")]

        # Create handoff with passthrough mode, no blocked tools
        config = HandoffConfig(tool_policy=HandoffToolPolicy(mode="passthrough"))
        handoff_obj = Handoff(agent=target_agent, config=config)

        # Compute effective tools
        effective_tools = handoff_obj._compute_effective_tools(source_agent)

        # Should return None (unrestricted access)
        assert effective_tools is None

    def test_compute_effective_tools_passthrough_with_blocked(self):
        """Test passthrough mode with blocked tools filters properly."""
        source_agent = Mock()
        source_agent.name = "source"
        
        target_agent = Mock()
        target_agent.name = "target"
        tool1 = Mock(__name__="safe_tool")
        tool2 = Mock(__name__="dangerous_tool")
        target_agent.tools = [tool1, tool2]

        # Create handoff with passthrough mode and blocked tools
        config = HandoffConfig(
            tool_policy=HandoffToolPolicy(
                mode="passthrough", 
                blocked_tools=["dangerous_tool"]
            )
        )
        handoff_obj = Handoff(agent=target_agent, config=config)

        # Compute effective tools
        effective_tools = handoff_obj._compute_effective_tools(source_agent)

        # Should only include safe_tool
        assert len(effective_tools) == 1
        assert effective_tools[0].__name__ == "safe_tool"

    def test_compute_effective_tools_handles_none_tools(self):
        """Test that None tools are handled correctly (no TypeError)."""
        # Mock agents with None tools
        source_agent = Mock()
        source_agent.name = "source"
        source_agent.tools = None

        target_agent = Mock()
        target_agent.name = "target"
        target_agent.tools = None

        # Create handoff with intersect mode
        config = HandoffConfig(tool_policy=HandoffToolPolicy(mode="intersect"))
        handoff_obj = Handoff(agent=target_agent, config=config)

        # Should not raise TypeError
        effective_tools = handoff_obj._compute_effective_tools(source_agent)
        assert effective_tools == []

    @patch('praisonaiagents.agent.handoff.time.time')
    def test_handoff_execution_respects_tool_boundary_sync(self, mock_time):
        """Test that programmatic handoff execution enforces tool boundaries."""
        mock_time.return_value = 123.0
        
        source_agent = Mock()
        source_agent.name = "source"
        source_agent.tools = [Mock(__name__="shared_tool")]

        target_agent = Mock()
        target_agent.name = "target"
        target_agent.tools = [Mock(__name__="shared_tool"), Mock(__name__="private_tool")]
        target_agent.chat = Mock(return_value="response")

        # Create handoff with intersect mode
        config = HandoffConfig(tool_policy=HandoffToolPolicy(mode="intersect"))
        handoff_obj = Handoff(agent=target_agent, config=config)

        # Execute programmatic handoff
        result = handoff_obj.execute_programmatic(source_agent, "test prompt")

        # Verify that target agent's chat was called with restricted tools
        target_agent.chat.assert_called_once()
        call_args = target_agent.chat.call_args
        assert "tools" in call_args.kwargs
        effective_tools = call_args.kwargs["tools"]
        assert len(effective_tools) == 1
        assert effective_tools[0].__name__ == "shared_tool"

    def test_handoff_factory_function_tool_policy_kwargs(self):
        """Test that handoff() factory function properly handles tool policy kwargs."""
        target_agent = Mock()
        target_agent.name = "target"

        # Test with tool policy kwargs
        h = handoff(
            agent=target_agent,
            tool_policy_mode="passthrough",
            blocked_tools=["dangerous_tool"]
        )

        assert h.config.tool_policy.mode == "passthrough"
        assert "dangerous_tool" in h.config.tool_policy.blocked_tools

    def test_handoff_factory_explicit_none_blocked_tools(self):
        """Test that blocked_tools=[] explicitly clears blocked tools."""
        target_agent = Mock()
        target_agent.name = "target"

        # Create config with some blocked tools
        base_config = HandoffConfig(
            tool_policy=HandoffToolPolicy(blocked_tools=["tool1", "tool2"])
        )

        # Use handoff factory to explicitly clear blocked tools
        h = handoff(
            agent=target_agent,
            config=base_config,
            blocked_tools=[]  # Explicit empty list should clear
        )

        # Should have cleared the blocked tools
        assert h.config.tool_policy.blocked_tools == []

    def test_handoff_factory_none_blocked_tools_preserves_existing(self):
        """Test that blocked_tools=None preserves existing blocked tools."""
        target_agent = Mock()
        target_agent.name = "target"

        # Create config with some blocked tools
        base_config = HandoffConfig(
            tool_policy=HandoffToolPolicy(blocked_tools=["tool1", "tool2"])
        )

        # Use handoff factory with blocked_tools=None
        h = handoff(
            agent=target_agent,
            config=base_config,
            blocked_tools=None  # Should preserve existing
        )

        # Should preserve the existing blocked tools
        assert "tool1" in h.config.tool_policy.blocked_tools
        assert "tool2" in h.config.tool_policy.blocked_tools


class TestToolSecurityBoundaryIntegration:
    """Integration tests for tools=[] vs tools=None security boundary."""

    def test_agent_chat_tools_none_inherits_agent_tools(self):
        """Test that tools=None in agent.chat() inherits agent's configured tools."""
        # Create mock agent with tools
        agent = Mock()
        agent.tools = [Mock(__name__="agent_tool")]
        agent.chat_history = []
        agent._memory_instance = None
        
        # Mock the _format_tools_for_completion method
        agent._format_tools_for_completion = Mock(return_value=[{"type": "function", "function": {"name": "agent_tool"}}])
        
        # Import and call the fixed method
        from praisonaiagents.agent.chat_mixin import ChatMixin
        # Temporarily bind the method to test the security fix
        bound_method = ChatMixin._format_tools_for_completion.__get__(agent)
        
        # Test tools=None should inherit from agent.tools
        result = bound_method(tools=None)
        
        # Should call with agent's tools
        agent._format_tools_for_completion.assert_called_once_with(agent.tools)

    def test_agent_chat_tools_empty_list_enforces_boundary(self):
        """Test that tools=[] in agent.chat() enforces empty tool boundary."""
        # Create mock agent with tools
        agent = Mock()
        agent.tools = [Mock(__name__="agent_tool")]
        
        # Import and call the fixed method
        from praisonaiagents.agent.chat_mixin import ChatMixin
        
        # Test tools=[] should return empty immediately
        result = ChatMixin._format_tools_for_completion(agent, tools=[])
        
        # Should return empty list immediately (security boundary)
        assert result == []

    @patch('praisonaiagents.agent.handoff.time.time')
    @patch('praisonaiagents.agent.agent.Agent')
    def test_handoff_tool_boundary_end_to_end(self, MockAgent, mock_time):
        """End-to-end test of handoff tool boundary enforcement."""
        mock_time.return_value = 123.0
        
        # Create real-ish agents with tools
        source = MockAgent()
        source.name = "orchestrator"
        source.tools = [Mock(__name__="search")]  # Only has search tool
        
        target = MockAgent()
        target.name = "automation"
        target.tools = [Mock(__name__="search"), Mock(__name__="execute_code")]  # Has both tools
        target.chat = Mock(return_value="automation response")

        # Create handoff with default intersect mode (secure)
        h = handoff(agent=target)

        # Execute handoff
        result = h.execute_programmatic(source, "automate this task")

        # Verify target agent only gets shared tools (search), not execute_code
        target.chat.assert_called_once()
        call_kwargs = target.chat.call_args.kwargs
        effective_tools = call_kwargs.get("tools", [])
        
        # Should only have the shared "search" tool, not "execute_code"
        tool_names = [t.__name__ for t in effective_tools if hasattr(t, '__name__')]
        assert "search" in tool_names
        assert "execute_code" not in tool_names


class TestHandoffConfigSerialization:
    """Test HandoffConfig serialization with HandoffToolPolicy."""

    def test_handoff_config_to_dict_with_tool_policy(self):
        """Test HandoffConfig.to_dict() includes tool_policy."""
        config = HandoffConfig(
            tool_policy=HandoffToolPolicy(
                mode="passthrough",
                blocked_tools=["dangerous_tool", "another_tool"]
            )
        )
        
        result = config.to_dict()
        
        assert "tool_policy" in result
        assert result["tool_policy"]["mode"] == "passthrough"
        assert result["tool_policy"]["blocked_tools"] == ["dangerous_tool", "another_tool"]

    def test_handoff_config_from_dict_with_tool_policy(self):
        """Test HandoffConfig.from_dict() reconstructs tool_policy."""
        data = {
            "context_policy": "summary",
            "tool_policy": {
                "mode": "intersect",
                "blocked_tools": ["exec_tool"]
            },
            "timeout_seconds": 60.0
        }
        
        config = HandoffConfig.from_dict(data)
        
        assert config.tool_policy.mode == "intersect"
        assert "exec_tool" in config.tool_policy.blocked_tools
        assert config.timeout_seconds == 60.0

    def test_handoff_config_from_dict_missing_tool_policy(self):
        """Test HandoffConfig.from_dict() with missing tool_policy uses default."""
        data = {"timeout_seconds": 30.0}
        
        config = HandoffConfig.from_dict(data)
        
        # Should use default HandoffToolPolicy
        assert config.tool_policy.mode == "intersect"
        assert config.tool_policy.blocked_tools == []


if __name__ == "__main__":
    pytest.main([__file__])