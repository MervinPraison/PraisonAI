#!/usr/bin/env python3
"""Test LLMConfig implementation with fallback models."""

import sys
sys.path.insert(0, 'src/praisonai-agents')

from praisonaiagents import Agent
from praisonaiagents.config import LLMConfig

def test_llm_config_basic():
    """Test basic LLMConfig usage via llm parameter."""
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=["claude-3-5-sonnet", "gpt-4o-mini"],
        base_url="https://api.example.com",
        api_key="test-key"
    )
    
    agent = Agent(
        name="TestAgent",
        llm=config  # Pass LLMConfig via llm parameter
    )
    
    # Verify values were applied
    assert agent.llm == "gpt-4o"
    assert agent.fallback_models == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert agent.base_url == "https://api.example.com"
    assert agent.api_key == "test-key"
    
    print("✓ LLMConfig basic test passed")

def test_llm_config_via_model_param():
    """Test using LLMConfig via model parameter."""
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=["claude-3-5-sonnet", "gpt-4o-mini"],
        base_url="https://api.example.com"
    )
    
    agent = Agent(
        name="TestAgent",
        model=config  # Pass LLMConfig via model parameter
    )
    
    # Verify values from LLMConfig via model param
    assert agent.llm == "gpt-4o"
    assert agent.fallback_models == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert agent.base_url == "https://api.example.com"
    
    print("✓ LLMConfig via model param test passed")

def test_no_fallback_without_config():
    """Test that fallback_models can only be set via LLMConfig."""
    agent = Agent(
        name="TestAgent",
        model="gpt-4o",
        base_url="https://api.example.com",
        api_key="test-key"
    )
    
    # Verify fallback_models is empty without LLMConfig
    assert agent.llm == "gpt-4o"
    assert agent.fallback_models == []  # No fallback without LLMConfig
    assert agent.base_url == "https://api.example.com"
    assert agent.api_key == "test-key"
    
    print("✓ No fallback without config test passed")

def test_fallback_models_defensive_copy():
    """Test that fallback_models creates defensive copy via LLMConfig."""
    original_list = ["claude-3-5-sonnet", "gpt-4o-mini"]
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=original_list
    )
    
    agent = Agent(
        name="TestAgent",
        model=config  # Use model parameter with LLMConfig
    )
    
    # Modify original list
    original_list.append("gemini-pro")
    
    # Agent's list should not be affected
    assert agent.fallback_models == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert "gemini-pro" not in agent.fallback_models
    
    print("✓ Defensive copy test passed")

def test_llm_config_serialization():
    """Test LLMConfig serialization."""
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=["claude-3-5-sonnet", "gpt-4o-mini"],
        base_url="https://api.example.com",
        api_key="test-key"
    )
    
    # Test to_dict
    config_dict = config.to_dict()
    assert config_dict["model"] == "gpt-4o"
    assert config_dict["fallback_models"] == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert config_dict["base_url"] == "https://api.example.com"
    assert config_dict["api_key"] == "test-key"
    
    # Test from_dict
    restored = LLMConfig.from_dict(config_dict)
    assert restored.model == "gpt-4o"
    assert restored.fallback_models == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert restored.base_url == "https://api.example.com"
    assert restored.api_key == "test-key"
    
    print("✓ LLMConfig serialization test passed")

if __name__ == "__main__":
    test_llm_config_basic()
    test_llm_config_via_model_param()
    test_no_fallback_without_config()
    test_fallback_models_defensive_copy()
    test_llm_config_serialization()
    print("\n✅ All tests passed!")