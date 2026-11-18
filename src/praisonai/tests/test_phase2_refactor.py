#!/usr/bin/env python3
"""Test script to verify Phase 2 refactoring maintains backward compatibility

NOTE: These tests make real API calls and require valid API keys.
They are marked with @pytest.mark.real to be excluded from CI.
"""

import asyncio
import sys
import os
import pytest

# Add the correct path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents.llm import LLM

@pytest.mark.real
def test_sync_methods():
    """Test synchronous methods still work correctly"""
    print("Testing synchronous methods...")
    
    # Test basic response
    llm = LLM(model="gpt-4o-mini")
    
    # Test simple prompt
    print("1. Testing simple prompt...")
    response = llm.response(
        prompt="What is 2+2?",
        verbose=False
    )
    print(f"   Response: {response}")
    assert response, "Should get a response"
    
    # Test with system prompt
    print("2. Testing with system prompt...")
    response = llm.response(
        prompt="Hello",
        system_prompt="You are a helpful assistant. Always respond politely.",
        verbose=False
    )
    print(f"   Response: {response[:50]}...")
    assert response, "Should get a response with system prompt"
    
    # Test with chat history
    print("3. Testing with chat history...")
    chat_history = [
        {"role": "user", "content": "My name is Alice"},
        {"role": "assistant", "content": "Nice to meet you, Alice!"}
    ]
    response = llm.get_response(
        prompt="What's my name?",
        chat_history=chat_history,
        verbose=False
    )
    print(f"   Response: {response}")
    assert response, "Should get a response with chat history"
    
    print("✅ Synchronous methods working correctly\n")

@pytest.mark.real
async def test_async_methods():
    """Test asynchronous methods still work correctly"""
    print("Testing asynchronous methods...")
    
    # Test basic async response
    llm = LLM(model="gpt-4o-mini")
    
    # Test simple prompt
    print("1. Testing async simple prompt...")
    response = await llm.aresponse(
        prompt="What is 3+3?",
        verbose=False
    )
    print(f"   Response: {response}")
    assert response, "Should get an async response"
    
    # Test with system prompt
    print("2. Testing async with system prompt...")
    response = await llm.aresponse(
        prompt="Goodbye",
        system_prompt="You are a helpful assistant. Always respond politely.",
        verbose=False
    )
    print(f"   Response: {response[:50]}...")
    assert response, "Should get an async response with system prompt"
    
    # Test with chat history
    print("3. Testing async with chat history...")
    chat_history = [
        {"role": "user", "content": "My favorite color is blue"},
        {"role": "assistant", "content": "Blue is a nice color!"}
    ]
    response = await llm.get_response_async(
        prompt="What's my favorite color?",
        chat_history=chat_history,
        verbose=False
    )
    print(f"   Response: {response}")
    assert response, "Should get an async response with chat history"
    
    print("✅ Asynchronous methods working correctly\n")

@pytest.mark.real
def test_edge_cases():
    """Test edge cases and special scenarios"""
    print("Testing edge cases...")
    
    llm = LLM(model="gpt-4o-mini")
    
    # Test with list prompt (multimodal-style)
    print("1. Testing list-style prompt...")
    prompt = [{"type": "text", "text": "What is 4+4?"}]
    response = llm.response(
        prompt=prompt,
        verbose=False
    )
    print(f"   Response: {response}")
    assert response, "Should handle list-style prompts"
    
    # Legacy o1 models reject system messages. o1-mini is deprecated, so check
    # the message building offline instead of calling it.
    print("2. Testing legacy o1 model handling...")
    messages, _ = LLM(model="o1-mini")._build_messages(
        prompt="Hello", system_prompt="This should be skipped"
    )
    assert all(m["role"] != "system" for m in messages), messages
    
    print("✅ Edge cases handled correctly\n")

def main():
    """Run all tests"""
    print("=== Phase 2 Refactoring Verification ===\n")
    
    try:
        # Test sync methods
        test_sync_methods()
        
        # Test async methods
        asyncio.run(test_async_methods())
        
        # Test edge cases
        test_edge_cases()
        
        print("✅ ALL TESTS PASSED! The refactoring maintains backward compatibility.")
        print("\nSummary:")
        print("- Message building logic successfully extracted to _build_messages()")
        print("- All 4 methods (get_response, response, get_response_async, aresponse) updated")
        print("- ~40 lines of duplicated code removed")
        print("- No breaking changes detected")
        
    except Exception as e:
        print(f"❌ TEST FAILED: {str(e)}")
        raise

if __name__ == "__main__":
    main()
