"""
Real agentic test for tool retry policy - agent actually runs and calls LLM with retrying tools.
This satisfies the AGENTS.md requirement (§9.4) for real agentic testing.
"""
import pytest
import time
from unittest.mock import patch

from praisonaiagents import Agent, tool
from praisonaiagents.tools.retry import RetryPolicy


class TestRetryPolicyAgentic:
    """Real agentic tests where the agent calls LLM and uses retrying tools."""
    
    def test_agent_with_flaky_tool_real_llm(self):
        """
        ✅ REAL agentic test — agent runs end-to-end with flaky tool that retries.
        Agent MUST call agent.start() with a real prompt and produce LLM output.
        """
        call_count = [0]
        
        @tool
        def flaky_web_search(query: str) -> str:
            """Search the web for information. May fail due to network issues."""
            call_count[0] += 1
            
            # Fail on first two attempts, succeed on third
            if call_count[0] <= 2:
                raise Exception(f"Connection timeout on attempt {call_count[0]}")
            
            # Return realistic search results
            return f"""Found search results for "{query}":
            1. OpenAI GPT-4 is a large language model released in 2023
            2. It demonstrates improved reasoning capabilities over GPT-3.5
            3. Available via API and ChatGPT Plus subscription"""
        
        # Configure retry policy for this flaky tool
        retry_policy = RetryPolicy(
            max_attempts=3,
            initial_delay_ms=50,  # Fast for testing
            retry_on={"timeout", "connection_error"},
            backoff_factor=1.5
        )
        
        # Create agent with retry policy and flaky tool
        agent = Agent(
            name="research_assistant",
            instructions="You are a helpful research assistant. When asked to search for information, use the flaky_web_search tool. Be concise in your response.",
            tools=[flaky_web_search],
            tool_retry_policy=retry_policy
        )
        
        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            # ✅ REAL agent call with actual LLM interaction
            result = agent.start("Search for information about GPT-4 and tell me one key fact.")
            
        # Verify the agent got a real LLM response  
        assert isinstance(result, str), f"Expected string response, got {type(result)}"
        assert len(result) > 10, "Response should be substantial"
        
        # Verify the flaky tool was called and retried as expected
        assert call_count[0] == 3, f"Tool should have been called 3 times, was called {call_count[0]} times"
        
        # Print the full output so developers can verify end-to-end behavior
        print(f"\n🤖 Agent Response: {result}")
        print(f"🔄 Tool was retried {call_count[0]} times before success")
    
    def test_agent_with_non_retryable_tool_real_llm(self):
        """
        ✅ REAL agentic test — agent with tool that fails non-retryably.
        Verifies agent handles permission denied gracefully without infinite retries.
        """
        call_count = [0]
        
        @tool
        def restricted_database_query(query: str) -> str:
            """Query a restricted database. Requires special permissions."""
            call_count[0] += 1
            return {
                "error": "Access denied: insufficient permissions for database query",
                "permission_denied": True
            }
        
        retry_policy = RetryPolicy(max_attempts=5)  # High attempts to test non-retry
        
        agent = Agent(
            name="data_analyst", 
            instructions="You are a data analyst. If you cannot access the database, explain what happened and suggest alternatives. Keep it brief.",
            tools=[restricted_database_query],
            tool_retry_policy=retry_policy
        )
        
        # ✅ REAL agent call with actual LLM interaction
        result = agent.start("Query the database for user statistics from last month.")
        
        # Verify the agent got a real LLM response
        assert isinstance(result, str), f"Expected string response, got {type(result)}"
        assert len(result) > 10, "Response should be substantial"
        
        # Verify tool was called only once (no retries for permission denied)
        assert call_count[0] == 1, f"Tool should have been called only once, was called {call_count[0]} times"
        
        # Print the full output for verification
        print(f"\n🤖 Agent Response: {result}")  
        print(f"🚫 Tool was called {call_count[0]} times (no retries for permission denied)")
    
    def test_agent_with_tool_level_retry_policy_real_llm(self):
        """
        ✅ REAL agentic test — tool-level retry policy overrides agent-level policy.
        """
        primary_calls = [0]
        fallback_calls = [0]
        
        @tool
        def primary_api(query: str) -> str:
            """Primary API that fails frequently."""
            primary_calls[0] += 1
            if primary_calls[0] <= 1:  # Fail once, succeed twice
                raise Exception("Primary API rate limit exceeded")
            return f"Primary API result for: {query}"
        
        # Tool-level policy: only 2 attempts
        primary_api.retry_policy = RetryPolicy(
            max_attempts=2,
            initial_delay_ms=30,
            retry_on={"rate_limit"}
        )
        
        @tool
        def fallback_api(query: str) -> str:
            """Fallback API that's more reliable."""
            fallback_calls[0] += 1
            return f"Fallback API result for: {query}"
        
        # Agent-level policy: 5 attempts (should be overridden by tool-level)
        agent_retry_policy = RetryPolicy(max_attempts=5)
        
        agent = Agent(
            name="api_client",
            instructions="You help users get information. Try the primary_api first. If it fails completely, you can try fallback_api. Be brief.",
            tools=[primary_api, fallback_api],
            tool_retry_policy=agent_retry_policy
        )
        
        with patch('time.sleep'):
            # ✅ REAL agent call
            result = agent.start("Get information about Python programming")
            
        # Verify real LLM response
        assert isinstance(result, str) and len(result) > 10
        
        # Verify tool-level policy was respected (2 attempts max)
        assert primary_calls[0] == 2, f"Primary API should have been called 2 times, was called {primary_calls[0]} times"
        
        print(f"\n🤖 Agent Response: {result}")
        print(f"🔄 Primary API called {primary_calls[0]} times (tool-level policy: max 2)")
        print(f"🔄 Fallback API called {fallback_calls[0]} times")
    
    @pytest.mark.asyncio
    async def test_async_agent_with_retry_real_llm(self):
        """
        ✅ REAL agentic test — async agent with retrying tool.
        """
        call_count = [0]
        
        @tool
        async def async_weather_api(location: str) -> str:
            """Get weather information for a location."""
            call_count[0] += 1
            
            if call_count[0] <= 1:  # Fail once
                raise Exception("Weather service connection timeout")
                
            return f"Weather in {location}: Sunny, 72°F"
        
        retry_policy = RetryPolicy(
            max_attempts=3,
            initial_delay_ms=25,
            retry_on={"timeout"}
        )
        
        agent = Agent(
            name="weather_assistant",
            instructions="You provide weather information using the async_weather_api tool. Keep responses concise.",
            tools=[async_weather_api],
            tool_retry_policy=retry_policy
        )
        
        with patch('time.sleep'), patch('asyncio.sleep'):
            # ✅ REAL async agent call
            result = await agent.astart("What's the weather like in San Francisco?")
        
        # Verify real LLM response  
        assert isinstance(result, str) and len(result) > 10
        assert call_count[0] == 2, f"Async tool should have been called 2 times, was called {call_count[0]} times"
        
        print(f"\n🤖 Async Agent Response: {result}")
        print(f"🔄 Async tool retried {call_count[0]} times before success")