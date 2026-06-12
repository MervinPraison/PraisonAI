"""
Tests for @tool(retry_policy=...) decorator functionality.
"""
from praisonaiagents import tool, Agent
from praisonaiagents.tools.retry import RetryPolicy


class TestToolDecoratorRetryPolicy:
    """Test @tool decorator with retry_policy parameter."""
    
    def test_tool_decorator_with_retry_policy(self):
        """Test @tool decorator accepts retry_policy parameter."""
        retry_policy = RetryPolicy(max_attempts=5, initial_delay_ms=500)
        
        @tool(retry_policy=retry_policy)
        def test_tool(query: str) -> str:
            """A test tool with retry policy."""
            return f"Result for {query}"
        
        assert hasattr(test_tool, 'retry_policy')
        assert test_tool.retry_policy == retry_policy
        assert test_tool.retry_policy.max_attempts == 5
        assert test_tool.retry_policy.initial_delay_ms == 500
    
    def test_tool_decorator_without_retry_policy(self):
        """Test @tool decorator works without retry_policy (default None)."""
        @tool
        def test_tool(query: str) -> str:
            """A test tool without retry policy."""
            return f"Result for {query}"
        
        assert hasattr(test_tool, 'retry_policy')
        assert test_tool.retry_policy is None
    
    def test_tool_with_retry_policy_used_by_agent(self):
        """Test that agent respects tool-level retry policy."""
        tool_retry_policy = RetryPolicy(max_attempts=7, initial_delay_ms=300)
        
        @tool(retry_policy=tool_retry_policy)
        def special_tool(query: str) -> str:
            """Special tool with custom retry policy."""
            return f"Special result for {query}"
        
        # Agent with different retry policy
        agent_retry_policy = RetryPolicy(max_attempts=2, initial_delay_ms=1000)
        agent = Agent(
            name="test_agent",
            instructions="Test agent",
            tools=[special_tool],
            tool_retry_policy=agent_retry_policy
        )
        
        # Should get tool-level policy (higher precedence)
        resolved_policy = agent._get_tool_retry_policy("special_tool")
        assert resolved_policy == tool_retry_policy
        assert resolved_policy.max_attempts == 7
        assert resolved_policy.initial_delay_ms == 300
    
    def test_mixed_tools_retry_policies(self):
        """Test agent with mix of tools - some with retry policy, some without."""
        policy_a = RetryPolicy(max_attempts=3)
        policy_b = RetryPolicy(max_attempts=6)
        
        @tool(retry_policy=policy_a)
        def tool_a(query: str) -> str:
            return f"A: {query}"
        
        @tool(retry_policy=policy_b)
        def tool_b(query: str) -> str:
            return f"B: {query}"
        
        @tool  # No retry policy
        def tool_c(query: str) -> str:
            return f"C: {query}"
        
        agent_policy = RetryPolicy(max_attempts=4)
        agent = Agent(
            name="test_agent",
            instructions="Test agent",
            tools=[tool_a, tool_b, tool_c],
            tool_retry_policy=agent_policy
        )
        
        # Tool A should use its own policy
        policy_a_resolved = agent._get_tool_retry_policy("tool_a")
        assert policy_a_resolved == policy_a
        assert policy_a_resolved.max_attempts == 3
        
        # Tool B should use its own policy
        policy_b_resolved = agent._get_tool_retry_policy("tool_b")
        assert policy_b_resolved == policy_b
        assert policy_b_resolved.max_attempts == 6
        
        # Tool C should use agent policy (fallback)
        policy_c_resolved = agent._get_tool_retry_policy("tool_c")
        assert policy_c_resolved == agent_policy
        assert policy_c_resolved.max_attempts == 4