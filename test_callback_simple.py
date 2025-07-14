#!/usr/bin/env python3
"""Simple test for callback enhancement - Issue #896"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

# Test just the callback registration and display functions
from praisonaiagents import register_display_callback, display_interaction

def test_callback(message=None, response=None, agent_name=None, agent_role=None, agent_tools=None, task_name=None, task_description=None, task_id=None, **kwargs):
    """Test callback function"""
    print("Callback triggered with:")
    print(f"  Message: {message}")
    print(f"  Response: {response}")
    print(f"  Agent Name: {agent_name}")
    print(f"  Agent Role: {agent_role}")
    print(f"  Agent Tools: {agent_tools}")
    print(f"  Task Name: {task_name}")
    print(f"  Task Description: {task_description}")
    print(f"  Task ID: {task_id}")
    print(f"  Other kwargs: {kwargs}")
    print()

# Register the callback
register_display_callback('interaction', test_callback, is_async=False)

# Test the display_interaction function with new parameters
print("Testing display_interaction with enhanced parameters...")

display_interaction(
    message="Test message",
    response="Test response",
    agent_name="TestAgent",
    agent_role="Assistant",
    agent_tools=["tool1", "tool2"],
    task_name="test_task",
    task_description="Test task description",
    task_id="task_123",
    markdown=True,
    generation_time=1.5
)

print("✅ Simple callback test completed!")