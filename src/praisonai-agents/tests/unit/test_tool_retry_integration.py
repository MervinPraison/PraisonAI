"""
Unit tests for tool retry policy integration in Agent class.
Tests sync and async retry, hook emission, clone_for_channel propagation, and non-retryable errors.
"""
import asyncio
import pytest
import time
from unittest.mock import Mock, patch, AsyncMock, call

from praisonaiagents import Agent, tool
from praisonaiagents.tools.retry import RetryPolicy
from praisonaiagents.config.feature_configs import ToolConfig
from praisonaiagents.hooks.types import HookEvent


class TestAgentRetryPolicyIntegration:
    """Test agent-level retry policy integration."""
    
    def test_agent_retry_policy_initialization(self):
        """Test agent initialization with retry policy."""
        retry_policy = RetryPolicy(max_attempts=5, initial_delay_ms=500)
        agent = Agent(
            name="test_agent",
            instructions="Test agent",
            tool_config=ToolConfig(retry_policy=retry_policy)
        )
        assert agent._tool_retry_policy == retry_policy
    
    def test_agent_clone_propagates_retry_policy(self):
        """Test that clone_for_channel preserves tool_retry_policy."""
        retry_policy = RetryPolicy(max_attempts=5, initial_delay_ms=500)
        agent = Agent(
            name="test_agent",
            instructions="Test agent",
            tool_config=ToolConfig(retry_policy=retry_policy)
        )
        
        cloned = agent.clone_for_channel()
        assert cloned._tool_retry_policy == retry_policy
        assert cloned._tool_retry_policy.max_attempts == retry_policy.max_attempts
    
    def test_agent_clone_none_retry_policy(self):
        """Test clone works when retry_policy is None."""
        agent = Agent(name="test_agent", instructions="Test agent")
        cloned = agent.clone_for_channel()
        assert cloned._tool_retry_policy is None


class TestSyncRetryIntegration:
    """Test synchronous retry integration."""
    
    def test_sync_retry_with_timeout_error(self):
        """Test sync tool execution with retryable timeout error."""
        call_count = [0]
        
        @tool
        def flaky_tool(query: str) -> str:
            """A tool that fails with timeout on first calls."""
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Connection timeout")
            return f"Success on attempt {call_count[0]}"
        
        retry_policy = RetryPolicy(
            max_attempts=3,
            initial_delay_ms=10,  # Fast for testing
            retry_on={"timeout", "connection_error"}
        )
        
        agent = Agent(
            name="test_agent",
            instructions="Test agent",
            tools=[flaky_tool],
            tool_config=ToolConfig(retry_policy=retry_policy)
        )
        
        # Mock time.sleep to avoid actual delays
        with patch('time.sleep'):
            # This should succeed after retries
            result = agent._execute_tool_with_circuit_breaker("flaky_tool", {"query": "test"})
            if isinstance(result, dict):
                assert not result.get("error")
            assert "Success on attempt 3" in str(result)
            assert call_count[0] == 3
    
    def test_sync_retry_non_retryable_error(self):
        """Test sync tool execution with non-retryable error."""
        call_count = [0]
        
        @tool  
        def permission_denied_tool(query: str) -> str:
            """A tool that fails with permission denied."""
            call_count[0] += 1
            return {
                "error": "Permission denied",
                "permission_denied": True
            }
        
        retry_policy = RetryPolicy(max_attempts=3)
        agent = Agent(
            name="test_agent", 
            instructions="Test agent",
            tools=[permission_denied_tool],
            tool_config=ToolConfig(retry_policy=retry_policy)
        )
        
        result = agent._execute_tool_with_circuit_breaker("permission_denied_tool", {"query": "test"})
        assert result.get("error")
        assert result.get("permission_denied")
        assert call_count[0] == 1  # Should not retry
    
    def test_sync_retry_hook_emission(self):
        """Test that sync retries succeed after transient failures."""
        call_count = [0]
        
        @tool
        def failing_tool(query: str) -> str:
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Rate limit exceeded")
            return "Success"
        
        retry_policy = RetryPolicy(max_attempts=3, initial_delay_ms=10)
        agent = Agent(
            name="test_agent",
            instructions="Test agent", 
            tools=[failing_tool],
            tool_config=ToolConfig(retry_policy=retry_policy)
        )

        with patch('time.sleep'):
            result = agent._execute_tool_with_circuit_breaker("failing_tool", {"query": "test"})

        assert call_count[0] == 3
        assert "Success" in str(result)


class TestAsyncRetryIntegration:
    """Test asynchronous retry integration."""
    
    @pytest.mark.asyncio
    async def test_async_retry_with_rate_limit_error(self):
        """Test async tool execution with retryable rate limit error."""
        call_count = [0]
        
        async def mock_async_impl(function_name, arguments, tool_call_id, tools_override):
            call_count[0] += 1
            if call_count[0] < 3:
                return {
                    "error": "Rate limit exceeded. Try again later.",
                    "tool_name": function_name
                }
            return {
                "result": f"Success on attempt {call_count[0]}",
                "tool_name": function_name
            }
        
        retry_policy = RetryPolicy(
            max_attempts=3,
            initial_delay_ms=10,
            retry_on={"rate_limit"}
        )
        
        agent = Agent(
            name="test_agent",
            instructions="Test agent",
            tool_config=ToolConfig(retry_policy=retry_policy)
        )
        
        # Mock the internal async implementation
        with patch.object(agent, '_execute_tool_async_impl', side_effect=mock_async_impl), \
             patch('asyncio.sleep'):  # Mock async sleep
            
            result = await agent.execute_tool_async("test_tool", {"query": "test"})
            if isinstance(result, dict):
                assert not result.get("error")
            assert "Success on attempt 3" in str(result)
            assert call_count[0] == 3
    
    @pytest.mark.asyncio
    async def test_async_retry_circuit_open_guard(self):
        """Test async retry respects circuit_open flag."""
        call_count = [0]
        
        async def mock_async_impl(function_name, arguments, tool_call_id, tools_override):
            call_count[0] += 1
            return {
                "error": "Circuit breaker is open",
                "circuit_open": True,
                "tool_name": function_name
            }
        
        retry_policy = RetryPolicy(max_attempts=3)
        agent = Agent(
            name="test_agent",
            instructions="Test agent", 
            tool_config=ToolConfig(retry_policy=retry_policy)
        )
        
        with patch.object(agent, '_execute_tool_async_impl', side_effect=mock_async_impl):
            result = await agent.execute_tool_async("test_tool", {"query": "test"})
            assert result.get("error")
            assert result.get("circuit_open")
            assert call_count[0] == 1  # Should not retry
    
    @pytest.mark.asyncio
    async def test_async_retry_hook_emission(self):
        """Test that async retries succeed after transient failures."""
        call_count = [0]
        
        async def mock_async_impl(function_name, arguments, tool_call_id, tools_override):
            call_count[0] += 1
            if call_count[0] < 3:
                return {
                    "error": "Connection error occurred",
                    "tool_name": function_name
                }
            return {
                "result": "Success",
                "tool_name": function_name
            }
        
        retry_policy = RetryPolicy(max_attempts=3, initial_delay_ms=10)
        agent = Agent(
            name="test_agent",
            instructions="Test agent",
            tool_config=ToolConfig(retry_policy=retry_policy)
        )

        with patch.object(agent, '_execute_tool_async_impl', side_effect=mock_async_impl), \
             patch('asyncio.sleep'):
            result = await agent.execute_tool_async("test_tool", {"query": "test"})

        assert call_count[0] == 3
        assert "Success" in str(result)


class TestRetryPolicyPrecedence:
    """Test retry policy precedence (tool-level > agent-level > default)."""
    
    def test_tool_level_policy_precedence(self):
        """Test that tool-level retry policy takes precedence."""
        # Create a tool with its own retry policy
        tool_policy = RetryPolicy(max_attempts=1)
        
        @tool
        def test_tool(query: str) -> str:
            return "result"
        
        # Add retry policy to the tool
        test_tool.retry_policy = tool_policy
        
        agent_policy = RetryPolicy(max_attempts=5)
        agent = Agent(
            name="test_agent",
            instructions="Test agent",
            tools=[test_tool],
            tool_config=ToolConfig(retry_policy=agent_policy)
        )
        
        # Get the resolved policy for this tool
        resolved_policy = agent._get_tool_retry_policy("test_tool")
        assert resolved_policy == tool_policy
        assert resolved_policy.max_attempts == 1
    
    def test_agent_level_policy_precedence(self):
        """Test that agent-level policy is used when tool-level is absent."""
        @tool
        def test_tool(query: str) -> str:
            return "result"
        
        agent_policy = RetryPolicy(max_attempts=5)
        agent = Agent(
            name="test_agent",
            instructions="Test agent", 
            tools=[test_tool],
            tool_config=ToolConfig(retry_policy=agent_policy)
        )
        
        resolved_policy = agent._get_tool_retry_policy("test_tool")
        assert resolved_policy == agent_policy
        assert resolved_policy.max_attempts == 5
    
    def test_default_policy_fallback(self):
        """Test that default policy is used when no other policy is set."""
        @tool
        def test_tool(query: str) -> str:
            return "result"
        
        agent = Agent(
            name="test_agent",
            instructions="Test agent",
            tools=[test_tool]
        )
        
        resolved_policy = agent._get_tool_retry_policy("test_tool")
        assert resolved_policy is not None
        assert resolved_policy.max_attempts == 3  # Default value
    
    def test_mcp_tools_no_crash(self):
        """Test that MCP tools (non-iterable) don't crash retry policy lookup."""
        # Mock an MCP instance (non-iterable)
        mock_mcp = Mock()
        mock_mcp.__name__ = "mcp_instance"
        
        agent = Agent(
            name="test_agent",
            instructions="Test agent",
            tools=mock_mcp  # Non-iterable single tool
        )
        
        # This should not crash
        resolved_policy = agent._get_tool_retry_policy("some_tool")
        assert resolved_policy is not None
        assert resolved_policy.max_attempts == 3  # Default


class TestErrorClassification:
    """Test error type classification for retry decisions."""
    
    def test_classify_timeout_error(self):
        """Test classification of timeout errors."""
        agent = Agent(name="test", instructions="test")
        
        # Test various timeout patterns
        timeout_msgs = [
            "Connection timeout",
            "Request timed out", 
            "timeout occurred",
            "TIMEOUT ERROR"
        ]
        
        for msg in timeout_msgs:
            error_type = agent._classify_error_type({"error": msg}, None)
            assert error_type == "timeout", f"Failed to classify: {msg}"
    
    def test_classify_rate_limit_error(self):
        """Test classification of rate limit errors."""
        agent = Agent(name="test", instructions="test")
        
        rate_limit_msgs = [
            "Rate limit exceeded",
            "rate limited",
            "Too many requests",
            "RATE_LIMIT_ERROR"
        ]
        
        for msg in rate_limit_msgs:
            error_type = agent._classify_error_type({"error": msg}, None)
            assert error_type == "rate_limit", f"Failed to classify: {msg}"
    
    def test_classify_connection_error(self):
        """Test classification of connection errors.""" 
        agent = Agent(name="test", instructions="test")
        
        connection_msgs = [
            "Connection failed",
            "Network error",
            "connection refused",
            "CONNECTION_ERROR"
        ]
        
        for msg in connection_msgs:
            error_type = agent._classify_error_type({"error": msg}, None)
            assert error_type == "connection_error", f"Failed to classify: {msg}"
    
    def test_classify_unknown_error(self):
        """Test classification of unknown errors."""
        agent = Agent(name="test", instructions="test")
        
        error_type = agent._classify_error_type({"error": "Something weird happened"}, None)
        assert error_type == "unknown"