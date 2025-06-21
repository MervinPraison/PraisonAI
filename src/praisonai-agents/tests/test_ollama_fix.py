#!/usr/bin/env python3
"""
Test script to verify Ollama empty response fix.
"""

import logging
from praisonaiagents import Agent, Task, PraisonAIAgents, TaskOutput
from typing import Dict, Any

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Define a simple tool for testing
def search_tool(query: str) -> Dict[str, Any]:
    """Simulate a search tool that returns results."""
    logging.debug(f"[TEST] Search tool called with query: {query}")
    results = {
        "results": [
            {"title": "Result 1", "description": f"Information about {query}"},
            {"title": "Result 2", "description": f"More details on {query}"}
        ],
        "total": 2
    }
    logging.debug(f"[TEST] Search tool returning: {results}")
    return results

# Test with both OpenAI and Ollama models
def test_model(model_name: str):
    print(f"\n{'='*60}")
    print(f"Testing with model: {model_name}")
    print('='*60)
    
    # Create agent with the search tool
    agent = Agent(
        name="SearchAgent",
        role="Information Researcher",
        goal="Search for information and provide helpful answers",
        backstory="You are an expert at finding and summarizing information.",
        llm=model_name,
        tools=[search_tool],
        verbose=True
    )
    
    # Create a task that requires tool usage
    task = Task(
        name="search_task",
        description="Search for information about 'Python programming' and provide a summary of what you found.",
        expected_output="A clear summary of the search results",
        agent=agent
    )
    
    # Create and run the workflow
    workflow = PraisonAIAgents(
        agents=[agent],
        tasks=[task],
        verbose=True
    )
    
    try:
        result = workflow.start()
        print(f"\n{'='*60}")
        print(f"FINAL RESULT for {model_name}:")
        print('='*60)
        print(result)
        
        # Check if result is empty
        if not result or (isinstance(result, dict) and not result.get('task_results', {}).get('search_task', {}).get('output')):
            print(f"\n❌ ERROR: Empty response from {model_name}")
            return False
        else:
            print(f"\n✅ SUCCESS: Got valid response from {model_name}")
            return True
            
    except Exception as e:
        print(f"\n❌ ERROR with {model_name}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing Ollama empty response fix...")
    
    # Test with OpenAI first (as baseline)
    print("\n1. Testing with OpenAI (baseline):")
    openai_success = test_model("openai/gpt-4o-mini")
    
    # Test with Ollama
    print("\n2. Testing with Ollama:")
    ollama_success = test_model("ollama/llama3.2")
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY:")
    print('='*60)
    print(f"OpenAI test: {'✅ PASSED' if openai_success else '❌ FAILED'}")
    print(f"Ollama test: {'✅ PASSED' if ollama_success else '❌ FAILED'}")
    
    if ollama_success:
        print("\n🎉 Ollama empty response issue has been fixed!")
    else:
        print("\n⚠️  Ollama empty response issue still exists.")