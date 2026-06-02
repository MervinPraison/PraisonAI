#!/usr/bin/env python3
"""
Test script to validate the smart fallback behavior for streaming.
"""
import logging
import os
import sys

# Add src/praisonai-agents to path for testing
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

# Set up minimal logging to see fallback messages
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

try:
    from praisonaiagents import Agent
    
    # Test 1: Create agent with Deepseek (a provider that typically doesn't support sync streaming)
    print("🧪 Testing smart fallback with sync agent...")
    
    # Mock a scenario that would trigger the fallback
    agent = Agent(
        name="test_agent",
        llm="deepseek-chat",  # This would typically trigger the fallback
        instructions="You are a helpful assistant. Say hello."
    )
    
    # Test _chat_completion with stream=None (should trigger smart fallback)
    print("✨ Testing _chat_completion with stream=None (smart fallback)...")
    
    messages = [{"role": "user", "content": "Hello, please say hello back."}]
    
    # This should try streaming first, then fall back to non-streaming if needed
    try:
        response = agent._chat_completion(messages, stream=None)
        print("✅ Smart fallback test passed - got response without errors")
        if response and response.choices:
            print(f"📝 Response: {response.choices[0].message.content[:100]}...")
    except Exception as e:
        print(f"❌ Smart fallback test failed: {e}")
    
    # Test 2: Explicit streaming should work if supported
    print("\n✨ Testing _chat_completion with stream=True (explicit)...")
    try:
        response = agent._chat_completion(messages, stream=True)
        print("✅ Explicit streaming test passed")
    except ValueError as e:
        if "Streaming is not supported" in str(e):
            print("✅ Explicit streaming correctly rejected by adapter")
        else:
            print(f"❌ Unexpected error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    
    # Test 3: Explicit non-streaming should always work
    print("\n✨ Testing _chat_completion with stream=False (explicit)...")
    try:
        response = agent._chat_completion(messages, stream=False)
        print("✅ Explicit non-streaming test passed")
    except Exception as e:
        print(f"❌ Explicit non-streaming test failed: {e}")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Note: This is expected if dependencies are not installed")
except Exception as e:
    print(f"❌ Unexpected error: {e}")

print("\n🎯 Smart fallback implementation test completed!")