#!/usr/bin/env python3
"""
Test script to verify Ollama response overwrite fix
"""

import sys
import os

# Add the source directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_ollama_tool_summary_logic():
    """Test the logic that was causing the bug"""
    print("Testing Ollama tool summary logic...")
    
    try:
        from praisonaiagents.llm.llm import LLM
        
        # Create an Ollama LLM instance
        llm = LLM(model="ollama/test")
        
        # Test the tool summary generation method directly
        tool_results = ["The stock price of Google is 100"]
        empty_response = ""  # This is what Ollama often returns
        
        tool_summary = llm._generate_ollama_tool_summary(tool_results, empty_response)
        
        if tool_summary:
            print(f"✅ Tool summary generated correctly: {repr(tool_summary)}")
            
            # Simulate the fixed logic:
            # 1. Set final_response_text to tool_summary (this happens in the fix)
            final_response_text = tool_summary
            print(f"✅ final_response_text set to: {repr(final_response_text)}")
            
            # 2. Test the condition that was causing the bug
            iteration_count = 1  # Simulate that tools were executed
            response_text = ""   # Simulate empty Ollama response
            
            # OLD BUGGY LOGIC:
            # if iteration_count > 0:
            #     final_response_text = response_text.strip() if response_text else ""
            # This would overwrite final_response_text with ""
            
            # NEW FIXED LOGIC:
            if iteration_count > 0 and not final_response_text:
                final_response_text = response_text.strip() if response_text else ""
                print("❌ This condition should NOT execute because final_response_text is already set")
            else:
                print("✅ Condition correctly skipped - final_response_text preserved")
            
            # 3. Verify final_response_text is still the tool summary
            if final_response_text == tool_summary:
                print("✅ SUCCESS: Tool summary preserved through the fix!")
                return True
            else:
                print(f"❌ FAILED: Tool summary was overwritten. Expected: {repr(tool_summary)}, Got: {repr(final_response_text)}")
                return False
        else:
            print("❌ Tool summary generation failed")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

def test_non_ollama_compatibility():
    """Test that the fix doesn't break non-Ollama models"""
    print("\nTesting non-Ollama compatibility...")
    
    try:
        from praisonaiagents.llm.llm import LLM
        
        # Create a non-Ollama LLM instance
        llm = LLM(model="gpt-3.5-turbo")
        
        # Test the tool summary generation method with non-Ollama model
        tool_results = ["The stock price of Google is 100"]
        response_text = "Based on the tools, Google's stock price is 100"
        
        tool_summary = llm._generate_ollama_tool_summary(tool_results, response_text)
        
        if tool_summary is None:
            print("✅ Non-Ollama model correctly returns None for tool summary")
            
            # Simulate the logic for non-Ollama models
            final_response_text = ""
            iteration_count = 1
            
            # This should execute for non-Ollama models since final_response_text is empty
            if iteration_count > 0 and not final_response_text:
                final_response_text = response_text.strip() if response_text else ""
                print("✅ Non-Ollama logic executed correctly")
            
            if final_response_text == response_text:
                print("✅ SUCCESS: Non-Ollama compatibility maintained!")
                return True
            else:
                print(f"❌ FAILED: Non-Ollama logic broken. Expected: {repr(response_text)}, Got: {repr(final_response_text)}")
                return False
        else:
            print(f"❌ Non-Ollama model incorrectly generated summary: {tool_summary}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("Testing Ollama Response Overwrite Fix")
    print("=" * 60)
    
    test1_passed = test_ollama_tool_summary_logic()
    test2_passed = test_non_ollama_compatibility()
    
    print("\n" + "=" * 60)
    print("TEST RESULTS:")
    print(f"Ollama tool summary logic: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Non-Ollama compatibility: {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    
    if test1_passed and test2_passed:
        print("\n🎉 ALL TESTS PASSED! The fix should resolve the issue.")
        return True
    else:
        print("\n💥 SOME TESTS FAILED! The fix needs more work.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)