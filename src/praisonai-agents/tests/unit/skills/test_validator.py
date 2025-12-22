"""Tests for Agent Skills validator."""

from pathlib import Path
import tempfile


class TestValidateName:
    """Tests for skill name validation."""
    
    def test_valid_name_simple(self):
        """Test valid simple skill name."""
        from praisonaiagents.skills.validator import _validate_name
        
        errors = _validate_name("test-skill", None)
        
        assert errors == []
    
    def test_valid_name_with_numbers(self):
        """Test valid name with numbers."""
        from praisonaiagents.skills.validator import _validate_name
        
        errors = _validate_name("skill-v2", None)
        
        assert errors == []
    
    def test_invalid_name_uppercase(self):
        """Test that uppercase letters are rejected."""
        from praisonaiagents.skills.validator import _validate_name
        
        errors = _validate_name("Test-Skill", None)
        
        assert len(errors) > 0
        assert any("lowercase" in e.lower() for e in errors)
    
    def test_invalid_name_starts_with_hyphen(self):
        """Test that names starting with hyphen are rejected."""
        from praisonaiagents.skills.validator import _validate_name
        
        errors = _validate_name("-skill", None)
        
        assert len(errors) > 0
        assert any("hyphen" in e.lower() for e in errors)
    
    def test_invalid_name_ends_with_hyphen(self):
        """Test that names ending with hyphen are rejected."""
        from praisonaiagents.skills.validator import _validate_name
        
        errors = _validate_name("skill-", None)
        
        assert len(errors) > 0
        assert any("hyphen" in e.lower() for e in errors)
    
    def test_invalid_name_consecutive_hyphens(self):
        """Test that consecutive hyphens are rejected."""
        from praisonaiagents.skills.validator import _validate_name
        
        errors = _validate_name("test--skill", None)
        
        assert len(errors) > 0
        assert any("consecutive" in e.lower() for e in errors)
    
    def test_invalid_name_too_long(self):
        """Test that names over 64 characters are rejected."""
        from praisonaiagents.skills.validator import _validate_name
        
        long_name = "a" * 65
        errors = _validate_name(long_name, None)
        
        assert len(errors) > 0
        assert any("64" in e or "limit" in e.lower() for e in errors)
    
    def test_invalid_name_special_characters(self):
        """Test that special characters are rejected."""
        from praisonaiagents.skills.validator import _validate_name
        
        errors = _validate_name("test_skill", None)
        
        assert len(errors) > 0
        assert any("invalid" in e.lower() or "character" in e.lower() for e in errors)
    
    def test_name_must_match_directory(self):
        """Test that name must match parent directory name."""
        from praisonaiagents.skills.validator import _validate_name
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "actual-name"
            skill_dir.mkdir()
            
            errors = _validate_name("different-name", skill_dir)
            
            assert len(errors) > 0
            assert any("match" in e.lower() for e in errors)


class TestValidateDescription:
    """Tests for skill description validation."""
    
    def test_valid_description(self):
        """Test valid description."""
        from praisonaiagents.skills.validator import _validate_description
        
        errors = _validate_description("A helpful skill that does things")
        
        assert errors == []
    
    def test_invalid_description_empty(self):
        """Test that empty description is rejected."""
        from praisonaiagents.skills.validator import _validate_description
        
        errors = _validate_description("")
        
        assert len(errors) > 0
        assert any("empty" in e.lower() or "non-empty" in e.lower() for e in errors)
    
    def test_invalid_description_too_long(self):
        """Test that descriptions over 1024 characters are rejected."""
        from praisonaiagents.skills.validator import _validate_description
        
        long_desc = "a" * 1025
        errors = _validate_description(long_desc)
        
        assert len(errors) > 0
        assert any("1024" in e or "limit" in e.lower() for e in errors)


class TestValidateCompatibility:
    """Tests for skill compatibility validation."""
    
    def test_valid_compatibility(self):
        """Test valid compatibility string."""
        from praisonaiagents.skills.validator import _validate_compatibility
        
        errors = _validate_compatibility("Requires Python 3.11+")
        
        assert errors == []
    
    def test_invalid_compatibility_too_long(self):
        """Test that compatibility over 500 characters is rejected."""
        from praisonaiagents.skills.validator import _validate_compatibility
        
        long_compat = "a" * 501
        errors = _validate_compatibility(long_compat)
        
        assert len(errors) > 0
        assert any("500" in e or "limit" in e.lower() for e in errors)


class TestValidateMetadata:
    """Tests for full metadata validation."""
    
    def test_valid_metadata(self):
        """Test valid complete metadata."""
        from praisonaiagents.skills.validator import validate_metadata
        
        metadata = {
            "name": "test-skill",
            "description": "A test skill"
        }
        
        errors = validate_metadata(metadata)
        
        assert errors == []
    
    def test_missing_name(self):
        """Test error when name is missing."""
        from praisonaiagents.skills.validator import validate_metadata
        
        metadata = {
            "description": "A test skill"
        }
        
        errors = validate_metadata(metadata)
        
        assert len(errors) > 0
        assert any("name" in e.lower() for e in errors)
    
    def test_missing_description(self):
        """Test error when description is missing."""
        from praisonaiagents.skills.validator import validate_metadata
        
        metadata = {
            "name": "test-skill"
        }
        
        errors = validate_metadata(metadata)
        
        assert len(errors) > 0
        assert any("description" in e.lower() for e in errors)
    
    def test_unexpected_fields_rejected(self):
        """Test that unexpected fields are rejected."""
        from praisonaiagents.skills.validator import validate_metadata
        
        metadata = {
            "name": "test-skill",
            "description": "A test skill",
            "unknown-field": "value"
        }
        
        errors = validate_metadata(metadata)
        
        assert len(errors) > 0
        assert any("unexpected" in e.lower() or "unknown-field" in e for e in errors)


class TestValidate:
    """Tests for full skill directory validation."""
    
    def test_validate_valid_skill(self):
        """Test validating a valid skill directory."""
        from praisonaiagents.skills.validator import validate
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill for validation
---

# Test Skill
""")
            
            errors = validate(skill_dir)
            
            assert errors == []
    
    def test_validate_missing_skill_md(self):
        """Test error when SKILL.md is missing."""
        from praisonaiagents.skills.validator import validate
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "empty-skill"
            skill_dir.mkdir()
            
            errors = validate(skill_dir)
            
            assert len(errors) > 0
            assert any("skill.md" in e.lower() for e in errors)
    
    def test_validate_nonexistent_directory(self):
        """Test error when directory doesn't exist."""
        from praisonaiagents.skills.validator import validate
        
        errors = validate(Path("/nonexistent/path"))
        
        assert len(errors) > 0
        assert any("exist" in e.lower() for e in errors)
    
    def test_validate_not_a_directory(self):
        """Test error when path is not a directory."""
        from praisonaiagents.skills.validator import validate
        
        with tempfile.NamedTemporaryFile() as tmpfile:
            errors = validate(Path(tmpfile.name))
            
            assert len(errors) > 0
            assert any("directory" in e.lower() for e in errors)
