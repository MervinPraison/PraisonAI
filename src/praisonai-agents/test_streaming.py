#!/usr/bin/env python3
"""
Test script to validate real-time streaming functionality
"""

import sys
import os

# Add the source path to enable imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

try:
    from praisonaiagents import Agent
    
    print("Creating agent with streaming enabled...")
    agent = Agent(
        instructions="You are a helpful assistant",
        llm="gemini/gemini-2.5-flash",
        stream=True,
        verbose=False  # Reduce noise during testing
    )
    
    print("Starting streaming test...")
    print("=" * 50)
    
    # Test the streaming functionality
    chunk_count = 0
    for chunk in agent.start("Write a short paragraph about the benefits of real-time streaming in AI applications"):
        print(chunk, end="", flush=True)
        chunk_count += 1
    
    print("\n" + "=" * 50)
    print(f"✅ Streaming test completed! Received {chunk_count} chunks.")
    
    if chunk_count > 1:
        print("✅ SUCCESS: Real-time streaming is working - received multiple chunks!")
    else:
        print("⚠️  WARNING: Only received 1 chunk - may still be using simulated streaming")
        
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're in the correct directory and dependencies are installed")
except Exception as e:
    print(f"❌ Error during streaming test: {e}")
    import traceback
    traceback.print_exc()