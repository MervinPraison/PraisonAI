#!/usr/bin/env python3

"""
Simple test to verify basic import and functionality
"""

import sys
import os

# Add the package to Python path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

def test_import():
    """Test basic import"""
    print("Testing basic import...")
    
    try:
        from praisonaiagents import Agent
        print("✅ Successfully imported Agent")
        
        # Create a basic agent
        agent = Agent(
            instructions="You are a helpful assistant",
            llm="gpt-3.5-turbo"
        )
        print("✅ Successfully created Agent instance")
        
        # Test that start method exists and has the right signature
        import inspect
        start_sig = inspect.signature(agent.start)
        print(f"✅ Agent.start method signature: {start_sig}")
        
        # Check if _start_stream method exists
        if hasattr(agent, '_start_stream'):
            print("✅ _start_stream method exists")
            stream_sig = inspect.signature(agent._start_stream)
            print(f"✅ Agent._start_stream method signature: {stream_sig}")
        else:
            print("❌ _start_stream method not found")
            
        return True
        
    except Exception as e:
        print(f"❌ Error in import test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_import()
    if success:
        print("\n✅ All basic tests passed!")
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)