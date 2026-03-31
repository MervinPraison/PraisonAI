#!/usr/bin/env python3
"""
Real agentic test as required by AGENTS.md section 9.4.

This test verifies that the Agent actually runs end-to-end and calls the LLM,
not just smoke tests. This ensures our thread safety fixes don't break actual
agent functionality.
"""

import sys
import os

# Add the path to find praisonaiagents
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

def test_real_agentic_functionality():
    """Test that Agent actually runs and calls LLM end-to-end."""
    print("🧪 Running real agentic test (Agent must call LLM)...")
    
    try:
        from praisonaiagents import Agent
        
        # Create agent and run a real task
        agent = Agent(name="test", instructions="You are a helpful assistant")
        print(f"📋 Agent created: {agent.name}")
        
        # This MUST call the LLM and produce actual output
        print("🚀 Starting agent with real prompt...")
        result = agent.start("Say hello in one sentence")
        
        # Print full output for verification
        print("📄 Agent output:")
        print(f"Result: {result}")
        
        # Verify we got actual output
        if not result or not isinstance(result, str) or len(result.strip()) == 0:
            print("❌ Agent did not produce valid output")
            return False
        
        print("✅ Agent successfully called LLM and produced output!")
        return True
        
    except Exception as e:
        print(f"❌ Agent test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run the real agentic test."""
    print("🤖 Testing real agentic functionality after thread safety fixes...\n")
    
    success = test_real_agentic_functionality()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Real agentic test PASSED!")
        print("✅ Thread safety fixes do not break agent functionality")
    else:
        print("❌ Real agentic test FAILED!")
        print("⚠️  Agent functionality may be broken")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)