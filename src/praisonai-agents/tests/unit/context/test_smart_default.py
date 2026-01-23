"""Tests for smart default context behavior.

When context=None (not explicitly set), context management should be
automatically enabled when tools are present, disabled otherwise.
"""


class TestSmartDefaultContext:
    """Tests for smart default context behavior."""
    
    def test_context_enabled_when_tools_present(self):
        """Context should be auto-enabled when agent has tools."""
        from praisonaiagents import Agent
        
        def sample_tool(query: str) -> str:
            """A sample tool."""
            return f"Result for {query}"
        
        # Create agent with tools but no explicit context setting
        agent = Agent(
            instructions="You are helpful",
            tools=[sample_tool],
            # context=None (default) - should auto-enable
        )
        
        # Context param should be True (auto-enabled)
        assert agent._context_param is True, "Context should be auto-enabled when tools present"
    
    def test_context_disabled_when_no_tools(self):
        """Context should remain disabled when agent has no tools."""
        from praisonaiagents import Agent
        
        # Create agent without tools
        agent = Agent(
            instructions="You are helpful",
            # No tools, context=None (default)
        )
        
        # Context param should remain None/False (disabled)
        assert agent._context_param is None or agent._context_param is False
    
    def test_explicit_context_false_respected(self):
        """Explicit context=False should be respected even with tools."""
        from praisonaiagents import Agent
        
        def sample_tool(query: str) -> str:
            """A sample tool."""
            return f"Result for {query}"
        
        # Create agent with tools but explicitly disable context
        agent = Agent(
            instructions="You are helpful",
            tools=[sample_tool],
            context=False,  # Explicitly disabled
        )
        
        # Context param should be False (user's choice)
        assert agent._context_param is False
    
    def test_explicit_context_true_respected(self):
        """Explicit context=True should be respected even without tools."""
        from praisonaiagents import Agent
        
        # Create agent without tools but explicitly enable context
        agent = Agent(
            instructions="You are helpful",
            context=True,  # Explicitly enabled
        )
        
        # Context param should be True (user's choice)
        assert agent._context_param is True
    
    def test_context_manager_config_respected(self):
        """ManagerConfig should be respected regardless of tools."""
        from praisonaiagents import Agent
        from praisonaiagents.context.manager import ManagerConfig
        
        config = ManagerConfig(auto_compact=True, compact_threshold=0.7)
        
        # Create agent with explicit config
        agent = Agent(
            instructions="You are helpful",
            context=config,
        )
        
        # Context param should be the config
        assert agent._context_param is config
    
    def test_context_auto_enabled_with_mcp_tools(self):
        """Context should be auto-enabled with MCP tools."""
        from praisonaiagents import Agent
        
        # Mock MCP-like tool (has tools attribute)
        class MockMCP:
            def __init__(self):
                self.tools = ["tool1", "tool2"]
        
        mcp = MockMCP()
        
        # Create agent with MCP tools
        agent = Agent(
            instructions="You are helpful",
            tools=[mcp],
        )
        
        # Context param should be True (auto-enabled)
        assert agent._context_param is True


class TestSmartDefaultContextManager:
    """Tests for context manager lazy initialization with smart default."""
    
    def test_context_manager_lazy_init_with_tools(self):
        """Context manager should lazy init when tools present."""
        from praisonaiagents import Agent
        
        def sample_tool(query: str) -> str:
            """A sample tool."""
            return f"Result for {query}"
        
        agent = Agent(
            instructions="You are helpful",
            tools=[sample_tool],
        )
        
        # Manager should not be initialized yet
        assert agent._context_manager is None
        assert agent._context_manager_initialized is False
        
        # Access manager to trigger lazy init
        cm = agent.context_manager
        
        # Now it should be initialized
        assert agent._context_manager_initialized is True
        assert cm is not None
    
    def test_context_manager_none_without_tools(self):
        """Context manager should be None when no tools and no explicit context."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="You are helpful",
        )
        
        # Access manager
        cm = agent.context_manager
        
        # Should be None (no context management)
        assert cm is None


class TestSmartDefaultPerformance:
    """Tests to verify smart default has no performance impact."""
    
    def test_no_import_overhead_without_tools(self):
        """No context imports should happen when no tools."""
        from praisonaiagents import Agent
        
        # Create agent without tools
        agent = Agent(instructions="You are helpful")
        
        # Context manager should not be accessed/initialized
        assert agent._context_manager is None
        assert agent._context_manager_initialized is False
    
    def test_lazy_init_only_when_accessed(self):
        """Context manager should only init when actually accessed."""
        from praisonaiagents import Agent
        
        def sample_tool(query: str) -> str:
            """A sample tool."""
            return f"Result for {query}"
        
        agent = Agent(
            instructions="You are helpful",
            tools=[sample_tool],
        )
        
        # Even with tools, manager should not be initialized until accessed
        assert agent._context_manager is None
        assert agent._context_manager_initialized is False
        
        # Only after access should it initialize
        _ = agent.context_manager
        assert agent._context_manager_initialized is True
