#!/usr/bin/env python3
"""
Test script to verify Ollama empty response fix for both sync and async methods.
"""

import asyncio
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

# Test with both sync and async workflows
async def test_model_async(model_name: str):
    print(f"\n{'='*60}")
    print(f"Testing ASYNC with model: {model_name}")
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
        result = await workflow.astart()  # Use async start
        print(f"\n{'='*60}")
        print(f"ASYNC RESULT for {model_name}:")
        print('='*60)
        print(result)
        
        # Check if result is empty
        if not result or (isinstance(result, dict) and not result.get('task_results', {}).get('search_task', {}).get('output')):
            print(f"\n❌ ERROR: Empty response from {model_name} (async)")
            return False
        else:
            print(f"\n✅ SUCCESS: Got valid response from {model_name} (async)")
            return True
            
    except Exception as e:
        print(f"\n❌ ERROR with {model_name} (async): {e}")
        import traceback
        traceback.print_exc()
        return False

def test_model_sync(model_name: str):
    print(f"\n{'='*60}")
    print(f"Testing SYNC with model: {model_name}")
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
        result = workflow.start()  # Use sync start
        print(f"\n{'='*60}")
        print(f"SYNC RESULT for {model_name}:")
        print('='*60)
        print(result)
        
        # Check if result is empty
        if not result or (isinstance(result, dict) and not result.get('task_results', {}).get('search_task', {}).get('output')):
            print(f"\n❌ ERROR: Empty response from {model_name} (sync)")
            return False
        else:
            print(f"\n✅ SUCCESS: Got valid response from {model_name} (sync)")
            return True
            
    except Exception as e:
        print(f"\n❌ ERROR with {model_name} (sync): {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("Testing Ollama empty response fix for both sync and async...")
    
    # Test sync methods
    print("\n1. Testing SYNC methods:")
    openai_sync_success = test_model_sync("openai/gpt-4o-mini")
    ollama_sync_success = test_model_sync("ollama/llama3.2")
    
    # Test async methods
    print("\n2. Testing ASYNC methods:")
    openai_async_success = await test_model_async("openai/gpt-4o-mini")
    ollama_async_success = await test_model_async("ollama/llama3.2")
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY:")
    print('='*60)
    print(f"OpenAI sync test: {'✅ PASSED' if openai_sync_success else '❌ FAILED'}")
    print(f"Ollama sync test: {'✅ PASSED' if ollama_sync_success else '❌ FAILED'}")
    print(f"OpenAI async test: {'✅ PASSED' if openai_async_success else '❌ FAILED'}")
    print(f"Ollama async test: {'✅ PASSED' if ollama_async_success else '❌ FAILED'}")
    
    if ollama_sync_success and ollama_async_success:
        print("\n🎉 Ollama empty response issue has been fixed for both sync and async!")
    else:
        print("\n⚠️  Ollama empty response issue still exists in some cases.")

if __name__ == "__main__":
    asyncio.run(main())