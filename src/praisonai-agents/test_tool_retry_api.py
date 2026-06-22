"""Test tool retry API consistency improvements."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from praisonaiagents import Agent
from praisonaiagents.config import ToolRetryConfig


def test_tool_retry_config_from_bool():
    """Test that tool_retry_config accepts bool for API consistency."""
    # True should create default config
    agent = Agent(
        name="test",
        tool_retry_config=True
    )
    assert agent.tool_retry_config is not None
    assert isinstance(agent.tool_retry_config, ToolRetryConfig)
    assert agent.tool_retry_config.max_attempts == 3  # Default value
    
    # False should disable
    agent2 = Agent(
        name="test2", 
        tool_retry_config=False
    )
    assert agent2.tool_retry_config is None
    
    print("✅ tool_retry_config from bool test passed!")


def test_tool_retry_config_from_dict():
    """Test that tool_retry_config accepts dict for API consistency."""
    agent = Agent(
        name="test",
        tool_retry_config={"max_attempts": 5, "initial_delay_s": 2.0}
    )
    assert agent.tool_retry_config is not None
    assert agent.tool_retry_config.max_attempts == 5
    assert agent.tool_retry_config.initial_delay_s == 2.0
    
    print("✅ tool_retry_config from dict test passed!")


def test_tool_retry_config_from_instance():
    """Test that tool_retry_config accepts ToolRetryConfig instance."""
    config = ToolRetryConfig(max_attempts=7, factor=3.0)
    agent = Agent(
        name="test",
        tool_retry_config=config
    )
    assert agent.tool_retry_config is config
    assert agent.tool_retry_config.max_attempts == 7
    assert agent.tool_retry_config.factor == 3.0
    
    print("✅ tool_retry_config from instance test passed!")


def test_tool_retry_config_none():
    """Test that tool_retry_config=None disables retry."""
    agent = Agent(
        name="test",
        tool_retry_config=None
    )
    assert agent.tool_retry_config is None
    
    print("✅ tool_retry_config=None test passed!")


if __name__ == "__main__":
    test_tool_retry_config_from_bool()
    test_tool_retry_config_from_dict()
    test_tool_retry_config_from_instance()
    test_tool_retry_config_none()
    print("\n🎉 All API consistency tests passed!")