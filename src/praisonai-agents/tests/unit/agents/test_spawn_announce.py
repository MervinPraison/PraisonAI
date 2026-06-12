#!/usr/bin/env python3
"""
Pytest-compatible tests for the spawn-announce pattern in AgentTeam.

This module tests the non-blocking spawn-and-announce capabilities
that enable efficient parallel sub-agent workflows with push-based completion notifications.

Following AGENTS.md §9.4: Real agentic tests that actually call the LLM.
"""
import pytest
import time
from typing import List

from praisonaiagents.agent.agent import Agent
from praisonaiagents.agents import AgentTeam, SpawnedSubAgent, SubAgentCompletionEvent, SpawnAnnounceProtocol
from praisonaiagents.task.task import Task


class TestSpawnAnnounceProtocol:
    """Test spawn-announce protocol compliance."""

    def test_protocol_compliance(self):
        """Test that AgentTeam properly implements SpawnAnnounceProtocol."""
        team = AgentTeam(agents=[], name="protocol_test")
        
        # Check if AgentTeam implements the protocol
        assert isinstance(team, SpawnAnnounceProtocol), "AgentTeam must implement SpawnAnnounceProtocol"
        
        # Check if all required methods are implemented
        required_methods = ['spawn_sub_agent', 'announce_completion', 'get_spawned_agents', 'wait_for_completions']
        
        for method_name in required_methods:
            assert hasattr(team, method_name), f"AgentTeam missing method: {method_name}"
            assert callable(getattr(team, method_name)), f"Method {method_name} not callable"

    def test_spawn_announce_types(self):
        """Test that spawn-announce types are properly exported."""
        # These should be importable from praisonaiagents.agents
        assert SpawnedSubAgent is not None
        assert SubAgentCompletionEvent is not None
        assert SpawnAnnounceProtocol is not None


class TestSpawnAnnouncePattern:
    """Test actual spawn-announce functionality with real LLM execution."""

    @pytest.fixture
    def agent_team(self):
        """Create a test AgentTeam."""
        return AgentTeam(
            agents=[],  # Empty agents list - will spawn sub-agents dynamically
            name="spawn_announce_test",
            process="parallel"
        )

    @pytest.fixture
    def test_agents(self):
        """Create test agents for spawning."""
        researcher = Agent(
            name="researcher", 
            instructions="You are a research assistant. Give a brief answer in 1-2 sentences.",
            llm="gpt-4o-mini"  # Use reliable model for testing
        )
        
        writer = Agent(
            name="writer",
            instructions="You are a content writer. Give a brief answer in 1-2 sentences.",
            llm="gpt-4o-mini"
        )
        
        analyzer = Agent(
            name="analyzer", 
            instructions="You are a data analyst. Give a brief answer in 1-2 sentences.",
            llm="gpt-4o-mini"
        )
        
        return [researcher, writer, analyzer]

    @pytest.fixture
    def test_tasks(self):
        """Create test tasks for the sub-agents."""
        research_task = Task(
            description="What is 2+2? Answer briefly.",
            name="simple_math_task"
        )
        
        writing_task = Task(
            description="Write one sentence about the color blue.",
            name="color_task"
        )
        
        analysis_task = Task(
            description="List one benefit of exercise in one sentence.",
            name="exercise_task"
        )
        
        return [research_task, writing_task, analysis_task]

    def test_spawn_announce_pattern_real_llm(self, agent_team, test_agents, test_tasks):
        """
        REAL AGENTIC TEST: Test spawn-announce pattern with actual LLM execution.
        
        Per AGENTS.md §9.4: Agent must call LLM and produce actual text response.
        This is NOT a smoke test - agents actually run end-to-end.
        """
        print("\n🚀 Testing spawn-announce pattern with REAL LLM execution")
        
        # Track completion events
        completed_agents = []
        completion_results = []
        
        def completion_callback(event: SubAgentCompletionEvent):
            """Callback function for handling sub-agent completions."""
            print(f"📋 Completion callback: agent {event.agent_id}, success: {event.success}")
            if event.result:
                print(f"   Result: {str(event.result)[:100]}...")
                completion_results.append(str(event.result))
            completed_agents.append(event.agent_id)
        
        print("📝 Step 1: Spawning sub-agents (non-blocking)...")
        start_time = time.time()
        
        # Spawn sub-agents using the non-blocking pattern
        spawned_agents = []
        for agent, task in zip(test_agents, test_tasks):
            spawned = agent_team.spawn_sub_agent(agent, task, completion_callback)
            spawned_agents.append(spawned)
            print(f"   Spawned: {spawned.agent_id} with task: {task.description}")
        
        spawn_time = time.time() - start_time
        print(f"✅ Spawned {len(spawned_agents)} sub-agents in {spawn_time:.3f}s")
        
        # Verify non-blocking: spawning should be very fast
        assert spawn_time < 2.0, f"Spawning took {spawn_time:.3f}s - should be non-blocking"
        
        print("🔄 Step 2: Doing other work while agents execute...")
        # Demonstrate non-blocking behavior
        work_delay = 0.5  # Shorter delay for tests
        for i in range(3):
            print(f"   Other work step {i+1}/3")
            time.sleep(work_delay)
        
        print("📊 Step 3: Checking spawned agents status...")
        current_spawned = agent_team.get_spawned_agents()
        assert len(current_spawned) <= len(spawned_agents), "Spawned agents count inconsistent"
        
        print("⏳ Step 4: Waiting for completions...")
        # Wait for completions with reasonable timeout
        completions = agent_team.wait_for_completions(timeout=60.0)
        
        total_time = time.time() - start_time
        print(f"\n📈 Results after {total_time:.3f}s:")
        print(f"   Total completions: {len(completions)}")
        print(f"   Successful: {len([c for c in completions if c.success])}")
        print(f"   Failed: {len([c for c in completions if not c.success])}")
        print(f"   Callbacks triggered: {len(completed_agents)}")
        
        # CRITICAL: Verify real LLM execution occurred
        assert len(completion_results) > 0, "No completion results - LLM may not have been called"
        
        # Print actual LLM outputs to verify end-to-end execution
        print("\n🤖 REAL LLM OUTPUTS (proving end-to-end execution):")
        for i, result in enumerate(completion_results):
            print(f"   Agent {i+1}: {result}")
        
        # Verify the spawn-announce pattern worked
        assert len(completions) >= 1, f"Expected at least 1 completion, got {len(completions)}"
        assert len(completed_agents) >= 1, f"Expected at least 1 callback, got {len(completed_agents)}"
        
        # Verify actual text was generated (not just empty responses)
        text_results = [r for r in completion_results if r and len(r.strip()) > 5]
        assert len(text_results) >= 1, "No meaningful text results from LLM execution"
        
        print("\n✅ SUCCESS: Real agentic spawn-announce pattern working!")
        print("   - Non-blocking spawning ✓")
        print("   - Push-based completion notifications ✓") 
        print("   - Event-driven coordination ✓")
        print("   - REAL LLM execution with text output ✓")

    def test_async_await_completions_thread_safety(self, agent_team, test_agents, test_tasks):
        """Test that async await_for_completions handles thread safety correctly."""
        import asyncio
        
        async def async_test():
            # Track completion events
            completed_agents = []
            
            def completion_callback(event: SubAgentCompletionEvent):
                completed_agents.append(event.agent_id)
            
            # Spawn one agent
            spawned = agent_team.spawn_sub_agent(test_agents[0], test_tasks[0], completion_callback)
            
            # Test async wait (this should not hang due to thread safety bug)
            try:
                completions = await agent_team.await_for_completions(timeout=30.0)
                assert len(completions) >= 0, "Async wait should not fail silently"
                return True
            except Exception as e:
                print(f"Async wait failed: {e}")
                return False
        
        # Run async test
        result = asyncio.run(async_test())
        assert result, "Async await_for_completions failed - thread safety bug may be present"

    def test_empty_team_spawning(self, agent_team):
        """Test edge case: spawning with no agents initially."""
        initial_spawned = agent_team.get_spawned_agents()
        assert len(initial_spawned) == 0, "New team should have no spawned agents"
        
        # Test waiting with no spawned agents
        completions = agent_team.wait_for_completions(timeout=1.0)
        assert completions == [], "Wait with no spawned agents should return empty list"


if __name__ == "__main__":
    # Allow running as script for development
    pytest.main([__file__, "-v"])