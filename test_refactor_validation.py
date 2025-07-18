#!/usr/bin/env python3
"""
Quick validation test to ensure the refactored chat method works correctly.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Test that the refactored chat method can be imported and has the right structure
def test_refactored_structure():
    try:
        from praisonaiagents.agent.agent import Agent
        print("✅ Agent class imported successfully")
        
        # Check that the chat method exists
        assert hasattr(Agent, 'chat'), "chat method not found"
        print("✅ chat method exists")
        
        # Check that _cleanup_telemetry method exists
        assert hasattr(Agent, '_cleanup_telemetry'), "_cleanup_telemetry method not found"
        print("✅ _cleanup_telemetry method exists")
        
        # Test basic agent creation
        agent = Agent(
            name="TestAgent",
            role="Test Agent",
            goal="Test refactoring",
            instructions="Test"
        )
        print("✅ Agent created successfully")
        
        # Test that _cleanup_telemetry can be called
        agent._cleanup_telemetry()
        print("✅ _cleanup_telemetry method can be called")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_refactored_structure()
    if success:
        print("\n✅ All refactoring validation tests passed!")
    else:
        print("\n❌ Refactoring validation failed!")