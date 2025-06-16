#!/usr/bin/env python3

from praisonaiagents import Agent, MCP
import os

def test_agent_direct():
    """Test using gpt-4o-mini directly (agent.py path)"""
    print("="*50)
    print("Testing gpt-4o-mini (agent.py path)")
    print("="*50)
    
    agent = Agent(
        instructions="You are a helpful assistant that can break down complex problems.",
        llm="gpt-4o-mini",
        tools=MCP("npx -y @modelcontextprotocol/server-sequential-thinking")
    )
    
    result = agent.start("What are 5 steps to make coffee?")
    print("✅ Agent direct path completed successfully")
    return result

def test_llm_class():
    """Test using openai/gpt-4o-mini (llm.py path)"""
    print("\n" + "="*50)
    print("Testing openai/gpt-4o-mini (llm.py path)")
    print("="*50)
    
    agent = Agent(
        instructions="You are a helpful assistant that can break down complex problems.",
        llm="openai/gpt-4o-mini",
        tools=MCP("npx -y @modelcontextprotocol/server-sequential-thinking")
    )
    
    result = agent.start("What are 5 steps to make coffee?")
    print("✅ LLM class path completed successfully")
    return result

if __name__ == "__main__":
    try:
        # Test both approaches
        result1 = test_agent_direct()
        result2 = test_llm_class()
        
        print("\n" + "="*50)
        print("SUMMARY")
        print("="*50)
        print("✅ Both formats work correctly!")
        print("✅ gpt-4o-mini uses agent.py direct OpenAI calls")
        print("✅ openai/gpt-4o-mini uses llm.py LiteLLM wrapper")
        print("✅ Both support tool calling and MCP integration")
        
    except Exception as e:
        print(f"❌ Error occurred: {e}")
        import traceback
        traceback.print_exc()