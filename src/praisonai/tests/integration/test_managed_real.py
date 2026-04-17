"""
Real Agentic Integration Tests for Managed Agents.

These tests make actual LLM calls to verify end-to-end functionality.
They are gated by environment variables and pytest markers.

Gate environment variables:
- RUN_REAL_AGENTIC=1 - enables these tests
- ANTHROPIC_API_KEY - required for Anthropic managed agent tests  
- OPENAI_API_KEY - required for local managed agent tests

Usage:
    # Run all real agentic tests (requires API keys)
    RUN_REAL_AGENTIC=1 pytest src/praisonai/tests/integration/test_managed_real.py -v

    # Run only Anthropic tests
    RUN_REAL_AGENTIC=1 PRAISONAI_TEST_PROVIDERS=anthropic pytest src/praisonai/tests/integration/test_managed_real.py::test_anthropic_managed_real -v

    # Run only local/OpenAI tests  
    RUN_REAL_AGENTIC=1 PRAISONAI_TEST_PROVIDERS=openai pytest src/praisonai/tests/integration/test_managed_real.py::test_local_managed_real_openai -v
"""

import os
import pytest


@pytest.mark.integration
@pytest.mark.network
@pytest.mark.provider_anthropic 
def test_anthropic_managed_real():
    """Test Anthropic managed agents with real LLM calls.
    
    Requirements per issue #1428:
    - Uses claude-haiku-4-5
    - Asserts non-empty result
    - Asserts total_input_tokens > 0
    - Asserts non-empty session_id
    - Prints full LLM output for human verification
    """
    # Gate check - skip unless explicitly enabled
    if not os.environ.get("RUN_REAL_AGENTIC"):
        pytest.skip("RUN_REAL_AGENTIC=1 not set - skipping real agentic test")
        
    # Import requirements with skipif for missing deps
    try:
        import anthropic
    except ImportError:
        pytest.skip("anthropic SDK not available - install with: pip install anthropic>=0.94.0")
    
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("CLAUDE_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY or CLAUDE_API_KEY not set")
    
    from praisonai.integrations.managed_agents import ManagedAgent, ManagedConfig
    from praisonaiagents import Agent
    
    # Create managed backend with claude-haiku-4-5
    config = ManagedConfig(
        model="claude-haiku-4-5",
        system="You are a helpful assistant that provides concise answers.",
        tools=[{"type": "agent_toolset_20260401"}]
    )
    
    managed = ManagedAgent(provider="anthropic", config=config)
    
    # Create agent with managed backend
    agent = Agent(
        name="test-anthropic-managed", 
        backend=managed
    )
    
    # Execute real prompt
    prompt = "Say hello and explain in one sentence what you are."
    print(f"\n🔸 Executing prompt: {prompt}")
    
    result = agent.start(prompt)
    
    # Print full LLM output for human verification
    print(f"\n✅ Full LLM Output:")
    print("-" * 60)
    print(result)
    print("-" * 60)
    
    # Assertions per requirements
    assert result, "Result should be non-empty"
    assert isinstance(result, str), "Result should be a string"
    assert len(result.strip()) > 0, "Result should contain non-whitespace content"
    
    # Check usage tracking
    assert managed.total_input_tokens > 0, f"Should have input tokens, got: {managed.total_input_tokens}"
    
    # Check session was created  
    assert managed.session_id, f"Should have session_id, got: {managed.session_id}"
    assert managed.session_id.startswith("sesn_"), f"Session ID should have Anthropic format, got: {managed.session_id}"
    
    print(f"\n📊 Usage: input_tokens={managed.total_input_tokens}, output_tokens={managed.total_output_tokens}")
    print(f"🆔 Session ID: {managed.session_id}")


@pytest.mark.integration
@pytest.mark.network
@pytest.mark.provider_openai
def test_local_managed_real_openai():
    """Test local managed agents using OpenAI with real LLM calls.
    
    Requirements per issue #1428:
    - Uses gpt-4o-mini
    - Same assertions as Anthropic test
    - Prints full LLM output for human verification
    """
    # Gate check - skip unless explicitly enabled
    if not os.environ.get("RUN_REAL_AGENTIC"):
        pytest.skip("RUN_REAL_AGENTIC=1 not set - skipping real agentic test")
        
    # Check for OpenAI API key
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
    # Import requirements
    try:
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    except ImportError:
        pytest.skip("LocalManagedAgent not available")
    
    from praisonaiagents import Agent
    
    # Create local managed backend with gpt-4o-mini
    config = LocalManagedConfig(
        model="gpt-4o-mini",
        system="You are a helpful assistant that provides concise answers.",
        tools=["execute_command", "read_file", "write_file"]  # Local tool format
    )
    
    managed = LocalManagedAgent(provider="openai", config=config)
    
    # Create agent with managed backend
    agent = Agent(
        name="test-local-openai-managed",
        backend=managed
    )
    
    # Execute real prompt  
    prompt = "Say hello and explain in one sentence what you are."
    print(f"\n🔸 Executing prompt: {prompt}")
    
    result = agent.start(prompt)
    
    # Print full LLM output for human verification
    print(f"\n✅ Full LLM Output:")
    print("-" * 60) 
    print(result)
    print("-" * 60)
    
    # Assertions per requirements
    assert result, "Result should be non-empty"
    assert isinstance(result, str), "Result should be a string"
    assert len(result.strip()) > 0, "Result should contain non-whitespace content"
    
    # Check usage tracking (local managed may or may not track)
    if hasattr(managed, 'total_input_tokens'):
        print(f"📊 Usage: input_tokens={managed.total_input_tokens}, output_tokens={managed.total_output_tokens}")
    
    # Check session was created
    assert managed.session_id, f"Should have session_id, got: {managed.session_id}"
    
    print(f"🆔 Session ID: {managed.session_id}")


@pytest.mark.integration 
@pytest.mark.network
@pytest.mark.provider_anthropic
def test_multi_turn_preserves_session():
    """Test that multiple turns preserve the same session ID.
    
    Requirements per issue #1428:
    - Two calls keep same session id
    """
    # Gate check - skip unless explicitly enabled
    if not os.environ.get("RUN_REAL_AGENTIC"):
        pytest.skip("RUN_REAL_AGENTIC=1 not set - skipping real agentic test")
        
    # Import requirements with skipif for missing deps
    try:
        import anthropic
    except ImportError:
        pytest.skip("anthropic SDK not available")
    
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("CLAUDE_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY or CLAUDE_API_KEY not set")
    
    from praisonai.integrations.managed_agents import ManagedAgent, ManagedConfig
    from praisonaiagents import Agent
    
    # Create managed backend
    config = ManagedConfig(
        model="claude-haiku-4-5",
        system="You are a helpful assistant. Remember previous interactions.",
    )
    
    managed = ManagedAgent(provider="anthropic", config=config)
    
    # Create agent with managed backend
    agent = Agent(
        name="test-session-persistence",
        backend=managed
    )
    
    # First turn
    print(f"\n🔸 First turn...")
    result1 = agent.start("Hi, I'm Alice. Please remember my name.")
    session_id_1 = managed.session_id
    
    print(f"Turn 1 result: {result1}")
    print(f"Session ID after turn 1: {session_id_1}")
    
    # Second turn - should preserve session
    print(f"\n🔸 Second turn...")
    result2 = agent.start("What's my name?")
    session_id_2 = managed.session_id
    
    print(f"Turn 2 result: {result2}")
    print(f"Session ID after turn 2: {session_id_2}")
    
    # Assertions
    assert result1, "First result should be non-empty"
    assert result2, "Second result should be non-empty" 
    
    assert session_id_1 == session_id_2, f"Session IDs should match: {session_id_1} != {session_id_2}"
    
    # The second response should ideally remember the name "Alice"
    # This is a best-effort check since it depends on the LLM's behavior
    print(f"\n📋 Multi-turn test completed. Session preserved: {session_id_1}")


@pytest.mark.integration
@pytest.mark.network 
@pytest.mark.provider_anthropic
def test_anthropic_tool_execution():
    """Test Anthropic managed agents with actual tool execution.
    
    Verifies that tools work end-to-end in managed environment.
    """
    # Gate check - skip unless explicitly enabled  
    if not os.environ.get("RUN_REAL_AGENTIC"):
        pytest.skip("RUN_REAL_AGENTIC=1 not set - skipping real agentic test")
        
    # Import requirements with skipif for missing deps
    try:
        import anthropic
    except ImportError:
        pytest.skip("anthropic SDK not available")
    
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("CLAUDE_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY or CLAUDE_API_KEY not set")
    
    from praisonai.integrations.managed_agents import ManagedAgent, ManagedConfig
    from praisonaiagents import Agent
    
    # Create managed backend with tools enabled
    config = ManagedConfig(
        model="claude-haiku-4-5",
        system="You are a helpful assistant with access to tools. Use tools when appropriate.",
        tools=[{"type": "agent_toolset_20260401"}]  # Includes bash, file ops, etc
    )
    
    managed = ManagedAgent(provider="anthropic", config=config)
    
    # Create agent with managed backend
    agent = Agent(
        name="test-tool-execution",
        backend=managed
    )
    
    # Execute prompt that should trigger tool use
    prompt = "Please create a simple Python file called hello.py that prints 'Hello from managed agent!' and then run it."
    print(f"\n🔸 Executing tool prompt: {prompt}")
    
    result = agent.start(prompt)
    
    # Print full output for human verification
    print(f"\n✅ Tool Execution Output:")
    print("-" * 60)
    print(result)
    print("-" * 60)
    
    # Assertions
    assert result, "Result should be non-empty"
    assert managed.session_id, "Should have session_id"
    assert managed.total_input_tokens > 0, "Should have tracked input tokens"
    
    # Best-effort check that tools were likely used  
    # (The exact output depends on the LLM's behavior)
    result_lower = result.lower()
    tool_indicators = ["file", "create", "run", "python", "hello", "executed", "output"]
    
    found_indicators = [indicator for indicator in tool_indicators if indicator in result_lower]
    print(f"\n🔧 Found tool usage indicators: {found_indicators}")
    
    # We expect at least some tool usage indicators
    assert len(found_indicators) >= 2, f"Expected some tool usage indicators, found: {found_indicators}"
    
    print(f"\n📊 Usage: input_tokens={managed.total_input_tokens}, output_tokens={managed.total_output_tokens}")
    print(f"🆔 Session ID: {managed.session_id}")


@pytest.mark.integration
@pytest.mark.network
@pytest.mark.provider_openai  
def test_local_managed_streaming():
    """Test streaming functionality with local managed agents.
    
    Verifies that streaming works correctly.
    """
    # Gate check - skip unless explicitly enabled
    if not os.environ.get("RUN_REAL_AGENTIC"):
        pytest.skip("RUN_REAL_AGENTIC=1 not set - skipping real agentic test")
        
    # Check for OpenAI API key
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    
    # Import requirements
    try:
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    except ImportError:
        pytest.skip("LocalManagedAgent not available")
    
    import asyncio
    
    # Create local managed backend
    config = LocalManagedConfig(
        model="gpt-4o-mini",
        system="You are a helpful assistant. Provide detailed responses.",
    )
    
    managed = LocalManagedAgent(provider="openai", config=config)
    
    async def test_streaming():
        # Test streaming execution
        prompt = "Count from 1 to 5, explaining each number."
        print(f"\n🔸 Testing streaming with prompt: {prompt}")
        
        chunks = []
        async for chunk in managed.stream(prompt):
            chunks.append(chunk)
            print(chunk, end="", flush=True)  # Print chunks as they arrive
        
        full_response = "".join(chunks)
        print(f"\n\n✅ Complete streamed response:")
        print("-" * 60)
        print(full_response)
        print("-" * 60)
        
        # Assertions
        assert len(chunks) > 0, "Should have received streaming chunks"
        assert full_response.strip(), "Full response should be non-empty"
        assert managed.session_id, "Should have session_id"
        
        print(f"\n📊 Received {len(chunks)} chunks")
        print(f"🆔 Session ID: {managed.session_id}")
        
        return full_response
    
    # Run the async test
    result = asyncio.run(test_streaming())
    assert result, "Async streaming test should return result"