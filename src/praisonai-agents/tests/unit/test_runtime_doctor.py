"""
Unit tests for runtime doctor migration.

Tests the DoctorContractProtocol and built-in cli_backend migration rule.
"""

import unittest
from typing import Any, Dict

from praisonaiagents.runtime.doctor_protocol import DoctorContractProtocol, Finding
from praisonaiagents.runtime.builtin_rules import CliBackendMigrationRule
from praisonaiagents.runtime.doctor_registry import DoctorRulesRegistry


class TestDoctorContractProtocol(unittest.TestCase):
    """Test the DoctorContractProtocol interface."""
    
    def test_protocol_compliance(self):
        """Test that CliBackendMigrationRule implements the protocol correctly."""
        rule = CliBackendMigrationRule()
        
        # Test required attributes/methods exist
        self.assertTrue(hasattr(rule, 'rule_id'))
        self.assertTrue(hasattr(rule, 'collect_findings'))
        self.assertTrue(hasattr(rule, 'apply_fix'))
        
        # Test rule_id is a string
        self.assertIsInstance(rule.rule_id, str)
        self.assertEqual(rule.rule_id, "cli_backend_migration")


class TestCliBackendMigrationRule(unittest.TestCase):
    """Test the built-in cli_backend migration rule."""
    
    def setUp(self):
        self.rule = CliBackendMigrationRule()
    
    def test_no_cli_backend_config(self):
        """Test config without cli_backend has no findings."""
        config = {
            "framework": "praisonai",
            "topic": "testing",
            "roles": {
                "tester": {
                    "role": "Test agent",
                    "goal": "Run tests",
                    "backstory": "An agent that runs tests"
                }
            }
        }
        
        findings = self.rule.collect_findings(config)
        self.assertEqual(len(findings), 0)
    
    def test_top_level_cli_backend(self):
        """Test detection of top-level cli_backend."""
        config = {
            "framework": "praisonai", 
            "cli_backend": "claude-code",
            "topic": "testing"
        }
        
        findings = self.rule.collect_findings(config)
        self.assertEqual(len(findings), 1)
        
        finding = findings[0]
        self.assertEqual(finding.rule_id, "cli_backend_migration")
        self.assertEqual(finding.severity, "warning")
        self.assertIn("cli_backend: claude-code", finding.message)
        self.assertEqual(finding.context["field"], "cli_backend")
        self.assertEqual(finding.context["value"], "claude-code")
        self.assertEqual(finding.context["location"], "root")
    
    def test_role_level_cli_backend(self):
        """Test detection of role-level cli_backend."""
        config = {
            "framework": "praisonai",
            "topic": "testing",
            "roles": {
                "coder": {
                    "role": "Code refactorer",
                    "goal": "Refactor code",
                    "backstory": "Expert coder",
                    "cli_backend": "claude-code"
                },
                "reviewer": {
                    "role": "Code reviewer",
                    "goal": "Review code", 
                    "backstory": "Expert reviewer"
                }
            }
        }
        
        findings = self.rule.collect_findings(config)
        self.assertEqual(len(findings), 1)
        
        finding = findings[0]
        self.assertEqual(finding.rule_id, "cli_backend_migration")
        self.assertEqual(finding.severity, "warning")
        self.assertIn("cli_backend: claude-code", finding.message)
        self.assertIn("role 'coder'", finding.message)
        self.assertEqual(finding.context["location"], "roles.coder")
    
    def test_multiple_cli_backends(self):
        """Test detection of multiple cli_backend configurations."""
        config = {
            "framework": "praisonai",
            "cli_backend": "claude-code", 
            "topic": "testing",
            "roles": {
                "coder": {
                    "role": "Code refactorer",
                    "cli_backend": "openai-gpt"
                },
                "reviewer": {
                    "role": "Code reviewer",
                    "cli_backend": "anthropic"
                }
            }
        }
        
        findings = self.rule.collect_findings(config)
        self.assertEqual(len(findings), 3)
        
        # Check all findings are from the same rule
        for finding in findings:
            self.assertEqual(finding.rule_id, "cli_backend_migration")
            self.assertEqual(finding.severity, "warning")
    
    def test_apply_fix_top_level(self):
        """Test applying fix to top-level cli_backend."""
        config = {
            "framework": "praisonai",
            "cli_backend": "claude-code",
            "topic": "testing"
        }
        
        result = self.rule.apply_fix(config)
        
        # cli_backend should be removed
        self.assertNotIn("cli_backend", result)
        
        # models.default.runtime should be set
        self.assertIn("models", result)
        self.assertIn("default", result["models"])
        self.assertEqual(result["models"]["default"]["runtime"], "claude-code")
        
        # Other fields should remain
        self.assertEqual(result["framework"], "praisonai")
        self.assertEqual(result["topic"], "testing")
    
    def test_apply_fix_role_level(self):
        """Test applying fix to role-level cli_backend."""
        config = {
            "framework": "praisonai", 
            "topic": "testing",
            "roles": {
                "coder": {
                    "role": "Code refactorer",
                    "cli_backend": "claude-code",
                    "goal": "Refactor code"
                }
            }
        }
        
        result = self.rule.apply_fix(config)
        
        # Role cli_backend should be removed
        self.assertNotIn("cli_backend", result["roles"]["coder"])
        
        # Role models.default.runtime should be set
        role = result["roles"]["coder"]
        self.assertIn("models", role)
        self.assertIn("default", role["models"])
        self.assertEqual(role["models"]["default"]["runtime"], "claude-code")
        
        # Other role fields should remain
        self.assertEqual(role["role"], "Code refactorer")
        self.assertEqual(role["goal"], "Refactor code")
    
    def test_apply_fix_preserves_existing_models(self):
        """Test that existing models config is preserved when applying fix."""
        config = {
            "framework": "praisonai",
            "cli_backend": "claude-code",
            "models": {
                "default": {
                    "provider": "anthropic",
                    "model": "claude-3-sonnet"
                }
            }
        }
        
        result = self.rule.apply_fix(config)
        
        # Existing models config should be preserved
        models = result["models"]["default"]
        self.assertEqual(models["provider"], "anthropic")
        self.assertEqual(models["model"], "claude-3-sonnet")
        
        # Runtime should be added
        self.assertEqual(models["runtime"], "claude-code")
        
        # cli_backend should be removed
        self.assertNotIn("cli_backend", result)
    
    def test_backend_mapping(self):
        """Test that backend values are mapped correctly."""
        test_cases = [
            ("claude-code", "claude-code"),
            ("openai-gpt", "openai-gpt"),
            ("anthropic", "anthropic"),
            ("unknown-backend", "unknown-backend")  # Unmapped values pass through
        ]
        
        for input_backend, expected_runtime in test_cases:
            config = {"cli_backend": input_backend}
            result = self.rule.apply_fix(config)
            
            actual_runtime = result["models"]["default"]["runtime"]
            self.assertEqual(actual_runtime, expected_runtime)
    
    def test_idempotent_fix(self):
        """Test that applying fix multiple times is idempotent."""
        config = {
            "framework": "praisonai",
            "cli_backend": "claude-code"
        }
        
        # Apply fix once
        result1 = self.rule.apply_fix(config)
        
        # Apply fix again
        result2 = self.rule.apply_fix(result1)
        
        # Should be identical
        self.assertEqual(result1, result2)
        
        # Should have no findings after migration
        findings = self.rule.collect_findings(result2)
        self.assertEqual(len(findings), 0)


class TestDoctorRulesRegistry(unittest.TestCase):
    """Test the doctor rules registry."""
    
    def setUp(self):
        self.registry = DoctorRulesRegistry()
    
    def test_register_rule(self):
        """Test registering a rule."""
        rule = CliBackendMigrationRule()
        self.registry.register_rule(rule)
        
        rules = self.registry.get_rules()
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule_id, "cli_backend_migration")
    
    def test_get_rule_by_id(self):
        """Test getting a rule by ID."""
        rule = CliBackendMigrationRule()
        self.registry.register_rule(rule)
        
        found_rule = self.registry.get_rule("cli_backend_migration")
        self.assertIsNotNone(found_rule)
        self.assertEqual(found_rule.rule_id, "cli_backend_migration")
        
        missing_rule = self.registry.get_rule("nonexistent")
        self.assertIsNone(missing_rule)
    
    def test_collect_all_findings(self):
        """Test collecting findings from all rules."""
        config = {
            "cli_backend": "claude-code",
            "roles": {
                "test": {
                    "cli_backend": "openai-gpt"
                }
            }
        }
        
        rule = CliBackendMigrationRule()
        self.registry.register_rule(rule)
        
        findings = self.registry.collect_all_findings(config)
        self.assertEqual(len(findings), 2)
    
    def test_apply_all_fixes(self):
        """Test applying fixes from all rules."""
        config = {
            "cli_backend": "claude-code"
        }
        
        rule = CliBackendMigrationRule()
        self.registry.register_rule(rule)
        
        result = self.registry.apply_all_fixes(config)
        
        # Should be migrated
        self.assertNotIn("cli_backend", result)
        self.assertEqual(result["models"]["default"]["runtime"], "claude-code")


if __name__ == '__main__':
    unittest.main()