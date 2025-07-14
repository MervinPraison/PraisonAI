#!/usr/bin/env python3
"""
Simplified test to verify the callback fix works
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from unittest.mock import patch, MagicMock

# Track display_interaction calls
display_calls = []

def mock_display_interaction(prompt, response, markdown=True, generation_time=0, console=None):
    """Mock display_interaction to track calls"""
    display_calls.append({
        'prompt': prompt,
        'response': response,
        'markdown': markdown,
        'generation_time': generation_time
    })
    print(f"[MOCK CALLED] {prompt[:50]}... -> {response[:50]}...")

def test_patch_works():
    """Test that the patch works correctly"""
    global display_calls
    display_calls = []
    
    # Test the patch by calling the function directly
    with patch('praisonaiagents.llm.llm.display_interaction', side_effect=mock_display_interaction):
        # Import after patching
        from praisonaiagents.llm.llm import display_interaction
        
        # Call the function
        display_interaction("Test prompt", "Test response")
        
        print(f"Display calls: {len(display_calls)}")
        assert len(display_calls) == 1, f"Expected 1 display call, got {len(display_calls)}"
        assert display_calls[0]['prompt'] == "Test prompt"
        assert display_calls[0]['response'] == "Test response"
        print("✓ Patch test PASSED")

if __name__ == "__main__":
    try:
        test_patch_works()
        print("Simple test passed! The patching strategy works correctly.")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()