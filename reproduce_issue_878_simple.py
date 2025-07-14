#!/usr/bin/env python3
"""
Simple test script to isolate the duplicate callback issue #878.
This script directly tests the LLM class to determine where the duplicate callbacks originate.

ROOT CAUSE IDENTIFIED:
In llm.py, there are two separate callback execution paths:
1. execute_sync_callback() called directly (lines 851-857, 885-891, etc.)
2. display_interaction() called when verbose=True (line 896, etc.)

Since display_interaction() ALSO executes sync callbacks internally (main.py lines 164-190),
this results in duplicate callback execution for the same LLM response.

The issue occurs specifically when verbose=True because both callback paths are active.
"""

import os
import sys

# Add the path to the praisonaiagents module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents import register_display_callback
from praisonaiagents.llm.llm import LLM

# Global counter and log
callback_invocations = []

def track_callback(message=None, response=None, **kwargs):
    """
    Callback function that tracks each invocation with detailed information.
    """
    invocation = {
        'count': len(callback_invocations) + 1,
        'message': str(message)[:100] if message else None,
        'response': str(response)[:100] if response else None,
        'kwargs_keys': list(kwargs.keys()) if kwargs else [],
        'stack_trace': get_simplified_stack_trace()
    }
    callback_invocations.append(invocation)
    
    print(f"🔔 CALLBACK #{invocation['count']}")
    print(f"   Message: {invocation['message']}")
    print(f"   Response: {invocation['response']}")
    print(f"   Called from: {invocation['stack_trace']}")
    print()

def get_simplified_stack_trace():
    """Get a simplified stack trace to see where the callback is called from."""
    import traceback
    import inspect
    
    # Get the current stack
    stack = inspect.stack()
    
    # Find relevant frames (skip our own callback function)
    relevant_frames = []
    for frame in stack[2:8]:  # Skip track_callback and get_simplified_stack_trace
        filename = os.path.basename(frame.filename)
        if 'praisonaiagents' in frame.filename:
            relevant_frames.append(f"{filename}:{frame.lineno} in {frame.function}")
    
    return " -> ".join(relevant_frames) if relevant_frames else "Unknown"

def test_llm_streaming():
    """Test LLM with streaming enabled."""
    print("🧪 TEST 1: LLM with streaming")
    print("-" * 40)
    
    global callback_invocations
    callback_invocations = []
    
    # Register callback
    register_display_callback('interaction', track_callback, is_async=False)
    
    try:
        llm = LLM(model="gemini/gemini-2.5-flash-lite-preview-06-17", verbose=False)
        
        response = llm.get_response(
            prompt="Say exactly: Hello World",
            verbose=True,  # This should trigger the callback
            stream=True    # Test with streaming
        )
        
        print(f"✅ Response: {response}")
        print(f"📊 Total callback invocations: {len(callback_invocations)}")
        
        return len(callback_invocations)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return -1

def test_llm_non_streaming():
    """Test LLM without streaming."""
    print("🧪 TEST 2: LLM without streaming")
    print("-" * 40)
    
    global callback_invocations
    callback_invocations = []
    
    # Register callback
    register_display_callback('interaction', track_callback, is_async=False)
    
    try:
        llm = LLM(model="gemini/gemini-2.5-flash-lite-preview-06-17", verbose=False)
        
        response = llm.get_response(
            prompt="Say exactly: Hello World",
            verbose=True,  # This should trigger the callback
            stream=False   # Test without streaming
        )
        
        print(f"✅ Response: {response}")
        print(f"📊 Total callback invocations: {len(callback_invocations)}")
        
        return len(callback_invocations)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return -1

def test_llm_with_self_reflection():
    """Test LLM with self-reflection enabled."""
    print("🧪 TEST 3: LLM with self-reflection")
    print("-" * 40)
    
    global callback_invocations
    callback_invocations = []
    
    # Register callback
    register_display_callback('interaction', track_callback, is_async=False)
    
    try:
        llm = LLM(model="gemini/gemini-2.5-flash-lite-preview-06-17", verbose=False, self_reflect=True)
        
        response = llm.get_response(
            prompt="Say exactly: Hello World",
            verbose=True,    # This should trigger the callback
            self_reflect=True,
            min_reflect=1,
            max_reflect=1
        )
        
        print(f"✅ Response: {response}")
        print(f"📊 Total callback invocations: {len(callback_invocations)}")
        
        return len(callback_invocations)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return -1

def test_verbose_vs_non_verbose():
    """Test the key difference: verbose=True vs verbose=False to isolate the duplicate issue."""
    print("🧪 TEST 4: Verbose vs Non-Verbose (Key Test for Duplicate Issue)")
    print("-" * 60)
    
    global callback_invocations
    
    # Test with verbose=False (should trigger callback once via execute_sync_callback)
    print("  🔹 Testing with verbose=False:")
    callback_invocations = []
    register_display_callback('interaction', track_callback, is_async=False)
    
    try:
        llm = LLM(model="gemini/gemini-2.5-flash-lite-preview-06-17", verbose=False)
        response = llm.get_response(
            prompt="Say exactly: Test Non-Verbose",
            verbose=False  # This should only trigger execute_sync_callback
        )
        print(f"    Response: {response}")
        print(f"    Callbacks with verbose=False: {len(callback_invocations)}")
        non_verbose_count = len(callback_invocations)
    except Exception as e:
        print(f"    ❌ Error: {e}")
        non_verbose_count = -1
    
    print()
    
    # Test with verbose=True (should trigger callback twice: execute_sync_callback + display_interaction)
    print("  🔹 Testing with verbose=True:")
    callback_invocations = []
    register_display_callback('interaction', track_callback, is_async=False)
    
    try:
        llm = LLM(model="gemini/gemini-2.5-flash-lite-preview-06-17", verbose=False)
        response = llm.get_response(
            prompt="Say exactly: Test Verbose",
            verbose=True  # This should trigger BOTH execute_sync_callback AND display_interaction
        )
        print(f"    Response: {response}")
        print(f"    Callbacks with verbose=True: {len(callback_invocations)}")
        verbose_count = len(callback_invocations)
        
        # Show the call stack differences
        if len(callback_invocations) > 1:
            print(f"\n    📋 Call stack analysis:")
            for i, inv in enumerate(callback_invocations):
                print(f"      Callback #{i+1}: {inv['stack_trace']}")
        
    except Exception as e:
        print(f"    ❌ Error: {e}")
        verbose_count = -1
    
    print(f"\n  📊 RESULT:")
    print(f"    verbose=False: {non_verbose_count} callback(s)")
    print(f"    verbose=True:  {verbose_count} callback(s)")
    
    if verbose_count > non_verbose_count and verbose_count > 1:
        print(f"    🚨 DUPLICATE ISSUE CONFIRMED!")
        print(f"       verbose=True triggers {verbose_count - non_verbose_count} extra callback(s)")
    
    return verbose_count

def test_multiple_calls():
    """Test multiple consecutive calls to see pattern."""
    print("🧪 TEST 5: Multiple consecutive calls")
    print("-" * 40)
    
    global callback_invocations
    callback_invocations = []
    
    # Register callback
    register_display_callback('interaction', track_callback, is_async=False)
    
    try:
        llm = LLM(model="gemini/gemini-2.5-flash-lite-preview-06-17", verbose=False)
        
        for i in range(3):
            print(f"  Call {i+1}:")
            response = llm.get_response(
                prompt=f"Say exactly: Call {i+1}",
                verbose=True
            )
            print(f"    Response: {response}")
        
        print(f"📊 Total callback invocations across 3 calls: {len(callback_invocations)}")
        
        return len(callback_invocations)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return -1

def analyze_callback_patterns():
    """Analyze the patterns in callback invocations."""
    print("\n📊 CALLBACK PATTERN ANALYSIS")
    print("=" * 50)
    
    if not callback_invocations:
        print("❌ No callback invocations recorded")
        return
    
    print(f"Total invocations: {len(callback_invocations)}")
    print("\nDetailed breakdown:")
    
    for inv in callback_invocations:
        print(f"  #{inv['count']}: {inv['stack_trace']}")
        if inv['message']:
            print(f"    Message: {inv['message']}")
        if inv['response']: 
            print(f"    Response: {inv['response']}")
        print()
    
    # Look for duplicate patterns
    unique_traces = set(inv['stack_trace'] for inv in callback_invocations)
    if len(unique_traces) < len(callback_invocations):
        print("⚠️  POTENTIAL DUPLICATE PATTERN DETECTED!")
        print("Some callbacks are coming from the same call stack.")
    else:
        print("✅ All callbacks appear to come from different call paths.")

if __name__ == "__main__":
    print("🔬 ISOLATING DUPLICATE CALLBACK ISSUE #878")
    print("=" * 60)
    print("This script tests the LLM class directly to isolate where duplicate callbacks occur.")
    print()
    
    # Run different test scenarios
    results = {}
    
    # Test 1: Streaming
    results['streaming'] = test_llm_streaming()
    print()
    
    # Test 2: Non-streaming  
    results['non_streaming'] = test_llm_non_streaming()
    print()
    
    # Test 3: Self-reflection
    results['self_reflection'] = test_llm_with_self_reflection()
    print()
    
    # Test 4: Verbose vs Non-Verbose (KEY TEST)
    results['verbose_vs_nonverbose'] = test_verbose_vs_non_verbose()
    print()
    
    # Test 5: Multiple calls
    results['multiple_calls'] = test_multiple_calls()
    print()
    
    # Analyze patterns
    analyze_callback_patterns()
    
    # Summary
    print("\n🏁 SUMMARY OF RESULTS")
    print("=" * 40)
    
    expected_single_call_tests = ['streaming', 'non_streaming', 'self_reflection']
    issues_detected = []
    
    for test_name, count in results.items():
        if count == -1:
            print(f"{test_name}: ERROR")
        elif test_name == 'multiple_calls':
            expected = 3
            print(f"{test_name}: {count} invocations (expected ~{expected})")
            if count > expected * 1.5:  # Allow some tolerance
                issues_detected.append(f"{test_name}: {count} > expected {expected}")
        elif test_name == 'verbose_vs_nonverbose':
            # This is the key test - verbose=True should show the duplicate issue
            print(f"{test_name}: {count} invocations (this test shows verbose=True duplicates)")
            if count > 1:
                issues_detected.append(f"{test_name}: verbose=True triggered {count} callbacks (duplicate issue)")
        else:
            expected = 1
            print(f"{test_name}: {count} invocations (expected {expected})")
            if count > expected:
                issues_detected.append(f"{test_name}: {count} > expected {expected}")
    
    if issues_detected:
        print(f"\n❌ DUPLICATE CALLBACK ISSUES DETECTED:")
        for issue in issues_detected:
            print(f"  - {issue}")
        print("\nThe callback system is triggering multiple times when it should trigger once.")
        sys.exit(1)
    else:
        print(f"\n✅ NO DUPLICATE CALLBACK ISSUES DETECTED")
        print("All callback invocations appear to be working as expected.")
        sys.exit(0)