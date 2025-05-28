#!/usr/bin/env python3
"""
Test script to reproduce the Mini Agents sequential task data passing issue.
This will help verify the fix works correctly.
"""

import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from praisonaiagents import Agent, Agents
from unittest.mock import patch

def mock_completion(*args, **kwargs):
    """Mock litellm.completion function to avoid calling actual API"""
    stream = kwargs.get('stream', False)
    
    # Determine response content based on messages
    messages = kwargs.get('messages', [])
    response_content = "mock response"
    
    for message in messages:
        content = message.get('content', '') if isinstance(message, dict) else str(message)
        if 'Generate the number 42' in content:
            response_content = "42"
            break
        elif 'multiply it by 2' in content:
            response_content = "84"
            break
    
    if stream:
        # Return streaming response (iterator)
        class MockDelta:
            def __init__(self, content):
                self.content = content
        
        class MockStreamChoice:
            def __init__(self, content):
                self.delta = MockDelta(content)
        
        class MockStreamChunk:
            def __init__(self, content):
                self.choices = [MockStreamChoice(content)]
        
        # Return a list that can be iterated (simulating streaming chunks)
        return [MockStreamChunk(response_content)]
    else:
        # Return non-streaming response
        class MockMessage:
            def __init__(self, content):
                self.content = content
            
            def get(self, key, default=None):
                if key == "tool_calls":
                    return None  # No tool calls in our simple test
                return getattr(self, key, default)
            
            def __getitem__(self, key):
                if hasattr(self, key):
                    return getattr(self, key)
                raise KeyError(key)
        
        class MockChoice:
            def __init__(self, content):
                self.message = MockMessage(content)
            
            def __getitem__(self, key):
                if key == "message":
                    return self.message
                if hasattr(self, key):
                    return getattr(self, key)
                raise KeyError(key)
        
        class MockResponse:
            def __init__(self, content):
                self.choices = [MockChoice(content)]
            
            def __getitem__(self, key):
                # Support dictionary-style access
                if key == "choices":
                    return self.choices
                if hasattr(self, key):
                    return getattr(self, key)
                raise KeyError(key)
        
        return MockResponse(response_content)

@patch('litellm.completion', side_effect=mock_completion)
def test_mini_agents_sequential_data_passing(mock_litellm):
    """Test that output from previous task is passed to next task in Mini Agents"""
    
    print("Testing Mini Agents Sequential Data Passing...")
    
    # Create two agents for sequential processing
    agent1 = Agent(instructions="Generate the number 42 as your output. Only return the number 42, nothing else.", llm={'model': 'gpt-3.5-turbo'})
    agent2 = Agent(instructions="Take the input number and multiply it by 2. Only return the result number, nothing else.", llm={'model': 'gpt-3.5-turbo'})
    
    # Create agents with sequential processing (Mini Agents pattern)
    agents = Agents(agents=[agent1, agent2], verbose=True)
    
    # Execute the agents
    result = agents.start(return_dict=True)
    
    print("\n=== Results ===")
    print("Task Status:", result['task_status'])
    print("\nTask Results:")
    for task_id, task_result in result['task_results'].items():
        if task_result:
            print(f"Task {task_id}: {task_result.raw}")
        else:
            print(f"Task {task_id}: No result")
    
    # Check if the second task received the first task's output
    task_results = result['task_results']
    assert len(task_results) >= 2, "Not enough tasks were executed"
    
    task1_result = task_results[0]
    task2_result = task_results[1]
    
    assert task1_result is not None, "First task produced no result"
    assert task2_result is not None, "Second task produced no result"
    
    print(f"\nFirst task output: {task1_result.raw}")
    print(f"Second task output: {task2_result.raw}")
    
    # The second task should have received "42" and returned "84"
    assert "42" in str(task1_result.raw), f"Expected first task to output '42', got: {task1_result.raw}"
    assert "84" in str(task2_result.raw), f"Expected second task to output '84', got: {task2_result.raw}"
    
    print("✅ SUCCESS: Data was passed correctly between tasks!")

if __name__ == "__main__":
    test_mini_agents_sequential_data_passing()
