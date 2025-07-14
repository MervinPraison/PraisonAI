#!/usr/bin/env python3
"""
Test script to reproduce the duplicate callback issue #878.
This script reproduces the exact issue described by the user where 
register_display_callback('interaction', callback_function) gets triggered twice 
for a single task execution.

The root cause: In llm.py, execute_sync_callback() is called directly AND 
display_interaction() is also called when verbose=True. Since display_interaction()
also executes sync callbacks internally, this causes duplicate callbacks.

Specific locations:
- llm.py line 851-857: execute_sync_callback() called directly  
- llm.py line 896: display_interaction() called when verbose=True
- main.py line 164-190: display_interaction() executes callbacks again
"""

import asyncio
import os
import sys

# Add the path to the praisonaiagents module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents import (
    register_display_callback,
    Agent, 
    Task, 
    PraisonAIAgents
)

# Global counter to track callback invocations
callback_count = 0
callback_log_file = 'callback_log.txt'

def simple_callback(message=None, response=None, **kwargs):
    """
    Simple callback function that logs invocations to demonstrate the duplicate issue.
    This matches the user's original reproduction case.
    """
    global callback_count
    callback_count += 1
    
    # Write to file as per user's original example
    with open(callback_log_file, 'a') as f:
        f.write(f"=== CALLBACK INVOCATION #{callback_count} ===\n")
        f.write(f"Received message: {message}\n")
        f.write(f"Got response: {response}\n")
        f.write(f"Other stuff: {kwargs}\n")
        f.write("-" * 50 + "\n")
    
    # Also print to console for immediate feedback
    print(f"🔔 CALLBACK #{callback_count}: message='{str(message)[:50]}...', response='{str(response)[:50]}...'")

def test_duplicate_callback_issue():
    """
    Test function that reproduces the exact scenario from the user's bug report.
    Expected: callback should be triggered only ONCE per task execution
    Actual (if bug exists): callback gets triggered TWICE
    """
    global callback_count
    callback_count = 0
    
    # Clear previous log file
    if os.path.exists(callback_log_file):
        os.remove(callback_log_file)
    
    print("🧪 Testing duplicate callback issue reproduction...")
    print("=" * 60)
    
    # Register as synchronous callback (exactly as user did)
    register_display_callback('interaction', simple_callback, is_async=False)
    print("✅ Registered 'interaction' callback")
    
    # Create an agent (exactly as user did)
    agent = Agent(
        name="MyAgent",
        role="Assistant",
        goal="Help with tasks",
        backstory="I am a helpful assistant",
        llm="gemini/gemini-2.5-flash-lite-preview-06-17",
        verbose=True  
    )
    print("✅ Created agent")
    
    # Create a task (exactly as user did)
    task = Task(
        name="simple_task",
        description="Say the number 1",
        agent=agent,
        expected_output="1"
    )
    print("✅ Created task")
    
    # Run the agent (exactly as user did)
    print("\n🚀 Starting agent execution...")
    print("⏱️  Watch for callback invocations below:")
    print("-" * 40)
    
    agents = PraisonAIAgents(
        agents=[agent],
        tasks=[task]
    )
    
    try:
        # This should trigger the callback
        result = agents.start()
        print("-" * 40)
        print(f"✅ Agent execution completed")
        
    except Exception as e:
        print(f"❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
    
    # Analyze results
    print("\n📊 RESULTS ANALYSIS:")
    print("=" * 60)
    print(f"Total callback invocations: {callback_count}")
    
    if os.path.exists(callback_log_file):
        with open(callback_log_file, 'r') as f:
            log_content = f.read()
        print(f"Log file size: {len(log_content)} characters")
        print("\n📄 Log file contents:")
        print("-" * 30)
        print(log_content)
    else:
        print("❌ No log file created")
    
    # Verdict
    print("\n🎯 VERDICT:")
    print("=" * 30)
    if callback_count == 1:
        print("✅ PASS: Callback invoked exactly once (expected behavior)")
        return True
    elif callback_count == 2:
        print("❌ FAIL: Duplicate callback detected! Callback invoked twice (this is the bug)")
        return False
    else:
        print(f"⚠️  UNEXPECTED: Callback invoked {callback_count} times (neither 1 nor 2)")
        return False

def test_direct_llm_call():
    """
    Test to isolate the issue by directly using the LLM class.
    This helps determine if the duplicate callback issue is in the LLM layer 
    or in the higher-level agent orchestration.
    """
    global callback_count
    callback_count = 0
    
    print("\n🔬 Testing direct LLM call (isolation test)...")
    print("=" * 60)
    
    # Clear previous log file
    if os.path.exists(callback_log_file):
        os.remove(callback_log_file)
    
    # Register callback for isolation test
    register_display_callback('interaction', simple_callback, is_async=False)
    
    # Import LLM directly
    from praisonaiagents.llm.llm import LLM
    
    try:
        # Create LLM instance
        llm = LLM(
            model="gemini/gemini-2.5-flash-lite-preview-06-17",
            verbose=True
        )
        print("✅ Created LLM instance")
        
        print("\n🚀 Making direct LLM call...")
        print("⏱️  Watch for callback invocations below:")
        print("-" * 40)
        
        # Make direct call to LLM
        response = llm.get_response(
            prompt="Say the number 1",
            verbose=True  # This should trigger the callback
        )
        
        print("-" * 40)
        print(f"✅ LLM call completed. Response: {response}")
        
    except Exception as e:
        print(f"❌ Error during LLM call: {e}")
        import traceback
        traceback.print_exc()
    
    # Analyze results
    print("\n📊 DIRECT LLM RESULTS:")
    print("=" * 40)
    print(f"Total callback invocations: {callback_count}")
    
    if callback_count == 1:
        print("✅ PASS: Direct LLM call triggered callback exactly once")
        return True
    elif callback_count == 2:
        print("❌ FAIL: Direct LLM call triggered duplicate callbacks")
        return False
    else:
        print(f"⚠️  UNEXPECTED: Direct LLM call triggered {callback_count} callbacks")
        return False

if __name__ == "__main__":
    print("🐛 REPRODUCING DUPLICATE CALLBACK ISSUE #878")
    print("=" * 60)
    print("This script reproduces the exact scenario from the user's bug report:")
    print("- Using register_display_callback('interaction', callback_function)")
    print("- Creating agent with simple task")
    print("- Expecting callback to be triggered ONCE, but seeing it triggered TWICE")
    print()
    
    # Test 1: Full agent reproduction
    full_test_passed = test_duplicate_callback_issue()
    
    # Test 2: Direct LLM isolation  
    direct_test_passed = test_direct_llm_call()
    
    # Summary
    print("\n🏁 FINAL SUMMARY:")
    print("=" * 50)
    print(f"Full agent test: {'PASSED' if full_test_passed else 'FAILED'}")
    print(f"Direct LLM test: {'PASSED' if direct_test_passed else 'FAILED'}")
    
    if not full_test_passed or not direct_test_passed:
        print("\n❌ DUPLICATE CALLBACK ISSUE CONFIRMED!")
        print("The callback is being triggered multiple times for a single task execution.")
        sys.exit(1)
    else:
        print("\n✅ NO DUPLICATE CALLBACK ISSUE DETECTED")
        print("Callbacks are working as expected.")
        sys.exit(0)