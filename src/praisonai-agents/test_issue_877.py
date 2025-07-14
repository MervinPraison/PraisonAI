#!/usr/bin/env python3
"""
Test script to reproduce and verify the fix for issue #877
where callbacks only work when verbose=True.
"""

import sys
sys.path.insert(0, 'src/praisonai-agents')

from praisonaiagents import (
    register_display_callback,
    Agent, 
    Task, 
    PraisonAIAgents
)

# Track callback execution
callback_log = []

def simple_callback(message=None, response=None, **kwargs):
    callback_log.append({
        'message': message,
        'response': response,
        'kwargs': kwargs
    })
    with open('callback_log.txt', 'a') as f:
        f.write(f"Received message: {message}\n")
        f.write(f"Got response: {response}\n")
        f.write(f"Other stuff: {kwargs}\n\n")

# Clear the log file
with open('callback_log.txt', 'w') as f:
    f.write("=== Testing Callback Issue #877 ===\n\n")

# Register as synchronous callback
register_display_callback('interaction', simple_callback, is_async=False)

print("=" * 60)
print("Testing Issue #877: Callbacks Only Work When verbose=True")
print("=" * 60)

# Test Case 1: verbose=False
print("\nTest Case 1: verbose=False")
print("-" * 30)
callback_log.clear()

agent1 = Agent(
    name="MyAgent",
    role="Assistant",
    goal="Help with tasks",
    backstory="I am a helpful assistant",
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",  # Using the same model as in the issue
    verbose=False  
)

task1 = Task(
    name="simple_task",
    description="Say the number 1",
    agent=agent1,
    expected_output="1"
)

try:
    agents1 = PraisonAIAgents(
        agents=[agent1],
        tasks=[task1]
    )
    result1 = agents1.start()
    print(f"Task completed. Callbacks executed: {len(callback_log)}")
    if len(callback_log) > 0:
        print("✅ SUCCESS: Callbacks were executed with verbose=False!")
        print(f"   First callback: message='{callback_log[0]['message'][:50]}...', response='{callback_log[0]['response'][:50]}...'")
    else:
        print("❌ FAILED: No callbacks were executed with verbose=False")
except Exception as e:
    print(f"❌ ERROR during test: {e}")
    import traceback
    traceback.print_exc()

# Test Case 2: verbose=True (for comparison)
print("\n\nTest Case 2: verbose=True (for comparison)")
print("-" * 30)
callback_log.clear()

agent2 = Agent(
    name="MyAgent",
    role="Assistant",
    goal="Help with tasks",
    backstory="I am a helpful assistant",
    llm="gemini/gemini-2.5-flash-lite-preview-06-17",
    verbose=True  
)

task2 = Task(
    name="simple_task",
    description="Say the number 2",
    agent=agent2,
    expected_output="2"
)

try:
    agents2 = PraisonAIAgents(
        agents=[agent2],
        tasks=[task2]
    )
    result2 = agents2.start()
    print(f"\nTask completed. Callbacks executed: {len(callback_log)}")
    if len(callback_log) > 0:
        print("✅ Callbacks were executed with verbose=True as expected")
        print(f"   First callback: message='{callback_log[0]['message'][:50]}...', response='{callback_log[0]['response'][:50]}...'")
    else:
        print("⚠️  WARNING: No callbacks were executed even with verbose=True")
except Exception as e:
    print(f"❌ ERROR during test: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test Results Summary:")
print("-" * 30)
print("Check callback_log.txt for detailed callback logs")
print("=" * 60)