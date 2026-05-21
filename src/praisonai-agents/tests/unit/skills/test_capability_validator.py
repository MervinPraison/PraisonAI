"""Tests for skill capability validation."""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, patch

from praisonaiagents.skills.models import SkillProperties, SkillRequirements, SkillState
from praisonaiagents.skills.capability_validator import (
    CapabilityValidator, 
    EnforcementLevel,
    ValidationResult
)


class TestSkillRequirements:
    """Test SkillRequirements parsing and normalization."""
    
    def test_from_frontmatter_empty(self):
        """Test parsing empty frontmatter."""
        requirements = SkillRequirements.from_frontmatter({})
        assert requirements.is_empty()
        assert not requirements  # Test __bool__
        
    def test_from_frontmatter_tools_list(self):
        """Test parsing tools from list."""
        metadata = {"requires_tools": ["web_search", "file_write"]}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.tools == ["web_search", "file_write"]
        assert requirements.servers == []
        assert not requirements.is_empty()
        
    def test_from_frontmatter_tools_string(self):
        """Test parsing tools from string."""
        metadata = {"requires-tools": "web_search file_write"}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.tools == ["web_search", "file_write"]
        
    def test_from_frontmatter_backward_compatibility(self):
        """Test backward compatibility with allowed-tools."""
        metadata = {"allowed-tools": ["existing_tool"]}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.tools == ["existing_tool"]
        
    def test_from_frontmatter_servers(self):
        """Test parsing server requirements."""
        metadata = {"requires_servers": ["mcp:filesystem", "http:internal"]}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.servers == ["mcp:filesystem", "http:internal"]
        
    def test_from_frontmatter_env_vars(self):
        """Test parsing environment variable requirements."""
        metadata = {"requires_env": ["API_KEY", "SECRET_TOKEN"]}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.env_vars == ["API_KEY", "SECRET_TOKEN"]
        
    def test_from_frontmatter_openclaw_hints(self):
        """Test parsing OpenClaw hints."""
        metadata = {"openclaw": {"version": "1.0", "compatibility": "hermes"}}
        requirements = SkillRequirements.from_frontmatter(metadata)
        assert requirements.openclaw_hints == {"version": "1.0", "compatibility": "hermes"}
        
    def test_normalize_list(self):
        """Test list normalization utility."""
        assert SkillRequirements._normalize_list("a b c") == ["a", "b", "c"]
        assert SkillRequirements._normalize_list("a,b,c") == ["a", "b", "c"]
        assert SkillRequirements._normalize_list("a, b c") == ["a", "b", "c"]
        assert SkillRequirements._normalize_list(["a", "b", "c"]) == ["a", "b", "c"]
        assert SkillRequirements._normalize_list("") == []
        assert SkillRequirements._normalize_list([]) == []
        assert SkillRequirements._normalize_list(123) == []


class TestCapabilityValidator:
    """Test capability validation logic."""
    
    def test_enforcement_levels(self):
        """Test different enforcement levels."""
        assert EnforcementLevel.DISABLED.value == "disabled"
        assert EnforcementLevel.WARN.value == "warn" 
        assert EnforcementLevel.STRICT.value == "strict"
        
    def test_validator_initialization(self):
        """Test validator initialization."""
        validator = CapabilityValidator()
        assert validator.enforcement_level == EnforcementLevel.WARN
        
        validator = CapabilityValidator(EnforcementLevel.STRICT)
        assert validator.enforcement_level == EnforcementLevel.STRICT
        
    def test_validate_skill_no_requirements(self):
        """Test validation of skill with no requirements."""
        skill = SkillProperties(
            name="test-skill",
            description="Test skill", 
            requirements=None
        )
        
        validator = CapabilityValidator()
        result = validator.validate_skill(skill)
        
        assert result.skill_name == "test-skill"
        assert result.state == SkillState.ACTIVE
        assert result.is_fully_satisfied
        assert not result.has_critical_missing
        
    def test_validate_skill_empty_requirements(self):
        """Test validation of skill with empty requirements."""
        requirements = SkillRequirements()
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )
        
        validator = CapabilityValidator()
        result = validator.validate_skill(skill)
        
        assert result.state == SkillState.ACTIVE
        assert result.is_fully_satisfied
        
    @patch.dict(os.environ, {"TEST_VAR": "value"})
    def test_validate_skill_satisfied_requirements(self):
        """Test validation with all requirements satisfied."""
        requirements = SkillRequirements(
            tools=["available_tool"],
            servers=["available_server"],
            env_vars=["TEST_VAR"]
        )
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )
        
        available_tools = {"available_tool"}
        available_servers = {"available_server"}
        
        validator = CapabilityValidator()
        result = validator.validate_skill(
            skill, 
            available_tools=available_tools,
            available_servers=available_servers
        )
        
        assert result.state == SkillState.ACTIVE
        assert result.satisfied_tools == ["available_tool"]
        assert result.satisfied_servers == ["available_server"]
        assert result.satisfied_env_vars == ["TEST_VAR"]
        assert result.is_fully_satisfied
        
    def test_validate_skill_missing_tools_warn_mode(self):
        """Test validation with missing tools in warn mode."""
        requirements = SkillRequirements(tools=["missing_tool"])
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )
        
        validator = CapabilityValidator(EnforcementLevel.WARN)
        result = validator.validate_skill(
            skill,
            available_tools=set(),
            available_servers=set()
        )
        
        assert result.state == SkillState.DEGRADED
        assert result.missing_tools == ["missing_tool"]
        assert not result.is_fully_satisfied
        assert result.has_critical_missing
        assert len(result.warnings) == 1
        assert "missing_tool" in result.warnings[0]
        
    def test_validate_skill_missing_tools_strict_mode(self):
        """Test validation with missing tools in strict mode."""
        requirements = SkillRequirements(tools=["missing_tool"])
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )
        
        validator = CapabilityValidator(EnforcementLevel.STRICT)
        result = validator.validate_skill(
            skill,
            available_tools=set(),
            available_servers=set()
        )
        
        assert result.state == SkillState.UNAVAILABLE
        assert result.missing_tools == ["missing_tool"]
        assert not result.is_fully_satisfied
        assert result.has_critical_missing
        assert len(result.errors) == 1
        assert "missing_tool" in result.errors[0]
        
    def test_validate_skill_missing_env_vars_warn(self):
        """Test validation with missing environment variables in warn mode."""
        requirements = SkillRequirements(env_vars=["MISSING_VAR"])
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )
        
        validator = CapabilityValidator(EnforcementLevel.WARN)
        result = validator.validate_skill(skill)
        
        assert result.state == SkillState.DEGRADED
        assert result.missing_env_vars == ["MISSING_VAR"]
        assert len(result.warnings) == 1
        assert len(result.errors) == 0

    def test_validate_skill_missing_env_vars_strict(self):
        """Test validation with missing environment variables in strict mode."""
        requirements = SkillRequirements(env_vars=["MISSING_VAR"])
        skill = SkillProperties(
            name="test-skill",
            description="Test skill",
            requirements=requirements
        )

        validator = CapabilityValidator(EnforcementLevel.STRICT)
        result = validator.validate_skill(skill)

        assert result.state == SkillState.UNAVAILABLE
        assert result.missing_env_vars == ["MISSING_VAR"]
        assert len(result.warnings) == 0
        assert len(result.errors) == 1
        
    def test_validation_result_to_dict(self):
        """Test ValidationResult serialization."""
        result = ValidationResult(
            skill_name="test-skill",
            state=SkillState.DEGRADED,
            satisfied_tools=["tool1"],
            missing_tools=["tool2"],
            satisfied_servers=[],
            missing_servers=[],
            satisfied_env_vars=[],
            missing_env_vars=["VAR1"],
            warnings=["Missing tool2"],
            errors=[]
        )
        
        data = result.to_dict()
        assert data["skill_name"] == "test-skill"
        assert data["state"] == "degraded"
        assert data["satisfied_tools"] == ["tool1"]
        assert data["missing_tools"] == ["tool2"]
        assert data["warnings"] == ["Missing tool2"]
        assert data["is_fully_satisfied"] == False
        assert data["has_critical_missing"] == True


class TestIntegration:
    """Integration tests for the full capability validation system."""
    
    def test_skill_parsing_with_requirements(self):
        """Test that skills parse requirements correctly."""
        from praisonaiagents.skills.parser import read_properties
        from tempfile import TemporaryDirectory
        
        with TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir) / "test-skill"
            skill_dir.mkdir()
            
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text('''---
name: test-skill
description: A test skill
requires_tools:
  - web_search
  - file_write
requires_servers:
  - mcp:filesystem
requires_env:
  - API_KEY
openclaw:
  version: "1.0"
---

# Test Skill

This is a test skill.
''')
            
            properties = read_properties(skill_dir)
            assert properties.requirements is not None
            assert properties.requirements.tools == ["web_search", "file_write"]
            assert properties.requirements.servers == ["mcp:filesystem"]
            assert properties.requirements.env_vars == ["API_KEY"]
            assert properties.requirements.openclaw_hints == {"version": "1.0"}
            
    def test_skill_manager_enforcement(self):
        """Test that SkillManager respects enforcement levels."""
        from praisonaiagents.skills.manager import SkillManager
        
        # Test that manager initializes with default enforcement
        manager = SkillManager()
        assert manager._validator.enforcement_level in [
            EnforcementLevel.WARN, 
            EnforcementLevel.DISABLED,
            EnforcementLevel.STRICT,
            EnforcementLevel.TELEMETRY
        ]
        
        # Test explicit enforcement level
        strict_manager = SkillManager(EnforcementLevel.STRICT)
        assert strict_manager._validator.enforcement_level == EnforcementLevel.STRICT
