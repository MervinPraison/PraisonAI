"""Tests for Skill Import Bridge (F5).

Tests scanning, parsing, and security analysis of OpenClaw-style skill directories.
"""

import os
import pytest
from pathlib import Path


class TestSkillInfo:
    """Test SkillInfo dataclass."""

    def test_defaults(self):
        from praisonaiagents.tools.skill_bridge import SkillInfo
        info = SkillInfo()
        assert info.name == ""
        assert info.compatible is True
        assert info.functions == []
        assert info.security_warnings == []


class TestScanSkills:
    """Test scanning a directory of skills."""

    def test_scan_empty_dir(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import scan_skills
        results = scan_skills(str(tmp_path))
        assert results == []

    def test_scan_single_skill(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import scan_skills
        skill_dir = tmp_path / "web_search"
        skill_dir.mkdir()
        (skill_dir / "tool.py").write_text("def search(query: str) -> str:\n    \"\"\"Search the web.\"\"\"\n    return query\n")
        results = scan_skills(str(tmp_path))
        assert len(results) == 1
        assert results[0].name == "web_search"
        assert "search" in results[0].functions

    def test_scan_multiple_skills(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import scan_skills
        for name in ["skill_a", "skill_b", "skill_c"]:
            d = tmp_path / name
            d.mkdir()
            (d / "tool.py").write_text(f"def {name}_func(): pass\n")
        results = scan_skills(str(tmp_path))
        assert len(results) == 3

    def test_scan_ignores_hidden_dirs(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import scan_skills
        hidden = tmp_path / ".hidden_skill"
        hidden.mkdir()
        (hidden / "tool.py").write_text("def hidden(): pass\n")
        results = scan_skills(str(tmp_path))
        assert len(results) == 0

    def test_scan_nonexistent_dir(self):
        from praisonaiagents.tools.skill_bridge import scan_skills
        results = scan_skills("/nonexistent/path")
        assert results == []


class TestSkillMdParsing:
    """Test SKILL.md frontmatter/description parsing."""

    def test_yaml_frontmatter(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import scan_skills
        skill = tmp_path / "my_skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\ndescription: Search the web for information\n---\n# My Skill\n")
        (skill / "search.py").write_text("def search(): pass\n")
        results = scan_skills(str(tmp_path))
        assert results[0].description == "Search the web for information"

    def test_plain_markdown(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import scan_skills
        skill = tmp_path / "my_skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("# My Skill\nThis skill does something cool.\n")
        (skill / "tool.py").write_text("def cool(): pass\n")
        results = scan_skills(str(tmp_path))
        assert "something cool" in results[0].description


class TestSecurityScanner:
    """Test security pattern detection."""

    def test_detects_subprocess(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import scan_skills
        skill = tmp_path / "dangerous"
        skill.mkdir()
        (skill / "tool.py").write_text("import subprocess\ndef run(cmd):\n    subprocess.run(cmd)\n")
        results = scan_skills(str(tmp_path))
        assert len(results[0].security_warnings) > 0
        assert any("Subprocess" in w for w in results[0].security_warnings)

    def test_detects_eval(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import scan_skills
        skill = tmp_path / "eval_skill"
        skill.mkdir()
        (skill / "tool.py").write_text("def execute(code):\n    return eval(code)\n")
        results = scan_skills(str(tmp_path))
        assert any("eval" in w for w in results[0].security_warnings)

    def test_detects_os_system(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import scan_skills
        skill = tmp_path / "os_skill"
        skill.mkdir()
        (skill / "tool.py").write_text("import os\ndef run(cmd):\n    os.system(cmd)\n")
        results = scan_skills(str(tmp_path))
        assert any("os.system" in w for w in results[0].security_warnings)

    def test_safe_skill_no_warnings(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import scan_skills
        skill = tmp_path / "safe"
        skill.mkdir()
        (skill / "tool.py").write_text("def greet(name: str) -> str:\n    return f'Hello, {name}'\n")
        results = scan_skills(str(tmp_path))
        assert len(results[0].security_warnings) == 0


class TestImportSkill:
    """Test importing skills as tool metadata."""

    def test_import_extracts_functions(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import import_skill
        skill = tmp_path / "my_skill"
        skill.mkdir()
        (skill / "tool.py").write_text(
            "def search(query: str) -> str:\n"
            "    \"\"\"Search the web.\"\"\"\n"
            "    return query\n"
            "\n"
            "def fetch(url: str) -> str:\n"
            "    \"\"\"Fetch a URL.\"\"\"\n"
            "    return url\n"
        )
        tools = import_skill(str(skill))
        assert len(tools) == 2
        names = [t["name"] for t in tools]
        assert "search" in names
        assert "fetch" in names

    def test_import_captures_docstrings(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import import_skill
        skill = tmp_path / "my_skill"
        skill.mkdir()
        (skill / "tool.py").write_text("def calc(x: int) -> int:\n    \"\"\"Calculate something.\"\"\"\n    return x\n")
        tools = import_skill(str(skill))
        assert tools[0]["description"] == "Calculate something."

    def test_import_skips_private(self, tmp_path):
        from praisonaiagents.tools.skill_bridge import import_skill
        skill = tmp_path / "my_skill"
        skill.mkdir()
        (skill / "tool.py").write_text("def public(): pass\ndef _private(): pass\n")
        tools = import_skill(str(skill))
        names = [t["name"] for t in tools]
        assert "public" in names
        assert "_private" not in names


class TestFormatScanReport:
    """Test terminal report formatting."""

    def test_format_empty(self):
        from praisonaiagents.tools.skill_bridge import format_scan_report
        assert format_scan_report([]) == "No skills found."

    def test_format_with_skills(self):
        from praisonaiagents.tools.skill_bridge import SkillInfo, format_scan_report
        skills = [
            SkillInfo(name="web_search", functions=["search"], compatible=True),
            SkillInfo(name="dangerous", functions=["run"], security_warnings=["eval"], compatible=False),
        ]
        result = format_scan_report(skills)
        assert "web_search" in result
        assert "dangerous" in result
        assert "2 skills" in result
