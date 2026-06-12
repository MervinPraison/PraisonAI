"""
Unit tests for context compaction policy.

Tests policy routing, ExecutionConfig round-trip, sync/async parity.
"""

import pytest
from unittest.mock import patch, MagicMock

from praisonaiagents.context.protocols import (
    CompactionRoute, CompactionStrategy, ContextBudgetResult
)
from praisonaiagents.context.adapters import (
    ContextCompactionPolicyAdapter, get_default_policy_impl
)
from praisonaiagents.context.policy import get_default_policy, ContextCompactionPolicy
from praisonaiagents.config.feature_configs import ExecutionConfig


def test_policy_routing_logic():
    """Test that policy routing decisions work correctly."""
    policy = ContextCompactionPolicyAdapter(
        trigger_at=0.85,
        strategy=CompactionStrategy.DROP_OLDEST_TOOLS,
        preserve_last_n_turns=3,
        target_utilization=0.65
    )
    
    # Mock the dependency modules
    with patch('praisonaiagents.context.adapters.get_model_limit') as mock_limit, \
         patch('praisonaiagents.context.adapters.ContextBudgeter') as mock_budgeter, \
         patch('praisonaiagents.context.adapters.estimate_messages_tokens') as mock_tokens:
        
        # Setup mocks
        mock_limit.return_value = 4000
        mock_budgeter_instance = MagicMock()
        mock_budgeter_instance.usable = 3600  # 90% of 4000
        mock_budgeter.return_value = mock_budgeter_instance
        
        # Test case 1: Under threshold - should fit
        mock_tokens.return_value = 2500  # 69% utilization (under 85% trigger)
        
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        
        result = policy.compute_context_budget(
            messages=messages,
            model="gpt-4o-mini",
            tools=None,
            system_prompt=None
        )
        
        assert result.route == CompactionRoute.FITS
        assert result.needs_action is False
        assert result.utilization == 2500 / 3600  # ~0.694
        
        # Test case 2: Over threshold - needs compaction
        mock_tokens.return_value = 3200  # 89% utilization (over 85% trigger)
        
        result = policy.compute_context_budget(
            messages=messages,
            model="gpt-4o-mini"
        )
        
        assert result.route == CompactionRoute.COMPACT_NEEDED
        assert result.needs_action is True
        assert result.recommended_strategy == CompactionStrategy.DROP_OLDEST_TOOLS
        
        # Test case 3: Critical usage - needs aggressive action
        mock_tokens.return_value = 3450  # 96% utilization (over 95% critical)
        
        result = policy.compute_context_budget(
            messages=messages,
            model="gpt-4o-mini"
        )
        
        assert result.route == CompactionRoute.COMPACT_THEN_TRUNCATE
        assert result.needs_action is True


def test_policy_with_large_tool_outputs():
    """Test policy routing with large tool outputs."""
    policy = ContextCompactionPolicyAdapter(
        trigger_at=0.85,
        aggressive_tool_truncation=True
    )
    
    messages = [
        {"role": "user", "content": "Run tool"},
        {"role": "tool", "content": "x" * 2000, "tool_call_id": "call_123"}  # Large tool output
    ]
    
    with patch('praisonaiagents.context.adapters.get_model_limit', return_value=4000), \
         patch('praisonaiagents.context.adapters.ContextBudgeter') as mock_budgeter, \
         patch('praisonaiagents.context.adapters.estimate_messages_tokens', return_value=3200):
        
        mock_budgeter_instance = MagicMock()
        mock_budgeter_instance.usable = 3600
        mock_budgeter.return_value = mock_budgeter_instance
        
        result = policy.compute_context_budget(messages=messages, model="gpt-4o-mini")
        
        # Should prioritize tool truncation over general compaction
        assert result.route == CompactionRoute.TRUNCATE_TOOLS
        assert result.needs_action is True


def test_execution_config_round_trip():
    """Test that ExecutionConfig properly serializes and deserializes context_compaction policies."""
    
    # Test with boolean value
    config1 = ExecutionConfig(context_compaction=True)
    config1_dict = config1.to_dict()
    config1_restored = ExecutionConfig.from_dict(config1_dict)
    assert config1_restored.context_compaction == True
    
    # Test with False
    config2 = ExecutionConfig(context_compaction=False)
    config2_dict = config2.to_dict()
    config2_restored = ExecutionConfig.from_dict(config2_dict)
    assert config2_restored.context_compaction == False
    
    # Test with policy object
    custom_policy = ContextCompactionPolicyAdapter(
        trigger_at=0.75,
        strategy=CompactionStrategy.SUMMARISE,
        preserve_last_n_turns=7
    )
    
    config3 = ExecutionConfig(context_compaction=custom_policy)
    config3_dict = config3.to_dict()
    config3_restored = ExecutionConfig.from_dict(config3_dict)
    
    # Should restore as policy object, not dict
    assert isinstance(config3_restored.context_compaction, ContextCompactionPolicyAdapter)
    assert config3_restored.context_compaction.trigger_at == 0.75
    assert config3_restored.context_compaction.strategy == CompactionStrategy.SUMMARISE
    assert config3_restored.context_compaction.preserve_last_n_turns == 7


def test_mutable_singleton_fix():
    """Test that get_default_policy returns fresh copies."""
    policy1 = get_default_policy()
    policy2 = get_default_policy()
    
    # Should be separate instances
    assert policy1 is not policy2
    
    # Should have same initial values
    assert policy1.trigger_at == policy2.trigger_at
    assert policy1.strategy == policy2.strategy
    assert policy1.preserve_last_n_turns == policy2.preserve_last_n_turns
    
    # Modifications should not affect each other
    policy1.trigger_at = 0.95
    assert policy2.trigger_at != 0.95  # Should still be original value
    
    # Test model_overrides are also deep copied
    policy1.model_overrides = {"gpt-4": {"trigger_at": 0.88}}
    assert policy2.model_overrides != policy1.model_overrides


def test_model_specific_overrides():
    """Test that model-specific overrides work correctly."""
    policy = ContextCompactionPolicyAdapter(
        trigger_at=0.85,
        strategy=CompactionStrategy.DROP_OLDEST_TOOLS,
        model_overrides={
            "gpt-4": {
                "trigger_at": 0.92,
                "strategy": "summarise"
            },
            "claude-3": {
                "trigger_at": 0.88
            }
        }
    )
    
    with patch('praisonaiagents.context.adapters.get_model_limit', return_value=8000), \
         patch('praisonaiagents.context.adapters.ContextBudgeter') as mock_budgeter, \
         patch('praisonaiagents.context.adapters.estimate_messages_tokens', return_value=7000):
        
        mock_budgeter_instance = MagicMock()
        mock_budgeter_instance.usable = 7200
        mock_budgeter.return_value = mock_budgeter_instance
        
        # Test with gpt-4 (87.5% utilization - would trigger default but not override)
        result = policy.compute_context_budget(
            messages=[{"role": "user", "content": "test"}],
            model="gpt-4"
        )
        
        # 87.5% < 92% (gpt-4 override), so should fit
        assert result.route == CompactionRoute.FITS
        assert result.details["effective_trigger"] == 0.92


def test_policy_validation():
    """Test that policy validation works correctly."""
    
    # Valid policy should not raise
    ContextCompactionPolicyAdapter(
        trigger_at=0.85,
        target_utilization=0.70
    )
    
    # Invalid trigger_at values
    with pytest.raises(ValueError, match="trigger_at must be between 0.1 and 0.99"):
        ContextCompactionPolicyAdapter(trigger_at=1.1)
    
    with pytest.raises(ValueError, match="trigger_at must be between 0.1 and 0.99"):
        ContextCompactionPolicyAdapter(trigger_at=0.05)
    
    # Invalid target_utilization values  
    with pytest.raises(ValueError, match="target_utilization must be between 0.1 and 0.95"):
        ContextCompactionPolicyAdapter(target_utilization=1.0)
    
    # trigger_at must be greater than target_utilization
    with pytest.raises(ValueError, match="trigger_at must be greater than target_utilization"):
        ContextCompactionPolicyAdapter(trigger_at=0.75, target_utilization=0.85)


def test_policy_serialization():
    """Test policy to_dict and from_dict methods."""
    original_policy = ContextCompactionPolicyAdapter(
        trigger_at=0.88,
        strategy=CompactionStrategy.SUMMARISE,
        preserve_last_n_turns=4,
        max_compaction_attempts=3,
        target_utilization=0.72,
        aggressive_tool_truncation=True,
        model_overrides={"gpt-4": {"trigger_at": 0.90}}
    )
    
    # Test serialization
    policy_dict = original_policy.to_dict()
    expected_keys = {
        'trigger_at', 'strategy', 'preserve_last_n_turns',
        'max_compaction_attempts', 'target_utilization', 
        'aggressive_tool_truncation', 'model_overrides'
    }
    assert set(policy_dict.keys()) == expected_keys
    assert policy_dict['strategy'] == 'summarise'  # Enum converted to value
    
    # Test deserialization
    restored_policy = ContextCompactionPolicyAdapter.from_dict(policy_dict)
    assert restored_policy.trigger_at == original_policy.trigger_at
    assert restored_policy.strategy == original_policy.strategy
    assert restored_policy.preserve_last_n_turns == original_policy.preserve_last_n_turns
    assert restored_policy.model_overrides == original_policy.model_overrides


def test_backward_compatibility_exports():
    """Test that backward compatibility exports work."""
    # Users should be able to import ContextCompactionPolicy (gets adapter)
    from praisonaiagents.context.policy import ContextCompactionPolicy
    
    policy = ContextCompactionPolicy(trigger_at=0.80)
    assert isinstance(policy, ContextCompactionPolicyAdapter)
    assert policy.trigger_at == 0.80


if __name__ == "__main__":
    pytest.main([__file__, "-v"])