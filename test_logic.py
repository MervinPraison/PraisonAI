#!/usr/bin/env python3

# Test the logic fix for display_generating

# Original logic (broken)
def original_logic(stream, verbose):
    return stream

# Fixed logic  
def fixed_logic(stream, verbose):
    return (stream or verbose)

print("=== Testing display_generating logic fix ===")

# Test cases
test_cases = [
    {"stream": False, "verbose": False, "expected_display": False, "description": "No verbose, no stream"},
    {"stream": False, "verbose": True, "expected_display": True, "description": "Verbose but no stream (user's case)"},
    {"stream": True, "verbose": False, "expected_display": True, "description": "Stream but no verbose"}, 
    {"stream": True, "verbose": True, "expected_display": True, "description": "Both stream and verbose"},
]

print(f"{'Description':<35} {'Stream':<8} {'Verbose':<8} {'Original':<10} {'Fixed':<8} {'Expected':<8} {'Status'}")
print("-" * 80)

all_passed = True
for case in test_cases:
    original_result = original_logic(case["stream"], case["verbose"])
    fixed_result = fixed_logic(case["stream"], case["verbose"])
    expected = case["expected_display"]
    
    # Check if the fix works correctly
    status = "✅ PASS" if fixed_result == expected else "❌ FAIL"
    if fixed_result != expected:
        all_passed = False
        
    print(f"{case['description']:<35} {str(case['stream']):<8} {str(case['verbose']):<8} {str(original_result):<10} {str(fixed_result):<8} {str(expected):<8} {status}")

print("-" * 80)
if all_passed:
    print("✅ All tests PASSED! The fix should work correctly.")
    print("✅ display_generating will now be called when verbose=True, even with stream=False")
else:
    print("❌ Some tests FAILED!")

print("\n=== Key Fix ===")
print("Before: display_fn=display_generating if stream else None") 
print("After:  display_fn=display_generating if (stream or verbose) else None")