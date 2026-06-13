#!/usr/bin/env python3
"""Test script for runtime migration functionality."""

import sys
import os

# Add the praisonai-agents source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.runtime.builtin_rules import CliBackendMigrationRule
from praisonaiagents.runtime import collect_findings, apply_fixes

def test_migration():
    """Test the migration functionality."""
    print("Testing Runtime Migration Functionality")
    print("=" * 50)
    
    # Test configuration with cli_backend
    test_config = {
        "framework": "praisonai",
        "topic": "coding",
        "cli_backend": "claude-code",
        "roles": {
            "coder": {
                "role": "Code refactorer", 
                "goal": "Refactor Python modules for better maintainability",
                "backstory": "Senior engineer with expertise in clean code principles",
                "cli_backend": "openai-gpt",
                "tasks": {
                    "refactor": {
                        "description": "Refactor utils.py to improve code quality",
                        "expected_output": "Refactored code with improved structure and documentation"
                    }
                }
            }
        }
    }
    
    print("Original configuration:")
    print(test_config)
    print()
    
    # Test individual rule
    rule = CliBackendMigrationRule()
    print(f"Using rule: {rule.rule_id}")
    
    findings = rule.collect_findings(test_config)
    print(f"Found {len(findings)} issues:")
    for finding in findings:
        print(f"  - {finding.message}")
        print(f"    Location: {finding.context.get('location', 'unknown')}")
        print(f"    Fix: {finding.fix_description}")
    print()
    
    # Test registry-based approach
    print("Testing registry-based approach:")
    registry_findings = collect_findings(test_config)
    print(f"Registry found {len(registry_findings)} issues")
    
    # Apply migration
    migrated_config = apply_fixes(test_config)
    print("Migrated configuration:")
    print(migrated_config)
    print()
    
    # Verify migration was successful
    post_migration_findings = collect_findings(migrated_config)
    print(f"After migration: {len(post_migration_findings)} issues remain")
    
    # Check that the migration worked correctly
    assert 'cli_backend' not in migrated_config, "Top-level cli_backend should be removed"
    assert 'models' in migrated_config, "Models section should exist"
    assert migrated_config['models']['default']['runtime'] == 'claude-code', "Runtime should be set correctly"
    
    coder_role = migrated_config['roles']['coder']
    assert 'cli_backend' not in coder_role, "Role cli_backend should be removed"
    assert 'models' in coder_role, "Role models section should exist"
    assert coder_role['models']['default']['runtime'] == 'openai-gpt', "Role runtime should be set correctly"
    
    print("✅ All tests passed!")

if __name__ == "__main__":
    test_migration()