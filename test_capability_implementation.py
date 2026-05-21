#!/usr/bin/env python3
"""Smoke test for skill capability validation implementation."""

import sys
import os
from pathlib import Path

# Add the source path to PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent / "src" / "praisonai-agents"))

def test_basic_functionality():
    """Test that our basic implementation works."""
    print("Testing basic skill capability validation...")
    
    try:
        # Test imports
        from praisonaiagents.skills.models import SkillRequirements, SkillState, SkillProperties
        from praisonaiagents.skills.capability_validator import CapabilityValidator, EnforcementLevel, ValidationResult
        print("✓ Imports successful")
        
        # Test SkillRequirements parsing
        metadata = {
            "requires_tools": ["web_search", "file_write"],
            "requires_servers": ["mcp:filesystem"],
            "requires_env": ["API_KEY"]
        }
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.tools == ["web_search", "file_write"]
        assert requirements.servers == ["mcp:filesystem"]
        assert requirements.env_vars == ["API_KEY"]
        print("✓ SkillRequirements parsing works")
        
        # Test CapabilityValidator
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )
        
        validator = CapabilityValidator(EnforcementLevel.WARN)
        result = validator.validate_skill(
            skill,
            available_tools=set(["web_search"]),  # Missing file_write
            available_servers=set()  # Missing mcp:filesystem
        )
        
        assert result.skill_name == "test-skill"
        assert result.state == SkillState.DEGRADED
        assert "file_write" in result.missing_tools
        assert "mcp:filesystem" in result.missing_servers
        print("✓ CapabilityValidator validation works")
        
        # Test enforcement levels
        strict_validator = CapabilityValidator(EnforcementLevel.STRICT)
        strict_result = strict_validator.validate_skill(skill, available_tools=set(), available_servers=set())
        assert strict_result.state == SkillState.UNAVAILABLE
        print("✓ Enforcement levels work")
        
        # Test skill with no requirements
        no_req_skill = SkillProperties(
            name="simple-skill",
            description="Simple skill"
        )
        simple_result = validator.validate_skill(no_req_skill)
        assert simple_result.state == SkillState.ACTIVE
        assert simple_result.is_fully_satisfied
        print("✓ Skills without requirements work")
        
        print("\n🎉 All basic functionality tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_manager_integration():
    """Test SkillManager integration."""
    print("\nTesting SkillManager integration...")
    
    try:
        from praisonaiagents.skills.manager import SkillManager
        from praisonaiagents.skills.capability_validator import EnforcementLevel
        
        # Test manager initialization
        manager = SkillManager()
        assert hasattr(manager, '_validator')
        assert hasattr(manager, '_validation_cache')
        print("✓ SkillManager initialization works")
        
        # Test with explicit enforcement level
        strict_manager = SkillManager(EnforcementLevel.STRICT)
        assert strict_manager._validator.enforcement_level == EnforcementLevel.STRICT
        print("✓ Explicit enforcement level works")
        
        print("✓ SkillManager integration works")
        return True
        
    except Exception as e:
        print(f"❌ SkillManager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 Running skill capability validation smoke tests...\n")
    
    success1 = test_basic_functionality()
    success2 = test_manager_integration()
    
    if success1 and success2:
        print("\n✅ All smoke tests passed! Implementation is working correctly.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Check the implementation.")
        sys.exit(1)
