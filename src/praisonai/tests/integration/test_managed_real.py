"""
Real agentic integration tests for managed agents.

These tests use actual LLM providers and are gated behind environment variables.
Run with: RUN_REAL_AGENTIC=1 pytest src/praisonai/tests/integration/test_managed_real.py

Requirements:
- ANTHROPIC_API_KEY for Anthropic Managed Agents
- OPENAI_API_KEY for Local Managed Agents  
"""

import os
import pytest
from praisonaiagents.trace.context_events import ContextListSink, trace_context


# Skip all tests unless explicitly enabled
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_REAL_AGENTIC"), 
    reason="Set RUN_REAL_AGENTIC=1 to run real agentic tests"
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anthropic_managed_real():
    """Real agentic test for Anthropic Managed Agents."""
    anthropic = pytest.importorskip("anthropic")
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    
    from praisonai.integrations.managed_agents import ManagedAgent, ManagedConfig
    from praisonaiagents import Agent
    
    # Create managed backend with haiku for speed
    config = ManagedConfig(
        model="claude-haiku-4-5",
        system="You are a helpful assistant. Keep responses very brief.",
        name="TestAgent"
    )
    managed = ManagedAgent(config=config, api_key=api_key)
    
    # Create Agent with backend
    agent = Agent(name="test", backend=managed)
    
    # Execute real prompt
    result = await agent.execute("Say hello in exactly one sentence.")
    
    print(f"\nAnthropicManagedAgent result:\n{result}")
    
    # Assertions
    assert isinstance(result, str)
    assert len(result.strip()) > 0
    assert managed.total_input_tokens > 0
    assert managed.session_id is not None and len(managed.session_id) > 0
    
    # Test session persistence
    first_session = managed.session_id
    result2 = await agent.execute("What did you just say?")
    assert managed.session_id == first_session  # Same session
    
    print(f"Second response: {result2}")


@pytest.mark.integration  
@pytest.mark.asyncio
async def test_local_managed_real_openai():
    """Real agentic test for Local Managed Agents with OpenAI."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")
    
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    from praisonaiagents import Agent
    
    # Create local managed backend
    config = LocalManagedConfig(
        model="gpt-4o-mini",
        system="You are a helpful assistant. Keep responses very brief.",
        name="LocalTestAgent",
        host_packages_ok=True  # Allow host execution for this test
    )
    managed = LocalManagedAgent(config=config, api_key=api_key)
    
    # Create Agent with backend
    agent = Agent(name="test", backend=managed)
    
    # Execute real prompt
    result = await agent.execute("Say hello in exactly one sentence.")
    
    print(f"\nLocalManagedAgent result:\n{result}")
    
    # Assertions
    assert isinstance(result, str)
    assert len(result.strip()) > 0
    assert managed.total_input_tokens > 0
    assert managed._session_id is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_turn_preserves_session():
    """Test that multi-turn conversations preserve session context."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")
    
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    from praisonaiagents import Agent
    
    config = LocalManagedConfig(
        model="gpt-4o-mini",
        system="You are a helpful assistant. Remember what users tell you.",
        host_packages_ok=True
    )
    managed = LocalManagedAgent(config=config, api_key=api_key)
    agent = Agent(name="test", backend=managed)
    
    # First turn: tell agent something to remember
    result1 = await agent.execute("My favorite color is blue. Please remember this.")
    print(f"\nFirst turn: {result1}")
    
    first_session = managed._session_id
    
    # Second turn: ask agent to recall
    result2 = await agent.execute("What is my favorite color?")
    print(f"Second turn: {result2}")
    
    # Verify session preservation
    assert managed._session_id == first_session
    assert "blue" in result2.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_managed_agents_trace_events():
    """Test that managed agents emit proper context trace events."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")
    
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    from praisonaiagents import Agent
    
    # Set up trace collection
    sink = ContextListSink()
    
    with trace_context(sink=sink, session_id="test_session"):
        config = LocalManagedConfig(
            model="gpt-4o-mini",
            system="You are a helpful assistant.",
            host_packages_ok=True
        )
        managed = LocalManagedAgent(config=config, api_key=api_key)
        agent = Agent(name="test", backend=managed)
        
        result = await agent.execute("Say hi")
        print(f"\nTrace test result: {result}")
    
    # Verify trace events were emitted
    events = sink.events
    print(f"\nEmitted {len(events)} trace events")
    
    # Should have at least agent_start and agent_end from managed level
    event_types = [event.event_type.value for event in events]
    print(f"Event types: {event_types}")
    
    assert len(events) >= 2
    assert "agent_start" in event_types
    assert "agent_end" in event_types


@pytest.mark.integration
@pytest.mark.asyncio 
async def test_managed_agent_packages_safety():
    """Test that package installation safety works in real scenarios."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    from praisonai.integrations.managed_agents import ManagedSandboxRequired
    
    # Test that packages without compute raises exception
    config = LocalManagedConfig(
        packages={"pip": ["requests"]},
        host_packages_ok=False,  # Safety enabled
        model="gpt-4o-mini"
    )
    managed = LocalManagedAgent(config=config)
    
    with pytest.raises(ManagedSandboxRequired, match="packages= requires compute="):
        await managed._install_packages()
    
    print("✓ Package safety check works correctly")