#!/usr/bin/env python3
"""
Simple test to check if the callback fix is working
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents.main import display_interaction, register_display_callback

# Track calls
calls = []

def test_callback(prompt, response, markdown=True, generation_time=0):
    """Test callback to track calls"""
    calls.append({
        'prompt': prompt,
        'response': response,
        'markdown': markdown,
        'generation_time': generation_time
    })
    print(f"[CALLBACK] {prompt[:50]}... -> {response[:50]}...")

if __name__ == "__main__":
    print("Testing callback fix...")
    
    # Register the callback
    register_display_callback('interaction', test_callback)
    
    # Call display_interaction
    display_interaction("Test prompt", "Test response")
    
    print(f"Callback calls: {len(calls)}")
    
    if len(calls) == 1:
        print("✓ PASSED: Callback was called once")
    else:
        print(f"✗ FAILED: Expected 1 callback, got {len(calls)}")
        print(f"Calls: {calls}")