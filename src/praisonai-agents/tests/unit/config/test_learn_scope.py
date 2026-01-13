"""
Tests for LearnScope enum - verifying PRIVATE/SHARED values only.

These tests verify that:
1. LearnScope only has PRIVATE and SHARED values
2. TEAM and ORG values do NOT exist
3. LearnConfig defaults to PRIVATE scope
4. BaseStore defaults to "private" scope
"""

import pytest


class TestLearnScopeValues:
    """Test LearnScope enum has exactly the right values."""
    
    def test_learn_scope_has_private(self):
        """LearnScope should have PRIVATE value."""
        from praisonaiagents.config.feature_configs import LearnScope
        
        assert hasattr(LearnScope, 'PRIVATE')
        assert LearnScope.PRIVATE.value == "private"
    
    def test_learn_scope_has_shared(self):
        """LearnScope should have SHARED value."""
        from praisonaiagents.config.feature_configs import LearnScope
        
        assert hasattr(LearnScope, 'SHARED')
        assert LearnScope.SHARED.value == "shared"
    
    def test_learn_scope_does_not_have_team(self):
        """LearnScope should NOT have TEAM value."""
        from praisonaiagents.config.feature_configs import LearnScope
        
        assert not hasattr(LearnScope, 'TEAM'), "TEAM should be removed from LearnScope"
    
    def test_learn_scope_does_not_have_org(self):
        """LearnScope should NOT have ORG value."""
        from praisonaiagents.config.feature_configs import LearnScope
        
        assert not hasattr(LearnScope, 'ORG'), "ORG should be removed from LearnScope"
    
    def test_learn_scope_does_not_have_user(self):
        """LearnScope should NOT have USER value (replaced by PRIVATE)."""
        from praisonaiagents.config.feature_configs import LearnScope
        
        assert not hasattr(LearnScope, 'USER'), "USER should be replaced by PRIVATE"
    
    def test_learn_scope_does_not_have_global(self):
        """LearnScope should NOT have GLOBAL value (replaced by SHARED)."""
        from praisonaiagents.config.feature_configs import LearnScope
        
        assert not hasattr(LearnScope, 'GLOBAL'), "GLOBAL should be replaced by SHARED"
    
    def test_learn_scope_has_exactly_two_values(self):
        """LearnScope should have exactly 2 values: PRIVATE and SHARED."""
        from praisonaiagents.config.feature_configs import LearnScope
        
        all_values = list(LearnScope)
        assert len(all_values) == 2, f"Expected 2 values, got {len(all_values)}: {all_values}"


class TestLearnConfigDefaults:
    """Test LearnConfig uses correct default scope."""
    
    def test_learn_config_default_scope_is_private(self):
        """LearnConfig should default to PRIVATE scope."""
        from praisonaiagents.config.feature_configs import LearnConfig, LearnScope
        
        config = LearnConfig()
        assert config.scope == LearnScope.PRIVATE
    
    def test_learn_config_scope_can_be_set_to_shared(self):
        """LearnConfig scope can be set to SHARED."""
        from praisonaiagents.config.feature_configs import LearnConfig, LearnScope
        
        config = LearnConfig(scope=LearnScope.SHARED)
        assert config.scope == LearnScope.SHARED
    
    def test_learn_config_to_dict_includes_scope(self):
        """LearnConfig.to_dict() should include scope with correct value."""
        from praisonaiagents.config.feature_configs import LearnConfig, LearnScope
        
        config = LearnConfig()
        d = config.to_dict()
        assert d['scope'] == 'private'
        
        config2 = LearnConfig(scope=LearnScope.SHARED)
        d2 = config2.to_dict()
        assert d2['scope'] == 'shared'


class TestBaseStoreDefaults:
    """Test BaseStore uses correct default scope."""
    
    def test_base_store_default_scope_is_private(self):
        """BaseStore should default to 'private' scope."""
        import inspect
        from praisonaiagents.memory.learn.stores import BaseStore
        
        sig = inspect.signature(BaseStore.__init__)
        scope_param = sig.parameters.get('scope')
        assert scope_param is not None
        assert scope_param.default == 'private', f"Expected 'private', got '{scope_param.default}'"
