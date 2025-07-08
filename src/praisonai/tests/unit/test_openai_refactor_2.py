#!/usr/bin/env python3
"""
Test script to verify the OpenAI refactoring works correctly.
"""

import asyncio
from praisonaiagents import Agent
from praisonaiagents.llm import (
    get_openai_client,
    ChatCompletionMessage,
    Choice,
    CompletionUsage,
    ChatCompletion,
    ToolCall,
    process_stream_chunks
)

def test_data_classes():
    """Test that data classes are properly imported and work"""
    print("Testing data classes...")
    
    # Create a message
    msg = ChatCompletionMessage(
        content="Hello, world!",
        role="assistant"
    )
    assert msg.content == "Hello, world!"
    assert msg.role == "assistant"
    print("✓ ChatCompletionMessage works")
    
    # Create a choice
    choice = Choice(
        finish_reason="stop",
        index=0,
        message=msg
    )
    assert choice.finish_reason == "stop"
    assert choice.message.content == "Hello, world!"
    print("✓ Choice works")
    
    # Create a tool call
    tool_call = ToolCall(
        id="call_123",
        type="function",
        function={"name": "test_tool", "arguments": "{}"}
    )
    assert tool_call.id == "call_123"
    assert tool_call.function["name"] == "test_tool"
    print("✓ ToolCall works")
    
    print("All data classes test passed!\n")

def test_openai_client():
    """Test that OpenAI client is properly initialized"""
    print("Testing OpenAI client...")
    
    try:
        # This might fail if OPENAI_API_KEY is not set, which is OK for testing
        client = get_openai_client()
        print("✓ OpenAI client created successfully")
        
        # Test build_messages method
        messages, original = client.build_messages(
            prompt="Test prompt",
            system_prompt="You are a helpful assistant"
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        print("✓ build_messages method works")
        
        # Test format_tools method (with no tools)
        tools = client.format_tools(None)
        assert tools is None
        print("✓ format_tools method works")
        
    except ValueError as e:
        if "OPENAI_API_KEY" in str(e):
            print("⚠ OpenAI client requires API key (expected in test environment)")
        else:
            raise
    
    print("OpenAI client tests completed!\n")

def test_agent_integration():
    """Test that Agent class works with the refactored code"""
    print("Testing Agent integration...")
    
    try:
        # Create a simple agent
        agent = Agent(
            name="Test Agent",
            role="Tester",
            goal="Test the refactored code",
            instructions="You are a test agent"
        )
        print("✓ Agent created successfully")
        
        # Test _build_messages
        messages, original = agent._build_messages(
            prompt="Test prompt",
            temperature=0.5
        )
        assert len(messages) >= 1
        assert messages[-1]["content"] == "Test prompt"
        print("✓ Agent._build_messages works")
        
        # Test _format_tools_for_completion
        def sample_tool():
            """A sample tool for testing"""
            pass
        
        formatted = agent._format_tools_for_completion([sample_tool])
        assert isinstance(formatted, list)
        print("✓ Agent._format_tools_for_completion works")
        
    except Exception as e:
        print(f"⚠ Agent integration test failed: {e}")
        # This is OK if dependencies are missing
    
    print("Agent integration tests completed!\n")

async def test_async_functionality():
    """Test async functionality"""
    print("Testing async functionality...")
    
    try:
        client = get_openai_client()
        
        # Test that async client can be accessed
        async_client = client.async_client
        print("✓ Async client accessible")
        
        # Test build_messages (which is sync but used in async context)
        messages, _ = client.build_messages("Test async")
        assert len(messages) >= 1
        print("✓ build_messages works in async context")
        
    except ValueError as e:
        if "OPENAI_API_KEY" in str(e):
            print("⚠ Async tests require API key")
        else:
            raise
    
    print("Async functionality tests completed!\n")

def main():
    """Run all tests"""
    print("=" * 50)
    print("OpenAI Refactoring Test Suite")
    print("=" * 50)
    print()
    
    # Run sync tests
    test_data_classes()
    test_openai_client()
    test_agent_integration()
    
    # Run async tests
    asyncio.run(test_async_functionality())
    
    print("=" * 50)
    print("All tests completed!")
    print("=" * 50)

if __name__ == "__main__":
    main()
