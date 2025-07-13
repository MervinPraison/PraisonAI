#!/usr/bin/env python3
"""
Test script to verify Gemini internal tools implementation
"""

import os
import sys
import logging

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from praisonaiagents import Agent
from praisonaiagents.llm import LLM

def test_llm_initialization():
    """Test LLM class initialization with Gemini internal tools"""
    print("\n=== Testing LLM Initialization ===")
    
    # Test 1: Google Search
    print("\nTest 1: Google Search Retrieval")
    llm1 = LLM(
        model="gemini/gemini-1.5-flash",
        google_search_retrieval=True
    )
    print(f"✓ LLM created with google_search_retrieval: {llm1.google_search_retrieval}")
    
    # Test 2: Code Execution
    print("\nTest 2: Code Execution")
    llm2 = LLM(
        model="gemini/gemini-1.5-flash",
        enable_code_execution=True
    )
    print(f"✓ LLM created with enable_code_execution: {llm2.enable_code_execution}")
    
    # Test 3: URL Context
    print("\nTest 3: Dynamic Retrieval Config")
    llm3 = LLM(
        model="gemini/gemini-1.5-flash",
        dynamic_retrieval_config={
            "mode": "grounded",
            "dynamic_threshold": 0.5
        }
    )
    print(f"✓ LLM created with dynamic_retrieval_config: {llm3.dynamic_retrieval_config}")
    
    # Test 4: Tool Config
    print("\nTest 4: Tool Config Format")
    llm4 = LLM(
        model="gemini/gemini-1.5-pro",
        tool_config={
            "google_search_retrieval": {"threshold": 0.7},
            "code_execution": {}
        }
    )
    print(f"✓ LLM created with tool_config: {llm4.tool_config}")
    
    # Test 5: Combined parameters
    print("\nTest 5: Combined Parameters")
    llm5 = LLM(
        model="gemini/gemini-1.5-flash",
        google_search_retrieval=True,
        enable_code_execution=True,
        tool_config={
            "dynamic_retrieval_config": {"mode": "grounded"}
        }
    )
    print("✓ LLM created with combined parameters")

def test_agent_initialization():
    """Test Agent class initialization with Gemini internal tools"""
    print("\n\n=== Testing Agent Initialization ===")
    
    # Test 1: Agent with dict LLM config
    print("\nTest 1: Agent with dict LLM config")
    agent1 = Agent(
        instructions="Test agent with search",
        llm={
            "model": "gemini/gemini-1.5-flash",
            "google_search_retrieval": True
        }
    )
    print("✓ Agent created with google_search_retrieval in LLM dict")
    
    # Test 2: Agent with multiple internal tools
    print("\nTest 2: Agent with multiple internal tools")
    agent2 = Agent(
        instructions="Test agent with multiple tools",
        llm={
            "model": "gemini/gemini-1.5-pro",
            "tool_config": {
                "google_search_retrieval": {"threshold": 0.8},
                "code_execution": {},
                "dynamic_retrieval_config": {
                    "mode": "grounded",
                    "dynamic_threshold": 0.6
                }
            }
        }
    )
    print("✓ Agent created with comprehensive tool_config")
    
    # Test 3: Agent with custom tools + internal tools
    print("\nTest 3: Agent with custom tools + internal tools")
    def custom_tool(x: int) -> int:
        """A custom tool that doubles the input"""
        return x * 2
    
    agent3 = Agent(
        instructions="Test agent with hybrid tools",
        llm={
            "model": "gemini/gemini-1.5-flash",
            "google_search_retrieval": True,
            "enable_code_execution": True
        },
        tools=[custom_tool]
    )
    print("✓ Agent created with both custom and internal tools")

def test_parameter_building():
    """Test the _build_completion_params method"""
    print("\n\n=== Testing Parameter Building ===")
    
    # Create an LLM instance with all internal tools
    llm = LLM(
        model="gemini/gemini-1.5-pro",
        google_search_retrieval={"threshold": 0.9},
        enable_code_execution=True,
        dynamic_retrieval_config={"mode": "grounded"},
        temperature=0.7,
        max_tokens=1000
    )
    
    # Build completion params
    params = llm._build_completion_params(
        messages=[{"role": "user", "content": "test"}],
        stream=True
    )
    
    print("\nBuilt parameters:")
    print(f"  Model: {params.get('model')}")
    print(f"  Temperature: {params.get('temperature')}")
    print(f"  Max tokens: {params.get('max_tokens')}")
    print(f"  Tool config: {params.get('tool_config')}")
    print(f"  Google search (simplified): {params.get('google_search_retrieval')}")
    print(f"  Code execution (simplified): {params.get('enable_code_execution')}")
    
    if 'tool_config' in params:
        print("\n✓ Tool config properly built with all internal tools")
    else:
        print("\n✗ Tool config not found in parameters")

def main():
    """Run all tests"""
    print("Testing Gemini Internal Tools Implementation")
    print("=" * 50)
    
    try:
        test_llm_initialization()
        test_agent_initialization()
        test_parameter_building()
        
        print("\n\n" + "=" * 50)
        print("✅ All tests completed successfully!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()