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
from praisonaiagents.agent.async_safety import DualLock
from praisonaiagents.agent.handoff import (
    HandoffToolPolicy, 
    Handoff, 
    HandoffConfig,
    handoff
)
from praisonaiagents import Agent

def _tool(name):
    """A stand-in tool whose NAME resolves the way a real tool's does.

    Mock is the wrong shape here: _compute_effective_tools reads
    getattr(tool, 'name', getattr(tool, '__name__', ...)), and a Mock
    AUTO-CREATES .name -- so every mock tool got a unique Mock object as its
    name and the intersection was always empty. A plain function has no .name,
    so the __name__ fallback runs, which is what a real callable tool does.
    """
    def fn():
        return name
    fn.__name__ = name
    return fn




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
        source_agent.tools = [_tool("shared_tool"), _tool("source_only")]

        # Mock target agent with tools
        target_agent = Mock()
        target_agent.name = "target"
        target_agent.tools = [_tool("shared_tool"), _tool("target_only")]

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
        source_agent.tools = [_tool("source_only")]

        # Mock target agent with different tools
        target_agent = Mock()
        target_agent.name = "target" 
        target_agent.tools = [_tool("target_only")]

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
        tool1 = _tool("safe_tool")
        tool2 = _tool("dangerous_tool")
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
        source_agent.tools = [_tool("shared_tool")]
        # _prepare_context does getattr(source_agent, 'chat_history', []) and
        # then iterates it. A Mock always HAS the attribute, so the [] default
        # never applies and the handoff died on "'Mock' object is not iterable"
        # -- caught and logged, leaving chat uncalled and the assertion below
        # reading like a broken tool boundary.
        source_agent.chat_history = []

        target_agent = Mock()
        target_agent.name = "target"
        target_agent.tools = [_tool("shared_tool"), _tool("private_tool")]
        target_agent.chat = Mock(return_value="response")
        target_agent.chat_history = []
        # _get_handoff_seed_lock does getattr(agent, '_handoff_seed_lock', None)
        # and creates a real DualLock only when that is None. A Mock returns a
        # Mock, so the seeding context manager got something that is not a
        # context manager at all.
        target_agent._handoff_seed_lock = DualLock()

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
        """tools=None inherits the agent's tools; tools=[] denies them all.

        This bound the REAL _format_tools_for_completion to a Mock and then
        asserted the MOCK's own _format_tools_for_completion had been called --
        which could only pass if the real method delegated to itself. It does
        not (that would recurse); it assigns `tools = self.tools` and formats
        them. So the assertion could never hold, and the Mock made the failure
        look like a security regression rather than a test that tested nothing.

        Uses a real Agent and asserts the OUTPUT, which is the security property
        that matters: None must not silently become "no tools", and an explicit
        empty list must not silently become "all the agent's tools".
        """
        from praisonaiagents import Agent

        def agent_tool(x: str = "") -> str:
            """A tool."""
            return x

        agent = Agent(name="t", instructions="x", tools=[agent_tool])

        inherited = agent._format_tools_for_completion(tools=None)
        assert [t["function"]["name"] for t in inherited] == ["agent_tool"]

        # The control: the same call with an explicit empty list denies them.
        assert agent._format_tools_for_completion(tools=[]) == []

    def test_agent_chat_tools_empty_list_enforces_boundary(self):
        """Test that tools=[] in agent.chat() enforces empty tool boundary."""
        # Create mock agent with tools
        agent = Mock()
        agent.tools = [_tool("agent_tool")]
        
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
        
        # Two DISTINCT agents. MockAgent() is a patched class, so calling it
        # twice returns the SAME return_value -- source and target were one
        # object, target.tools overwrote source.tools, and intersecting a set
        # with itself returned both tools. That looked like the tool boundary
        # failing when it was the test collapsing two agents into one.
        source = Mock()
        source.name = "orchestrator"
        source.tools = [_tool("search")]  # Only has search tool
        # See the sync test above: _prepare_context iterates chat_history, and a
        # Mock's auto-created attribute is not iterable.
        source.chat_history = []

        target = Mock()
        target.name = "automation"
        target.tools = [_tool("search"), _tool("execute_code")]  # Has both tools
        target.chat = Mock(return_value="automation response")
        target.chat_history = []
        # _get_handoff_seed_lock only builds a real DualLock when
        # getattr(agent, '_handoff_seed_lock', None) is None, which a Mock never is.
        target._handoff_seed_lock = DualLock()

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