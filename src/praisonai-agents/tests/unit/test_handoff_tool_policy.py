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


def _tool(tool_name):
    """A stand-in tool whose name the policy can actually read.

    _tool("x") is not enough: _compute_effective_tools resolves a name
    with getattr(tool, 'name', getattr(tool, '__name__', ...)), and a bare Mock
    auto-creates `.name` as a fresh Mock object. Every tool therefore had a
    unique, non-string "name", so intersect mode found no overlap at all and
    blocked-tool lists never matched. Set both attributes explicitly.
    """
    tool = Mock()
    tool.__name__ = tool_name
    tool.name = tool_name
    return tool



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
        target_agent.tools = [_tool("tool1"), _tool("tool2")]

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

    def test_handoff_execution_respects_tool_boundary_sync(self):
        """A programmatic handoff hands the target only the intersected tools.

        Built on real Agents. A bare Mock agent cannot carry this path: the
        source's chat_history is sliced into prior_messages (a Mock is not
        iterable) and the runtime resolution enters a context manager (a Mock
        does not support the protocol). Each failure was swallowed by
        execute_programmatic's except clause and surfaced only as "chat was
        never called", hiding the real cause. Only chat() is stubbed, so the
        tool-policy computation under test runs for real.
        """
        def shared_tool(q: str) -> str:
            """Shared by both agents."""
            return q

        def private_tool(q: str) -> str:
            """Only the target has this one."""
            return q

        source_agent = Agent(name="source", instructions="x", tools=[shared_tool])
        target_agent = Agent(name="target", instructions="x",
                             tools=[shared_tool, private_tool])
        target_agent.chat = Mock(return_value="response")

        config = HandoffConfig(tool_policy=HandoffToolPolicy(mode="intersect"))
        handoff_obj = Handoff(agent=target_agent, config=config)

        result = handoff_obj.execute_programmatic(source_agent, "test prompt")

        assert result.success, f"handoff failed: {getattr(result, 'error', None)}"
        target_agent.chat.assert_called_once()
        effective_tools = target_agent.chat.call_args.kwargs["tools"]
        assert [getattr(t_, "__name__", None) for t_ in effective_tools] == ["shared_tool"], (
            "the target must receive only the tools both agents share"
        )

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

        Rewritten against a real Agent. The original could not pass: it
        replaced agent._format_tools_for_completion with a Mock, bound the REAL
        method, then asserted the Mock had been called -- the real method never
        calls itself. It also left _cache_get as a bare Mock, which returns a
        truthy Mock, so the cache-hit branch ran and
        `cached_tools, cached_metadata = cached_entry` raised TypeError first.
        And a Mock-based agent cannot produce a formatted payload at all: the
        JSON-serialisability check rejects it, so the result was [] whatever
        the tools were. The behaviour itself is correct and worth asserting.
        """
        def agent_tool(query: str) -> str:
            """A real callable -- Mock tools are not JSON serializable."""
            return query

        agent = Agent(name="boundary", instructions="x", tools=[agent_tool])

        inherited = agent._format_tools_for_completion(None)
        assert [f["function"]["name"] for f in inherited] == ["agent_tool"], (
            "tools=None must inherit the agent's configured tools"
        )
        assert agent._format_tools_for_completion([]) == [], (
            "tools=[] must deny every tool, not fall back to the agent's"
        )

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

    def test_handoff_tool_boundary_end_to_end(self):
        """End to end: the target must not gain a tool the source lacks.

        Rebuilt on real Agents for the same reason as the sync test above -- a
        Mock agent cannot carry the handoff path, and its failures were
        swallowed and reported as an unrelated assertion.
        """
        def search(q: str) -> str:
            """Both agents have this."""
            return q

        def execute_code(q: str) -> str:
            """Only the target has this -- it must not cross the boundary."""
            return q

        source = Agent(name="orchestrator", instructions="x", tools=[search])
        target = Agent(name="automation", instructions="x",
                       tools=[search, execute_code])
        target.chat = Mock(return_value="automation response")

        h = handoff(agent=target)          # default policy is intersect
        result = h.execute_programmatic(source, "automate this task")

        assert result.success, f"handoff failed: {getattr(result, 'error', None)}"
        target.chat.assert_called_once()
        effective_tools = target.chat.call_args.kwargs.get("tools", [])
        tool_names = [t_.__name__ for t_ in effective_tools if hasattr(t_, "__name__")]
        assert "search" in tool_names
        assert "execute_code" not in tool_names, (
            "a tool the source does not have must not cross the handoff boundary"
        )


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