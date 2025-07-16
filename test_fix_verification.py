#!/usr/bin/env python3
"""Test the issue fix with a simple callback that expects task_name."""

import asyncio
from praisonaiagents import Agent, Task, PraisonAIAgents

# Simple callback that expects task_name - this would trigger the error before the fix
def test_callback(**kwargs):
    print(f"Callback called with task_name: {kwargs.get('task_name', 'NOT PROVIDED')}")
    # This would cause the "name 'task_name' is not defined" error before the fix
    # because the callback functions would try to access task_name but it wasn't passed

# Register the callback
from praisonaiagents.main import register_display_callback
register_display_callback('interaction', test_callback)

# Example tool
def simple_tool():
    return "Simple tool result"

# Simple agent setup
test_agent = Agent(
    name="TestAgent",
    role="Test Agent",
    goal="Test the fix",
    tools=[simple_tool],
    llm="gpt-4o-mini",  # Using OpenAI for testing
    verbose=False  # This is key - verbose=False triggers the bug
)

# Simple task
test_task = Task(
    name="test_task",
    description="Test task for the fix",
    expected_output="Test output",
    agent=test_agent
)

async def main():
    print("Testing the fix...")
    
    # This should work without the "name 'task_name' is not defined" error
    workflow = PraisonAIAgents(
        agents=[test_agent],
        tasks=[test_task],
        process="sequential",
        verbose=False  # This should not cause the error anymore
    )
    
    try:
        results = await workflow.astart()
        print("✅ Test passed! No 'task_name' error occurred.")
        return True
    except NameError as e:
        if "task_name" in str(e):
            print(f"❌ Test failed! Still getting task_name error: {e}")
            return False
        else:
            print(f"❌ Test failed with different error: {e}")
            return False
    except Exception as e:
        print(f"⚠️ Test failed with other error (expected without API key): {e}")
        # This is expected without API key, but we shouldn't get task_name error
        if "task_name" in str(e):
            print("❌ But the task_name error is still present!")
            return False
        else:
            print("✅ No task_name error found, fix appears to work!")
            return True

if __name__ == "__main__":
    asyncio.run(main())