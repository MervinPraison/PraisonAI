#!/usr/bin/env python3
"""Test script to verify callbacks work with verbose=False"""

import sys
sys.path.insert(0, 'src/praisonai-agents')

from praisonaiagents import (
    register_display_callback,
    Agent, 
    Task, 
    PraisonAIAgents
)

# Track if callback was executed
callback_executed = False

def simple_callback(message=None, response=None, **kwargs):
    global callback_executed
    callback_executed = True
    with open('callback_test_log.txt', 'a') as f:
        f.write(f"CALLBACK EXECUTED!\n")
        f.write(f"Message: {message}\n")
        f.write(f"Response: {response}\n")
        f.write(f"Other kwargs: {kwargs}\n")
        f.write("-" * 50 + "\n")

# Register callback
register_display_callback('interaction', simple_callback, is_async=False)

# Test with verbose=False
print("Testing with verbose=False...")
agent = Agent(
    name="TestAgent",
    role="Assistant",
    goal="Help with tasks",
    backstory="I am a helpful assistant",
    llm="gpt-5-nano",  # Using a simple model for testing
    verbose=False
)

task = Task(
    name="simple_task",
    description="Say hello world",
    agent=agent,
    expected_output="A greeting"
)

# Clear the log file
with open('callback_test_log.txt', 'w') as f:
    f.write("Starting test with verbose=False\n")

# Run the agent
try:
    agents = PraisonAIAgents(
        agents=[agent],
        tasks=[task]
    )
    result = agents.start()
    print(f"Task completed. Result: {result}")
    print(f"Callback executed: {callback_executed}")
    
    # Check if callback was executed
    if callback_executed:
        print("✅ SUCCESS: Callback was executed with verbose=False!")
    else:
        print("❌ FAILED: Callback was NOT executed with verbose=False")
        
except Exception as e:
    print(f"Error during test: {e}")
    import traceback
    traceback.print_exc()