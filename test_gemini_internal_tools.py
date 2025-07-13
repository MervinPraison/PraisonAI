#!/usr/bin/env python3
"""Test script for Gemini internal tools functionality."""

from praisonaiagents import Agent

def test_gemini_internal_tools():
    """Test that Gemini internal tools are properly configured."""
    
    # Test 1: Agent with Google Search enabled
    print("Test 1: Agent with Google Search enabled")
    agent1 = Agent(
        name="Search Agent",
        instructions="You are a helpful research assistant",
        gemini_google_search=True,
        gemini_code_execution=False,
        llm="gemini/gemini-1.5-flash"
    )
    
    # Check if Gemini tools are prepared correctly
    gemini_tools = agent1._prepare_gemini_tools()
    print(f"Gemini tools prepared: {gemini_tools}")
    assert len(gemini_tools) == 1
    assert {"google_search_retrieval": {}} in gemini_tools
    
    # Test 2: Agent with Code Execution enabled
    print("\nTest 2: Agent with Code Execution enabled")
    agent2 = Agent(
        name="Code Agent",
        instructions="You are a helpful coding assistant",
        gemini_google_search=False,
        gemini_code_execution=True,
        llm="gemini/gemini-1.5-flash"
    )
    
    gemini_tools = agent2._prepare_gemini_tools()
    print(f"Gemini tools prepared: {gemini_tools}")
    assert len(gemini_tools) == 1
    assert {"code_execution": {}} in gemini_tools
    
    # Test 3: Agent with both tools enabled
    print("\nTest 3: Agent with both tools enabled")
    agent3 = Agent(
        name="Full Agent",
        instructions="You are a helpful assistant with all capabilities",
        gemini_google_search=True,
        gemini_code_execution=True,
        llm="gemini/gemini-1.5-flash"
    )
    
    gemini_tools = agent3._prepare_gemini_tools()
    print(f"Gemini tools prepared: {gemini_tools}")
    assert len(gemini_tools) == 2
    assert {"google_search_retrieval": {}} in gemini_tools
    assert {"code_execution": {}} in gemini_tools
    
    # Test 4: Agent with no Gemini tools (default behavior)
    print("\nTest 4: Agent with no Gemini tools (default)")
    agent4 = Agent(
        name="Standard Agent",
        instructions="You are a helpful assistant",
        llm="gemini/gemini-1.5-flash"
    )
    
    gemini_tools = agent4._prepare_gemini_tools()
    print(f"Gemini tools prepared: {gemini_tools}")
    assert len(gemini_tools) == 0
    
    # Test 5: Test _format_tools_for_completion handles Gemini tools
    print("\nTest 5: Test _format_tools_for_completion with Gemini tools")
    test_tools = [
        {"google_search_retrieval": {}},
        {"code_execution": {}},
        lambda x: x  # Regular function tool
    ]
    
    formatted = agent3._format_tools_for_completion(test_tools)
    print(f"Formatted tools count: {len(formatted)}")
    # Should have 3 tools: 2 Gemini + 1 function
    assert len(formatted) == 3
    
    print("\nAll tests passed! ✓")

if __name__ == "__main__":
    test_gemini_internal_tools()