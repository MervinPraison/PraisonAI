"""Tests for Agent Skills loader."""

from pathlib import Path
import tempfile


class TestSkillLoader:
    """Tests for SkillLoader class."""
    
    def test_load_metadata_valid_skill(self):
        """Test loading metadata from valid skill."""
        from praisonaiagents.skills.loader import SkillLoader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

# Instructions
""")
            
            loader = SkillLoader()
            skill = loader.load_metadata(str(skill_dir))
            
            assert skill is not None
            assert skill.properties.name == "test-skill"
            assert skill.instructions is None  # Not activated yet
    
    def test_load_metadata_nonexistent(self):
        """Test loading from nonexistent path."""
        from praisonaiagents.skills.loader import SkillLoader
        
        loader = SkillLoader()
        skill = loader.load_metadata("/nonexistent/path")
        
        assert skill is None
    
    def test_activate_skill(self):
        """Test activating a skill loads instructions."""
        from praisonaiagents.skills.loader import SkillLoader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

# Instructions

Follow these steps:
1. Do this
2. Do that
""")
            
            loader = SkillLoader()
            skill = loader.load_metadata(str(skill_dir))
            
            assert not skill.is_activated
            
            result = loader.activate(skill)
            
            assert result is True
            assert skill.is_activated
            assert "Follow these steps" in skill.instructions
    
    def test_activate_already_activated(self):
        """Test activating already activated skill returns True."""
        from praisonaiagents.skills.loader import SkillLoader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

Instructions.
""")
            
            loader = SkillLoader()
            skill = loader.load_metadata(str(skill_dir))
            loader.activate(skill)
            
            # Activate again
            result = loader.activate(skill)
            
            assert result is True
    
    def test_load_scripts(self):
        """Test loading scripts from skill."""
        from praisonaiagents.skills.loader import SkillLoader
        
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
            (scripts_dir / "utils.sh").write_text("echo 'hello'")
            
            loader = SkillLoader()
            skill = loader.load_metadata(str(skill_dir))
            scripts = loader.load_scripts(skill)
            
            assert "helper.py" in scripts
            assert "utils.sh" in scripts
            assert "print('hello')" in scripts["helper.py"]
    
    def test_load_references(self):
        """Test loading references from skill."""
        from praisonaiagents.skills.loader import SkillLoader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            # Create references directory
            refs_dir = skill_dir / "references"
            refs_dir.mkdir()
            (refs_dir / "api.md").write_text("# API Reference")
            
            loader = SkillLoader()
            skill = loader.load_metadata(str(skill_dir))
            refs = loader.load_references(skill)
            
            assert "api.md" in refs
            assert "# API Reference" in refs["api.md"]
    
    def test_load_assets(self):
        """Test loading assets from skill."""
        from praisonaiagents.skills.loader import SkillLoader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            # Create assets directory
            assets_dir = skill_dir / "assets"
            assets_dir.mkdir()
            (assets_dir / "template.json").write_text("{}")
            
            loader = SkillLoader()
            skill = loader.load_metadata(str(skill_dir))
            assets = loader.load_assets(skill)
            
            assert "template.json" in assets
            # Path may be resolved differently on macOS (/var vs /private/var)
            assert assets["template.json"].endswith("test-skill/assets/template.json")
    
    def test_class_method_load(self):
        """Test convenience class method load."""
        from praisonaiagents.skills.loader import SkillLoader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

Instructions here.
""")
            
            skill = SkillLoader.load(str(skill_dir), activate=True)
            
            assert skill is not None
            assert skill.is_activated
            assert "Instructions here" in skill.instructions


class TestLoadedSkill:
    """Tests for LoadedSkill dataclass."""
    
    def test_metadata_property(self):
        """Test metadata property returns SkillMetadata."""
        from praisonaiagents.skills.loader import SkillLoader
        from praisonaiagents.skills.models import SkillMetadata
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---
""")
            
            loader = SkillLoader()
            skill = loader.load_metadata(str(skill_dir))
            
            meta = skill.metadata
            
            assert isinstance(meta, SkillMetadata)
            assert meta.name == "test-skill"
            assert meta.description == "A test skill"
    
    def test_is_activated_property(self):
        """Test is_activated property."""
        from praisonaiagents.skills.loader import SkillLoader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

Body.
""")
            
            loader = SkillLoader()
            skill = loader.load_metadata(str(skill_dir))
            
            assert skill.is_activated is False
            
            loader.activate(skill)
            
            assert skill.is_activated is True
    
    def test_load_utf8_content(self):
        """Test loading UTF-8 encoded skill content.
        
        Regression test for Windows encoding issues (Issue #1695).
        Tests UTF-8 handling in SKILL.md body, scripts, and references.
        """
        from praisonaiagents.skills.loader import SkillLoader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "utf8-loader-test"
            skill_dir.mkdir()
            
            # Create SKILL.md with UTF-8 characters
            skill_content = """---
name: utf8-loader-test
description: Loader test with UTF-8 — em dashes — and more
---

# UTF-8 Instructions

This skill handles UTF-8 content:
- Smart quotes: "hello" and 'world'
- Em dash: —
- Arrows: → ← ↑ ↓
- Accented: café, naïve, résumé
- Emoji: 🔥 📝 ✨
"""
            
            with open(skill_dir / "SKILL.md", 'w', encoding='utf-8') as f:
                f.write(skill_content)
            
            # Create scripts directory with UTF-8 script
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()
            
            script_content = """#!/bin/bash
# Script with UTF-8: café processing → résumé generation
echo "Processing naïve input with émphasis"
"""
            
            with open(scripts_dir / "process.sh", 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            # Create references directory with UTF-8 content
            refs_dir = skill_dir / "references"
            refs_dir.mkdir()
            
            ref_content = """Reference with UTF-8:
Café automation guide — step by step
Arrow symbols: → ← ↑ ↓
Special chars: "smart quotes" and émphasis
"""
            
            with open(refs_dir / "readme.txt", 'w', encoding='utf-8') as f:
                f.write(ref_content)
            
            # Test loading and activation
            loader = SkillLoader()
            skill = loader.load_metadata(str(skill_dir))
            
            assert skill is not None
            assert "—" in skill.properties.description  # UTF-8 in metadata
            
            # Test activation (loads SKILL.md body)
            success = loader.activate(skill)
            assert success is True
            assert "—" in skill.instructions  # UTF-8 in instructions
            assert "café" in skill.instructions
            assert "🔥" in skill.instructions  # Emoji
            
            # Test script loading
            scripts = loader.load_scripts(skill)
            assert "process.sh" in scripts
            script_text = scripts["process.sh"]
            assert "café" in script_text
            assert "résumé" in script_text
            assert "naïve" in script_text
            
            # Test references loading
            refs = loader.load_references(skill)
            assert "readme.txt" in refs
            ref_text = refs["readme.txt"]
            assert "Café" in ref_text
            assert "—" in ref_text
            assert "émphasis" in ref_text
