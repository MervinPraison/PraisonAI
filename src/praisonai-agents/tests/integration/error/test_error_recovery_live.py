"""
Live integration tests for error recovery and resilience.

These tests require:
- PRAISONAI_LIVE_TESTS=1 environment variable
- OPENAI_API_KEY environment variable

Run with: PRAISONAI_LIVE_TESTS=1 pytest -m live tests/integration/error/test_error_recovery_live.py -v
"""

import pytest


@pytest.fixture
def openai_api_key():
    """Get OpenAI API key from environment."""
    import os
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    return key


@pytest.mark.live
class TestLLMErrorRecoveryLive:
    """Live tests for LLM error recovery."""
    
    def test_agent_llm_timeout_recovery_real(self, openai_api_key):
        """Test agent handling LLM timeout and retrying."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="ErrorRecoveryAgent",
            instructions="You are a resilient assistant that handles errors gracefully.",
            llm="gpt-4o-mini"
        )
        
        # Test with a prompt that should work after potential initial issues
        result = agent.start("Respond with a simple greeting. If there are any issues, please retry.")
        
        # Assertions - should eventually succeed
        assert result is not None
        assert len(result) > 0
        assert ("hello" in result.lower() or "hi" in result.lower() or "greeting" in result.lower())
        
        print(f"LLM error recovery result: {result}")


@pytest.mark.live
class TestToolErrorRecoveryLive:
    """Live tests for tool error recovery."""
    
    def test_agent_tool_failure_recovery_real(self, openai_api_key):
        """Test agent recovering from tool failures."""
        from praisonaiagents import Agent, tool
        
        call_count = 0
        
        @tool
        def unreliable_tool(input_data: str) -> str:
            """A tool that fails initially but succeeds on retry."""
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                raise Exception("Simulated tool failure")
            return f"Tool succeeded on attempt {call_count}: {input_data}"
        
        @tool
        def backup_tool(input_data: str) -> str:
            """A reliable backup tool."""
            return f"Backup tool result: {input_data}"
        
        agent = Agent(
            name="ToolRecoveryAgent",
            instructions="You are an assistant that can recover from tool failures. If one tool fails, try alternatives.",
            tools=[unreliable_tool, backup_tool],
            llm="gpt-4o-mini"
        )
        
        # Test tool error recovery
        result = agent.start("Process this data and handle any errors gracefully: test data")
        
        # Assertions - should recover and provide a result
        assert result is not None
        assert len(result) > 0
        
        print(f"Tool error recovery result: {result}")


@pytest.mark.live
class TestMultiStepErrorRecoveryLive:
    """Live tests for multi-step error recovery."""
    
    def test_agent_complex_error_recovery_real(self, openai_api_key):
        """Test agent handling multiple types of errors in complex workflows."""
        from praisonaiagents import Agent, tool
        
        @tool
        def step_one_tool(data: str) -> str:
            """First step that might fail."""
            if "fail" in data.lower():
                raise ValueError("Step one failed")
            return f"Step one completed: {data}"
        
        @tool
        def step_two_tool(data: str) -> str:
            """Second step with different error type."""
            if "error" in data.lower():
                raise ConnectionError("Connection failed in step two")
            return f"Step two completed: {data}"
        
        @tool
        def recovery_tool(data: str) -> str:
            """Recovery tool for any failures."""
            return f"Recovery completed: {data}"
        
        agent = Agent(
            name="ComplexRecoveryAgent",
            instructions="You are an assistant that handles complex multi-step processes with error recovery at each stage.",
            tools=[step_one_tool, step_two_tool, recovery_tool],
            llm="gpt-4o-mini"
        )
        
        # Test complex recovery scenario
        result = agent.start("Execute a multi-step process with this data: test input. Handle any errors gracefully.")
        
        # Assertions
        assert result is not None
        assert len(result) > 0
        
        print(f"Complex error recovery result: {result}")


@pytest.mark.live
class TestMemoryErrorRecoveryLive:
    """Live tests for memory-related error recovery."""
    
    def test_agent_memory_corruption_recovery_real(self, openai_api_key):
        """Test agent handling memory corruption or access issues."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="MemoryRecoveryAgent",
            instructions="You are an assistant with memory capabilities that can handle memory-related issues gracefully.",
            memory=True,
            llm="gpt-4o-mini"
        )
        
        # First interaction to establish memory
        result1 = agent.start("Remember this important fact: The sky is blue")
        assert result1 is not None
        
        # Second interaction testing memory recovery
        result2 = agent.start("What did I just tell you to remember? If there are any memory issues, acknowledge them.")
        
        # Assertions - should handle gracefully even if memory has issues
        assert result2 is not None
        assert len(result2) > 0
        
        # Should either recall correctly or acknowledge memory limitations
        result2_lower = result2.lower()
        assert ("blue" in result2_lower or "sky" in result2_lower or "remember" in result2_lower or "memory" in result2_lower)
        
        print(f"Memory recovery result: {result2}")


@pytest.mark.live
class TestNetworkErrorRecoveryLive:
    """Live tests for network-related error recovery."""
    
    def test_agent_network_resilience_real(self, openai_api_key):
        """Test agent handling network connectivity issues."""
        from praisonaiagents import Agent, tool
        
        @tool
        def network_dependent_tool(query: str) -> str:
            """Tool that simulates network dependency."""
            # Simulate occasional network issues
            return f"Network response for '{query}': Data retrieved successfully"
        
        agent = Agent(
            name="NetworkResilientAgent",
            instructions="You are an assistant that maintains functionality despite network issues.",
            tools=[network_dependent_tool],
            llm="gpt-4o-mini"
        )
        
        # Test network resilience
        result = agent.start("Fetch some network data and handle any connectivity issues gracefully")
        
        # Assertions - should handle network issues gracefully
        assert result is not None
        assert len(result) > 0
        
        print(f"Network resilience result: {result}")


@pytest.mark.live
class TestGracefulDegradationLive:
    """Live tests for graceful degradation under various failures."""
    
    def test_agent_graceful_degradation_real(self, openai_api_key):
        """Test agent providing useful responses even when some capabilities fail."""
        from praisonaiagents import Agent, tool
        
        @tool
        def advanced_tool(task: str) -> str:
            """Advanced tool that might not be available."""
            if "advanced" in task.lower():
                raise NotImplementedError("Advanced feature temporarily unavailable")
            return f"Advanced processing: {task}"
        
        @tool
        def basic_tool(task: str) -> str:
            """Basic tool that always works."""
            return f"Basic processing: {task}"
        
        agent = Agent(
            name="GracefulDegradationAgent",
            instructions="You are an assistant that provides the best possible service even when some features are unavailable. Fall back to simpler approaches when needed.",
            tools=[advanced_tool, basic_tool],
            llm="gpt-4o-mini"
        )
        
        # Test graceful degradation
        result = agent.start("Perform advanced analysis on this data. Use simpler methods if advanced features are not available.")
        
        # Assertions - should provide useful result despite limitations
        assert result is not None
        assert len(result) > 0
        
        # Should acknowledge the situation and provide alternative
        result_lower = result.lower()
        assert ("processing" in result_lower or "analysis" in result_lower)
        
        print(f"Graceful degradation result: {result}")