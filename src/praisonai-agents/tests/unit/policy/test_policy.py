"""
Unit tests for the Policy module.

Tests cover:
- PolicyResult creation
- PolicyRule matching and evaluation
- Policy evaluation
- PolicyEngine management and checks
"""

import pytest

from praisonaiagents.policy.types import PolicyAction, PolicyResult
from praisonaiagents.policy.policy import Policy, PolicyRule
from praisonaiagents.policy.config import PolicyConfig
from praisonaiagents.policy.engine import (
    PolicyEngine, create_deny_tools_policy,
    create_allow_tools_policy, create_read_only_policy
)


# =============================================================================
# PolicyResult Tests
# =============================================================================

class TestPolicyResult:
    """Tests for PolicyResult class."""
    
    def test_result_creation(self):
        """Test creating a result."""
        result = PolicyResult(
            allowed=True,
            action=PolicyAction.ALLOW,
            reason="Test"
        )
        assert result.allowed
        assert result.action == PolicyAction.ALLOW
    
    def test_result_allow(self):
        """Test allow factory method."""
        result = PolicyResult.allow("Allowed")
        assert result.allowed
        assert result.action == PolicyAction.ALLOW
        assert result.reason == "Allowed"
    
    def test_result_deny(self):
        """Test deny factory method."""
        result = PolicyResult.deny("Not allowed", "test_policy")
        assert not result.allowed
        assert result.action == PolicyAction.DENY
        assert result.reason == "Not allowed"
        assert result.policy_name == "test_policy"
    
    def test_result_ask(self):
        """Test ask factory method."""
        result = PolicyResult.ask("Confirm action")
        assert not result.allowed
        assert result.action == PolicyAction.ASK
    
    def test_result_to_dict(self):
        """Test result serialization."""
        result = PolicyResult(
            allowed=False,
            action=PolicyAction.DENY,
            policy_name="test",
            reason="Test reason"
        )
        data = result.to_dict()
        
        assert data["allowed"] is False
        assert data["action"] == "deny"
        assert data["policy_name"] == "test"


# =============================================================================
# PolicyRule Tests
# =============================================================================

class TestPolicyRule:
    """Tests for PolicyRule class."""
    
    def test_rule_creation(self):
        """Test creating a rule."""
        rule = PolicyRule(
            action=PolicyAction.DENY,
            resource="tool:delete_*",
            reason="No delete"
        )
        assert rule.action == PolicyAction.DENY
        assert rule.resource == "tool:delete_*"
    
    def test_rule_exact_match(self):
        """Test exact resource matching."""
        rule = PolicyRule(
            action=PolicyAction.DENY,
            resource="tool:delete_file"
        )
        
        assert rule.matches("tool:delete_file", {})
        assert not rule.matches("tool:read_file", {})
    
    def test_rule_wildcard_match(self):
        """Test wildcard resource matching."""
        rule = PolicyRule(
            action=PolicyAction.DENY,
            resource="tool:delete_*"
        )
        
        assert rule.matches("tool:delete_file", {})
        assert rule.matches("tool:delete_directory", {})
        assert not rule.matches("tool:read_file", {})
    
    def test_rule_condition(self):
        """Test rule with condition."""
        rule = PolicyRule(
            action=PolicyAction.DENY,
            resource="tool:*",
            condition=lambda ctx: ctx.get("dangerous", False)
        )
        
        assert rule.matches("tool:test", {"dangerous": True})
        assert not rule.matches("tool:test", {"dangerous": False})
        assert not rule.matches("tool:test", {})
    
    def test_rule_evaluate_match(self):
        """Test rule evaluation when matching."""
        rule = PolicyRule(
            action=PolicyAction.DENY,
            resource="tool:delete_*",
            reason="No delete",
            name="deny_delete"
        )
        
        result = rule.evaluate("tool:delete_file", {})
        
        assert result is not None
        assert not result.allowed
        assert result.action == PolicyAction.DENY
        assert result.reason == "No delete"
    
    def test_rule_evaluate_no_match(self):
        """Test rule evaluation when not matching."""
        rule = PolicyRule(
            action=PolicyAction.DENY,
            resource="tool:delete_*"
        )
        
        result = rule.evaluate("tool:read_file", {})
        
        assert result is None
    
    def test_rule_to_dict(self):
        """Test rule serialization."""
        rule = PolicyRule(
            action=PolicyAction.DENY,
            resource="tool:test",
            reason="Test",
            name="test_rule",
            priority=10
        )
        data = rule.to_dict()
        
        assert data["action"] == "deny"
        assert data["resource"] == "tool:test"
        assert data["priority"] == 10


# =============================================================================
# Policy Tests
# =============================================================================

class TestPolicy:
    """Tests for Policy class."""
    
    def test_policy_creation(self):
        """Test creating a policy."""
        policy = Policy(
            name="test_policy",
            description="Test policy"
        )
        assert policy.name == "test_policy"
        assert policy.enabled
    
    def test_policy_add_rule(self):
        """Test adding rules to a policy."""
        policy = Policy(name="test")
        
        policy.add_rule(PolicyRule(
            action=PolicyAction.DENY,
            resource="tool:delete_*"
        ))
        
        assert len(policy.rules) == 1
    
    def test_policy_remove_rule(self):
        """Test removing rules from a policy."""
        policy = Policy(name="test")
        policy.add_rule(PolicyRule(
            action=PolicyAction.DENY,
            resource="tool:delete_*",
            name="deny_delete"
        ))
        
        result = policy.remove_rule("deny_delete")
        
        assert result
        assert len(policy.rules) == 0
    
    def test_policy_evaluate_match(self):
        """Test policy evaluation when rule matches."""
        policy = Policy(
            name="test",
            rules=[
                PolicyRule(
                    action=PolicyAction.DENY,
                    resource="tool:delete_*",
                    reason="No delete"
                )
            ]
        )
        
        result = policy.evaluate("tool:delete_file", {})
        
        assert result is not None
        assert not result.allowed
        assert result.policy_name == "test"
    
    def test_policy_evaluate_no_match(self):
        """Test policy evaluation when no rule matches."""
        policy = Policy(
            name="test",
            rules=[
                PolicyRule(
                    action=PolicyAction.DENY,
                    resource="tool:delete_*"
                )
            ]
        )
        
        result = policy.evaluate("tool:read_file", {})
        
        assert result is None
    
    def test_policy_disabled(self):
        """Test disabled policy."""
        policy = Policy(
            name="test",
            enabled=False,
            rules=[
                PolicyRule(
                    action=PolicyAction.DENY,
                    resource="tool:*"
                )
            ]
        )
        
        result = policy.evaluate("tool:delete_file", {})
        
        assert result is None
    
    def test_policy_to_dict(self):
        """Test policy serialization."""
        policy = Policy(
            name="test",
            description="Test policy",
            rules=[
                PolicyRule(action=PolicyAction.DENY, resource="tool:*")
            ]
        )
        data = policy.to_dict()
        
        assert data["name"] == "test"
        assert len(data["rules"]) == 1
    
    def test_policy_from_dict(self):
        """Test policy deserialization."""
        data = {
            "name": "test",
            "description": "Test",
            "rules": [
                {"action": "deny", "resource": "tool:delete_*"}
            ]
        }
        
        policy = Policy.from_dict(data)
        
        assert policy.name == "test"
        assert len(policy.rules) == 1
        assert policy.rules[0].action == PolicyAction.DENY


# =============================================================================
# PolicyConfig Tests
# =============================================================================

class TestPolicyConfig:
    """Tests for PolicyConfig class."""
    
    def test_config_defaults(self):
        """Test default configuration."""
        config = PolicyConfig()
        
        assert config.enabled
        assert config.default_action == "allow"
        assert not config.strict_mode
    
    def test_config_custom(self):
        """Test custom configuration."""
        config = PolicyConfig(
            enabled=False,
            strict_mode=True
        )
        
        assert not config.enabled
        assert config.strict_mode


# =============================================================================
# PolicyEngine Tests
# =============================================================================

class TestPolicyEngine:
    """Tests for PolicyEngine class."""
    
    @pytest.fixture
    def engine(self):
        """Create a test engine."""
        return PolicyEngine()
    
    def test_engine_creation(self, engine):
        """Test creating an engine."""
        assert engine.config.enabled
        assert len(engine.policies) == 0
    
    def test_engine_add_policy(self, engine):
        """Test adding a policy."""
        policy = Policy(name="test")
        engine.add_policy(policy)
        
        assert len(engine.policies) == 1
        assert engine.get_policy("test") is not None
    
    def test_engine_remove_policy(self, engine):
        """Test removing a policy."""
        engine.add_policy(Policy(name="test"))
        
        result = engine.remove_policy("test")
        
        assert result
        assert len(engine.policies) == 0
    
    def test_engine_check_allow(self, engine):
        """Test check that allows."""
        engine.add_policy(Policy(
            name="allow_read",
            rules=[
                PolicyRule(
                    action=PolicyAction.ALLOW,
                    resource="tool:read_*"
                )
            ]
        ))
        
        result = engine.check("tool:read_file", {})
        
        assert result.allowed
    
    def test_engine_check_deny(self, engine):
        """Test check that denies."""
        engine.add_policy(Policy(
            name="deny_delete",
            rules=[
                PolicyRule(
                    action=PolicyAction.DENY,
                    resource="tool:delete_*",
                    reason="No delete"
                )
            ]
        ))
        
        result = engine.check("tool:delete_file", {})
        
        assert not result.allowed
        assert result.reason == "No delete"
    
    def test_engine_check_no_match(self, engine):
        """Test check with no matching policy."""
        result = engine.check("tool:anything", {})
        
        assert result.allowed  # Default is allow
    
    def test_engine_strict_mode(self):
        """Test strict mode denies when no match."""
        engine = PolicyEngine(PolicyConfig(strict_mode=True))
        
        result = engine.check("tool:anything", {})
        
        assert not result.allowed
    
    def test_engine_disabled(self):
        """Test disabled engine allows everything."""
        engine = PolicyEngine(PolicyConfig(enabled=False))
        engine.add_policy(Policy(
            name="deny_all",
            rules=[PolicyRule(action=PolicyAction.DENY, resource="*")]
        ))
        
        result = engine.check("tool:anything", {})
        
        assert result.allowed
    
    def test_engine_check_tool(self, engine):
        """Test check_tool helper."""
        engine.add_policy(Policy(
            name="deny_delete",
            rules=[
                PolicyRule(
                    action=PolicyAction.DENY,
                    resource="tool:delete_file"
                )
            ]
        ))
        
        result = engine.check_tool("delete_file")
        
        assert not result.allowed
    
    def test_engine_check_file(self, engine):
        """Test check_file helper."""
        engine.add_policy(Policy(
            name="deny_write",
            rules=[
                PolicyRule(
                    action=PolicyAction.DENY,
                    resource="file:write"
                )
            ]
        ))
        
        result = engine.check_file("write", "/path/to/file")
        
        assert not result.allowed
    
    def test_engine_enable_disable_policy(self, engine):
        """Test enabling/disabling policies."""
        engine.add_policy(Policy(name="test"))
        
        engine.disable_policy("test")
        assert not engine.get_policy("test").enabled
        
        engine.enable_policy("test")
        assert engine.get_policy("test").enabled
    
    def test_engine_clear(self, engine):
        """Test clearing all policies."""
        engine.add_policy(Policy(name="test1"))
        engine.add_policy(Policy(name="test2"))
        
        engine.clear()
        
        assert len(engine.policies) == 0
    
    def test_engine_to_dict(self, engine):
        """Test engine serialization."""
        engine.add_policy(Policy(name="test"))
        
        data = engine.to_dict()
        
        assert "config" in data
        assert "policies" in data
        assert len(data["policies"]) == 1


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience policy creation functions."""
    
    def test_create_deny_tools_policy(self):
        """Test creating deny tools policy."""
        policy = create_deny_tools_policy(
            ["delete_*", "write_*"],
            reason="Not allowed"
        )
        
        assert policy.name == "deny_tools"
        assert len(policy.rules) == 2
    
    def test_create_allow_tools_policy(self):
        """Test creating allow tools policy."""
        policy = create_allow_tools_policy(["read_*", "list_*"])
        
        assert policy.name == "allow_tools"
        assert len(policy.rules) == 2
    
    def test_create_read_only_policy(self):
        """Test creating read-only policy."""
        policy = create_read_only_policy()
        
        assert policy.name == "read_only"
        assert len(policy.rules) >= 2
        assert policy.priority == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
