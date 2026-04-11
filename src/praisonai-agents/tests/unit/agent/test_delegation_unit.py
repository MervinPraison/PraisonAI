#!/usr/bin/env python3
"""
Unit test for backend delegation functionality.
"""

import sys
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

from praisonaiagents import Agent
import asyncio
from typing import Dict, Any, AsyncIterator

class MockManagedBackend:
    """Mock backend to test delegation."""
    
    def __init__(self):
        self.executed_prompts = []
        self.execution_kwargs = []
    
    async def execute(self, prompt: str, **kwargs) -> str:
        self.executed_prompts.append(prompt)
        self.execution_kwargs.append(kwargs)
        return f"Backend response: {prompt}"
    
    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[Dict[str, Any]]:
        self.executed_prompts.append(prompt)
        self.execution_kwargs.append(kwargs)
        yield {
            'type': 'agent.message',
            'content': [{'type': 'text', 'text': f"Backend streamed: {prompt}"}]
        }

def test_agent_backend_delegation():
    """Test that Agent properly delegates execution to backend."""
    
    # Create mock backend
    mock_backend = MockManagedBackend()
    
    # Create agent with backend
    agent = Agent(
        name="test-agent",
        instructions="Test agent",
        backend=mock_backend
    )
    
    # Test run() delegation
    result = agent.run("Test run prompt")
    assert result == "Backend response: Test run prompt"
    assert len(mock_backend.executed_prompts) == 1
    assert mock_backend.executed_prompts[0] == "Test run prompt"
    print("✅ run() delegation test passed")
    
    # Test start() delegation
    result = agent.start("Test start prompt")
    assert result == "Backend response: Test start prompt"
    assert len(mock_backend.executed_prompts) == 2
    assert mock_backend.executed_prompts[1] == "Test start prompt"
    print("✅ start() delegation test passed")
    
    # Test chat() delegation
    result = agent.chat("Test chat prompt")
    assert result == "Backend response: Test chat prompt"
    assert len(mock_backend.executed_prompts) == 3
    assert mock_backend.executed_prompts[2] == "Test chat prompt"
    print("✅ chat() delegation test passed")
    
    # Test that Agent without backend doesn't delegate
    local_agent = Agent(name="local", instructions="Local agent")
    assert not hasattr(local_agent, 'backend') or local_agent.backend is None
    print("✅ Non-backend agent test passed")
    
    print("\n🎉 All unit tests passed!")

if __name__ == "__main__":
    test_agent_backend_delegation()