#!/usr/bin/env python3
"""Test script to verify retry logic works correctly."""

import sys
import os
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

from praisonaiagents import Agent
from praisonaiagents.agent.retry_utils import RetryBackoffConfig

def test_retry_config_initialization():
    """Test that retry config can be initialized in different ways."""
    
    # Test with boolean True
    agent1 = Agent(name="TestAgent1", retry=True)
    assert agent1._retry_config is not None
    assert isinstance(agent1._retry_config, RetryBackoffConfig)
    print("✓ Retry with True works")
    
    # Test with dict
    agent2 = Agent(name="TestAgent2", retry={"max_retries": 5, "base_delay": 2.0})
    assert agent2._retry_config is not None
    assert agent2._retry_config.max_retries == 5
    assert agent2._retry_config.base_delay == 2.0
    print("✓ Retry with dict works")
    
    # Test with RetryBackoffConfig object
    config = RetryBackoffConfig(max_retries=3, base_delay=1.0)
    agent3 = Agent(name="TestAgent3", retry=config)
    assert agent3._retry_config is not None
    assert agent3._retry_config.max_retries == 3
    print("✓ Retry with RetryBackoffConfig object works")
    
    # Test with False/None
    agent4 = Agent(name="TestAgent4", retry=False)
    assert agent4._retry_config is None
    print("✓ Retry disabled with False works")
    
    print("\n✅ All retry configuration tests passed!")

def test_retry_wrapper_exists():
    """Test that retry wrapper methods exist."""
    agent = Agent(name="TestAgent", retry=True)
    
    # Check that retry methods exist
    assert hasattr(agent, '_chat_completion_with_retry')
    assert hasattr(agent, '_achat_completion_with_retry')
    print("✓ Retry wrapper methods exist")
    
    # Check that they're callable
    assert callable(agent._chat_completion_with_retry)
    assert callable(agent._achat_completion_with_retry)
    print("✓ Retry wrapper methods are callable")
    
    print("\n✅ Retry wrapper method tests passed!")

if __name__ == "__main__":
    test_retry_config_initialization()
    test_retry_wrapper_exists()
    print("\n🎉 All tests passed successfully!")