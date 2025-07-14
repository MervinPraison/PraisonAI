#!/usr/bin/env python3
"""
Test script to verify the duplicate callback fix for issue #878.
This tests that callbacks are triggered exactly once per LLM response.
"""

import os
import sys

# Add the path to the praisonaiagents module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents import register_display_callback
from praisonaiagents.llm.llm import LLM

# Track callback invocations
callback_count = 0
callback_details = []

def test_callback(message=None, response=None, **kwargs):
    """Callback function to track invocations."""
    global callback_count, callback_details
    callback_count += 1
    callback_details.append({
        'count': callback_count,
        'message': str(message)[:50] if message else None,
        'response': str(response)[:50] if response else None,
        'kwargs': list(kwargs.keys()) if kwargs else []
    })
    print(f"🔔 CALLBACK #{callback_count}: {response[:50] if response else 'No response'}")

def test_verbose_true():
    """Test with verbose=True (this was causing duplicates before the fix)."""
    global callback_count, callback_details
    callback_count = 0
    callback_details = []
    
    print("🧪 Testing with verbose=True...")
    register_display_callback('interaction', test_callback, is_async=False)
    
    try:
        llm = LLM(model="gemini/gemini-2.5-flash-lite-preview-06-17", verbose=False)
        response = llm.get_response(
            prompt="Say exactly: Hello World",
            verbose=True  # This should NOT cause duplicate callbacks after the fix
        )
        
        print(f"✅ Response: {response}")
        print(f"📊 Callback count: {callback_count}")
        
        if callback_count == 1:
            print("✅ SUCCESS: Exactly 1 callback triggered (no duplicates)")
            return True
        else:
            print(f"❌ FAIL: Expected 1 callback, got {callback_count}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_verbose_false():
    """Test with verbose=False (should still work)."""
    global callback_count, callback_details
    callback_count = 0
    callback_details = []
    
    print("\n🧪 Testing with verbose=False...")
    register_display_callback('interaction', test_callback, is_async=False)
    
    try:
        llm = LLM(model="gemini/gemini-2.5-flash-lite-preview-06-17", verbose=False)
        response = llm.get_response(
            prompt="Say exactly: Hello Non-Verbose",
            verbose=False
        )
        
        print(f"✅ Response: {response}")
        print(f"📊 Callback count: {callback_count}")
        
        if callback_count == 1:
            print("✅ SUCCESS: Exactly 1 callback triggered")
            return True
        else:
            print(f"❌ FAIL: Expected 1 callback, got {callback_count}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_multiple_calls():
    """Test multiple consecutive calls."""
    global callback_count, callback_details
    callback_count = 0
    callback_details = []
    
    print("\n🧪 Testing multiple consecutive calls...")
    register_display_callback('interaction', test_callback, is_async=False)
    
    try:
        llm = LLM(model="gemini/gemini-2.5-flash-lite-preview-06-17", verbose=False)
        
        for i in range(3):
            response = llm.get_response(
                prompt=f"Say exactly: Call {i+1}",
                verbose=True
            )
            print(f"  Call {i+1}: {response}")
        
        print(f"📊 Total callback count: {callback_count}")
        
        if callback_count == 3:
            print("✅ SUCCESS: Exactly 3 callbacks for 3 calls (1 each)")
            return True
        else:
            print(f"❌ FAIL: Expected 3 callbacks, got {callback_count}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    print("🔧 TESTING DUPLICATE CALLBACK FIX FOR ISSUE #878")
    print("=" * 60)
    
    results = []
    
    # Test 1: verbose=True (the main issue)
    results.append(test_verbose_true())
    
    # Test 2: verbose=False (should still work)
    results.append(test_verbose_false())
    
    # Test 3: multiple calls
    results.append(test_multiple_calls())
    
    # Summary
    print(f"\n🏁 SUMMARY")
    print("=" * 30)
    
    success_count = sum(results)
    total_tests = len(results)
    
    print(f"Tests passed: {success_count}/{total_tests}")
    
    if success_count == total_tests:
        print("✅ ALL TESTS PASSED! The duplicate callback issue is FIXED.")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED! The duplicate callback issue still exists.")
        sys.exit(1)