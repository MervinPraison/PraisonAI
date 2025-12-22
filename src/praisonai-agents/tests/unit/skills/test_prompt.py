"""Tests for Agent Skills prompt generation."""

from pathlib import Path
import tempfile


class TestToPrompt:
    """Tests for to_prompt function (XML generation)."""
    
    def test_to_prompt_empty_list(self):
        """Test generating prompt with no skills."""
        from praisonaiagents.skills.prompt import to_prompt
        
        result = to_prompt([])
        
        assert "<available_skills>" in result
        assert "</available_skills>" in result
    
    def test_to_prompt_single_skill(self):
        """Test generating prompt with one skill."""
        from praisonaiagents.skills.prompt import to_prompt
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill for prompt generation
---

# Test Skill
""")
            
            result = to_prompt([skill_dir])
            
            assert "<available_skills>" in result
            assert "</available_skills>" in result
            assert "<skill>" in result
            assert "</skill>" in result
            assert "<name>" in result
            assert "test-skill" in result
            assert "<description>" in result
            assert "A test skill for prompt generation" in result
            assert "<location>" in result
    
    def test_to_prompt_multiple_skills(self):
        """Test generating prompt with multiple skills."""
        from praisonaiagents.skills.prompt import to_prompt
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create first skill
            skill1_dir = Path(tmpdir) / "skill-one"
            skill1_dir.mkdir()
            (skill1_dir / "SKILL.md").write_text("""---
name: skill-one
description: First skill
---
""")
            
            # Create second skill
            skill2_dir = Path(tmpdir) / "skill-two"
            skill2_dir.mkdir()
            (skill2_dir / "SKILL.md").write_text("""---
name: skill-two
description: Second skill
---
""")
            
            result = to_prompt([skill1_dir, skill2_dir])
            
            assert result.count("<skill>") == 2
            assert result.count("</skill>") == 2
            assert "skill-one" in result
            assert "skill-two" in result
            assert "First skill" in result
            assert "Second skill" in result
    
    def test_to_prompt_escapes_html(self):
        """Test that special characters are HTML escaped."""
        from praisonaiagents.skills.prompt import to_prompt
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "escape-test"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: escape-test
description: Test <script> & "quotes" handling
---
""")
            
            result = to_prompt([skill_dir])
            
            # Should escape < > & "
            assert "<script>" not in result or "&lt;script&gt;" in result
            assert "&amp;" in result or "& " not in result
    
    def test_to_prompt_includes_location(self):
        """Test that location points to SKILL.md file."""
        from praisonaiagents.skills.prompt import to_prompt
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "location-test"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: location-test
description: Test location field
---
""")
            
            result = to_prompt([skill_dir])
            
            assert "<location>" in result
            assert "SKILL.md" in result
            assert "</location>" in result


class TestGenerateSkillsXml:
    """Tests for generate_skills_xml helper function."""
    
    def test_generate_skills_xml_from_metadata_list(self):
        """Test generating XML from SkillMetadata list."""
        from praisonaiagents.skills.prompt import generate_skills_xml
        from praisonaiagents.skills.models import SkillMetadata
        
        skills = [
            SkillMetadata(
                name="pdf-skill",
                description="Process PDF files",
                location="/path/to/pdf-skill/SKILL.md"
            ),
            SkillMetadata(
                name="excel-skill",
                description="Process Excel files",
                location="/path/to/excel-skill/SKILL.md"
            )
        ]
        
        result = generate_skills_xml(skills)
        
        assert "<available_skills>" in result
        assert "pdf-skill" in result
        assert "excel-skill" in result
        assert "Process PDF files" in result
        assert "Process Excel files" in result
    
    def test_generate_skills_xml_empty_list(self):
        """Test generating XML with empty list."""
        from praisonaiagents.skills.prompt import generate_skills_xml
        
        result = generate_skills_xml([])
        
        assert "<available_skills>" in result
        assert "</available_skills>" in result
        assert "<skill>" not in result


class TestFormatSkillForPrompt:
    """Tests for format_skill_for_prompt helper."""
    
    def test_format_single_skill(self):
        """Test formatting a single skill for prompt."""
        from praisonaiagents.skills.prompt import format_skill_for_prompt
        from praisonaiagents.skills.models import SkillMetadata
        
        skill = SkillMetadata(
            name="test-skill",
            description="A test skill",
            location="/path/to/SKILL.md"
        )
        
        result = format_skill_for_prompt(skill)
        
        assert "<skill>" in result
        assert "</skill>" in result
        assert "<name>" in result
        assert "test-skill" in result
        assert "<description>" in result
        assert "A test skill" in result
        assert "<location>" in result
        assert "/path/to/SKILL.md" in result
