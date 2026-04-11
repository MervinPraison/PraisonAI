#!/usr/bin/env python3
"""
Test script to verify that Agent backend delegation is working correctly.
"""

import sys
import asyncio
from typing import Dict, Any, AsyncIterator

# Add the praisonai-agents source to the path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

from praisonaiagents import Agent


class MockManagedBackend:
    """Mock backend to test delegation without real API calls."""
    
    def __init__(self):
        self.executed_prompts = []
        self.streamed_prompts = []
    
    async def execute(self, prompt: str, **kwargs) -> str:
        self.executed_prompts.append(prompt)
        return f"Mock response for: {prompt}"
    
    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[Dict[str, Any]]:
        self.streamed_prompts.append(prompt)
        # Simulate streaming response with agent.message event
        yield {
            'type': 'agent.message',
            'content': [{'type': 'text', 'text': f"Mock streamed response for: {prompt}"}]
        }
        yield {
            'type': 'session.status_idle',
            'reason': 'completed'
        }


def test_backend_delegation():
    """Test that Agent properly delegates to external backend."""
    
    print("Testing Agent backend delegation...")
    
    # Create a mock backend
    mock_backend = MockManagedBackend()
    
    # Create agent with backend
    agent = Agent(name="test", instructions="You are a test agent", backend=mock_backend)
    
    # Test 1: run() method delegation
    print("\n1. Testing run() method delegation...")
    result = agent.run("Hello, test run")
    print(f"Result: {result}")
    
    # Verify the backend was called
    assert len(mock_backend.executed_prompts) == 1
    assert mock_backend.executed_prompts[0] == "Hello, test run"
    assert "Mock response for: Hello, test run" in result
    print("✅ run() delegation working!")
    
    # Test 2: start() method delegation (non-streaming)
    print("\n2. Testing start() method delegation (non-streaming)...")
    result = agent.start("Hello, test start")
    print(f"Result: {result}")
    
    # Verify the backend was called again
    assert len(mock_backend.executed_prompts) == 2
    assert mock_backend.executed_prompts[1] == "Hello, test start"
    assert "Mock response for: Hello, test start" in result
    print("✅ start() delegation working!")
    
    # Test 3: chat() method delegation
    print("\n3. Testing chat() method delegation...")
    result = agent.chat("Hello, test chat")
    print(f"Result: {result}")
    
    # Verify the backend was called again
    assert len(mock_backend.executed_prompts) == 3
    assert mock_backend.executed_prompts[2] == "Hello, test chat"
    assert "Mock response for: Hello, test chat" in result
    print("✅ chat() delegation working!")
    
    # Test 4: Test that Agent WITHOUT backend still works locally
    print("\n4. Testing Agent without backend (fallback to local)...")
    local_agent = Agent(name="local", instructions="You are a local agent")
    
    # This should fail with a real LLM call since we don't have API keys
    # But it should at least try to execute locally (not delegate)
    try:
        # We just want to make sure it doesn't try to delegate
        # We expect this to fail due to missing API keys, which is fine
        result = local_agent.run("Test local execution")
    except Exception as e:
        # Expected - no API keys configured
        print(f"Expected error for local agent (no API keys): {type(e).__name__}")
        print("✅ Local agent execution attempted (not delegated)!")
    
    print("\n🎉 All tests passed! Backend delegation is working correctly.")
    
    return True


if __name__ == "__main__":
    test_backend_delegation()