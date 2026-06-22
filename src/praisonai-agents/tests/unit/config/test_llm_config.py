"""Tests for LLMConfig implementation with fallback models."""

from praisonaiagents import Agent
from praisonaiagents.config import LLMConfig


def test_llm_config_basic():
    """Test basic LLMConfig usage via llm parameter."""
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=["claude-3-5-sonnet", "gpt-4o-mini"],
        base_url="https://api.example.com",
        api_key="test-key",
    )

    agent = Agent(
        name="TestAgent",
        llm=config,
    )

    assert agent.llm == "gpt-4o"
    assert agent.fallback_models == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert agent.base_url == "https://api.example.com"
    assert agent.api_key == "test-key"


def test_llm_config_via_model_param():
    """Test using LLMConfig via model parameter."""
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=["claude-3-5-sonnet", "gpt-4o-mini"],
        base_url="https://api.example.com",
    )

    agent = Agent(
        name="TestAgent",
        model=config,
    )

    assert agent.llm == "gpt-4o"
    assert agent.fallback_models == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert agent.base_url == "https://api.example.com"


def test_no_fallback_without_config():
    """Test that fallback_models can only be set via LLMConfig."""
    agent = Agent(
        name="TestAgent",
        model="gpt-4o",
        base_url="https://api.example.com",
        api_key="test-key",
    )

    assert agent.llm == "gpt-4o"
    assert agent.fallback_models == []
    assert agent.base_url == "https://api.example.com"
    assert agent.api_key == "test-key"


def test_fallback_models_defensive_copy():
    """Test that fallback_models creates defensive copy via LLMConfig."""
    original_list = ["claude-3-5-sonnet", "gpt-4o-mini"]
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=original_list,
    )

    agent = Agent(
        name="TestAgent",
        model=config,
    )

    original_list.append("gemini-pro")

    assert agent.fallback_models == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert "gemini-pro" not in agent.fallback_models


def test_llm_config_serialization():
    """Test LLMConfig serialization."""
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=["claude-3-5-sonnet", "gpt-4o-mini"],
        base_url="https://api.example.com",
        api_key="test-key",
    )

    config_dict = config.to_dict()
    assert config_dict["model"] == "gpt-4o"
    assert config_dict["fallback_models"] == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert config_dict["base_url"] == "https://api.example.com"
    assert config_dict["api_key"] == "test-key"

    restored = LLMConfig.from_dict(config_dict)
    assert restored.model == "gpt-4o"
    assert restored.fallback_models == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert restored.base_url == "https://api.example.com"
    assert restored.api_key == "test-key"
