"""Tests for Agent Skills discovery."""

from pathlib import Path
import tempfile


class TestGetDefaultSkillDirs:
    """Tests for get_default_skill_dirs function."""
    
    def test_returns_list(self):
        """Test that function returns a list."""
        from praisonaiagents.skills.discovery import get_default_skill_dirs
        
        result = get_default_skill_dirs()
        
        assert isinstance(result, list)
    
    def test_returns_path_objects(self):
        """Test that returned items are Path objects."""
        from praisonaiagents.skills.discovery import get_default_skill_dirs
        
        result = get_default_skill_dirs()
        
        for item in result:
            assert isinstance(item, Path)


class TestDiscoverSkills:
    """Tests for discover_skills function."""
    
    def test_discover_empty_directory(self):
        """Test discovering skills in empty directory."""
        from praisonaiagents.skills.discovery import discover_skills
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = discover_skills([tmpdir], include_defaults=False)
            
            assert result == []
    
    def test_discover_single_skill(self):
        """Test discovering a single valid skill."""
        from praisonaiagents.skills.discovery import discover_skills
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a skill directory
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill for discovery
---

# Test Skill
""")
            
            result = discover_skills([tmpdir], include_defaults=False)
            
            assert len(result) == 1
            assert result[0].name == "test-skill"
            assert result[0].description == "A test skill for discovery"
    
    def test_discover_multiple_skills(self):
        """Test discovering multiple skills."""
        from praisonaiagents.skills.discovery import discover_skills
        
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
            
            result = discover_skills([tmpdir], include_defaults=False)
            
            assert len(result) == 2
            names = {s.name for s in result}
            assert "skill-one" in names
            assert "skill-two" in names
    
    def test_discover_skips_invalid_skills(self):
        """Test that invalid skills are skipped."""
        from praisonaiagents.skills.discovery import discover_skills
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create valid skill
            valid_dir = Path(tmpdir) / "valid-skill"
            valid_dir.mkdir()
            (valid_dir / "SKILL.md").write_text("""---
name: valid-skill
description: A valid skill
---
""")
            
            # Create invalid skill (no SKILL.md)
            invalid_dir = Path(tmpdir) / "invalid-skill"
            invalid_dir.mkdir()
            
            result = discover_skills([tmpdir], include_defaults=False)
            
            assert len(result) == 1
            assert result[0].name == "valid-skill"
    
    def test_discover_from_multiple_directories(self):
        """Test discovering from multiple directories."""
        from praisonaiagents.skills.discovery import discover_skills
        
        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                # Create skill in first directory
                skill1_dir = Path(tmpdir1) / "skill-a"
                skill1_dir.mkdir()
                (skill1_dir / "SKILL.md").write_text("""---
name: skill-a
description: Skill A
---
""")
                
                # Create skill in second directory
                skill2_dir = Path(tmpdir2) / "skill-b"
                skill2_dir.mkdir()
                (skill2_dir / "SKILL.md").write_text("""---
name: skill-b
description: Skill B
---
""")
                
                result = discover_skills([tmpdir1, tmpdir2], include_defaults=False)
                
                assert len(result) == 2


class TestDiscoverSkill:
    """Tests for discover_skill function (single skill)."""
    
    def test_discover_valid_skill(self):
        """Test discovering a single valid skill."""
        from praisonaiagents.skills.discovery import discover_skill
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "my-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: My skill
---
""")
            
            result = discover_skill(str(skill_dir))
            
            assert result is not None
            assert result.name == "my-skill"
    
    def test_discover_nonexistent_path(self):
        """Test discovering from nonexistent path."""
        from praisonaiagents.skills.discovery import discover_skill
        
        result = discover_skill("/nonexistent/path")
        
        assert result is None
    
    def test_discover_directory_without_skill_md(self):
        """Test discovering from directory without SKILL.md."""
        from praisonaiagents.skills.discovery import discover_skill
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = discover_skill(tmpdir)
            
            assert result is None
