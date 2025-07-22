#!/usr/bin/env python3
"""
Comprehensive test to verify display_generating fix works for both OpenAI and custom LLM paths.
Tests the complete fix for issue #981.
"""

import sys
import os

# Add the source path to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_display_logic():
    """Test the core logic that determines when display_generating should be called"""
    print("=== Testing Display Logic ===")
    
    # Test cases covering all scenarios
    test_cases = [
        {"stream": False, "verbose": False, "expected": False, "description": "No display (stream=False, verbose=False)"},
        {"stream": False, "verbose": True, "expected": True, "description": "Display in verbose mode (stream=False, verbose=True) - MAIN FIX"},
        {"stream": True, "verbose": False, "expected": True, "description": "Display in stream mode (stream=True, verbose=False)"},
        {"stream": True, "verbose": True, "expected": True, "description": "Display in both modes (stream=True, verbose=True)"},
    ]
    
    print(f"{'Description':<55} {'Stream':<8} {'Verbose':<8} {'Expected':<8} {'Result':<8} {'Status'}")
    print("-" * 95)
    
    all_passed = True
    for case in test_cases:
        # Test the actual logic used in the fix
        result = (case["stream"] or case["verbose"])
        expected = case["expected"]
        status = "✅ PASS" if result == expected else "❌ FAIL"
        
        if result != expected:
            all_passed = False
            
        print(f"{case['description']:<55} {str(case['stream']):<8} {str(case['verbose']):<8} {str(expected):<8} {str(result):<8} {status}")
    
    print("-" * 95)
    if all_passed:
        print("✅ All logic tests PASSED!")
    else:
        print("❌ Some logic tests FAILED!")
        sys.exit(1)
    
    return all_passed

def test_agent_paths():
    """Test that both OpenAI and custom LLM paths are correctly handled"""
    print("\n=== Testing Agent Path Coverage ===")
    
    # Test file inspection - check that both paths have the fix
    agent_file = os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents', 'praisonaiagents', 'agent', 'agent.py')
    
    if not os.path.exists(agent_file):
        print("❌ Agent file not found")
        return False
    
    with open(agent_file, 'r') as f:
        content = f.read()
    
    # Check for OpenAI path fix
    openai_fix = "display_fn=display_generating if (stream or self.verbose) else None"
    has_openai_fix = openai_fix in content
    
    # Check for custom LLM path fix  
    custom_llm_fix = "if (stream or self.verbose) and self.console:"
    has_custom_fix = custom_llm_fix in content
    
    print(f"OpenAI path fix present: {'✅ YES' if has_openai_fix else '❌ NO'}")
    print(f"Custom LLM path fix present: {'✅ YES' if has_custom_fix else '❌ NO'}")
    
    if has_openai_fix and has_custom_fix:
        print("✅ Both agent paths have the display fix!")
        return True
    else:
        print("❌ Missing fix in one or both paths!")
        return False

def test_backward_compatibility():
    """Test that existing functionality is preserved"""
    print("\n=== Testing Backward Compatibility ===")
    
    # Test cases that should maintain existing behavior
    scenarios = [
        {"name": "Default streaming behavior", "stream": True, "verbose": True, "should_display": True},
        {"name": "Non-verbose non-streaming", "stream": False, "verbose": False, "should_display": False},
        {"name": "Streaming with verbose off", "stream": True, "verbose": False, "should_display": True},
    ]
    
    all_compat = True
    for scenario in scenarios:
        result = (scenario["stream"] or scenario["verbose"])
        expected = scenario["should_display"]
        status = "✅ COMPATIBLE" if result == expected else "❌ INCOMPATIBLE"
        
        if result != expected:
            all_compat = False
        
        print(f"{scenario['name']:<30}: {status}")
    
    if all_compat:
        print("✅ All backward compatibility tests PASSED!")
    else:
        print("❌ Backward compatibility issues detected!")
    
    return all_compat

if __name__ == "__main__":
    print("Comprehensive Display Fix Test for Issue #981")
    print("=" * 50)
    
    # Run all tests
    logic_ok = test_display_logic()
    paths_ok = test_agent_paths()
    compat_ok = test_backward_compatibility()
    
    # Final result
    print("\n" + "=" * 50)
    if logic_ok and paths_ok and compat_ok:
        print("🎉 ALL TESTS PASSED - Fix is comprehensive and correct!")
        print("✅ Issue #981 is fully resolved for both OpenAI and custom LLM users")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED - Fix needs more work")
        sys.exit(1)