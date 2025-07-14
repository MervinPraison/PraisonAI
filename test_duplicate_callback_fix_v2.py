#!/usr/bin/env python3
"""
Test script to verify the duplicate callback fix for issue #878
This version uses the callback registration system
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents.llm.llm import LLM
from praisonaiagents.main import register_display_callback, sync_display_callbacks
from unittest.mock import patch, MagicMock
import json

# Track display_interaction calls
display_calls = []

def mock_display_interaction(prompt, response, markdown=True, generation_time=0):
    """Mock display_interaction to track calls"""
    display_calls.append({
        'prompt': prompt,
        'response': response,
        'markdown': markdown,
        'generation_time': generation_time
    })
    print(f"[DISPLAY] {prompt[:50]}... -> {response[:50]}...")

def test_single_display_no_tools():
    """Test that display_interaction callback is called only once without tools"""
    global display_calls
    display_calls = []
    
    # Register callback
    register_display_callback('interaction', mock_display_interaction)
    
    try:
        with patch('litellm.completion') as mock_completion:
            # Mock streaming response
            mock_completion.return_value = [
                MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content=" world"))]),
                MagicMock(choices=[MagicMock(delta=MagicMock(content="!"))])
            ]
            
            llm = LLM(model="gpt-4o-mini", verbose=False)
            response = llm.get_response(
                prompt="Test prompt",
                verbose=True,
                stream=True
            )
            
            print(f"\nResponse: {response}")
            print(f"Display calls: {len(display_calls)}")
            
            assert len(display_calls) == 1, f"Expected 1 display call, got {len(display_calls)}"
            assert response == "Hello world!"
            
    finally:
        # Clean up callback
        if 'interaction' in sync_display_callbacks:
            del sync_display_callbacks['interaction']

def test_single_display_with_reasoning():
    """Test that display_interaction callback is called only once with reasoning steps"""
    global display_calls
    display_calls = []
    
    # Register callback
    register_display_callback('interaction', mock_display_interaction)
    
    try:
        with patch('litellm.completion') as mock_completion:
            # Mock non-streaming response with reasoning
            mock_completion.return_value = {
                "choices": [{
                    "message": {
                        "content": "The answer is 42",
                        "provider_specific_fields": {
                            "reasoning_content": "Let me think about this..."
                        }
                    }
                }]
            }
            
            llm = LLM(model="o1-preview", verbose=False, reasoning_steps=True)
            response = llm.get_response(
                prompt="What is the meaning of life?",
                verbose=True,
                stream=False,
                reasoning_steps=True
            )
            
            print(f"\nResponse: {response}")
            print(f"Display calls: {len(display_calls)}")
            
            assert len(display_calls) == 1, f"Expected 1 display call, got {len(display_calls)}"
            
    finally:
        # Clean up callback
        if 'interaction' in sync_display_callbacks:
            del sync_display_callbacks['interaction']

if __name__ == "__main__":
    print("Testing duplicate callback fix using callback system...\n")
    
    try:
        print("1. Testing single display without tools...")
        test_single_display_no_tools()
        print("✓ PASSED\n")
        
        print("2. Testing single display with reasoning...")
        test_single_display_with_reasoning()
        print("✓ PASSED\n")
        
        print("All tests passed! The callback system is working correctly.")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)