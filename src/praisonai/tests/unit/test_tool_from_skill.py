"""
Tests for G-F: tool_from_skill adapter.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from praisonai.capabilities.skills import tool_from_skill


def test_tool_from_skill():
    """Test tool_from_skill adapter creates a working tool function."""
    # Create temporary skill
    with tempfile.TemporaryDirectory() as tmp_dir:
        skill_dir = Path(tmp_dir) / "test-skill"
        skill_dir.mkdir()
        
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: test-skill
description: A test skill for validation
---

# Test Skill

This skill does testing things.
Use it like: /test-skill arg1 arg2
""")
        
        # Create the tool
        tool_func = tool_from_skill(str(skill_dir))
        
        # Test tool properties
        assert tool_func.__name__ == "skill_test_skill"  # hyphens converted to underscores
        assert "test skill" in tool_func.__doc__.lower()
        
        # Test tool execution
        result = tool_func()
        assert "This skill does testing things" in result
        assert "/test-skill arg1 arg2" in result


def test_tool_from_skill_with_arguments():
    """Test tool_from_skill with arguments parameter."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        skill_dir = Path(tmp_dir) / "args-skill"
        skill_dir.mkdir()
        
        skill_md = skill_dir / "SKILL.md" 
        skill_md.write_text("""---
name: args-skill
description: Skill that uses arguments
---

Process data with arguments: $ARGUMENTS
""")
        
        tool_func = tool_from_skill(str(skill_dir))
        
        # Test with arguments
        result = tool_func("file1.txt file2.txt")
        assert "Process data with arguments" in result


def test_tool_from_skill_nonexistent_path():
    """Test tool_from_skill with nonexistent path raises error."""
    with pytest.raises(ValueError, match="Skill not found at path"):
        tool_from_skill("/nonexistent/path")


def test_tool_from_skill_no_instructions():
    """Test tool_from_skill when skill has no instructions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        skill_dir = Path(tmp_dir) / "empty-skill"
        skill_dir.mkdir()
        
        # Create skill with frontmatter but no body
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: empty-skill
description: Skill with no body
---
""")
        
        # Mock load_skill to return skill with no instructions
        with patch('praisonai.capabilities.skills.load_skill') as mock_load:
            mock_skill = type('MockSkill', (), {})()
            mock_skill.properties = type('Props', (), {'name': 'empty-skill', 'description': 'Empty skill'})()
            mock_skill.instructions = None
            mock_load.return_value = mock_skill
            
            tool_func = tool_from_skill(str(skill_dir))
            result = tool_func()
            assert "has no instructions" in result


def test_tool_from_skill_import_fallback():
    """Test tool_from_skill fallback when imports not available."""
    with patch('praisonai.capabilities.skills.load_skill', side_effect=ImportError):
        tool_func = tool_from_skill("/any/path")
        result = tool_func()
        assert "Skills not available" in result