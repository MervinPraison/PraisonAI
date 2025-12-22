"""Tests for Agent Skills parser."""

from pathlib import Path
import tempfile


class TestParseFrontmatter:
    """Tests for parse_frontmatter function."""
    
    def test_parse_valid_frontmatter(self):
        """Test parsing valid YAML frontmatter."""
        from praisonaiagents.skills.parser import parse_frontmatter
        
        content = """---
name: test-skill
description: A test skill for unit testing
---

# Test Skill

Instructions go here.
"""
        metadata, body = parse_frontmatter(content)
        
        assert metadata["name"] == "test-skill"
        assert metadata["description"] == "A test skill for unit testing"
        assert "# Test Skill" in body
    
    def test_parse_frontmatter_with_optional_fields(self):
        """Test parsing frontmatter with all optional fields."""
        from praisonaiagents.skills.parser import parse_frontmatter
        
        content = """---
name: pdf-processing
description: Extract text from PDFs
license: Apache-2.0
compatibility: Requires pypdf
allowed-tools: Read Grep
metadata:
  author: test-org
  version: "1.0"
---

Body content.
"""
        metadata, body = parse_frontmatter(content)
        
        assert metadata["name"] == "pdf-processing"
        assert metadata["license"] == "Apache-2.0"
        assert metadata["compatibility"] == "Requires pypdf"
        assert metadata["allowed-tools"] == "Read Grep"
        assert metadata["metadata"]["author"] == "test-org"
        assert metadata["metadata"]["version"] == "1.0"
    
    def test_parse_frontmatter_missing_opening_delimiter(self):
        """Test error when frontmatter doesn't start with ---."""
        from praisonaiagents.skills.parser import parse_frontmatter
        from praisonaiagents.skills.models import ParseError
        
        content = """name: test-skill
description: Missing opening delimiter
---

Body content.
"""
        try:
            parse_frontmatter(content)
            assert False, "Should have raised ParseError"
        except ParseError as e:
            assert "must start with" in str(e).lower() or "---" in str(e)
    
    def test_parse_frontmatter_missing_closing_delimiter(self):
        """Test error when frontmatter is not closed."""
        from praisonaiagents.skills.parser import parse_frontmatter
        from praisonaiagents.skills.models import ParseError
        
        content = """---
name: test-skill
description: Missing closing delimiter

Body content without closing delimiter.
"""
        try:
            parse_frontmatter(content)
            assert False, "Should have raised ParseError"
        except ParseError as e:
            assert "closed" in str(e).lower() or "---" in str(e)
    
    def test_parse_frontmatter_invalid_yaml(self):
        """Test error when YAML is invalid."""
        from praisonaiagents.skills.parser import parse_frontmatter
        from praisonaiagents.skills.models import ParseError
        
        content = """---
name: test-skill
description: [invalid yaml
  - missing bracket
---

Body content.
"""
        try:
            parse_frontmatter(content)
            assert False, "Should have raised ParseError"
        except ParseError as e:
            assert "yaml" in str(e).lower() or "invalid" in str(e).lower()
    
    def test_parse_frontmatter_empty_body(self):
        """Test parsing when body is empty."""
        from praisonaiagents.skills.parser import parse_frontmatter
        
        content = """---
name: test-skill
description: A skill with no body
---
"""
        metadata, body = parse_frontmatter(content)
        
        assert metadata["name"] == "test-skill"
        assert body.strip() == ""


class TestFindSkillMd:
    """Tests for find_skill_md function."""
    
    def test_find_skill_md_uppercase(self):
        """Test finding SKILL.md (uppercase)."""
        from praisonaiagents.skills.parser import find_skill_md
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("---\nname: test\ndescription: test\n---\n")
            
            result = find_skill_md(skill_dir)
            
            assert result is not None
            assert result.name == "SKILL.md"
    
    def test_find_skill_md_lowercase(self):
        """Test finding skill.md (lowercase) as fallback."""
        from praisonaiagents.skills.parser import find_skill_md
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            skill_md = skill_dir / "skill.md"
            skill_md.write_text("---\nname: test\ndescription: test\n---\n")
            
            result = find_skill_md(skill_dir)
            
            assert result is not None
            # On case-insensitive filesystems (macOS), SKILL.md may match skill.md
            assert result.name.lower() == "skill.md"
    
    def test_find_skill_md_prefers_uppercase(self):
        """Test that SKILL.md is preferred over skill.md."""
        from praisonaiagents.skills.parser import find_skill_md
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            (skill_dir / "SKILL.md").write_text("uppercase")
            (skill_dir / "skill.md").write_text("lowercase")
            
            result = find_skill_md(skill_dir)
            
            assert result is not None
            assert result.name == "SKILL.md"
    
    def test_find_skill_md_not_found(self):
        """Test returning None when no SKILL.md exists."""
        from praisonaiagents.skills.parser import find_skill_md
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            
            result = find_skill_md(skill_dir)
            
            assert result is None


class TestReadProperties:
    """Tests for read_properties function."""
    
    def test_read_properties_valid_skill(self):
        """Test reading properties from a valid skill directory."""
        from praisonaiagents.skills.parser import read_properties
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill for unit testing
---

# Test Skill
""")
            
            props = read_properties(skill_dir)
            
            assert props.name == "test-skill"
            assert props.description == "A test skill for unit testing"
    
    def test_read_properties_with_all_fields(self):
        """Test reading properties with all optional fields."""
        from praisonaiagents.skills.parser import read_properties
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "pdf-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: pdf-skill
description: Process PDF files
license: MIT
compatibility: Requires pypdf
allowed-tools: Read Write
metadata:
  author: test
  version: "2.0"
---

Instructions.
""")
            
            props = read_properties(skill_dir)
            
            assert props.name == "pdf-skill"
            assert props.license == "MIT"
            assert props.compatibility == "Requires pypdf"
            assert props.allowed_tools == "Read Write"
            assert props.metadata["author"] == "test"
    
    def test_read_properties_missing_skill_md(self):
        """Test error when SKILL.md is missing."""
        from praisonaiagents.skills.parser import read_properties
        from praisonaiagents.skills.models import ParseError
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "empty-skill"
            skill_dir.mkdir()
            
            try:
                read_properties(skill_dir)
                assert False, "Should have raised ParseError"
            except ParseError as e:
                assert "not found" in str(e).lower() or "skill.md" in str(e).lower()
    
    def test_read_properties_missing_name(self):
        """Test error when name field is missing."""
        from praisonaiagents.skills.parser import read_properties
        from praisonaiagents.skills.models import ValidationError
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "no-name"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
description: Missing name field
---

Body.
""")
            
            try:
                read_properties(skill_dir)
                assert False, "Should have raised ValidationError"
            except ValidationError as e:
                assert "name" in str(e).lower()
    
    def test_read_properties_missing_description(self):
        """Test error when description field is missing."""
        from praisonaiagents.skills.parser import read_properties
        from praisonaiagents.skills.models import ValidationError
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "no-desc"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: no-desc
---

Body.
""")
            
            try:
                read_properties(skill_dir)
                assert False, "Should have raised ValidationError"
            except ValidationError as e:
                assert "description" in str(e).lower()
