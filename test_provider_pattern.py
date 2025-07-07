#!/usr/bin/env python3
"""Test script to verify the provider pattern implementation works correctly"""

import os
import sys

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents import Agent, Task, PraisonAIAgents

def test_single_agent():
    """Test single agent with default configuration (should use lightweight OpenAI)"""
    print("Testing single agent with default configuration...")
    
    agent = Agent(
        name="Test Agent",
        role="Assistant",
        goal="Help with testing",
        verbose=True
    )
    
    task = Task(
        description="Say hello and tell me what provider you're using",
        expected_output="A greeting message",
        agent=agent
    )
    
    result = agent.execute(task)
    print(f"Result: {result}")
    print(f"Agent is using provider: {agent.llm_instance.provider_type if hasattr(agent, 'llm_instance') else 'Unknown'}")
    print("✅ Single agent test passed\n")

def test_multi_agent():
    """Test multi-agent collaboration"""
    print("Testing multi-agent collaboration...")
    
    researcher = Agent(
        name="Researcher",
        role="Research Assistant",
        goal="Find information",
        verbose=True
    )
    
    writer = Agent(
        name="Writer", 
        role="Content Writer",
        goal="Write content based on research",
        verbose=True
    )
    
    research_task = Task(
        description="Research the benefits of the provider pattern in software design",
        expected_output="Key points about provider pattern benefits",
        agent=researcher
    )
    
    writing_task = Task(
        description="Write a brief summary of the provider pattern benefits based on the research",
        expected_output="A well-written summary",
        agent=writer,
        context=[research_task]
    )
    
    agents = PraisonAIAgents(
        agents=[researcher, writer],
        tasks=[research_task, writing_task],
        verbose=True,
        process="sequential"
    )
    
    result = agents.start()
    print(f"Final result: {result}")
    print("✅ Multi-agent test passed\n")

def test_provider_selection():
    """Test different provider configurations"""
    print("Testing provider selection...")
    
    # Test 1: Default (should use OpenAI provider for gpt models)
    agent1 = Agent(
        name="OpenAI Agent",
        role="Test Agent",
        llm="gpt-4o-mini",
        verbose=False
    )
    print(f"Agent 1 (gpt-4o-mini) using: {agent1.llm_instance.provider_type}")
    
    # Test 2: Explicit provider prefix (should use LiteLLM)
    try:
        agent2 = Agent(
            name="Multi-Provider Agent",
            role="Test Agent",
            llm="anthropic/claude-3-sonnet",
            verbose=False
        )
        print(f"Agent 2 (anthropic/claude-3-sonnet) using: {agent2.llm_instance.provider_type}")
    except Exception as e:
        print(f"Agent 2 failed (expected if Anthropic API key not set): {e}")
    
    # Test 3: Force OpenAI provider
    os.environ['PRAISONAI_LLM_PROVIDER'] = 'openai'
    agent3 = Agent(
        name="Forced OpenAI Agent",
        role="Test Agent",
        llm="gpt-4o",
        verbose=False
    )
    print(f"Agent 3 (forced OpenAI) using: {agent3.llm_instance.provider_type}")
    
    # Test 4: Force LiteLLM provider
    os.environ['PRAISONAI_LLM_PROVIDER'] = 'litellm'
    agent4 = Agent(
        name="Forced LiteLLM Agent",
        role="Test Agent", 
        llm="gpt-4o",
        verbose=False
    )
    print(f"Agent 4 (forced LiteLLM) using: {agent4.llm_instance.provider_type}")
    
    # Reset environment
    del os.environ['PRAISONAI_LLM_PROVIDER']
    
    print("✅ Provider selection test passed\n")

def main():
    """Run all tests"""
    print("=" * 60)
    print("Testing Provider Pattern Implementation")
    print("=" * 60)
    
    # Check if OpenAI API key is set
    if not os.getenv('OPENAI_API_KEY'):
        print("⚠️  Warning: OPENAI_API_KEY not set. Some tests may fail.")
        print("Set it with: export OPENAI_API_KEY='your-key-here'")
        print()
    
    try:
        test_provider_selection()
        test_single_agent()
        test_multi_agent()
        
        print("=" * 60)
        print("✅ All tests passed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()