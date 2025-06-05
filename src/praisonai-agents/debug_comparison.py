#!/usr/bin/env python3

import sys
import traceback
from praisonaiagents import Agent, MCP

def test_agent_direct():
    """Test gpt-4o-mini (agent.py path)"""
    print("=" * 50)
    print("TESTING: gpt-4o-mini (agent.py direct calls)")
    print("=" * 50)
    
    try:
        agent = Agent(
            instructions="""You are a helpful assistant that can break down complex problems.
            Use the available tools when relevant to perform step-by-step analysis.""",
            llm="gpt-4o-mini",
            tools=MCP("npx -y @modelcontextprotocol/server-sequential-thinking")
        )
        
        print("✅ Agent created successfully")
        print(f"✅ Agent LLM: {getattr(agent, 'llm', 'Not set')}")
        print(f"✅ Agent using custom LLM: {getattr(agent, '_using_custom_llm', False)}")
        
        result = agent.start("What are 3 steps to make coffee?")
        print("✅ Agent execution completed successfully")
        return True, result
        
    except Exception as e:
        print(f"❌ Error in agent direct: {e}")
        traceback.print_exc()
        return False, str(e)

def test_llm_class():
    """Test openai/gpt-4o-mini (llm.py path)"""
    print("\n" + "=" * 50)
    print("TESTING: openai/gpt-4o-mini (llm.py LiteLLM)")
    print("=" * 50)
    
    try:
        agent = Agent(
            instructions="""You are a helpful assistant that can break down complex problems.
            Use the available tools when relevant to perform step-by-step analysis.""",
            llm="openai/gpt-4o-mini",
            tools=MCP("npx -y @modelcontextprotocol/server-sequential-thinking")
        )
        
        print("✅ Agent created successfully")
        print(f"✅ Agent LLM instance: {getattr(agent, 'llm_instance', 'Not set')}")
        print(f"✅ Agent using custom LLM: {getattr(agent, '_using_custom_llm', False)}")
        
        result = agent.start("What are 3 steps to make coffee?")
        print("✅ Agent execution completed successfully")
        return True, result
        
    except Exception as e:
        print(f"❌ Error in llm class: {e}")
        traceback.print_exc()
        return False, str(e)

if __name__ == "__main__":
    print("🔍 DEBUGGING: Comparing both LLM approaches\n")
    
    # Test agent direct
    success1, result1 = test_agent_direct()
    
    # Test LLM class
    success2, result2 = test_llm_class()
    
    print("\n" + "=" * 50)
    print("FINAL RESULTS")
    print("=" * 50)
    
    if success1:
        print("✅ gpt-4o-mini (agent.py) - SUCCESS")
    else:
        print("❌ gpt-4o-mini (agent.py) - FAILED")
        print(f"   Error: {result1}")
    
    if success2:
        print("✅ openai/gpt-4o-mini (llm.py) - SUCCESS")
    else:
        print("❌ openai/gpt-4o-mini (llm.py) - FAILED")
        print(f"   Error: {result2}")
    
    if success1 and success2:
        print("\n🎉 BOTH FORMATS WORK CORRECTLY!")
        print("📝 The issue mentioned might be resolved or was a different problem.")
    elif success1 and not success2:
        print("\n⚠️  CONFIRMED: LLM class path has issues")
        print("📝 Need to debug the LLM class implementation")
    elif success2 and not success1:
        print("\n⚠️  CONFIRMED: Agent direct path has issues")
        print("📝 Need to debug the agent direct implementation")
    else:
        print("\n💥 BOTH PATHS FAILED - Something is fundamentally wrong")