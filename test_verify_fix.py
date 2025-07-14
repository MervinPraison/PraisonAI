#!/usr/bin/env python3
"""
Test to verify the fix works by checking imports and function calls
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

try:
    # Test 1: Check that the modules import correctly
    print("Testing imports...")
    from praisonaiagents.main import display_interaction as main_display_interaction
    from praisonaiagents.llm.llm import display_interaction as llm_display_interaction
    print("✓ Both display_interaction functions imported successfully")
    
    # Test 2: Check that they're the same function
    print(f"Main function: {main_display_interaction}")
    print(f"LLM function: {llm_display_interaction}")
    print(f"Are they the same function? {main_display_interaction is llm_display_interaction}")
    
    # Test 3: Check the callback system exists
    from praisonaiagents.main import sync_display_callbacks, execute_sync_callback
    print(f"Sync callbacks registry: {sync_display_callbacks}")
    print("✓ Callback system exists")
    
    # Test 4: Test function call
    print("\nTesting function call...")
    from unittest.mock import patch
    
    call_count = 0
    def mock_func(*args, **kwargs):
        global call_count
        call_count += 1
        print(f"Mock called with args: {args}, kwargs: {kwargs}")
    
    with patch('praisonaiagents.llm.llm.display_interaction', side_effect=mock_func):
        # Import after patching
        from praisonaiagents.llm.llm import display_interaction
        display_interaction("test", "response")
        
    print(f"Call count: {call_count}")
    if call_count == 1:
        print("✓ Patching works correctly!")
    else:
        print("✗ Patching failed!")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()