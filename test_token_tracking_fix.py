#!/usr/bin/env python3
"""
Test script to verify that metrics=True is properly passed from Agent to LLM instance.
This test verifies the fix without requiring an actual API call.
"""

import os
import sys

# Add the source path
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

try:
    from praisonaiagents import Agent
    
    print("✅ Testing Agent with metrics=True parameter...")
    
    # Test 1: Agent with string LLM and metrics=True
    agent = Agent(
        name="Test Agent",
        role="Test Role",
        goal="Test Goal",
        backstory="Test backstory",
        llm="gpt-4o-mini",
        metrics=True,
        base_url="http://localhost:1234/v1",  # Use local URL to trigger LLM instance creation
        api_key="test-key"
    )
    
    # Check if LLM instance was created
    if hasattr(agent, 'llm_instance') and agent.llm_instance:
        print("✅ LLM instance created successfully")
        
        # Check if metrics parameter was passed
        if hasattr(agent.llm_instance, 'metrics') and agent.llm_instance.metrics == True:
            print("✅ SUCCESS: metrics=True was properly passed to LLM instance!")
            print(f"   Agent.metrics: {agent.metrics}")
            print(f"   LLM.metrics: {agent.llm_instance.metrics}")
        else:
            print(f"❌ FAILED: metrics parameter not passed correctly")
            print(f"   Agent.metrics: {agent.metrics}")
            print(f"   LLM.metrics: {getattr(agent.llm_instance, 'metrics', 'NOT_FOUND')}")
    else:
        print("❌ LLM instance not created")
    
    # Test 2: Agent with dict LLM config and metrics=True
    print("\n✅ Testing Agent with dict LLM config and metrics=True...")
    
    agent2 = Agent(
        name="Test Agent 2", 
        role="Test Role",
        goal="Test Goal",
        backstory="Test backstory",
        llm={"model": "gpt-4o-mini", "base_url": "http://localhost:1234/v1"},
        metrics=True,
        api_key="test-key"
    )
    
    if hasattr(agent2, 'llm_instance') and agent2.llm_instance:
        print("✅ LLM instance created successfully")
        
        if hasattr(agent2.llm_instance, 'metrics') and agent2.llm_instance.metrics == True:
            print("✅ SUCCESS: metrics=True was properly passed to LLM instance!")
            print(f"   Agent.metrics: {agent2.metrics}")
            print(f"   LLM.metrics: {agent2.llm_instance.metrics}")
        else:
            print(f"❌ FAILED: metrics parameter not passed correctly")
            print(f"   Agent.metrics: {agent2.metrics}")
            print(f"   LLM.metrics: {getattr(agent2.llm_instance, 'metrics', 'NOT_FOUND')}")
    else:
        print("❌ LLM instance not created")
    
    # Test 3: Agent with provider/model format and metrics=True 
    print("\n✅ Testing Agent with provider/model format and metrics=True...")
    
    agent3 = Agent(
        name="Test Agent 3",
        role="Test Role", 
        goal="Test Goal",
        backstory="Test backstory",
        llm="openai/gpt-4o-mini",
        metrics=True,
        api_key="test-key"
    )
    
    if hasattr(agent3, 'llm_instance') and agent3.llm_instance:
        print("✅ LLM instance created successfully")
        
        if hasattr(agent3.llm_instance, 'metrics') and agent3.llm_instance.metrics == True:
            print("✅ SUCCESS: metrics=True was properly passed to LLM instance!")
            print(f"   Agent.metrics: {agent3.metrics}")
            print(f"   LLM.metrics: {agent3.llm_instance.metrics}")
        else:
            print(f"❌ FAILED: metrics parameter not passed correctly")
            print(f"   Agent.metrics: {agent3.metrics}")
            print(f"   LLM.metrics: {getattr(agent3.llm_instance, 'metrics', 'NOT_FOUND')}")
    else:
        print("❌ LLM instance not created")
        
    print("\n🎯 Token tracking fix verification complete!")
    
except Exception as e:
    print(f"❌ Error during test: {e}")
    import traceback
    traceback.print_exc()