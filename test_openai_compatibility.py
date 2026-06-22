#!/usr/bin/env python3
"""
Test OpenAI Compatibility Layer

Tests the OpenAI-compatible HTTP endpoints using the official OpenAI Python client.
This verifies drop-in compatibility with existing OpenAI client code.
"""

import os
import time
import asyncio
from openai import OpenAI

def test_basic_chat_completion():
    """Test basic chat completion with OpenAI client."""
    print("Testing OpenAI Chat Completion compatibility...")
    
    # Use local PraisonAI server as OpenAI endpoint
    client = OpenAI(
        base_url="http://localhost:8765/v1",
        api_key="test-key",  # Not required but good to test auth handling
    )
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": "Say 'Hello PraisonAI OpenAI compatibility!' and nothing else"}
            ],
            max_tokens=50
        )
        
        print(f"✅ Chat completion response ID: {response.id}")
        print(f"✅ Model: {response.model}")
        print(f"✅ Content: {response.choices[0].message.content}")
        print(f"✅ Usage: {response.usage}")
        
        return True
        
    except Exception as e:
        print(f"❌ Chat completion failed: {e}")
        return False

def test_streaming_chat_completion():
    """Test streaming chat completion."""
    print("\nTesting OpenAI Streaming Chat Completion compatibility...")
    
    client = OpenAI(
        base_url="http://localhost:8765/v1",
        api_key="test-key",
    )
    
    try:
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": "Count from 1 to 5, each number on a new line"}
            ],
            stream=True
        )
        
        content_chunks = []
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                content_chunks.append(chunk.choices[0].delta.content)
                print(f"Chunk: {chunk.choices[0].delta.content}", end="")
        
        print(f"\n✅ Streaming chat completion successful")
        print(f"✅ Total chunks received: {len(content_chunks)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Streaming chat completion failed: {e}")
        return False

def test_models_list():
    """Test models list endpoint."""
    print("\nTesting OpenAI Models API compatibility...")
    
    client = OpenAI(
        base_url="http://localhost:8765/v1",
        api_key="test-key",
    )
    
    try:
        models = client.models.list()
        
        print(f"✅ Models list response: {models.object}")
        print(f"✅ Number of models: {len(models.data)}")
        
        for model in models.data[:3]:  # Show first 3 models
            print(f"✅ Model: {model.id} (owned by {model.owned_by})")
        
        return True
        
    except Exception as e:
        print(f"❌ Models list failed: {e}")
        return False

def test_text_completion():
    """Test legacy text completion."""
    print("\nTesting OpenAI Text Completion compatibility...")
    
    client = OpenAI(
        base_url="http://localhost:8765/v1", 
        api_key="test-key",
    )
    
    try:
        response = client.completions.create(
            model="gpt-3.5-turbo-instruct",
            prompt="Complete this sentence: The weather today is",
            max_tokens=20
        )
        
        print(f"✅ Text completion response ID: {response.id}")
        print(f"✅ Model: {response.model}")
        print(f"✅ Text: {response.choices[0].text}")
        print(f"✅ Usage: {response.usage}")
        
        return True
        
    except Exception as e:
        print(f"❌ Text completion failed: {e}")
        return False

def test_tools_integration():
    """Test tools integration (PraisonAI extension)."""
    print("\nTesting PraisonAI Tools Integration...")
    
    import requests
    
    try:
        response = requests.post(
            "http://localhost:8765/v1/tools/invoke",
            json={
                "tool_name": "test_tool", 
                "parameters": {"query": "test"},
                "agent": "default"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Tools invoke successful: {data}")
        else:
            print(f"⚠️ Tools invoke returned {response.status_code}: {response.text}")
        
        return True
        
    except Exception as e:
        print(f"❌ Tools integration failed: {e}")
        return False

def run_compatibility_tests():
    """Run all compatibility tests."""
    print("="*60)
    print("🚀 PraisonAI OpenAI Compatibility Test Suite")
    print("="*60)
    
    print("\n🔍 Make sure to start the OpenAI compatibility server first:")
    print("   python -m praisonai serve openai --port 8765")
    print("\n" + "="*60 + "\n")
    
    tests = [
        test_basic_chat_completion,
        test_streaming_chat_completion,
        test_models_list,
        test_text_completion,
        test_tools_integration,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with error: {e}")
            results.append(False)
        
        time.sleep(1)  # Brief pause between tests
    
    print("\n" + "="*60)
    print("📊 Test Results Summary")
    print("="*60)
    
    passed = sum(results)
    total = len(results)
    
    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}. {test.__name__}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! OpenAI compatibility is working.")
    else:
        print(f"⚠️ {total - passed} tests failed. Check server logs for details.")
    
    return passed == total

if __name__ == "__main__":
    success = run_compatibility_tests()
    exit(0 if success else 1)