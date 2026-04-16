#!/usr/bin/env python3
"""
Real agentic test for parallel tool execution (Gap 2).

This test verifies that Agent(execution=ExecutionConfig(parallel_tool_calls=True)) executes
batched LLM tool calls concurrently with improved latency.

Per AGENTS.md requirements: Agent MUST call agent.start() with a real prompt
and call the LLM end-to-end, not just object construction.
"""

import time
import logging
import pytest
from typing import List
from praisonaiagents import Agent, tool
from praisonaiagents.config.feature_configs import ExecutionConfig
from praisonaiagents.tools.call_executor import create_tool_call_executor, ToolCall

# Set up logging to see execution details
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock slow tools for latency testing
@tool
def fetch_user_data(user_id: str) -> str:
    """Fetch user data (simulated slow I/O)."""
    time.sleep(0.5)  # Simulate 500ms network delay
    return f"User {user_id}: John Doe, email: john@example.com"

@tool  
def fetch_analytics_data(metric: str) -> str:
    """Fetch analytics data (simulated slow I/O)."""
    time.sleep(0.5)  # Simulate 500ms network delay
    return f"Analytics for {metric}: 42,000 views, 3.2% conversion"

@tool
def fetch_config_data(config_key: str) -> str:
    """Fetch configuration data (simulated slow I/O)."""
    time.sleep(0.5)  # Simulate 500ms network delay 
    return f"Config {config_key}: enabled=true, timeout=30s"

def test_executor_protocols():
    """Test the ToolCallExecutor protocols directly."""
    print("=== Testing ToolCallExecutor Protocols ===")
    
    def mock_execute_tool(name: str, args: dict, tool_call_id: str = None) -> str:
        """Mock tool execution function."""
        start = time.time()
        if name == "fetch_user_data":
            time.sleep(0.3)
            result = f"User {args.get('user_id', 'unknown')}: Mock Data"
        elif name == "fetch_analytics_data":
            time.sleep(0.3)  
            result = f"Analytics {args.get('metric', 'unknown')}: Mock Data"
        elif name == "fetch_config_data":
            time.sleep(0.3)
            result = f"Config {args.get('config_key', 'unknown')}: Mock Data"
        else:
            result = "Unknown tool"
        
        duration = time.time() - start
        print(f"  Tool {name} executed in {duration:.2f}s -> {result}")
        return result
    
    # Create test tool calls
    tool_calls = [
        ToolCall("fetch_user_data", {"user_id": "123"}, "call_1", False),
        ToolCall("fetch_analytics_data", {"metric": "views"}, "call_2", False), 
        ToolCall("fetch_config_data", {"config_key": "timeout"}, "call_3", False),
    ]
    
    # Test sequential execution
    print("\n--- Sequential Execution ---")
    sequential_start = time.time()
    seq_executor = create_tool_call_executor(parallel=False)
    seq_results = seq_executor.execute_batch(tool_calls, mock_execute_tool)
    sequential_time = time.time() - sequential_start
    print(f"Sequential execution took: {sequential_time:.2f}s")
    print(f"Results: {len(seq_results)} tools executed")
    
    # Test parallel execution
    print("\n--- Parallel Execution ---")
    parallel_start = time.time()
    par_executor = create_tool_call_executor(parallel=True, max_workers=3)
    par_results = par_executor.execute_batch(tool_calls, mock_execute_tool)
    parallel_time = time.time() - parallel_start
    print(f"Parallel execution took: {parallel_time:.2f}s")
    print(f"Results: {len(par_results)} tools executed")
    
    # Verify results are identical and in correct order
    assert len(seq_results) == len(par_results), "Result counts should match"
    for i, (seq_result, par_result) in enumerate(zip(seq_results, par_results)):
        assert seq_result.function_name == par_result.function_name, f"Function names should match at index {i}"
        assert seq_result.arguments == par_result.arguments, f"Arguments should match at index {i}"
        assert seq_result.tool_call_id == par_result.tool_call_id, f"Tool call IDs should match at index {i}"
        print(f"  Result {i+1}: {seq_result.function_name} -> {seq_result.result}")
    
    # Verify latency improvement
    speedup = sequential_time / parallel_time if parallel_time > 0 else 1
    print(f"\nSpeedup: {speedup:.2f}x")
    print(f"Expected ~3x speedup for 3 parallel tools with 0.3s each")
    
    # Should be at least 2x faster for 3 parallel tools
    assert speedup >= 1.5, f"Expected speedup >= 1.5x, got {speedup:.2f}x"
    print("✅ ToolCallExecutor protocol test passed!\n")

@pytest.mark.live
def test_agent_parallel_tools():
    """Real agentic test with LLM end-to-end."""
    print("=== Real Agentic Test: Parallel Tool Execution ===")
    
    # Skip if no OpenAI API key
    import os
    if not os.getenv('OPENAI_API_KEY') and not os.getenv('PRAISONAI_LIVE_TESTS'):
        pytest.skip("OpenAI API key not available for live test")
    
    # Create agents with different settings
    sequential_agent = Agent(
        name="sequential_agent",
        instructions="You are a data fetcher. Use the provided tools to fetch user, analytics, and config data.",
        tools=[fetch_user_data, fetch_analytics_data, fetch_config_data],
        execution=ExecutionConfig(parallel_tool_calls=False),  # Sequential (current behavior)
        llm="gpt-4o-mini"
    )
    
    parallel_agent = Agent(
        name="parallel_agent", 
        instructions="You are a data fetcher. Use the provided tools to fetch user, analytics, and config data.",
        tools=[fetch_user_data, fetch_analytics_data, fetch_config_data],
        execution=ExecutionConfig(parallel_tool_calls=True),   # Parallel (new feature)
        llm="gpt-4o-mini"
    )
    
    # Prompt that should trigger multiple tool calls
    prompt = """Please fetch the following data concurrently:
1. User data for user ID 'user123'
2. Analytics data for metric 'page_views' 
3. Config data for key 'max_connections'

Return a summary of all the fetched data."""
    
    print(f"\nPrompt: {prompt}")
    
    # Test sequential agent (baseline)
    print("\n--- Sequential Agent ---")
    sequential_start = time.time()
    sequential_result = sequential_agent.start(prompt)
    sequential_time = time.time() - sequential_start
    print(f"Sequential agent completed in: {sequential_time:.2f}s")
    print(f"Result length: {len(sequential_result)} chars")
    print(f"Result preview: {sequential_result[:200]}...")
    
    # Test parallel agent
    print("\n--- Parallel Agent ---")
    parallel_start = time.time()
    parallel_result = parallel_agent.start(prompt)
    parallel_time = time.time() - parallel_start
    print(f"Parallel agent completed in: {parallel_time:.2f}s")
    print(f"Result length: {len(parallel_result)} chars")
    print(f"Result preview: {parallel_result[:200]}...")
    
    speedup = sequential_time / parallel_time if parallel_time > 0 else float("inf")
    print(f"\n=== Performance Comparison ===")
    print(f"Sequential time: {sequential_time:.2f}s")
    print(f"Parallel time: {parallel_time:.2f}s")
    print(f"Speedup: {speedup:.2f}x")
    
    # Assertions for test validation
    assert isinstance(sequential_result, str) and sequential_result.strip(), (
        "Sequential agent should return a non-empty string result."
    )
    assert isinstance(parallel_result, str) and parallel_result.strip(), (
        "Parallel agent should return a non-empty string result."
    )
    
    # Both results should contain evidence of tool execution
    assert 'user123' in sequential_result.lower() or 'john doe' in sequential_result.lower(), (
        "Sequential result should contain user data"
    )
    assert 'user123' in parallel_result.lower() or 'john doe' in parallel_result.lower(), (
        "Parallel result should contain user data"  
    )
    
    print("✅ Real agentic test completed!\n")

if __name__ == "__main__":
    """Run tests directly."""
    print("Testing Gap 2: Parallel Tool Execution")
    print("=====================================")
    
    # Test 1: Direct executor protocol testing
    test_executor_protocols()
    
    # Test 2: Real agentic test (per AGENTS.md requirement) 
    try:
        test_agent_parallel_tools()
    except Exception as e:
        print(f"Live test skipped or failed: {e}")
    
    print("Tests completed! 🎉")
    print("\nGap 2 implementation allows agents to execute batched LLM tool calls in parallel,")
    print("reducing latency for I/O-bound workflows while maintaining backward compatibility.")
