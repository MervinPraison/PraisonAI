#!/usr/bin/env python3

import sys
import os

# Add current directory to path
sys.path.insert(0, '.')

try:
    from praisonaiagents.agent.agent import Agent
    
    # Create agent
    agent = Agent(name='test', instructions='test agent')
    print("✓ Agent creation works")
    
    # Test clone method
    cloned = agent.clone_for_channel()
    print("✓ Clone method works")
    
    # Verify they're different instances
    assert agent is not cloned
    print("✓ Cloning produces different instances")
    
    # Verify they have different locks
    assert agent._Agent__cache_lock is not cloned._Agent__cache_lock
    print("✓ Cloning produces different locks")
    
    print("All basic tests passed!")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)