#!/usr/bin/env python3
"""
Basic test to verify streaming functionality without API calls
"""

import sys
import os
import logging

# Add the source path to enable imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_imports():
    """Test that we can import the required modules"""
    try:
        print("Testing imports...")
        
        # Test LLM import
        from praisonaiagents.llm.llm import LLM
        print("✅ LLM import successful")
        
        # Test Agent import
        from praisonaiagents.agent.agent import Agent
        print("✅ Agent import successful")
        
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_method_existence():
    """Test that the new streaming methods exist"""
    try:
        from praisonaiagents.llm.llm import LLM
        
        # Check if the new method exists
        llm = LLM(model="test")
        if hasattr(llm, 'get_response_stream'):
            print("✅ get_response_stream method exists in LLM")
        else:
            print("❌ get_response_stream method missing in LLM")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Method test error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_agent_streaming_setup():
    """Test that agent streaming is set up correctly"""
    try:
        from praisonaiagents.agent.agent import Agent
        
        # Create a basic agent instance (without API calls)
        agent = Agent(
            instructions="Test agent",
            llm="test/model",  # Mock model that won't make real API calls
            stream=True,
            verbose=False
        )
        
        print("✅ Agent creation successful")
        
        # Check if streaming methods exist
        if hasattr(agent, '_start_stream'):
            print("✅ _start_stream method exists in Agent")
        else:
            print("❌ _start_stream method missing in Agent")
            return False
            
        return True
    except Exception as e:
        print(f"❌ Agent test error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Running basic streaming functionality tests...")
    print("=" * 50)
    
    # Set logging to reduce noise
    logging.getLogger().setLevel(logging.WARNING)
    
    success = True
    
    # Test imports
    if not test_imports():
        success = False
    
    # Test method existence  
    if not test_method_existence():
        success = False
        
    # Test agent setup
    if not test_agent_streaming_setup():
        success = False
    
    print("=" * 50)
    
    if success:
        print("✅ All basic tests passed!")
        print("✅ Streaming infrastructure is properly set up")
        print("📝 Note: Real streaming tests require API keys and will be tested later")
    else:
        print("❌ Some tests failed - check the implementation")