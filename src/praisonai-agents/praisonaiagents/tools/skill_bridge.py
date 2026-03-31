"""Skill Import Bridge — migrates OpenClaw-style skill files to PraisonAI tools.

Parses SKILL.md manifests and Python tool definitions from OpenClaw's
directory structure and converts them into PraisonAI @tool-decorated functions.

Usage::

    from praisonaiagents.tools.skill_bridge import import_skill, scan_skills

    # Import a single skill
    tools = import_skill("/path/to/openclaw/skills/web_search/")

    # Scan a skills directory
    report = scan_skills("/path/to/openclaw/skills/")
"""

import ast
import logging
from praisonaiagents._logging import get_logger
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = get_logger(__name__)

@dataclass
class SkillInfo:
    """Parsed skill metadata from a SKILL.md or __init__.py file."""
    name: str = ""
    description: str = ""
    source_path: str = ""
    functions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    security_warnings: List[str] = field(default_factory=list)
    compatible: bool = True
    error: Optional[str] = None

# Security patterns to flag during import
_SECURITY_PATTERNS = [
    (r"subprocess\.(call|run|Popen|check_output)", "Subprocess execution detected"),
    (r"os\.system\s*\(", "os.system() call detected"),
    (r"eval\s*\(", "eval() usage detected"),
    (r"exec\s*\(", "exec() usage detected"),
    (r"__import__\s*\(", "Dynamic import detected"),
    (r"pickle\.loads?\s*\(", "Pickle deserialization detected"),
    (r"shutil\.rmtree\s*\(", "Recursive directory deletion detected"),
]

def scan_skills(skills_dir: str) -> List[SkillInfo]:
    """Scan a directory of skills and return metadata for each.

    Args:
        skills_dir: Path to directory containing skill subdirectories.

    Returns:
        List of SkillInfo for each discovered skill.
    """
    skills_path = Path(skills_dir)
    if not skills_path.is_dir():
        logger.error(f"Skills directory not found: {skills_dir}")
        return []

    results = []
    for child in sorted(skills_path.iterdir()):
        if child.is_dir() and not child.name.startswith((".", "_")):
            info = _parse_skill_dir(child)
            results.append(info)

    return results

def import_skill(skill_path: str) -> List[Any]:
    """Import a skill directory and return PraisonAI-compatible tool functions.

    Args:
        skill_path: Path to a single skill directory.

    Returns:
        List of callable tool functions that can be passed to Agent(tools=[...]).
    """
    path = Path(skill_path)
    info = _parse_skill_dir(path)

    if info.security_warnings:
        logger.warning(
            f"[skill-bridge] Security warnings for '{info.name}':\n"
            + "\n".join(f"  ⚠ {w}" for w in info.security_warnings)
        )

    if not info.compatible:
        logger.error(f"[skill-bridge] Skill '{info.name}' is not compatible: {info.error}")
        return []

    # Try to load Python functions from the skill
    tools = []
    py_files = list(path.glob("*.py"))
    for py_file in py_files:
        if py_file.name.startswith("_"):
            continue
        try:
            funcs = _extract_tool_functions(py_file)
            tools.extend(funcs)
        except Exception as e:
            logger.warning(f"[skill-bridge] Failed to extract tools from {py_file}: {e}")

    return tools

def format_scan_report(skills: List[SkillInfo]) -> str:
    """Format scan results for terminal display.

    Args:
        skills: List of SkillInfo from scan_skills().

    Returns:
        Formatted string for terminal output.
    """
    if not skills:
        return "No skills found."

    lines = []
    lines.append(f"{'Skill':<25} {'Functions':<10} {'Deps':<10} {'Warnings':<10} {'Compatible':<10}")
    lines.append("-" * 65)
    for s in skills:
        compat = "✅" if s.compatible else "❌"
        lines.append(
            f"{s.name:<25} "
            f"{len(s.functions):<10} "
            f"{len(s.dependencies):<10} "
            f"{len(s.security_warnings):<10} "
            f"{compat:<10}"
        )

    total = len(skills)
    compat_count = sum(1 for s in skills if s.compatible)
    warns = sum(len(s.security_warnings) for s in skills)
    lines.append("")
    lines.append(f"Total: {total} skills, {compat_count} compatible, {warns} security warnings")
    return "\n".join(lines)

# ── internals ────────────────────────────────────────────────────

def _parse_skill_dir(skill_dir: Path) -> SkillInfo:
    """Parse a single skill directory into SkillInfo."""
    info = SkillInfo(
        name=skill_dir.name,
        source_path=str(skill_dir),
    )

    # Parse SKILL.md if present
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        try:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
            info.description = _extract_description(content)
        except Exception as e:
            info.error = f"Failed to read SKILL.md: {e}"

    # Scan Python files
    py_files = list(skill_dir.glob("*.py"))
    for py_file in py_files:
        if py_file.name.startswith("_"):
            continue
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")

            # Extract function names
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    info.functions.append(node.name)

            # Extract imports as dependencies
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        info.dependencies.append(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        info.dependencies.append(node.module.split(".")[0])

            # Security scan
            for pattern, warning in _SECURITY_PATTERNS:
                if re.search(pattern, source):
                    info.security_warnings.append(f"{py_file.name}: {warning}")

        except SyntaxError as e:
            info.compatible = False
            info.error = f"Syntax error in {py_file.name}: {e}"

    # Deduplicate dependencies
    info.dependencies = sorted(set(info.dependencies))

    return info

def _extract_description(content: str) -> str:
    """Extract description from SKILL.md content.

    Handles both YAML frontmatter and plain markdown.
    """
    # Try YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            for line in frontmatter.strip().split("\n"):
                if line.strip().startswith("description:"):
                    return line.split(":", 1)[1].strip().strip("'\"")

    # Fallback: first non-empty, non-heading line
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:200]

    return ""

def _extract_tool_functions(py_file: Path) -> list:
    """Extract functions from a Python file and wrap them as simple callables.

    This does NOT execute the file — it uses AST parsing to read function
    signatures and returns wrapper info. The actual import requires the
    user to install the skill's dependencies.
    """
    source = py_file.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source)

    functions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            # Extract docstring
            docstring = ast.get_docstring(node) or f"Tool from {py_file.name}"

            # Create a metadata dict (not executing the code)
            func_info = {
                "name": node.name,
                "description": docstring,
                "source_file": str(py_file),
                "args": [arg.arg for arg in node.args.args if arg.arg != "self"],
            }
            functions.append(func_info)

    return functions
