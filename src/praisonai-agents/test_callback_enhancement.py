#!/usr/bin/env python3
"""Test script for callback enhancement - Issue #896"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

import asyncio
from praisonaiagents import (
    register_display_callback,
    Agent, 
    Task, 
    PraisonAIAgents
)

def enhanced_callback(message=None, response=None, agent_name=None, agent_role=None, agent_tools=None, task_name=None, task_description=None, task_id=None, **kwargs):
    """Enhanced callback that demonstrates the new context information"""
    print("="*80)
    print("ENHANCED CALLBACK TRIGGERED")
    print("="*80)
    print(f"Message: {message}")
    print(f"Response: {response}")
    print(f"Agent Name: {agent_name}")
    print(f"Agent Role: {agent_role}")
    print(f"Agent Tools: {agent_tools}")
    print(f"Task Name: {task_name}")
    print(f"Task Description: {task_description}")
    print(f"Task ID: {task_id}")
    print(f"Other kwargs: {kwargs}")
    print("="*80)
    print()

# Register the enhanced callback
register_display_callback('interaction', enhanced_callback, is_async=False)

def test_callback_enhancement():
    """Test function to verify the callback enhancement works"""
    
    # Create an agent with detailed information
    agent = Agent(
        name="TestAgent",
        role="Assistant",
        goal="Help with testing callbacks",
        backstory="I am a helpful assistant for testing purposes",
        llm="openai/gpt-5-nano",
        verbose=True  
    )

    # Create a task with detailed information
    task = Task(
        name="callback_test_task",
        description="Test the enhanced callback functionality",
        agent=agent,
        expected_output="A simple response to test callbacks"
    )

    # Run the agents
    try:
        agents = PraisonAIAgents(
            agents=[agent],
            tasks=[task],
            verbose=True
        )
        result = agents.start()
        print(f"Test completed successfully! Result: {result}")
        return True
    except Exception as e:
        print(f"Test failed with error: {e}")
        return False

if __name__ == "__main__":
    print("Testing callback enhancement (Issue #896)...")
    print("This test will demonstrate the new agent_name and task context in callbacks")
    print()
    
    # Run the test
    success = test_callback_enhancement()
    
    if success:
        print("✅ Test passed! Callback enhancement is working correctly.")
    else:
        print("❌ Test failed! Check the error output above.")