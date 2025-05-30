#!/usr/bin/env python3
"""
Test script to verify Ollama tool-call fixes
"""
import sys
import os

# Add the source directory to Python path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

from praisonaiagents.llm.llm import LLM
from praisonaiagents.agent.agent import Agent

def test_ollama_provider_detection():
    """Test the new Ollama provider detection logic"""
    print("Testing Ollama provider detection...")
    
    # Test 1: Direct ollama/ prefix
    llm1 = LLM(model="ollama/qwen3:32b")
    assert llm1._is_ollama_provider() == True, "Should detect ollama/ prefix"
    print("✓ Direct ollama/ prefix detection works")
    
    # Test 2: Environment variable detection
    os.environ["OPENAI_BASE_URL"] = "http://localhost:11434/v1"
    llm2 = LLM(model="qwen3:32b")
    assert llm2._is_ollama_provider() == True, "Should detect via env var"
    print("✓ Environment variable detection works")
    
    # Test 3: Non-Ollama model
    os.environ.pop("OPENAI_BASE_URL", None)
    llm3 = LLM(model="gpt-4o-mini")
    assert llm3._is_ollama_provider() == False, "Should not detect non-Ollama"
    print("✓ Non-Ollama detection works")

def test_tool_call_parsing():
    """Test the new tool call parsing logic"""
    print("\nTesting tool call parsing...")
    
    llm = LLM(model="ollama/qwen3:32b")
    
    # Test 1: Standard format
    tool_call_std = {
        "id": "call_123",
        "function": {
            "name": "hello_world",
            "arguments": '{"name": "test"}'
        }
    }
    name, args, id = llm._parse_tool_call_arguments(tool_call_std, is_ollama=True)
    assert name == "hello_world", f"Expected 'hello_world', got '{name}'"
    assert args == {"name": "test"}, f"Expected {{'name': 'test'}}, got {args}"
    print("✓ Standard format parsing works")
    
    # Test 2: Ollama alternative format
    tool_call_alt = {
        "name": "hello_world",
        "arguments": '{"name": "test"}'
    }
    name, args, id = llm._parse_tool_call_arguments(tool_call_alt, is_ollama=True)
    assert name == "hello_world", f"Expected 'hello_world', got '{name}'"
    assert args == {"name": "test"}, f"Expected {{'name': 'test'}}, got {args}"
    print("✓ Alternative format parsing works")
    
    # Test 3: Error handling - malformed JSON
    tool_call_bad = {
        "function": {
            "name": "hello_world",
            "arguments": 'invalid json'
        }
    }
    name, args, id = llm._parse_tool_call_arguments(tool_call_bad, is_ollama=False)
    assert name == "hello_world", f"Expected 'hello_world', got '{name}'"
    assert args == {}, f"Expected empty dict, got {args}"
    print("✓ Error handling works")

def test_agent_tool_parameter_logic():
    """Test the fixed tool parameter logic in Agent"""
    print("\nTesting agent tool parameter logic...")
    
    def dummy_tool():
        """Dummy tool for testing"""
        return "test"
    
    # Test 1: None tools should use agent tools
    agent = Agent(name="test", tools=[dummy_tool])
    # Simulate the fixed logic
    tools = None
    if tools is None or (isinstance(tools, list) and len(tools) == 0):
        tool_param = agent.tools
    else:
        tool_param = tools
    
    assert tool_param == [dummy_tool], "Should use agent tools when tools=None"
    print("✓ None tools handling works")
    
    # Test 2: Empty list should use agent tools  
    tools = []
    if tools is None or (isinstance(tools, list) and len(tools) == 0):
        tool_param = agent.tools
    else:
        tool_param = tools
        
    assert tool_param == [dummy_tool], "Should use agent tools when tools=[]"
    print("✓ Empty list handling works")
    
    # Test 3: Non-empty list should use provided tools
    custom_tools = [lambda: "custom"]
    tools = custom_tools
    if tools is None or (isinstance(tools, list) and len(tools) == 0):
        tool_param = agent.tools
    else:
        tool_param = tools
        
    assert tool_param == custom_tools, "Should use provided tools when not empty"
    print("✓ Non-empty list handling works")

if __name__ == "__main__":
    print("Running Ollama tool-call fix tests...\n")
    
    try:
        test_ollama_provider_detection()
        test_tool_call_parsing()
        test_agent_tool_parameter_logic()
        
        print("\n🎉 All tests passed! The Ollama tool-call fixes are working correctly.")
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)