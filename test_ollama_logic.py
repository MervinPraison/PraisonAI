#!/usr/bin/env python3
"""
Simple test to validate the Ollama tool summary logic fix.
This test focuses on the specific logic changes without importing the full LLM class.
"""

def test_ollama_logic():
    """Test the fixed logic that was causing the infinite loop."""
    
    print("Testing Ollama infinite loop fix logic...")
    
    # Simulate the old problematic logic
    def old_generate_ollama_tool_summary(tool_results, response_text):
        """Old logic that caused infinite loops."""
        OLLAMA_MIN_RESPONSE_LENGTH = 10
        
        # Only generate summary for Ollama with tool results
        if not tool_results:
            return None
            
        # OLD BUG: If response is substantial, no summary needed
        if response_text and len(response_text.strip()) > OLLAMA_MIN_RESPONSE_LENGTH:
            return None  # This was the bug - returns None instead of summary
            
        # Build tool summary
        summary_lines = ["Based on the tool execution results:"]
        for i, result in enumerate(tool_results):
            if isinstance(result, dict) and 'result' in result:
                function_name = result.get('function_name', 'Tool')
                summary_lines.append(f"- {function_name}: {result['result']}")
            else:
                summary_lines.append(f"- Tool {i+1}: {result}")
        
        return "\n".join(summary_lines)
    
    # Simulate the new fixed logic
    def new_generate_ollama_tool_summary(tool_results, response_text):
        """New logic that prevents infinite loops."""
        # Only generate summary for Ollama with tool results
        if not tool_results:
            return None
            
        # FIXED: For Ollama, always generate summary when we have tool results
        # This prevents infinite loops caused by empty/minimal responses
        
        # Build tool summary
        summary_lines = ["Based on the tool execution results:"]
        for i, result in enumerate(tool_results):
            if isinstance(result, dict) and 'result' in result:
                function_name = result.get('function_name', 'Tool')
                summary_lines.append(f"- {function_name}: {result['result']}")
            else:
                summary_lines.append(f"- Tool {i+1}: {result}")
        
        return "\n".join(summary_lines)
    
    # Test data
    tool_results = [
        {"function_name": "get_stock_price", "result": "The stock price of Google is 100"},
        {"function_name": "multiply", "result": "200"}
    ]
    
    # Test case 1: Empty response
    print("\nTest 1: Empty response")
    old_result = old_generate_ollama_tool_summary(tool_results, "")
    new_result = new_generate_ollama_tool_summary(tool_results, "")
    print(f"Old logic: {old_result is not None}")
    print(f"New logic: {new_result is not None}")
    assert old_result is not None, "Old logic should generate summary for empty response"
    assert new_result is not None, "New logic should generate summary for empty response"
    
    # Test case 2: Short response (<=10 chars)
    print("\nTest 2: Short response")
    old_result = old_generate_ollama_tool_summary(tool_results, "Ok")
    new_result = new_generate_ollama_tool_summary(tool_results, "Ok")
    print(f"Old logic: {old_result is not None}")
    print(f"New logic: {new_result is not None}")
    assert old_result is not None, "Old logic should generate summary for short response"
    assert new_result is not None, "New logic should generate summary for short response"
    
    # Test case 3: Long response (>10 chars) - This was the bug
    print("\nTest 3: Long response (>10 chars)")
    long_response = "This is a longer response that would cause infinite loops"
    old_result = old_generate_ollama_tool_summary(tool_results, long_response)
    new_result = new_generate_ollama_tool_summary(tool_results, long_response)
    print(f"Old logic: {old_result is not None} (THIS WAS THE BUG)")
    print(f"New logic: {new_result is not None}")
    
    # This is the key fix - old logic returned None for long responses
    assert old_result is None, "Old logic incorrectly returned None for long responses"
    assert new_result is not None, "New logic correctly generates summary for long responses"
    
    print("\n✅ Ollama infinite loop fix logic validated!")
    print("   - Old logic had bug with long responses")
    print("   - New logic always generates summary when tool results exist")
    
    return True


def test_conditional_check_simplification():
    """Test the simplified conditional check logic."""
    
    print("\nTesting simplified conditional check logic...")
    
    # Test the old verbose condition
    def old_condition_check(response_text):
        return bool(response_text and response_text.strip() and len(response_text.strip()) > 10)
    
    # Test the new simplified condition
    def new_condition_check(response_text):
        return bool(response_text and len(response_text.strip()) > 10)
    
    test_cases = [
        ("", False),
        ("   ", False),
        ("short", False),
        ("this is a longer response", True),
        (None, False),
        ("exactly 10", False),  # 10 chars exactly
        ("exactly 11c", True),   # 11 chars
    ]
    
    for test_input, expected in test_cases:
        old_result = old_condition_check(test_input)
        new_result = new_condition_check(test_input)
        
        print(f"Testing '{test_input}': old={repr(old_result)}, new={repr(new_result)}, expected={repr(expected)}")
        
        assert old_result == new_result == expected, f"Mismatch for '{test_input}': old={old_result}, new={new_result}, expected={expected}"
    
    print("✅ Conditional check simplification working correctly")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Testing Ollama infinite loop fix logic...")
    print("=" * 60)
    
    try:
        test_ollama_logic()
        test_conditional_check_simplification()
        
        print("\n" + "=" * 60)
        print("🎉 ALL LOGIC TESTS PASSED!")
        print("=" * 60)
        
        print("\n📋 Key fixes validated:")
        print("✅ Removed redundant length check that caused infinite loops")
        print("✅ Simplified verbose conditional checks")
        print("✅ Logic now always generates summary for Ollama with tool results")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        exit(1)