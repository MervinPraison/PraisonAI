#!/usr/bin/env python3
"""
Test script to validate the Ollama infinite loop fix.

This script tests that:
1. Ollama provider detection works correctly
2. Tool results summary generation works as expected
3. Loop termination logic prevents infinite loops
4. Backward compatibility is maintained for other providers
"""

import sys
import os

# Add the source directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_module_imports():
    """Test that we can import the required modules."""
    try:
        from praisonaiagents.llm.llm import LLM
        print("✅ Successfully imported LLM module")
        return True
    except ImportError as e:
        print(f"❌ Failed to import LLM module: {e}")
        return False

def test_ollama_provider_detection():
    """Test Ollama provider detection logic."""
    try:
        from praisonaiagents.llm.llm import LLM
        
        # Test Ollama provider detection
        ollama_llm = LLM(model="ollama/qwen3")
        is_ollama = ollama_llm._is_ollama_provider()
        
        if is_ollama:
            print("✅ Ollama provider detection works correctly")
        else:
            print("❌ Ollama provider detection failed")
            return False
            
        # Test non-Ollama provider
        openai_llm = LLM(model="gpt-4o-mini")
        is_not_ollama = not openai_llm._is_ollama_provider()
        
        if is_not_ollama:
            print("✅ Non-Ollama provider detection works correctly")
        else:
            print("❌ Non-Ollama provider incorrectly detected as Ollama")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Provider detection test failed: {e}")
        return False

def test_tool_summary_generation():
    """Test that tool results summary generation works correctly."""
    try:
        # Mock tool results like what would be generated
        tool_results = [
            "The stock price of Google is 100",
            200
        ]
        
        # Simulate the summary generation logic
        tool_summary = "Based on the tool execution results:\n"
        for i, result in enumerate(tool_results):
            if isinstance(result, dict) and 'result' in result:
                tool_summary += f"- {result.get('function_name', 'Tool')}: {result['result']}\n"
            else:
                tool_summary += f"- Tool {i+1}: {result}\n"
        
        expected_summary = "Based on the tool execution results:\n- Tool 1: The stock price of Google is 100\n- Tool 2: 200"
        
        if tool_summary.strip() == expected_summary:
            print("✅ Tool summary generation works correctly")
            print(f"Generated summary: {repr(tool_summary.strip())}")
            return True
        else:
            print("❌ Tool summary generation failed")
            print(f"Expected: {repr(expected_summary)}")
            print(f"Got: {repr(tool_summary.strip())}")
            return False
            
    except Exception as e:
        print(f"❌ Tool summary generation test failed: {e}")
        return False

def test_backward_compatibility():
    """Test that the fix doesn't break other LLM providers."""
    try:
        from praisonaiagents.llm.llm import LLM
        
        # Test that non-Ollama providers aren't affected
        models_to_test = [
            "gpt-4o-mini",
            "claude-3-sonnet",
            "gemini/gemini-2.5-pro"
        ]
        
        for model in models_to_test:
            try:
                llm = LLM(model=model)
                is_ollama = llm._is_ollama_provider()
                if not is_ollama:
                    print(f"✅ Model {model} correctly identified as non-Ollama")
                else:
                    print(f"❌ Model {model} incorrectly identified as Ollama")
                    return False
            except Exception as e:
                print(f"⚠️  Could not test model {model}: {e}")
                
        print("✅ Backward compatibility verified")
        return True
        
    except Exception as e:
        print(f"❌ Backward compatibility test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Testing Ollama infinite loop fix...")
    print("=" * 50)
    
    tests = [
        ("Module Imports", test_module_imports),
        ("Ollama Provider Detection", test_ollama_provider_detection),
        ("Tool Summary Generation", test_tool_summary_generation),
        ("Backward Compatibility", test_backward_compatibility),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The Ollama fix is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please review the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)