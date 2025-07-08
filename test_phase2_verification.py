#!/usr/bin/env python3
"""Test script to verify Phase 2 refactoring changes"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praisonai-agents'))

from praisonaiagents.llm.llm import LLM

def test_helper_methods_exist():
    """Verify all helper methods are present"""
    llm = LLM()
    
    # Check Phase 1 method
    assert hasattr(llm, '_supports_streaming_tools'), "Missing _supports_streaming_tools method"
    
    # Check Phase 2 methods
    assert hasattr(llm, '_build_messages'), "Missing _build_messages method"
    assert hasattr(llm, '_format_tools_for_litellm'), "Missing _format_tools_for_litellm method"
    assert hasattr(llm, '_capture_streaming_tool_calls'), "Missing _capture_streaming_tool_calls method"
    assert hasattr(llm, '_serialize_tool_calls'), "Missing _serialize_tool_calls method"
    
    print("✅ All helper methods exist")

def test_format_tools():
    """Test tool formatting functionality"""
    llm = LLM()
    
    # Test with None
    assert llm._format_tools_for_litellm(None) is None
    
    # Test with empty list
    assert llm._format_tools_for_litellm([]) is None
    
    # Test with pre-formatted OpenAI tool
    openai_tool = {
        'type': 'function',
        'function': {
            'name': 'test_tool',
            'description': 'A test tool'
        }
    }
    result = llm._format_tools_for_litellm([openai_tool])
    assert result == [openai_tool]
    
    print("✅ Tool formatting works correctly")

def test_serialize_tool_calls():
    """Test tool call serialization"""
    llm = LLM()
    
    # Test with dict tool calls
    dict_calls = [
        {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "test_func",
                "arguments": '{"arg": "value"}'
            }
        }
    ]
    result = llm._serialize_tool_calls(dict_calls)
    assert result == dict_calls
    
    # Test with object-like tool calls
    class MockToolCall:
        def __init__(self, id, name, args):
            self.id = id
            self.type = "function"
            self.function = type('obj', (object,), {
                'name': name,
                'arguments': args
            })()
    
    obj_calls = [MockToolCall("call_456", "test_func2", '{"arg2": "value2"}')]
    result = llm._serialize_tool_calls(obj_calls)
    assert len(result) == 1
    assert result[0]["id"] == "call_456"
    assert result[0]["function"]["name"] == "test_func2"
    
    print("✅ Tool call serialization works correctly")

def test_streaming_tool_capture():
    """Test streaming tool call capture"""
    llm = LLM()
    
    # Mock delta object
    class MockDelta:
        def __init__(self, has_tools=False):
            if has_tools:
                self.tool_calls = [
                    type('obj', (object,), {
                        'index': 0,
                        'id': 'call_789',
                        'function': type('obj', (object,), {
                            'name': 'stream_tool',
                            'arguments': '{"stream": true}'
                        })()
                    })()
                ]
    
    # Test capture
    tool_calls = []
    delta = MockDelta(has_tools=True)
    llm._capture_streaming_tool_calls(delta, tool_calls)
    
    assert len(tool_calls) == 1
    assert tool_calls[0]["id"] == "call_789"
    assert tool_calls[0]["function"]["name"] == "stream_tool"
    
    print("✅ Streaming tool capture works correctly")

def main():
    """Run all tests"""
    print("Testing Phase 2 refactoring implementation...")
    print("-" * 50)
    
    try:
        test_helper_methods_exist()
        test_format_tools()
        test_serialize_tool_calls()
        test_streaming_tool_capture()
        
        print("-" * 50)
        print("🎉 All tests passed! Phase 2 refactoring is working correctly.")
        
    except AssertionError as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()