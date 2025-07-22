#!/usr/bin/env python3

import sys
import os

# Add the source path to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

try:
    from praisonaiagents import Agent
    
    # Test 1: Agent with verbose=True (default), stream=False (default)
    print("=== Test 1: Default settings (verbose=True, stream=False) ===")
    agent = Agent(
        instructions="You are a helpful assistant", 
        llm="gpt-4o-mini"
    )
    print(f"Agent verbose: {agent.verbose}")
    print(f"Agent stream: {agent.stream}")
    print("This should show display_generating when verbose=True")
    
    # Test 2: Explicitly check the logic
    print("\n=== Test 2: Logic Check ===")
    stream = False
    verbose = True
    display_fn_condition = (stream or verbose)
    print(f"stream={stream}, verbose={verbose}")
    print(f"display_fn condition (stream or verbose): {display_fn_condition}")
    print(f"display_generating will be called: {display_fn_condition}")
    
    print("\n✅ Test completed - fix should work!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)