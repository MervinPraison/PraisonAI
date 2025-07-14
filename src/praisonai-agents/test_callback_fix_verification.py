#!/usr/bin/env python3
"""
Simple test to verify that the callback fix is working
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from praisonaiagents import register_display_callback
from praisonaiagents.main import display_interaction, display_self_reflection

# Track callback calls
callback_calls = []

def test_callback(message, response, **kwargs):
    """Test callback function"""
    callback_calls.append({
        'type': 'interaction',
        'message': message,
        'response': response
    })
    print(f"[CALLBACK] Interaction: {message[:30]}... -> {response[:30]}...")

def test_self_reflection_callback(message, **kwargs):
    """Test self-reflection callback function"""
    callback_calls.append({
        'type': 'self_reflection',
        'message': message
    })
    print(f"[CALLBACK] Self-reflection: {message[:50]}...")

def test_display_interaction_callback():
    """Test that display_interaction calls the callback"""
    global callback_calls
    callback_calls = []
    
    # Register callback
    register_display_callback('interaction', test_callback)
    
    try:
        # Call display_interaction
        display_interaction(
            message="Test message",
            response="Test response",
            markdown=True,
            generation_time=1.5
        )
        
        print(f"Callback calls: {len(callback_calls)}")
        
        # Verify callback was called
        assert len(callback_calls) == 1, f"Expected 1 callback call, got {len(callback_calls)}"
        assert callback_calls[0]['type'] == 'interaction'
        assert callback_calls[0]['message'] == "Test message"
        assert callback_calls[0]['response'] == "Test response"
        
        print("✓ display_interaction callback test PASSED")
        
    finally:
        # Clean up
        from praisonaiagents.main import sync_display_callbacks
        sync_display_callbacks.pop('interaction', None)

def test_display_self_reflection_callback():
    """Test that display_self_reflection calls the callback"""
    global callback_calls
    callback_calls = []
    
    # Register callback
    register_display_callback('self_reflection', test_self_reflection_callback)
    
    try:
        # Call display_self_reflection
        display_self_reflection("This is a self-reflection message")
        
        print(f"Self-reflection callback calls: {len(callback_calls)}")
        
        # Verify callback was called
        assert len(callback_calls) == 1, f"Expected 1 callback call, got {len(callback_calls)}"
        assert callback_calls[0]['type'] == 'self_reflection'
        assert callback_calls[0]['message'] == "This is a self-reflection message"
        
        print("✓ display_self_reflection callback test PASSED")
        
    finally:
        # Clean up
        from praisonaiagents.main import sync_display_callbacks
        sync_display_callbacks.pop('self_reflection', None)

if __name__ == "__main__":
    print("Testing callback fix for display functions...\n")
    
    try:
        print("1. Testing display_interaction callback...")
        test_display_interaction_callback()
        print()
        
        print("2. Testing display_self_reflection callback...")
        test_display_self_reflection_callback()
        print()
        
        print("All callback tests passed! The fix is working correctly.")
        
    except AssertionError as e:
        print(f"✗ FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)