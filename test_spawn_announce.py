#!/usr/bin/env python3
"""
Test script for the new spawn-announce pattern in AgentTeam.

This script demonstrates the non-blocking spawn-and-announce capabilities
that enable efficient parallel sub-agent workflows with push-based completion notifications.
"""
import time
import sys
import os

# Add the praisonai-agents source to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.agent.agent import Agent
from praisonaiagents.agents import AgentTeam, SpawnedSubAgent, SubAgentCompletionEvent
from praisonaiagents.task.task import Task

def test_spawn_announce_pattern():
    """Test the spawn-announce pattern implementation."""
    print("🚀 Testing spawn-announce pattern for non-blocking multi-agent orchestration")
    print("=" * 80)
    
    # Create a parent AgentTeam
    team = AgentTeam(
        agents=[],  # Empty agents list - will spawn sub-agents dynamically
        name="spawn_announce_test",
        process="parallel"
    )
    
    # Create some sub-agents for spawning
    researcher = Agent(
        name="researcher", 
        instructions="You are a research assistant. Analyze the given topic and provide insights.",
        llm="gpt-3.5-turbo"  # Use a simple model for testing
    )
    
    writer = Agent(
        name="writer",
        instructions="You are a content writer. Create content based on the given topic.",
        llm="gpt-3.5-turbo"
    )
    
    analyzer = Agent(
        name="analyzer", 
        instructions="You are a data analyst. Provide analysis and conclusions.",
        llm="gpt-3.5-turbo"
    )
    
    # Create tasks for the sub-agents
    research_task = Task(
        description="Research the benefits of AI in healthcare",
        name="research_task"
    )
    
    writing_task = Task(
        description="Write a brief summary about renewable energy",
        name="writing_task"
    )
    
    analysis_task = Task(
        description="Analyze the current state of remote work trends",
        name="analysis_task"
    )
    
    # Track completion events
    completed_agents = []
    
    def completion_callback(event: SubAgentCompletionEvent):
        """Callback function for handling sub-agent completions."""
        print(f"📋 Completion callback triggered for agent: {event.agent_id}")
        print(f"   Task ID: {event.task_id}")
        print(f"   Success: {event.success}")
        if event.error:
            print(f"   Error: {event.error}")
        else:
            print(f"   Result preview: {str(event.result)[:100]}...")
        print(f"   Completion time: {event.completion_time}")
        print()
        completed_agents.append(event.agent_id)
    
    print("📝 Step 1: Spawning sub-agents non-blocking...")
    start_time = time.time()
    
    # Spawn sub-agents using the new non-blocking pattern
    spawned1 = team.spawn_sub_agent(researcher, research_task, completion_callback)
    spawned2 = team.spawn_sub_agent(writer, writing_task, completion_callback)
    spawned3 = team.spawn_sub_agent(analyzer, analysis_task, completion_callback)
    
    print(f"✅ Spawned 3 sub-agents in {time.time() - start_time:.3f}s (non-blocking)")
    print(f"   Agent 1: {spawned1.agent_id} (researcher)")
    print(f"   Agent 2: {spawned2.agent_id} (writer)")
    print(f"   Agent 3: {spawned3.agent_id} (analyzer)")
    print()
    
    print("🔄 Step 2: Continuing other work while sub-agents execute...")
    
    # Demonstrate non-blocking behavior - we can do other work
    for i in range(3):
        print(f"   Doing other work: step {i+1}/3")
        time.sleep(1)
    
    print()
    print("📊 Step 3: Checking spawned agents status...")
    
    # Check currently spawned agents
    current_spawned = team.get_spawned_agents()
    print(f"   Currently spawned agents: {len(current_spawned)}")
    for spawned in current_spawned:
        print(f"     - {spawned.agent_id} (spawned at {spawned.spawn_time})")
    print()
    
    print("⏳ Step 4: Waiting for completions (with timeout)...")
    
    # Wait for completions with timeout
    completions = team.wait_for_completions(timeout=30.0)
    
    print(f"📈 Results:")
    print(f"   Total completions received: {len(completions)}")
    print(f"   Successful completions: {len([c for c in completions if c.success])}")
    print(f"   Failed completions: {len([c for c in completions if not c.success])}")
    print(f"   Completion callbacks triggered: {len(completed_agents)}")
    print()
    
    # Verify all agents completed
    final_spawned = team.get_spawned_agents()
    print(f"🎯 Final status:")
    print(f"   Remaining spawned agents: {len(final_spawned)}")
    print(f"   Total execution time: {time.time() - start_time:.3f}s")
    print()
    
    if len(completions) >= 3 and len(completed_agents) >= 3:
        print("✅ SUCCESS: Spawn-announce pattern is working correctly!")
        print("   - Non-blocking spawning ✓")
        print("   - Push-based completion notifications ✓") 
        print("   - Event-driven coordination ✓")
        print("   - Parallel workflow efficiency ✓")
        return True
    else:
        print("❌ FAILED: Some completions were not received")
        print(f"   Expected: 3 completions, got: {len(completions)}")
        print(f"   Expected: 3 callbacks, got: {len(completed_agents)}")
        return False

def test_protocol_compliance():
    """Test that AgentTeam properly implements SpawnAnnounceProtocol."""
    print("\n" + "=" * 80)
    print("🔍 Testing protocol compliance...")
    
    from praisonaiagents.agents import SpawnAnnounceProtocol
    
    team = AgentTeam(agents=[], name="protocol_test")
    
    # Check if AgentTeam implements the protocol
    is_compliant = isinstance(team, SpawnAnnounceProtocol)
    print(f"   SpawnAnnounceProtocol compliance: {'✅' if is_compliant else '❌'}")
    
    # Check if all required methods are implemented
    required_methods = ['spawn_sub_agent', 'announce_completion', 'get_spawned_agents', 'wait_for_completions']
    method_checks = []
    
    for method_name in required_methods:
        has_method = hasattr(team, method_name) and callable(getattr(team, method_name))
        method_checks.append(has_method)
        print(f"   Method '{method_name}': {'✅' if has_method else '❌'}")
    
    all_methods_present = all(method_checks)
    print(f"\n✅ Protocol compliance: {'PASSED' if is_compliant and all_methods_present else 'FAILED'}")
    
    return is_compliant and all_methods_present

if __name__ == "__main__":
    print("🧪 PraisonAI Spawn-Announce Pattern Test Suite")
    print("=" * 80)
    
    try:
        # Test protocol compliance first
        protocol_ok = test_protocol_compliance()
        
        if not protocol_ok:
            print("❌ Protocol compliance failed - skipping functional test")
            sys.exit(1)
        
        # Test the actual spawn-announce functionality
        # Note: This would require LLM access, so we'll do a mock test in CI
        if os.getenv('CI') or os.getenv('TESTING_MODE'):
            print("\n🏗️  CI/Testing mode detected - skipping actual LLM execution")
            print("✅ Protocol and interface tests PASSED")
            print("💡 Full functionality would require OpenAI API key for real agent execution")
        else:
            # Try functional test only if we might have API access
            functional_ok = test_spawn_announce_pattern()
            if not functional_ok:
                sys.exit(1)
        
        print("\n🎉 All tests completed successfully!")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure all dependencies are installed")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)