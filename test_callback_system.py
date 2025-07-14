#!/usr/bin/env python3
"""
Test to verify the callback system works correctly
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents.main import register_display_callback, display_interaction, display_self_reflection

# Track callback calls
callback_calls = []

def test_callback(prompt, response, markdown=True, generation_time=None):
    """Test callback function"""
    callback_calls.append({
        'prompt': prompt,
        'response': response,
        'markdown': markdown,
        'generation_time': generation_time
    })
    print(f"[CALLBACK] {prompt[:50]}... -> {response[:50]}...")

def test_self_reflection_callback(message):
    """Test self-reflection callback"""
    callback_calls.append({
        'type': 'self_reflection',
        'message': message
    })
    print(f"[SELF_REFLECTION] {message[:50]}...")

def test_callback_system():
    """Test the callback registration system"""
    global callback_calls
    callback_calls = []
    
    # Register the callback
    register_display_callback('interaction', test_callback)
    register_display_callback('self_reflection', test_self_reflection_callback)
    
    # Test display_interaction
    display_interaction("Test prompt", "Test response")
    
    # Test display_self_reflection
    display_self_reflection("Test reflection message")
    
    print(f"Total callback calls: {len(callback_calls)}")
    
    # Verify interaction callback
    interaction_calls = [call for call in callback_calls if 'prompt' in call]
    assert len(interaction_calls) == 1, f"Expected 1 interaction call, got {len(interaction_calls)}"
    assert interaction_calls[0]['prompt'] == "Test prompt"
    assert interaction_calls[0]['response'] == "Test response"
    
    # Verify self-reflection callback
    reflection_calls = [call for call in callback_calls if call.get('type') == 'self_reflection']
    assert len(reflection_calls) == 1, f"Expected 1 self-reflection call, got {len(reflection_calls)}"
    assert reflection_calls[0]['message'] == "Test reflection message"
    
    print("✓ Callback system works correctly!")

if __name__ == "__main__":
    try:
        test_callback_system()
        print("Callback system test passed!")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()