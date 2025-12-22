"""Tests for Agent Skills models."""

from pathlib import Path


class TestSkillProperties:
    """Tests for SkillProperties dataclass."""
    
    def test_skill_properties_required_fields(self):
        """Test that SkillProperties requires name and description."""
        from praisonaiagents.skills.models import SkillProperties
        
        skill = SkillProperties(
            name="test-skill",
            description="A test skill for unit testing"
        )
        
        assert skill.name == "test-skill"
        assert skill.description == "A test skill for unit testing"
    
    def test_skill_properties_optional_fields_default_none(self):
        """Test that optional fields default to None."""
        from praisonaiagents.skills.models import SkillProperties
        
        skill = SkillProperties(
            name="test-skill",
            description="A test skill"
        )
        
        assert skill.license is None
        assert skill.compatibility is None
        assert skill.allowed_tools is None
        assert skill.path is None
    
    def test_skill_properties_metadata_defaults_empty_dict(self):
        """Test that metadata defaults to empty dict."""
        from praisonaiagents.skills.models import SkillProperties
        
        skill = SkillProperties(
            name="test-skill",
            description="A test skill"
        )
        
        assert skill.metadata == {}
    
    def test_skill_properties_all_fields(self):
        """Test SkillProperties with all fields populated."""
        from praisonaiagents.skills.models import SkillProperties
        
        skill = SkillProperties(
            name="pdf-processing",
            description="Extract text and tables from PDF files",
            license="Apache-2.0",
            compatibility="Requires pypdf package",
            allowed_tools="Read Grep Bash",
            metadata={"author": "test-org", "version": "1.0"},
            path=Path("/path/to/skill")
        )
        
        assert skill.name == "pdf-processing"
        assert skill.description == "Extract text and tables from PDF files"
        assert skill.license == "Apache-2.0"
        assert skill.compatibility == "Requires pypdf package"
        assert skill.allowed_tools == "Read Grep Bash"
        assert skill.metadata == {"author": "test-org", "version": "1.0"}
        assert skill.path == Path("/path/to/skill")
    
    def test_skill_properties_to_dict(self):
        """Test to_dict method excludes None values."""
        from praisonaiagents.skills.models import SkillProperties
        
        skill = SkillProperties(
            name="test-skill",
            description="A test skill",
            license="MIT"
        )
        
        result = skill.to_dict()
        
        assert result["name"] == "test-skill"
        assert result["description"] == "A test skill"
        assert result["license"] == "MIT"
        assert "compatibility" not in result
        assert "allowed-tools" not in result
        assert "metadata" not in result  # Empty metadata excluded
    
    def test_skill_properties_to_dict_with_metadata(self):
        """Test to_dict includes non-empty metadata."""
        from praisonaiagents.skills.models import SkillProperties
        
        skill = SkillProperties(
            name="test-skill",
            description="A test skill",
            metadata={"version": "1.0"}
        )
        
        result = skill.to_dict()
        
        assert result["metadata"] == {"version": "1.0"}
    
    def test_skill_properties_to_dict_allowed_tools_key(self):
        """Test to_dict uses 'allowed-tools' key (hyphenated)."""
        from praisonaiagents.skills.models import SkillProperties
        
        skill = SkillProperties(
            name="test-skill",
            description="A test skill",
            allowed_tools="Read Write"
        )
        
        result = skill.to_dict()
        
        assert "allowed-tools" in result
        assert result["allowed-tools"] == "Read Write"


class TestSkillMetadata:
    """Tests for SkillMetadata dataclass (lightweight for system prompt)."""
    
    def test_skill_metadata_required_fields(self):
        """Test SkillMetadata with required fields."""
        from praisonaiagents.skills.models import SkillMetadata
        
        meta = SkillMetadata(
            name="test-skill",
            description="A test skill",
            location="/path/to/skill/SKILL.md"
        )
        
        assert meta.name == "test-skill"
        assert meta.description == "A test skill"
        assert meta.location == "/path/to/skill/SKILL.md"
    
    def test_skill_metadata_from_properties(self):
        """Test creating SkillMetadata from SkillProperties."""
        from praisonaiagents.skills.models import SkillProperties, SkillMetadata
        
        props = SkillProperties(
            name="pdf-skill",
            description="Process PDF files",
            path=Path("/skills/pdf-skill")
        )
        
        meta = SkillMetadata.from_properties(props)
        
        assert meta.name == "pdf-skill"
        assert meta.description == "Process PDF files"
        assert "/skills/pdf-skill" in meta.location


class TestParseError:
    """Tests for ParseError exception."""
    
    def test_parse_error_message(self):
        """Test ParseError stores message correctly."""
        from praisonaiagents.skills.models import ParseError
        
        error = ParseError("Invalid YAML frontmatter")
        
        assert str(error) == "Invalid YAML frontmatter"
    
    def test_parse_error_is_exception(self):
        """Test ParseError is an Exception subclass."""
        from praisonaiagents.skills.models import ParseError
        
        assert issubclass(ParseError, Exception)


class TestValidationError:
    """Tests for ValidationError exception."""
    
    def test_validation_error_message(self):
        """Test ValidationError stores message correctly."""
        from praisonaiagents.skills.models import ValidationError
        
        error = ValidationError("Missing required field: name")
        
        assert str(error) == "Missing required field: name"
    
    def test_validation_error_is_exception(self):
        """Test ValidationError is an Exception subclass."""
        from praisonaiagents.skills.models import ValidationError
        
        assert issubclass(ValidationError, Exception)
