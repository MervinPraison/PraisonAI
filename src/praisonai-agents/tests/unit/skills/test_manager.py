"""Tests for Agent Skills manager."""

from pathlib import Path
import tempfile


class TestSkillManager:
    """Tests for SkillManager class."""
    
    def test_init_empty(self):
        """Test initializing empty manager."""
        from praisonaiagents.skills.manager import SkillManager
        
        manager = SkillManager()
        
        assert len(manager) == 0
        assert manager.skill_names == []
    
    def test_discover_skills(self):
        """Test discovering skills from directory."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a skill
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            manager = SkillManager()
            count = manager.discover([tmpdir], include_defaults=False)
            
            assert count == 1
            assert len(manager) == 1
            assert "test-skill" in manager
    
    def test_add_skill(self):
        """Test adding a single skill."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "my-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: My skill
---
""")
            
            manager = SkillManager()
            skill = manager.add_skill(str(skill_dir))
            
            assert skill is not None
            assert skill.properties.name == "my-skill"
            assert "my-skill" in manager
    
    def test_get_skill(self):
        """Test getting a skill by name."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            
            skill = manager.get_skill("test-skill")
            
            assert skill is not None
            assert skill.properties.name == "test-skill"
    
    def test_get_skill_not_found(self):
        """Test getting nonexistent skill."""
        from praisonaiagents.skills.manager import SkillManager
        
        manager = SkillManager()
        skill = manager.get_skill("nonexistent")
        
        assert skill is None
    
    def test_activate_by_name(self):
        """Test activating skill by name."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

# Instructions
""")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            
            result = manager.activate_by_name("test-skill")
            
            assert result is True
            skill = manager.get_skill("test-skill")
            assert skill.is_activated
    
    def test_get_available_skills(self):
        """Test getting available skills metadata."""
        from praisonaiagents.skills.manager import SkillManager
        from praisonaiagents.skills.models import SkillMetadata
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            
            skills = manager.get_available_skills()
            
            assert len(skills) == 1
            assert isinstance(skills[0], SkillMetadata)
            assert skills[0].name == "test-skill"
    
    def test_to_prompt(self):
        """Test generating prompt XML."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            
            prompt = manager.to_prompt()
            
            assert "<available_skills>" in prompt
            assert "test-skill" in prompt
            assert "A test skill" in prompt
    
    def test_get_instructions(self):
        """Test getting instructions for a skill."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

# Instructions

Do this and that.
""")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            
            instructions = manager.get_instructions("test-skill")
            
            assert instructions is not None
            assert "Do this and that" in instructions
    
    def test_load_resources(self):
        """Test loading resources for a skill."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            # Create scripts directory
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "helper.py").write_text("print('hello')")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            
            result = manager.load_resources("test-skill")
            
            assert result is True
            skill = manager.get_skill("test-skill")
            assert skill.resources_loaded
    
    def test_clear(self):
        """Test clearing all skills."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            manager = SkillManager()
            manager.add_skill(str(skill_dir))
            assert len(manager) == 1
            
            manager.clear()
            
            assert len(manager) == 0
    
    def test_iteration(self):
        """Test iterating over skills."""
        from praisonaiagents.skills.manager import SkillManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two skills
            for name in ["skill-a", "skill-b"]:
                skill_dir = Path(tmpdir) / name
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(f"""---
name: {name}
description: Skill {name}
---
""")
            
            manager = SkillManager()
            manager.discover([tmpdir], include_defaults=False)
            
            names = [s.properties.name for s in manager]
            
            assert len(names) == 2
            assert "skill-a" in names
            assert "skill-b" in names
