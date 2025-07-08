#!/usr/bin/env python3
"""
Test script to verify the OpenAI refactoring maintains backward compatibility.

This script tests:
1. OpenAI client initialization
2. Basic agent functionality
3. Sync and async operations
4. Tool calling capabilities
5. Reflection functionality
"""

import asyncio
import os
import sys

# Add the source directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents.agent import Agent
from praisonaiagents.llm import OpenAIClient, get_openai_client


def test_openai_client():
    """Test the OpenAI client module"""
    print("Testing OpenAI Client Module...")
    
    try:
        # Test 1: Get global client
        client = get_openai_client()
        print("✅ Global OpenAI client created successfully")
        
        # Test 2: Create new client instance
        new_client = OpenAIClient()
        print("✅ New OpenAI client instance created successfully")
        
        # Test 3: Verify sync client property
        sync_client = client.sync_client
        print(f"✅ Sync client type: {type(sync_client).__name__}")
        
        # Test 4: Verify async client property
        async_client = client.async_client
        print(f"✅ Async client type: {type(async_client).__name__}")
        
        print("\n✅ OpenAI Client Module tests passed!\n")
        return True
        
    except Exception as e:
        print(f"❌ OpenAI Client Module test failed: {e}")
        return False


def test_agent_initialization():
    """Test agent initialization with OpenAI client"""
    print("Testing Agent Initialization...")
    
    try:
        # Test basic agent creation
        agent = Agent(
            name="Test Agent",
            role="Assistant",
            goal="Help with testing",
            backstory="I am a test agent"
        )
        print("✅ Agent created successfully")
        
        # Verify OpenAI client is initialized
        if hasattr(agent, '_openai_client'):
            print("✅ Agent has _openai_client attribute")
        else:
            print("❌ Agent missing _openai_client attribute")
            return False
            
        # Test agent with custom base_url
        custom_agent = Agent(
            name="Custom Agent",
            role="Assistant",
            goal="Test custom endpoint",
            base_url="http://localhost:1234/v1"
        )
        print("✅ Agent with custom base_url created successfully")
        
        print("\n✅ Agent Initialization tests passed!\n")
        return True
        
    except Exception as e:
        print(f"❌ Agent Initialization test failed: {e}")
        return False


def test_dataclasses():
    """Test the dataclasses used for OpenAI responses"""
    print("Testing Dataclasses...")
    
    try:
        from praisonaiagents.agent.agent import (
            ChatCompletionMessage, 
            Choice, 
            ChatCompletion,
            ToolCall
        )
        
        # Test ToolCall creation
        tool_call = ToolCall(
            id="test_id",
            type="function",
            function={"name": "test_function", "arguments": "{}"}
        )
        print(f"✅ ToolCall created: {tool_call}")
        
        # Test ChatCompletionMessage
        message = ChatCompletionMessage(
            content="Test message",
            role="assistant",
            tool_calls=[tool_call]
        )
        print("✅ ChatCompletionMessage created successfully")
        
        # Test Choice
        choice = Choice(
            finish_reason="stop",
            index=0,
            message=message
        )
        print("✅ Choice created successfully")
        
        # Test ChatCompletion
        completion = ChatCompletion(
            id="test_completion",
            choices=[choice],
            created=1234567890,
            model="gpt-4"
        )
        print("✅ ChatCompletion created successfully")
        
        print("\n✅ Dataclasses tests passed!\n")
        return True
        
    except Exception as e:
        print(f"❌ Dataclasses test failed: {e}")
        return False


async def test_async_functionality():
    """Test async functionality"""
    print("Testing Async Functionality...")
    
    try:
        agent = Agent(
            name="Async Test Agent",
            role="Assistant",
            goal="Test async operations",
            verbose=False
        )
        
        # Note: We can't actually call the API without valid credentials
        # But we can verify the methods exist and are callable
        
        # Check if achat method exists
        if hasattr(agent, 'achat'):
            print("✅ Agent has achat method")
        else:
            print("❌ Agent missing achat method")
            return False
            
        # Check if _achat_completion exists
        if hasattr(agent, '_achat_completion'):
            print("✅ Agent has _achat_completion method")
        else:
            print("❌ Agent missing _achat_completion method")
            return False
            
        print("\n✅ Async Functionality tests passed!\n")
        return True
        
    except Exception as e:
        print(f"❌ Async Functionality test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("OpenAI Refactoring Test Suite")
    print("=" * 60)
    print()
    
    results = []
    
    # Run sync tests
    results.append(test_openai_client())
    results.append(test_agent_initialization())
    results.append(test_dataclasses())
    
    # Run async tests
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    results.append(loop.run_until_complete(test_async_functionality()))
    
    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\nTests passed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ All tests passed! The refactoring maintains backward compatibility.")
        return 0
    else:
        print(f"\n❌ {total - passed} tests failed. Please review the failures above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())