"""
Integration tests for Agent-Centric API enhancements.

Tests the new guardrail presets, context presets, caching presets with real API calls.
Requires OPENAI_API_KEY environment variable.
"""

import os
import pytest

# Skip entire module if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)


def test_guardrail_string_preset():
    """Test guardrail string preset with real agent."""
    from praisonaiagents import Agent
    
    # Create agent with guardrail preset
    agent = Agent(
        instructions="You are a helpful assistant. Always respond briefly.",
        guardrails="strict",  # Uses strict preset
    )
    
    # Verify agent created successfully
    assert agent is not None
    print("✓ Agent with guardrails='strict' created successfully")


def test_guardrail_array_preset():
    """Test guardrail array preset with overrides."""
    from praisonaiagents import Agent
    
    agent = Agent(
        instructions="You are a helpful assistant.",
        guardrails=["strict", {"max_retries": 10}],
    )
    
    assert agent is not None
    print("✓ Agent with guardrails=['strict', {...}] created successfully")


def test_guardrail_llm_prompt():
    """Test guardrail with LLM validator prompt."""
    from praisonaiagents import Agent
    
    agent = Agent(
        instructions="You are a helpful assistant.",
        guardrails="Ensure the response is helpful and does not contain harmful content.",
    )
    
    assert agent is not None
    print("✓ Agent with guardrails='<LLM prompt>' created successfully")


def test_context_string_preset():
    """Test context string preset."""
    from praisonaiagents import Agent
    
    agent = Agent(
        instructions="You are a helpful assistant.",
        context="sliding_window",
    )
    
    assert agent is not None
    print("✓ Agent with context='sliding_window' created successfully")


def test_context_bool():
    """Test context bool enable."""
    from praisonaiagents import Agent
    
    agent = Agent(
        instructions="You are a helpful assistant.",
        context=True,
    )
    
    assert agent is not None
    print("✓ Agent with context=True created successfully")


def test_caching_string_preset():
    """Test caching string preset."""
    from praisonaiagents import Agent
    
    agent = Agent(
        instructions="You are a helpful assistant.",
        caching="prompt",
    )
    
    assert agent is not None
    print("✓ Agent with caching='prompt' created successfully")


def test_output_string_preset():
    """Test output string preset."""
    from praisonaiagents import Agent
    
    agent = Agent(
        instructions="You are a helpful assistant.",
        output="verbose",
    )
    
    assert agent is not None
    print("✓ Agent with output='verbose' created successfully")


def test_execution_string_preset():
    """Test execution string preset."""
    from praisonaiagents import Agent
    
    agent = Agent(
        instructions="You are a helpful assistant.",
        execution="fast",
    )
    
    assert agent is not None
    print("✓ Agent with execution='fast' created successfully")


def test_combined_presets():
    """Test multiple presets combined."""
    from praisonaiagents import Agent
    
    agent = Agent(
        instructions="You are a helpful assistant.",
        output="verbose",
        execution="fast",
        caching="enabled",
        guardrails="permissive",
    )
    
    assert agent is not None
    print("✓ Agent with multiple presets created successfully")


def test_agent_chat_with_presets():
    """Test agent chat with presets."""
    from praisonaiagents import Agent
    
    agent = Agent(
        instructions="You are a helpful assistant. Always respond with exactly one word.",
        output="minimal",
        execution="fast",
    )
    
    response = agent.chat("Say hello")
    assert response is not None
    print(f"✓ Agent chat response: {response[:50]}...")


def test_policy_string_parsing():
    """Test policy string parsing utilities."""
    from praisonaiagents import is_policy_string, parse_policy_string
    
    # Test is_policy_string
    assert is_policy_string("policy:strict") is True
    assert is_policy_string("pii:redact") is True
    assert is_policy_string("strict") is False
    assert is_policy_string("some long prompt") is False
    
    # Test parse_policy_string
    policy_type, action = parse_policy_string("policy:strict")
    assert policy_type == "policy"
    assert action == "strict"
    
    policy_type, action = parse_policy_string("pii:redact")
    assert policy_type == "pii"
    assert action == "redact"
    
    print("✓ Policy string parsing works correctly")


def test_guardrail_presets_import():
    """Test GUARDRAIL_PRESETS can be imported."""
    from praisonaiagents import GUARDRAIL_PRESETS
    
    assert "strict" in GUARDRAIL_PRESETS
    assert "permissive" in GUARDRAIL_PRESETS
    assert "safety" in GUARDRAIL_PRESETS
    
    print("✓ GUARDRAIL_PRESETS imported successfully")


def test_knowledge_presets_import():
    """Test KNOWLEDGE_PRESETS can be imported."""
    from praisonaiagents import KNOWLEDGE_PRESETS
    
    assert "auto" in KNOWLEDGE_PRESETS
    
    print("✓ KNOWLEDGE_PRESETS imported successfully")


if __name__ == "__main__":
    print("=" * 60)
    print("Agent-Centric API Integration Tests")
    print("=" * 60)
    
    tests = [
        test_guardrail_string_preset,
        test_guardrail_array_preset,
        test_guardrail_llm_prompt,
        test_context_string_preset,
        test_context_bool,
        test_caching_string_preset,
        test_output_string_preset,
        test_execution_string_preset,
        test_combined_presets,
        test_policy_string_parsing,
        test_guardrail_presets_import,
        test_knowledge_presets_import,
        test_agent_chat_with_presets,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
