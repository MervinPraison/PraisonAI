"""
Test script to reproduce and verify fix for multi-agent streaming issue #1882
"""
import os

import pytest

# Set minimal OpenAI API key for testing (should fail gracefully)
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-reproduction")


def test_config_defaults():
    """Test that the config default is now False"""
    from praisonaiagents.config.feature_configs import MultiAgentOutputConfig

    config = MultiAgentOutputConfig()
    assert config.stream is False


@pytest.mark.live
def test_single_agent():
    """Test single agent (should work with fallback)"""
    from praisonaiagents import Agent

    agent = Agent(instructions="Reply with exactly the requested text")
    result = agent.start("Reply with exactly: OK")
    assert result is not None


@pytest.mark.live
def test_multi_agent():
    """Test multi-agent (should work after fix)"""
    from praisonaiagents import Agent, Agents

    research_agent = Agent(instructions="Research about AI")
    summarise_agent = Agent(instructions="Summarise research agent's findings")
    agents = Agents(agents=[research_agent, summarise_agent])

    try:
        result = agents.start("What is Python?")
        assert result is not None
    except Exception as exc:
        if "Streaming is not supported in sync OpenAIAdapter" in str(exc):
            pytest.fail("Streaming error still exists — fix did not work")
        raise
