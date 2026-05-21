#!/usr/bin/env python3
"""Test backward compatibility of skills system."""

import sys
import tempfile
from pathlib import Path

# Add the source path to PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent / "src" / "praisonai-agents"))

def test_existing_skill_parsing():
    """Test that existing skills still parse correctly."""
    print("Testing existing skill parsing...")
    
    try:
        from praisonaiagents.skills.parser import read_properties
        
        # Create a skill with old-style frontmatter (no requires_* fields)
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir) / "old-skill"
            skill_dir.mkdir()
            
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text('''---
name: old-skill
description: An existing skill without requirements
allowed-tools: web_search file_read
license: MIT
compatibility: all
when_to_use: When you need to process files
disable-model-invocation: false
user-invocable: true
---

# Old Skill

This skill should still work exactly as before.
''')
            
            properties = read_properties(skill_dir)
            
            # Basic properties should work
            assert properties.name == "old-skill"
            assert properties.description == "An existing skill without requirements"
            assert properties.license == "MIT"
            assert properties.compatibility == "all"
            assert properties.when_to_use == "When you need to process files"
            assert properties.disable_model_invocation == False
            assert properties.user_invocable == True
            
            # Requirements should be parsed but with allowed-tools converted
            assert properties.requirements is not None
            assert properties.requirements.tools == ["web_search", "file_read"]
            assert properties.requirements.servers == []
            assert properties.requirements.env_vars == []
            
            print("✓ Existing skill parsing works")
            
            # Test empty skill (no frontmatter extensions)
            empty_skill_dir = Path(temp_dir) / "minimal-skill"
            empty_skill_dir.mkdir()
            
            empty_skill_md = empty_skill_dir / "SKILL.md"
            empty_skill_md.write_text('''---
name: minimal-skill
description: A minimal skill
---

# Minimal Skill

Just the basics.
''')
            
            minimal_props = read_properties(empty_skill_dir)
            assert minimal_props.name == "minimal-skill"
            assert minimal_props.description == "A minimal skill"
            assert minimal_props.requirements is not None
            assert minimal_props.requirements.is_empty()
            
            print("✓ Minimal skill parsing works")
            
        return True
        
    except Exception as e:
        print(f"❌ Parsing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_manager_backward_compatibility():
    """Test that SkillManager still works with existing features."""
    print("\nTesting SkillManager backward compatibility...")
    
    try:
        from praisonaiagents.skills.manager import SkillManager
        
        # Test that manager can be created without any parameters (old way)
        manager = SkillManager()
        assert hasattr(manager, '_skills')
        assert hasattr(manager, '_loader')
        assert hasattr(manager, '_discovered')
        
        # Test that existing methods still exist
        assert hasattr(manager, 'discover')
        assert hasattr(manager, 'get_skill')
        assert hasattr(manager, 'activate')
        assert hasattr(manager, 'get_available_skills')
        assert hasattr(manager, 'get_user_invocable_skills')
        assert hasattr(manager, 'invoke')
        assert hasattr(manager, 'to_prompt')
        
        print("✓ SkillManager interface preserved")
        
        # Test that new methods are additive only
        assert hasattr(manager, 'validate_skill_capabilities')
        assert hasattr(manager, 'get_available_skills_by_state')
        assert hasattr(manager, 'get_skills_diagnostics')
        
        print("✓ New methods added without breaking existing interface")
        
        return True
        
    except Exception as e:
        print(f"❌ SkillManager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_enforcement_level_defaults():
    """Test that enforcement level defaults are backward compatible."""
    print("\nTesting enforcement level defaults...")
    
    try:
        import os
        from praisonaiagents.skills.manager import SkillManager
        from praisonaiagents.skills.capability_validator import EnforcementLevel
        
        # Test default behavior (no env var)
        if 'SKILL_CAPABILITY_ENFORCEMENT' in os.environ:
            del os.environ['SKILL_CAPABILITY_ENFORCEMENT']
            
        manager = SkillManager()
        # Default should be WARN (non-breaking but informative)
        assert manager._validator.enforcement_level == EnforcementLevel.WARN
        
        print("✓ Default enforcement level is WARN (backward compatible)")
        
        # Test that disabled mode works (completely backward compatible)
        os.environ['SKILL_CAPABILITY_ENFORCEMENT'] = 'disabled'
        disabled_manager = SkillManager()
        assert disabled_manager._validator.enforcement_level == EnforcementLevel.DISABLED
        
        print("✓ Disabled mode works for full backward compatibility")
        
        # Clean up
        if 'SKILL_CAPABILITY_ENFORCEMENT' in os.environ:
            del os.environ['SKILL_CAPABILITY_ENFORCEMENT']
            
        return True
        
    except Exception as e:
        print(f"❌ Enforcement defaults test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_skills_without_requirements():
    """Test that skills without requirements work exactly as before."""
    print("\nTesting skills without requirements...")
    
    try:
        from praisonaiagents.skills.models import SkillProperties
        from praisonaiagents.skills.capability_validator import CapabilityValidator, EnforcementLevel
        
        # Create a skill without any requirements (old style)
        skill = SkillProperties(
            name="legacy-skill",
            description="A legacy skill without requirements",
            allowed_tools="web_search file_read",  # Old format
            # No requirements field
        )
        
        # Test with all enforcement levels - should always be ACTIVE
        for level in EnforcementLevel:
            validator = CapabilityValidator(level)
            result = validator.validate_skill(skill)
            
            assert result.state.value == "active"
            assert result.is_fully_satisfied
            assert not result.has_critical_missing
            assert len(result.warnings) == 0
            assert len(result.errors) == 0
        
        print("✓ Skills without requirements are always ACTIVE")
        
        return True
        
    except Exception as e:
        print(f"❌ Legacy skills test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🔄 Testing backward compatibility of skill capability validation...\n")
    
    success1 = test_existing_skill_parsing()
    success2 = test_manager_backward_compatibility()  
    success3 = test_enforcement_level_defaults()
    success4 = test_skills_without_requirements()
    
    if all([success1, success2, success3, success4]):
        print("\n✅ All backward compatibility tests passed! Existing functionality preserved.")
        sys.exit(0)
    else:
        print("\n❌ Some backward compatibility tests failed.")
        sys.exit(1)
